"""
Accounting tools for OpenAI function calling.

These tools give the AI assistant the ability to query accounting
data (accounts with balances, transactions) from a connected
accounting system via the live Merge.dev API.
"""
from __future__ import annotations

import logging
from datetime import datetime

from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase
from services.merge_service import fetch_accounts, fetch_transactions, create_bill

log = logging.getLogger(__name__)


def _get_accounting_token() -> tuple[str | None, dict | None]:
    """Return (account_token, meta) for the user's active accounting integration."""
    user_id = getattr(g, "user_id", None)
    try:
        sb = get_supabase()
        result = (
            sb.table("integrations")
            .select("id, provider, integration_name, account_token")
            .eq("user_id", user_id)
            .in_("provider", ["quickbooks", "netsuite"])
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return row["account_token"], {
                "id": row["id"],
                "provider": row["provider"],
                "integration_name": row["integration_name"],
            }
    except Exception:
        log.exception("accounting token lookup failed user=%s", user_id)
    return None, None


_NO_INTEGRATION = {
    "error": (
        "No active accounting integration found. The user needs to connect "
        "their accounting system first via the Integrations page."
    ),
}


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
    token, meta = _get_accounting_token()
    if not token or not meta:
        return {**_NO_INTEGRATION, "tool_used": "accounting_list_accounts"}

    try:
        raw_accounts = fetch_accounts(token, user_id=g.user_id)
    except Exception as e:
        log.exception("accounting_list_accounts fetch failed")
        return {"error": str(e), "tool_used": "accounting_list_accounts"}

    accounts = []
    for a in raw_accounts:
        cls = (a.get("classification") or "").lower() or None
        if classification and cls != classification.lower():
            continue
        accounts.append({
            "name": a.get("name", ""),
            "classification": cls,
            "type": (a.get("type") or "").lower() or None,
            "current_balance": a.get("current_balance"),
            "currency": a.get("currency") or "USD",
            "status": (a.get("status") or "active").lower(),
        })

    totals: dict[str, float] = {}
    for a in accounts:
        cls = a.get("classification") or "other"
        bal = a.get("current_balance") or 0
        totals[cls] = totals.get(cls, 0) + float(bal)

    return {
        "tool_used": "accounting_list_accounts",
        "source": f"{meta['integration_name']} via Merge.dev (live)",
        "filter_applied": classification or "none",
        "total_accounts": len(accounts),
        "accounts": accounts,
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
    token, meta = _get_accounting_token()
    if not token or not meta:
        return {**_NO_INTEGRATION, "tool_used": "accounting_search_transactions"}

    limit = min(max(limit, 1), 200)

    try:
        raw_txns = fetch_transactions(token, modified_after=start_date, user_id=g.user_id)
    except Exception as e:
        log.exception("accounting_search_transactions fetch failed")
        return {"error": str(e), "tool_used": "accounting_search_transactions"}

    filtered = []
    for txn in raw_txns:
        txn_date = txn.get("transaction_date")
        if start_date and txn_date and txn_date < start_date:
            continue
        if end_date and txn_date and txn_date > end_date:
            continue

        amount = txn.get("total_amount")
        if amount is not None:
            try:
                amount_f = float(amount)
            except (ValueError, TypeError):
                amount_f = 0
            if min_amount is not None and amount_f < min_amount:
                continue
            if max_amount is not None and amount_f > max_amount:
                continue

        acct = txn.get("account") or ""
        if account_name and account_name.lower() not in str(acct).lower():
            continue

        if search:
            haystack = " ".join(str(v) for v in [
                txn.get("memo"), txn.get("description"),
                txn.get("contact"), txn.get("number"),
            ] if v).lower()
            if search.lower() not in haystack:
                continue

        contact_name = None
        contact_ref = txn.get("contact")
        if isinstance(contact_ref, dict):
            contact_name = contact_ref.get("name")
        elif isinstance(contact_ref, str) and contact_ref:
            contact_name = contact_ref

        filtered.append({
            "date": txn_date,
            "number": txn.get("number"),
            "memo": txn.get("memo") or txn.get("description"),
            "amount": amount,
            "currency": txn.get("currency") or "USD",
            "contact": contact_name,
            "account": str(acct) if acct else None,
            "type": (txn.get("transaction_type") or "").lower() or None,
            "line_items": txn.get("line_items"),
        })

    filtered.sort(key=lambda t: t.get("date") or "", reverse=True)
    truncated = filtered[:limit]

    total_sum = sum(float(t.get("amount") or 0) for t in truncated)

    return {
        "tool_used": "accounting_search_transactions",
        "source": f"{meta['integration_name']} via Merge.dev (live)",
        "filters_applied": {
            "start_date": start_date,
            "end_date": end_date,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "account_name": account_name,
            "search": search,
        },
        "total_results": len(truncated),
        "total_amount_sum": round(total_sum, 2),
        "transactions": truncated,
    }


# ── accounting_create_bill ────────────────────────────────────


@tool_registry.register(
    name="accounting_create_bill",
    label="Create Bill",
    category="accounting",
    requires_approval=True,
    description=(
        "Create a bill (accounts-payable) in the user's connected accounting "
        "system (QuickBooks Online or NetSuite). Requires a vendor, at least "
        "one line item with a description and amount, and optionally issue/due "
        "dates. Use accounting_list_accounts to look up account IDs for line "
        "items if the user wants to specify GL accounts."
    ),
    parameters={
        "type": "object",
        "properties": {
            "vendor_id": {
                "type": "string",
                "description": (
                    "The Merge remote ID of the vendor / supplier. "
                    "Use accounting_search_transactions to find vendor references."
                ),
            },
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Line item description.",
                        },
                        "total_amount": {
                            "type": "number",
                            "description": "Total amount for this line item.",
                        },
                        "account": {
                            "type": "string",
                            "description": (
                                "Optional Merge remote ID of the GL account "
                                "to post against."
                            ),
                        },
                        "quantity": {
                            "type": "number",
                            "description": "Quantity (default 1).",
                        },
                        "unit_price": {
                            "type": "number",
                            "description": "Price per unit.",
                        },
                    },
                    "required": ["description", "total_amount"],
                },
                "description": "One or more line items for the bill.",
            },
            "issue_date": {
                "type": "string",
                "description": "Bill issue date (YYYY-MM-DD). Defaults to today.",
            },
            "due_date": {
                "type": "string",
                "description": "Payment due date (YYYY-MM-DD). Optional.",
            },
            "currency": {
                "type": "string",
                "description": "Three-letter currency code (default USD).",
            },
            "memo": {
                "type": "string",
                "description": "Optional memo / notes for the bill.",
            },
        },
        "required": ["vendor_id", "line_items"],
    },
)
def accounting_create_bill(
    vendor_id: str,
    line_items: list[dict],
    issue_date: str | None = None,
    due_date: str | None = None,
    currency: str = "USD",
    memo: str | None = None,
) -> dict:
    token, meta = _get_accounting_token()
    if not token or not meta:
        return {**_NO_INTEGRATION, "tool_used": "accounting_create_bill"}

    try:
        result = create_bill(
            token,
            vendor_id=vendor_id,
            line_items=line_items,
            issue_date=issue_date,
            due_date=due_date,
            currency=currency,
            memo=memo,
            user_id=g.user_id,
        )
        model = result.get("model", {})
        return {
            "tool_used": "accounting_create_bill",
            "source": f"{meta['integration_name']} via Merge.dev",
            "status": "created",
            "bill_id": model.get("id"),
            "remote_id": model.get("remote_id"),
            "vendor": model.get("vendor"),
            "total_amount": model.get("total_amount"),
            "issue_date": model.get("issue_date"),
            "due_date": model.get("due_date"),
            "currency": model.get("currency"),
            "line_items_count": len(model.get("line_items", [])),
        }
    except Exception as e:
        log.exception("accounting_create_bill failed")
        return {"error": str(e), "tool_used": "accounting_create_bill"}
