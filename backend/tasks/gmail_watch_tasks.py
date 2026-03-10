"""Celery tasks for Gmail watch registration/renewal."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery_app import celery
from config import Config
from services.supabase_service import get_supabase
from services.gmail_service import register_inbox_watch, get_profile

log = logging.getLogger(__name__)
WATCH_MIN_TTL_SECONDS = 60 * 60


def _to_utc_iso_from_epoch_ms(raw: str | int | None) -> str | None:
    if raw is None:
        return None
    try:
        epoch_ms = int(str(raw).strip())
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _watch_is_fresh(row: dict, min_ttl_seconds: int = WATCH_MIN_TTL_SECONDS) -> bool:
    if not row.get("gmail_email") or not row.get("gmail_history_id"):
        return False
    raw_exp = row.get("gmail_watch_expiration")
    if not raw_exp:
        return False
    try:
        exp = datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00"))
    except Exception:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > datetime.now(timezone.utc) + timedelta(seconds=min_ttl_seconds)


def ensure_gmail_watches_on_startup() -> dict:
    """Best-effort startup bootstrap for Gmail watches.

    Fast path: exits quickly when active integrations already have valid
    watch expiration + routing metadata.
    """
    topic_name = (Config.GMAIL_WATCH_TOPIC or "").strip()
    if not topic_name:
        log.info("gmail_watch_bootstrap_skipped reason=missing_topic")
        return {"status": "skipped", "reason": "missing_topic"}

    sb = get_supabase()
    integrations = (
        sb.table("integrations")
        .select("id, user_id, account_token, gmail_email, gmail_history_id, gmail_watch_expiration")
        .eq("provider", "gmail")
        .eq("status", "active")
        .execute()
    ).data or []

    skipped_fresh = 0
    bootstrapped = 0
    failed = 0
    log.info("gmail_watch_bootstrap_start total=%s", len(integrations))

    for row in integrations:
        integration_id = row.get("id")
        user_id = row.get("user_id")
        if _watch_is_fresh(row):
            skipped_fresh += 1
            continue
        try:
            watch = register_inbox_watch(row["account_token"], topic_name)
            history_id = watch.get("historyId")
            expiration_iso = _to_utc_iso_from_epoch_ms(watch.get("expiration"))
            update_fields: dict[str, str] = {
                "gmail_history_id": history_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if expiration_iso:
                update_fields["gmail_watch_expiration"] = expiration_iso
            if not row.get("gmail_email"):
                profile = get_profile(row["account_token"])
                if profile.get("emailAddress"):
                    update_fields["gmail_email"] = profile["emailAddress"]
            sb.table("integrations").update(update_fields).eq("id", integration_id).execute()
            bootstrapped += 1
            log.info(
                "gmail_watch_bootstrap_success integration_id=%s user_id=%s history_id=%s expiration=%s",
                integration_id,
                user_id,
                history_id,
                expiration_iso or "-",
            )
        except Exception as exc:
            failed += 1
            log.exception(
                "gmail_watch_bootstrap_failed integration_id=%s user_id=%s error=%s",
                integration_id,
                user_id,
                exc,
            )

    log.info(
        "gmail_watch_bootstrap_complete total=%s bootstrapped=%s skipped_fresh=%s failed=%s",
        len(integrations),
        bootstrapped,
        skipped_fresh,
        failed,
    )
    return {
        "status": "ok",
        "total": len(integrations),
        "bootstrapped": bootstrapped,
        "skipped_fresh": skipped_fresh,
        "failed": failed,
    }


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
        .select("id, user_id, account_token, gmail_email, gmail_watch_expiration")
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
            expiration_iso = _to_utc_iso_from_epoch_ms(expiration)
            update_fields = {
                "gmail_history_id": history_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if expiration_iso:
                update_fields["gmail_watch_expiration"] = expiration_iso
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
