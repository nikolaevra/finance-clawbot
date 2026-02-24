"""
Document tools for OpenAI function calling.

These tools give the AI assistant the ability to list and read
user-uploaded documents (PDF, DOCX, XLSX). Document content is
also automatically searchable via the existing memory_search tool
since it is indexed into memory_chunks.
"""
from __future__ import annotations

from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase


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
