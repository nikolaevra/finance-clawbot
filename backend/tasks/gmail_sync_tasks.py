"""Gmail sync tasks — fetch inbox emails via the Gmail API."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from celery_app import celery
from services.supabase_service import get_supabase
from services.gmail_service import fetch_emails

log = logging.getLogger(__name__)


@celery.task(name="tasks.gmail_sync_tasks.sync_gmail")
def sync_gmail(integration_id: str, user_id: str) -> dict:
    log.info("sync_gmail started integration=%s user=%s", integration_id, user_id)
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
        credentials_json = int_result.data["account_token"]
        last_sync = int_result.data.get("last_sync_at")

        since = None
        if last_sync:
            try:
                dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                since = dt.strftime("%Y/%m/%d")
            except Exception:
                pass

        raw_emails = fetch_emails(credentials_json, max_results=200, since=since)
        log.info("integration=%s fetched %d emails", integration_id, len(raw_emails))

        synced = 0
        for email in raw_emails:
            labels = email.get("labels", [])
            row = {
                "user_id": user_id,
                "integration_id": integration_id,
                "remote_id": email["remote_id"],
                "thread_id": email.get("thread_id"),
                "subject": email.get("subject", ""),
                "from_address": email.get("from_address", ""),
                "to_addresses": email.get("to_addresses", ""),
                "date": email.get("date", ""),
                "snippet": email.get("snippet", ""),
                "body_text": email.get("body_text", ""),
                "labels": json.dumps(labels) if isinstance(labels, list) else labels,
            }
            sb.table("emails").upsert(
                row, on_conflict="integration_id,remote_id"
            ).execute()
            synced += 1

        now = datetime.now(timezone.utc).isoformat()
        sb.table("integrations").update({
            "status": "active",
            "last_sync_at": now,
            "last_sync_status": f"Synced {synced} emails",
        }).eq("id", integration_id).execute()

        log.info("sync_gmail complete integration=%s synced=%d", integration_id, synced)
        return {"emails_synced": synced}

    except Exception as exc:
        log.exception("sync_gmail failed integration=%s", integration_id)
        sb.table("integrations").update({
            "status": "error",
            "last_sync_status": str(exc)[:500],
        }).eq("id", integration_id).execute()
        raise
