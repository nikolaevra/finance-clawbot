"""
Integrations routes – manage accounting (Merge.dev), Gmail, and Float integrations.

Endpoints:
  GET    /integrations                – list user's integrations
  POST   /integrations/link-token     – create a Merge Link token (accounting)
  POST   /integrations                – save a new Merge accounting integration
  POST   /integrations/float          – connect Float via API key
  POST   /integrations/gmail/auth-url – get Google OAuth URL
  GET    /integrations/gmail/callback – handle Google OAuth redirect
  POST   /integrations/<id>/sync      – trigger full data sync
  DELETE /integrations/<id>           – disconnect integration
  GET    /transactions                – list user's synced accounting transactions
"""
from __future__ import annotations

import logging
from flask import Blueprint, request, g, jsonify, redirect
from middleware.auth import require_auth

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.merge_service import (
    create_link_token,
    exchange_public_token,
    delete_account,
)
from services.float_service import validate_token as float_validate_token

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
    integration_slug = body.get("integration_slug")

    try:
        data = create_link_token(
            user_id=g.user_id,
            organization_name=org_name,
            user_email=email,
            integration_slug=integration_slug,
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


# ── Float: connect via API key ────────────────────────────────

@integrations_bp.route("/integrations/float", methods=["POST"])
@require_auth
def connect_float():
    body = request.get_json(silent=True) or {}
    api_token = body.get("api_token", "").strip()
    if not api_token:
        return jsonify({"error": "api_token is required"}), 400

    if not float_validate_token(api_token):
        return jsonify({"error": "Invalid Float API token"}), 401

    sb = get_supabase()
    result = (
        sb.table("integrations")
        .insert({
            "user_id": g.user_id,
            "provider": "float",
            "integration_name": "Float",
            "account_token": api_token,
            "status": "active",
        })
        .execute()
    )

    row = result.data[0] if result.data else {}
    row.pop("account_token", None)
    return jsonify(row), 201


# ── Gmail: OAuth flow ─────────────────────────────────────────

@integrations_bp.route("/integrations/gmail/auth-url", methods=["POST"])
@require_auth
def gmail_auth_url():
    from services.gmail_service import get_auth_url
    try:
        url = get_auth_url(g.user_id)
        return jsonify({"auth_url": url})
    except Exception as e:
        log.exception("gmail_auth_url failed for user=%s", g.user_id)
        return jsonify({"error": f"Failed to generate auth URL: {e}"}), 500


@integrations_bp.route("/integrations/gmail/callback", methods=["GET"])
def gmail_callback():
    """Handle the Google OAuth redirect.  No @require_auth because
    the user_id is passed via the ``state`` query parameter."""
    from services.gmail_service import exchange_code
    from config import Config

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return jsonify({"error": "Missing code or state"}), 400

    user_id = state

    try:
        credentials_json = exchange_code(code)
    except Exception as e:
        log.exception("gmail exchange_code failed user=%s", user_id)
        return jsonify({"error": f"OAuth exchange failed: {e}"}), 502

    sb = get_supabase()
    result = (
        sb.table("integrations")
        .insert({
            "user_id": user_id,
            "provider": "gmail",
            "integration_name": "Gmail",
            "account_token": credentials_json,
            "status": "active",
        })
        .execute()
    )

    frontend_url = Config.FRONTEND_URL
    return redirect(f"{frontend_url}/chat/integrations?gmail=connected")


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

    int_result = (
        sb.table("integrations")
        .select("id, provider, account_token")
        .eq("id", integration_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not int_result.data:
        return jsonify({"error": "Integration not found"}), 404

    provider = int_result.data.get("provider", "")
    account_token = int_result.data.get("account_token", "")

    # Provider-specific cleanup
    if provider in ("quickbooks", "netsuite"):
        delete_account(account_token)
        sb.table("accounting_transactions").delete().eq("integration_id", integration_id).execute()
        sb.table("accounting_accounts").delete().eq("integration_id", integration_id).execute()
    elif provider == "float":
        sb.table("float_transactions").delete().eq("integration_id", integration_id).execute()
    elif provider == "gmail":
        sb.table("emails").delete().eq("integration_id", integration_id).execute()

    sb.table("integrations").update({
        "status": "disconnected",
        "account_token": "",
    }).eq("id", integration_id).execute()

    return jsonify({"status": "disconnected"})
