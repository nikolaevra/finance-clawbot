"""Generic trigger dispatcher for skill-based automations."""
from __future__ import annotations

import logging
from typing import Any

from services.supabase_service import get_supabase
from tasks.skill_automation_tasks import execute_triggered_skill_automation

log = logging.getLogger(__name__)


def _text_match(value: str | None, needle: str | None) -> bool:
    if not needle:
        return True
    return needle.lower() in (value or "").lower()


def _matches_filters(filters: dict[str, Any] | None, payload: dict[str, Any]) -> bool:
    filters = filters or {}
    inbox_only = bool(filters.get("inbox_only", True))
    if inbox_only and not bool(payload.get("is_inbox", True)):
        return False
    if not _text_match(payload.get("from"), filters.get("from_contains")):
        return False
    if not _text_match(payload.get("subject"), filters.get("subject_contains")):
        return False
    return True


def dispatch_trigger_event(
    *,
    provider: str,
    event: str,
    event_id: str,
    payload: dict[str, Any],
    user_id: str,
) -> dict[str, int]:
    """Find matching automations and enqueue trigger execution."""
    sb = get_supabase()
    rows = (
        sb.table("skills")
        .select(
            "id, trigger_filters, enabled, trigger_enabled, "
            "trigger_provider, trigger_event, last_trigger_event_key"
        )
        .eq("user_id", user_id)
        .eq("enabled", True)
        .eq("trigger_enabled", True)
        .eq("trigger_provider", provider)
        .eq("trigger_event", event)
        .execute()
    )
    enqueued = 0
    checked = len(rows.data or [])
    for skill in rows.data or []:
        if skill.get("last_trigger_event_key") == event_id:
            continue
        if not _matches_filters(skill.get("trigger_filters"), payload):
            continue
        execute_triggered_skill_automation.delay(skill["id"], event_id, payload)
        enqueued += 1

    log.info(
        "trigger_dispatch provider=%s event=%s user=%s checked=%s enqueued=%s",
        provider,
        event,
        user_id,
        checked,
        enqueued,
    )
    return {"checked": checked, "enqueued": enqueued}
