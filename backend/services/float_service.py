"""
Float Financial REST API client.

Handles token validation, paginated card-transaction fetching,
and account-transaction fetching from https://api.floatfinancial.com
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

FLOAT_BASE = "https://api.floatfinancial.com"


def _headers(api_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }


def validate_token(api_token: str) -> bool:
    """Return True if *api_token* can successfully authenticate with Float."""
    try:
        resp = requests.get(
            f"{FLOAT_BASE}/v1/card-transactions",
            headers=_headers(api_token),
            params={"page_size": 1},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _fetch_all_pages(url: str, api_token: str, params: dict | None = None) -> list[dict]:
    """Paginate through Float's page-based API and collect all items."""
    results: list[dict] = []
    params = dict(params or {})
    page = 1

    while True:
        params["page"] = page
        resp = requests.get(url, headers=_headers(api_token), params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        results.extend(items)

        page_size = data.get("page_size", 1000)
        if len(items) < page_size:
            break
        page += 1

    return results


def fetch_card_transactions(
    api_token: str,
    created_at_gte: str | None = None,
) -> list[dict]:
    """Fetch all card transactions, optionally filtered by creation date."""
    params: dict[str, str] = {"page_size": "1000", "order_by": "-created_at"}
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/card-transactions", api_token, params)


def fetch_account_transactions(
    api_token: str,
    created_at_gte: str | None = None,
) -> list[dict]:
    """Fetch all account-level transactions (topups, cashback, etc.)."""
    params: dict[str, str] = {"page_size": "1000", "order_by": "-created_at"}
    if created_at_gte:
        params["created_at__gte"] = created_at_gte
    return _fetch_all_pages(f"{FLOAT_BASE}/v1/account-transactions", api_token, params)
