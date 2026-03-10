from __future__ import annotations

from datetime import datetime, timezone

import services.automation_trigger_service as trigger_service
import tasks.skill_automation_tasks as automation_tasks
from tests.fakes import FakeSupabase


def test_compute_schedule_run_key_daily_and_weekly():
    now_utc = datetime(2026, 3, 9, 13, 5, tzinfo=timezone.utc)  # Monday

    daily = {
        "schedule_type": "daily",
        "schedule_time": "13:05",
        "schedule_timezone": "UTC",
    }
    assert automation_tasks._compute_schedule_run_key(daily, now_utc) == "2026-03-09:13:05:daily"

    weekly_ok = {
        "schedule_type": "weekly",
        "schedule_time": "13:05",
        "schedule_timezone": "UTC",
        "schedule_days": [1],  # Monday in Sunday=0 format
    }
    assert automation_tasks._compute_schedule_run_key(weekly_ok, now_utc) == "2026-03-09:13:05:weekly"

    weekly_skip = {
        "schedule_type": "weekly",
        "schedule_time": "13:05",
        "schedule_timezone": "UTC",
        "schedule_days": [2],  # Tuesday
    }
    assert automation_tasks._compute_schedule_run_key(weekly_skip, now_utc) is None


def test_scan_scheduled_automations_enqueues_due_rows(monkeypatch):
    fake = FakeSupabase(
        {
            "skills": [
                {
                    "id": "skill-1",
                    "user_id": "user-1",
                    "name": "daily-summary",
                    "enabled": True,
                    "schedule_enabled": True,
                    "schedule_type": "daily",
                    "schedule_time": "13:05",
                    "schedule_timezone": "UTC",
                    "schedule_days": None,
                    "last_scheduled_run_key": None,
                }
            ]
        }
    )
    monkeypatch.setattr(automation_tasks, "get_supabase", lambda: fake)

    enqueued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        automation_tasks.execute_scheduled_skill_automation,
        "delay",
        lambda skill_id, run_key: enqueued.append((skill_id, run_key)),
    )
    monkeypatch.setattr(
        automation_tasks,
        "datetime",
        type(
            "FrozenDateTime",
            (),
            {"now": staticmethod(lambda _tz=None: datetime(2026, 3, 9, 13, 5, tzinfo=timezone.utc))},
        ),
    )

    out = automation_tasks.scan_scheduled_automations.run()
    assert out["enqueued"] == 1
    assert enqueued[0][0] == "skill-1"


def test_dispatch_trigger_event_matches_filters_and_enqueues(monkeypatch):
    fake = FakeSupabase(
        {
            "skills": [
                {
                    "id": "skill-1",
                    "user_id": "user-1",
                    "enabled": True,
                    "trigger_enabled": True,
                    "trigger_provider": "gmail",
                    "trigger_event": "new_email",
                    "trigger_filters": {"inbox_only": True, "subject_contains": "invoice"},
                    "last_trigger_event_key": None,
                },
                {
                    "id": "skill-2",
                    "user_id": "user-1",
                    "enabled": True,
                    "trigger_enabled": True,
                    "trigger_provider": "gmail",
                    "trigger_event": "new_email",
                    "trigger_filters": {"inbox_only": True, "subject_contains": "receipt"},
                    "last_trigger_event_key": None,
                },
            ]
        }
    )
    monkeypatch.setattr(trigger_service, "get_supabase", lambda: fake)
    enqueued: list[str] = []
    monkeypatch.setattr(
        trigger_service.execute_triggered_skill_automation,
        "delay",
        lambda skill_id, _event_id, _payload: enqueued.append(skill_id),
    )

    out = trigger_service.dispatch_trigger_event(
        provider="gmail",
        event="new_email",
        event_id="evt-1",
        payload={"is_inbox": True, "subject": "Invoice Q1"},
        user_id="user-1",
    )
    assert out["checked"] == 2
    assert enqueued == ["skill-1"]


def test_execute_triggered_skill_automation_dedup(monkeypatch):
    fake = FakeSupabase(
        {
            "skills": [
                {
                    "id": "skill-1",
                    "user_id": "user-1",
                    "name": "mail-skill",
                    "enabled": True,
                    "trigger_enabled": True,
                    "last_trigger_event_key": "evt-1",
                }
            ],
            "conversations": [{"id": "conv-1", "user_id": "user-1", "created_at": "2026-03-08T00:00:00Z"}],
        }
    )
    monkeypatch.setattr(automation_tasks, "get_supabase", lambda: fake)

    out = automation_tasks.execute_triggered_skill_automation.run(
        "skill-1", "evt-1", {"subject": "Hello"}
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "already_ran"
