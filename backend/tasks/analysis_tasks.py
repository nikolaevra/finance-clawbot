"""AI-powered financial analysis tasks.

These can be called as workflow steps (``user_id, input_data``) or as
standalone Celery tasks.

All accounting data is fetched live from the Merge.dev API rather than
from local Supabase tables.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from celery_app import celery

log = logging.getLogger(__name__)
from services.supabase_service import get_supabase
from services.merge_service import fetch_accounts, fetch_transactions
from services.openai_service import get_openai
from config import Config


def _get_accounting_token(user_id: str) -> str | None:
    """Return the Merge.dev account_token for the user's active accounting integration."""
    try:
        sb = get_supabase()
        result = (
            sb.table("integrations")
            .select("account_token")
            .eq("user_id", user_id)
            .in_("provider", ["quickbooks", "netsuite"])
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["account_token"]
    except Exception:
        log.exception("accounting token lookup failed user=%s", user_id)
    return None


def _fetch_live_transactions(user_id: str, days: int = 30, limit: int = 200) -> list[dict]:
    """Fetch transactions from the live Merge.dev API for the given user."""
    token = _get_accounting_token(user_id)
    if not token:
        return []

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    raw = fetch_transactions(token, modified_after=cutoff)

    txns = []
    for t in raw[:limit]:
        contact_name = None
        contact_ref = t.get("contact")
        if isinstance(contact_ref, dict):
            contact_name = contact_ref.get("name")
        elif isinstance(contact_ref, str) and contact_ref:
            contact_name = contact_ref

        txns.append({
            "id": t.get("id", ""),
            "transaction_date": t.get("transaction_date"),
            "memo": t.get("memo") or t.get("description"),
            "total_amount": t.get("total_amount"),
            "contact_name": contact_name,
            "account_name": str(t.get("account") or ""),
            "transaction_type": (t.get("transaction_type") or "").lower() or None,
        })

    txns.sort(key=lambda x: x.get("transaction_date") or "", reverse=True)
    return txns


# ---------------------------------------------------------------------------
# Workflow-compatible step functions
# ---------------------------------------------------------------------------

def categorize_transactions(user_id: str, input_data: dict | None = None) -> dict:
    """Use an LLM to suggest categories for recent transactions (fetched live).

    Returns ``{"suggestions": [{"transaction_id": ..., "suggested_category": ..., "reason": ...}]}``.
    """
    input_data = input_data or {}
    limit = input_data.get("limit", 50)

    transactions = _fetch_live_transactions(user_id, days=30, limit=limit)
    if not transactions:
        return {"suggestions": [], "message": "No transactions found"}

    txn_text = json.dumps(transactions, default=str, indent=2)

    client = get_openai()
    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MINI_MODEL,
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
            max_completion_tokens=2000,
            response_format={"type": "json_object"},
        )
    except Exception:
        log.exception(
            "categorize_transactions_openai_failed user=%s model=%s limit=%s",
            user_id,
            Config.OPENAI_MINI_MODEL,
            limit,
        )
        raise

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
    """Return previously suggested categories (no local storage to update)."""
    input_data = input_data or {}
    suggestions = input_data.get("suggestions", [])
    return {"applied": 0, "suggestions": suggestions, "message": "Categories are advisory only; no local data store."}


def detect_anomalies(user_id: str, input_data: dict | None = None) -> dict:
    """Flag transactions that look unusual based on amount or pattern.

    Returns ``{"anomalies": [...]}``.
    """
    input_data = input_data or {}
    days = input_data.get("days", 30)

    transactions = _fetch_live_transactions(user_id, days=days, limit=200)
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
    """Generate a structured financial report using AI with live API data."""
    input_data = input_data or {}
    days = input_data.get("days", 30)

    token = _get_accounting_token(user_id)
    if not token:
        return {"report": "No active accounting integration found.", "period_days": days}

    try:
        raw_accounts = fetch_accounts(token)
    except Exception:
        raw_accounts = []

    accounts = [
        {
            "name": a.get("name", ""),
            "classification": (a.get("classification") or "").lower(),
            "type": (a.get("type") or "").lower(),
            "current_balance": a.get("current_balance"),
            "currency": a.get("currency") or "USD",
        }
        for a in raw_accounts
    ]

    transactions = _fetch_live_transactions(user_id, days=days, limit=300)

    if not accounts and not transactions:
        return {"report": "No financial data available.", "period_days": days}

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    data_block = json.dumps({
        "accounts": accounts[:50],
        "recent_transactions": transactions[:100],
        "period": f"Last {days} days (since {cutoff})",
    }, default=str, indent=2)

    client = get_openai()
    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MINI_MODEL,
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
            max_completion_tokens=1500,
        )
    except Exception:
        log.exception(
            "financial_summary_openai_failed user=%s model=%s days=%s accounts=%s txns=%s",
            user_id,
            Config.OPENAI_MINI_MODEL,
            days,
            len(accounts),
            len(transactions),
        )
        raise

    report = response.choices[0].message.content.strip()
    return {"report": report, "period_days": days, "accounts_count": len(accounts), "transactions_count": len(transactions)}


# ---------------------------------------------------------------------------
# Celery Beat wrappers
# ---------------------------------------------------------------------------

@celery.task(name="tasks.analysis_tasks.run_anomaly_detection_all")
def run_anomaly_detection_all() -> dict:
    """Run anomaly detection for all users with active accounting integrations."""
    sb = get_supabase()
    users = (
        sb.table("integrations")
        .select("user_id")
        .eq("status", "active")
        .in_("provider", ["quickbooks", "netsuite"])
        .execute()
    ).data or []
    log.info("anomaly_detection_batch_start candidates=%d", len(users))

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
            log.info("anomaly_detection_user_done user=%s anomalies=%d", uid, result.get("count", 0))
        except Exception:
            log.exception("anomaly_detection_user_failed user=%s", uid)
            results.append({"user_id": uid, "error": True})

    log.info("anomaly_detection_batch_done users_processed=%d", len(results))
    return {"users_processed": len(results), "results": results}
