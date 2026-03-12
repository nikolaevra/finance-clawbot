"""Durable omnichannel wait-state management for skill execution."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any

from services.supabase_service import get_supabase
from services.audit_log_service import log_wait_lifecycle

log = logging.getLogger(__name__)

ALLOWED_CHANNELS = {"email", "slack", "whatsapp", "sms", "generic"}
ALLOWED_OPS = {"equals", "contains", "in", "regex", "starts_with", "ends_with", "exists"}
MAX_CONDITIONS = 25
MAX_REGEX_LEN = 256


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json(value: Any) -> str:
    return json.dumps(value, default=str)


def _deep_get(obj: dict[str, Any], path: str) -> Any:
    current: Any = obj
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _to_json(value)


def _eval_condition(event: dict[str, Any], cond: dict[str, Any]) -> bool:
    field = str(cond.get("field") or "").strip()
    op = str(cond.get("op") or "").strip().lower()
    value = cond.get("value")
    case_sensitive = bool(cond.get("case_sensitive", False))
    if not field or op not in ALLOWED_OPS:
        return False

    actual = _deep_get(event, field)
    if op == "exists":
        return actual is not None

    if op == "in":
        if not isinstance(value, list):
            return False
        actual_text = _coerce_text(actual)
        if not case_sensitive:
            actual_text = actual_text.lower()
            return actual_text in {str(v).lower() for v in value}
        return actual_text in {str(v) for v in value}

    actual_text = _coerce_text(actual)
    expected = _coerce_text(value)
    if not case_sensitive:
        actual_text = actual_text.lower()
        expected = expected.lower()

    if op == "equals":
        return actual_text == expected
    if op == "contains":
        return expected in actual_text
    if op == "starts_with":
        return actual_text.startswith(expected)
    if op == "ends_with":
        return actual_text.endswith(expected)
    if op == "regex":
        raw_pattern = _coerce_text(value)
        if len(raw_pattern) > MAX_REGEX_LEN:
            return False
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return bool(re.search(raw_pattern, _coerce_text(actual), flags=flags))
        except re.error:
            return False
    return False


def _normalize_matcher(matcher: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy matcher keys and preserve explicit condition groups."""
    matcher = matcher or {}
    all_conditions = list(matcher.get("all") or [])
    any_conditions = list(matcher.get("any") or [])
    none_conditions = list(matcher.get("none") or [])

    legacy_map = {
        "from_contains": ("sender", "contains"),
        "from_equals": ("sender_email", "equals"),
        "subject_contains": ("subject", "contains"),
        "thread_id": ("thread_ref", "equals"),
    }
    for key, (field, op) in legacy_map.items():
        if matcher.get(key):
            all_conditions.append({"field": field, "op": op, "value": matcher[key]})

    if matcher.get("body_contains_any"):
        phrases = matcher.get("body_contains_any")
        if isinstance(phrases, list):
            for phrase in phrases:
                any_conditions.append({"field": "body_text", "op": "contains", "value": phrase})

    return {
        "all": all_conditions,
        "any": any_conditions,
        "none": none_conditions,
    }


def _validate_matcher(matcher: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_matcher(matcher)
    total = len(normalized["all"]) + len(normalized["any"]) + len(normalized["none"])
    if total <= 0:
        raise ValueError("matcher must contain at least one condition")
    if total > MAX_CONDITIONS:
        raise ValueError(f"matcher has too many conditions (max {MAX_CONDITIONS})")
    return normalized


def evaluate_matcher(matcher: dict[str, Any], event: dict[str, Any]) -> bool:
    normalized = _normalize_matcher(matcher)
    all_conditions = normalized.get("all") or []
    any_conditions = normalized.get("any") or []
    none_conditions = normalized.get("none") or []

    if any(not _eval_condition(event, cond) for cond in all_conditions):
        return False
    if any_conditions and not any(_eval_condition(event, cond) for cond in any_conditions):
        return False
    if any(_eval_condition(event, cond) for cond in none_conditions):
        return False
    return True


def create_wait(
    *,
    user_id: str,
    conversation_id: str | None,
    channel: str,
    matcher: dict[str, Any],
    wait_type: str = "external_response",
    timeout_minutes: int | None = None,
    skill_name: str | None = None,
    run_key: str | None = None,
    tool_call_id: str | None = None,
    correlation: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if channel not in ALLOWED_CHANNELS:
        raise ValueError(f"Unsupported channel '{channel}'")
    checked_matcher = _validate_matcher(matcher)

    timeout_at: str | None = None
    if timeout_minutes is not None:
        timeout_minutes = int(timeout_minutes)
        if timeout_minutes < 1 or timeout_minutes > 60 * 24 * 30:
            raise ValueError("timeout_minutes must be between 1 and 43200")
        timeout_at = (datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)).isoformat()

    correlation = correlation or {}
    row = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "status": "pending",
        "channel": channel,
        "wait_type": wait_type or "external_response",
        "matcher_json": checked_matcher,
        "timeout_at": timeout_at,
        "skill_name": skill_name,
        "run_key": run_key,
        "tool_call_id": tool_call_id,
        "thread_id": correlation.get("thread_id"),
        "channel_ref": correlation.get("channel_ref"),
        "phone_number": correlation.get("phone_number"),
        "metadata": metadata or {},
    }
    sb = get_supabase()
    result = sb.table("automation_waits").insert(row).execute()
    created = result.data[0]
    log_wait_lifecycle(
        user_id=user_id,
        conversation_id=conversation_id,
        wait_id=created["id"],
        event_type="wait_created",
        status="pending",
        message=f"Created wait for {created['channel']} response",
        details={"channel": created["channel"], "wait_type": created.get("wait_type")},
    )
    return created


