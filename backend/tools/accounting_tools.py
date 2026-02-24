"""
Accounting tools for OpenAI function calling.

These tools give the AI assistant the ability to query accounting
data (accounts with balances, transactions) that has been imported
from a connected accounting system via Merge.dev.
"""
from __future__ import annotations

import json
from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase


def _get_integration_meta() -> dict | None:
    """Return the user's active integration metadata (provider, last sync)."""
    try:
        sb = get_supabase()
        result = (
            sb.table("integrations")
            .select("id, provider, integration_name, last_sync_at")
            .eq("user_id", g.user_id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
    except Exception:
        pass
    return None


def _log_accounting_access(tool_name: str) -> None:
    """Best-effort insert into memory_access_log for accounting tool usage."""
    try:
        conversation_id = getattr(g, "conversation_id", None)
        if not conversation_id:
            return
        sb = get_supabase()
        sb.table("memory_access_log").insert({
            "user_id": g.user_id,
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "source_file": "accounting/integration",
        }).execute()
    except Exception:
        pass


# ── accounting_list_accounts ──────────────────────────────────

@tool_registry.register(
    name="accounting_list_accounts",
    label="List Accounts",
    category="accounting",
    description=(
        "List all accounts with current balances from the user's connected "
        "accounting system (e.g. QuickBooks Online). Shows account name, "
        "type, classification (asset/liability/equity/revenue/expense), "
        "and current balance. Optionally filter by classification."
    ),
    parameters={
        "type": "object",
        "properties": {
            "classification": {
                "type": "string",
                "description": (
                    "Optional filter: one of 'asset', 'liability', 'equity', "
                    "'revenue', 'expense'. Leave empty for all accounts."
                ),
            },
        },
        "required": [],
    },
)
def accounting_list_accounts(classification: str | None = None) -> dict:
    user_id = g.user_id
    _log_accounting_access("accounting_list_accounts")

    meta = _get_integration_meta()
    if not meta:
        return {
            "error": "No active accounting integration found. The user needs to connect their accounting system first via the Integrations page.",
            "tool_used": "accounting_list_accounts",
        }

    sb = get_supabase()
    query = (
        sb.table("accounting_accounts")
        .select("name, description, classification, type, status, current_balance, currency")
        .eq("user_id", user_id)
        .eq("integration_id", meta["id"])
    )

    if classification:
        query = query.eq("classification", classification.lower())

    query = query.order("classification").order("name")
    result = query.execute()

    accounts = result.data or []

    # Compute summary totals by classification
    totals: dict[str, float] = {}
    for a in accounts:
        cls = a.get("classification") or "other"
        bal = a.get("current_balance") or 0
        totals[cls] = totals.get(cls, 0) + float(bal)

    return {
        "tool_used": "accounting_list_accounts",
        "source": f"{meta['integration_name']} via Merge.dev",
        "last_synced": meta.get("last_sync_at"),
        "filter_applied": classification or "none",
        "total_accounts": len(accounts),
        "accounts": [
            {
                "name": a["name"],
                "classification": a.get("classification"),
                "type": a.get("type"),
                "current_balance": a.get("current_balance"),
                "currency": a.get("currency", "USD"),
                "status": a.get("status"),
            }
            for a in accounts
        ],
        "summary_by_classification": totals,
    }


# ── accounting_search_transactions ────────────────────────────

@tool_registry.register(
    name="accounting_search_transactions",
    label="Search Transactions",
    category="accounting",
    description=(
        "Search transactions from the user's connected accounting system "
        "(e.g. QuickBooks Online). Filter by date range, minimum/maximum "
        "amount, account name, or keyword in memo/contact name. Returns "
        "matching transactions with dates, amounts, and descriptions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Start date (YYYY-MM-DD) for the date range filter.",
            },
            "end_date": {
                "type": "string",
                "description": "End date (YYYY-MM-DD) for the date range filter.",
            },
            "min_amount": {
                "type": "number",
                "description": "Minimum transaction amount (absolute value).",
            },
            "max_amount": {
                "type": "number",
                "description": "Maximum transaction amount (absolute value).",
            },
            "account_name": {
                "type": "string",
                "description": "Filter by account name (partial match, case-insensitive).",
            },
            "search": {
                "type": "string",
                "description": "Keyword search in memo, contact name, or transaction number.",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of transactions to return. Default 50, max 200.",
            },
        },
        "required": [],
    },
)
def accounting_search_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    account_name: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> dict:
    user_id = g.user_id
    _log_accounting_access("accounting_search_transactions")

    meta = _get_integration_meta()
    if not meta:
        return {
            "error": "No active accounting integration found. The user needs to connect their accounting system first via the Integrations page.",
            "tool_used": "accounting_search_transactions",
        }

    limit = min(max(limit, 1), 200)

    sb = get_supabase()
    query = (
        sb.table("accounting_transactions")
        .select("transaction_date, number, memo, total_amount, currency, contact_name, account_name, transaction_type, line_items")
        .eq("user_id", user_id)
        .eq("integration_id", meta["id"])
    )

    # Apply filters
    if start_date:
        query = query.gte("transaction_date", start_date)
    if end_date:
        query = query.lte("transaction_date", end_date)
    if min_amount is not None:
        query = query.gte("total_amount", min_amount)
    if max_amount is not None:
        query = query.lte("total_amount", max_amount)
    if account_name:
        query = query.ilike("account_name", f"%{account_name}%")
    if search:
        # Search across memo, contact_name, and number
        query = query.or_(
            f"memo.ilike.%{search}%,"
            f"contact_name.ilike.%{search}%,"
            f"number.ilike.%{search}%"
        )

    query = query.order("transaction_date", desc=True).limit(limit)
    result = query.execute()

    transactions = result.data or []

    # Compute summary
    total_sum = sum(float(t.get("total_amount") or 0) for t in transactions)

    return {
        "tool_used": "accounting_search_transactions",
        "source": f"{meta['integration_name']} via Merge.dev",
        "last_synced": meta.get("last_sync_at"),
        "filters_applied": {
            "start_date": start_date,
            "end_date": end_date,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "account_name": account_name,
            "search": search,
        },
        "total_results": len(transactions),
        "total_amount_sum": round(total_sum, 2),
        "transactions": [
            {
                "date": t.get("transaction_date"),
                "number": t.get("number"),
                "memo": t.get("memo"),
                "amount": t.get("total_amount"),
                "currency": t.get("currency", "USD"),
                "contact": t.get("contact_name"),
                "account": t.get("account_name"),
                "type": t.get("transaction_type"),
                "line_items": t.get("line_items"),
            }
            for t in transactions
        ],
    }
