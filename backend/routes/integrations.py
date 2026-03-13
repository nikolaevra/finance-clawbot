"""
Integrations routes – manage accounting (Merge.dev), Gmail, and Float integrations.

Endpoints:
  GET    /integrations                – list user's integrations
  POST   /integrations/link-token     – create a Merge Link token (accounting)
  POST   /integrations                – save a new Merge accounting integration
  POST   /integrations/float          – connect Float via API key
  POST   /integrations/gmail/auth-url – get Google OAuth URL
  GET    /integrations/gmail/callback – handle Google OAuth redirect
  POST   /integrations/gmail/webhook  – receive Gmail push events
  DELETE /integrations/<id>           – disconnect integration
"""
from __future__ import annotations

import logging
import json
import base64
import hmac
from datetime import datetime, timezone
from typing import Any
from flask import Blueprint, request, g, jsonify, redirect
from middleware.auth import require_auth

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from config import Config
from services.merge_service import (
    create_link_token,
    exchange_public_token,
    delete_account,
)
from services.float_service import validate_token as float_validate_token
from services.audit_log_service import log_gmail_inbound

integrations_bp = Blueprint("integrations", __name__)


def _latest_google_workspace_integration(user_id: str) -> dict[str, Any] | None:
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, user_id, account_token, status")
        .eq("user_id", user_id)
        .eq("provider", "google_workspace")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _persist_integration_token(integration_id: str, account_token: str) -> None:
    sb = get_supabase()
    sb.table("integrations").update(
        {
            "account_token": account_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", integration_id).execute()


# ── List integrations ─────────────────────────────────────────

@integrations_bp.route("/integrations", methods=["GET"])
@require_auth
def list_integrations():
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, provider, integration_name, status, created_at, updated_at")
        .eq("user_id", g.user_id)
        .neq("status", "disconnected")
        .order("created_at", desc=True)
        .execute()
    )
    return jsonify(result.data)


# ── Create Link token ────────────────────────────────────────

@integrations_bp.route("/integrations/link-token", methods=["POST"])
@require_auth
def get_link_token():
    body = request.get_json(silent=True) or {}
    org_name = body.get("organization_name", "My Organization")
    email = body.get("email", "user@example.com")
    integration_slug = body.get("integration_slug")

    try:
        data = create_link_token(
            user_id=g.user_id,
            organization_name=org_name,
            user_email=email,
            integration_slug=integration_slug,
        )
        return jsonify(data)
    except Exception as e:
        log.exception("create_link_token failed for user=%s", g.user_id)
        return jsonify({"error": f"Failed to create link token: {e}"}), 502


# ── Create integration (exchange token & persist) ─────────────

@integrations_bp.route("/integrations", methods=["POST"])
@require_auth
def create_integration():
    body = request.get_json(silent=True) or {}
    public_token = body.get("public_token")
    if not public_token:
        return jsonify({"error": "public_token is required"}), 400

    provider = body.get("provider", "quickbooks")
    integration_name = body.get("integration_name", "QuickBooks Online")
    log.info("create_integration_start user=%s provider=%s", g.user_id, provider)

    try:
        token_data = exchange_public_token(public_token, user_id=g.user_id)
    except Exception as e:
        log.exception("Token exchange failed for user=%s", g.user_id)
        return jsonify({"error": f"Token exchange failed: {e}"}), 502

    account_token = token_data.get("account_token", "")
    merge_account_id = token_data.get("integration", {}).get("id", "") if isinstance(token_data.get("integration"), dict) else ""

    if not account_token:
        log.error("create_integration_missing_account_token user=%s provider=%s", g.user_id, provider)
        return jsonify({"error": "No account_token returned from Merge"}), 502

    sb = get_supabase()
    result = (
        sb.table("integrations")
        .insert({
            "user_id": g.user_id,
            "provider": provider,
            "integration_name": integration_name,
            "account_token": account_token,
            "merge_account_id": merge_account_id,
            "status": "active",
        })
        .execute()
    )

    row = result.data[0] if result.data else {}
    row.pop("account_token", None)
    log.info("create_integration_success user=%s provider=%s integration_id=%s", g.user_id, provider, row.get("id"))
    return jsonify(row), 201


# ── Float: connect via API key ────────────────────────────────

@integrations_bp.route("/integrations/float", methods=["POST"])
@require_auth
def connect_float():
    body = request.get_json(silent=True) or {}
    api_token = body.get("api_token", "").strip()
    if not api_token:
        return jsonify({"error": "api_token is required"}), 400

    log.info("connect_float_start user=%s", g.user_id)
    if not float_validate_token(api_token, user_id=g.user_id):
        log.warning("connect_float_invalid_token user=%s", g.user_id)
        return jsonify({"error": "Invalid Float API token"}), 401

    sb = get_supabase()
    result = (
        sb.table("integrations")
        .insert({
            "user_id": g.user_id,
            "provider": "float",
            "integration_name": "Float",
            "account_token": api_token,
            "status": "active",
        })
        .execute()
    )

    row = result.data[0] if result.data else {}
    row.pop("account_token", None)
    log.info("connect_float_success user=%s integration_id=%s", g.user_id, row.get("id"))
    return jsonify(row), 201


# ── Gmail: OAuth flow ─────────────────────────────────────────

@integrations_bp.route("/integrations/gmail/auth-url", methods=["POST"])
@require_auth
def gmail_auth_url():
    from services.gmail_service import get_auth_url
    try:
        url = get_auth_url(g.user_id)
        return jsonify({"auth_url": url})
    except Exception as e:
        log.exception("gmail_auth_url failed for user=%s", g.user_id)
        return jsonify({"error": f"Failed to generate auth URL: {e}"}), 500


@integrations_bp.route("/integrations/gmail/callback", methods=["GET"])
def gmail_callback():
    """Handle the Google OAuth redirect.  No @require_auth because
    the user_id is passed via the ``state`` query parameter."""
    from services.gmail_service import exchange_code, get_profile, parse_oauth_state

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return jsonify({"error": "Missing code or state"}), 400

    try:
        user_id, code_verifier = parse_oauth_state(state)
    except Exception as e:
        log.warning("gmail_callback_invalid_state state=%s err=%s", state, e)
        return jsonify({"error": "Invalid OAuth state"}), 400
    log.info("gmail_callback_start user=%s", user_id)

    try:
        credentials_json = exchange_code(code, code_verifier=code_verifier)
        profile = get_profile(credentials_json)
    except Exception as e:
        log.exception("gmail exchange_code failed user=%s", user_id)
        return jsonify({"error": f"OAuth exchange failed: {e}"}), 502

    sb = get_supabase()
    result = (
        sb.table("integrations")
        .insert({
            "user_id": user_id,
            "provider": "gmail",
            "integration_name": f"Gmail ({profile.get('emailAddress', '')})",
            "account_token": credentials_json,
            "status": "active",
            "gmail_email": profile.get("emailAddress", ""),
            "gmail_history_id": profile.get("historyId", ""),
        })
        .execute()
    )
    integration_row = result.data[0] if result.data else {}
    integration_id = integration_row.get("id")
    if integration_id:
        sb.table("gmail_sync_state").upsert(
            {
                "user_id": user_id,
                "integration_id": integration_id,
                "last_history_id": profile.get("historyId", ""),
                "sync_cursor_status": "queued",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="integration_id",
        ).execute()
        from tasks.email_sync_tasks import kickoff_initial_gmail_sync

        kickoff_initial_gmail_sync.delay(integration_id)

    log.info("gmail_callback_success user=%s integration_id=%s", user_id, integration_id)

    frontend_url = Config.FRONTEND_URL
    return redirect(f"{frontend_url}/chat/integrations?gmail=connected")


# ── Google Workspace: OAuth flow + API ops ────────────────────

@integrations_bp.route("/integrations/google-workspace/auth-url", methods=["POST"])
@require_auth
def google_workspace_auth_url():
    from services.google_workspace_service import get_auth_url
    try:
        url = get_auth_url(g.user_id)
        return jsonify({"auth_url": url})
    except Exception as e:
        log.exception("google_workspace_auth_url failed for user=%s", g.user_id)
        return jsonify({"error": f"Failed to generate auth URL: {e}"}), 500


@integrations_bp.route("/integrations/google-workspace/callback", methods=["GET"])
def google_workspace_callback():
    from services.google_workspace_service import (
        exchange_code,
        get_user_profile,
        parse_oauth_state,
    )

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return jsonify({"error": "Missing code or state"}), 400

    try:
        user_id, code_verifier = parse_oauth_state(state)
    except Exception as e:
        log.warning("google_workspace_callback_invalid_state state=%s err=%s", state, e)
        return jsonify({"error": "Invalid OAuth state"}), 400

    try:
        credentials_json = exchange_code(code, code_verifier=code_verifier)
        profile, refreshed_token = get_user_profile(credentials_json)
        token_to_store = refreshed_token or credentials_json
    except Exception as e:
        log.exception("google_workspace exchange_code failed user=%s", user_id)
        return jsonify({"error": f"OAuth exchange failed: {e}"}), 502

    email = (profile.get("email") or "").strip()
    integration_name = f"Google Workspace ({email})" if email else "Google Workspace"
    sb = get_supabase()
    sb.table("integrations").insert({
        "user_id": user_id,
        "provider": "google_workspace",
        "integration_name": integration_name,
        "account_token": token_to_store,
        "status": "active",
    }).execute()

    frontend_url = Config.FRONTEND_URL
    return redirect(f"{frontend_url}/chat/integrations?google_workspace=connected")


def _require_workspace_credentials() -> tuple[dict[str, Any] | None, Any | None]:
    integration = _latest_google_workspace_integration(g.user_id)
    if not integration:
        return None, (jsonify({"error": "No active Google Workspace integration found"}), 404)
    return integration, None


@integrations_bp.route("/integrations/google-workspace/drive/list", methods=["POST"])
@require_auth
def google_workspace_drive_list():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    page_size = int(body.get("page_size", 20) or 20)
    try:
        payload, refreshed = google_workspace_service.drive_list_files(
            integration["account_token"],
            query=query,
            page_size=page_size,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_drive_list failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/drive/file", methods=["POST"])
@require_auth
def google_workspace_drive_get_file_metadata():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    file_id = (body.get("file_id") or "").strip()
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400
    try:
        payload, refreshed = google_workspace_service.drive_get_file_metadata(
            integration["account_token"],
            file_id=file_id,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_drive_get_file_metadata failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/drive/file/content", methods=["POST"])
@require_auth
def google_workspace_drive_get_file_content():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    file_id = (body.get("file_id") or "").strip()
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400
    try:
        payload, refreshed = google_workspace_service.drive_get_text_content(
            integration["account_token"],
            file_id=file_id,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_drive_get_file_content failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/drive/file/create-text", methods=["POST"])
@require_auth
def google_workspace_drive_create_text_file():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    content = str(body.get("content") or "")
    mime_type = (body.get("mime_type") or "text/plain").strip()
    parent_folder_id = (body.get("parent_folder_id") or "").strip() or None
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        payload, refreshed = google_workspace_service.drive_create_text_file(
            integration["account_token"],
            name=name,
            content=content,
            mime_type=mime_type,
            parent_folder_id=parent_folder_id,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload), 201
    except Exception as e:
        log.exception("google_workspace_drive_create_text_file failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/drive/file/update-text", methods=["POST"])
@require_auth
def google_workspace_drive_update_text_file():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    file_id = (body.get("file_id") or "").strip()
    content = str(body.get("content") or "")
    mime_type = (body.get("mime_type") or "text/plain").strip()
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400
    try:
        payload, refreshed = google_workspace_service.drive_update_text_file(
            integration["account_token"],
            file_id=file_id,
            content=content,
            mime_type=mime_type,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_drive_update_text_file failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/docs/create", methods=["POST"])
@require_auth
def google_workspace_docs_create():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    content = str(body.get("content") or "")
    if not title:
        return jsonify({"error": "title is required"}), 400
    try:
        payload, refreshed = google_workspace_service.docs_create_document(
            integration["account_token"],
            title=title,
            content=content,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload), 201
    except Exception as e:
        log.exception("google_workspace_docs_create failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/docs/get", methods=["POST"])
@require_auth
def google_workspace_docs_get():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    document_id = (body.get("document_id") or "").strip()
    if not document_id:
        return jsonify({"error": "document_id is required"}), 400
    try:
        payload, refreshed = google_workspace_service.docs_get_document(
            integration["account_token"],
            document_id=document_id,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_docs_get failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/docs/append-text", methods=["POST"])
@require_auth
def google_workspace_docs_append_text():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    document_id = (body.get("document_id") or "").strip()
    text = str(body.get("text") or "")
    if not document_id:
        return jsonify({"error": "document_id is required"}), 400
    if not text:
        return jsonify({"error": "text is required"}), 400
    try:
        payload, refreshed = google_workspace_service.docs_append_text(
            integration["account_token"],
            document_id=document_id,
            text=text,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_docs_append_text failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/docs/replace-text", methods=["POST"])
@require_auth
def google_workspace_docs_replace_text():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    document_id = (body.get("document_id") or "").strip()
    replacements = body.get("replacements") or []
    if not document_id:
        return jsonify({"error": "document_id is required"}), 400
    if not isinstance(replacements, list):
        return jsonify({"error": "replacements must be an array"}), 400
    try:
        payload, refreshed = google_workspace_service.docs_replace_all_text(
            integration["account_token"],
            document_id=document_id,
            replacements=replacements,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_docs_replace_text failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/sheets/create", methods=["POST"])
@require_auth
def google_workspace_sheets_create():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    sheet_title = (body.get("sheet_title") or "Sheet1").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    try:
        payload, refreshed = google_workspace_service.sheets_create_spreadsheet(
            integration["account_token"],
            title=title,
            sheet_title=sheet_title,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload), 201
    except Exception as e:
        log.exception("google_workspace_sheets_create failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/sheets/read", methods=["POST"])
@require_auth
def google_workspace_sheets_read():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    spreadsheet_id = (body.get("spreadsheet_id") or "").strip()
    range_a1 = (body.get("range") or "").strip()
    if not spreadsheet_id or not range_a1:
        return jsonify({"error": "spreadsheet_id and range are required"}), 400
    try:
        payload, refreshed = google_workspace_service.sheets_read_values(
            integration["account_token"],
            spreadsheet_id=spreadsheet_id,
            range_a1=range_a1,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_sheets_read failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/sheets/update", methods=["POST"])
@require_auth
def google_workspace_sheets_update():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    spreadsheet_id = (body.get("spreadsheet_id") or "").strip()
    range_a1 = (body.get("range") or "").strip()
    values = body.get("values")
    if not spreadsheet_id or not range_a1:
        return jsonify({"error": "spreadsheet_id and range are required"}), 400
    if not isinstance(values, list):
        return jsonify({"error": "values must be a 2D array"}), 400
    try:
        payload, refreshed = google_workspace_service.sheets_update_values(
            integration["account_token"],
            spreadsheet_id=spreadsheet_id,
            range_a1=range_a1,
            values=values,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_sheets_update failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/google-workspace/sheets/append", methods=["POST"])
@require_auth
def google_workspace_sheets_append():
    from services import google_workspace_service

    integration, err = _require_workspace_credentials()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    spreadsheet_id = (body.get("spreadsheet_id") or "").strip()
    range_a1 = (body.get("range") or "").strip()
    values = body.get("values")
    if not spreadsheet_id or not range_a1:
        return jsonify({"error": "spreadsheet_id and range are required"}), 400
    if not isinstance(values, list):
        return jsonify({"error": "values must be a 2D array"}), 400
    try:
        payload, refreshed = google_workspace_service.sheets_append_values(
            integration["account_token"],
            spreadsheet_id=spreadsheet_id,
            range_a1=range_a1,
            values=values,
        )
        if refreshed:
            _persist_integration_token(integration["id"], refreshed)
        return jsonify(payload)
    except Exception as e:
        log.exception("google_workspace_sheets_append failed user=%s", g.user_id)
        return jsonify({"error": str(e)}), 500


@integrations_bp.route("/integrations/gmail/webhook", methods=["POST"])
def gmail_webhook():
    """Receive Gmail push notifications and dispatch trigger automations."""
    if Config.GMAIL_WEBHOOK_SECRET:
        incoming = request.headers.get("X-Webhook-Secret", "")
        if not hmac.compare_digest(incoming, Config.GMAIL_WEBHOOK_SECRET):
            return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    data_b64 = ((body.get("message") or {}).get("data") or "").strip()
    if not data_b64:
        return jsonify({"status": "ignored", "reason": "no_data"}), 200

    try:
        decoded = base64.b64decode(data_b64).decode("utf-8")
        payload = json.loads(decoded)
    except Exception:
        return jsonify({"status": "ignored", "reason": "invalid_payload"}), 200

    email = payload.get("emailAddress")
    if not email:
        return jsonify({"status": "ignored", "reason": "missing_email"}), 200

    sb = get_supabase()
    integration = (
        sb.table("integrations")
        .select("id, user_id, account_token, gmail_history_id, gmail_email")
        .eq("provider", "gmail")
        .eq("status", "active")
        .eq("gmail_email", email)
        .limit(1)
        .execute()
    )
    if not integration.data:
        return jsonify({"status": "ignored", "reason": "integration_not_found"}), 200
    row = integration.data[0]

    from services.gmail_service import list_new_inbox_messages_since
    from services.automation_trigger_service import dispatch_trigger_event
    from tasks.email_sync_tasks import sync_gmail_history_delta

    events, latest_history_id = list_new_inbox_messages_since(
        row["account_token"], row.get("gmail_history_id")
    )
    enqueued = 0
    for event in events:
        message_id = event.get("message_id")
        if not message_id:
            continue
        event_id = f"gmail:{row['id']}:{message_id}"
        log_gmail_inbound(
            user_id=row["user_id"],
            integration_id=row["id"],
            event_id=event_id,
            details={
                "message_id": message_id,
                "thread_id": event.get("thread_id"),
                "subject": event.get("subject"),
                "from": event.get("from"),
            },
        )
        dispatch = dispatch_trigger_event(
            provider="gmail",
            event="new_email",
            event_id=event_id,
            payload=event,
            user_id=row["user_id"],
        )
        enqueued += dispatch.get("enqueued", 0)

    if latest_history_id:
        sb.table("integrations").update(
            {"gmail_history_id": latest_history_id}
        ).eq("id", row["id"]).execute()

    sync_gmail_history_delta.delay(row["id"])

    return jsonify(
        {
            "status": "ok",
            "events": len(events),
            "enqueued": enqueued,
            "sync_enqueued": True,
        }
    )


# ── Disconnect integration ────────────────────────────────────

@integrations_bp.route("/integrations/<integration_id>", methods=["DELETE"])
@require_auth
def disconnect_integration(integration_id: str):
    sb = get_supabase()

    int_result = (
        sb.table("integrations")
        .select("id, provider, account_token")
        .eq("id", integration_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not int_result.data:
        log.warning("disconnect_integration_not_found user=%s integration_id=%s", g.user_id, integration_id)
        return jsonify({"error": "Integration not found"}), 404

    provider = int_result.data.get("provider", "")
    account_token = int_result.data.get("account_token", "")

    if provider in ("quickbooks", "netsuite"):
        log.info("disconnect_integration_remote_delete user=%s provider=%s integration_id=%s", g.user_id, provider, integration_id)
        delete_account(account_token, user_id=g.user_id)

    sb.table("integrations").update({
        "status": "disconnected",
        "account_token": "",
    }).eq("id", integration_id).execute()
    log.info("disconnect_integration_success user=%s provider=%s integration_id=%s", g.user_id, provider, integration_id)

    return jsonify({"status": "disconnected"})
