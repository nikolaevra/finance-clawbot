"""
Google Gmail API client.

Handles OAuth URL generation, code exchange, and full Gmail operations:
read, send, and label modification.
"""
from __future__ import annotations

import json
import logging
import base64
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
