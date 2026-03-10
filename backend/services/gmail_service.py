"""
Google Gmail API client.

Handles OAuth URL generation, code exchange, and full Gmail operations:
read, send, and label modification.
"""
from __future__ import annotations

import json
import logging
import base64
import hashlib
import hmac
import secrets
import time
from typing import Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parseaddr

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import g, has_request_context

from config import Config
from services.audit_log_service import log_external_api_call

log = logging.getLogger(__name__)
def _log_gmail_call(
    *,
    operation: str,
    status: str,
    started: float,
    error_message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if not has_request_context():
        return
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return
    log_external_api_call(
        user_id=user_id,
        service="gmail",
        operation=operation,
        status=status,
        duration_ms=(time.monotonic() - started) * 1000,
        error_message=error_message,
        details=details,
    )



SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _state_secret() -> str:
    # Reuse existing secret config; this should always be set in deployed envs.
    return Config.GOOGLE_CLIENT_SECRET or "dev-oauth-state-secret"


def build_oauth_state(user_id: str, code_verifier: str) -> str:
    """Create a signed OAuth state payload carrying user and PKCE verifier."""
    payload = {
        "u": user_id,
        "cv": code_verifier,
        "ts": int(time.time()),
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(
        _state_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"v1.{body}.{sig}"


def parse_oauth_state(state: str, max_age_seconds: int = 900) -> tuple[str, str | None]:
    """Parse state and return (user_id, code_verifier).

    Backward compatible with older plain-user-id state values.
    """
    if not state.startswith("v1."):
        return state, None

    parts = state.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid OAuth state format")
    _, body, supplied_sig = parts
    expected_sig = hmac.new(
        _state_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_sig, supplied_sig):
        raise ValueError("Invalid OAuth state signature")

    payload = json.loads(_b64url_decode(body).decode("utf-8"))
    user_id = str(payload.get("u", "")).strip()
    code_verifier = str(payload.get("cv", "")).strip()
    ts = int(payload.get("ts", 0) or 0)
    if not user_id:
        raise ValueError("Missing user in OAuth state")
    if not code_verifier:
        raise ValueError("Missing code verifier in OAuth state")
    if ts and int(time.time()) - ts > max_age_seconds:
        raise ValueError("OAuth state expired")
    return user_id, code_verifier


def _client_config() -> dict:
    return {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [Config.GOOGLE_REDIRECT_URI],
        }
    }


def get_auth_url(user_id: str) -> str:
    """Build a Google OAuth consent URL.  *user_id* is passed as ``state``
    so the callback can identify the user."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = Config.GOOGLE_REDIRECT_URI
    code_verifier = secrets.token_urlsafe(64)
    flow.code_verifier = code_verifier
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=build_oauth_state(user_id, code_verifier),
        code_challenge_method="S256",
    )
    return url


def exchange_code(code: str, code_verifier: str | None = None) -> str:
    """Exchange an authorization *code* for OAuth credentials.
    Returns a JSON string suitable for storage in the DB."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = Config.GOOGLE_REDIRECT_URI
    if code_verifier:
        flow.code_verifier = code_verifier
        flow.fetch_token(code=code, code_verifier=code_verifier)
    else:
        flow.fetch_token(code=code)
    creds = flow.credentials
    return creds.to_json()


def _build_service(credentials_json: str):
    """Build an authorized Gmail API client from stored credentials.

    Scopes are NOT overridden here — the credentials carry whatever
    scopes were granted at authorization time.  This avoids
    ``invalid_scope`` errors when refreshing tokens that were issued
    before we expanded SCOPES.
    """
    info = json.loads(credentials_json)
    granted_scopes = info.get("scopes", info.get("scope", []))
    has_refresh = bool(info.get("refresh_token"))
    log.info(
        "_build_service granted_scopes=%s has_refresh_token=%s expired=%s",
        granted_scopes,
        has_refresh,
        info.get("expiry", "N/A"),
    )
    creds = Credentials.from_authorized_user_info(info)
    log.info(
        "_build_service creds.valid=%s creds.expired=%s creds.scopes=%s",
        creds.valid, creds.expired, creds.scopes,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_profile(credentials_json: str) -> dict[str, str]:
    """Return Gmail profile basics used for webhook routing."""
    service = _build_service(credentials_json)
    profile = service.users().getProfile(userId="me").execute()
    return {
        "emailAddress": profile.get("emailAddress", ""),
        "historyId": str(profile.get("historyId", "")),
    }


def register_inbox_watch(credentials_json: str, topic_name: str) -> dict[str, str]:
    """Register Gmail push watch for inbox changes.

    Returns ``historyId`` and ``expiration`` from Gmail API response.
    """
    if not topic_name:
        raise ValueError("topic_name is required for Gmail watch registration")

    started = time.monotonic()
    try:
        service = _build_service(credentials_json)
        response = (
            service.users()
            .watch(
                userId="me",
                body={
                    "topicName": topic_name,
                    "labelIds": ["INBOX"],
                    "labelFilterAction": "include",
                },
            )
            .execute()
        )
        _log_gmail_call(operation="users.watch", status="success", started=started)
        return {
            "historyId": str(response.get("historyId", "")),
            "expiration": str(response.get("expiration", "")),
        }
    except Exception as exc:
        _log_gmail_call(
            operation="users.watch",
            status="error",
            started=started,
            error_message=str(exc),
        )
        raise


def list_new_inbox_messages_since(
    credentials_json: str,
    start_history_id: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return new inbox message summaries since a history cursor."""
    started = time.monotonic()
    service = _build_service(credentials_json)

    if not start_history_id:
        profile = get_profile(credentials_json)
        _log_gmail_call(
            operation="users.history.list + users.getProfile",
            status="success",
            started=started,
            details={"events": 0, "cursor_seeded": True},
        )
        return [], profile.get("historyId")

    try:
        history_resp = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
            )
            .execute()
        )
    except Exception:
        # Cursor can expire; caller can re-seed from latest profile historyId.
        profile = get_profile(credentials_json)
        _log_gmail_call(
            operation="users.history.list + users.getProfile",
            status="success",
            started=started,
            details={"events": 0, "cursor_reseeded": True},
        )
        return [], profile.get("historyId")

    seen_ids: set[str] = set()
    events: list[dict[str, Any]] = []
    skipped_missing = 0
    for row in history_resp.get("history", []):
        for added in row.get("messagesAdded", []) or []:
            msg = added.get("message") or {}
            msg_id = msg.get("id")
            if not msg_id or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
            try:
                full = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                    .execute()
                )
            except HttpError as exc:
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status == 404:
                    skipped_missing += 1
                    log.info("gmail_history_message_missing id=%s status=404 (skipping)", msg_id)
                    continue
                log.warning("gmail_history_message_fetch_failed id=%s status=%s", msg_id, status, exc_info=True)
                continue
            except Exception:
                log.warning("gmail_history_message_fetch_failed id=%s", msg_id, exc_info=True)
                continue
            headers = {
                h["name"].lower(): h["value"]
                for h in full.get("payload", {}).get("headers", [])
            }
            labels = full.get("labelIds", []) or []
            events.append(
                {
                    "message_id": msg_id,
                    "thread_id": full.get("threadId"),
                    "subject": headers.get("subject", ""),
                    "from": headers.get("from", ""),
                    "date": headers.get("date", ""),
                    "snippet": full.get("snippet", ""),
                    "label_ids": labels,
                    "is_inbox": "INBOX" in labels,
                }
            )

    latest_history_id = str(history_resp.get("historyId") or start_history_id)
    _log_gmail_call(
        operation="users.history.list + users.messages.get(metadata)",
        status="success",
        started=started,
        details={"events": len(events), "skipped_missing": skipped_missing},
    )
    return events, latest_history_id


def fetch_emails(credentials_json: str, max_results: int = 100, since: str | None = None) -> list[dict]:
    """Fetch recent inbox messages.  Returns a list of dicts ready for DB upsert.

    *since* is an RFC-2822 or ISO date string used in the Gmail ``after:`` query.
    """
    service = _build_service(credentials_json)

    query = "in:inbox"
    if since:
        query += f" after:{since}"

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    message_ids = [m["id"] for m in results.get("messages", [])]

    emails: list[dict] = []
    for msg_id in message_ids:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

        body_text = ""
        payload = msg.get("payload", {})
        if payload.get("body", {}).get("data"):
            body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        else:
            for part in payload.get("parts", []):
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break

        _, from_addr = parseaddr(headers.get("from", ""))

        emails.append({
            "remote_id": msg_id,
            "thread_id": msg.get("threadId"),
            "subject": headers.get("subject", ""),
            "from_address": from_addr,
            "to_addresses": headers.get("to", ""),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body_text": body_text[:10000],
            "labels": msg.get("labelIds", []),
        })

    return emails


def list_message_ids_page(
    credentials_json: str,
    query: str = "",
    label_ids: list[str] | None = None,
    max_results: int = 100,
    page_token: str | None = None,
) -> dict[str, Any]:
    """Return one page of Gmail message IDs for mailbox sync jobs."""
    service = _build_service(credentials_json)
    max_results = min(max(max_results, 1), 500)

    kwargs: dict[str, Any] = {"userId": "me", "maxResults": max_results}
    if query:
        kwargs["q"] = query
    if label_ids:
        kwargs["labelIds"] = label_ids
    if page_token:
        kwargs["pageToken"] = page_token

    result = service.users().messages().list(**kwargs).execute()
    return {
        "message_ids": [m["id"] for m in result.get("messages", []) if m.get("id")],
        "next_page_token": result.get("nextPageToken"),
        "result_size_estimate": int(result.get("resultSizeEstimate", 0) or 0),
    }


def get_message_raw(
    credentials_json: str,
    message_id: str,
    format: str = "metadata",
    metadata_headers: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch raw Gmail message payload with caller-selected format."""
    service = _build_service(credentials_json)
    kwargs: dict[str, Any] = {"userId": "me", "id": message_id, "format": format}
    if metadata_headers:
        kwargs["metadataHeaders"] = metadata_headers
    return service.users().messages().get(**kwargs).execute()


def list_history_page(
    credentials_json: str,
    start_history_id: str,
    page_token: str | None = None,
) -> dict[str, Any]:
    """Return one page of Gmail history deltas from a checkpoint."""
    started = time.monotonic()
    try:
        service = _build_service(credentials_json)
        kwargs: dict[str, Any] = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "historyTypes": ["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"],
        }
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().history().list(**kwargs).execute()
        _log_gmail_call(
            operation="users.history.list",
            status="success",
            started=started,
            details={"has_next_page": bool(result.get("nextPageToken"))},
        )
        return {
            "history": result.get("history", []) or [],
            "next_page_token": result.get("nextPageToken"),
            "history_id": str(result.get("historyId") or start_history_id),
        }
    except Exception as exc:
        _log_gmail_call(
            operation="users.history.list",
            status="error",
            started=started,
            error_message=str(exc),
        )
        raise


# ── list_messages ────────────────────────────────────────────────────


def list_messages(
    credentials_json: str,
    query: str = "",
    label_ids: list[str] | None = None,
    max_results: int = 20,
) -> list[dict]:
    """List messages matching a query and/or label filter.

    Returns lightweight message stubs (id, threadId, snippet, subject,
    from, date) without the full body.
    """
    log.info("list_messages query=%r label_ids=%s max=%d", query, label_ids, max_results)
    service = _build_service(credentials_json)
    max_results = min(max(max_results, 1), 100)

    kwargs: dict = {"userId": "me", "maxResults": max_results}
    if query:
        kwargs["q"] = query
    if label_ids:
        kwargs["labelIds"] = label_ids

    results = service.users().messages().list(**kwargs).execute()
    message_ids = [m["id"] for m in results.get("messages", [])]
    log.info("list_messages got %d message IDs from API", len(message_ids))

    messages: list[dict] = []
    for msg_id in message_ids:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="metadata",
                 metadataHeaders=["Subject", "From", "To", "Date"])
            .execute()
        )
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        messages.append({
            "id": msg["id"],
            "threadId": msg.get("threadId"),
            "snippet": msg.get("snippet", ""),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "labelIds": msg.get("labelIds", []),
        })

    return messages


# ── attachment helpers ────────────────────────────────────────────────


def _extract_attachment_metadata(payload: dict) -> list[dict]:
    """Walk a message payload and return metadata for every attachment part."""
    attachments: list[dict] = []

    def _walk(parts: list[dict]) -> None:
        for part in parts:
            filename = part.get("filename")
            if filename and part.get("body", {}).get("attachmentId"):
                attachments.append({
                    "attachment_id": part["body"]["attachmentId"],
                    "filename": filename,
                    "mime_type": part.get("mimeType", ""),
                    "size": part.get("body", {}).get("size", 0),
                })
            if part.get("parts"):
                _walk(part["parts"])

    top_parts = payload.get("parts", [])
    if top_parts:
        _walk(top_parts)
    return attachments


def list_attachments(credentials_json: str, message_id: str) -> list[dict]:
    """Return attachment metadata for all files on a message."""
    log.info("list_attachments id=%s", message_id)
    service = _build_service(credentials_json)
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    return _extract_attachment_metadata(msg.get("payload", {}))


def download_attachment(
    credentials_json: str, message_id: str, attachment_id: str,
) -> bytes:
    """Download a single attachment by its attachment ID."""
    log.info("download_attachment msg=%s att=%s", message_id, attachment_id)
    service = _build_service(credentials_json)
    att = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data = att.get("data", "")
    return base64.urlsafe_b64decode(data)


# ── get_message ──────────────────────────────────────────────────────


def get_message(credentials_json: str, message_id: str) -> dict:
    """Fetch a single message with full body text."""
    log.info("get_message id=%s", message_id)
    service = _build_service(credentials_json)

    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }

    body_text = ""
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        body_text = base64.urlsafe_b64decode(
            payload["body"]["data"]
        ).decode("utf-8", errors="replace")
    else:
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body_text = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="replace")
                break

    _, from_addr = parseaddr(headers.get("from", ""))

    attachments = _extract_attachment_metadata(payload)

    return {
        "id": msg["id"],
        "threadId": msg.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "from_address": from_addr,
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "body_text": body_text[:50000],
        "labelIds": msg.get("labelIds", []),
        "attachments": attachments,
    }


