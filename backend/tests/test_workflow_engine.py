from __future__ import annotations

import types

import pytest

import services.workflow_engine as workflow_engine
from tests.fakes import FakeSupabase


def _patch_execute_delay(monkeypatch):
    delay_calls: list[str] = []

    class _Task:
        @staticmethod
        def delay(run_id):
            delay_calls.append(run_id)
            return types.SimpleNamespace(id="celery-task-1")

    mod = types.ModuleType("tasks.workflow_tasks")
    mod.execute_workflow = _Task()
    monkeypatch.setitem(__import__("sys").modules, "tasks.workflow_tasks", mod)
    return delay_calls


def test_helper_resolve_step_input_and_condition():
    steps = [{"id": "review", "result": {"approved": True}}, {"id": "fetch", "result": "ok"}]

    assert workflow_engine._resolve_step_input({"input_from": "$args"}, steps, {"x": 1}) == {"x": 1}
    assert workflow_engine._resolve_step_input({"input_from": "$fetch"}, steps, {}) == "ok"
    assert workflow_engine._resolve_step_input({"args": {"direct": True}}, steps, {"ignored": 1}) == {"direct": True}
    assert workflow_engine._resolve_step_input({"input_from": "$missing"}, steps, {}) is None

    assert workflow_engine._evaluate_condition("$review.approved", steps) is True
    assert workflow_engine._evaluate_condition("$review.denied", steps) is False
    assert workflow_engine._evaluate_condition("bad-format", steps) is True


def test_start_resume_and_cancel_workflow(monkeypatch):
    fake = FakeSupabase(
        {
            "workflow_templates": [
                {
                    "id": "tpl-1",
                    "name": "memory_consolidation",
                    "steps": [{"id": "fetch"}, {"id": "review", "approval": {"required": True}}],
                    "is_active": True,
                }
            ],
            "workflow_runs": [],
        }
    )
    monkeypatch.setattr(workflow_engine, "get_supabase", lambda: fake)
    delay_calls = _patch_execute_delay(monkeypatch)

    run = workflow_engine.start_workflow("tpl-1", "user-1", args={"limit": 5})
    assert run["status"] == "running"
    assert run["steps_state"][0]["id"] == "fetch"
    assert delay_calls == [run["id"]]

    fake.tables["workflow_runs"][0]["status"] = "paused"
    fake.tables["workflow_runs"][0]["current_step_index"] = 0

    resumed = workflow_engine.resume_workflow(run["id"], approve=True, comment="looks good")
    assert resumed["status"] == "running"
    assert resumed["current_step_index"] == 1
    assert resumed["steps_state"][0]["status"] == "approved"

    cancelled = workflow_engine.cancel_workflow(run["id"])
    assert cancelled["status"] == "cancelled"


def test_resume_rejects_paused_run_and_missing_run(monkeypatch):
    fake = FakeSupabase({"workflow_runs": []})
    monkeypatch.setattr(workflow_engine, "get_supabase", lambda: fake)

    with pytest.raises(ValueError, match="not found"):
        workflow_engine.resume_workflow("missing")
