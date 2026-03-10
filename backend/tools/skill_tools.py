"""Skill tools for OpenAI function calling.

These tools let the agent discover and read user-defined skills at
runtime.  Skills are loaded into the system prompt as a compact list
(name + description); the agent uses ``skill_read`` to fetch the full
instructions only when a skill is activated.
"""
from __future__ import annotations

import re

from flask import g

from tools.registry import tool_registry
from services import skill_service

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


@tool_registry.register(
    name="skill_list",
    label="List Skills",
    category="skills",
    description=(
        "List all available user-defined skills with their name, "
        "description, and enabled status. Use this to discover what "
        "skills the user has configured."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def skill_list() -> dict:
    user_id = g.user_id
    skills = skill_service.list_skills(user_id)
    return {
        "tool_used": "skill_list",
        "total": len(skills),
        "skills": [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "enabled": s.get("enabled", True),
            }
            for s in skills
        ],
    }


@tool_registry.register(
    name="skill_read",
    label="Read Skill",
    category="skills",
    description=(
        "Read the full instructions (SKILL.md) of a specific skill. "
        "Use this after scanning the skills list to load the detailed "
        "instructions for a skill that matches the user's request. "
        "Follow the instructions in the skill content to fulfill "
        "the user's intent."
    ),
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "The name of the skill to read.",
            },
        },
        "required": ["skill_name"],
    },
)
def skill_read(skill_name: str) -> str:
    user_id = g.user_id
    content = skill_service.get_skill(user_id, skill_name)
    if content is None:
        return f"Skill '{skill_name}' not found. Use skill_list to see available skills."
    return content


@tool_registry.register(
    name="skill_create",
    label="Create Skill",
    category="skills",
    requires_approval=True,
    description=(
        "Create a new user skill (SKILL.md content) in the app. "
        "Use after gathering requirements and confirming the final draft "
        "with the user."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Skill slug name (lowercase letters, numbers, hyphens, "
                    "underscores; 1-63 chars)."
                ),
            },
            "content": {
                "type": "string",
                "description": "Full SKILL.md content including frontmatter.",
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether the skill is enabled after creation (default true).",
            },
            "schedule_enabled": {
                "type": "boolean",
                "description": "Enable schedule automation for this skill.",
            },
            "schedule_type": {
                "type": "string",
                "description": "Schedule type: daily or weekly (if schedule_enabled=true).",
            },
            "schedule_days": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Weekly run days (0-6, Sunday=0) when schedule_type=weekly.",
            },
            "schedule_time": {
                "type": "string",
                "description": "HH:MM (24-hour) local schedule time.",
            },
            "schedule_timezone": {
                "type": "string",
                "description": "IANA timezone, e.g. America/New_York.",
            },
            "trigger_enabled": {
                "type": "boolean",
                "description": "Enable event trigger automation.",
            },
            "trigger_provider": {
                "type": "string",
                "description": "Trigger provider (currently gmail).",
            },
            "trigger_event": {
                "type": "string",
                "description": "Trigger event (currently new_email).",
            },
            "trigger_filters": {
                "type": "object",
                "description": "Optional trigger filters object.",
            },
        },
        "required": ["name", "content"],
    },
)
def skill_create(
    name: str,
    content: str,
    enabled: bool = True,
    schedule_enabled: bool = False,
    schedule_type: str | None = None,
    schedule_days: list[int] | None = None,
    schedule_time: str | None = None,
    schedule_timezone: str | None = None,
    trigger_enabled: bool = False,
    trigger_provider: str | None = None,
    trigger_event: str | None = None,
    trigger_filters: dict | None = None,
) -> dict:
    user_id = g.user_id
    clean_name = (name or "").strip()
    if not clean_name:
        return {"tool_used": "skill_create", "error": "Skill name is required."}
    if not _SKILL_NAME_RE.match(clean_name):
        return {
            "tool_used": "skill_create",
            "error": (
                "Invalid skill name. Use lowercase letters, numbers, hyphens, "
                "and underscores (1-63 chars, must start with letter or number)."
            ),
        }

    clean_content = (content or "").strip()
    if not clean_content:
        return {"tool_used": "skill_create", "error": "Skill content is required."}

    existing = skill_service.get_skill(user_id, clean_name)
    if existing is not None:
        return {
            "tool_used": "skill_create",
            "error": f"Skill '{clean_name}' already exists. Use update via app UI.",
        }

    automation = {
        "enabled": bool(enabled),
        "schedule_enabled": bool(schedule_enabled),
        "schedule_type": schedule_type,
        "schedule_days": schedule_days,
        "schedule_time": schedule_time,
        "schedule_timezone": schedule_timezone,
        "trigger_enabled": bool(trigger_enabled),
        "trigger_provider": trigger_provider,
        "trigger_event": trigger_event,
        "trigger_filters": trigger_filters,
    }

    row = skill_service.save_skill(
        user_id=user_id,
        skill_name=clean_name,
        content=clean_content,
        automation=automation,
    )
    return {
        "tool_used": "skill_create",
        "status": "created",
        "skill": {
            "name": row.get("name", clean_name),
            "enabled": row.get("enabled", True),
            "description": row.get("description", ""),
        },
    }
