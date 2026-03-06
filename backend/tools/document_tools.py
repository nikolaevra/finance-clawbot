"""
Document tools for OpenAI function calling.

These tools give the AI assistant the ability to list, read, save,
and delete user documents (PDF, DOCX, XLSX). Document content is
also automatically searchable via the existing memory_search tool
since it is indexed into memory_chunks.
"""
from __future__ import annotations

import logging

from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase

log = logging.getLogger(__name__)


def _doc_service():
    """Lazy import to avoid circular import at module load time."""
    from services import document_service
    return document_service


def _log_document_access(tool_name: str, source_file: str | None = None) -> None:
    """Best-effort insert into memory_access_log for document tool usage."""
    try:
        conversation_id = getattr(g, "conversation_id", None)
        if not conversation_id:
            return
        sb = get_supabase()
        sb.table("memory_access_log").insert({
            "user_id": g.user_id,
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "source_file": source_file,
        }).execute()
    except Exception:
        pass  # logging failure should never block the tool


# ── document_list ─────────────────────────────────────────────────────

@tool_registry.register(
    name="document_list",
    label="List Documents",
    category="documents",
    description=(
        "List all documents the user has uploaded. Returns document names, "
        "types (PDF, DOCX, XLSX), sizes, and upload dates. Use this to see "
        "what documents are available before reading one."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def document_list() -> dict:
    user_id = g.user_id
    sb = get_supabase()

    result = (
        sb.table("documents")
        .select("id, filename, file_type, file_size, status, created_at")
        .eq("user_id", user_id)
        .eq("status", "ready")
        .order("created_at", desc=True)
        .execute()
    )

    _log_document_access("document_list", None)

    if not result.data:
        return {"documents": [], "message": "No documents uploaded yet."}

    return {
        "documents": [
            {
                "filename": d["filename"],
                "file_type": d["file_type"],
                "file_size": d["file_size"],
                "uploaded": d["created_at"],
            }
            for d in result.data
        ]
    }


# ── document_read ─────────────────────────────────────────────────────

@tool_registry.register(
    name="document_read",
    label="Read Document",
    category="documents",
    description=(
        "Read the full extracted text content of a specific uploaded document. "
        "Provide the exact filename (e.g. 'report.pdf'). Use document_list "
        "first if you don't know the filename. This returns the complete "
        "text extracted from the document."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The exact filename of the document to read (e.g. 'report.pdf').",
            },
        },
        "required": ["filename"],
    },
)
def document_read(filename: str) -> str:
    user_id = g.user_id
    sb = get_supabase()

    result = (
        sb.table("documents")
        .select("id, filename, extracted_text, status")
        .eq("user_id", user_id)
        .eq("filename", filename)
        .execute()
    )

    if not result.data:
        return f"Document not found: '{filename}'. Use document_list to see available documents."

    doc = result.data[0]

    if doc["status"] != "ready":
        return f"Document '{filename}' is still being processed (status: {doc['status']})."

    source_file = f"documents/{filename}"
    _log_document_access("document_read", source_file)

    text = doc["extracted_text"] or ""
    if not text:
        return f"Document '{filename}' has no extractable text content."

    # Truncate very long documents to avoid token overflow
    max_chars = 50000  # ~12.5k tokens
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated, {len(doc['extracted_text'])} total characters]"

    return text


# ── gmail_save_attachment ─────────────────────────────────────────────


def _get_gmail_credentials() -> str | None:
    """Return the Gmail OAuth credentials JSON for the current user."""
    user_id = getattr(g, "user_id", None)
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
            return result.data[0]["account_token"]
    except Exception:
        log.exception("gmail creds lookup failed user=%s", user_id)
    return None


_MIME_TO_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
}


