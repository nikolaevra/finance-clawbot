"""Lobster-style workflow engine: deterministic pipelines with approval gates.

The engine manages workflow lifecycle (start, pause, resume, cancel) and
delegates step execution to Celery tasks.  Workflow state is persisted in
the ``workflow_runs`` table so runs survive worker restarts.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from services.supabase_service import get_supabase

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_workflow(
    template_id: str,
    user_id: str,
    *,
    args: dict | None = None,
    conversation_id: str | None = None,
    trigger: str = "manual",
) -> dict:
    """Create a workflow run and dispatch it to Celery.

    Returns the newly created ``workflow_runs`` row (dict).
    """
    sb = get_supabase()

    tpl = (
        sb.table("workflow_templates")
        .select("*")
        .eq("id", template_id)
        .single()
        .execute()
    )
    if not tpl.data:
        raise ValueError(f"Workflow template {template_id} not found")

    template = tpl.data
    steps = template.get("steps") or []

    steps_state = [
        {
            "id": step.get("id", f"step_{i}"),
            "status": "pending",
            "result": None,
            "started_at": None,
            "completed_at": None,
        }
        for i, step in enumerate(steps)
    ]

    run_row = {
        "user_id": user_id,
        "template_id": template_id,
        "conversation_id": conversation_id,
        "status": "running",
        "current_step_index": 0,
        "steps_state": steps_state,
        "trigger": trigger,
        "input_args": args or {},
    }

    result = sb.table("workflow_runs").insert(run_row).execute()
    run = result.data[0]

    log.info("Starting workflow run=%s template=%s user=%s trigger=%s", run["id"], template_id, user_id, trigger)
    from tasks.workflow_tasks import execute_workflow
    async_result = execute_workflow.delay(run["id"])
    log.info("workflow_enqueued run=%s task_id=%s", run["id"], async_result.id)

    return run


def resume_workflow(run_id: str, *, approve: bool = True, comment: str | None = None) -> dict:
    """Resume a paused workflow after an approval gate.

    If *approve* is ``False`` the workflow is cancelled.
    Returns the updated ``workflow_runs`` row.
    """
    sb = get_supabase()

    run = (
        sb.table("workflow_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    ).data
    if not run:
        raise ValueError(f"Workflow run {run_id} not found")
    if run["status"] != "paused":
        raise ValueError(f"Run {run_id} is not paused (status={run['status']})")

    if not approve:
        log.info("Workflow run=%s rejected by user", run_id)
        now = datetime.now(timezone.utc).isoformat()
        sb.table("workflow_runs").update({
            "status": "cancelled",
            "resume_token": None,
            "completed_at": now,
        }).eq("id", run_id).execute()
        run["status"] = "cancelled"
        return run

    step_idx = run["current_step_index"]
    steps_state = run.get("steps_state") or []
    if step_idx < len(steps_state):
        steps_state[step_idx]["status"] = "approved"
        steps_state[step_idx]["result"] = {"approved": True, "comment": comment}
        steps_state[step_idx]["completed_at"] = datetime.now(timezone.utc).isoformat()

    next_idx = step_idx + 1
    sb.table("workflow_runs").update({
        "status": "running",
        "current_step_index": next_idx,
        "steps_state": steps_state,
        "resume_token": None,
    }).eq("id", run_id).execute()

    from tasks.workflow_tasks import execute_workflow
    async_result = execute_workflow.delay(run_id)
    log.info("workflow_resumed_enqueued run=%s task_id=%s", run_id, async_result.id)

    run["status"] = "running"
    run["current_step_index"] = next_idx
    run["steps_state"] = steps_state
    return run


def cancel_workflow(run_id: str) -> dict:
    """Cancel a running or paused workflow."""
    sb = get_supabase()

    run = (
        sb.table("workflow_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    ).data
    if not run:
        raise ValueError(f"Workflow run {run_id} not found")
    if run["status"] in ("completed", "failed", "cancelled"):
        raise ValueError(f"Run {run_id} already terminal (status={run['status']})")

    now = datetime.now(timezone.utc).isoformat()
    sb.table("workflow_runs").update({
        "status": "cancelled",
        "resume_token": None,
        "completed_at": now,
    }).eq("id", run_id).execute()

    run["status"] = "cancelled"
    return run


def get_run_status(run_id: str) -> dict:
    """Return the current state of a workflow run with template info."""
    sb = get_supabase()

    run = (
        sb.table("workflow_runs")
        .select("*, workflow_templates(name, description, steps)")
        .eq("id", run_id)
        .single()
        .execute()
    ).data
    if not run:
        raise ValueError(f"Workflow run {run_id} not found")
    return run


def get_pending_approvals(user_id: str) -> list[dict]:
    """Return all paused runs awaiting approval for a user."""
    sb = get_supabase()
    result = (
        sb.table("workflow_runs")
        .select("id, template_id, current_step_index, steps_state, resume_token, created_at, workflow_templates(name, description, steps)")
        .eq("user_id", user_id)
        .eq("status", "paused")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_active_workflows(user_id: str) -> list[dict]:
    """Return running + paused workflow runs for a user."""
    sb = get_supabase()
    result = (
        sb.table("workflow_runs")
        .select("id, template_id, status, current_step_index, steps_state, trigger, created_at, workflow_templates(name, description)")
        .eq("user_id", user_id)
        .in_("status", ["pending", "running", "paused"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def list_templates(user_id: str) -> list[dict]:
    """Return workflow templates visible to a user (own + system-wide)."""
    sb = get_supabase()
    result = (
        sb.table("workflow_templates")
        .select("id, name, description, steps, schedule, is_active, user_id, created_at")
        .or_(f"user_id.eq.{user_id},user_id.is.null")
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    return result.data or []


def find_template_by_name(name: str, user_id: str) -> dict | None:
    """Look up a template by name (user-owned first, then system-wide)."""
    sb = get_supabase()
    result = (
        sb.table("workflow_templates")
        .select("*")
        .eq("name", name)
        .or_(f"user_id.eq.{user_id},user_id.is.null")
        .eq("is_active", True)
        .order("user_id", desc=True)  # user-owned first (non-null sorts after null in desc)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ---------------------------------------------------------------------------
# Step execution helpers (called from Celery tasks)
# ---------------------------------------------------------------------------

def _resolve_step_input(step_def: dict, steps_state: list[dict], input_args: dict) -> Any:
    """Resolve ``input_from`` references like ``$step_id`` or ``$args``."""
    input_from = step_def.get("input_from")
    if not input_from:
        return step_def.get("args") or input_args

    if input_from == "$args":
        return input_args

    ref_id = input_from.lstrip("$")
    for ss in steps_state:
        if ss["id"] == ref_id:
            return ss.get("result")
    return None


def _evaluate_condition(condition: str | None, steps_state: list[dict]) -> bool:
    """Evaluate a step condition like ``$review.approved``."""
    if not condition:
        return True

    parts = condition.lstrip("$").split(".")
    if len(parts) != 2:
        return True

    step_id, field = parts
    for ss in steps_state:
        if ss["id"] == step_id:
            result = ss.get("result")
            if isinstance(result, dict):
                return bool(result.get(field))
            return bool(result)
    return False


def _generate_resume_token() -> str:
    return uuid.uuid4().hex[:16]
