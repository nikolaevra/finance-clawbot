"""Activity SSE endpoint for real-time system activity.

The frontend opens an EventSource connection to this endpoint.  Events are
pushed to per-user Redis lists by Gateway / Lobster workers.  A Redis
Pub/Sub notification wakes the SSE generator so events are delivered with
near-zero latency.
"""
from __future__ import annotations

import json
import logging
import time

import redis
from flask import Blueprint, Response, g, request, stream_with_context

from config import Config
from middleware.auth import require_auth
from services.event_bus import get_events_since, notify_channel

log = logging.getLogger(__name__)

activity_bp = Blueprint("activity", __name__)

_HEARTBEAT_INTERVAL = 15   # seconds between SSE keep-alive comments
_PUBSUB_TIMEOUT = 1        # seconds to block on Redis Pub/Sub per iteration


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
        events, cursor = get_events_since(user_id, initial_cursor)
        yield f"event: activity\ndata: {json.dumps({'events': events, 'cursor': cursor})}\n\n"

        client = redis.Redis.from_url(
            Config.CELERY_BROKER_URL, decode_responses=True
        )
        pubsub = client.pubsub()
        channel = notify_channel(user_id)
        pubsub.subscribe(channel)

        try:
            last_heartbeat = time.monotonic()

            while True:
                msg = pubsub.get_message(timeout=_PUBSUB_TIMEOUT)
                now = time.monotonic()

                if msg and msg["type"] == "message":
                    events, cursor = get_events_since(user_id, cursor)
                    if events:
                        yield (
                            f"event: activity\n"
                            f"data: {json.dumps({'events': events, 'cursor': cursor})}\n\n"
                        )

                if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()
            client.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
