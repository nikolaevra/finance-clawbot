"""
Embedding service: reactive indexing and hybrid search.

This module is ONLY called when a memory file has actually changed on disk
(i.e. after a confirmed write via memory_service).  Normal conversation
turns never trigger anything here.

Responsibilities:
- Generate embeddings via OpenAI text-embedding-3-small
- Chunk memory file content and upsert into memory_chunks table
- Execute hybrid search (keyword + semantic) via the database RPC
"""
from __future__ import annotations

import re
from services.supabase_service import get_supabase
from config import Config

# ── Embedding generation ─────────────────────────────────────────────

def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text via OpenAI."""
    # Lazy import to avoid circular dependency:
    # openai_service → tools.registry → tools/__init__ → memory_tools → embedding_service
    from services.openai_service import get_openai

    client = get_openai()
    response = client.embeddings.create(
        model=Config.OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


# ── Chunking ─────────────────────────────────────────────────────────

_MAX_CHUNK_CHARS = 2000   # ~500 tokens at ~4 chars/token
_MIN_CHUNK_CHARS = 100


def _split_into_chunks(content: str) -> list[str]:
    """
    Split content into chunks of roughly ~500 tokens each.

    Strategy:
    1. Split on paragraph boundaries (double newline).
    2. Merge adjacent small paragraphs up to _MAX_CHUNK_CHARS.
    3. Split oversized paragraphs on sentence boundaries.
    """
    paragraphs = re.split(r"\n{2,}", content.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # If adding this paragraph would exceed the max, flush current
        if current and len(current) + len(para) + 2 > _MAX_CHUNK_CHARS:
            chunks.append(current.strip())
            current = ""

        # If a single paragraph is oversized, split it on sentences
        if len(para) > _MAX_CHUNK_CHARS:
            if current:
                chunks.append(current.strip())
                current = ""
            for sentence_chunk in _split_long_text(para):
                chunks.append(sentence_chunk.strip())
        else:
            current = (current + "\n\n" + para) if current else para

    if current.strip():
        chunks.append(current.strip())

    # Drop chunks that are too small to be meaningful on their own
    # (unless that's all we have)
    if len(chunks) > 1:
        chunks = [c for c in chunks if len(c) >= _MIN_CHUNK_CHARS]

    return chunks if chunks else [content.strip()] if content.strip() else []


def _split_long_text(text: str) -> list[str]:
    """Split a long text on sentence boundaries into ≤ _MAX_CHUNK_CHARS pieces."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > _MAX_CHUNK_CHARS:
            chunks.append(current.strip())
            current = ""
        current = (current + " " + sentence) if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ── Reactive indexing ────────────────────────────────────────────────

def index_memory_file(user_id: str, source_file: str, content: str) -> None:
    """
    Re-index a memory file after it has been written to Storage.

    Called ONLY after a confirmed file write.  Steps:
    1. Delete existing chunks for (user_id, source_file).
    2. Split content into chunks.
    3. Generate embeddings for each chunk.
    4. Insert new chunk rows.
    """
    sb = get_supabase()

    # 1. Delete old chunks for this file
    sb.table("memory_chunks") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("source_file", source_file) \
        .execute()

    # 2. Chunk the content
    chunks = _split_into_chunks(content)
    if not chunks:
        return

    # 3. Generate embeddings + insert
    rows = []
    for idx, chunk_text in enumerate(chunks):
        try:
            embedding = generate_embedding(chunk_text)
        except Exception:
            embedding = None

        rows.append({
            "user_id": user_id,
            "source_file": source_file,
            "chunk_text": chunk_text,
            "chunk_index": idx,
            "embedding": embedding,
        })

    # 4. Bulk insert
    if rows:
        sb.table("memory_chunks").insert(rows).execute()


# ── Hybrid search ────────────────────────────────────────────────────

def hybrid_search(user_id: str, query: str, limit: int = 10) -> list[dict]:
    """
    Execute hybrid memory search (keyword + semantic) via the database RPC.

    Returns a list of dicts with keys: source_file, chunk_text, score.
    """
    sb = get_supabase()

    # Generate query embedding
    try:
        query_embedding = generate_embedding(query)
    except Exception:
        query_embedding = [0.0] * 1536  # fallback: keyword-only search

    result = sb.rpc(
        "hybrid_memory_search",
        {
            "p_user_id": user_id,
            "p_query_text": query,
            "p_query_embedding": query_embedding,
            "p_limit": limit,
        },
    ).execute()

    return result.data or []
