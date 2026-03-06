from __future__ import annotations

import services.embedding_service as embedding_service


def test_split_chunks_and_long_text():
    text = (
        "First paragraph.\n\n"
        + ("This is a long sentence. " * 120)
        + "\n\nThird paragraph."
    )
    chunks = embedding_service._split_into_chunks(text)
    assert chunks
    assert all(isinstance(chunk, str) for chunk in chunks)
    assert all(len(chunk) > 0 for chunk in chunks)

    long_chunks = embedding_service._split_long_text("Sentence. " * 1000)
    assert long_chunks
    assert all(len(chunk) <= 2000 for chunk in long_chunks)


def test_index_file_and_hybrid_search(monkeypatch, fake_supabase):
    monkeypatch.setattr(embedding_service, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(embedding_service, "generate_embedding", lambda _t: [0.1, 0.2, 0.3])

    embedding_service.index_memory_file("user-1", "daily/2026-03-06.md", "alpha\n\nbeta")
    rows = fake_supabase.tables["memory_chunks"]
    assert len(rows) >= 1
    assert rows[0]["user_id"] == "user-1"

    fake_supabase.rpc_result = [{"source_file": "daily/2026-03-06.md", "chunk_text": "alpha", "score": 0.9}]
    out = embedding_service.hybrid_search("user-1", "alpha", limit=3)
    assert out[0]["score"] == 0.9
    assert fake_supabase.rpc_calls[0][0] == "hybrid_memory_search"
