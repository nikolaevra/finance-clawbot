"""Gateway service — orchestration layer between chat and tool execution.

Replicates the OpenClaw Gateway pattern: every tool call is routed through
``dispatch_tool_call``, which decides whether to execute inline or hand off
to the workflow engine / Celery.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from tools.registry import tool_registry
from services.event_bus import publish_event

log = logging.getLogger(__name__)
from services.workflow_engine import (
    get_pending_approvals,
    get_active_workflows,
)


# ---------------------------------------------------------------------------
# Human-readable event descriptions
# ---------------------------------------------------------------------------

_WORKFLOW_LABELS = {
    "sync_accounting": "Sync Accounting Data",
    "categorize_transactions": "Categorize Transactions",
    "generate_financial_report": "Generate Financial Report",
    "memory_consolidation": "Memory Consolidation",
    "detect_anomalies": "Detect Anomalies",
}


def _parse_args(tool_args: str | dict) -> dict:
    if isinstance(tool_args, dict):
        return tool_args
    try:
        return json.loads(tool_args) if tool_args else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _workflow_label(name: str) -> str:
    return _WORKFLOW_LABELS.get(name, name.replace("_", " ").title())


def _describe_tool(tool_name: str, args: dict) -> tuple[str, "Callable[[str | None], str]"]:
    """Return (dispatch_message, complete_message_fn) for a tool call.

    The complete_message_fn receives the raw result string and should return
    a human-readable completion message.
    """
    if tool_name == "workflow_run":
        wf = args.get("workflow_name", "unknown")
        label = _workflow_label(wf)
        return (
            f"Running {label} workflow",
            lambda _r: f"Dispatched {label} to a background worker",
        )

    if tool_name == "workflow_status":
        rid = args.get("run_id", "")[:8]
        def _status_complete(r: str | None) -> str:
            try:
                d = json.loads(r) if r else {}
                wf = _workflow_label(d.get("workflow", ""))
                return f"{wf} is {d.get('status', 'unknown')}"
            except Exception:
                return f"Checked workflow status ({rid}…)"
        return (f"Checking workflow status ({rid}…)", _status_complete)

    if tool_name == "workflow_approve":
        approve = args.get("approve", True)
        action = "Approving" if approve else "Rejecting"
        return (
            f"{action} workflow run",
            lambda _r: f"Workflow {'approved and resumed' if approve else 'rejected'}",
        )

    if tool_name == "workflow_list":
        return (
            "Listing available workflows",
            lambda _r: "Retrieved workflow catalog",
        )

    # Memory / document / accounting tools — short human labels
    _TOOL_LABELS: dict[str, tuple[str, str]] = {
        "memory_append": ("Saving to daily memory log", "Saved to memory"),
        "memory_read": ("Reading memory file", "Memory file retrieved"),
        "memory_search": ("Searching memories", "Memory search complete"),
        "memory_save": ("Writing to long-term memory", "Long-term memory updated"),
        "document_list": ("Listing uploaded documents", "Document list retrieved"),
        "document_read": ("Reading document content", "Document content retrieved"),
        "accounting_list_accounts": ("Fetching chart of accounts", "Accounts retrieved"),
        "accounting_search_transactions": ("Searching transactions", "Transaction search complete"),
    }
    if tool_name in _TOOL_LABELS:
        dispatch, complete = _TOOL_LABELS[tool_name]
        return (dispatch, lambda _r, c=complete: c)

    return (
        f"Executing {tool_name.replace('_', ' ')}",
        lambda r: f"{tool_name.replace('_', ' ').capitalize()} completed",
    )


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def dispatch_tool_call(
    tool_name: str,
    tool_args: str | dict,
    user_id: str,
    conversation_id: str | None = None,
) -> str:
    """Route a tool call to the appropriate executor.

    - ``workflow_*`` tools are handled by the tool registry like everything
      else (the workflow tools themselves call into the workflow engine).
    - This function exists as a single choke-point for future extensions
      (rate limiting, audit logging, A/B routing, etc.).

    Returns a JSON string with the tool result.
    """
    log.debug("dispatch tool=%s args=%s user=%s", tool_name, tool_args, user_id)

    parsed_args = _parse_args(tool_args)
    dispatch_msg, complete_fn = _describe_tool(tool_name, parsed_args)

    publish_event(user_id, {
        "type": "tool_dispatch",
        "actor": "gateway",
        "tool_name": tool_name,
        "message": dispatch_msg,
    })
    try:
        result = tool_registry.execute(tool_name, tool_args)
        log.debug("tool=%s completed (%d chars)", tool_name, len(result) if result else 0)
        publish_event(user_id, {
            "type": "tool_complete",
            "actor": "gateway",
            "tool_name": tool_name,
            "message": complete_fn(result),
        })
        return result
    except Exception as exc:
        log.exception("tool=%s raised an exception", tool_name)
        publish_event(user_id, {
            "type": "tool_error",
            "actor": "gateway",
            "tool_name": tool_name,
            "message": f"{tool_name} failed: {exc}",
        })
        raise


# ---------------------------------------------------------------------------
# Context helpers (injected into the chat system prompt)
# ---------------------------------------------------------------------------

def build_workflow_context(user_id: str) -> str | None:
    """Return a system-message block describing pending approvals and active
    workflows so the AI can proactively inform the user.

    Returns ``None`` if there is nothing to report.
    """
    parts: list[str] = []

    try:
        pending = get_pending_approvals(user_id)
        if pending:
            lines = ["[Pending Workflow Approvals]"]
            for p in pending:
                tpl = p.get("workflow_templates") or {}
                name = tpl.get("name", "unknown")
                steps = tpl.get("steps") or []
                idx = p.get("current_step_index", 0)
                prompt = ""
                if idx < len(steps):
                    approval = steps[idx].get("approval") or {}
                    prompt = approval.get("prompt", "")
                lines.append(
                    f"- Workflow '{name}' (run {p['id']}) awaits approval: {prompt}"
                )
            parts.append("\n".join(lines))
    except Exception:
        log.exception("get_pending_approvals failed for user=%s", user_id)

    try:
        active = get_active_workflows(user_id)
        running = [w for w in active if w["status"] == "running"]
        if running:
            lines = ["[Running Workflows]"]
            for w in running:
                tpl = w.get("workflow_templates") or {}
                name = tpl.get("name", "unknown")
                lines.append(f"- '{name}' (run {w['id']}) — step {w.get('current_step_index', '?')}")
            parts.append("\n".join(lines))
    except Exception:
        log.exception("get_active_workflows failed for user=%s", user_id)

    return "\n\n".join(parts) if parts else None


def build_workflow_events(run: dict) -> list[dict]:
    """Convert a workflow run dict into structured SSE event payloads."""
    events: list[dict] = []
    tpl = run.get("workflow_templates") or {}

    if run["status"] == "pending" or run["status"] == "running":
        events.append({
            "type": "workflow_started",
            "run_id": run["id"],
            "workflow": tpl.get("name", "unknown"),
            "status": run["status"],
        })

    if run["status"] == "paused":
        steps = tpl.get("steps") or []
        idx = run.get("current_step_index", 0)
        prompt = ""
        if idx < len(steps):
            approval = steps[idx].get("approval") or {}
            prompt = approval.get("prompt", "Approve this step?")
        events.append({
            "type": "workflow_approval_needed",
            "run_id": run["id"],
            "workflow": tpl.get("name", "unknown"),
            "prompt": prompt,
            "resume_token": run.get("resume_token"),
        })

    if run["status"] == "completed":
        events.append({
            "type": "workflow_completed",
            "run_id": run["id"],
            "workflow": tpl.get("name", "unknown"),
            "steps_state": run.get("steps_state"),
        })

    if run["status"] == "failed":
        events.append({
            "type": "workflow_failed",
            "run_id": run["id"],
            "workflow": tpl.get("name", "unknown"),
            "error": run.get("error"),
        })

    return events
