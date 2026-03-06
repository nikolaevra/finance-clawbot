"""Scheduled memory operations — daily log consolidation into MEMORY.md."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from celery_app import celery
from config import Config

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.memory_service import get_daily_log, get_long_term_memory, save_long_term_memory
from services.openai_service import get_openai


def consolidate_memories(user_id: str, input_data: dict | None = None) -> dict:
    """Summarise recent daily logs and merge into MEMORY.md.

    Workflow-compatible step function.
    """
    input_data = input_data or {}
    days_back = input_data.get("days", 7)

    today = date.today()
    logs: list[str] = []
    for i in range(1, days_back + 1):
        d = today - timedelta(days=i)
        content = get_daily_log(user_id, d)
        if content and content.strip():
            logs.append(f"## {d.isoformat()}\n{content.strip()}")

    if not logs:
        return {"message": "No recent daily logs to consolidate", "consolidated": False}

    combined = "\n\n---\n\n".join(logs)
    existing_memory = get_long_term_memory(user_id) or ""

    client = get_openai()
    response = client.chat.completions.create(
        model=Config.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a personal knowledge assistant. Given the user's recent daily "
                    "notes and their existing long-term memory, produce a concise update to "
                    "append to MEMORY.md. Focus on durable facts, decisions, preferences, "
                    "and important context. Avoid ephemeral details. Use markdown bullet points."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## Existing MEMORY.md\n{existing_memory[:3000]}\n\n"
                    f"## Recent Daily Logs\n{combined[:6000]}"
                ),
            },
        ],
        max_tokens=800,
    )

    update_text = response.choices[0].message.content.strip()
    return {
        "update": update_text,
        "logs_processed": len(logs),
        "consolidated": True,
    }


def apply_memory_consolidation(user_id: str, input_data: dict | None = None) -> dict:
    """Apply the consolidation result to MEMORY.md.

    Expects ``input_data.update`` from ``consolidate_memories``.
    """
    input_data = input_data or {}
    update_text = input_data.get("update")
    if not update_text:
        return {"applied": False, "reason": "No update text provided"}

    section = f"\n## Consolidated — {date.today().isoformat()}\n\n{update_text}"
    save_long_term_memory(user_id, section, mode="append")

    from services.embedding_service import index_memory_file
    full = get_long_term_memory(user_id) or ""
    index_memory_file(user_id, "MEMORY.md", full)

    return {"applied": True}


def save_report_to_memory(user_id: str, input_data: dict | None = None) -> dict:
    """Save a generated report to the user's daily memory log.

    Expects ``input_data.report`` from ``generate_financial_summary``.
    """
    input_data = input_data or {}
    report = input_data.get("report")
    if not report:
        return {"saved": False, "reason": "No report text provided"}

    from services.memory_service import append_daily_log, ensure_daily_file
    ensure_daily_file(user_id)

    days = input_data.get("period_days", 30)
    entry = f"## Financial Report (last {days} days)\n\n{report}"
    append_daily_log(user_id, entry)

    from services.embedding_service import index_memory_file
    from services.memory_service import get_daily_log
    from datetime import date
    today_source = f"daily/{date.today().isoformat()}.md"
    full = get_daily_log(user_id) or ""
    index_memory_file(user_id, today_source, full)

    return {"saved": True}


@celery.task(name="tasks.memory_tasks.consolidate_all_users")
def consolidate_all_users() -> dict:
    """Celery Beat entry: run memory consolidation for all users with activity."""
    sb = get_supabase()
    users = (
        sb.table("conversations")
        .select("user_id")
        .execute()
    ).data or []
    log.info("memory_consolidation_batch_start candidates=%d", len(users))

    seen = set()
    processed = 0
    for row in users:
        uid = row["user_id"]
        if uid in seen:
            continue
        seen.add(uid)
        try:
            result = consolidate_memories(uid)
            if result.get("consolidated"):
                apply_memory_consolidation(uid, result)
                processed += 1
                log.info("memory_consolidation_user_done user=%s logs=%s", uid, result.get("logs_processed"))
        except Exception:
            log.exception("memory_consolidation_user_failed user=%s", uid)

    log.info("memory_consolidation_batch_done users_processed=%d unique_users=%d", processed, len(seen))
    return {"users_processed": processed}
