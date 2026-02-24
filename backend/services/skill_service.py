"""Skill service — manages user-editable skills stored in Supabase Storage.

Skills are markdown files (SKILL.md) with YAML frontmatter for metadata.
The DB ``skills`` table is a lightweight metadata index for fast listing;
the actual content lives in Supabase Storage under
``skills/{user_id}/{skill_name}/SKILL.md``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import frontmatter

from services.supabase_service import get_supabase

log = logging.getLogger(__name__)

STORAGE_BUCKET = "skills"
MAX_SKILLS_IN_PROMPT = 50
MAX_SKILLS_PROMPT_CHARS = 15_000

_bucket_ready = False


def _ensure_bucket() -> None:
    """Lazily create the skills Storage bucket if it doesn't exist."""
    global _bucket_ready
    if _bucket_ready:
        return
    sb = get_supabase()
    try:
        sb.storage.get_bucket(STORAGE_BUCKET)
    except Exception:
        sb.storage.create_bucket(
            STORAGE_BUCKET,
            options={"public": False},
        )
    _bucket_ready = True


def _storage():
    """Return a storage client scoped to the skills bucket."""
    _ensure_bucket()
    return get_supabase().storage.from_(STORAGE_BUCKET)


def _storage_path(user_id: str, skill_name: str) -> str:
    return f"{user_id}/{skill_name}/SKILL.md"


def _parse_frontmatter(raw: str) -> dict[str, Any]:
    """Parse YAML frontmatter from raw markdown. Returns metadata dict."""
    try:
        post = frontmatter.loads(raw)
        return dict(post.metadata)
    except Exception:
        return {}


# ── CRUD ──────────────────────────────────────────────────────────────


def list_skills(user_id: str) -> list[dict]:
    """Return skill metadata rows from the DB for fast listing."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select("id, name, description, enabled, created_at, updated_at")
        .eq("user_id", user_id)
        .order("name")
        .execute()
    )
    return result.data or []


def get_skill(user_id: str, skill_name: str) -> str | None:
    """Read the raw SKILL.md content from Storage. Returns None if missing."""
    path = _storage_path(user_id, skill_name)
    try:
        data = _storage().download(path)
        return data.decode("utf-8") if isinstance(data, bytes) else data
    except Exception:
        log.debug("Skill not found in storage: %s", path)
        return None


def save_skill(user_id: str, skill_name: str, content: str) -> dict:
    """Create or update a skill. Writes content to Storage and upserts metadata."""
    meta = _parse_frontmatter(content)
    description = meta.get("description", "")
    enabled = meta.get("enabled", True)

    sb = get_supabase()
    path = _storage_path(user_id, skill_name)
    store = _storage()

    content_bytes = content.encode("utf-8")
    try:
        store.update(
            path, content_bytes, {"content-type": "text/markdown"}
        )
    except Exception:
        store.upload(
            path, content_bytes, {"content-type": "text/markdown"}
        )

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id": user_id,
        "name": skill_name,
        "description": description,
        "enabled": bool(enabled),
        "updated_at": now,
    }
    result = (
        sb.table("skills")
        .upsert(row, on_conflict="user_id,name")
        .execute()
    )
    return result.data[0] if result.data else row


def delete_skill(user_id: str, skill_name: str) -> bool:
    """Delete a skill from both Storage and the metadata table."""
    sb = get_supabase()
    path = _storage_path(user_id, skill_name)

    try:
        _storage().remove([path])
    except Exception:
        log.warning("Failed to remove skill file from storage: %s", path)

    sb.table("skills").delete().eq("user_id", user_id).eq("name", skill_name).execute()
    return True


def toggle_skill(user_id: str, skill_name: str, enabled: bool) -> dict | None:
    """Toggle a skill's enabled state and sync to the SKILL.md frontmatter."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .update({"enabled": enabled, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("user_id", user_id)
        .eq("name", skill_name)
        .execute()
    )
    if not result.data:
        return None

    raw = get_skill(user_id, skill_name)
    if raw:
        try:
            post = frontmatter.loads(raw)
            post.metadata["enabled"] = enabled
            updated_content = frontmatter.dumps(post)
            path = _storage_path(user_id, skill_name)
            _storage().update(
                path,
                updated_content.encode("utf-8"),
                {"content-type": "text/markdown"},
            )
        except Exception:
            log.warning("Failed to sync enabled flag to SKILL.md for %s", skill_name)

    return result.data[0]


# ── Prompt injection ──────────────────────────────────────────────────


def load_skills_for_prompt(user_id: str) -> str | None:
    """Build the compact skills list for system prompt injection.

    Returns an XML-formatted block listing enabled skills with their
    name and description, or None if no skills are available.
    """
    skills = list_skills(user_id)
    enabled = [s for s in skills if s.get("enabled", True)]

    if not enabled:
        return None

    entries: list[str] = []
    total_chars = 0

    for s in enabled[:MAX_SKILLS_IN_PROMPT]:
        name = s["name"]
        desc = s.get("description") or ""
        entry = f'  <skill name="{name}">{desc}</skill>'
        if total_chars + len(entry) > MAX_SKILLS_PROMPT_CHARS:
            break
        entries.append(entry)
        total_chars += len(entry)

    if not entries:
        return None

    return "<skills>\n" + "\n".join(entries) + "\n</skills>"
