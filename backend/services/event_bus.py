"""Redis list event bus for real-time activity streaming.

Gateway and Lobster workers push structured events to per-user Redis lists.
An SSE endpoint subscribes to a Redis Pub/Sub channel to push events to
the frontend in real time.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import redis

from config import Config

log = logging.getLogger(__name__)

_redis_url = Config.CELERY_BROKER_URL

_EVENT_TTL = 300  # keep events for 5 minutes
_MAX_EVENTS = 500  # cap list length


def _list_key(user_id: str) -> str:
    return f"activity_events:{user_id}"


def notify_channel(user_id: str) -> str:
    """Redis Pub/Sub channel name used to wake up SSE listeners."""
    return f"activity_notify:{user_id}"


def _get_client() -> redis.Redis:
    return redis.Redis.from_url(_redis_url, decode_responses=True)


def publish_event(user_id: str, event: dict[str, Any]) -> None:
    """Push an event to the user's event list in Redis."""
    if not user_id:
        return
    try:
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        key = _list_key(user_id)
        payload = json.dumps(event)
        client = _get_client()
        pipe = client.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -_MAX_EVENTS, -1)
        pipe.expire(key, _EVENT_TTL)
        pipe.publish(notify_channel(user_id), "1")
        pipe.execute()
        client.close()
        log.info(
            "event_bus: pushed %s for user=%s (pid=%d)",
            event.get("type", "?"),
            user_id[:8],
            os.getpid(),
        )
    except Exception:
        log.warning("event_bus publish failed for user=%s", user_id, exc_info=True)


def get_events_since(user_id: str, cursor: int) -> tuple[list[dict[str, Any]], int]:
    """Return (new_events, new_cursor) since the given cursor index.

    ``cursor`` is the index of the last event the client has seen.
    Pass ``0`` to get all current events, or ``-1`` to start fresh
    (returns empty list and current length as cursor).
    """
    try:
        client = _get_client()
        key = _list_key(user_id)

        if cursor < 0:
            length = client.llen(key)
            client.close()
            return [], length

        items = client.lrange(key, cursor, -1)
        new_cursor = cursor + len(items)
        client.close()

        events: list[dict[str, Any]] = []
        for raw in items:
            try:
                events.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue

        return events, new_cursor
    except Exception:
        log.warning("event_bus get_events_since failed for user=%s", user_id, exc_info=True)
        return [], cursor
