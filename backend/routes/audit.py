"""Audit log retrieval routes."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from middleware.auth import require_auth
from services.audit_log_service import get_audit_event, list_audit_events

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/audit/events", methods=["GET"])
@require_auth
def list_events():
    limit = request.args.get("limit", "100")
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 100

    events = list_audit_events(
        user_id=g.user_id,
        limit=parsed_limit,
        cursor=request.args.get("cursor"),
        category=request.args.get("category"),
        event_type=request.args.get("event_type"),
        source=request.args.get("source"),
        from_ts=request.args.get("from"),
        to_ts=request.args.get("to"),
    )
    next_cursor = events[-1]["occurred_at"] if events else None
    return jsonify({"events": events, "next_cursor": next_cursor})


@audit_bp.route("/audit/events/<event_id>", methods=["GET"])
@require_auth
def get_event(event_id: str):
    event = get_audit_event(g.user_id, event_id)
    if not event:
        return jsonify({"error": "Not found"}), 404
    return jsonify(event)
