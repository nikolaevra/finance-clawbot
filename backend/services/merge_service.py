"""
Merge.dev REST API client for accounting integrations.

Handles link-token creation, public→account token exchange,
and paginated fetching of accounts / transactions.
"""
from __future__ import annotations

import requests
from config import Config

MERGE_BASE = "https://api.merge.dev/api"
ACCOUNTING_V1 = f"{MERGE_BASE}/accounting/v1"


def _headers(account_token: str | None = None) -> dict[str, str]:
    """Standard headers for all Merge.dev requests."""
    h: dict[str, str] = {
        "Authorization": f"Bearer {Config.MERGE_API_KEY}",
        "Content-Type": "application/json",
    }
    if account_token:
        h["X-Account-Token"] = account_token
    return h


# ── Link token ────────────────────────────────────────────────

def create_link_token(
    user_id: str,
    organization_name: str = "My Organization",
    user_email: str = "user@example.com",
    integration_slug: str | None = None,
) -> dict:
    """
    Create a Merge Link token so the frontend can open the
    Link modal for the end-user.

    If *integration_slug* is provided (e.g. ``"quickbooks-online"`` or
    ``"netsuite"``), Merge Link will skip the provider picker and go
    straight to that integration's configuration form.

    Returns the full JSON response which includes ``link_token``.
    """
    body: dict = {
        "end_user_origin_id": user_id,
        "end_user_organization_name": organization_name,
        "end_user_email_address": user_email,
        "categories": ["accounting"],
        "link_expiry_mins": 60,
    }
    if integration_slug:
        body["integration"] = integration_slug

    resp = requests.post(
        f"{ACCOUNTING_V1}/link-token",
        headers=_headers(),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ── Token exchange ────────────────────────────────────────────

def exchange_public_token(public_token: str) -> dict:
    """
    Exchange the public_token returned by Merge Link for a
    permanent account_token.

    Returns ``{"account_token": "...", "integration": {...}}``.
    """
    resp = requests.get(
        f"{ACCOUNTING_V1}/account-token/{public_token}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ── Paginated helpers ─────────────────────────────────────────

def _fetch_all_pages(url: str, account_token: str, params: dict | None = None) -> list[dict]:
    """Generic paginated GET that follows ``next`` cursors."""
    results: list[dict] = []
    params = dict(params or {})
    # Merge uses cursor-based pagination
    while url:
        resp = requests.get(url, headers=_headers(account_token), params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        url = data.get("next")  # full URL or None
        params = {}  # params are baked into the ``next`` URL
    return results


# ── Accounts ──────────────────────────────────────────────────

def fetch_accounts(account_token: str) -> list[dict]:
    """Fetch all accounts (chart of accounts) from the linked integration."""
    return _fetch_all_pages(f"{ACCOUNTING_V1}/accounts", account_token)


# ── Transactions ──────────────────────────────────────────────

def fetch_transactions(
    account_token: str,
    modified_after: str | None = None,
) -> list[dict]:
    """
    Fetch transactions from the linked integration.

    ``modified_after`` is an ISO-8601 timestamp for incremental sync.
    """
    params: dict[str, str] = {}
    if modified_after:
        params["modified_after"] = modified_after
    return _fetch_all_pages(f"{ACCOUNTING_V1}/transactions", account_token, params)


# ── Disconnect ────────────────────────────────────────────────

def delete_account(account_token: str) -> bool:
    """
    Tell Merge to delete the linked account, revoking the
    account_token.  Returns True on success.
    """
    try:
        resp = requests.post(
            f"{ACCOUNTING_V1}/delete-account",
            headers=_headers(account_token),
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False
