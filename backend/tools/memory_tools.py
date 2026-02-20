"""
Memory tools for OpenAI function calling.

These four tools are the ONLY way memory changes.  Normal conversation
turns never mutate memory or the search index.  Each write tool triggers
a reactive re-index of the affected file.

Every tool invocation is logged to memory_access_log so the user can
see which conversations referenced which memory files.
"""
from __future__ import annotations

from datetime import date
from flask import g

from tools.registry import tool_registry
from services import memory_service, embedding_service
from services.supabase_service import get_supabase


def _log_access(tool_name: str, source_file: str | None = None) -> None:
    """Best-effort insert into memory_access_log. Never raises."""
    try:
        conversation_id = getattr(g, 'conversation_id', None)
        if not conversation_id:
            return
        sb = get_supabase()
        sb.table('memory_access_log').insert({
            'user_id': g.user_id,
            'conversation_id': conversation_id,
            'tool_name': tool_name,
            'source_file': source_file,
        }).execute()
    except Exception:
        pass  # logging failure should never block the tool


# ── memory_append ────────────────────────────────────────────────────

@tool_registry.register(
    name="memory_append",
    description=(
        "Append a note to today's daily memory log. Use this to persist "
        "important decisions, facts, preferences, or context that should "
        "survive beyond this conversation. Content is appended to the "
        "current day's log file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The text to append to today's daily log.",
            },
        },
        "required": ["content"],
    },
)
def memory_append(content: str) -> str:
    user_id = g.user_id
    today = date.today()
    source_file = f"daily/{today.isoformat()}.md"

    # Write to Storage (source of truth)
    updated_content = memory_service.append_daily_log(user_id, content)

    # Reactive re-index: only because the file just changed
    try:
        embedding_service.index_memory_file(user_id, source_file, updated_content)
    except Exception:
        pass  # indexing failure should not block the write confirmation

    _log_access('memory_append', source_file)
    return f"Appended to {source_file}."


# ── memory_read ──────────────────────────────────────────────────────

@tool_registry.register(
    name="memory_read",
    description=(
        "Read a daily memory log. Defaults to today's log if no date is "
        "provided. Returns the full markdown content of the log file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "The date to read in YYYY-MM-DD format. "
                    "Defaults to today if omitted."
                ),
            },
        },
        "required": [],
    },
)
def memory_read(date: str | None = None) -> str:
    from datetime import date as date_cls

    user_id = g.user_id
    if date:
        try:
            d = date_cls.fromisoformat(date)
        except ValueError:
            return f"Invalid date format: {date}. Use YYYY-MM-DD."
    else:
        d = date_cls.today()

    source_file = f"daily/{d.isoformat()}.md"
    content = memory_service.get_daily_log(user_id, d)

    _log_access('memory_read', source_file)

    if content is None:
        return f"No daily log found for {d.isoformat()}."
    return content


# ── memory_search ────────────────────────────────────────────────────

@tool_registry.register(
    name="memory_search",
    description=(
        "Search across all memory files (daily logs, MEMORY.md, and uploaded "
        "documents) using hybrid keyword + semantic search. Returns the most "
        "relevant snippets with their source file and relevance score."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return. Defaults to 10.",
            },
        },
        "required": ["query"],
    },
)
def memory_search(query: str, limit: int = 10) -> dict:
    user_id = g.user_id
    results = embedding_service.hybrid_search(user_id, query, limit)

    _log_access('memory_search', None)

    if not results:
        return {"results": [], "message": "No matching memory found."}

    return {
        "results": [
            {
                "source_file": r["source_file"],
                "content": r["chunk_text"],
                "score": round(r["score"], 4),
            }
            for r in results
        ]
    }


# ── memory_save ──────────────────────────────────────────────────────

@tool_registry.register(
    name="memory_save",
    description=(
        "Write to the long-term MEMORY.md file. Use this for curated "
        "durable facts: preferences, stable decisions, important notes "
        "that should persist indefinitely. Use mode='append' to add to "
        "the end, or mode='replace' to overwrite the entire file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The text to write to MEMORY.md.",
            },
            "mode": {
                "type": "string",
                "enum": ["append", "replace"],
                "description": (
                    "Write mode. 'append' adds to the end of MEMORY.md. "
                    "'replace' overwrites the entire file. Defaults to 'append'."
                ),
            },
        },
        "required": ["content"],
    },
)
def memory_save(content: str, mode: str = "append") -> str:
    user_id = g.user_id

    # Write to Storage (source of truth)
    updated_content = memory_service.save_long_term_memory(user_id, content, mode)

    # Reactive re-index: only because the file just changed
    try:
        embedding_service.index_memory_file(user_id, "MEMORY.md", updated_content)
    except Exception:
        pass  # indexing failure should not block the write confirmation

    _log_access('memory_save', 'MEMORY.md')

    action = "Replaced" if mode == "replace" else "Appended to"
    return f"{action} MEMORY.md."
