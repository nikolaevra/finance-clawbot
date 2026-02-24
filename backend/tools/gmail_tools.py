"""Gmail tools for OpenAI function calling.

These tools expose Gmail operations (list, read, send, label) to the
AI agent.  Each tool resolves the user's Gmail OAuth credentials from
the ``integrations`` table before calling the underlying service.
"""
from __future__ import annotations

import json
import logging

from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase
from services import gmail_service

log = logging.getLogger(__name__)


def _get_gmail_credentials() -> str | None:
    """Return the Gmail OAuth credentials JSON for the current user,
    or None if no active Gmail integration exists."""
    user_id = getattr(g, "user_id", None)
    log.info("gmail creds lookup user=%s", user_id)
    try:
        sb = get_supabase()
        result = (
            sb.table("integrations")
            .select("account_token")
            .eq("user_id", user_id)
            .eq("provider", "gmail")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            token_json = result.data[0]["account_token"]
            try:
                info = json.loads(token_json)
                scopes = info.get("scopes", info.get("scope", "N/A"))
                log.info(
                    "gmail creds found user=%s scopes=%s token_prefix=%s",
                    user_id, scopes, token_json[:80],
                )
            except (json.JSONDecodeError, TypeError):
                log.warning("gmail creds found but not valid JSON user=%s", user_id)
            return token_json
        log.warning("no active gmail integration for user=%s", user_id)
    except Exception:
        log.exception("gmail creds lookup failed user=%s", user_id)
    return None


_NO_GMAIL = {
    "error": (
        "No active Gmail integration found. The user needs to connect "
        "Gmail first via the Integrations page."
    ),
}

_INSUFFICIENT_SCOPE_HINTS = ("insufficient", "403", "Forbidden", "access denied")


def _needs_reauth(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(h.lower() in msg for h in _INSUFFICIENT_SCOPE_HINTS)


_REAUTH_MSG = (
    "The current Gmail connection only has read-only permissions. "
    "The user needs to disconnect and reconnect Gmail on the "
    "Integrations page to grant send/modify access."
)


# ── gmail_list_messages ──────────────────────────────────────────────


@tool_registry.register(
    name="gmail_list_messages",
    label="List Gmail Messages",
    category="gmail",
    description=(
        "List messages from the user's Gmail inbox. Supports Gmail search "
        "syntax (e.g. 'is:unread', 'from:alice@example.com', "
        "'subject:invoice after:2025/01/01'). Returns message stubs with "
        "id, subject, sender, date, snippet, and labels."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Gmail search query (e.g. 'is:unread', 'from:boss@co.com', "
                    "'subject:invoice'). Empty string returns recent messages."
                ),
            },
            "label_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of Gmail label IDs to filter by "
                    "(e.g. ['INBOX'], ['UNREAD']). Leave empty for no label filter."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of messages to return (1-100, default 20).",
            },
        },
        "required": [],
    },
)
def gmail_list_messages(
    query: str = "",
    label_ids: list[str] | None = None,
    max_results: int = 20,
) -> dict:
    log.info("gmail_list_messages called query=%r label_ids=%s max=%d", query, label_ids, max_results)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_list_messages aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_list_messages"}

    try:
        messages = gmail_service.list_messages(
            creds,
            query=query,
            label_ids=label_ids,
            max_results=max_results,
        )
        log.info("gmail_list_messages success count=%d", len(messages))
        return {
            "tool_used": "gmail_list_messages",
            "source": "Gmail API",
            "query": query,
            "total_results": len(messages),
            "messages": messages,
        }
    except Exception as e:
        log.exception("gmail_list_messages failed")
        return {"error": str(e), "tool_used": "gmail_list_messages"}


# ── gmail_get_message ────────────────────────────────────────────────