# ── send_message ─────────────────────────────────────────────────────


def send_message(
    credentials_json: str,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
) -> dict:
    """Send an email via the Gmail API.  Returns the sent message metadata."""
    log.info("send_message to=%r subject=%r", to, subject)
    started = time.monotonic()
    service = _build_service(credentials_json)

    mime = MIMEMultipart()
    mime["to"] = to
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc
    mime.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

    try:
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        _log_gmail_call(
            operation="users.messages.send",
            status="success",
            started=started,
        )
        return {
            "id": sent.get("id"),
            "threadId": sent.get("threadId"),
            "labelIds": sent.get("labelIds", []),
        }
    except Exception as exc:
        _log_gmail_call(
            operation="users.messages.send",
            status="error",
            started=started,
            error_message=str(exc),
        )
        raise


# ── create_draft ─────────────────────────────────────────────────────


def create_draft(
    credentials_json: str,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
) -> dict:
    """Create a draft email in the user's Gmail account.  Returns the
    draft ID and underlying message metadata."""
    log.info("create_draft to=%r subject=%r", to, subject)
    service = _build_service(credentials_json)

    mime = MIMEMultipart()
    mime["to"] = to
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc
    mime.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return {
        "id": draft.get("id"),
        "message_id": draft.get("message", {}).get("id"),
        "thread_id": draft.get("message", {}).get("threadId"),
        "label_ids": draft.get("message", {}).get("labelIds", []),
    }


