"""Core workflow execution tasks.

``execute_workflow`` is the top-level task dispatched when a run starts or
resumes.  It walks through steps sequentially, pausing on approval gates
and recording results in ``workflow_runs.steps_state``.
"""
from __future__ import annotations

import importlib
import json
import logging
import traceback
from datetime import datetime, timezone

from celery_app import celery
from config import Config

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.audit_log_service import publish_event
from services.openai_service import get_openai
from services.workflow_engine import (
    _resolve_step_input,
    _evaluate_condition,
    _generate_resume_token,
)


_WORKFLOW_LABELS = {
    "memory_consolidation": "Memory Consolidation",
}


def _wf_label(name: str) -> str:
    return _WORKFLOW_LABELS.get(name, name.replace("_", " ").title())


def _elapsed_str(start_iso: str | None) -> str:
    """Return human-readable elapsed time like '2m 14s'."""
    if not start_iso:
        return "unknown"
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        total = int(delta.total_seconds())
        if total < 60:
            return f"{total}s"
        minutes, seconds = divmod(total, 60)
        return f"{minutes}m {seconds}s"
    except Exception:
        return "unknown"


def _summarize_result(result: dict | None) -> str | None:
    """Extract a one-line human-readable summary from a step result dict."""
    if not result or not isinstance(result, dict):
        return None
    parts: list[str] = []

    if "suggestions" in result:
        count = result.get("count", len(result["suggestions"]))
        parts.append(f"{count} category suggestions generated")
    if "applied" in result:
        parts.append(f"{result['applied']} categories applied")
    if "anomalies" in result:
        count = result.get("count", len(result["anomalies"]))
        parts.append(f"{count} anomalies detected")
        if result.get("threshold"):
            parts.append(f"threshold: ${result['threshold']:.0f}")
    if "report" in result:
        rlen = len(result["report"])
        parts.append(f"report generated ({rlen} chars)")
        if result.get("transactions_count"):
            parts.append(f"analyzed {result['transactions_count']} transactions")
    if "accounts_synced" in result or "transactions_synced" in result:
        a = result.get("accounts_synced", 0)
        t = result.get("transactions_synced", 0)
        parts.append(f"synced {a} accounts, {t} transactions")
    if "connection" in result:
        status = result.get("status", result.get("connection", ""))
        parts.append(f"connection {status}")
    if "saved" in result:
        parts.append("saved to memory")
    if result.get("message") and not parts:
        parts.append(result["message"])

    return "; ".join(parts) if parts else None


def _approval_preview(steps_state: list, current_index: int) -> dict | None:
    """Build a preview dict from previous step results for the approval gate."""
    preview_items: list[dict] = []
    for s in steps_state[:current_index]:
        if not isinstance(s, dict):
            continue
        res = s.get("result")
        if not res or not isinstance(res, dict):
            continue
        summary = _summarize_result(res)
        if summary:
            preview_items.append({
                "step": s.get("id", "?"),
                "summary": summary,
            })
        if "suggestions" in res:
            preview_items.append({
                "step": s.get("id", "?"),
                "type": "suggestions",
                "count": res.get("count", len(res["suggestions"])),
                "sample": res["suggestions"][:3],
            })
        elif "anomalies" in res:
            preview_items.append({
                "step": s.get("id", "?"),
                "type": "anomalies",
                "count": res.get("count", len(res["anomalies"])),
                "sample": res["anomalies"][:3],
            })
        elif "report" in res:
            preview_items.append({
                "step": s.get("id", "?"),
                "type": "report",
                "preview": res["report"][:300],
            })
    return {"items": preview_items} if preview_items else None


def _save_transcript_message(
    conversation_id: str | None,
    role: str,
    *,
    content: str | None = None,
    thinking: str | None = None,
) -> None:
    if not conversation_id:
        return
    sb = get_supabase()
    row = {"conversation_id": conversation_id, "role": role}
    if content is not None:
        row["content"] = content
    if thinking:
        row["thinking"] = thinking
    sb.table("messages").insert(row).execute()


def _narrate_event_with_mini_model(label: str, event: dict) -> tuple[str, str]:
    event_type = str(event.get("type") or "workflow_event")
    fallback = str(event.get("message") or event_type.replace("_", " "))
    fallback_thinking = f"Tracking workflow progress: {event_type}."
    try:
        client = get_openai()
        response = client.chat.completions.create(
            model=Config.OPENAI_MINI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are narrating a background workflow transcript.\n"
                        "Return strict JSON with keys: content, thinking.\n"
                        "content: one concise user-facing sentence.\n"
                        "thinking: one concise internal planning sentence."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "workflow_label": label,
                        "event": event,
                    }, default=str),
                },
            ],
            max_completion_tokens=180,
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        content = str(parsed.get("content") or "").strip()
        thinking = str(parsed.get("thinking") or "").strip()
        if not content:
            content = fallback
        if not thinking:
            thinking = fallback_thinking
        return content, thinking
    except Exception:
        return fallback, fallback_thinking