@tool_registry.register(
    name="gmail_get_message",
    label="Get Gmail Message",
    category="gmail",
    description=(
        "Fetch a single Gmail message with its full body text. "
        "Use gmail_list_messages first to find the message ID, "
        "then use this to read the complete content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID to retrieve.",
            },
        },
        "required": ["message_id"],
    },
)
def gmail_get_message(message_id: str) -> dict:
    log.info("gmail_get_message called id=%s", message_id)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_get_message aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_get_message"}

    try:
        msg = gmail_service.get_message(creds, message_id)
        log.info("gmail_get_message success id=%s subject=%r", message_id, msg.get("subject"))
        return {
            "tool_used": "gmail_get_message",
            "source": "Gmail API",
            "message": msg,
        }
    except Exception as e:
        log.exception("gmail_get_message failed id=%s", message_id)
        return {"error": str(e), "tool_used": "gmail_get_message"}


# ── gmail_send_message ───────────────────────────────────────────────


@tool_registry.register(
    name="gmail_send_message",
    label="Send Gmail Message",
    category="gmail",
    description=(
        "Send an email from the user's connected Gmail account. "
        "Requires the recipient address, subject, and body text. "
        "Optionally include CC recipients."
    ),
    parameters={
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address (or comma-separated list).",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
            },
            "body": {
                "type": "string",
                "description": "Plain text email body.",
            },
            "cc": {
                "type": "string",
                "description": "CC recipients (comma-separated). Optional.",
            },
        },
        "required": ["to", "subject", "body"],
    },
)
def gmail_send_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
) -> dict:
    log.info("gmail_send_message called to=%r subject=%r cc=%r", to, subject, cc)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_send_message aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_send_message"}

    try:
        result = gmail_service.send_message(
            creds, to=to, subject=subject, body=body, cc=cc,
        )
        log.info("gmail_send_message success id=%s", result.get("id"))
        return {
            "tool_used": "gmail_send_message",
            "source": "Gmail API",
            "status": "sent",
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
        }
    except Exception as e:
        log.exception("gmail_send_message failed")
        err = _REAUTH_MSG if _needs_reauth(e) else str(e)
        return {"error": err, "tool_used": "gmail_send_message"}


# ── gmail_modify_labels ──────────────────────────────────────────────


@tool_registry.register(
    name="gmail_modify_labels",
    label="Modify Gmail Labels",
    category="gmail",
    description=(
        "Add or remove labels on a Gmail message. Common labels include "
        "INBOX, UNREAD, STARRED, IMPORTANT, SPAM, TRASH, or custom label "
        "IDs. Use gmail_get_message first to see current labels."
    ),
    parameters={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID to modify.",
            },
            "add_label_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Label IDs to add (e.g. ['STARRED', 'IMPORTANT'])."
                ),
            },
            "remove_label_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Label IDs to remove (e.g. ['UNREAD', 'INBOX'])."
                ),
            },
        },
        "required": ["message_id"],
    },
)
def gmail_modify_labels(
    message_id: str,
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
) -> dict:
    log.info("gmail_modify_labels called id=%s add=%s remove=%s", message_id, add_label_ids, remove_label_ids)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_modify_labels aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_modify_labels"}

    try:
        result = gmail_service.modify_labels(
            creds,
            message_id=message_id,
            add_label_ids=add_label_ids,
            remove_label_ids=remove_label_ids,
        )
        if "error" in result:
            log.warning("gmail_modify_labels returned error: %s", result["error"])
            return {**result, "tool_used": "gmail_modify_labels"}
        log.info("gmail_modify_labels success id=%s labels=%s", message_id, result.get("labelIds"))
        return {
            "tool_used": "gmail_modify_labels",
            "source": "Gmail API",
            "message_id": result.get("id"),
            "updated_labels": result.get("labelIds", []),
        }
    except Exception as e:
        log.exception("gmail_modify_labels failed id=%s", message_id)
        err = _REAUTH_MSG if _needs_reauth(e) else str(e)
        return {"error": err, "tool_used": "gmail_modify_labels"}
