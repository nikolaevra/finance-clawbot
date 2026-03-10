"""Skill service — manages user-editable skills stored in Supabase Storage.

Skills are markdown files (SKILL.md) with YAML frontmatter for metadata.
The DB ``skills`` table is a lightweight metadata index for fast listing;
the actual content lives in Supabase Storage under
``skills/{user_id}/{skill_name}/SKILL.md``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any

import frontmatter

from services.supabase_service import get_supabase

log = logging.getLogger(__name__)

STORAGE_BUCKET = "skills"
MAX_SKILLS_IN_PROMPT = 50
MAX_SKILLS_PROMPT_CHARS = 15_000
DEFAULT_ONBOARDING_SKILL_NAME = "guided-onboarding-account-setup"
AUTOMATION_FRONTMATTER_KEYS = {
    "enabled",
    "schedule_enabled",
    "schedule_type",
    "schedule_days",
    "schedule_time",
    "schedule_timezone",
    "trigger_enabled",
    "trigger_provider",
    "trigger_event",
    "trigger_filters",
}

DEFAULT_ONBOARDING_SKILL_CONTENT = dedent(
    """\
    ---
    name: guided-onboarding-account-setup
    description: Runs a guided onboarding and account-creation flow. Use when the user asks what you can do, wants onboarding, account setup, email inbox setup, Gmail automations, or accounting integration setup.
    ---

    # Guided Onboarding + Account Setup

    ## Goal
    Run a complete, step-by-step onboarding that:
    1. Explains assistant capabilities in plain language
    2. Sets up required memory files (especially USER.md and long-term memory)
    3. Verifies or guides connection of Gmail and accounting integrations
    4. Ends with a concrete "ready to use" checklist

    ## How To Run This Skill
    Follow the steps in order. Keep each step short, clear, and actionable.
    Do not skip checks even if the user sounds ready.

    ### Step 1 - Capability Overview
    - Explain what you can do:
      - Inbox management (read/summarize/draft/reply/forward with confirmation when sending)
      - Finance analysis from connected accounting systems
      - Tracking and recalling context via memory files
      - Running repeatable skills and automations
    - End this step by asking: "Want me to guide you through full setup now?"

    ### Step 2 - Identity + User Profile Memory Setup
    Your objective is to set up profile context even on day 1.

    - Ask for missing essentials:
      - preferred name
      - timezone
      - company/business name
      - role
      - primary finance priorities (for example: cash flow, expenses, invoicing)
    - Persist what you learn:
      - Use memory_save to store durable profile facts in MEMORY.md
      - Use memory_append to add today's onboarding notes to daily memory
    - If USER.md is incomplete or stale:
      - Tell the user exactly what fields should be filled in USER.md
      - Offer to generate a clean USER.md draft they can paste into the Memories editor

    ### Step 3 - Email Setup Check (Inbox + Drafting + Automations)
    - Confirm whether Gmail integration is connected.
    - If not connected, provide this setup sequence:
      1. Open Integrations page
      2. Connect Gmail
      3. Return here and say "Gmail connected"
    - After connected, explain what unlocks:
      - Manage inbox from chat
      - Draft replies quickly
      - Trigger automations when new emails arrive (for example: invoice triage, follow-up draft prep)
    - Ask whether they want an email-trigger automation configured next.

    ### Step 4 - Accounting Setup Check
    - Confirm whether an accounting integration is connected (QuickBooks / NetSuite / Float as available).
    - If not connected, provide this setup sequence:
      1. Open Integrations page
      2. Connect accounting system
      3. Return here and say "Accounting connected"
    - After connected, explain what unlocks:
      - account and transaction lookup
      - spend analysis and anomaly checks
      - bill and reporting assistance

    ### Step 5 - Completion Checklist + Next Action
    End with a checklist showing status:
    - [ ] USER profile captured
    - [ ] Memory baseline saved
    - [ ] Gmail connected
    - [ ] Accounting connected
    - [ ] First automation selected

    Then propose exactly one high-value next action based on missing items.

    ## Output Style
    - Keep guidance practical and concise.
    - Prefer numbered steps and checklists over long paragraphs.
    - Ask one setup question at a time during onboarding.
    """
)

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


def _strip_automation_frontmatter(raw: str) -> str:
    """Remove automation settings from SKILL.md frontmatter.

    Automation settings are persisted in the DB, not markdown metadata.
    """
    try:
        post = frontmatter.loads(raw)
    except Exception:
        return raw

    changed = False
    for key in AUTOMATION_FRONTMATTER_KEYS:
        if key in post.metadata:
            del post.metadata[key]
            changed = True

    return frontmatter.dumps(post) if changed else raw


# ── CRUD ──────────────────────────────────────────────────────────────


def list_skills(user_id: str) -> list[dict]:
    """Return skill metadata rows from the DB for fast listing."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select(
            "id, name, description, enabled, "
            "schedule_enabled, schedule_type, schedule_days, schedule_time, schedule_timezone, "
            "trigger_enabled, trigger_provider, trigger_event, trigger_filters, "
            "created_at, updated_at"
        )
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