@celery.task(name="tasks.workflow_tasks.execute_workflow", bind=True, max_retries=1)
def execute_workflow(self, run_id: str) -> dict:
    """Walk through workflow steps starting from ``current_step_index``."""
    sb = get_supabase()
    task_id = getattr(getattr(self, "request", None), "id", None)

    log.info("execute_workflow started run=%s task_id=%s", run_id, task_id or "-")
    run = (
        sb.table("workflow_runs")
        .select("*, workflow_templates(steps, name)")
        .eq("id", run_id)
        .single()
        .execute()
    ).data
    if not run:
        log.error("Workflow run=%s not found", run_id)
        return {"error": f"Run {run_id} not found"}

    template_steps = (run.get("workflow_templates") or {}).get("steps") or []
    workflow_name = (run.get("workflow_templates") or {}).get("name", "unknown")
    label = _wf_label(workflow_name)
    steps_state = run.get("steps_state") or []
    input_args = run.get("input_args") or {}
    current_idx = run.get("current_step_index", 0)
    user_id = run.get("user_id")
    conversation_id = run.get("conversation_id")

    def _emit(event: dict) -> None:
        content, thinking = _narrate_event_with_mini_model(label, event)
        enriched_event = {
            **event,
            "simulated_thinking": thinking,
            "run_id": run_id,
            "workflow_name": workflow_name,
            "conversation_id": conversation_id,
        }
        publish_event(
            user_id,
            enriched_event,
        )
        _save_transcript_message(
            conversation_id,
            "assistant",
            content=content,
            thinking=thinking,
        )
        if event.get("type") in {"step_start", "step_complete", "step_failed", "step_skipped", "approval_gate"}:
            _save_transcript_message(
                conversation_id,
                "tool",
                content=json.dumps({
                    "tool_used": "workflow_step",
                    "run_id": run_id,
                    "workflow_name": workflow_name,
                    "event_type": event.get("type"),
                    "step_id": event.get("step_id"),
                    "detail": event.get("detail"),
                    "message": event.get("message"),
                    "payload": event.get("payload"),
                }, default=str),
            )

    _emit({"type": "workflow_start", "actor": "lobster",
           "message": f"Started {label} workflow ({len(template_steps)} steps)"})

    now_iso = datetime.now(timezone.utc).isoformat()
    started_at = run.get("started_at") or now_iso
    if run["status"] == "pending":
        sb.table("workflow_runs").update({
            "status": "running",
            "started_at": now_iso,
        }).eq("id", run_id).execute()
        started_at = now_iso

    for i in range(current_idx, len(template_steps)):
        step_def = template_steps[i]
        step_state = steps_state[i] if i < len(steps_state) else {
            "id": step_def.get("id", f"step_{i}"),
            "status": "pending",
            "result": None,
            "started_at": None,
            "completed_at": None,
        }

        # --- Condition gate ---
        if not _evaluate_condition(step_def.get("condition"), steps_state):
            step_state["status"] = "skipped"
            step_state["completed_at"] = datetime.now(timezone.utc).isoformat()
            steps_state[i] = step_state
            _update_run(sb, run_id, i, steps_state)
            _emit({"type": "step_skipped", "actor": "lobster",
                   "step_id": step_def.get("id", f"step_{i}"),
                   "message": f"Skipped \"{step_def.get('name', step_def.get('id'))}\" (condition not met)",
                   "payload": {"condition": step_def.get("condition")}})
            continue

        # --- Approval gate ---
        approval = step_def.get("approval")
        if approval and approval.get("required"):
            token = _generate_resume_token()
            step_state["status"] = "awaiting_approval"
            step_state["started_at"] = datetime.now(timezone.utc).isoformat()
            steps_state[i] = step_state
            sb.table("workflow_runs").update({
                "status": "paused",
                "current_step_index": i,
                "steps_state": steps_state,
                "resume_token": token,
            }).eq("id", run_id).execute()

            preview = _approval_preview(steps_state, i)
            _emit({"type": "approval_gate", "actor": "lobster",
                   "step_id": step_def.get("id", f"step_{i}"),
                   "message": f"Requires approval from user",
                   "detail": approval.get("prompt", "Approve this step?"),
                   "preview": preview,
                   "payload": {"approval": approval, "preview": preview}})
            return {
                "status": "paused",
                "run_id": run_id,
                "approval_prompt": approval.get("prompt", "Approve this step?"),
                "resume_token": token,
            }

        # --- Task execution ---
        task_path = step_def.get("task")
        if not task_path:
            step_state["status"] = "skipped"
            step_state["completed_at"] = datetime.now(timezone.utc).isoformat()
            steps_state[i] = step_state
            _update_run(sb, run_id, i, steps_state)
            continue

        step_state["status"] = "running"
        step_state["started_at"] = datetime.now(timezone.utc).isoformat()
        steps_state[i] = step_state
        _update_run(sb, run_id, i, steps_state)
        step_name = step_def.get("name", step_def.get("id", f"step_{i}"))
        step_id = step_def.get("id", f"step_{i}")

        try:
            step_input = _resolve_step_input(step_def, steps_state, input_args)
            _emit({"type": "step_start", "actor": "lobster",
                   "step_id": step_id,
                   "message": f"Running: {step_name} (step {i + 1}/{len(template_steps)})",
                   "payload": {"task": task_path, "step_input": step_input}})
            log.info("run=%s task_id=%s executing step %d task=%s", run_id, task_id or "-", i, task_path)
            result = _call_step_task(task_path, user_id, step_input)
            step_state["status"] = "completed"
            step_state["result"] = result
            log.info("run=%s task_id=%s step %d completed", run_id, task_id or "-", i)

            summary = _summarize_result(result)
            complete_msg = f"Completed: {step_name}"
            if summary:
                complete_msg += f" — {summary}"

            _emit({"type": "step_complete", "actor": "lobster",
                   "step_id": step_id,
                   "message": complete_msg,
                   "payload": {"result": result}})
        except Exception as exc:
            log.exception("run=%s task_id=%s step %d failed task=%s", run_id, task_id or "-", i, task_path)
            step_state["status"] = "failed"
            step_state["result"] = {"error": str(exc), "traceback": traceback.format_exc()[:500]}
            steps_state[i] = step_state
            _emit({"type": "step_failed", "actor": "lobster",
                   "step_id": step_id,
                   "message": f"Failed: {step_name} — {str(exc)[:200]}",
                   "payload": {"error": str(exc)}})

            elapsed = _elapsed_str(started_at)
            sb.table("workflow_runs").update({
                "status": "failed",
                "current_step_index": i,
                "steps_state": steps_state,
                "error": str(exc)[:500],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            _emit({"type": "workflow_failed", "actor": "lobster",
                   "message": f"{label} failed at \"{step_name}\" after {elapsed}"})
            _emit({"type": "workflow_done", "actor": "gateway",
                   "message": f"{label} failed after {elapsed}"})
            return {"status": "failed", "run_id": run_id, "error": str(exc)}

        step_state["completed_at"] = datetime.now(timezone.utc).isoformat()
        steps_state[i] = step_state
        _update_run(sb, run_id, i, steps_state)

    elapsed = _elapsed_str(started_at)

    final_summary_parts: list[str] = []
    for s in steps_state:
        if isinstance(s, dict) and s.get("result"):
            summary = _summarize_result(s["result"])
            if summary:
                final_summary_parts.append(summary)
    result_line = "; ".join(final_summary_parts) if final_summary_parts else ""

    log.info("Workflow run=%s completed all %d steps", run_id, len(template_steps))
    sb.table("workflow_runs").update({
        "status": "completed",
        "current_step_index": len(template_steps),
        "steps_state": steps_state,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id).execute()

    complete_msg = f"{label} completed successfully in {elapsed}"
    if result_line:
        complete_msg += f" — {result_line}"

    _emit({"type": "workflow_complete", "actor": "lobster",
           "message": complete_msg})

    gateway_msg = f"{label} completed in {elapsed} successfully"
    if result_line:
        gateway_msg += f" — {result_line}"
    _emit({"type": "workflow_done", "actor": "gateway",
           "message": gateway_msg})

    return {"status": "completed", "run_id": run_id}


def _update_run(sb, run_id: str, step_index: int, steps_state: list) -> None:
    sb.table("workflow_runs").update({
        "current_step_index": step_index,
        "steps_state": steps_state,
    }).eq("id", run_id).execute()


def _call_step_task(task_path: str, user_id: str, step_input) -> dict:
    """Import and call a step task function synchronously within the worker.

    ``task_path`` is a dotted path like ``tasks.sync_tasks.fetch_merge_data``.
    The function is expected to accept ``(user_id, input_data)`` and return a
    JSON-serialisable dict.
    """
    module_path, func_name = task_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    return func(user_id, step_input)
