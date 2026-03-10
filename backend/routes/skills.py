"""Skills and Tools API routes.

Provides CRUD for user-editable skills (markdown files) and a
read-only tool catalog endpoint.
"""
from __future__ import annotations

import re
from typing import Any

from flask import Blueprint, g, jsonify, request

from middleware.auth import require_auth
from services import skill_service
from tools.registry import tool_registry

skills_bp = Blueprint("skills", __name__)

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_AT_TOOL_RE = re.compile(r"(?<![A-Za-z0-9_])@([a-z][a-z0-9_]*)")
_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def _validate_skill_name(name: str) -> str | None:
    """Return an error message if the skill name is invalid, else None."""
    if not name:
        return "Skill name is required."
    if not _SKILL_NAME_RE.match(name):
        return (
            "Invalid skill name. Use lowercase letters, numbers, hyphens, "
            "and underscores (1-63 chars, must start with letter or number)."
        )
    return None


def _resolve_tool_mentions(content: str) -> str:
    """Resolve @tool mentions to canonical tool names when known."""

    def _replace(match: re.Match[str]) -> str:
        tool_name = match.group(1)
        return tool_name if tool_registry.get_tool(tool_name) else match.group(0)

    return _AT_TOOL_RE.sub(_replace, content)


def _validate_automation(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Validate schedule/trigger fields and return normalized payload."""
    out: dict[str, Any] = {}

    if "enabled" in body:
        out["enabled"] = bool(body.get("enabled"))

    if "schedule_enabled" in body:
        out["schedule_enabled"] = bool(body.get("schedule_enabled"))
    schedule_enabled = out.get("schedule_enabled", False)
    if schedule_enabled:
        schedule_type = body.get("schedule_type")
        if schedule_type not in ("daily", "weekly"):
            return {}, "schedule_type must be 'daily' or 'weekly' when schedule_enabled=true."
        schedule_time = (body.get("schedule_time") or "").strip()
        if not _TIME_RE.match(schedule_time):
            return {}, "schedule_time must be HH:MM in 24-hour format."
        schedule_timezone = (body.get("schedule_timezone") or "").strip()
        if not schedule_timezone:
            return {}, "schedule_timezone is required when schedule_enabled=true."

        out["schedule_type"] = schedule_type
        out["schedule_time"] = schedule_time
        out["schedule_timezone"] = schedule_timezone
        if schedule_type == "weekly":
            days = body.get("schedule_days")
            if not isinstance(days, list) or not days:
                return {}, "schedule_days is required for weekly schedules."
            if any(not isinstance(day, int) or day < 0 or day > 6 for day in days):
                return {}, "schedule_days must be integers in range 0-6."
            out["schedule_days"] = sorted(list(set(days)))
        else:
            out["schedule_days"] = None
    elif "schedule_enabled" in body and not schedule_enabled:
        out["schedule_type"] = None
        out["schedule_days"] = None
        out["schedule_time"] = None
        out["schedule_timezone"] = None

    if "trigger_enabled" in body:
        out["trigger_enabled"] = bool(body.get("trigger_enabled"))
    trigger_enabled = out.get("trigger_enabled", False)
    if trigger_enabled:
        provider = body.get("trigger_provider")
        event = body.get("trigger_event")
        if provider != "gmail":
            return {}, "trigger_provider must be 'gmail' when trigger_enabled=true."
        if event != "new_email":
            return {}, "trigger_event must be 'new_email' when trigger_enabled=true."
        filters = body.get("trigger_filters") or {}
        if not isinstance(filters, dict):
            return {}, "trigger_filters must be an object."
        inbox_only = filters.get("inbox_only", True)
        from_contains = filters.get("from_contains")
        subject_contains = filters.get("subject_contains")
        if not isinstance(inbox_only, bool):
            return {}, "trigger_filters.inbox_only must be boolean."
        if from_contains is not None and not isinstance(from_contains, str):
            return {}, "trigger_filters.from_contains must be a string when provided."
        if subject_contains is not None and not isinstance(subject_contains, str):
            return {}, "trigger_filters.subject_contains must be a string when provided."

        out["trigger_provider"] = "gmail"
        out["trigger_event"] = "new_email"
        out["trigger_filters"] = {
            "inbox_only": inbox_only,
            "from_contains": (from_contains or "").strip() or None,
            "subject_contains": (subject_contains or "").strip() or None,
        }
    elif "trigger_enabled" in body and not trigger_enabled:
        out["trigger_provider"] = None
        out["trigger_event"] = None
        out["trigger_filters"] = None

    return out, None


# ── Tool catalog (read-only) ─────────────────────────────────────────


@skills_bp.route("/tools", methods=["GET"])
@require_auth
def list_tools():
    """Return the read-only tool catalog."""
    return jsonify(tool_registry.to_catalog())


# ── Skills CRUD ──────────────────────────────────────────────────────


@skills_bp.route("/skills", methods=["GET"])
@require_auth
def list_skills():
    """List all skills for the current user."""
    skills = skill_service.list_skills(g.user_id)
    return jsonify(skills)


@skills_bp.route("/skills/<name>", methods=["GET"])
@require_auth
def get_skill(name: str):
    """Get the full raw markdown content of a skill."""
    content = skill_service.get_skill(g.user_id, name)
    if content is None:
        return jsonify({"error": f"Skill '{name}' not found."}), 404
    row = skill_service.get_skill_record(g.user_id, name) or {}
    return jsonify({"name": name, "content": content, **row})


@skills_bp.route("/skills", methods=["POST"])
@require_auth
def create_skill():
    """Create a new skill."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    content = _resolve_tool_mentions(body.get("content", "")).strip()

    error = _validate_skill_name(name)
    if error:
        return jsonify({"error": error}), 400

    if not content:
        return jsonify({"error": "Skill content is required."}), 400

    automation, automation_error = _validate_automation(body)
    if automation_error:
        return jsonify({"error": automation_error}), 400

    existing = skill_service.get_skill(g.user_id, name)
    if existing is not None:
        return jsonify({"error": f"Skill '{name}' already exists. Use PUT to update."}), 409

    row = skill_service.save_skill(g.user_id, name, content, automation)
    return jsonify(row), 201


@skills_bp.route("/skills/<name>", methods=["PUT"])
@require_auth
def update_skill(name: str):
    """Update an existing skill's content."""
    body = request.get_json(silent=True) or {}
    content = _resolve_tool_mentions(body.get("content", "")).strip()
    new_name = (body.get("new_name") or "").strip()

    if not content:
        return jsonify({"error": "Skill content is required."}), 400

    if new_name:
        name_error = _validate_skill_name(new_name)
        if name_error:
            return jsonify({"error": name_error}), 400
        if new_name != name:
            existing = skill_service.get_skill_record(g.user_id, new_name)
            if existing is not None:
                return jsonify({"error": f"Skill '{new_name}' already exists."}), 409

    automation, automation_error = _validate_automation(body)
    if automation_error:
        return jsonify({"error": automation_error}), 400

    row = skill_service.save_skill(g.user_id, name, content, automation)
    if new_name and new_name != name:
        try:
            renamed = skill_service.rename_skill(g.user_id, name, new_name)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        if renamed is None:
            return jsonify({"error": f"Skill '{name}' not found."}), 404
        row = renamed
    return jsonify(row)


@skills_bp.route("/skills/<name>", methods=["DELETE"])
@require_auth
def delete_skill(name: str):
    """Delete a skill."""
    skill_service.delete_skill(g.user_id, name)
    return "", 204


@skills_bp.route("/skills/<name>/toggle", methods=["POST"])
@require_auth
def toggle_skill(name: str):
    """Toggle a skill's enabled state."""
    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled", True)
    row = skill_service.toggle_skill(g.user_id, name, bool(enabled))
    if row is None:
        return jsonify({"error": f"Skill '{name}' not found."}), 404
    return jsonify(row)
