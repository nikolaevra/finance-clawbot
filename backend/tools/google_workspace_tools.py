"""Google Workspace tools for Drive, Docs, and Sheets."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import g

from services import google_workspace_service
from services.supabase_service import get_supabase
from tools.registry import tool_registry

log = logging.getLogger(__name__)

_NO_WORKSPACE = {
    "error": (
        "No active Google Workspace integration found. The user needs to connect "
        "Google Workspace first via the Integrations page."
    ),
}


def _integration() -> dict[str, Any] | None:
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, account_token")
        .eq("user_id", g.user_id)
        .eq("provider", "google_workspace")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _persist_token(integration_id: str, refreshed_token: str | None) -> None:
    if not refreshed_token:
        return
    sb = get_supabase()
    sb.table("integrations").update(
        {
            "account_token": refreshed_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", integration_id).execute()


@tool_registry.register(
    name="google_workspace_drive_list_files",
    label="List Drive Files",
    category="google_workspace",
    description="List Google Drive files by query and return file metadata.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Drive API query (q) string."},
            "page_size": {"type": "integer", "description": "Max files to return (1-100)."},
        },
        "required": [],
    },
)
def google_workspace_drive_list_files(query: str = "", page_size: int = 20) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_drive_list_files"}
    try:
        payload, refreshed = google_workspace_service.drive_list_files(
            row["account_token"],
            query=query,
            page_size=page_size,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_drive_list_files", **payload}
    except Exception as exc:
        log.exception("google_workspace_drive_list_files failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_drive_list_files"}


@tool_registry.register(
    name="google_workspace_drive_get_file",
    label="Get Drive File",
    category="google_workspace",
    description="Get metadata for a single Google Drive file by file_id.",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Google Drive file ID."},
        },
        "required": ["file_id"],
    },
)
def google_workspace_drive_get_file(file_id: str) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_drive_get_file"}
    try:
        payload, refreshed = google_workspace_service.drive_get_file_metadata(
            row["account_token"],
            file_id=file_id,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_drive_get_file", "file": payload}
    except Exception as exc:
        log.exception("google_workspace_drive_get_file failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_drive_get_file"}


@tool_registry.register(
    name="google_workspace_drive_read_text",
    label="Read Drive File Text",
    category="google_workspace",
    description="Read text content from Drive or native Google Docs files.",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Google Drive file ID."},
        },
        "required": ["file_id"],
    },
)
def google_workspace_drive_read_text(file_id: str) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_drive_read_text"}
    try:
        payload, refreshed = google_workspace_service.drive_get_text_content(
            row["account_token"],
            file_id=file_id,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_drive_read_text", **payload}
    except Exception as exc:
        log.exception("google_workspace_drive_read_text failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_drive_read_text"}


@tool_registry.register(
    name="google_workspace_drive_create_text_file",
    label="Create Drive Text File",
    category="google_workspace",
    requires_approval=True,
    description="Create a text-based file in Google Drive.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "File name."},
            "content": {"type": "string", "description": "File content."},
            "mime_type": {"type": "string", "description": "MIME type, defaults to text/plain."},
            "parent_folder_id": {"type": "string", "description": "Optional parent Drive folder ID."},
        },
        "required": ["name", "content"],
    },
)
def google_workspace_drive_create_text_file(
    name: str,
    content: str,
    mime_type: str = "text/plain",
    parent_folder_id: str = "",
) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_drive_create_text_file"}
    try:
        payload, refreshed = google_workspace_service.drive_create_text_file(
            row["account_token"],
            name=name,
            content=content,
            mime_type=mime_type,
            parent_folder_id=parent_folder_id or None,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_drive_create_text_file", "file": payload}
    except Exception as exc:
        log.exception("google_workspace_drive_create_text_file failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_drive_create_text_file"}


@tool_registry.register(
    name="google_workspace_drive_update_text_file",
    label="Update Drive Text File",
    category="google_workspace",
    requires_approval=True,
    description="Replace content for a Drive text file by file_id.",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Google Drive file ID."},
            "content": {"type": "string", "description": "New file content."},
            "mime_type": {"type": "string", "description": "MIME type, defaults to text/plain."},
        },
        "required": ["file_id", "content"],
    },
)
def google_workspace_drive_update_text_file(
    file_id: str,
    content: str,
    mime_type: str = "text/plain",
) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_drive_update_text_file"}
    try:
        payload, refreshed = google_workspace_service.drive_update_text_file(
            row["account_token"],
            file_id=file_id,
            content=content,
            mime_type=mime_type,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_drive_update_text_file", "file": payload}
    except Exception as exc:
        log.exception("google_workspace_drive_update_text_file failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_drive_update_text_file"}


@tool_registry.register(
    name="google_workspace_docs_create_document",
    label="Create Google Doc",
    category="google_workspace",
    requires_approval=True,
    description="Create a new Google Docs document with optional initial content.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Document title."},
            "content": {"type": "string", "description": "Optional initial body text."},
        },
        "required": ["title"],
    },
)
def google_workspace_docs_create_document(title: str, content: str = "") -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_docs_create_document"}
    try:
        payload, refreshed = google_workspace_service.docs_create_document(
            row["account_token"],
            title=title,
            content=content,
        )
        _persist_token(row["id"], refreshed)
        return {
            "tool_used": "google_workspace_docs_create_document",
            "document": payload,
        }
    except Exception as exc:
        log.exception("google_workspace_docs_create_document failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_docs_create_document"}


@tool_registry.register(
    name="google_workspace_docs_get_document",
    label="Read Google Doc",
    category="google_workspace",
    description="Read title and extracted text content from a Google Doc.",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "Google Docs document ID."},
        },
        "required": ["document_id"],
    },
)
def google_workspace_docs_get_document(document_id: str) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_docs_get_document"}
    try:
        payload, refreshed = google_workspace_service.docs_get_document(
            row["account_token"],
            document_id=document_id,
        )
        _persist_token(row["id"], refreshed)
        return {
            "tool_used": "google_workspace_docs_get_document",
            "document": payload,
        }
    except Exception as exc:
        log.exception("google_workspace_docs_get_document failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_docs_get_document"}


@tool_registry.register(
    name="google_workspace_docs_append_text",
    label="Append Google Doc Text",
    category="google_workspace",
    requires_approval=True,
    description="Append text to the end of a Google Doc.",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "Google Docs document ID."},
            "text": {"type": "string", "description": "Text to append."},
        },
        "required": ["document_id", "text"],
    },
)
def google_workspace_docs_append_text(document_id: str, text: str) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_docs_append_text"}
    try:
        payload, refreshed = google_workspace_service.docs_append_text(
            row["account_token"],
            document_id=document_id,
            text=text,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_docs_append_text", "result": payload}
    except Exception as exc:
        log.exception("google_workspace_docs_append_text failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_docs_append_text"}


@tool_registry.register(
    name="google_workspace_docs_replace_text",
    label="Replace Google Doc Text",
    category="google_workspace",
    requires_approval=True,
    description="Replace one or more strings in a Google Doc using replaceAllText.",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "Google Docs document ID."},
            "replacements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["old_text", "new_text"],
                },
            },
        },
        "required": ["document_id", "replacements"],
    },
)
def google_workspace_docs_replace_text(document_id: str, replacements: list[dict[str, str]]) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_docs_replace_text"}
    try:
        payload, refreshed = google_workspace_service.docs_replace_all_text(
            row["account_token"],
            document_id=document_id,
            replacements=replacements,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_docs_replace_text", "result": payload}
    except Exception as exc:
        log.exception("google_workspace_docs_replace_text failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_docs_replace_text"}


@tool_registry.register(
    name="google_workspace_sheets_create_spreadsheet",
    label="Create Google Sheet",
    category="google_workspace",
    requires_approval=True,
    description="Create a new Google Sheets spreadsheet.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Spreadsheet title."},
            "sheet_title": {"type": "string", "description": "Optional first tab title."},
        },
        "required": ["title"],
    },
)
def google_workspace_sheets_create_spreadsheet(
    title: str,
    sheet_title: str = "Sheet1",
) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_sheets_create_spreadsheet"}
    try:
        payload, refreshed = google_workspace_service.sheets_create_spreadsheet(
            row["account_token"],
            title=title,
            sheet_title=sheet_title,
        )
        _persist_token(row["id"], refreshed)
        return {
            "tool_used": "google_workspace_sheets_create_spreadsheet",
            "spreadsheet": payload,
        }
    except Exception as exc:
        log.exception("google_workspace_sheets_create_spreadsheet failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_sheets_create_spreadsheet"}


@tool_registry.register(
    name="google_workspace_sheets_read_values",
    label="Read Google Sheet Values",
    category="google_workspace",
    description="Read values from a Google Sheets range (A1 notation).",
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID."},
            "range": {"type": "string", "description": "A1 range (e.g. Sheet1!A1:D20)."},
        },
        "required": ["spreadsheet_id", "range"],
    },
)
def google_workspace_sheets_read_values(spreadsheet_id: str, range: str) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_sheets_read_values"}
    try:
        payload, refreshed = google_workspace_service.sheets_read_values(
            row["account_token"],
            spreadsheet_id=spreadsheet_id,
            range_a1=range,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_sheets_read_values", **payload}
    except Exception as exc:
        log.exception("google_workspace_sheets_read_values failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_sheets_read_values"}


@tool_registry.register(
    name="google_workspace_sheets_update_values",
    label="Update Google Sheet Values",
    category="google_workspace",
    requires_approval=True,
    description="Update values in a Google Sheets range (A1 notation).",
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID."},
            "range": {"type": "string", "description": "A1 range (e.g. Sheet1!A1:D1)."},
            "values": {
                "type": "array",
                "items": {"type": "array", "items": {}},
                "description": "2D array of row values.",
            },
        },
        "required": ["spreadsheet_id", "range", "values"],
    },
)
def google_workspace_sheets_update_values(
    spreadsheet_id: str,
    range: str,
    values: list[list[Any]],
) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_sheets_update_values"}
    try:
        payload, refreshed = google_workspace_service.sheets_update_values(
            row["account_token"],
            spreadsheet_id=spreadsheet_id,
            range_a1=range,
            values=values,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_sheets_update_values", "result": payload}
    except Exception as exc:
        log.exception("google_workspace_sheets_update_values failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_sheets_update_values"}


@tool_registry.register(
    name="google_workspace_sheets_append_values",
    label="Append Google Sheet Values",
    category="google_workspace",
    requires_approval=True,
    description="Append rows to a Google Sheets range.",
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID."},
            "range": {"type": "string", "description": "A1 range for append start."},
            "values": {
                "type": "array",
                "items": {"type": "array", "items": {}},
                "description": "2D array of row values.",
            },
        },
        "required": ["spreadsheet_id", "range", "values"],
    },
)
def google_workspace_sheets_append_values(
    spreadsheet_id: str,
    range: str,
    values: list[list[Any]],
) -> dict:
    row = _integration()
    if not row:
        return {**_NO_WORKSPACE, "tool_used": "google_workspace_sheets_append_values"}
    try:
        payload, refreshed = google_workspace_service.sheets_append_values(
            row["account_token"],
            spreadsheet_id=spreadsheet_id,
            range_a1=range,
            values=values,
        )
        _persist_token(row["id"], refreshed)
        return {"tool_used": "google_workspace_sheets_append_values", "result": payload}
    except Exception as exc:
        log.exception("google_workspace_sheets_append_values failed user=%s", g.user_id)
        return {"error": str(exc), "tool_used": "google_workspace_sheets_append_values"}
