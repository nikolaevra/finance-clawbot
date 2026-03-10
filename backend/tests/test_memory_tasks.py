from __future__ import annotations

import logging

import pytest

import tasks.memory_tasks as memory_tasks


def test_consolidate_memories_logs_openai_failure(monkeypatch, caplog):
    monkeypatch.setattr(memory_tasks, "get_daily_log", lambda _u, _d: "daily note")
    monkeypatch.setattr(memory_tasks, "get_long_term_memory", lambda _u: "existing memory")
    monkeypatch.setattr(memory_tasks.Config, "OPENAI_MODEL", "test-model")

    class _OpenAI:
        class chat:
            class completions:
                @staticmethod
                def create(*_args, **_kwargs):
                    raise RuntimeError("boom")

    monkeypatch.setattr(memory_tasks, "get_openai", lambda: _OpenAI())

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            memory_tasks.consolidate_memories("user-1", {"days": 1})

    assert "memory_consolidation_openai_failed user=user-1 model=test-model" in caplog.text
