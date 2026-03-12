"""Celery tasks for scheduled skill-based automations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from celery_app import celery
from services.supabase_service import get_supabase
from services.gateway_service import gateway
from services.skill_service import get_skill
from services.audit_log_service import log_skill_background, log_wait_lifecycle
from services.conversation_service import create_background_conversation
from services.automation_wait_service import get_wait, expire_pending_waits

log = logging.getLogger(__name__)


def _weekday_sunday_zero(local_now: datetime) -> int:
    """Convert Python weekday (Mon=0) to Sunday=0 format used by frontend."""
    return (local_now.weekday() + 1) % 7


def _compute_schedule_run_key(skill: dict, now_utc: datetime) -> str | None:
    schedule_type = skill.get("schedule_type")
    schedule_time = skill.get("schedule_time")
    schedule_timezone = skill.get("schedule_timezone") or "UTC"
    if not schedule_type or not schedule_time:
        return None
    try:
        tz = ZoneInfo(schedule_timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    local_now = now_utc.astimezone(tz)
    if local_now.strftime("%H:%M") != schedule_time:
        return None

    if schedule_type == "weekly":
        allowed = skill.get("schedule_days") or []
        if _weekday_sunday_zero(local_now) not in allowed:
            return None

    return f"{local_now.strftime('%Y-%m-%d')}:{schedule_time}:{schedule_type}"


def _scheduled_prompt(skill_name: str, content: str, run_key: str) -> str:
    return (
        f"Execute automation '{skill_name}'. This run was triggered by schedule ({run_key}).\n\n"
        "Follow the automation instructions below exactly. Use tools as needed, then return a concise completion summary.\n\n"
        f"{content}"
    )


def _trigger_prompt(skill_name: str, content: str, event_id: str, payload: dict) -> str:
    return (
        f"Execute automation '{skill_name}'. This run was triggered by event ({event_id}).\n\n"
        f"Event payload:\n{payload}\n\n"
        "Follow the automation instructions below exactly. Use tools as needed, then return a concise completion summary.\n\n"
        f"{content}"
    )


@celery.task(name="tasks.skill_automation_tasks.scan_scheduled_automations")
def scan_scheduled_automations() -> dict:
    """Scan due automations and enqueue execution tasks."""
    sb = get_supabase()
    now_utc = datetime.now(timezone.utc)
    rows = (
        sb.table("skills")
        .select(
            "id, user_id, name, enabled, schedule_enabled, "
            "schedule_type, schedule_days, schedule_time, schedule_timezone, "
            "last_scheduled_run_key"
        )
        .eq("enabled", True)
        .eq("schedule_enabled", True)
        .execute()
    )
    due_count = 0
    for skill in rows.data or []:
        run_key = _compute_schedule_run_key(skill, now_utc)
        if not run_key:
            continue
        if skill.get("last_scheduled_run_key") == run_key:
            continue
        execute_scheduled_skill_automation.delay(skill["id"], run_key)
        due_count += 1
    return {"checked": len(rows.data or []), "enqueued": due_count}


@celery.task(name="tasks.skill_automation_tasks.execute_scheduled_skill_automation")
def execute_scheduled_skill_automation(skill_id: str, run_key: str) -> dict:
    """Execute one scheduled automation once per run key."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select(
            "id, user_id, name, enabled, schedule_enabled, last_scheduled_run_key"
        )
        .eq("id", skill_id)
        .single()
        .execute()
    )
    skill = result.data
    if not skill or not skill.get("enabled") or not skill.get("schedule_enabled"):
        if skill and skill.get("user_id"):
            log_skill_background(
                user_id=skill["user_id"],
                skill_id=skill_id,
                skill_name=skill.get("name", "unknown"),
                trigger_type="scheduled",
                status="skipped",
                details={"reason": "inactive_or_missing", "run_key": run_key},
            )
        return {"status": "skipped", "reason": "inactive_or_missing", "skill_id": skill_id}
    if skill.get("last_scheduled_run_key") == run_key:
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill.get("name", "unknown"),
            trigger_type="scheduled",
            status="skipped",
            details={"reason": "already_ran", "run_key": run_key},
        )
        return {"status": "skipped", "reason": "already_ran", "skill_id": skill_id}

    sb.table("skills").update({"last_scheduled_run_key": run_key}).eq("id", skill_id).execute()
    content = get_skill(skill["user_id"], skill["name"])
    if not content:
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill["name"],
            trigger_type="scheduled",
            status="skipped",
            details={"reason": "missing_content", "run_key": run_key},
        )
        return {"status": "skipped", "reason": "missing_content", "skill_id": skill_id}

    conversation_id = create_background_conversation(
        user_id=skill["user_id"],
        agent_name=skill["name"],
        agent_source="skill_schedule",
        agent_run_id=run_key,
    )
    prompt = _scheduled_prompt(skill["name"], content, run_key)
    log_skill_background(
        user_id=skill["user_id"],
        skill_id=skill_id,
        skill_name=skill["name"],
        trigger_type="scheduled",
        status="started",
        details={"run_key": run_key, "conversation_id": conversation_id},
    )
    try:
        for _ in gateway.handle_message(skill["user_id"], conversation_id, prompt):
            pass
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill["name"],
            trigger_type="scheduled",
            status="ok",
            details={"run_key": run_key, "conversation_id": conversation_id},
        )
        log.info("scheduled_automation_completed skill_id=%s run_key=%s", skill_id, run_key)
        return {"status": "ok", "skill_id": skill_id, "run_key": run_key}
    except Exception as exc:
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill["name"],
            trigger_type="scheduled",
            status="failed",
            details={"run_key": run_key, "error": str(exc)},
        )
        raise


