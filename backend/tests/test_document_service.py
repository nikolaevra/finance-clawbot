from __future__ import annotations

import pytest

import services.document_service as document_service
import services.memory_service as memory_service
from tests.fakes import FakeSupabase


def _setup(monkeypatch, fake_supabase: FakeSupabase):
    monkeypatch.setattr(document_service, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(memory_service, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(memory_service.Config, "MEMORY_BUCKET", "memory-test")
    memory_service._bucket_ready = False


def test_file_extension_and_extract_router():
    assert document_service.get_file_extension("hello.PDF") == "pdf"
    assert document_service.get_file_extension("noext") == ""
    with pytest.raises(ValueError):
        document_service.extract_text(b"", "txt")


def test_process_document_success_and_empty_text(monkeypatch, fake_supabase):
    _setup(monkeypatch, fake_supabase)
    fake_supabase.tables["documents"] = [
        {"id": "doc-1", "filename": "report.pdf", "status": "processing"}
    ]

    monkeypatch.setattr(document_service, "download_document", lambda _path: b"content")
    monkeypatch.setattr(document_service, "extract_text", lambda _b, _t: "Extracted text")
    indexed = []
    monkeypatch.setattr(document_service, "index_memory_file", lambda *args: indexed.append(args))
    monkeypatch.setattr(document_service, "summarize_document", lambda _text, _name: "summary")
    monkeypatch.setattr(document_service, "ensure_daily_file", lambda _uid: None)
    monkeypatch.setattr(document_service, "append_daily_log", lambda _uid, _entry: "# today\nsummary")

    document_service.process_document("user-1", "doc-1", "path/report.pdf", "pdf")
    assert fake_supabase.tables["documents"][0]["status"] == "ready"
    assert indexed[0][1] == "documents/report.pdf"

    monkeypatch.setattr(document_service, "extract_text", lambda _b, _t: "   ")
    fake_supabase.tables["documents"][0]["status"] = "processing"
    document_service.process_document("user-1", "doc-1", "path/report.pdf", "pdf")
    assert fake_supabase.tables["documents"][0]["status"] == "error"


def test_delete_document_full_removes_storage_chunks_and_row(monkeypatch, fake_supabase):
    _setup(monkeypatch, fake_supabase)
    fake_supabase.tables["documents"] = [
        {
            "id": "doc-1",
            "user_id": "user-1",
            "filename": "report.pdf",
            "storage_path": "user-1/documents/x_report.pdf",
        }
    ]
    fake_supabase.tables["memory_chunks"] = [
        {"id": "chunk-1", "user_id": "user-1", "source_file": "documents/report.pdf"}
    ]
    removed = []
    monkeypatch.setattr(document_service, "delete_document_file", lambda path: removed.append(path))

    document_service.delete_document_full("user-1", "doc-1")
    assert removed == ["user-1/documents/x_report.pdf"]
    assert fake_supabase.tables["documents"] == []
    assert fake_supabase.tables["memory_chunks"] == []
