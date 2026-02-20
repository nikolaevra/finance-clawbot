"""
Integrations routes – manage Merge.dev accounting integrations.

Endpoints:
  GET    /integrations              – list user's integrations
  POST   /integrations/link-token   – create a Merge Link token
  POST   /integrations              – save a new integration (public_token → account_token)
  POST   /integrations/<id>/sync    – trigger full data sync
  DELETE /integrations/<id>         – disconnect integration
  GET    /transactions              – list user's synced accounting transactions
"""
from __future__ import annotations

import logging
from flask import Blueprint, request, g, jsonify
from middleware.auth import require_auth

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.merge_service import (
    create_link_token,
    exchange_public_token,
    delete_account,
)

integrations_bp = Blueprint("integrations", __name__)


# ── List integrations ─────────────────────────────────────────

@integrations_bp.route("/integrations", methods=["GET"])
@require_auth
def list_integrations():
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, provider, integration_name, status, last_sync_at, last_sync_status, created_at, updated_at")
        .eq("user_id", g.user_id)
        .neq("status", "disconnected")
        .order("created_at", desc=True)
        .execute()
    )
    return jsonify(result.data)


# ── List transactions ──────────────────────────────────────────

@integrations_bp.route("/transactions", methods=["GET"])
@require_auth
def list_transactions():
    sb = get_supabase()

    # Build a lookup of integration_id → provider for the user
    int_result = (
        sb.table("integrations")
        .select("id, provider, integration_name")
        .eq("user_id", g.user_id)
        .neq("status", "disconnected")
        .execute()
    )
    integration_map = {
        row["id"]: {
            "provider": row["provider"],
            "integration_name": row["integration_name"],
        }
        for row in (int_result.data or [])
    }

    if not integration_map:
        return jsonify([])

    # Fetch transactions for this user, newest first
    result = (
        sb.table("accounting_transactions")
        .select(
            "id, integration_id, remote_id, transaction_date, number, memo, "
            "total_amount, currency, contact_name, account_name, "
            "transaction_type, remote_created_at, remote_updated_at, created_at"
        )
        .eq("user_id", g.user_id)
        .order("transaction_date", desc=True)
        .limit(500)
        .execute()
    )

    # Enrich each transaction with provider info
    transactions = []
    for txn in (result.data or []):
        int_id = txn.get("integration_id")
        meta = integration_map.get(int_id, {})
        txn["provider"] = meta.get("provider")
        txn["integration_name"] = meta.get("integration_name")
        # Remove integration_id from response (not needed by frontend)
        txn.pop("integration_id", None)
        transactions.append(txn)

    return jsonify(transactions)


# ── Create Link token ────────────────────────────────────────

@integrations_bp.route("/integrations/link-token", methods=["POST"])
@require_auth
def get_link_token():
    body = request.get_json(silent=True) or {}
    org_name = body.get("organization_name", "My Organization")
    email = body.get("email", "user@example.com")

    try:
        data = create_link_token(
            user_id=g.user_id,
            organization_name=org_name,
            user_email=email,
        )
        return jsonify(data)
    except Exception as e:
        log.exception("create_link_token failed for user=%s", g.user_id)
        return jsonify({"error": f"Failed to create link token: {e}"}), 502


# ── Create integration (exchange token & persist) ─────────────

@integrations_bp.route("/integrations", methods=["POST"])
@require_auth
def create_integration():
    body = request.get_json(silent=True) or {}
    public_token = body.get("public_token")
    if not public_token:
        return jsonify({"error": "public_token is required"}), 400

    provider = body.get("provider", "quickbooks")
    integration_name = body.get("integration_name", "QuickBooks Online")

    # Exchange for account token
    try:
        token_data = exchange_public_token(public_token)
    except Exception as e:
        log.exception("Token exchange failed for user=%s", g.user_id)
        return jsonify({"error": f"Token exchange failed: {e}"}), 502

    account_token = token_data.get("account_token", "")
    merge_account_id = token_data.get("integration", {}).get("id", "") if isinstance(token_data.get("integration"), dict) else ""

    if not account_token:
        return jsonify({"error": "No account_token returned from Merge"}), 502

    # Persist
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .insert({
            "user_id": g.user_id,
            "provider": provider,
            "integration_name": integration_name,
            "account_token": account_token,
            "merge_account_id": merge_account_id,
            "status": "active",
        })
        .execute()
    )

    row = result.data[0] if result.data else {}
    # Don't leak account_token to frontend
    row.pop("account_token", None)
    return jsonify(row), 201


# ── Sync integration data ────────────────────────────────────

@integrations_bp.route("/integrations/<integration_id>/sync", methods=["POST"])
@require_auth
def sync_integration(integration_id: str):
    sb = get_supabase()

    # Verify ownership
    int_result = (
        sb.table("integrations")
        .select("id")
        .eq("id", integration_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not int_result.data:
        return jsonify({"error": "Integration not found"}), 404

    # Dispatch to Celery for async processing
    from tasks.sync_tasks import sync_integration as sync_task
    task = sync_task.delay(integration_id, g.user_id)

    return jsonify({
        "status": "syncing",
        "task_id": task.id,
        "message": "Sync started in the background. Check back shortly.",
    })


# ── Disconnect integration ────────────────────────────────────

@integrations_bp.route("/integrations/<integration_id>", methods=["DELETE"])
@require_auth
def disconnect_integration(integration_id: str):
    sb = get_supabase()

    # Verify ownership & get account_token
    int_result = (
        sb.table("integrations")
        .select("id, account_token")
        .eq("id", integration_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not int_result.data:
        return jsonify({"error": "Integration not found"}), 404

    account_token = int_result.data["account_token"]

    # Tell Merge to revoke (best-effort)
    delete_account(account_token)

    # Clean up synced data
    sb.table("accounting_transactions").delete().eq("integration_id", integration_id).execute()
    sb.table("accounting_accounts").delete().eq("integration_id", integration_id).execute()

    # Mark disconnected (soft delete — keeps audit trail)
    sb.table("integrations").update({
        "status": "disconnected",
        "account_token": "",
    }).eq("id", integration_id).execute()

    return jsonify({"status": "disconnected"})
