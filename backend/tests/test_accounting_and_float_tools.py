from __future__ import annotations

from flask import g

import tools.accounting_tools as accounting_tools
import tools.float_tools as float_tools
from tests.fakes import FakeSupabase


def _seed_integrations(fake_supabase: FakeSupabase):
    fake_supabase.tables["integrations"] = [
        {
            "id": "int-1",
            "user_id": "user-1",
            "provider": "quickbooks",
            "integration_name": "QuickBooks Online",
            "account_token": "acct-token",
            "status": "active",
            "created_at": "2026-03-06T00:00:00Z",
        },
        {
            "id": "int-2",
            "user_id": "user-1",
            "provider": "float",
            "integration_name": "Float",
            "account_token": "float-token",
            "status": "active",
            "created_at": "2026-03-06T00:00:00Z",
        },
    ]


def test_accounting_tools_paths(monkeypatch, fake_supabase, request_context):
    _seed_integrations(fake_supabase)
    g.user_id = "user-1"

    monkeypatch.setattr(accounting_tools, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(
        accounting_tools,
        "fetch_accounts",
        lambda _token: [
            {"name": "Cash", "classification": "asset", "type": "bank", "current_balance": 1000}
        ],
    )
    monkeypatch.setattr(
        accounting_tools,
        "fetch_transactions",
        lambda _token, modified_after=None: [
            {"transaction_date": "2026-03-06", "total_amount": 25, "memo": "Coffee", "account": "Cash"}
        ],
    )
    monkeypatch.setattr(
        accounting_tools,
        "create_bill",
        lambda *_args, **_kwargs: {"model": {"id": "bill-1", "remote_id": "remote-1", "line_items": [{"x": 1}]}}
    )

    accounts = accounting_tools.accounting_list_accounts("asset")
    assert accounts["total_accounts"] == 1

    tx = accounting_tools.accounting_search_transactions(search="coffee")
    assert tx["total_results"] == 1

    bill = accounting_tools.accounting_create_bill("vendor-1", [{"description": "Services", "total_amount": 25}])
    assert bill["status"] == "created"
    assert bill["bill_id"] == "bill-1"


def test_float_tools_transformers(monkeypatch, fake_supabase, request_context):
    _seed_integrations(fake_supabase)
    g.user_id = "user-1"
    monkeypatch.setattr(float_tools, "get_supabase", lambda: fake_supabase)

    assert float_tools._cents_to_dollars(1234) == 12.34
    assert float_tools._cents_to_dollars(None) is None

    monkeypatch.setattr(
        float_tools.float_service,
        "fetch_account_transactions",
        lambda *_args, **_kwargs: [{"id": "a1", "total": {"value": 2300, "currency": "USD"}}],
    )
    monkeypatch.setattr(
        float_tools.float_service,
        "fetch_bill_payments",
        lambda *_args, **_kwargs: [{"id": "p1", "amount": {"value": 5000, "currency": "USD"}}],
    )

    acct = float_tools.float_account_transactions()
    assert acct["transactions"][0]["amount"] == 23.0

    payments = float_tools.float_bill_payments()
    assert payments["payments"][0]["amount"] == 50.0
