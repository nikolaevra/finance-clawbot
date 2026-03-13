"""
Documents API: upload, list, read content, and delete user documents.

Supported file types: PDF, DOCX, XLSX.
Files are stored in Supabase Storage and their text content is extracted
and indexed into memory_chunks for RAG search.
"""
from __future__ import annotations

from urllib.parse import urlparse, parse_qs

from flask import Blueprint, request, jsonify, g
from middleware.auth import require_auth

from services.supabase_service import get_supabase
from services.document_service import (
    delete_document_full,
    ingest_document_upload,
    ingest_google_drive_document,
    refresh_google_drive_document_if_stale,
)

documents_bp = Blueprint("documents", __name__)


def _extract_drive_file_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        segments = [seg for seg in parsed.path.split("/") if seg]
        if "d" in segments:
            idx = segments.index("d")
            if idx + 1 < len(segments):
                return segments[idx + 1]
        query = parse_qs(parsed.query)
        if query.get("id"):
            return query["id"][0]
    return raw


def _latest_google_workspace_integration(user_id: str) -> dict | None:
    sb = get_supabase()
    result = (
        sb.table("integrations")
        .select("id, account_token")
        .eq("user_id", user_id)
        .eq("provider", "google_workspace")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _persist_workspace_token(integration_id: str, token: str | None) -> None:
    if not token:
        return
    sb = get_supabase()
    sb.table("integrations").update({"account_token": token}).eq("id", integration_id).execute()


@documents_bp.route("/documents/upload", methods=["POST"])
@require_auth
def upload_document():
    """
    Upload a document file.

    Accepts multipart/form-data with a 'file' field.
    Validates type and size, stores in Supabase Storage,
    extracts text, and indexes for RAG.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400

    # Read file bytes
    file_bytes = file.read()

    user_id = g.user_id
    try:
        doc = ingest_document_upload(
            user_id=user_id,
            filename=file.filename,
            file_bytes=file_bytes,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(doc), 201


@documents_bp.route("/documents/link-google-drive", methods=["POST"])
@require_auth
def link_google_drive_document():
    """Link and ingest a file from Google Drive by file ID."""
    body = request.get_json(silent=True) or {}
    file_id = _extract_drive_file_id(str(body.get("file_id") or ""))
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    integration = _latest_google_workspace_integration(g.user_id)
    if not integration:
        return jsonify({"error": "No active Google Workspace integration found"}), 404

    try:
        doc, refreshed = ingest_google_drive_document(
            user_id=g.user_id,
            credentials_json=integration["account_token"],
            file_id=file_id,
        )
        _persist_workspace_token(integration["id"], refreshed)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(doc), 201


@documents_bp.route("/documents", methods=["GET"])
@require_auth
def list_documents():
    """List all documents for the authenticated user, newest first."""
    sb = get_supabase()
    result = (
        sb.table("documents")
        .select("*")
        .eq("user_id", g.user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return jsonify(result.data)


@documents_bp.route("/documents/<document_id>/content", methods=["GET"])
@require_auth
def get_document_content(document_id: str):
    """Return the extracted text content of a document."""
    sb = get_supabase()
    result = (
        sb.table("documents")
        .select("*")
        .eq("id", document_id)
        .eq("user_id", g.user_id)
        .execute()
    )

    if not result.data:
        return jsonify({"error": "Document not found"}), 404

    doc = result.data[0]
    if doc.get("source") == "google_drive":
        integration = _latest_google_workspace_integration(g.user_id)
        if integration:
            try:
                doc, refreshed = refresh_google_drive_document_if_stale(
                    g.user_id,
                    doc,
                    integration["account_token"],
                )
                _persist_workspace_token(integration["id"], refreshed)
            except Exception:
                # best effort; fallback to last stored content
                pass

    if doc["status"] != "ready":
        return jsonify({"error": f"Document is not ready (status: {doc['status']})"}), 400

    return jsonify({
        "id": doc["id"],
        "filename": doc["filename"],
        "content": doc["extracted_text"] or "",
    })


@documents_bp.route("/documents/<document_id>", methods=["DELETE"])
@require_auth
def delete_document(document_id: str):
    """Delete a document (Storage file, memory_chunks, and DB row)."""
    try:
        delete_document_full(g.user_id, document_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({"status": "deleted"}), 200
