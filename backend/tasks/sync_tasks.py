"""Integration sync tasks — moved from the synchronous route handler.

These tasks can be called directly by Celery Beat or composed into
workflow pipelines via the workflow engine.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery_app import celery

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.merge_service import (
    fetch_accounts as merge_fetch_accounts,
    fetch_transactions as merge_fetch_transactions,
)


# ---------------------------------------------------------------------------
# Workflow-compatible step functions (user_id, input_data) -> dict
# ---------------------------------------------------------------------------

def verify_connection(user_id: str, input_data: dict | None = None) -> dict:
    """Verify that the user has an active integration."""
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, provider, integration_name, account_token, last_sync_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise RuntimeError("No active accounting integration found")
    integration = result.data[0]
    return {
        "integration_id": integration["id"],
        "provider": integration["provider"],
        "integration_name": integration["integration_name"],
        "account_token": integration["account_token"],
        "last_sync_at": integration.get("last_sync_at"),
    }


def fetch_merge_accounts(user_id: str, input_data: dict | None = None) -> dict:
    """Fetch accounts from Merge.dev for the user's active integration."""
    input_data = input_data or {}
    account_token = input_data.get("account_token")
    if not account_token:
        conn = verify_connection(user_id)
        account_token = conn["account_token"]
        input_data.update(conn)

    raw = merge_fetch_accounts(account_token)
    return {
        **input_data,
        "accounts": raw,
        "accounts_count": len(raw),
    }


def fetch_merge_transactions(user_id: str, input_data: dict | None = None) -> dict:
    """Fetch transactions from Merge.dev for the user's active integration."""
    input_data = input_data or {}
    account_token = input_data.get("account_token")
    if not account_token:
        conn = verify_connection(user_id)
        account_token = conn["account_token"]
        input_data.update(conn)

    raw = merge_fetch_transactions(account_token)
    return {
        **input_data,
        "transactions": raw,
        "transactions_count": len(raw),
    }


def upsert_accounting_data(user_id: str, input_data: dict | None = None) -> dict:
    """Upsert fetched accounts and transactions into the database."""
    input_data = input_data or {}
    integration_id = input_data.get("integration_id")
    if not integration_id:
        raise RuntimeError("integration_id not provided in step input")

    sb = get_supabase()

    accounts_synced = 0
    for acct in input_data.get("accounts", []):
        remote_id = acct.get("id", "")
        if not remote_id:
            continue
        row = {
            "user_id": user_id,
            "integration_id": integration_id,
            "remote_id": remote_id,
            "name": acct.get("name") or "",
            "description": acct.get("description") or "",
            "classification": (acct.get("classification") or "").lower() or None,
            "type": (acct.get("type") or "").lower() or None,
            "status": (acct.get("status") or "active").lower(),
            "current_balance": acct.get("current_balance"),
            "currency": acct.get("currency") or "USD",
            "parent_account_remote_id": acct.get("parent_account") or None,
            "company": acct.get("company") or None,
            "remote_created_at": acct.get("remote_created_at"),
            "remote_updated_at": acct.get("remote_updated_at"),
        }
        sb.table("accounting_accounts").upsert(
            row, on_conflict="integration_id,remote_id"
        ).execute()
        accounts_synced += 1

    txns_synced = 0
    for txn in input_data.get("transactions", []):
        remote_id = txn.get("id", "")
        if not remote_id:
            continue

        acct_remote_id = txn.get("account") or None
        acct_name = None
        if acct_remote_id:
            acct_lookup = (
                sb.table("accounting_accounts")
                .select("name")
                .eq("integration_id", integration_id)
                .eq("remote_id", acct_remote_id)
                .limit(1)
                .execute()
            )
            if acct_lookup.data:
                acct_name = acct_lookup.data[0]["name"]

        contact_name = None
        contact_ref = txn.get("contact")
        if isinstance(contact_ref, dict):
            contact_name = contact_ref.get("name")
        elif isinstance(contact_ref, str) and contact_ref:
            contact_name = contact_ref

        row = {
            "user_id": user_id,
            "integration_id": integration_id,
            "remote_id": remote_id,
            "transaction_date": txn.get("transaction_date"),
            "number": txn.get("number") or None,
            "memo": txn.get("memo") or txn.get("description") or None,
            "total_amount": txn.get("total_amount"),
            "currency": txn.get("currency") or "USD",
            "contact_name": contact_name,
            "account_name": acct_name,
            "account_remote_id": acct_remote_id,
            "transaction_type": (txn.get("transaction_type") or "").lower() or None,
            "line_items": txn.get("line_items") or None,
            "remote_created_at": txn.get("remote_created_at"),
            "remote_updated_at": txn.get("remote_updated_at"),
        }
        sb.table("accounting_transactions").upsert(
            row, on_conflict="integration_id,remote_id"
        ).execute()
        txns_synced += 1

    now = datetime.now(timezone.utc).isoformat()
    sb.table("integrations").update({
        "status": "active",
        "last_sync_at": now,
        "last_sync_status": f"Synced {accounts_synced} accounts, {txns_synced} transactions",
    }).eq("id", integration_id).execute()

    return {
        "accounts_synced": accounts_synced,
        "transactions_synced": txns_synced,
    }


