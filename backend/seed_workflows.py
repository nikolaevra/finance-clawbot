"""Seed built-in workflow templates into the database.

Run once after applying migration 008:
    python seed_workflows.py

Templates with user_id=NULL are system-wide and visible to all users.
"""
from __future__ import annotations

import json
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from services.supabase_service import get_supabase

TEMPLATES = [
    {
        "name": "memory_consolidation",
        "description": "Consolidate recent daily notes into long-term memory (MEMORY.md).",
        "schedule": "0 0 * * *",
        "steps": [
            {
                "id": "consolidate",
                "name": "Summarize recent daily logs",
                "task": "tasks.memory_tasks.consolidate_memories",
                "args": {"days": 7},
                "timeout_seconds": 120,
            },
            {
                "id": "review",
                "name": "Review consolidation",
                "approval": {
                    "required": True,
                    "prompt": "Review the memory consolidation summary. Approve to update MEMORY.md.",
                },
            },
            {
                "id": "apply",
                "name": "Update MEMORY.md",
                "task": "tasks.memory_tasks.apply_memory_consolidation",
                "input_from": "$consolidate",
                "condition": "$review.approved",
                "timeout_seconds": 30,
            },
        ],
    },
]


def seed():
    sb = get_supabase()
    allowed_template_names = {tpl["name"] for tpl in TEMPLATES}

    # Keep only the supported system templates.
    existing_system_templates = (
        sb.table("workflow_templates")
        .select("id, name")
        .is_("user_id", "null")
        .execute()
    ).data or []
    for existing in existing_system_templates:
        if existing["name"] not in allowed_template_names:
            sb.table("workflow_templates").delete().eq("id", existing["id"]).execute()
            print(f"  Deleted: {existing['name']}")

    for tpl in TEMPLATES:
        existing = (
            sb.table("workflow_templates")
            .select("id")
            .eq("name", tpl["name"])
            .is_("user_id", "null")
            .execute()
        )

        row = {
            "user_id": None,
            "name": tpl["name"],
            "description": tpl["description"],
            "steps": tpl["steps"],
            "schedule": tpl.get("schedule"),
            "is_active": True,
        }

        if existing.data:
            sb.table("workflow_templates").update(row).eq("id", existing.data[0]["id"]).execute()
            print(f"  Updated: {tpl['name']}")
        else:
            sb.table("workflow_templates").insert(row).execute()
            print(f"  Created: {tpl['name']}")


if __name__ == "__main__":
    print("Seeding workflow templates...")
    seed()
    print("Done.")