def get_skill_record(user_id: str, skill_name: str) -> dict | None:
    """Return DB metadata row for a single skill."""
    sb = get_supabase()
    result = (
        sb.table("skills")
        .select(
            "id, name, description, enabled, "
            "schedule_enabled, schedule_type, schedule_days, schedule_time, schedule_timezone, "
            "trigger_enabled, trigger_provider, trigger_event, trigger_filters, "
            "created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("name", skill_name)
        .limit(1)
        .execute()
    )
    if not result or not result.data:
        return None
    if isinstance(result.data, list):
        return result.data[0] if result.data else None
    return result.data


def save_skill(
    user_id: str,
    skill_name: str,
    content: str,
    automation: dict[str, Any] | None = None,
) -> dict:
    """Create or update a skill. Stores automation in DB, content in Storage."""
    meta = _parse_frontmatter(content)
    description = meta.get("description", "")
    existing = get_skill_record(user_id, skill_name) or {}
    automation = automation or {}
    enabled = bool(automation.get("enabled", existing.get("enabled", True)))
    schedule_enabled = bool(automation.get("schedule_enabled", existing.get("schedule_enabled", False)))
    schedule_type = automation.get("schedule_type", existing.get("schedule_type"))
    schedule_days = automation.get("schedule_days", existing.get("schedule_days"))
    schedule_time = automation.get("schedule_time", existing.get("schedule_time"))
    schedule_timezone = automation.get("schedule_timezone", existing.get("schedule_timezone"))
    trigger_enabled = bool(automation.get("trigger_enabled", existing.get("trigger_enabled", False)))
    trigger_provider = automation.get("trigger_provider", existing.get("trigger_provider"))
    trigger_event = automation.get("trigger_event", existing.get("trigger_event"))
    trigger_filters = automation.get("trigger_filters", existing.get("trigger_filters"))

    sb = get_supabase()
    path = _storage_path(user_id, skill_name)
    store = _storage()

    content = _strip_automation_frontmatter(content)

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
        "schedule_enabled": schedule_enabled,
        "schedule_type": schedule_type,
        "schedule_days": schedule_days,
        "schedule_time": schedule_time,
        "schedule_timezone": schedule_timezone,
        "trigger_enabled": trigger_enabled,
        "trigger_provider": trigger_provider,
        "trigger_event": trigger_event,
        "trigger_filters": trigger_filters,
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
    """Toggle a skill's enabled state in DB metadata."""
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

    return result.data[0]


def rename_skill(user_id: str, old_name: str, new_name: str) -> dict | None:
    """Rename a skill in both storage and DB metadata."""
    if old_name == new_name:
        return get_skill_record(user_id, old_name)

    existing_new = get_skill_record(user_id, new_name)
    if existing_new is not None:
        raise ValueError(f"Skill '{new_name}' already exists.")

    existing_old = get_skill_record(user_id, old_name)
    if existing_old is None:
        return None

    old_path = _storage_path(user_id, old_name)
    new_path = _storage_path(user_id, new_name)
    store = _storage()

    raw = get_skill(user_id, old_name)
    if raw is not None:
        try:
            post = frontmatter.loads(raw)
            post.metadata["name"] = new_name
            raw = frontmatter.dumps(post)
        except Exception:
            # Keep rename non-blocking if markdown cannot be parsed.
            pass
        content_bytes = raw.encode("utf-8")
        try:
            store.update(new_path, content_bytes, {"content-type": "text/markdown"})
        except Exception:
            store.upload(new_path, content_bytes, {"content-type": "text/markdown"})
        try:
            store.remove([old_path])
        except Exception:
            log.warning("Failed to remove old skill file after rename: %s", old_path)

    sb = get_supabase()
    result = (
        sb.table("skills")
        .update({"name": new_name, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("user_id", user_id)
        .eq("name", old_name)
        .execute()
    )
    return result.data[0] if result and result.data else None


def ensure_default_onboarding_skill(user_id: str) -> None:
    """Create the default guided onboarding skill when it is missing."""
    if get_skill(user_id, DEFAULT_ONBOARDING_SKILL_NAME) is not None:
        return
    save_skill(
        user_id=user_id,
        skill_name=DEFAULT_ONBOARDING_SKILL_NAME,
        content=DEFAULT_ONBOARDING_SKILL_CONTENT,
        automation={"enabled": True},
    )


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
