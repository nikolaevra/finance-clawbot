"""
Float Financial REST API client.

Handles token validation, paginated card-transaction fetching,
and account-transaction fetching from https://api.floatfinancial.com
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests
from services.audit_log_service import log_external_api_call

log = logging.getLogger(__name__)

FLOAT_BASE = "https://api.floatfinancial.com"
DEFAULT_LOOKBACK_DAYS = 30


def _headers(api_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }


def _default_gte() -> str:
    """ISO-8601 timestamp for DEFAULT_LOOKBACK_DAYS ago."""
    return (datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()


def validate_token(api_token: str, user_id: str | None = None) -> bool:
    """Return True if *api_token* can successfully authenticate with Float."""
    try:
        started = time.monotonic()
        resp = requests.get(
            f"{FLOAT_BASE}/v1/card-transactions",
            headers=_headers(api_token),
            params={"page_size": 1},
            timeout=15,
        )
        ok = resp.status_code == 200
        duration_ms = (time.monotonic() - started) * 1000
        if user_id:
            log_external_api_call(
                user_id=user_id,
                service="float",
                operation="GET /v1/card-transactions",
                status="success" if ok else "error",
                duration_ms=duration_ms,
                details={"status_code": resp.status_code, "purpose": "validate_token"},
            )
        log.info("float_validate_token status=%s ok=%s duration_ms=%.0f", resp.status_code, ok, duration_ms)
        return ok
    except Exception as exc:
        if user_id:
            log_external_api_call(
                user_id=user_id,
                service="float",
                operation="GET /v1/card-transactions",
                status="error",
                duration_ms=(time.monotonic() - started) * 1000,
                error_message=str(exc),
                details={"purpose": "validate_token"},
            )
        log.exception("float_validate_token_failed")
        return False


def _fetch_all_pages(
    url: str,
    api_token: str,
    params: dict | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Paginate through Float's page-based API and collect all items.

    Float requires ``created_at__lte`` for any page > 1. We capture the
    value the API returns on page 1 and forward it automatically.
    """
    results: list[dict] = []
    params = dict(params or {})
    page = 1
    started = time.monotonic()

    try:
        while True:
            params["page"] = page
            resp = requests.get(url, headers=_headers(api_token), params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            results.extend(items)

            if page == 1 and "created_at__lte" not in params:
                lte = data.get("created_at__lte")
                if lte:
                    params["created_at__lte"] = lte

            page_size = data.get("page_size", 1000)
            if len(items) < page_size:
                break
            page += 1
    except Exception as exc:
        if user_id:
            log_external_api_call(
                user_id=user_id,
                service="float",
                operation=f"GET /{url.split('/v1/', 1)[-1]}",
                status="error",
                duration_ms=(time.monotonic() - started) * 1000,
                error_message=str(exc),
                details={"pages": page, "items": len(results)},
            )
        raise
    if user_id:
        log_external_api_call(
            user_id=user_id,
            service="float",
            operation=f"GET /{url.split('/v1/', 1)[-1]}",
            status="success",
            duration_ms=(time.monotonic() - started) * 1000,
            details={"pages": page, "items": len(results)},
        )

    log.info(
        "float_fetch_pages_done endpoint=%s pages=%d items=%d duration_ms=%.0f",
        url.rsplit("/", 1)[-1],
        page,
        len(results),
        (time.monotonic() - started) * 1000,
    )
    return results


def fetch_card_transactions_page(
    api_token: str,
    created_at_gte: str | None = None,
    created_at_lte: str | None = None,
    page: int = 1,
    page_size: int = 200,
    user_id: str | None = None,
) -> dict:
    """Fetch one page of card transactions with Float paging metadata."""
    if not created_at_gte and not created_at_lte:
        created_at_gte = _default_gte()

    params: dict[str, str | int] = {
        "page": max(page, 1),
        "page_size": max(page_size, 1),
        "order_by": "-created_at",
    }
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    if created_at_lte:
        params["created_at__lte"] = created_at_lte

    started = time.monotonic()
    try:
        resp = requests.get(
            f"{FLOAT_BASE}/v1/card-transactions",
            headers=_headers(api_token),
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
    except Exception as exc:
        if user_id:
            log_external_api_call(
                user_id=user_id,
                service="float",
                operation="GET /v1/card-transactions",
                status="error",
                duration_ms=(time.monotonic() - started) * 1000,
                error_message=str(exc),
            )
        raise
    data = resp.json() or {}
    if user_id:
        log_external_api_call(
            user_id=user_id,
            service="float",
            operation="GET /v1/card-transactions",
            status="success",
            duration_ms=(time.monotonic() - started) * 1000,
            details={"status_code": resp.status_code, "page": data.get("page", params["page"])},
        )

    return {
        "items": data.get("items") or [],
        "page": data.get("page", params["page"]),
        "page_size": data.get("page_size", params["page_size"]),
        "pages": data.get("pages"),
        "count": data.get("count"),
        "created_at__gte": data.get("created_at__gte", created_at_gte),
        "created_at__lte": data.get("created_at__lte", created_at_lte),
        "ordered_by": data.get("ordered_by", "-created_at"),
    }


def fetch_card_transactions(
    api_token: str,
    created_at_gte: str | None = None,
    created_at_lte: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Fetch card transactions. Defaults to last 30 days when no dates given."""
    params: dict[str, str] = {"page_size": "1000", "order_by": "-created_at"}
    if not created_at_gte and not created_at_lte:
        created_at_gte = _default_gte()
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    if created_at_lte:
        params["created_at__lte"] = created_at_lte
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/card-transactions", api_token, params, user_id=user_id)


def fetch_account_transactions(
    api_token: str,
    created_at_gte: str | None = None,
    created_at_lte: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Fetch account-level transactions. Defaults to last 30 days when no dates given."""
    params: dict[str, str] = {"page_size": "1000", "order_by": "-created_at"}
    if not created_at_gte and not created_at_lte:
        created_at_gte = _default_gte()
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    if created_at_lte:
        params["created_at__lte"] = created_at_lte
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/account-transactions", api_token, params, user_id=user_id)


def fetch_bill_payments(
    api_token: str,
    created_at_gte: str | None = None,
    created_at_lte: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Fetch bill payments. Defaults to last 30 days when no dates given."""
    params: dict[str, str] = {"page_size": "1000", "order_by": "-created_at"}
    if not created_at_gte and not created_at_lte:
        created_at_gte = _default_gte()
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    if created_at_lte:
        params["created_at__lte"] = created_at_lte
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/payments", api_token, params, user_id=user_id)


def fetch_reimbursements(
    api_token: str,
    created_at_gte: str | None = None,
    created_at_lte: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Fetch reimbursement reports. Defaults to last 30 days when no dates given."""
    params: dict[str, str] = {"page_size": "1000", "order_by": "-created_at"}
    if not created_at_gte and not created_at_lte:
        created_at_gte = _default_gte()
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    if created_at_lte:
        params["created_at__lte"] = created_at_lte
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/reimbursements", api_token, params, user_id=user_id)


def fetch_users(api_token: str, user_id: str | None = None) -> list[dict]:
    """Fetch all users in the Float organization."""
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/users", api_token, {"page_size": "1000"}, user_id=user_id)


def fetch_cards(api_token: str, status: str | None = None, user_id: str | None = None) -> list[dict]:
    """Fetch cards, optionally filtered by status (e.g. 'ACTIVE')."""
    params: dict[str, str] = {"page_size": "1000"}
    if status:
        params["status"] = status
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/cards", api_token, params, user_id=user_id)