# ── send_draft_by_message_id ─────────────────────────────────────────


def send_draft_by_message_id(
    credentials_json: str,
    message_id: str,
) -> dict:
    """Send an existing Gmail draft by locating it via draft message ID."""
    log.info("send_draft_by_message_id message_id=%s", message_id)
    service = _build_service(credentials_json)

    draft_id: str | None = None
    page_token: str | None = None
    scanned_pages = 0

    while True:
        scanned_pages += 1
        request_kwargs: dict[str, Any] = {"userId": "me", "maxResults": 100}
        if page_token:
            request_kwargs["pageToken"] = page_token
        page = service.users().drafts().list(**request_kwargs).execute()

        for draft in page.get("drafts", []) or []:
            draft_message_id = (draft.get("message") or {}).get("id")
            if draft_message_id == message_id:
                draft_id = draft.get("id")
                break

        if draft_id:
            break

        page_token = page.get("nextPageToken")
        if not page_token:
            break

    if not draft_id:
        raise ValueError(
            f"Draft not found for message_id={message_id} (scanned_pages={scanned_pages})"
        )

    sent = (
        service.users()
        .drafts()
        .send(userId="me", body={"id": draft_id})
        .execute()
    )
    return {
        "id": sent.get("id"),
        "threadId": sent.get("threadId"),
        "labelIds": sent.get("labelIds", []),
    }


