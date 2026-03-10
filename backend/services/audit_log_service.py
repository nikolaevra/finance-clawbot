"""Durable audit logging service backed by Supabase Postgres."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.supabase_service import get_supabase

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _activity_category(event_type: str) -> str:
    if event_type.startswith("tool_") or event_type.startswith("message_"):
        return "skill"
    if event_type.startswith("workflow_") or event_type.startswith("step_") or event_type == "approval_gate":
        return "workflow"
    if event_type.startswith("gmail_"):
        return "gmail"
    if event_type.startswith("external_api_"):
        return "external_api"
    return "system"


def _to_activity_event(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("details") or {}
    event: dict[str, Any] = {
        "type": row.get("event_type") or "activity",
        "actor": row.get("actor") or "gateway",
        "timestamp": row.get("occurred_at") or row.get("created_at") or _now_iso(),
        "message": row.get("message") or row.get("title") or "Activity update",
    }
    if row.get("workflow_run_id"):
        event["run_id"] = row["workflow_run_id"]
    if row.get("step_id"):
        event["step_id"] = row["step_id"]
    if row.get("tool_name"):
        event["tool_name"] = row["tool_name"]
    if row.get("workflow_name"):
        event["workflow_name"] = row["workflow_name"]
    if row.get("detail"):
        event["detail"] = row["detail"]
    if details.get("preview"):
        event["preview"] = details.get("preview")
    return event


def log_event(
    *,
    user_id: str,
    event_type: str,
    event_source: str,
    title: str,
    event_category: str | None = None,
    status: str | None = None,
    actor: str | None = None,
    message: str | None = None,
    detail: str | None = None,
    conversation_id: str | None = None,
    workflow_run_id: str | None = None,
    workflow_name: str | None = None,
    tool_name: str | None = None,
    step_id: str | None = None,
    external_service: str | None = None,
    external_endpoint: str | None = None,
    request_id: str | None = None,
    occurred_at: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert one durable audit event. Never raises."""
    if not user_id:
        return
    try:
        sb = get_supabase()
        sb.table("automation_audit_log").insert({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "workflow_run_id": workflow_run_id,
            "event_type": event_type,
            "event_category": event_category or _activity_category(event_type),
            "event_source": event_source,
            "status": status,
            "actor": actor,
            "title": title,
            "message": message,
            "detail": detail,
            "details": details or {},
            "tool_name": tool_name,
            "step_id": step_id,
            "workflow_name": workflow_name,
            "external_service": external_service,
            "external_endpoint": external_endpoint,
            "request_id": request_id,
            "occurred_at": occurred_at or _now_iso(),
        }).execute()
    except Exception:
        log.warning(
            "audit_log_insert_failed user=%s type=%s source=%s",
            user_id,
            event_type,
            event_source,
            exc_info=True,
        )


def publish_event(user_id: str, event: dict[str, Any]) -> None:
    """Compatibility bridge for existing activity event publishers."""
    event_type = str(event.get("type") or "activity")
    log_event(
        user_id=user_id,
        event_type=event_type,
        event_category=_activity_category(event_type),
        event_source="activity_bridge",
        status=event.get("status"),
        actor=event.get("actor"),
        title=event.get("message") or event_type.replace("_", " ").title(),
        message=event.get("message"),
        detail=event.get("detail"),
        workflow_run_id=event.get("run_id"),
        workflow_name=event.get("workflow_name"),
        tool_name=event.get("tool_name"),
        step_id=event.get("step_id"),
        occurred_at=event.get("timestamp"),
        details={k: v for k, v in event.items() if k not in {
            "type", "status", "actor", "message", "detail", "run_id",
            "workflow_name", "tool_name", "step_id", "timestamp",
        }},
    )


def log_skill_live(
    *,
    user_id: str,
    conversation_id: str,
    tool_name: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    log_event(
        user_id=user_id,
        conversation_id=conversation_id,
        event_type="skill_live_used",
        event_category="skill",
        event_source="chat_gateway",
        status=status,
        actor="gateway",
        title=f"Skill used: {tool_name}",
        message=message,
        tool_name=tool_name,
        details=details,
    )


def log_skill_background(
    *,
    user_id: str,
    skill_id: str,
    skill_name: str,
    trigger_type: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    event_type = {
        "started": "skill_background_triggered",
        "ok": "skill_background_completed",
        "failed": "skill_background_failed",
        "skipped": "skill_background_skipped",
    }.get(status, "skill_background_event")
    log_event(
        user_id=user_id,
        event_type=event_type,
        event_category="skill",
        event_source="celery_automation",
        status=status,
        actor="lobster",
        title=f"Background skill {status}: {skill_name}",
        message=f"{skill_name} ({trigger_type})",
        details={"skill_id": skill_id, "trigger_type": trigger_type, **(details or {})},
    )


def log_gmail_inbound(
    *,
    user_id: str,
    integration_id: str,
    event_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    log_event(
        user_id=user_id,
        event_type="gmail_message_received",
        event_category="gmail",
        event_source="gmail_webhook",
        status="received",
        actor="gateway",
        title="New Gmail message received",
        message="Inbound Gmail event processed",
        details={"integration_id": integration_id, "event_id": event_id, **(details or {})},
    )


def log_external_api_call(
    *,
    user_id: str,
    service: str,
    operation: str,
    status: str,
    duration_ms: float | None = None,
    error_message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    event_type = "external_api_call_success" if status == "success" else "external_api_call_error"
    log_event(
        user_id=user_id,
        event_type=event_type,
        event_category="external_api",
        event_source=f"{service}_service",
        status=status,
        actor="gateway",
        title=f"{service} API call {status}",
        message=f"{operation}",
        detail=error_message,
        external_service=service,
        external_endpoint=operation,
        details={"duration_ms": round(duration_ms or 0, 2), **(details or {})},
    )


def fetch_activity_events_since(
    *,
    user_id: str,
    after_occurred_at: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return activity-shaped events for the activity SSE stream."""
    sb = get_supabase()
    query = (
        sb.table("automation_audit_log")
        .select(
            "id, event_type, actor, occurred_at, created_at, message, title, "
            "detail, workflow_run_id, step_id, tool_name, workflow_name, details"
        )
        .eq("user_id", user_id)
        .order("occurred_at", desc=False)
        .limit(limit)
    )
    if after_occurred_at:
        query = query.gt("occurred_at", after_occurred_at)
    rows = query.execute().data or []
    return [_to_activity_event(row) for row in rows]


def list_audit_events(
    *,
    user_id: str,
    limit: int = 100,
    cursor: str | None = None,
    category: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> list[dict[str, Any]]:
    """List durable audit events with optional filters."""
    sb = get_supabase()
    q = (
        sb.table("automation_audit_log")
        .select("*")
        .eq("user_id", user_id)
        .order("occurred_at", desc=True)
        .limit(min(max(limit, 1), 200))
    )
    if category:
        q = q.eq("event_category", category)
    if event_type:
        q = q.eq("event_type", event_type)
    if source:
        q = q.eq("event_source", source)
    if from_ts:
        q = q.gte("occurred_at", from_ts)
    if to_ts:
        q = q.lte("occurred_at", to_ts)
    if cursor:
        q = q.lt("occurred_at", cursor)
    return q.execute().data or []


def get_audit_event(user_id: str, event_id: str) -> dict[str, Any] | None:
    sb = get_supabase()
    result = (
        sb.table("automation_audit_log")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", event_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]