@celery.task(name="tasks.skill_automation_tasks.execute_triggered_skill_automation")
def execute_triggered_skill_automation(skill_id: str, event_id: str, payload: dict) -> dict:
    """Execute one trigger-based automation event."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select(
            "id, user_id, name, enabled, trigger_enabled, last_trigger_event_key"
        )
        .eq("id", skill_id)
        .single()
        .execute()
    )
    skill = result.data
    if not skill or not skill.get("enabled") or not skill.get("trigger_enabled"):
        if skill and skill.get("user_id"):
            log_skill_background(
                user_id=skill["user_id"],
                skill_id=skill_id,
                skill_name=skill.get("name", "unknown"),
                trigger_type="triggered",
                status="skipped",
                details={"reason": "inactive_or_missing", "event_id": event_id},
            )
        return {"status": "skipped", "reason": "inactive_or_missing", "skill_id": skill_id}
    if skill.get("last_trigger_event_key") == event_id:
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill.get("name", "unknown"),
            trigger_type="triggered",
            status="skipped",
            details={"reason": "already_ran", "event_id": event_id},
        )
        return {"status": "skipped", "reason": "already_ran", "skill_id": skill_id}

    sb.table("skills").update({"last_trigger_event_key": event_id}).eq("id", skill_id).execute()
    content = get_skill(skill["user_id"], skill["name"])
    if not content:
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill["name"],
            trigger_type="triggered",
            status="skipped",
            details={"reason": "missing_content", "event_id": event_id},
        )
        return {"status": "skipped", "reason": "missing_content", "skill_id": skill_id}

    conversation_id = create_background_conversation(
        user_id=skill["user_id"],
        agent_name=skill["name"],
        agent_source="skill_trigger",
        agent_run_id=event_id,
    )
    prompt = _trigger_prompt(skill["name"], content, event_id, payload or {})
    log_skill_background(
        user_id=skill["user_id"],
        skill_id=skill_id,
        skill_name=skill["name"],
        trigger_type="triggered",
        status="started",
        details={"event_id": event_id, "conversation_id": conversation_id},
    )
    try:
        for _ in gateway.handle_message(skill["user_id"], conversation_id, prompt):
            pass
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill["name"],
            trigger_type="triggered",
            status="ok",
            details={"event_id": event_id, "conversation_id": conversation_id},
        )
        log.info("triggered_automation_completed skill_id=%s event_id=%s", skill_id, event_id)
        return {"status": "ok", "skill_id": skill_id, "event_id": event_id}
    except Exception as exc:
        log_skill_background(
            user_id=skill["user_id"],
            skill_id=skill_id,
            skill_name=skill["name"],
            trigger_type="triggered",
            status="failed",
            details={"event_id": event_id, "error": str(exc)},
        )
        raise


@celery.task(name="tasks.skill_automation_tasks.resume_waiting_skill_execution")
def resume_waiting_skill_execution(wait_id: str) -> dict:
    """Resume a previously paused skill execution after inbound wait match."""
    wait = get_wait(wait_id)
    if not wait:
        return {"status": "skipped", "reason": "wait_not_found", "wait_id": wait_id}
    if wait.get("status") != "matched":
        return {"status": "skipped", "reason": "wait_not_matched", "wait_id": wait_id}

    user_id = wait.get("user_id")
    conversation_id = wait.get("conversation_id")
    if not user_id or not conversation_id:
        return {"status": "skipped", "reason": "missing_context", "wait_id": wait_id}

    for _ in gateway.resume_after_wait(
        user_id=user_id,
        conversation_id=conversation_id,
        wait_id=wait_id,
    ):
        pass
    log_wait_lifecycle(
        user_id=user_id,
        conversation_id=conversation_id,
        wait_id=wait_id,
        event_type="wait_resumed",
        status="resumed",
        message="Wait matched and execution resumed.",
    )
    return {"status": "ok", "wait_id": wait_id}


@celery.task(name="tasks.skill_automation_tasks.expire_automation_waits")
def expire_automation_waits() -> dict:
    """Mark timed-out pending waits as expired."""
    expired = expire_pending_waits()
    return {"status": "ok", "expired": expired}
