"""Float tools for OpenAI function calling.

These tools give the AI assistant the ability to fetch live data from
the Float Financial API — card transactions, account transactions,
bill payments, reimbursements, users, and active cards.

Each tool resolves the user's Float API token from the ``integrations``
table before calling the underlying service.
"""
from __future__ import annotations

import logging

from flask import g

from tools.registry import tool_registry
from services.supabase_service import get_supabase
from services import float_service

log = logging.getLogger(__name__)


def _get_float_token() -> str | None:
    """Return the Float API token for the current user, or None."""
    user_id = getattr(g, "user_id", None)
    try:
        sb = get_supabase()
        result = (
            sb.table("integrations")
            .select("account_token")
            .eq("user_id", user_id)
            .eq("provider", "float")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["account_token"]
    except Exception:
        log.exception("float token lookup failed user=%s", user_id)
    return None


_NO_FLOAT = {
    "error": (
        "No active Float integration found. The user needs to connect "
        "Float first via the Integrations page."
    ),
}

_MAX_ITEMS = 200
_MAX_PAGE_SIZE = 1000


def _cents_to_dollars(cents: int | None) -> float | None:
    if cents is None:
        return None
    return round(cents / 100, 2)


# ── float_card_transactions ──────────────────────────────────────


@tool_registry.register(
    name="float_card_transactions",
    label="Float Card Transactions",
    category="float",
    description=(
        "Fetch card transactions from the user's connected Float account. "
        "Returns card transaction details (merchant, card, spender, spend "
        "compliance, accounting stage, amounts, and dates). Supports page/"
        "page_size pagination and defaults to the last 30 days when no "
        "date filters are given."
    ),
    parameters={
        "type": "object",
        "properties": {
            "created_after": {
                "type": "string",
                "description": (
                    "Only return transactions created on or after this "
                    "ISO-8601 timestamp (e.g. '2025-01-01T00:00:00Z'). "
                    "Defaults to 30 days ago."
                ),
            },
            "created_before": {
                "type": "string",
                "description": (
                    "Only return transactions created on or before this "
                    "ISO-8601 timestamp. Defaults to now."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Deprecated. Kept for backward compatibility; ignored "
                    "when page/page_size is provided."
                ),
            },
            "page": {
                "type": "integer",
                "description": "1-based result page number (default 1).",
            },
            "page_size": {
                "type": "integer",
                "description": (
                    f"Items per page (default 200, max {_MAX_PAGE_SIZE}). "
                    "Use with page to fetch >200 transactions across pages."
                ),
            },
        },
        "required": [],
    },
)
def float_card_transactions(
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict:
    token = _get_float_token()
    if not token:
        return {**_NO_FLOAT, "tool_used": "float_card_transactions"}

    page = max(page, 1)
    page_size = min(max(page_size, 1), _MAX_PAGE_SIZE)

    try:
        data = float_service.fetch_card_transactions_page(
            token,
            created_at_gte=created_after,
            created_at_lte=created_before,
            page=page,
            page_size=page_size,
        )
        items = data.get("items", [])

        if limit is not None:
            # Legacy fallback: older callers may still send limit only.
            items = items[: min(max(limit, 1), page_size)]

        results = []
        for txn in items:
            total = txn.get("total") or {}
            merchant = txn.get("merchant") or {}
            card = txn.get("card") or {}
            user = txn.get("user") or {}
            lines = txn.get("lines") or []
            first_line = lines[0] if lines else {}
            line_gl_code = (first_line.get("gl_code") or {}).get("external_id")
            results.append({
                "id": txn.get("id"),
                "type": txn.get("type"),
                "description": txn.get("description"),
                "amount": _cents_to_dollars(total.get("value")),
                "currency": total.get("currency"),
                "vendor_external_id": (txn.get("vendor") or {}).get("external_id"),
                "merchant_name": merchant.get("name"),
                "merchant_raw_name": merchant.get("raw_name"),
                "spender": user.get("email"),
                "team": (txn.get("team") or {}).get("name"),
                "card_name": card.get("name"),
                "gl_code": line_gl_code,
                "spend_compliance_status": txn.get("spend_compliance_status"),
                "accounting_stage": txn.get("accounting_stage"),
                "created_at": txn.get("created_at"),
                "updated_at": txn.get("updated_at"),
            })

        return {
            "tool_used": "float_card_transactions",
            "source": "Float API",
            "filter_created_after": data.get("created_at__gte", created_after),
            "filter_created_before": data.get("created_at__lte", created_before),
            "page": data.get("page", page),
            "page_size": data.get("page_size", page_size),
            "pages": data.get("pages"),
            "count": data.get("count"),
            "total_fetched": data.get("count", len(results)),
            "returned": len(results),
            "transactions": results,
        }
    except Exception as e:
        log.exception("float_card_transactions failed")
        return {"error": str(e), "tool_used": "float_card_transactions"}


# ── float_account_transactions ───────────────────────────────────


@tool_registry.register(
    name="float_account_transactions",
    label="Float Account Transactions",
    category="float",
    description=(
        "Fetch account-level transactions from Float (topups, cashback, "
        "fund withdrawals, billing charges, etc.). Defaults to the last "
        "30 days when no date filters are given."
    ),
    parameters={
        "type": "object",
        "properties": {
            "created_after": {
                "type": "string",
                "description": (
                    "Only return transactions created on or after this "
                    "ISO-8601 timestamp. Defaults to 30 days ago."
                ),
            },
            "created_before": {
                "type": "string",
                "description": (
                    "Only return transactions created on or before this "
                    "ISO-8601 timestamp. Defaults to now."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Max items to return (default 50, max {_MAX_ITEMS}).",
            },
        },
        "required": [],
    },
)
def float_account_transactions(
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = 50,
) -> dict:
    token = _get_float_token()
    if not token:
        return {**_NO_FLOAT, "tool_used": "float_account_transactions"}

    limit = min(max(limit, 1), _MAX_ITEMS)

    try:
        items = float_service.fetch_account_transactions(
            token, created_at_gte=created_after, created_at_lte=created_before,
        )
        truncated = items[:limit]

        results = []
        for txn in truncated:
            total = txn.get("total") or {}
            results.append({
                "id": txn.get("id"),
                "type": txn.get("type"),
                "description": txn.get("description"),
                "amount": _cents_to_dollars(total.get("value")),
                "currency": total.get("currency"),
                "spender": (txn.get("spender") or {}).get("email"),
                "team": (txn.get("team") or {}).get("name"),
                "account_type": (txn.get("account") or {}).get("type"),
                "created_at": txn.get("created_at"),
            })

        return {
            "tool_used": "float_account_transactions",
            "source": "Float API",
            "filter_created_after": created_after,
            "filter_created_before": created_before,
            "total_fetched": len(items),
            "returned": len(results),
            "transactions": results,
        }
    except Exception as e:
        log.exception("float_account_transactions failed")
        return {"error": str(e), "tool_used": "float_account_transactions"}


# ── float_bill_payments ──────────────────────────────────────────


@tool_registry.register(
    name="float_bill_payments",
    label="Float Bill Payments",
    category="float",
    description=(
        "Fetch bill payments from Float. Each payment includes status, "
        "amount, resource type (BILL or EXPENSE_REPORT), funding source, "
        "and failure reason if applicable. Optionally filter by date range."
    ),
    parameters={
        "type": "object",
        "properties": {
            "created_after": {
                "type": "string",
                "description": "ISO-8601 lower bound for creation date.",
            },
            "created_before": {
                "type": "string",
                "description": "ISO-8601 upper bound for creation date.",
            },
            "limit": {
                "type": "integer",
                "description": f"Max items to return (default 50, max {_MAX_ITEMS}).",
            },
        },
        "required": [],
    },
)
def float_bill_payments(
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = 50,
) -> dict:
    token = _get_float_token()
    if not token:
        return {**_NO_FLOAT, "tool_used": "float_bill_payments"}

    limit = min(max(limit, 1), _MAX_ITEMS)

    try:
        items = float_service.fetch_bill_payments(
            token, created_at_gte=created_after, created_at_lte=created_before,
        )
        truncated = items[:limit]

        results = []
        for p in truncated:
            amount = p.get("amount") or {}
            results.append({
                "id": p.get("id"),
                "date": p.get("date"),
                "status": p.get("status"),
                "resource_type": p.get("resource_type"),
                "resource_id": p.get("resource_id"),
                "amount": _cents_to_dollars(amount.get("value")),
                "currency": amount.get("currency"),
                "failure_reason": p.get("failure_reason"),
                "funding_source": (p.get("funding_source") or {}).get("type"),
            })

        return {
            "tool_used": "float_bill_payments",
            "source": "Float API",
            "filter_created_after": created_after,
            "filter_created_before": created_before,
            "total_fetched": len(items),
            "returned": len(results),
            "payments": results,
        }
    except Exception as e:
        log.exception("float_bill_payments failed")
        return {"error": str(e), "tool_used": "float_bill_payments"}


# ── float_reimbursements ─────────────────────────────────────────


@tool_registry.register(
    name="float_reimbursements",
    label="Float Reimbursements",
    category="float",
    description=(
        "Fetch reimbursement reports from Float. Each report includes "
        "approval state, payment status, total amount, submitter, "
        "and line-item expense details. Optionally filter by date range."
    ),
    parameters={
        "type": "object",
        "properties": {
            "created_after": {
                "type": "string",
                "description": "ISO-8601 lower bound for creation date.",
            },
            "created_before": {
                "type": "string",
                "description": "ISO-8601 upper bound for creation date.",
            },
            "limit": {
                "type": "integer",
                "description": f"Max items to return (default 50, max {_MAX_ITEMS}).",
            },
        },
        "required": [],
    },
)
def float_reimbursements(
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = 50,
) -> dict:
    token = _get_float_token()
    if not token:
        return {**_NO_FLOAT, "tool_used": "float_reimbursements"}

    limit = min(max(limit, 1), _MAX_ITEMS)

    try:
        items = float_service.fetch_reimbursements(
            token, created_at_gte=created_after, created_at_lte=created_before,
        )
        truncated = items[:limit]

        results = []
        for r in truncated:
            total = r.get("total") or {}
            submitter = r.get("submitter") or {}
            results.append({
                "id": r.get("id"),
                "title": r.get("title"),
                "approval_state": r.get("approval_state"),
                "payment_status": r.get("payment_status"),
                "amount": _cents_to_dollars(total.get("value")),
                "currency": total.get("currency"),
                "submitter_email": submitter.get("email"),
                "expense_count": len(r.get("expenses", [])),
                "created_at": r.get("created_at"),
            })

        return {
            "tool_used": "float_reimbursements",
            "source": "Float API",
            "filter_created_after": created_after,
            "filter_created_before": created_before,
            "total_fetched": len(items),
            "returned": len(results),
            "reimbursements": results,
        }
    except Exception as e:
        log.exception("float_reimbursements failed")
        return {"error": str(e), "tool_used": "float_reimbursements"}


# ── float_users ──────────────────────────────────────────────────


@tool_registry.register(
    name="float_users",
    label="Float Users",
    category="float",
    description=(
        "Fetch the list of users in the Float organization. Returns each "
        "user's name, email, role, and status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": f"Max items to return (default 100, max {_MAX_ITEMS}).",
            },
        },
        "required": [],
    },
)
def float_users(limit: int = 100) -> dict:
    token = _get_float_token()
    if not token:
        return {**_NO_FLOAT, "tool_used": "float_users"}

    limit = min(max(limit, 1), _MAX_ITEMS)

    try:
        items = float_service.fetch_users(token)
        truncated = items[:limit]

        results = []
        for u in truncated:
            results.append({
                "id": u.get("id"),
                "first_name": u.get("first_name"),
                "last_name": u.get("last_name"),
                "email": u.get("email"),
                "role": u.get("role"),
                "status": u.get("status"),
            })

        return {
            "tool_used": "float_users",
            "source": "Float API",
            "total_fetched": len(items),
            "returned": len(results),
            "users": results,
        }
    except Exception as e:
        log.exception("float_users failed")
        return {"error": str(e), "tool_used": "float_users"}


# ── float_active_cards ───────────────────────────────────────────


@tool_registry.register(
    name="float_active_cards",
    label="Float Active Cards",
    category="float",
    description=(
        "Fetch active cards from the Float organization. Returns each "
        "card's nickname, last four digits, cardholder, type (virtual/physical), "
        "spending limit, and status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": f"Max items to return (default 100, max {_MAX_ITEMS}).",
            },
        },
        "required": [],
    },
)
def float_active_cards(limit: int = 100) -> dict:
    token = _get_float_token()
    if not token:
        return {**_NO_FLOAT, "tool_used": "float_active_cards"}

    limit = min(max(limit, 1), _MAX_ITEMS)

    try:
        items = float_service.fetch_cards(token, status="ACTIVE")
        truncated = items[:limit]

        results = []
        for c in truncated:
            spend_limit = c.get("spend_limit") or {}
            holder = c.get("cardholder") or {}
            results.append({
                "id": c.get("id"),
                "nickname": c.get("nickname"),
                "last_four": c.get("last_four"),
                "card_type": c.get("type"),
                "status": c.get("status"),
                "cardholder_email": holder.get("email"),
                "cardholder_name": holder.get("name"),
                "spend_limit": _cents_to_dollars(spend_limit.get("value")),
                "spend_limit_currency": spend_limit.get("currency"),
            })

        return {
            "tool_used": "float_active_cards",
            "source": "Float API",
            "total_fetched": len(items),
            "returned": len(results),
            "cards": results,
        }
    except Exception as e:
        log.exception("float_active_cards failed")
        return {"error": str(e), "tool_used": "float_active_cards"}
