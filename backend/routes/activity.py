"""Activity SSE endpoint backed by durable audit log records."""
from __future__ import annotations

import json
import time

from flask import Blueprint, Response, g, request, stream_with_context

from middleware.auth import require_auth
from services.audit_log_service import fetch_activity_events_since

activity_bp = Blueprint("activity", __name__)

_HEARTBEAT_INTERVAL = 15   # seconds between SSE keep-alive comments
_POLL_INTERVAL = 1.0       # seconds between DB polling iterations


@activity_bp.route("/activity/events", methods=["GET"])
@require_auth
def activity_events():
    """SSE stream of activity events."""
    cursor_raw = request.args.get("cursor", "-1")
    try:
        initial_cursor = int(cursor_raw)
    except (ValueError, TypeError):
        initial_cursor = -1

    user_id = g.user_id

    def generate():
        # Match prior semantics: cursor=-1 means "start fresh now".
        cursor = max(initial_cursor, 0)
        last_seen = None
        if initial_cursor < 0:
            yield f"event: activity\ndata: {json.dumps({'events': [], 'cursor': cursor})}\n\n"
        else:
            bootstrap_events = fetch_activity_events_since(user_id=user_id, limit=200)
            if bootstrap_events:
                last_seen = bootstrap_events[-1].get("timestamp")
                cursor += len(bootstrap_events)
            yield f"event: activity\ndata: {json.dumps({'events': bootstrap_events, 'cursor': cursor})}\n\n"

        last_heartbeat = time.monotonic()
        while True:
            now = time.monotonic()
            events = fetch_activity_events_since(
                user_id=user_id,
                after_occurred_at=last_seen,
                limit=200,
            )
            if events:
                last_seen = events[-1].get("timestamp")
                cursor += len(events)
                yield (
                    f"event: activity\n"
                    f"data: {json.dumps({'events': events, 'cursor': cursor})}\n\n"
                )

            if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            time.sleep(_POLL_INTERVAL)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
