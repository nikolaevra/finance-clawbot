"""Inbox API routes backed by local Gmail sync tables."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request, send_file

from middleware.auth import require_auth
from services.document_service import ingest_document_upload
from services.gmail_service import (
    download_attachment,
    forward_message,
    modify_labels,
    reply_message,
    send_draft_by_message_id,
    send_message,
    trash_message,
)
from services.supabase_service import get_supabase
from tasks.email_sync_tasks import hydrate_message_bodies, sync_gmail_history_delta

inbox_bp = Blueprint("inbox", __name__)
log = logging.getLogger(__name__)


def _get_gmail_integration(user_id: str) -> dict | None:
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, user_id, account_token")
        .eq("user_id", user_id)
        .eq("provider", "gmail")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def _get_attachment_row(
    *,
    user_id: str,
    integration_id: str,
    message_id: str,
    attachment_id: str,
) -> dict | None:
    sb = get_supabase()
    rows = (
        sb.table("email_attachments")
        .select("filename, mime_type, gmail_message_id, gmail_attachment_id")
        .eq("user_id", user_id)
        .eq("integration_id", integration_id)
        .eq("gmail_message_id", message_id)
        .eq("gmail_attachment_id", attachment_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    return rows[0]


def _thread_ids_by_inbox_scope(
    sb,
    *,
    user_id: str,
    integration_id: str,
    scope: str,
    max_scan: int = 5000,
) -> list[str]:
    rows = (
        sb.table("emails")
        .select("gmail_thread_id, label_ids_json, internal_date_ts")
        .eq("user_id", user_id)
        .eq("integration_id", integration_id)
        .is_("deleted_at", "null")
        .order("internal_date_ts", desc=True)
        .range(0, max_scan - 1)
        .execute()
    ).data or []

    ordered_thread_ids: list[str] = []
    seen_thread_ids: set[str] = set()
    inbox_thread_ids: set[str] = set()
    for row in rows:
        thread_id = row.get("gmail_thread_id")
        if not thread_id:
            continue
        labels = row.get("label_ids_json") or []
        if "INBOX" in labels:
            inbox_thread_ids.add(thread_id)
        if thread_id not in seen_thread_ids:
            seen_thread_ids.add(thread_id)
            ordered_thread_ids.append(thread_id)

    if scope == "inbox":
        return [thread_id for thread_id in ordered_thread_ids if thread_id in inbox_thread_ids]
    if scope == "skip_inbox":
        return [thread_id for thread_id in ordered_thread_ids if thread_id not in inbox_thread_ids]
    return ordered_thread_ids


@inbox_bp.route("/inbox/threads", methods=["GET"])
@require_auth
def list_threads():
    tab = (request.args.get("tab", "inbox") or "inbox").lower()
    if tab == "all":
        tab = "all_mail"
    page = max(int(request.args.get("page", 1) or 1), 1)
    limit = min(max(int(request.args.get("limit", 25) or 25), 1), 100)
    offset = (page - 1) * limit

    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"threads": [], "page": page, "limit": limit, "has_more": False})

    sb = get_supabase()
    query = (
        sb.table("email_threads")
        .select(
            "gmail_thread_id, subject_normalized, participants_json, "
            "last_message_internal_at, has_unread, snippet"
        )
        .eq("user_id", g.user_id)
        .eq("integration_id", integration["id"])
        .order("last_message_internal_at", desc=True)
    )

    if tab in ("inbox", "skip_inbox"):
        scoped_thread_ids = _thread_ids_by_inbox_scope(
            sb,
            user_id=g.user_id,
            integration_id=integration["id"],
            scope=tab,
        )
        if not scoped_thread_ids:
            return jsonify({"threads": [], "page": page, "limit": limit, "has_more": False})
        page_thread_ids = scoped_thread_ids[offset : offset + limit + 1]
        has_more = len(page_thread_ids) > limit
        selected_ids = page_thread_ids[:limit]
        rows = (
            sb.table("email_threads")
            .select(
                "gmail_thread_id, subject_normalized, participants_json, "
                "last_message_internal_at, has_unread, snippet"
            )
            .eq("user_id", g.user_id)
            .eq("integration_id", integration["id"])
            .in_("gmail_thread_id", selected_ids)
            .execute()
        ).data or []
        row_by_id = {row["gmail_thread_id"]: row for row in rows}
        ordered_rows = [row_by_id[thread_id] for thread_id in selected_ids if thread_id in row_by_id]
        return jsonify(
            {
                "threads": ordered_rows,
                "page": page,
                "limit": limit,
                "has_more": has_more,
            }
        )

    if tab == "unread":
        query = query.eq("has_unread", True)

    if tab in ("sent", "drafts"):
        flag_col = "is_sent" if tab == "sent" else "is_draft"
        rows = (
            sb.table("emails")
            .select("gmail_thread_id")
            .eq("user_id", g.user_id)
            .eq("integration_id", integration["id"])
            .eq(flag_col, True)
            .is_("deleted_at", "null")
            .order("internal_date_ts", desc=True)
            .limit(500)
            .execute()
        ).data or []
        thread_ids = list({r.get("gmail_thread_id") for r in rows if r.get("gmail_thread_id")})
        if not thread_ids:
            return jsonify({"threads": [], "page": page, "limit": limit, "has_more": False})
        query = query.in_("gmail_thread_id", thread_ids)

    rows = query.range(offset, offset + limit).execute().data or []
    has_more = len(rows) > limit
    return jsonify(
        {
            "threads": rows[:limit],
            "page": page,
            "limit": limit,
            "has_more": has_more,
        }
    )


@inbox_bp.route("/inbox/threads/<thread_id>", methods=["GET"])
@require_auth
def get_thread(thread_id: str):
    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sb = get_supabase()
    thread_rows = (
        sb.table("email_threads")
        .select(
            "gmail_thread_id, subject_normalized, participants_json, "
            "last_message_internal_at, has_unread, snippet"
        )
        .eq("user_id", g.user_id)
        .eq("integration_id", integration["id"])
        .eq("gmail_thread_id", thread_id)
        .limit(1)
        .execute()
    ).data or []
    if not thread_rows:
        return jsonify({"error": "Thread not found"}), 404

    # Pull latest label/message changes so newly created drafts are visible.
    try:
        sync_gmail_history_delta(integration["id"])
    except Exception:
        log.exception("thread_delta_sync_failed integration_id=%s thread_id=%s", integration["id"], thread_id)
        sync_gmail_history_delta.delay(integration["id"])

    messages = (
        sb.table("emails")
        .select("*")
        .eq("user_id", g.user_id)
        .eq("integration_id", integration["id"])
        .eq("gmail_thread_id", thread_id)
        .is_("deleted_at", "null")
        .order("internal_date_ts", desc=False)
        .execute()
    ).data or []

    missing_bodies = [
        row["gmail_message_id"]
        for row in messages
        if not row.get("body_text") and not row.get("body_html_sanitized")
    ]
    hydrate_enqueued = False
    if missing_bodies:
        try:
            hydrate_message_bodies(integration["id"], missing_bodies[:25])
            messages = (
                sb.table("emails")
                .select("*")
                .eq("user_id", g.user_id)
                .eq("integration_id", integration["id"])
                .eq("gmail_thread_id", thread_id)
                .is_("deleted_at", "null")
                .order("internal_date_ts", desc=False)
                .execute()
            ).data or []
        except Exception:
            log.exception("thread_sync_hydration_failed integration_id=%s thread_id=%s", integration["id"], thread_id)
            hydrate_message_bodies.delay(integration["id"], missing_bodies[:25])
            hydrate_enqueued = True

    message_ids = [row["gmail_message_id"] for row in messages if row.get("gmail_message_id")]
    attachments_by_message: dict[str, list[dict]] = {}
    if message_ids:
        attachment_rows = (
            sb.table("email_attachments")
            .select("gmail_message_id, gmail_attachment_id, filename, mime_type, size_bytes, storage_key")
            .eq("user_id", g.user_id)
            .eq("integration_id", integration["id"])
            .in_("gmail_message_id", message_ids)
            .execute()
        ).data or []
        for row in attachment_rows:
            msg_id = row.get("gmail_message_id")
            if not msg_id:
                continue
            attachments_by_message.setdefault(msg_id, []).append(row)

    return jsonify(
        {
            "thread": thread_rows[0],
            "messages": messages,
            "attachments_by_message": attachments_by_message,
            "hydrate_enqueued": hydrate_enqueued,
        }
    )


@inbox_bp.route("/inbox/messages/<message_id>/attachments/<attachment_id>/download", methods=["GET"])
@require_auth
def download_inbox_attachment(message_id: str, attachment_id: str):
    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    attachment = _get_attachment_row(
        user_id=g.user_id,
        integration_id=integration["id"],
        message_id=message_id,
        attachment_id=attachment_id,
    )
    if not attachment:
        return jsonify({"error": "Attachment not found"}), 404

    try:
        file_bytes = download_attachment(
            integration["account_token"],
            message_id=message_id,
            attachment_id=attachment_id,
        )
    except Exception:
        log.exception(
            "inbox_attachment_download_failed user=%s integration_id=%s message_id=%s attachment_id=%s",
            g.user_id,
            integration["id"],
            message_id,
            attachment_id,
        )
        return jsonify({"error": "Failed to download attachment"}), 502

    filename = attachment.get("filename") or f"attachment-{attachment_id}"
    mime_type = attachment.get("mime_type") or "application/octet-stream"
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        as_attachment=True,
        download_name=filename,
    )


@inbox_bp.route("/inbox/messages/<message_id>/attachments/<attachment_id>/save-to-documents", methods=["POST"])
@require_auth
def save_attachment_to_documents(message_id: str, attachment_id: str):
    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    attachment = _get_attachment_row(
        user_id=g.user_id,
        integration_id=integration["id"],
        message_id=message_id,
        attachment_id=attachment_id,
    )
    if not attachment:
        return jsonify({"error": "Attachment not found"}), 404

    try:
        file_bytes = download_attachment(
            integration["account_token"],
            message_id=message_id,
            attachment_id=attachment_id,
        )
    except Exception:
        log.exception(
            "inbox_attachment_download_failed_for_save user=%s integration_id=%s message_id=%s attachment_id=%s",
            g.user_id,
            integration["id"],
            message_id,
            attachment_id,
        )
        return jsonify({"error": "Failed to download attachment"}), 502

    filename = attachment.get("filename") or f"attachment-{attachment_id}"
    mime_type = attachment.get("mime_type") or "application/octet-stream"

    try:
        doc = ingest_document_upload(
            user_id=g.user_id,
            filename=filename,
            file_bytes=file_bytes,
            content_type=mime_type,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        log.exception(
            "inbox_attachment_save_failed user=%s integration_id=%s message_id=%s attachment_id=%s",
            g.user_id,
            integration["id"],
            message_id,
            attachment_id,
        )
        return jsonify({"error": "Failed to save attachment to documents"}), 500

    return jsonify(doc), 201


@inbox_bp.route("/inbox/send", methods=["POST"])
@require_auth
def inbox_send():
    body = request.get_json(silent=True) or {}
    to = (body.get("to") or "").strip()
    subject = body.get("subject") or ""
    message = body.get("body") or ""
    cc = body.get("cc") or ""
    if not to:
        return jsonify({"error": "to is required"}), 400

    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sent = send_message(integration["account_token"], to=to, subject=subject, body=message, cc=cc)
    if sent.get("id"):
        hydrate_message_bodies.delay(integration["id"], [sent["id"]])
        sync_gmail_history_delta.delay(integration["id"])
    return jsonify(sent), 201


@inbox_bp.route("/inbox/reply", methods=["POST"])
@require_auth
def inbox_reply():
    body = request.get_json(silent=True) or {}
    message_id = (body.get("message_id") or "").strip()
    message = body.get("body") or ""
    cc = body.get("cc") or ""
    if not message_id:
        return jsonify({"error": "message_id is required"}), 400

    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sent = reply_message(integration["account_token"], message_id=message_id, body=message, cc=cc)
    if sent.get("id"):
        hydrate_message_bodies.delay(integration["id"], [sent["id"]])
        sync_gmail_history_delta.delay(integration["id"])
    return jsonify(sent), 201


@inbox_bp.route("/inbox/forward", methods=["POST"])
@require_auth
def inbox_forward():
    body = request.get_json(silent=True) or {}
    message_id = (body.get("message_id") or "").strip()
    to = (body.get("to") or "").strip()
    comment = body.get("body") or ""
    cc = body.get("cc") or ""
    if not message_id or not to:
        return jsonify({"error": "message_id and to are required"}), 400

    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sent = forward_message(
        integration["account_token"],
        message_id=message_id,
        to=to,
        body=comment,
        cc=cc,
    )
    if sent.get("id"):
        hydrate_message_bodies.delay(integration["id"], [sent["id"]])
        sync_gmail_history_delta.delay(integration["id"])
    return jsonify(sent), 201


@inbox_bp.route("/inbox/drafts/<message_id>/send", methods=["POST"])
@require_auth
def inbox_send_draft(message_id: str):
    message_id = (message_id or "").strip()
    if not message_id:
        return jsonify({"error": "message_id is required"}), 400

    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sb = get_supabase()
    rows = (
        sb.table("emails")
        .select("gmail_message_id, is_draft, label_ids_json")
        .eq("user_id", g.user_id)
        .eq("integration_id", integration["id"])
        .eq("gmail_message_id", message_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return jsonify({"error": "Draft message not found"}), 404

    row = rows[0]
    labels = row.get("label_ids_json") or []
    if not row.get("is_draft") and "DRAFT" not in labels:
        return jsonify({"error": "Message is not a draft"}), 400

    try:
        sent = send_draft_by_message_id(
            integration["account_token"],
            message_id=message_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception:
        log.exception(
            "inbox_send_draft_failed user=%s integration_id=%s message_id=%s",
            g.user_id,
            integration["id"],
            message_id,
        )
        return jsonify({"error": "Failed to send draft"}), 502

    if sent.get("id"):
        hydrate_message_bodies.delay(integration["id"], [sent["id"]])
    sync_gmail_history_delta.delay(integration["id"])
    return jsonify(sent), 201


@inbox_bp.route("/inbox/messages/<message_id>/read", methods=["POST"])
@require_auth
def mark_read(message_id: str):
    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    modify_result = modify_labels(
        integration["account_token"],
        message_id=message_id,
        remove_label_ids=["UNREAD"],
    )
    sb = get_supabase()
    sb.table("emails").update({"is_read": True}).eq("integration_id", integration["id"]).eq(
        "gmail_message_id", message_id
    ).execute()
    sync_gmail_history_delta.delay(integration["id"])
    return jsonify({"status": "ok", "message": modify_result})


@inbox_bp.route("/inbox/threads/<thread_id>/archive", methods=["POST"])
@require_auth
def archive_thread(thread_id: str):
    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sb = get_supabase()
    messages = (
        sb.table("emails")
        .select("gmail_message_id, label_ids_json")
        .eq("user_id", g.user_id)
        .eq("integration_id", integration["id"])
        .eq("gmail_thread_id", thread_id)
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    if not messages:
        return jsonify({"error": "Thread not found"}), 404

    archived_count = 0
    for row in messages:
        message_id = row.get("gmail_message_id")
        labels = row.get("label_ids_json") or []
        if not message_id or "INBOX" not in labels:
            continue

        modify_labels(
            integration["account_token"],
            message_id=message_id,
            remove_label_ids=["INBOX"],
        )
        updated_labels = [label for label in labels if label != "INBOX"]
        sb.table("emails").update({"label_ids_json": updated_labels}).eq(
            "integration_id", integration["id"]
        ).eq("gmail_message_id", message_id).execute()
        archived_count += 1

    sync_gmail_history_delta.delay(integration["id"])
    return jsonify({"status": "ok", "archived_messages": archived_count})


@inbox_bp.route("/inbox/threads/<thread_id>/discard", methods=["POST"])
@require_auth
def discard_thread_drafts(thread_id: str):
    integration = _get_gmail_integration(g.user_id)
    if not integration:
        return jsonify({"error": "Gmail integration not connected"}), 404

    sb = get_supabase()
    messages = (
        sb.table("emails")
        .select("gmail_message_id, label_ids_json, is_draft")
        .eq("user_id", g.user_id)
        .eq("integration_id", integration["id"])
        .eq("gmail_thread_id", thread_id)
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    if not messages:
        return jsonify({"error": "Thread not found"}), 404

    draft_rows = [
        row
        for row in messages
        if row.get("is_draft") or "DRAFT" in (row.get("label_ids_json") or [])
    ]
    if not draft_rows:
        return jsonify({"error": "No draft messages found in this thread"}), 400

    discarded_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for row in draft_rows:
        message_id = row.get("gmail_message_id")
        if not message_id:
            continue
        trash_message(integration["account_token"], message_id=message_id)
        sb.table("emails").update(
            {
                "deleted_at": now_iso,
                "updated_at": now_iso,
                "is_draft": False,
                "label_ids_json": [label for label in (row.get("label_ids_json") or []) if label != "DRAFT"],
            }
        ).eq("integration_id", integration["id"]).eq("gmail_message_id", message_id).execute()
        discarded_count += 1

    sync_gmail_history_delta.delay(integration["id"])
    return jsonify({"status": "ok", "discarded_drafts": discarded_count})
