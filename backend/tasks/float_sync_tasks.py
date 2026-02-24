"""Float sync tasks — fetch card + account transactions from Float API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery_app import celery
from services.supabase_service import get_supabase
from services.float_service import fetch_card_transactions, fetch_account_transactions

log = logging.getLogger(__name__)


@celery.task(name="tasks.float_sync_tasks.sync_float")
def sync_float(integration_id: str, user_id: str) -> dict:
    log.info("sync_float started integration=%s user=%s", integration_id, user_id)
    sb = get_supabase()
    sb.table("integrations").update({"status": "syncing"}).eq("id", integration_id).execute()

    try:
        int_result = (
            sb.table("integrations")
            .select("account_token, last_sync_at")
            .eq("id", integration_id)
            .single()
            .execute()
        )
        api_token = int_result.data["account_token"]
        last_sync = int_result.data.get("last_sync_at")

        card_txns = fetch_card_transactions(api_token, created_at_gte=last_sync)
        log.info("integration=%s fetched %d card transactions", integration_id, len(card_txns))

        acct_txns = fetch_account_transactions(api_token, created_at_gte=last_sync)
        log.info("integration=%s fetched %d account transactions", integration_id, len(acct_txns))

        synced = 0

        for txn in card_txns:
            remote_id = txn.get("id", "")
            if not remote_id:
                continue
            total = txn.get("total") or {}
            row = {
                "user_id": user_id,
                "integration_id": integration_id,
                "remote_id": remote_id,
                "source": "card",
                "transaction_type": txn.get("type"),
                "description": txn.get("description"),
                "amount_cents": total.get("value"),
                "currency": total.get("currency", "CAD"),
                "spender_email": (txn.get("spender") or {}).get("email"),
                "team_name": (txn.get("team") or {}).get("name"),
                "vendor_name": (txn.get("vendor") or {}).get("name"),
                "gl_code_external_id": (txn.get("gl_code") or {}).get("external_id"),
                "account_id": (txn.get("account") or {}).get("id"),
                "account_type": (txn.get("account") or {}).get("type"),
                "remote_created_at": txn.get("created_at"),
                "remote_updated_at": txn.get("updated_at"),
            }
            sb.table("float_transactions").upsert(
                row, on_conflict="integration_id,remote_id"
            ).execute()
            synced += 1

        for txn in acct_txns:
            remote_id = txn.get("id", "")
            if not remote_id:
                continue
            total = txn.get("total") or {}
            row = {
                "user_id": user_id,
                "integration_id": integration_id,
                "remote_id": remote_id,
                "source": "account",
                "transaction_type": txn.get("type"),
                "description": txn.get("description"),
                "amount_cents": total.get("value"),
                "currency": total.get("currency", "CAD"),
                "spender_email": (txn.get("spender") or {}).get("email"),
                "team_name": (txn.get("team") or {}).get("name"),
                "vendor_name": (txn.get("vendor") or {}).get("name"),
                "gl_code_external_id": None,
                "account_id": (txn.get("account") or {}).get("id"),
                "account_type": (txn.get("account") or {}).get("type"),
                "remote_created_at": txn.get("created_at"),
                "remote_updated_at": txn.get("updated_at"),
            }
            sb.table("float_transactions").upsert(
                row, on_conflict="integration_id,remote_id"
            ).execute()
            synced += 1

        now = datetime.now(timezone.utc).isoformat()
        sb.table("integrations").update({
            "status": "active",
            "last_sync_at": now,
            "last_sync_status": f"Synced {synced} Float transactions",
        }).eq("id", integration_id).execute()

        log.info("sync_float complete integration=%s synced=%d", integration_id, synced)
        return {"transactions_synced": synced}

    except Exception as exc:
        log.exception("sync_float failed integration=%s", integration_id)
        sb.table("integrations").update({
            "status": "error",
            "last_sync_status": str(exc)[:500],
        }).eq("id", integration_id).execute()
        raise
