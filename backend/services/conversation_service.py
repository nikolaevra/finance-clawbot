"""Conversation helpers for live and background agent sessions."""
from __future__ import annotations

from services.supabase_service import get_supabase


def create_background_conversation(
    *,
    user_id: str,
    agent_name: str,
    agent_source: str,
    agent_run_id: str | None = None,
    title: str | None = None,
) -> str:
    """Create a conversation row tagged for background agent execution."""
    sb = get_supabase()
    row = (
        sb.table("conversations")
        .insert({
            "user_id": user_id,
            "title": title or f"Background: {agent_name}",
            "conversation_type": "background",
            "agent_mode": "background",
            "agent_source": agent_source,
            "agent_run_id": agent_run_id,
            "agent_name": agent_name,
        })
        .execute()
    )
    return row.data[0]["id"]
