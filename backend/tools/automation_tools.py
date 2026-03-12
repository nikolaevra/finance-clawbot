"""Automation tools for omnichannel await/resume flows."""
from __future__ import annotations

from flask import g

from tools.registry import tool_registry
from services.automation_wait_service import create_wait


@tool_registry.register(
    name="await_external_response",
    label="Await External Response",
    category="automation",
    description=(
        "Pause skill execution and wait for an inbound response event from a "
        "communication channel (email, slack, whatsapp, sms, or generic). "
        "Provide custom matcher rules and optional timeout."
    ),
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel to wait on: email, slack, whatsapp, sms, or generic.",
            },
            "matcher": {
                "type": "object",
                "description": (
                    "Custom match rules. Supports all/any/none arrays of conditions: "
                    "{field, op, value, case_sensitive}. Ops: equals, contains, in, "
                    "regex, starts_with, ends_with, exists."
                ),
            },
            "timeout_minutes": {
                "type": "integer",
                "description": "Optional timeout in minutes (1 to 43200).",
            },
            "wait_type": {
                "type": "string",
                "description": "Optional semantic wait type label.",
            },
            "correlation": {
                "type": "object",
                "description": "Optional channel correlation hints (thread_id, channel_ref, phone_number).",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata stored with the wait record.",
            },
        },
        "required": ["channel", "matcher"],
    },
)
def await_external_response(
    channel: str,
    matcher: dict,
    timeout_minutes: int | None = None,
    wait_type: str = "external_response",
    correlation: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    user_id = g.user_id
    conversation_id = getattr(g, "conversation_id", None)
    tool_call_id = getattr(g, "current_tool_call_id", None)
    wait = create_wait(
        user_id=user_id,
        conversation_id=conversation_id,
        channel=(channel or "").strip().lower(),
        matcher=matcher or {},
        wait_type=wait_type,
        timeout_minutes=timeout_minutes,
        tool_call_id=tool_call_id,
        correlation=correlation or {},
        metadata=metadata or {},
    )
    return {
        "tool_used": "await_external_response",
        "status": "awaiting_external_response",
        "pause_execution": True,
        "wait_id": wait["id"],
        "channel": wait["channel"],
        "message": f"Execution paused and awaiting {wait['channel']} response.",
        "timeout_at": wait.get("timeout_at"),
    }
