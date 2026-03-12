from __future__ import annotations

from dataclasses import dataclass

import tasks.email_sync_tasks as email_sync_tasks


@dataclass
class _Result:
    data: list[dict]


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._filters: dict[str, object] = {}
        self._mode = "select"
        self._payload: dict | None = None

    def select(self, _fields: str = "*"):
        self._mode = "select"
        return self

    def update(self, payload: dict):
        self._mode = "update"
        self._payload = payload
        return self

    def eq(self, key: str, value: object):
        self._filters[key] = value
        return self

    def limit(self, _value: int):
        return self

    def execute(self):
        matches = [
            row
            for row in self._rows
            if all(row.get(key) == value for key, value in self._filters.items())
        ]
        if self._mode == "select":
            return _Result(matches[:1])
        if self._mode == "update":
            for row in matches:
                row.update(self._payload or {})
            return _Result(matches)
        raise AssertionError(f"Unsupported mode: {self._mode}")


class _FakeSupabase:
    def __init__(self, email_threads: list[dict]) -> None:
        self._email_threads = email_threads

    def table(self, name: str):
        if name != "email_threads":
            raise AssertionError(f"Unexpected table: {name}")
        return _FakeTable(self._email_threads)


def test_summarize_thread_preview_persists_ai_summary(monkeypatch):
    fake_sb = _FakeSupabase(
        [
            {
                "user_id": "user-1",
                "integration_id": "int-1",
                "gmail_thread_id": "thread-1",
                "subject_normalized": "board update",
                "ai_summary_preview": "",
            }
        ]
    )
    monkeypatch.setattr(email_sync_tasks, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(
        email_sync_tasks,
        "_get_integration",
        lambda _sb, _integration_id: {"user_id": "user-1"},
    )
    monkeypatch.setattr(
        email_sync_tasks,
        "_fetch_thread_messages_for_summary",
        lambda *_args, **_kwargs: [{"body_text": "Need approval to proceed", "snippet": ""}],
    )
    monkeypatch.setattr(
        email_sync_tasks,
        "summarize_email_thread_preview",
        lambda **_kwargs: "AI summary text",
    )

    result = email_sync_tasks.summarize_thread_preview("int-1", "thread-1")

    assert result["status"] == "ok"
    assert result["source"] == "ai"
    assert fake_sb._email_threads[0]["ai_summary_preview"] == "AI summary text"
    assert fake_sb._email_threads[0]["ai_summary_updated_at"]


def test_summarize_thread_preview_uses_fallback_when_ai_returns_none(monkeypatch):
    fake_sb = _FakeSupabase(
        [
            {
                "user_id": "user-1",
                "integration_id": "int-1",
                "gmail_thread_id": "thread-2",
                "subject_normalized": "vendor follow up",
                "ai_summary_preview": "",
            }
        ]
    )
    monkeypatch.setattr(email_sync_tasks, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(
        email_sync_tasks,
        "_get_integration",
        lambda _sb, _integration_id: {"user_id": "user-1"},
    )
    monkeypatch.setattr(
        email_sync_tasks,
        "_fetch_thread_messages_for_summary",
        lambda *_args, **_kwargs: [{"body_text": "", "snippet": "Fallback snippet text"}],
    )
    monkeypatch.setattr(
        email_sync_tasks,
        "summarize_email_thread_preview",
        lambda **_kwargs: None,
    )

    result = email_sync_tasks.summarize_thread_preview("int-1", "thread-2")

    assert result["status"] == "ok"
    assert result["source"] == "fallback"
    assert fake_sb._email_threads[0]["ai_summary_preview"] == "Fallback snippet text"

