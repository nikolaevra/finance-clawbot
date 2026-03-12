"""Normalize inbound provider events into a channel-agnostic shape."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.automation_wait_service import extract_sender_email


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SUPPORTED_PROVIDERS = {"gmail": {"channel": "email"}}


def provider_channel(provider: str) -> str:
    info = SUPPORTED_PROVIDERS.get(provider)
    if not info:
        raise ValueError(f"Unsupported provider '{provider}'")
    return str(info["channel"])


def normalize_gmail_event(*, integration_id: str, event: dict[str, Any], user_id: str) -> dict[str, Any]:
    message_id = str(event.get("message_id") or "").strip()
    thread_id = str(event.get("thread_id") or "").strip()
    sender = str(event.get("from") or "").strip()
    normalized = {
        "provider": "gmail",
        "provider_event_id": f"gmail:{integration_id}:{message_id}" if message_id else "",
        "user_id": user_id,
        "channel": "email",
        "timestamp": _now_iso(),
        "sender": sender,
        "sender_email": extract_sender_email(sender),
        "recipient": None,
        "subject": str(event.get("subject") or ""),
        "body_text": str(event.get("snippet") or ""),
        "thread_ref": thread_id or None,
        "metadata": {
            "message_id": message_id,
            "thread_id": thread_id,
            "label_ids": event.get("label_ids") or [],
            "is_inbox": bool(event.get("is_inbox", True)),
            "date": event.get("date"),
        },
    }
    return normalized


def normalize_event(
    *,
    provider: str,
    user_id: str,
    integration_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider '{provider}'")
    if provider == "gmail":
        normalized = normalize_gmail_event(integration_id=integration_id, event=payload, user_id=user_id)
    else:
        raise ValueError(f"Unsupported provider '{provider}'")
    if not normalized.get("provider_event_id"):
        raise ValueError("Normalized event missing provider_event_id")
    return normalized
