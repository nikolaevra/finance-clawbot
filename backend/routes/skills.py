"""Skills and Tools API routes.

Provides CRUD for user-editable skills (markdown files) and a
read-only tool catalog endpoint.
"""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

from middleware.auth import require_auth
from services import skill_service
from tools.registry import tool_registry

skills_bp = Blueprint("skills", __name__)

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


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
    return jsonify({"name": name, "content": content})


@skills_bp.route("/skills", methods=["POST"])
@require_auth
def create_skill():
    """Create a new skill."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    content = body.get("content", "").strip()

    error = _validate_skill_name(name)
    if error:
        return jsonify({"error": error}), 400

    if not content:
        return jsonify({"error": "Skill content is required."}), 400

    existing = skill_service.get_skill(g.user_id, name)
    if existing is not None:
        return jsonify({"error": f"Skill '{name}' already exists. Use PUT to update."}), 409

    row = skill_service.save_skill(g.user_id, name, content)
    return jsonify(row), 201


@skills_bp.route("/skills/<name>", methods=["PUT"])
@require_auth
def update_skill(name: str):
    """Update an existing skill's content."""
    body = request.get_json(silent=True) or {}
    content = body.get("content", "").strip()

    if not content:
        return jsonify({"error": "Skill content is required."}), 400

    row = skill_service.save_skill(g.user_id, name, content)
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
