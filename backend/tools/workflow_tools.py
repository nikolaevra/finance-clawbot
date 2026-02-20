"""Workflow tools for OpenAI function calling.

These tools let the AI agent trigger, monitor, approve, and list
deterministic workflow pipelines (Lobster-style).
"""
from __future__ import annotations

import json
from flask import g

from tools.registry import tool_registry
from services.workflow_engine import (
    start_workflow,
    resume_workflow,
    get_run_status,
    cancel_workflow,
    list_templates,
    find_template_by_name,
    get_pending_approvals,
)


@tool_registry.register(
    name="workflow_run",
    description=(
        "Trigger a named workflow pipeline. Workflows are multi-step "
        "deterministic pipelines that run in the background (e.g. "
        "'sync_accounting', 'categorize_transactions', 'generate_financial_report', "
        "'memory_consolidation', 'detect_anomalies'). Returns the run ID and "
        "initial status. If the workflow has approval gates, it will pause and "
        "require explicit approval before continuing."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workflow_name": {
                "type": "string",
                "description": "Name of the workflow to run (e.g. 'sync_accounting').",
            },
            "args": {
                "type": "object",
                "description": "Optional arguments to pass to the workflow (e.g. {\"days\": 30}).",
            },
        },
        "required": ["workflow_name"],
    },
)
def workflow_run(workflow_name: str, args: dict | None = None) -> dict:
    user_id = g.user_id
    conversation_id = getattr(g, "conversation_id", None)

    template = find_template_by_name(workflow_name, user_id)
    if not template:
        return {
            "error": f"Workflow '{workflow_name}' not found. Use workflow_list to see available workflows.",
            "tool_used": "workflow_run",
        }

    try:
        run = start_workflow(
            template_id=template["id"],
            user_id=user_id,
            args=args,
            conversation_id=conversation_id,
            trigger="chat",
        )
        return {
            "tool_used": "workflow_run",
            "run_id": run["id"],
            "workflow": workflow_name,
            "status": run["status"],
            "message": f"Workflow '{workflow_name}' started (run {run['id']}). "
                       "It will execute in the background.",
        }
    except Exception as e:
        return {"error": str(e), "tool_used": "workflow_run"}


@tool_registry.register(
    name="workflow_status",
    description=(
        "Check the current status of a workflow run, including per-step "
        "progress. Use this to report back to the user on running or "
        "completed workflows."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "description": "The workflow run ID to check.",
            },
        },
        "required": ["run_id"],
    },
)
def workflow_status(run_id: str) -> dict:
    try:
        run = get_run_status(run_id)
        tpl = run.get("workflow_templates") or {}
        return {
            "tool_used": "workflow_status",
            "run_id": run["id"],
            "workflow": tpl.get("name", "unknown"),
            "status": run["status"],
            "current_step": run.get("current_step_index"),
            "steps_state": run.get("steps_state"),
            "error": run.get("error"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
        }
    except Exception as e:
        return {"error": str(e), "tool_used": "workflow_status"}


@tool_registry.register(
    name="workflow_approve",
    description=(
        "Approve or reject a workflow that is paused at an approval gate. "
        "When a workflow pauses for approval, the user must explicitly "
        "approve before side effects (like applying changes) proceed. "
        "Pass approve=false to cancel the workflow."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "description": "The workflow run ID to approve or reject.",
            },
            "approve": {
                "type": "boolean",
                "description": "True to approve, false to reject/cancel.",
            },
            "comment": {
                "type": "string",
                "description": "Optional comment from the user about the approval decision.",
            },
        },
        "required": ["run_id", "approve"],
    },
)
def workflow_approve(run_id: str, approve: bool = True, comment: str | None = None) -> dict:
    try:
        run = resume_workflow(run_id, approve=approve, comment=comment)
        action = "approved and resumed" if approve else "rejected and cancelled"
        return {
            "tool_used": "workflow_approve",
            "run_id": run["id"],
            "status": run["status"],
            "action": action,
            "message": f"Workflow {action}.",
        }
    except Exception as e:
        return {"error": str(e), "tool_used": "workflow_approve"}


@tool_registry.register(
    name="workflow_list",
    description=(
        "List all available workflow templates the user can trigger. "
        "Shows workflow names, descriptions, and whether they run on a schedule."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def workflow_list() -> dict:
    user_id = g.user_id
    try:
        templates = list_templates(user_id)
        pending = get_pending_approvals(user_id)
        return {
            "tool_used": "workflow_list",
            "workflows": [
                {
                    "name": t["name"],
                    "description": t.get("description"),
                    "schedule": t.get("schedule"),
                    "steps_count": len(t.get("steps") or []),
                    "is_system": t.get("user_id") is None,
                }
                for t in templates
            ],
            "pending_approvals": len(pending),
        }
    except Exception as e:
        return {"error": str(e), "tool_used": "workflow_list"}
