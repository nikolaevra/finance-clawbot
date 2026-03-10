from __future__ import annotations

import logging
import types

import pytest

import tasks.analysis_tasks as analysis_tasks


def test_fetch_live_transactions_normalizes_payload(monkeypatch):
    monkeypatch.setattr(analysis_tasks, "_get_accounting_token", lambda _u: "acct-token")
    monkeypatch.setattr(
        analysis_tasks,
        "fetch_transactions",
        lambda _token, modified_after=None, user_id=None: [
            {
                "id": "t1",
                "transaction_date": "2026-03-06",
                "memo": "Coffee",
                "total_amount": 12.5,
                "contact": {"name": "Cafe"},
                "account": "Card",
                "transaction_type": "DEBIT",
            }
        ],
    )

    txns = analysis_tasks._fetch_live_transactions("user-1")
    assert txns[0]["contact_name"] == "Cafe"
    assert txns[0]["transaction_type"] == "debit"


def test_detect_anomalies_uses_statistical_threshold(monkeypatch):
    monkeypatch.setattr(
        analysis_tasks,
        "_fetch_live_transactions",
        lambda _u, days=30, limit=200: [
            {"id": "a", "transaction_date": "2026-03-06", "memo": "A", "total_amount": 1},
            {"id": "b", "transaction_date": "2026-03-06", "memo": "B", "total_amount": 2},
            {"id": "c", "transaction_date": "2026-03-06", "memo": "C", "total_amount": 3},
            {"id": "d", "transaction_date": "2026-03-06", "memo": "D", "total_amount": 4},
            {"id": "e", "transaction_date": "2026-03-06", "memo": "E", "total_amount": 20},
        ],
    )
    result = analysis_tasks.detect_anomalies("user-1")
    assert "threshold" in result
    assert "avg_amount" in result
    assert result["count"] == len(result["anomalies"])


def test_categorize_and_summary_use_openai(monkeypatch):
    monkeypatch.setattr(
        analysis_tasks,
        "_fetch_live_transactions",
        lambda _u, days=30, limit=50: [{"id": "t1", "total_amount": 10, "transaction_date": "2026-03-06"}],
    )
    monkeypatch.setattr(analysis_tasks, "_get_accounting_token", lambda _u: "acct-token")
    monkeypatch.setattr(
        analysis_tasks,
        "fetch_accounts",
        lambda _token: [{"name": "Checking", "classification": "asset", "type": "bank", "current_balance": 1000}],
    )

    class _OpenAI:
        class chat:
            class completions:
                @staticmethod
                def create(*_args, **_kwargs):
                    return types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                message=types.SimpleNamespace(
                                    content='{"suggestions":[{"transaction_id":"t1","suggested_category":"Meals","reason":"memo"}]}'
                                )
                            )
                        ]
                    )

    monkeypatch.setattr(analysis_tasks, "get_openai", lambda: _OpenAI())
    monkeypatch.setattr(analysis_tasks.Config, "OPENAI_MINI_MODEL", "test-model")

    categorized = analysis_tasks.categorize_transactions("user-1", {"limit": 1})
    assert categorized["count"] == 1

    class _OpenAIReport:
        class chat:
            class completions:
                @staticmethod
                def create(*_args, **_kwargs):
                    return types.SimpleNamespace(
                        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="Financial summary"))]
                    )

    monkeypatch.setattr(analysis_tasks, "get_openai", lambda: _OpenAIReport())
    summary = analysis_tasks.generate_financial_summary("user-1", {"days": 7})
    assert "Financial summary" in summary["report"]


def test_categorize_transactions_logs_openai_failure(monkeypatch, caplog):
    monkeypatch.setattr(
        analysis_tasks,
        "_fetch_live_transactions",
        lambda _u, days=30, limit=50: [{"id": "t1", "total_amount": 10, "transaction_date": "2026-03-06"}],
    )
    monkeypatch.setattr(analysis_tasks.Config, "OPENAI_MINI_MODEL", "mini-test")

    class _OpenAI:
        class chat:
            class completions:
                @staticmethod
                def create(*_args, **_kwargs):
                    raise RuntimeError("bad request")

    monkeypatch.setattr(analysis_tasks, "get_openai", lambda: _OpenAI())

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            analysis_tasks.categorize_transactions("user-1", {"limit": 1})

    assert "categorize_transactions_openai_failed user=user-1 model=mini-test limit=1" in caplog.text
