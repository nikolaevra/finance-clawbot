"""Skill tools for OpenAI function calling.

These tools let the agent discover and read user-defined skills at
runtime.  Skills are loaded into the system prompt as a compact list
(name + description); the agent uses ``skill_read`` to fetch the full
instructions only when a skill is activated.
"""
from __future__ import annotations

from flask import g

from tools.registry import tool_registry
from services import skill_service


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
