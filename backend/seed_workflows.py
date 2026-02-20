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
        "name": "sync_accounting",
        "description": "Sync accounting data (accounts and transactions) from the connected accounting system via Merge.dev.",
        "schedule": "0 */6 * * *",
        "steps": [
            {
                "id": "verify",
                "name": "Verify connection",
                "task": "tasks.sync_tasks.verify_connection",
                "timeout_seconds": 30,
            },
            {
                "id": "fetch_accounts",
                "name": "Fetch accounts from Merge.dev",
                "task": "tasks.sync_tasks.fetch_merge_accounts",
                "input_from": "$verify",
                "timeout_seconds": 120,
            },
            {
                "id": "fetch_transactions",
                "name": "Fetch transactions from Merge.dev",
                "task": "tasks.sync_tasks.fetch_merge_transactions",
                "input_from": "$fetch_accounts",
                "timeout_seconds": 120,
            },
            {
                "id": "upsert",
                "name": "Upsert data into database",
                "task": "tasks.sync_tasks.upsert_accounting_data",
                "input_from": "$fetch_transactions",
                "timeout_seconds": 180,
            },
        ],
    },
    {
        "name": "categorize_transactions",
        "description": "Use AI to suggest categories for recent transactions, then apply after approval.",
        "steps": [
            {
                "id": "categorize",
                "name": "AI categorization",
                "task": "tasks.analysis_tasks.categorize_transactions",
                "args": {"limit": 50},
                "timeout_seconds": 120,
            },
            {
                "id": "review",
                "name": "Review suggested categories",
                "approval": {
                    "required": True,
                    "prompt": "Review the AI-suggested categories. Approve to apply them to your transactions.",
                },
            },
            {
                "id": "apply",
                "name": "Apply categories",
                "task": "tasks.analysis_tasks.apply_categories",
                "input_from": "$categorize",
                "condition": "$review.approved",
                "timeout_seconds": 60,
            },
        ],
    },
    {
        "name": "generate_financial_report",
        "description": "Generate an AI-powered financial summary report and save it to your memory.",
        "steps": [
            {
                "id": "generate",
                "name": "Generate financial summary",
                "task": "tasks.analysis_tasks.generate_financial_summary",
                "args": {"days": 30},
                "timeout_seconds": 120,
            },
            {
                "id": "review",
                "name": "Review report",
                "approval": {
                    "required": True,
                    "prompt": "Review the generated financial report. Approve to save it to your daily memory.",
                },
            },
            {
                "id": "save",
                "name": "Save report to memory",
                "task": "tasks.memory_tasks.save_report_to_memory",
                "input_from": "$generate",
                "condition": "$review.approved",
                "timeout_seconds": 30,
            },
        ],
    },
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
    {
        "name": "detect_anomalies",
        "description": "Detect unusual transactions based on statistical analysis of recent activity.",
        "schedule": "30 8 * * *",
        "steps": [
            {
                "id": "detect",
                "name": "Run anomaly detection",
                "task": "tasks.analysis_tasks.detect_anomalies",
                "args": {"days": 30},
                "timeout_seconds": 60,
            },
        ],
    },
]


def seed():
    sb = get_supabase()

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