# ── reply_message ────────────────────────────────────────────────────


def reply_message(
    credentials_json: str,
    message_id: str,
    body: str,
    cc: str = "",
) -> dict:
    """Reply to an existing Gmail message, preserving the thread.

    Fetches the original message to extract headers (From, Subject,
    Message-ID) and constructs a properly threaded reply.
    """
    log.info("reply_message original_id=%s", message_id)
    service = _build_service(credentials_json)

    original = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="metadata",
             metadataHeaders=["Subject", "From", "To", "Message-ID", "References"])
        .execute()
    )
    headers = {
        h["name"].lower(): h["value"]
        for h in original.get("payload", {}).get("headers", [])
    }

    reply_to = headers.get("from", "")
    subject = headers.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    orig_msg_id = headers.get("message-id", "")
    references = headers.get("references", "")
    if orig_msg_id:
        references = f"{references} {orig_msg_id}".strip()
    thread_id = original.get("threadId")

    mime = MIMEMultipart()
    mime["to"] = reply_to
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc
    if orig_msg_id:
        mime["In-Reply-To"] = orig_msg_id
        mime["References"] = references
    mime.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id})
        .execute()
    )
    return {
        "id": sent.get("id"),
        "threadId": sent.get("threadId"),
        "labelIds": sent.get("labelIds", []),
    }


