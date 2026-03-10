"""Celery tasks for Gmail inbox storage sync."""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr
from typing import Any

from googleapiclient.errors import HttpError

from celery_app import celery
from services.gmail_service import (
    get_message_raw,
    get_profile,
    list_history_page,
    list_message_ids_page,
)
from services.supabase_service import get_supabase

log = logging.getLogger(__name__)

METADATA_HEADERS = [
    "Subject",
    "From",
    "To",
    "Cc",
    "Bcc",
    "Date",
    "Message-ID",
    "In-Reply-To",
    "References",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_internal_datetime(internal_ts: int | None) -> str | None:
    if not internal_ts:
        return None
    try:
        return datetime.fromtimestamp(internal_ts / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _extract_headers(msg: dict[str, Any]) -> dict[str, str]:
    return {
        (h.get("name", "").lower()): h.get("value", "")
        for h in ((msg.get("payload") or {}).get("headers") or [])
    }


def _parse_recipients(value: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for name, addr in getaddresses([value or ""]):
        if not addr:
            continue
        parsed.append({"name": name or "", "email": addr})
    return parsed


def _sanitize_html(html: str) -> str:
    if not html:
        return ""
    sanitized = html
    sanitized = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", sanitized, flags=re.I)
    sanitized = re.sub(r"<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>", "", sanitized, flags=re.I)
    sanitized = re.sub(r"<object\b[^<]*(?:(?!<\/object>)<[^<]*)*<\/object>", "", sanitized, flags=re.I)
    sanitized = re.sub(r"<embed\b[^<]*(?:(?!<\/embed>)<[^<]*)*<\/embed>", "", sanitized, flags=re.I)
    sanitized = re.sub(r"\s+on[a-z]+\s*=\s*\"[^\"]*\"", "", sanitized, flags=re.I)
    sanitized = re.sub(r"\s+on[a-z]+\s*=\s*'[^']*'", "", sanitized, flags=re.I)
    sanitized = re.sub(r"\s+on[a-z]+\s*=\s*[^\s>]+", "", sanitized, flags=re.I)
    sanitized = re.sub(
        r"(href|src)\s*=\s*\"javascript:[^\"]*\"",
        r'\1="#"',
        sanitized,
        flags=re.I,
    )
    sanitized = re.sub(
        r"(href|src)\s*=\s*'javascript:[^']*'",
        r"\1='#'",
        sanitized,
        flags=re.I,
    )
    return sanitized[:100000]


def _extract_body(payload: dict[str, Any]) -> tuple[str, str]:
    html_candidates: list[tuple[int, int, str]] = []
    text_candidates: list[tuple[int, int, str]] = []

    def _decode_part_data(raw_data: str | None) -> str:
        if not raw_data:
            return ""
        try:
            return base64.urlsafe_b64decode(raw_data).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _walk(part: dict[str, Any], *, depth: int, in_alternative: bool) -> None:
        mime_type = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        decoded = _decode_part_data(body.get("data"))
        rank = 0 if in_alternative else 1
        if decoded and mime_type == "text/html":
            html_candidates.append((rank, depth, decoded))
        if decoded and mime_type == "text/plain":
            text_candidates.append((rank, depth, decoded))

        next_is_alternative = mime_type.startswith("multipart/alternative")
        for child in part.get("parts") or []:
            _walk(
                child,
                depth=depth + 1,
                in_alternative=next_is_alternative or in_alternative,
            )

    _walk(payload or {}, depth=0, in_alternative=False)
    html_candidates.sort(key=lambda item: (item[0], item[1]))
    text_candidates.sort(key=lambda item: (item[0], item[1]))
    body_html = html_candidates[0][2] if html_candidates else ""
    body_text = text_candidates[0][2] if text_candidates else ""
    return body_text[:100000], _sanitize_html(body_html)


def _extract_attachment_metadata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []

    def _walk(parts: list[dict[str, Any]]) -> None:
        for part in parts:
            filename = part.get("filename")
            if filename and (part.get("body") or {}).get("attachmentId"):
                body = part.get("body") or {}
                attachments.append(
                    {
                        "gmail_attachment_id": body.get("attachmentId", ""),
                        "filename": filename,
                        "mime_type": part.get("mimeType", "") or "",
                        "size_bytes": int(body.get("size", 0) or 0),
                    }
                )
            if part.get("parts"):
                _walk(part["parts"])

    _walk((payload or {}).get("parts") or [])
    return attachments


def _normalize_subject(subject: str) -> str:
    normalized = (subject or "").strip().lower()
    normalized = re.sub(r"^(re:|fwd:|fw:)\s*", "", normalized)
    return normalized[:500]


def _is_truthy_label(labels: list[str], label: str) -> bool:
    return label in (labels or [])


def _upsert_sync_state(
    sb,
    user_id: str,
    integration_id: str,
    *,
    last_history_id: str | None = None,
    sync_cursor_status: str | None = None,
    last_full_sync_at: str | None = None,
    last_delta_sync_at: str | None = None,
    last_error: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "integration_id": integration_id,
        "updated_at": _now_iso(),
    }
    if last_history_id is not None:
        payload["last_history_id"] = last_history_id
    if sync_cursor_status is not None:
        payload["sync_cursor_status"] = sync_cursor_status
    if last_full_sync_at is not None:
        payload["last_full_sync_at"] = last_full_sync_at
    if last_delta_sync_at is not None:
        payload["last_delta_sync_at"] = last_delta_sync_at
    if last_error is not None:
        payload["last_error"] = last_error

    sb.table("gmail_sync_state").upsert(
        payload,
        on_conflict="integration_id",
    ).execute()


def _sync_attachments(
    sb,
    user_id: str,
    integration_id: str,
    email_id: str,
    gmail_message_id: str,
    payload: dict[str, Any],
) -> None:
    attachments = _extract_attachment_metadata(payload)
    sb.table("email_attachments").delete().eq("email_id", email_id).execute()
    if not attachments:
        return

    rows = [
        {
            "user_id": user_id,
            "integration_id": integration_id,
            "email_id": email_id,
            "gmail_message_id": gmail_message_id,
            "gmail_attachment_id": item["gmail_attachment_id"],
            "filename": item["filename"],
            "mime_type": item["mime_type"],
            "size_bytes": item["size_bytes"],
            "updated_at": _now_iso(),
        }
        for item in attachments
    ]
    sb.table("email_attachments").upsert(
        rows,
        on_conflict="integration_id,gmail_message_id,gmail_attachment_id",
    ).execute()


def _upsert_message(
    sb,
    user_id: str,
    integration_id: str,
    msg: dict[str, Any],
    *,
    hydrate_body: bool,
) -> None:
    gmail_message_id = msg.get("id")
    gmail_thread_id = msg.get("threadId")
    if not gmail_message_id or not gmail_thread_id:
        return

    payload = msg.get("payload") or {}
    headers = _extract_headers(msg)
    labels = msg.get("labelIds") or []
    internal_ts = int(msg.get("internalDate") or 0) if str(msg.get("internalDate") or "").isdigit() else None
    internal_at = _to_internal_datetime(internal_ts)
    from_name, from_email = parseaddr(headers.get("from", ""))
    to_list = _parse_recipients(headers.get("to", ""))
    cc_list = _parse_recipients(headers.get("cc", ""))
    bcc_list = _parse_recipients(headers.get("bcc", ""))
    participants = []
    if from_email:
        participants.append({"name": from_name or "", "email": from_email})
    participants.extend(to_list)
    participants.extend(cc_list)

    body_text = ""
    body_html = ""
    if hydrate_body:
        body_text, body_html = _extract_body(payload)

    row = {
        "user_id": user_id,
        "integration_id": integration_id,
        "gmail_message_id": gmail_message_id,
        "gmail_thread_id": gmail_thread_id,
        "internal_date_ts": internal_ts,
        "from_json": {"name": from_name or "", "email": from_email or ""},
        "to_json": to_list,
        "cc_json": cc_list,
        "bcc_json": bcc_list,
        "subject": (headers.get("subject", "") or "")[:1000],
        "snippet": (msg.get("snippet", "") or "")[:2000],
        "body_text": body_text,
        "body_html_sanitized": body_html,
        "payload_json": payload if hydrate_body else {},
        "label_ids_json": labels,
        "is_read": not _is_truthy_label(labels, "UNREAD"),
        "is_starred": _is_truthy_label(labels, "STARRED"),
        "is_draft": _is_truthy_label(labels, "DRAFT"),
        "is_sent": _is_truthy_label(labels, "SENT"),
        "has_attachments": bool(_extract_attachment_metadata(payload)) if hydrate_body else False,
        "message_id_header": (headers.get("message-id", "") or "")[:1000],
        "in_reply_to_header": (headers.get("in-reply-to", "") or "")[:1000],
        "references_header": (headers.get("references", "") or "")[:4000],
        "updated_at": _now_iso(),
        "deleted_at": None,
    }
    sb.table("emails").upsert(row, on_conflict="integration_id,gmail_message_id").execute()

    thread_row = {
        "user_id": user_id,
        "integration_id": integration_id,
        "gmail_thread_id": gmail_thread_id,
        "subject_normalized": _normalize_subject(headers.get("subject", "")),
        "participants_json": participants,
        "last_message_internal_at": internal_at,
        "has_unread": _is_truthy_label(labels, "UNREAD"),
        "snippet": (msg.get("snippet", "") or "")[:2000],
        "updated_at": _now_iso(),
    }
    sb.table("email_threads").upsert(
        thread_row,
        on_conflict="integration_id,gmail_thread_id",
    ).execute()

    if hydrate_body:
        email_row = (
            sb.table("emails")
            .select("id")
            .eq("integration_id", integration_id)
            .eq("gmail_message_id", gmail_message_id)
            .limit(1)
            .execute()
        ).data or []
        if email_row:
            _sync_attachments(
                sb,
                user_id,
                integration_id,
                email_row[0]["id"],
                gmail_message_id,
                payload,
            )


def _get_integration(sb, integration_id: str) -> dict[str, Any] | None:
    result = (
        sb.table("integrations")
        .select("id, user_id, account_token, gmail_history_id, status, provider")
        .eq("id", integration_id)
        .eq("provider", "gmail")
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


@celery.task(name="tasks.email_sync_tasks.kickoff_initial_gmail_sync")
def kickoff_initial_gmail_sync(integration_id: str) -> dict[str, Any]:
    """Initial metadata-first Gmail backfill for first connect."""
    sb = get_supabase()
    integration = _get_integration(sb, integration_id)
    if not integration:
        return {"status": "skipped", "reason": "integration_not_found", "integration_id": integration_id}

    user_id = integration["user_id"]
    token = integration["account_token"]
    inserted = 0
    errors = 0
    hydrated_candidates: list[str] = []

    _upsert_sync_state(
        sb,
        user_id,
        integration_id,
        sync_cursor_status="syncing_initial",
        last_error=None,
    )

    page_token: str | None = None
    try:
        while True:
            page = list_message_ids_page(
                token,
                query="in:anywhere",
                max_results=250,
                page_token=page_token,
            )
            message_ids = page.get("message_ids", [])
            for msg_id in message_ids:
                try:
                    msg = get_message_raw(
                        token,
                        msg_id,
                        format="metadata",
                        metadata_headers=METADATA_HEADERS,
                    )
                    _upsert_message(sb, user_id, integration_id, msg, hydrate_body=False)
                    inserted += 1
                    labels = msg.get("labelIds") or []
                    internal_ts = int(msg.get("internalDate") or 0) if str(msg.get("internalDate") or "").isdigit() else 0
                    is_recent = False
                    if internal_ts:
                        days_old = (datetime.now(timezone.utc).timestamp() * 1000 - internal_ts) / (1000 * 60 * 60 * 24)
                        is_recent = days_old <= 60
                    if "UNREAD" in labels or "STARRED" in labels or "INBOX" in labels or is_recent:
                        hydrated_candidates.append(msg_id)
                except Exception:
                    errors += 1
                    log.exception("gmail_initial_sync_message_failed integration_id=%s msg_id=%s", integration_id, msg_id)

            page_token = page.get("next_page_token")
            if not page_token:
                break

        profile = get_profile(token)
        latest_history_id = profile.get("historyId") or integration.get("gmail_history_id")
        if latest_history_id:
            sb.table("integrations").update(
                {"gmail_history_id": latest_history_id, "updated_at": _now_iso()}
            ).eq("id", integration_id).execute()

        _upsert_sync_state(
            sb,
            user_id,
            integration_id,
            last_history_id=latest_history_id,
            sync_cursor_status="idle",
            last_full_sync_at=_now_iso(),
            last_error=None,
        )

        if hydrated_candidates:
            hydrate_message_bodies.delay(integration_id, hydrated_candidates[:500])

        return {
            "status": "ok",
            "integration_id": integration_id,
            "inserted": inserted,
            "errors": errors,
            "hydration_enqueued": min(len(hydrated_candidates), 500),
        }
    except Exception as exc:
        _upsert_sync_state(
            sb,
            user_id,
            integration_id,
            sync_cursor_status="error",
            last_error=str(exc)[:1000],
        )
        log.exception("gmail_initial_sync_failed integration_id=%s", integration_id)
        raise


@celery.task(name="tasks.email_sync_tasks.hydrate_message_bodies")
def hydrate_message_bodies(integration_id: str, message_ids: list[str]) -> dict[str, Any]:
    """Hydrate message bodies for already-upserted message shells."""
    sb = get_supabase()
    integration = _get_integration(sb, integration_id)
    if not integration:
        return {"status": "skipped", "reason": "integration_not_found", "integration_id": integration_id}

    user_id = integration["user_id"]
    token = integration["account_token"]
    hydrated = 0
    failed = 0
    for msg_id in message_ids:
        try:
            msg = get_message_raw(token, msg_id, format="full")
            _upsert_message(sb, user_id, integration_id, msg, hydrate_body=True)
            hydrated += 1
        except Exception:
            failed += 1
            log.exception("gmail_hydrate_failed integration_id=%s msg_id=%s", integration_id, msg_id)
    return {"status": "ok", "integration_id": integration_id, "hydrated": hydrated, "failed": failed}


@celery.task(name="tasks.email_sync_tasks.sync_gmail_history_delta")
def sync_gmail_history_delta(integration_id: str) -> dict[str, Any]:
    """Apply incremental Gmail changes from the last history checkpoint."""
    sb = get_supabase()
    integration = _get_integration(sb, integration_id)
    if not integration:
        return {"status": "skipped", "reason": "integration_not_found", "integration_id": integration_id}

    user_id = integration["user_id"]
    token = integration["account_token"]

    sync_state_row = (
        sb.table("gmail_sync_state")
        .select("last_history_id")
        .eq("integration_id", integration_id)
        .limit(1)
        .execute()
    ).data or []
    start_history_id = (sync_state_row[0].get("last_history_id") if sync_state_row else None) or integration.get("gmail_history_id")
    if not start_history_id:
        profile = get_profile(token)
        start_history_id = profile.get("historyId")
        _upsert_sync_state(
            sb,
            user_id,
            integration_id,
            last_history_id=start_history_id,
            sync_cursor_status="idle",
            last_error=None,
        )
        return {"status": "seeded", "integration_id": integration_id, "history_id": start_history_id}

    _upsert_sync_state(sb, user_id, integration_id, sync_cursor_status="syncing_delta", last_error=None)

    added_or_changed: set[str] = set()
    deleted_ids: set[str] = set()
    hydrated_candidates: set[str] = set()
    skipped_missing = 0
    upserted_count = 0
    latest_history_id = start_history_id
    page_token: str | None = None
    try:
        while True:
            page = list_history_page(token, start_history_id, page_token=page_token)
            latest_history_id = page.get("history_id") or latest_history_id
            for row in page.get("history", []):
                for item in row.get("messagesAdded", []) or []:
                    msg_id = ((item.get("message") or {}).get("id"))
                    if msg_id:
                        added_or_changed.add(msg_id)
                for item in row.get("labelsAdded", []) or []:
                    msg_id = ((item.get("message") or {}).get("id"))
                    if msg_id:
                        added_or_changed.add(msg_id)
                for item in row.get("labelsRemoved", []) or []:
                    msg_id = ((item.get("message") or {}).get("id"))
                    if msg_id:
                        added_or_changed.add(msg_id)
                for item in row.get("messagesDeleted", []) or []:
                    msg_id = ((item.get("message") or {}).get("id"))
                    if msg_id:
                        deleted_ids.add(msg_id)
            page_token = page.get("next_page_token")
            if not page_token:
                break

        for msg_id in added_or_changed:
            try:
                msg = get_message_raw(
                    token,
                    msg_id,
                    format="metadata",
                    metadata_headers=METADATA_HEADERS,
                )
            except HttpError as exc:
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status == 404:
                    skipped_missing += 1
                    log.info("gmail_delta_missing_message_skipped integration_id=%s msg_id=%s", integration_id, msg_id)
                    continue
                raise
            _upsert_message(sb, user_id, integration_id, msg, hydrate_body=False)
            upserted_count += 1
            labels = msg.get("labelIds") or []
            internal_ts = int(msg.get("internalDate") or 0) if str(msg.get("internalDate") or "").isdigit() else 0
            is_recent = False
            if internal_ts:
                days_old = (datetime.now(timezone.utc).timestamp() * 1000 - internal_ts) / (1000 * 60 * 60 * 24)
                is_recent = days_old <= 14
            if "UNREAD" in labels or "STARRED" in labels or "INBOX" in labels or is_recent:
                hydrated_candidates.add(msg_id)

        if deleted_ids:
            sb.table("emails").update(
                {"deleted_at": _now_iso(), "updated_at": _now_iso()}
            ).eq("integration_id", integration_id).in_("gmail_message_id", list(deleted_ids)).execute()

        sb.table("integrations").update(
            {"gmail_history_id": latest_history_id, "updated_at": _now_iso()}
        ).eq("id", integration_id).execute()
        _upsert_sync_state(
            sb,
            user_id,
            integration_id,
            last_history_id=latest_history_id,
            sync_cursor_status="idle",
            last_delta_sync_at=_now_iso(),
            last_error=None,
        )
        if hydrated_candidates:
            hydrate_message_bodies.delay(integration_id, list(hydrated_candidates)[:500])
        return {
            "status": "ok",
            "integration_id": integration_id,
            "upserted": upserted_count,
            "skipped_missing": skipped_missing,
            "deleted": len(deleted_ids),
            "history_id": latest_history_id,
            "hydration_enqueued": min(len(hydrated_candidates), 500),
        }
    except Exception as exc:
        _upsert_sync_state(
            sb,
            user_id,
            integration_id,
            sync_cursor_status="error",
            last_error=str(exc)[:1000],
        )
        log.exception("gmail_delta_sync_failed integration_id=%s", integration_id)
        raise


@celery.task(name="tasks.email_sync_tasks.sync_all_gmail_history_deltas")
def sync_all_gmail_history_deltas() -> dict[str, Any]:
    """Periodic fan-out task that schedules per-integration delta sync."""
    sb = get_supabase()
    integrations = (
        sb.table("integrations")
        .select("id")
        .eq("provider", "gmail")
        .eq("status", "active")
        .execute()
    ).data or []
    for row in integrations:
        sync_gmail_history_delta.delay(row["id"])
    return {"status": "ok", "scheduled": len(integrations)}
