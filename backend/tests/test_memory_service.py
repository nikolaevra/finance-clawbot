from __future__ import annotations

from datetime import date

import services.memory_service as memory_service


def _setup_storage(monkeypatch, fake_supabase):
    monkeypatch.setattr(memory_service, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(memory_service.Config, "MEMORY_BUCKET", "memory-test")
    memory_service._bucket_ready = False
    return fake_supabase.storage.from_("memory-test")


def test_ensure_daily_append_and_session_context(monkeypatch, fake_supabase):
    storage = _setup_storage(monkeypatch, fake_supabase)

    path = memory_service.ensure_daily_file("user-1")
    assert path.startswith("user-1/daily/")

    updated = memory_service.append_daily_log("user-1", "hello world")
    assert "hello world" in updated

    yesterday = date.today().replace(day=max(1, date.today().day - 1))
    storage.upload(
        f"user-1/daily/{yesterday.isoformat()}.md",
        b"# yesterday\n\nnotes",
        {"content-type": "text/markdown"},
    )
    context = memory_service.get_session_context("user-1")
    assert "[Today" in context


def test_bootstrap_file_roundtrip_and_limits(monkeypatch, fake_supabase):
    _setup_storage(monkeypatch, fake_supabase)

    memory_service.save_bootstrap_file("user-1", "SOUL.md", "soul")
    assert memory_service.get_bootstrap_file("user-1", "SOUL.md") == "soul"
    assert memory_service.delete_bootstrap_file("user-1", "SOUL.md") is True
    assert memory_service.delete_bootstrap_file("user-1", "BAD.md") is False

    memory_service.save_bootstrap_file("user-1", "SOUL.md", "a" * 25_000)
    payload = memory_service.load_bootstrap_files("user-1")
    assert len(payload) <= 80_000
