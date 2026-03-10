"""Celery tasks for Gmail watch registration/renewal."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery_app import celery
from config import Config
from services.supabase_service import get_supabase
from services.gmail_service import register_inbox_watch, get_profile

log = logging.getLogger(__name__)


@celery.task(name="tasks.gmail_watch_tasks.refresh_all_gmail_watches")
def refresh_all_gmail_watches() -> dict:
    """Renew Gmail watch for all active Gmail integrations."""
    topic_name = (Config.GMAIL_WATCH_TOPIC or "").strip()
    if not topic_name:
        log.warning("refresh_all_gmail_watches skipped: GMAIL_WATCH_TOPIC not configured")
        return {"status": "skipped", "reason": "missing_topic"}

    log.info("gmail_watch_refresh_start topic=%s", topic_name)

    sb = get_supabase()
    integrations = (
        sb.table("integrations")
        .select("id, user_id, account_token, gmail_email")
        .eq("provider", "gmail")
        .eq("status", "active")
        .execute()
    ).data or []

    renewed = 0
    failed = 0

    for row in integrations:
        integration_id = row["id"]
        user_id = row.get("user_id")
        existing_email = row.get("gmail_email") or ""
        log.info(
            "gmail_watch_refresh_attempt integration_id=%s user_id=%s has_email=%s",
            integration_id,
            user_id,
            bool(existing_email),
        )
        try:
            watch = register_inbox_watch(row["account_token"], topic_name)
            history_id = watch.get("historyId")
            expiration = watch.get("expiration")
            update_fields = {
                "gmail_history_id": history_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if not row.get("gmail_email"):
                profile = get_profile(row["account_token"])
                if profile.get("emailAddress"):
                    update_fields["gmail_email"] = profile["emailAddress"]
            sb.table("integrations").update(update_fields).eq("id", integration_id).execute()
            renewed += 1
            log.info(
                "gmail_watch_refresh_success integration_id=%s user_id=%s history_id=%s expiration=%s email_updated=%s",
                integration_id,
                user_id,
                history_id,
                expiration,
                "gmail_email" in update_fields,
            )
        except Exception as exc:
            failed += 1
            log.exception(
                "gmail_watch_refresh_failed integration_id=%s user_id=%s error=%s",
                integration_id,
                user_id,
                exc,
            )

    log.info(
        "gmail_watch_refresh_complete total=%s renewed=%s failed=%s",
        len(integrations),
        renewed,
        failed,
    )
    return {"status": "ok", "total": len(integrations), "renewed": renewed, "failed": failed}
