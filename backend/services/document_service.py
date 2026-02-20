"""
Document service: file storage, text extraction, and lifecycle management.

Handles uploading documents to Supabase Storage, extracting text content
from PDF, DOCX, and XLSX files, and managing document metadata in the
documents table.
"""
from __future__ import annotations

import io
import uuid
import traceback
from datetime import date

from services.supabase_service import get_supabase
from services.memory_service import _ensure_bucket, _storage, append_daily_log, ensure_daily_file
from services.embedding_service import index_memory_file
from services.openai_service import summarize_document
from config import Config


# ── Allowed file types ────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "doc", "xls"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _document_storage_path(user_id: str, filename: str) -> str:
    """Build a unique Storage path for a document."""
    unique = uuid.uuid4().hex[:8]
    safe_name = filename.replace(" ", "_")
    return f"{user_id}/documents/{unique}_{safe_name}"


def get_file_extension(filename: str) -> str:
    """Extract and normalise the file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext


# ── Text extraction ───────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file."""
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text.strip())
    return "\n\n".join(parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file (Word / Google Docs export)."""
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(file_bytes))
    parts: list[str] = []

    # Paragraphs
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    # Tables
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n\n".join(parts)


def extract_text_from_xlsx(file_bytes: bytes) -> str:
    """Extract text from an XLSX/XLS file."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    parts: list[str] = []

    for sheet in wb.sheetnames:
        ws = wb[sheet]
        parts.append(f"## Sheet: {sheet}")

        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            non_empty = [c for c in cells if c]
            if non_empty:
                parts.append(" | ".join(cells))

    wb.close()
    return "\n\n".join(parts)


def extract_text(file_bytes: bytes, file_type: str) -> str:
    """Route to the correct extractor based on file type."""
    if file_type in ("pdf",):
        return extract_text_from_pdf(file_bytes)
    elif file_type in ("docx", "doc"):
        return extract_text_from_docx(file_bytes)
    elif file_type in ("xlsx", "xls"):
        return extract_text_from_xlsx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


# ── Storage operations ────────────────────────────────────────────────

def store_document(user_id: str, filename: str, file_bytes: bytes, content_type: str) -> str:
    """
    Upload a document to Supabase Storage.

    Returns the storage path.
    """
    _ensure_bucket()
    storage = _storage()
    path = _document_storage_path(user_id, filename)

    storage.upload(
        path,
        file_bytes,
        {"content-type": content_type},
    )
    return path


def download_document(storage_path: str) -> bytes:
    """Download a document from Supabase Storage."""
    _ensure_bucket()
    storage = _storage()
    data = storage.download(storage_path)
    return data if isinstance(data, bytes) else data.encode("utf-8")


def delete_document_file(storage_path: str) -> None:
    """Delete a document from Supabase Storage."""
    _ensure_bucket()
    storage = _storage()
    try:
        storage.remove([storage_path])
    except Exception:
        pass  # best-effort deletion


# ── Full lifecycle ────────────────────────────────────────────────────

def process_document(user_id: str, document_id: str, storage_path: str, file_type: str) -> None:
    """
    Download, extract text, index into memory_chunks, and update status.

    This is called after the initial upload. It:
    1. Downloads the file from Storage
    2. Extracts text content
    3. Stores extracted text in the documents table
    4. Indexes content into memory_chunks for RAG
    5. Updates status to 'ready' (or 'error')
    """
    sb = get_supabase()

    try:
        # 1. Download
        file_bytes = download_document(storage_path)

        # 2. Extract text
        text = extract_text(file_bytes, file_type)

        if not text.strip():
            print(f"[document_service] No text extracted from {document_id} (type={file_type})")
            sb.table("documents").update({
                "status": "error",
                "extracted_text": "",
            }).eq("id", document_id).execute()
            return

        # 3. Save extracted text to documents table
        sb.table("documents").update({
            "extracted_text": text,
            "status": "ready",
        }).eq("id", document_id).execute()

        # 4. Index into memory_chunks for RAG search
        # Use source_file format: "documents/<filename>"
        result = sb.table("documents").select("filename").eq("id", document_id).execute()
        if result.data:
            source_file = f"documents/{result.data[0]['filename']}"
            index_memory_file(user_id, source_file, text)

        # 5. Generate summary and save to daily memory log
        #    Wrapped in its own try/except so summarisation failure never
        #    marks the document as 'error' — the document is already ready.
        try:
            if result.data:
                filename = result.data[0]["filename"]
                summary = summarize_document(text, filename)
                if summary:
                    memory_entry = (
                        f"## Document uploaded: {filename}\n\n"
                        f"{summary}"
                    )
                    ensure_daily_file(user_id)
                    updated_daily = append_daily_log(user_id, memory_entry)

                    # Re-index the daily log so the summary is searchable
                    today_source = f"daily/{date.today().isoformat()}.md"
                    index_memory_file(user_id, today_source, updated_daily)
        except Exception:
            print(f"[document_service] Summarisation failed (non-blocking):\n{traceback.format_exc()}")

    except Exception as e:
        # Mark as error
        print(f"[document_service] process_document FAILED for {document_id}:\n{traceback.format_exc()}")
        sb.table("documents").update({
            "status": "error",
        }).eq("id", document_id).execute()
        raise e


def delete_document_full(user_id: str, document_id: str) -> None:
    """
    Delete a document completely: Storage file, memory_chunks, and DB row.
    """
    sb = get_supabase()

    # Get document info
    result = sb.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()
    if not result.data:
        raise ValueError("Document not found")

    doc = result.data[0]

    # 1. Delete from Storage
    delete_document_file(doc["storage_path"])

    # 2. Delete memory chunks
    source_file = f"documents/{doc['filename']}"
    sb.table("memory_chunks") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("source_file", source_file) \
        .execute()

    # 3. Delete DB row
    sb.table("documents").delete().eq("id", document_id).execute()
