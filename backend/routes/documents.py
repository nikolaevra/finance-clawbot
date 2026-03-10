"""
Documents API: upload, list, read content, and delete user documents.

Supported file types: PDF, DOCX, XLSX.
Files are stored in Supabase Storage and their text content is extracted
and indexed into memory_chunks for RAG search.
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify, g
from middleware.auth import require_auth

from services.supabase_service import get_supabase
from services.document_service import (
    delete_document_full,
    ingest_document_upload,
)

documents_bp = Blueprint("documents", __name__)


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


@documents_bp.route("/documents", methods=["GET"])
@require_auth
def list_documents():
    """List all documents for the authenticated user, newest first."""
    sb = get_supabase()
    result = (
        sb.table("documents")
        .select("id, user_id, filename, file_type, file_size, storage_path, status, created_at")
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
        .select("id, filename, extracted_text, status")
        .eq("id", document_id)
        .eq("user_id", g.user_id)
        .execute()
    )

    if not result.data:
        return jsonify({"error": "Document not found"}), 404

    doc = result.data[0]

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
