"""
Google Gmail API client.

Handles OAuth URL generation, code exchange, and full Gmail operations:
read, send, and label modification.
"""
from __future__ import annotations

import json
import logging
import base64
from typing import Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parseaddr

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config import Config

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


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
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=user_id,
    )
    return url


def exchange_code(code: str) -> str:
    """Exchange an authorization *code* for OAuth credentials.
    Returns a JSON string suitable for storage in the DB."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = Config.GOOGLE_REDIRECT_URI
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
    return {
        "historyId": str(response.get("historyId", "")),
        "expiration": str(response.get("expiration", "")),
    }


def list_new_inbox_messages_since(
    credentials_json: str,
    start_history_id: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return new inbox message summaries since a history cursor."""
    service = _build_service(credentials_json)

    if not start_history_id:
        profile = get_profile(credentials_json)
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
        return [], profile.get("historyId")

    seen_ids: set[str] = set()
    events: list[dict[str, Any]] = []
    for row in history_resp.get("history", []):
        for added in row.get("messagesAdded", []) or []:
            msg = added.get("message") or {}
            msg_id = msg.get("id")
            if not msg_id or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
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
    service = _build_service(credentials_json)
    kwargs: dict[str, Any] = {
        "userId": "me",
        "startHistoryId": start_history_id,
        "historyTypes": ["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"],
    }
    if page_token:
        kwargs["pageToken"] = page_token

    result = service.users().history().list(**kwargs).execute()
    return {
        "history": result.get("history", []) or [],
        "next_page_token": result.get("nextPageToken"),
        "history_id": str(result.get("historyId") or start_history_id),
    }


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
    service = _build_service(credentials_json)

    mime = MIMEMultipart()
    mime["to"] = to
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc
    mime.attach(MIMEText(body, "plain"))

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
