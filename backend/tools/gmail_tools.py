"""Gmail tools for OpenAI function calling.

These tools expose Gmail operations (list, read, send, label) to the
AI agent.  Each tool resolves the user's Gmail OAuth credentials from
the ``integrations`` table before calling the underlying service.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase
from services import gmail_service

log = logging.getLogger(__name__)


def _get_gmail_integration() -> dict | None:
    """Return the active Gmail integration row for the current user."""
    user_id = getattr(g, "user_id", None)
    log.info("gmail integration lookup user=%s", user_id)
    try:
        sb = get_supabase()
        result = (
            sb.table("integrations")
            .select("id, user_id, account_token, gmail_history_id")
            .eq("user_id", user_id)
            .eq("provider", "gmail")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        log.warning("no active gmail integration for user=%s", user_id)
    except Exception:
        log.exception("gmail integration lookup failed user=%s", user_id)
    return None


def _get_gmail_credentials() -> str | None:
    """Return the Gmail OAuth credentials JSON for the current user,
    or None if no active Gmail integration exists."""
    user_id = getattr(g, "user_id", None)
    row = _get_gmail_integration()
    if row:
        token_json = row["account_token"]
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


def _enqueue_delta_sync(integration_id: str) -> bool:
    try:
        from tasks.email_sync_tasks import sync_gmail_history_delta

        sync_gmail_history_delta.delay(integration_id)
        return True
    except Exception:
        log.exception("gmail local refresh enqueue failed integration_id=%s", integration_id)
        return False


def _search_local_messages(
    integration_id: str,
    query: str,
    label_ids: list[str] | None,
    max_results: int,
) -> list[dict]:
    """Best-effort local cache query for Gmail list semantics."""
    sb = get_supabase()
    max_results = min(max(max_results, 1), 100)
    rows = (
        sb.table("emails")
        .select("gmail_message_id, gmail_thread_id, snippet, subject, from_json, to_json, internal_date_ts, label_ids_json, is_read, is_sent, is_draft")
        .eq("user_id", g.user_id)
        .eq("integration_id", integration_id)
        .is_("deleted_at", "null")
        .order("internal_date_ts", desc=True)
        .limit(min(max_results * 10, 500))
        .execute()
    ).data or []

    q = (query or "").strip().lower()

    def _match(row: dict) -> bool:
        labels = row.get("label_ids_json", []) or []
        if label_ids and not all(label in labels for label in label_ids):
            return False

        if not q:
            return True

        if "is:unread" in q and row.get("is_read", True):
            return False
        if "in:sent" in q and not row.get("is_sent", False):
            return False
        if "in:draft" in q and not row.get("is_draft", False):
            return False
        if "in:inbox" in q and "INBOX" not in labels:
            return False

        from_match = re.search(r"from:([^\s]+)", q)
        if from_match:
            needle = from_match.group(1)
            sender = ((row.get("from_json") or {}).get("email", "") or "").lower()
            if needle not in sender:
                return False

        subject_match = re.search(r"subject:([^\s]+)", q)
        if subject_match:
            needle = subject_match.group(1)
            subject = (row.get("subject", "") or "").lower()
            if needle not in subject:
                return False

        residual = re.sub(r"(is:unread|in:sent|in:draft|in:inbox|from:[^\s]+|subject:[^\s]+)", "", q).strip()
        if residual:
            hay = f"{(row.get('subject', '') or '').lower()} {(row.get('snippet', '') or '').lower()}"
            if residual not in hay:
                return False
        return True

    filtered = [row for row in rows if _match(row)]
    messages: list[dict] = []
    for row in filtered[:max_results]:
        sender = row.get("from_json") or {}
        to_list = row.get("to_json") or []
        from_email = sender.get("email", "") or ""
        from_name = sender.get("name", "") or ""
        from_value = f"{from_name} <{from_email}>".strip() if from_name else from_email
        to_value = ", ".join([item.get("email", "") for item in to_list if item.get("email")])
        date_value = ""
        internal_ts = row.get("internal_date_ts")
        if isinstance(internal_ts, int):
            date_value = datetime.fromtimestamp(internal_ts / 1000, timezone.utc).isoformat()
        messages.append(
            {
                "id": row.get("gmail_message_id"),
                "threadId": row.get("gmail_thread_id"),
                "snippet": row.get("snippet", ""),
                "subject": row.get("subject", ""),
                "from": from_value,
                "to": to_value,
                "date": date_value,
                "labelIds": row.get("label_ids_json", []) or [],
            }
        )
    return messages


def _get_local_message(integration_id: str, message_id: str) -> dict | None:
    sb = get_supabase()
    rows = (
        sb.table("emails")
        .select("*")
        .eq("user_id", g.user_id)
        .eq("integration_id", integration_id)
        .eq("gmail_message_id", message_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    from_json = row.get("from_json") or {}
    to_json = row.get("to_json") or []
    cc_json = row.get("cc_json") or []
    return {
        "id": row.get("gmail_message_id"),
        "threadId": row.get("gmail_thread_id"),
        "subject": row.get("subject", ""),
        "from": from_json.get("email", ""),
        "from_address": from_json.get("email", ""),
        "to": ", ".join([item.get("email", "") for item in to_json if item.get("email")]),
        "cc": ", ".join([item.get("email", "") for item in cc_json if item.get("email")]),
        "date": (
            datetime.fromtimestamp(row["internal_date_ts"] / 1000, timezone.utc).isoformat()
            if isinstance(row.get("internal_date_ts"), int)
            else ""
        ),
        "snippet": row.get("snippet", ""),
        "body_text": row.get("body_text", ""),
        "labelIds": row.get("label_ids_json", []) or [],
        "attachments": [],
    }


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
            "source": {
                "type": "string",
                "description": (
                    "Read source: 'auto' (default, local cache first with remote fallback), "
                    "'local' (cache only), or 'remote' (Gmail API)."
                ),
            },
            "refresh_local": {
                "type": "boolean",
                "description": "If true, enqueue a background delta sync before reading local cache.",
            },
        },
        "required": [],
    },
)
def gmail_list_messages(
    query: str = "",
    label_ids: list[str] | None = None,
    max_results: int = 20,
    source: str = "auto",
    refresh_local: bool = False,
) -> dict:
    log.info(
        "gmail_list_messages called query=%r label_ids=%s max=%d source=%s refresh_local=%s",
        query, label_ids, max_results, source, refresh_local
    )
    integration = _get_gmail_integration()
    if not integration:
        log.warning("gmail_list_messages aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_list_messages"}

    source = (source or "auto").lower()
    sync_enqueued = _enqueue_delta_sync(integration["id"]) if refresh_local else False

    if source in ("auto", "local"):
        try:
            messages = _search_local_messages(integration["id"], query, label_ids, max_results)
            if source == "local" or messages:
                return {
                    "tool_used": "gmail_list_messages",
                    "source": "Local cache",
                    "query": query,
                    "total_results": len(messages),
                    "messages": messages,
                    "sync_enqueued": sync_enqueued,
                }
        except Exception:
            log.exception("gmail_list_messages local cache query failed")
            if source == "local":
                return {"error": "Local inbox cache query failed", "tool_used": "gmail_list_messages"}

    creds = integration["account_token"]
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
            "sync_enqueued": sync_enqueued,
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
            "source": {
                "type": "string",
                "description": (
                    "Read source: 'auto' (default, local cache first with remote fallback), "
                    "'local' (cache only), or 'remote' (Gmail API)."
                ),
            },
            "refresh_local": {
                "type": "boolean",
                "description": "If true, enqueue a background delta sync before reading local cache.",
            },
        },
        "required": ["message_id"],
    },
)
def gmail_get_message(message_id: str, source: str = "auto", refresh_local: bool = False) -> dict:
    log.info("gmail_get_message called id=%s source=%s refresh_local=%s", message_id, source, refresh_local)
    integration = _get_gmail_integration()
    if not integration:
        log.warning("gmail_get_message aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_get_message"}

    source = (source or "auto").lower()
    sync_enqueued = _enqueue_delta_sync(integration["id"]) if refresh_local else False

    if source in ("auto", "local"):
        try:
            msg = _get_local_message(integration["id"], message_id)
            if msg:
                return {
                    "tool_used": "gmail_get_message",
                    "source": "Local cache",
                    "message": msg,
                    "sync_enqueued": sync_enqueued,
                }
            if source == "local":
                return {
                    "tool_used": "gmail_get_message",
                    "source": "Local cache",
                    "error": "Message not found in local cache yet. Try refresh_local=true or source='remote'.",
                    "sync_enqueued": sync_enqueued,
                }
        except Exception:
            log.exception("gmail_get_message local cache query failed id=%s", message_id)
            if source == "local":
                return {"error": "Local inbox cache query failed", "tool_used": "gmail_get_message"}

    creds = integration["account_token"]
    try:
        msg = gmail_service.get_message(creds, message_id)
        log.info("gmail_get_message success id=%s subject=%r", message_id, msg.get("subject"))
        return {
            "tool_used": "gmail_get_message",
            "source": "Gmail API",
            "message": msg,
            "sync_enqueued": sync_enqueued,
        }
    except Exception as e:
        log.exception("gmail_get_message failed id=%s", message_id)
        return {"error": str(e), "tool_used": "gmail_get_message"}


# ── gmail_refresh_local_emails ───────────────────────────────────────


@tool_registry.register(
    name="gmail_refresh_local_emails",
    label="Refresh Local Gmail Cache",
    category="gmail",
    description=(
        "Enqueue a background sync to refresh locally stored Gmail emails. "
        "Use this to improve freshness before local cache reads."
    ),
    parameters={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "description": "Sync mode: 'delta' (default) or 'full' for initial-style backfill.",
            },
        },
        "required": [],
    },
)
def gmail_refresh_local_emails(mode: str = "delta") -> dict:
    integration = _get_gmail_integration()
    if not integration:
        return {**_NO_GMAIL, "tool_used": "gmail_refresh_local_emails"}

    mode = (mode or "delta").lower()
    try:
        if mode == "full":
            from tasks.email_sync_tasks import kickoff_initial_gmail_sync

            kickoff_initial_gmail_sync.delay(integration["id"])
            task_name = "kickoff_initial_gmail_sync"
        else:
            from tasks.email_sync_tasks import sync_gmail_history_delta

            sync_gmail_history_delta.delay(integration["id"])
            task_name = "sync_gmail_history_delta"

        sb = get_supabase()
        state_rows = (
            sb.table("gmail_sync_state")
            .select("last_history_id, last_full_sync_at, last_delta_sync_at, sync_cursor_status, last_error")
            .eq("integration_id", integration["id"])
            .limit(1)
            .execute()
        ).data or []
        state = state_rows[0] if state_rows else {}

        return {
            "tool_used": "gmail_refresh_local_emails",
            "status": "queued",
            "mode": mode,
            "task": task_name,
            "integration_id": integration["id"],
            "sync_state": state,
        }
    except Exception as exc:
        log.exception("gmail_refresh_local_emails failed integration_id=%s", integration["id"])
        return {"error": str(exc), "tool_used": "gmail_refresh_local_emails"}


# ── gmail_send_message ───────────────────────────────────────────────


@tool_registry.register(
    name="gmail_send_message",
    label="Send Gmail Message",
    category="gmail",
    requires_approval=True,
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


# ── gmail_create_draft ───────────────────────────────────────────────


@tool_registry.register(
    name="gmail_create_draft",
    label="Create Gmail Draft",
    category="gmail",
    description=(
        "Create a draft email in the user's Gmail account without sending it. "
        "Useful when the user wants to review or edit the message before "
        "sending. The draft will appear in their Gmail Drafts folder."
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
def gmail_create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
) -> dict:
    log.info("gmail_create_draft called to=%r subject=%r cc=%r", to, subject, cc)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_create_draft aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_create_draft"}

    try:
        result = gmail_service.create_draft(
            creds, to=to, subject=subject, body=body, cc=cc,
        )
        log.info("gmail_create_draft success draft_id=%s", result.get("id"))
        return {
            "tool_used": "gmail_create_draft",
            "source": "Gmail API",
            "status": "draft_created",
            "draft_id": result.get("id"),
            "message_id": result.get("message_id"),
            "thread_id": result.get("thread_id"),
        }
    except Exception as e:
        log.exception("gmail_create_draft failed")
        err = _REAUTH_MSG if _needs_reauth(e) else str(e)
        return {"error": err, "tool_used": "gmail_create_draft"}


# ── gmail_reply_message ──────────────────────────────────────────────


@tool_registry.register(
    name="gmail_reply_message",
    label="Reply to Gmail Message",
    category="gmail",
    requires_approval=True,
    description=(
        "Reply to an existing Gmail message. The reply is threaded onto "
        "the original conversation. Requires the original message ID "
        "(use gmail_get_message to read the message first) and the reply "
        "body text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID to reply to.",
            },
            "body": {
                "type": "string",
                "description": "Plain text reply body.",
            },
            "cc": {
                "type": "string",
                "description": "CC recipients (comma-separated). Optional.",
            },
        },
        "required": ["message_id", "body"],
    },
)
def gmail_reply_message(
    message_id: str,
    body: str,
    cc: str = "",
) -> dict:
    log.info("gmail_reply_message called id=%s cc=%r", message_id, cc)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_reply_message aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_reply_message"}

    try:
        result = gmail_service.reply_message(
            creds, message_id=message_id, body=body, cc=cc,
        )
        log.info("gmail_reply_message success id=%s", result.get("id"))
        return {
            "tool_used": "gmail_reply_message",
            "source": "Gmail API",
            "status": "sent",
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
        }
    except Exception as e:
        log.exception("gmail_reply_message failed id=%s", message_id)
        err = _REAUTH_MSG if _needs_reauth(e) else str(e)
        return {"error": err, "tool_used": "gmail_reply_message"}


# ── gmail_forward_message ───────────────────────────────────────────


@tool_registry.register(
    name="gmail_forward_message",
    label="Forward Gmail Message",
    category="gmail",
    requires_approval=True,
    description=(
        "Forward a Gmail message to one or more recipients. Includes the "
        "original message body with a forwarded-message header. Optionally "
        "add a comment above the forwarded content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID to forward.",
            },
            "to": {
                "type": "string",
                "description": "Recipient email address (or comma-separated list).",
            },
            "body": {
                "type": "string",
                "description": (
                    "Optional comment to include above the forwarded message."
                ),
            },
            "cc": {
                "type": "string",
                "description": "CC recipients (comma-separated). Optional.",
            },
        },
        "required": ["message_id", "to"],
    },
)
def gmail_forward_message(
    message_id: str,
    to: str,
    body: str = "",
    cc: str = "",
) -> dict:
    log.info("gmail_forward_message called id=%s to=%r cc=%r", message_id, to, cc)
    creds = _get_gmail_credentials()
    if not creds:
        log.warning("gmail_forward_message aborted — no credentials")
        return {**_NO_GMAIL, "tool_used": "gmail_forward_message"}

    try:
        result = gmail_service.forward_message(
            creds, message_id=message_id, to=to, body=body, cc=cc,
        )
        log.info("gmail_forward_message success id=%s", result.get("id"))
        return {
            "tool_used": "gmail_forward_message",
            "source": "Gmail API",
            "status": "sent",
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
        }
    except Exception as e:
        log.exception("gmail_forward_message failed id=%s", message_id)
        err = _REAUTH_MSG if _needs_reauth(e) else str(e)
        return {"error": err, "tool_used": "gmail_forward_message"}


# ── gmail_modify_labels ──────────────────────────────────────────────


@tool_registry.register(
    name="gmail_modify_labels",
    label="Modify Gmail Labels",
    category="gmail",
    requires_approval=True,
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