# ---------------------------------------------------------------------------
# Top-level Celery tasks (for direct invocation / Celery Beat)
# ---------------------------------------------------------------------------

def _sync_merge(integration_id: str, user_id: str) -> dict:
    """Merge.dev sync pipeline (QBO / NetSuite)."""
    sb = get_supabase()
    int_result = (
        sb.table("integrations")
        .select("account_token")
        .eq("id", integration_id)
        .single()
        .execute()
    )
    account_token = int_result.data["account_token"]

    pipe = {"integration_id": integration_id, "account_token": account_token}
    pipe = fetch_merge_accounts(user_id, pipe)
    log.info("integration=%s fetched %d accounts", integration_id, pipe.get("accounts_count", 0))
    pipe = fetch_merge_transactions(user_id, pipe)
    log.info("integration=%s fetched %d transactions", integration_id, pipe.get("transactions_count", 0))
    result = upsert_accounting_data(user_id, pipe)
    return result


@celery.task(name="tasks.sync_tasks.sync_integration")
def sync_integration(integration_id: str, user_id: str) -> dict:
    """Full sync for a single integration — dispatches to the correct
    provider-specific sync based on the ``provider`` column."""
    log.info("sync_integration started integration=%s user=%s", integration_id, user_id)
    sb = get_supabase()

    int_result = (
        sb.table("integrations")
        .select("provider")
        .eq("id", integration_id)
        .single()
        .execute()
    )
    provider = (int_result.data or {}).get("provider", "quickbooks")

    if provider in ("quickbooks", "netsuite"):
        sb.table("integrations").update({"status": "syncing"}).eq("id", integration_id).execute()
        try:
            result = _sync_merge(integration_id, user_id)
            log.info("integration=%s sync complete: %s", integration_id, result)
            return result
        except Exception as exc:
            log.exception("sync_integration failed integration=%s", integration_id)
            sb.table("integrations").update({
                "status": "error",
                "last_sync_status": str(exc)[:500],
            }).eq("id", integration_id).execute()
            raise

    elif provider == "float":
        from tasks.float_sync_tasks import sync_float
        return sync_float(integration_id, user_id)

    elif provider == "gmail":
        from tasks.gmail_sync_tasks import sync_gmail
        return sync_gmail(integration_id, user_id)

    else:
        raise RuntimeError(f"Unknown provider: {provider}")


@celery.task(name="tasks.sync_tasks.sync_all_active_integrations")
def sync_all_active_integrations() -> dict:
    """Celery Beat entry: sync every active integration."""
    log.info("sync_all_active_integrations triggered")
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, user_id")
        .eq("status", "active")
        .execute()
    )
    dispatched = 0
    for row in result.data or []:
        sync_integration.delay(row["id"], row["user_id"])
        dispatched += 1
    log.info("sync_all dispatched %d integration syncs", dispatched)
    return {"dispatched": dispatched}