def expire_pending_waits(now_iso: str | None = None) -> int:
    sb = get_supabase()
    now_iso = now_iso or _now_iso()
    rows = (
        sb.table("automation_waits")
        .select("id, user_id, conversation_id")
        .eq("status", "pending")
        .lte("timeout_at", now_iso)
        .execute()
    ).data or []
    if not rows:
        return 0
    ids = [row["id"] for row in rows]
    sb.table("automation_waits").update({
        "status": "expired",
        "resolved_at": now_iso,
    }).in_("id", ids).execute()
    for row in rows:
        log_wait_lifecycle(
            user_id=row["user_id"],
            conversation_id=row.get("conversation_id"),
            wait_id=row["id"],
            event_type="wait_expired",
            status="expired",
            message="Wait expired before matching an inbound response.",
        )
    return len(ids)


def record_inbound_event(
    *,
    provider: str,
    provider_event_id: str,
    user_id: str,
    channel: str,
    normalized_event: dict[str, Any],
) -> dict[str, Any]:
    if channel not in ALLOWED_CHANNELS:
        raise ValueError(f"Unsupported channel '{channel}'")
    sb = get_supabase()
    payload = {
        "provider": provider,
        "provider_event_id": provider_event_id,
        "user_id": user_id,
        "channel": channel,
        "normalized_event_json": normalized_event,
    }
    try:
        result = (
            sb.table("inbound_events")
            .upsert(payload, on_conflict="provider,provider_event_id")
            .execute()
        )
        if result.data:
            return result.data[0]
    except Exception:
        log.exception("record_inbound_event_upsert_failed provider=%s event=%s", provider, provider_event_id)

    existing = (
        sb.table("inbound_events")
        .select("*")
        .eq("provider", provider)
        .eq("provider_event_id", provider_event_id)
        .limit(1)
        .execute()
    ).data or []
    if existing:
        return existing[0]
    raise RuntimeError("Failed to record inbound event")


def match_pending_wait(
    *,
    user_id: str,
    channel: str,
    inbound_event: dict[str, Any],
    inbound_event_id: str,
) -> dict[str, Any] | None:
    sb = get_supabase()
    waits = (
        sb.table("automation_waits")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel", channel)
        .eq("status", "pending")
        .order("created_at")
        .execute()
    ).data or []

    now_iso = _now_iso()
    for wait in waits:
        timeout_at = wait.get("timeout_at")
        if timeout_at and str(timeout_at) <= now_iso:
            sb.table("automation_waits").update({
                "status": "expired",
                "resolved_at": now_iso,
            }).eq("id", wait["id"]).eq("status", "pending").execute()
            continue

        matcher = wait.get("matcher_json") or {}
        if not evaluate_matcher(matcher, inbound_event):
            continue

        updated = (
            sb.table("automation_waits")
            .update({
                "status": "matched",
                "matched_event_id": inbound_event_id,
                "matched_payload": inbound_event,
                "resolved_at": now_iso,
            })
            .eq("id", wait["id"])
            .eq("status", "pending")
            .execute()
        ).data or []
        if updated:
            log_wait_lifecycle(
                user_id=user_id,
                conversation_id=updated[0].get("conversation_id"),
                wait_id=updated[0]["id"],
                event_type="wait_matched",
                status="matched",
                message=f"Matched inbound {channel} response",
                details={"inbound_event_id": inbound_event_id},
            )
            return updated[0]
    return None


def get_wait(wait_id: str) -> dict[str, Any] | None:
    sb = get_supabase()
    rows = (
        sb.table("automation_waits")
        .select("*")
        .eq("id", wait_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def extract_sender_email(raw_from: str) -> str:
    _name, email = parseaddr(raw_from or "")
    return (email or "").strip().lower()
