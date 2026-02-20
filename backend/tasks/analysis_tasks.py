"""AI-powered financial analysis tasks.

These can be called as workflow steps (``user_id, input_data``) or as
standalone Celery tasks.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from celery_app import celery

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.openai_service import get_openai
from config import Config


# ---------------------------------------------------------------------------
# Workflow-compatible step functions
# ---------------------------------------------------------------------------

def categorize_transactions(user_id: str, input_data: dict | None = None) -> dict:
    """Use an LLM to suggest categories for uncategorized transactions.

    Returns ``{"suggestions": [{"transaction_id": ..., "suggested_category": ..., "reason": ...}]}``.
    """
    input_data = input_data or {}
    limit = input_data.get("limit", 50)

    sb = get_supabase()
    result = (
        sb.table("accounting_transactions")
        .select("id, transaction_date, memo, total_amount, contact_name, account_name, transaction_type")
        .eq("user_id", user_id)
        .order("transaction_date", desc=True)
        .limit(limit)
        .execute()
    )
    transactions = result.data or []
    if not transactions:
        return {"suggestions": [], "message": "No transactions found"}

    txn_text = json.dumps(transactions, default=str, indent=2)

    client = get_openai()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial analyst. For each transaction below, suggest a "
                    "category and brief reason. Return a JSON array of objects with keys: "
                    "transaction_id, suggested_category, reason. Only output valid JSON."
                ),
            },
            {"role": "user", "content": txn_text},
        ],
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    try:
        parsed = json.loads(raw)
        suggestions = parsed if isinstance(parsed, list) else parsed.get("suggestions", parsed.get("results", []))
    except json.JSONDecodeError:
        suggestions = []

    return {
        "suggestions": suggestions,
        "count": len(suggestions),
    }


def apply_categories(user_id: str, input_data: dict | None = None) -> dict:
    """Apply previously suggested categories to transactions.

    Expects ``input_data`` to contain ``suggestions`` from ``categorize_transactions``.
    """
    input_data = input_data or {}
    suggestions = input_data.get("suggestions", [])
    if not suggestions:
        return {"applied": 0}

    sb = get_supabase()
    applied = 0
    for s in suggestions:
        txn_id = s.get("transaction_id")
        category = s.get("suggested_category")
        if txn_id and category:
            sb.table("accounting_transactions").update({
                "memo": f"[{category}] " + (s.get("original_memo") or ""),
            }).eq("id", txn_id).eq("user_id", user_id).execute()
            applied += 1

    return {"applied": applied}


def detect_anomalies(user_id: str, input_data: dict | None = None) -> dict:
    """Flag transactions that look unusual based on amount or pattern.

    Returns ``{"anomalies": [...]}``.
    """
    input_data = input_data or {}
    days = input_data.get("days", 30)
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    sb = get_supabase()
    result = (
        sb.table("accounting_transactions")
        .select("id, transaction_date, memo, total_amount, contact_name, account_name, transaction_type")
        .eq("user_id", user_id)
        .gte("transaction_date", cutoff)
        .order("transaction_date", desc=True)
        .limit(200)
        .execute()
    )
    transactions = result.data or []
    if not transactions:
        return {"anomalies": [], "message": "No recent transactions"}

    amounts = [abs(float(t.get("total_amount") or 0)) for t in transactions]
    if not amounts:
        return {"anomalies": []}

    avg = sum(amounts) / len(amounts)
    std_dev = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5
    threshold = avg + 2 * std_dev

    anomalies = []
    for t in transactions:
        amount = abs(float(t.get("total_amount") or 0))
        if amount > threshold:
            anomalies.append({
                "transaction_id": t["id"],
                "date": t.get("transaction_date"),
                "amount": t.get("total_amount"),
                "memo": t.get("memo"),
                "contact": t.get("contact_name"),
                "reason": f"Amount ${amount:.2f} exceeds 2σ threshold (${threshold:.2f})",
            })

    return {
        "anomalies": anomalies,
        "count": len(anomalies),
        "avg_amount": round(avg, 2),
        "threshold": round(threshold, 2),
    }


def generate_financial_summary(user_id: str, input_data: dict | None = None) -> dict:
    """Generate a structured financial report using AI."""
    input_data = input_data or {}
    days = input_data.get("days", 30)
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    sb = get_supabase()

    accounts = (
        sb.table("accounting_accounts")
        .select("name, classification, type, current_balance, currency")
        .eq("user_id", user_id)
        .execute()
    ).data or []

    transactions = (
        sb.table("accounting_transactions")
        .select("transaction_date, memo, total_amount, contact_name, account_name, transaction_type")
        .eq("user_id", user_id)
        .gte("transaction_date", cutoff)
        .order("transaction_date", desc=True)
        .limit(300)
        .execute()
    ).data or []

    if not accounts and not transactions:
        return {"report": "No financial data available.", "period_days": days}

    data_block = json.dumps({
        "accounts": accounts[:50],
        "recent_transactions": transactions[:100],
        "period": f"Last {days} days (since {cutoff})",
    }, default=str, indent=2)

    client = get_openai()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial analyst. Given the accounts and recent transactions, "
                    "produce a concise financial summary including: overview, key metrics, "
                    "notable trends, and recommendations. Use markdown formatting."
                ),
            },
            {"role": "user", "content": data_block},
        ],
        max_tokens=1500,
    )

    report = response.choices[0].message.content.strip()
    return {"report": report, "period_days": days, "accounts_count": len(accounts), "transactions_count": len(transactions)}


# ---------------------------------------------------------------------------
# Celery Beat wrappers
# ---------------------------------------------------------------------------

@celery.task(name="tasks.analysis_tasks.run_anomaly_detection_all")
def run_anomaly_detection_all() -> dict:
    """Run anomaly detection for all users with active integrations."""
    sb = get_supabase()
    users = (
        sb.table("integrations")
        .select("user_id")
        .eq("status", "active")
        .execute()
    ).data or []

    seen = set()
    results = []
    for row in users:
        uid = row["user_id"]
        if uid in seen:
            continue
        seen.add(uid)
        try:
            result = detect_anomalies(uid)
            results.append({"user_id": uid, "anomalies": result.get("count", 0)})
        except Exception:
            results.append({"user_id": uid, "error": True})

    return {"users_processed": len(results), "results": results}
