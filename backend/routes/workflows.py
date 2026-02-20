"""Workflow REST API routes — CRUD for templates, run management, approval, SSE events.

Endpoints:
  GET    /workflows                      – list workflow templates
  POST   /workflows                      – create a workflow template
  GET    /workflows/<id>                 – get template details
  PUT    /workflows/<id>                 – update template
  DELETE /workflows/<id>                 – delete template
  POST   /workflows/<id>/run             – trigger a workflow run
  GET    /workflow-runs                  – list runs (with status filter)
  GET    /workflow-runs/<id>             – get run details + step states
  POST   /workflow-runs/<id>/approve     – approve or reject a paused run
  POST   /workflow-runs/<id>/cancel      – cancel a running/paused run
  GET    /workflow-runs/<id>/events      – SSE stream for real-time run updates
"""
from __future__ import annotations

import json
import logging
import time
from flask import Blueprint, request, g, jsonify, Response, stream_with_context

from middleware.auth import require_auth

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.workflow_engine import (
    start_workflow,
    resume_workflow,
    cancel_workflow,
    get_run_status,
    list_templates,
)

workflows_bp = Blueprint("workflows", __name__)


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------

@workflows_bp.route("/workflows", methods=["GET"])
@require_auth
def list_workflow_templates():
    templates = list_templates(g.user_id)
    return jsonify(templates)


@workflows_bp.route("/workflows", methods=["POST"])
@require_auth
def create_workflow_template():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    sb = get_supabase()
    row = {
        "user_id": g.user_id,
        "name": name,
        "description": body.get("description"),
        "steps": body.get("steps", []),
        "schedule": body.get("schedule"),
        "is_active": body.get("is_active", True),
    }
    result = sb.table("workflow_templates").insert(row).execute()
    return jsonify(result.data[0]), 201


@workflows_bp.route("/workflows/<template_id>", methods=["GET"])
@require_auth
def get_workflow_template(template_id: str):
    sb = get_supabase()
    result = (
        sb.table("workflow_templates")
        .select("*")
        .eq("id", template_id)
        .or_(f"user_id.eq.{g.user_id},user_id.is.null")
        .single()
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Template not found"}), 404
    return jsonify(result.data)


@workflows_bp.route("/workflows/<template_id>", methods=["PUT"])
@require_auth
def update_workflow_template(template_id: str):
    sb = get_supabase()
    existing = (
        sb.table("workflow_templates")
        .select("id")
        .eq("id", template_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not existing.data:
        return jsonify({"error": "Template not found or not owned by user"}), 404

    body = request.get_json(silent=True) or {}
    update_fields = {}
    for field in ("name", "description", "steps", "schedule", "is_active"):
        if field in body:
            update_fields[field] = body[field]

    if not update_fields:
        return jsonify({"error": "No fields to update"}), 400

    result = (
        sb.table("workflow_templates")
        .update(update_fields)
        .eq("id", template_id)
        .execute()
    )
    return jsonify(result.data[0] if result.data else {})


@workflows_bp.route("/workflows/<template_id>", methods=["DELETE"])
@require_auth
def delete_workflow_template(template_id: str):
    sb = get_supabase()
    sb.table("workflow_templates").delete().eq("id", template_id).eq("user_id", g.user_id).execute()
    return jsonify({"status": "deleted"})


# ---------------------------------------------------------------------------
# Trigger a run from a template
# ---------------------------------------------------------------------------

@workflows_bp.route("/workflows/<template_id>/run", methods=["POST"])
@require_auth
def trigger_workflow_run(template_id: str):
    body = request.get_json(silent=True) or {}
    try:
        run = start_workflow(
            template_id=template_id,
            user_id=g.user_id,
            args=body.get("args"),
            trigger="manual",
        )
        return jsonify(run), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log.exception("trigger_workflow_run failed template=%s user=%s", template_id, g.user_id)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Run management
# ---------------------------------------------------------------------------

@workflows_bp.route("/workflow-runs", methods=["GET"])
@require_auth
def list_workflow_runs():
    sb = get_supabase()
    query = (
        sb.table("workflow_runs")
        .select("id, template_id, status, current_step_index, steps_state, trigger, error, started_at, completed_at, created_at, workflow_templates(name, description, steps)")
        .eq("user_id", g.user_id)
        .order("created_at", desc=True)
        .limit(50)
    )

    status_filter = request.args.get("status")
    if status_filter:
        query = query.eq("status", status_filter)

    result = query.execute()
    return jsonify(result.data or [])


@workflows_bp.route("/workflow-runs/<run_id>", methods=["GET"])
@require_auth
def get_workflow_run(run_id: str):
    try:
        run = get_run_status(run_id)
        return jsonify(run)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@workflows_bp.route("/workflow-runs/<run_id>/approve", methods=["POST"])
@require_auth
def approve_workflow_run(run_id: str):
    body = request.get_json(silent=True) or {}
    approve = body.get("approve", True)
    comment = body.get("comment")

    try:
        run = resume_workflow(run_id, approve=approve, comment=comment)
        return jsonify(run)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("approve_workflow_run failed run=%s", run_id)
        return jsonify({"error": str(e)}), 500


@workflows_bp.route("/workflow-runs/<run_id>/cancel", methods=["POST"])
@require_auth
def cancel_workflow_run(run_id: str):
    try:
        run = cancel_workflow(run_id)
        return jsonify(run)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("cancel_workflow_run failed run=%s", run_id)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# SSE stream for real-time run updates
# ---------------------------------------------------------------------------

@workflows_bp.route("/workflow-runs/<run_id>/events", methods=["GET"])
@require_auth
def workflow_run_events(run_id: str):
    """Long-poll SSE stream that emits run state changes until terminal."""

    def generate():
        last_status = None
        last_step = -1
        poll_interval = 1
        max_polls = 300  # 5 minutes max

        for _ in range(max_polls):
            try:
                run = get_run_status(run_id)
            except Exception:
                yield f"event: error\ndata: {json.dumps({'error': 'Run not found'})}\n\n"
                return

            current_status = run["status"]
            current_step = run.get("current_step_index", 0)

            if current_status != last_status or current_step != last_step:
                payload = {
                    "run_id": run["id"],
                    "status": current_status,
                    "current_step_index": current_step,
                    "steps_state": run.get("steps_state"),
                }
                if current_status == "paused":
                    payload["resume_token"] = run.get("resume_token")
                if current_status == "failed":
                    payload["error"] = run.get("error")

                yield f"event: workflow_update\ndata: {json.dumps(payload)}\n\n"
                last_status = current_status
                last_step = current_step

            if current_status in ("completed", "failed", "cancelled"):
                yield f"event: workflow_done\ndata: {json.dumps({'status': current_status})}\n\n"
                return

            time.sleep(poll_interval)

        yield f"event: workflow_timeout\ndata: {json.dumps({'message': 'SSE stream timeout'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