# ── forward_message ──────────────────────────────────────────────────


def forward_message(
    credentials_json: str,
    message_id: str,
    to: str,
    body: str = "",
    cc: str = "",
) -> dict:
    """Forward a Gmail message to a new recipient.

    Fetches the original message body, prepends the user's optional
    comment, and sends to the specified recipient(s).
    """
    log.info("forward_message original_id=%s to=%r", message_id, to)
    service = _build_service(credentials_json)

    original = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {
        h["name"].lower(): h["value"]
        for h in original.get("payload", {}).get("headers", [])
    }

    subject = headers.get("subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"

    orig_body = ""
    payload = original.get("payload", {})
    if payload.get("body", {}).get("data"):
        orig_body = base64.urlsafe_b64decode(
            payload["body"]["data"]
        ).decode("utf-8", errors="replace")
    else:
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                orig_body = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="replace")
                break

    fwd_header = (
        f"\n\n---------- Forwarded message ----------\n"
        f"From: {headers.get('from', '')}\n"
        f"Date: {headers.get('date', '')}\n"
        f"Subject: {headers.get('subject', '')}\n"
        f"To: {headers.get('to', '')}\n\n"
    )
    full_body = body + fwd_header + orig_body

    mime = MIMEMultipart()
    mime["to"] = to
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc
    mime.attach(MIMEText(full_body, "plain"))

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )
    return {
        "id": sent.get("id"),
        "threadId": sent.get("threadId"),
        "labelIds": sent.get("labelIds", []),
    }


# ── modify_labels ────────────────────────────────────────────────────


def modify_labels(
    credentials_json: str,
    message_id: str,
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
) -> dict:
    """Add or remove labels from a message."""
    log.info("modify_labels id=%s add=%s remove=%s", message_id, add_label_ids, remove_label_ids)
    service = _build_service(credentials_json)

    body: dict = {}
    if add_label_ids:
        body["addLabelIds"] = add_label_ids
    if remove_label_ids:
        body["removeLabelIds"] = remove_label_ids

    if not body:
        return {"error": "No label changes specified."}

    result = (
        service.users()
        .messages()
        .modify(userId="me", id=message_id, body=body)
        .execute()
    )
    return {
        "id": result.get("id"),
        "threadId": result.get("threadId"),
        "labelIds": result.get("labelIds", []),
    }


def trash_message(credentials_json: str, message_id: str) -> dict:
    """Move a message to trash."""
    log.info("trash_message id=%s", message_id)
    service = _build_service(credentials_json)
    result = (
        service.users()
        .messages()
        .trash(userId="me", id=message_id)
        .execute()
    )
    return {
        "id": result.get("id"),
        "threadId": result.get("threadId"),
        "labelIds": result.get("labelIds", []),
    }
