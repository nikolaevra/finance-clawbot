from __future__ import annotations

import logging

import tasks.gmail_watch_tasks as gmail_watch_tasks
from tests.fakes import FakeSupabase


def test_refresh_all_gmail_watches_skips_without_topic(monkeypatch):
    monkeypatch.setattr(gmail_watch_tasks.Config, "GMAIL_WATCH_TOPIC", "")
    out = gmail_watch_tasks.refresh_all_gmail_watches.run()
    assert out["status"] == "skipped"
    assert out["reason"] == "missing_topic"


def test_refresh_all_gmail_watches_updates_history_and_email(monkeypatch):
    fake = FakeSupabase(
        {
            "integrations": [
                {
                    "id": "int-1",
                    "user_id": "user-1",
                    "provider": "gmail",
                    "status": "active",
                    "account_token": '{"token":"x"}',
                    "gmail_email": "",
                    "gmail_history_id": "",
                }
            ]
        }
    )
    monkeypatch.setattr(gmail_watch_tasks.Config, "GMAIL_WATCH_TOPIC", "projects/p/topics/t")
    monkeypatch.setattr(gmail_watch_tasks, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        gmail_watch_tasks,
        "register_inbox_watch",
        lambda _creds, _topic: {"historyId": "12345", "expiration": "999"},
    )
    monkeypatch.setattr(
        gmail_watch_tasks,
        "get_profile",
        lambda _creds: {"emailAddress": "user@example.com", "historyId": "12345"},
    )

    out = gmail_watch_tasks.refresh_all_gmail_watches.run()

    assert out["status"] == "ok"
    assert out["total"] == 1
    assert out["renewed"] == 1
    updated = fake.tables["integrations"][0]
    assert updated["gmail_history_id"] == "12345"
    assert updated["gmail_email"] == "user@example.com"


def test_refresh_all_gmail_watches_emits_success_logs(monkeypatch, caplog):
    fake = FakeSupabase(
        {
            "integrations": [
                {
                    "id": "int-1",
                    "user_id": "user-1",
                    "provider": "gmail",
                    "status": "active",
                    "account_token": '{"token":"x"}',
                    "gmail_email": "user@example.com",
                    "gmail_history_id": "old",
                }
            ]
        }
    )
    monkeypatch.setattr(gmail_watch_tasks.Config, "GMAIL_WATCH_TOPIC", "projects/p/topics/t")
    monkeypatch.setattr(gmail_watch_tasks, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        gmail_watch_tasks,
        "register_inbox_watch",
        lambda _creds, _topic: {"historyId": "new-history", "expiration": "123456789"},
    )

    with caplog.at_level(logging.INFO):
        out = gmail_watch_tasks.refresh_all_gmail_watches.run()

    assert out["renewed"] == 1
    text = caplog.text
    assert "gmail_watch_refresh_start" in text
    assert "gmail_watch_refresh_attempt integration_id=int-1" in text
    assert "gmail_watch_refresh_success integration_id=int-1" in text
    assert "gmail_watch_refresh_complete total=1 renewed=1 failed=0" in text


def test_refresh_all_gmail_watches_emits_failure_log(monkeypatch, caplog):
    fake = FakeSupabase(
        {
            "integrations": [
                {
                    "id": "int-1",
                    "user_id": "user-1",
                    "provider": "gmail",
                    "status": "active",
                    "account_token": '{"token":"x"}',
                    "gmail_email": "user@example.com",
                    "gmail_history_id": "old",
                }
            ]
        }
    )
    monkeypatch.setattr(gmail_watch_tasks.Config, "GMAIL_WATCH_TOPIC", "projects/p/topics/t")
    monkeypatch.setattr(gmail_watch_tasks, "get_supabase", lambda: fake)

    def _raise(_creds, _topic):
        raise RuntimeError("boom")

    monkeypatch.setattr(gmail_watch_tasks, "register_inbox_watch", _raise)

    with caplog.at_level(logging.INFO):
        out = gmail_watch_tasks.refresh_all_gmail_watches.run()

    assert out["failed"] == 1
    text = caplog.text
    assert "gmail_watch_refresh_attempt integration_id=int-1" in text
    assert "gmail_watch_refresh_failed integration_id=int-1 user_id=user-1" in text
    assert "gmail_watch_refresh_complete total=1 renewed=0 failed=1" in text