@tool_registry.register(
    name="gmail_save_attachment",
    label="Save Email Attachment to Documents",
    category="documents",
    description=(
        "Save a file attachment from a Gmail message into the user's "
        "document storage. The file will be stored, its text extracted, "
        "and indexed for search. Provide the Gmail message_id (from "
        "gmail_get_message) and the attachment_filename. If you don't "
        "know the filename, call gmail_get_message first — its response "
        "includes an 'attachments' list with filenames. "
        "Supported file types: PDF, DOCX, DOC, XLSX, XLS."
    ),
    parameters={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID containing the attachment.",
            },
            "attachment_filename": {
                "type": "string",
                "description": (
                    "Exact filename of the attachment to save "
                    "(e.g. 'invoice.pdf'). If omitted and only one "
                    "supported attachment exists, it will be saved "
                    "automatically."
                ),
            },
        },
        "required": ["message_id"],
    },
)
def gmail_save_attachment(
    message_id: str,
    attachment_filename: str | None = None,
) -> dict:
    from services import gmail_service

    user_id = g.user_id
    creds = _get_gmail_credentials()
    if not creds:
        return {
            "error": (
                "No active Gmail integration found. The user needs to connect "
                "Gmail first via the Integrations page."
            ),
            "tool_used": "gmail_save_attachment",
        }

    try:
        attachments = gmail_service.list_attachments(creds, message_id)
    except Exception as e:
        log.exception("gmail_save_attachment list failed msg=%s", message_id)
        return {"error": str(e), "tool_used": "gmail_save_attachment"}

    if not attachments:
        return {
            "error": "This message has no file attachments.",
            "tool_used": "gmail_save_attachment",
        }

    ds = _doc_service()
    supported = [
        a for a in attachments
        if ds.get_file_extension(a["filename"]) in ds.ALLOWED_EXTENSIONS
    ]

    if attachment_filename:
        match = [a for a in supported if a["filename"] == attachment_filename]
        if not match:
            return {
                "error": (
                    f"Attachment '{attachment_filename}' not found or is not a "
                    f"supported type. Available supported attachments: "
                    f"{[a['filename'] for a in supported]}"
                ),
                "tool_used": "gmail_save_attachment",
            }
        target = match[0]
    elif len(supported) == 1:
        target = supported[0]
    else:
        return {
            "error": (
                "Multiple supported attachments found. Please specify "
                "attachment_filename. Available: "
                f"{[a['filename'] for a in supported]}"
            ),
            "tool_used": "gmail_save_attachment",
        }

    if target.get("size", 0) > ds.MAX_FILE_SIZE:
        return {
            "error": f"Attachment is too large (max {ds.MAX_FILE_SIZE // (1024*1024)}MB).",
            "tool_used": "gmail_save_attachment",
        }

    try:
        file_bytes = gmail_service.download_attachment(
            creds, message_id, target["attachment_id"],
        )
    except Exception as e:
        log.exception("gmail_save_attachment download failed msg=%s", message_id)
        return {"error": f"Failed to download attachment: {e}", "tool_used": "gmail_save_attachment"}

    filename = target["filename"]
    ext = ds.get_file_extension(filename)
    content_type = _MIME_TO_CONTENT_TYPE.get(ext, target.get("mime_type", "application/octet-stream"))

    try:
        storage_path = ds.store_document(user_id, filename, file_bytes, content_type)

        sb = get_supabase()
        result = sb.table("documents").insert({
            "user_id": user_id,
            "filename": filename,
            "file_type": ext,
            "file_size": len(file_bytes),
            "storage_path": storage_path,
            "status": "processing",
        }).execute()
        doc = result.data[0]

        ds.process_document(user_id, doc["id"], storage_path, ext)

        return {
            "tool_used": "gmail_save_attachment",
            "status": "saved",
            "filename": filename,
            "file_type": ext,
            "file_size": len(file_bytes),
            "message": f"Attachment '{filename}' saved to documents and indexed for search.",
        }
    except Exception as e:
        log.exception("gmail_save_attachment store/process failed")
        return {"error": f"Failed to save document: {e}", "tool_used": "gmail_save_attachment"}


# ── document_delete ───────────────────────────────────────────────────


@tool_registry.register(
    name="document_delete",
    label="Delete Document",
    category="documents",
    requires_approval=True,
    description=(
        "Permanently delete a document from the user's storage. This removes "
        "the stored file, all extracted text, and search index entries. "
        "Provide the exact filename (use document_list to find it). "
        "This action cannot be undone."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The exact filename of the document to delete (e.g. 'report.pdf').",
            },
        },
        "required": ["filename"],
    },
)
def document_delete(filename: str) -> dict:
    user_id = g.user_id
    sb = get_supabase()

    result = (
        sb.table("documents")
        .select("id, filename")
        .eq("user_id", user_id)
        .eq("filename", filename)
        .execute()
    )

    if not result.data:
        return {
            "error": f"Document '{filename}' not found. Use document_list to see available documents.",
            "tool_used": "document_delete",
        }

    doc_id = result.data[0]["id"]

    try:
        _doc_service().delete_document_full(user_id, doc_id)
    except Exception as e:
        log.exception("document_delete failed doc=%s user=%s", doc_id, user_id)
        return {"error": str(e), "tool_used": "document_delete"}

    _log_document_access("document_delete", f"documents/{filename}")

    return {
        "tool_used": "document_delete",
        "status": "deleted",
        "filename": filename,
        "message": f"Document '{filename}' has been permanently deleted.",
    }
