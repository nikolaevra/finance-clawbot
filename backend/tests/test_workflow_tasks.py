from __future__ import annotations

import types

import tasks.workflow_tasks as workflow_tasks
from tests.fakes import FakeSupabase


def _base_run(status: str = "pending"):
    return {
        "id": "run-1",
        "user_id": "user-1",
        "status": status,
        "started_at": "2026-03-06T12:00:00+00:00",
        "current_step_index": 0,
        "input_args": {"x": 1},
        "steps_state": [{"id": "step-1", "status": "pending", "result": None, "started_at": None, "completed_at": None}],
        "workflow_templates": {
            "name": "memory_consolidation",
            "steps": [{"id": "step-1", "name": "First", "task": "fake.module.task"}],
        },
    }


def test_summarize_and_preview_helpers():
    summary = workflow_tasks._summarize_result({"suggestions": [1, 2], "count": 2})
    assert summary == "2 category suggestions generated"

    preview = workflow_tasks._approval_preview(
        [{"id": "s1", "result": {"anomalies": [{"id": "a1"}], "count": 1}}],
        1,
    )
    assert preview is not None
    assert preview["items"][0]["step"] == "s1"


def test_call_step_task_imports_dotted_function(monkeypatch):
    mod = types.ModuleType("fake.module")
    mod.task = lambda user_id, payload: {"ok": True, "user_id": user_id, "payload": payload}
    monkeypatch.setitem(__import__("sys").modules, "fake.module", mod)

    out = workflow_tasks._call_step_task("fake.module.task", "user-1", {"a": 1})
    assert out["ok"] is True
    assert out["payload"] == {"a": 1}


def test_execute_workflow_pauses_for_approval(monkeypatch):
    run = _base_run("running")
    run["workflow_templates"]["steps"][0]["approval"] = {"required": True, "prompt": "Approve?"}
    fake = FakeSupabase({"workflow_runs": [run]})

    published = []
    monkeypatch.setattr(workflow_tasks, "get_supabase", lambda: fake)
    monkeypatch.setattr(workflow_tasks, "publish_event", lambda _uid, event: published.append(event))
    monkeypatch.setattr(workflow_tasks, "_generate_resume_token", lambda: "token-123")

    res = workflow_tasks.execute_workflow.run("run-1")
    assert res["status"] == "paused"
    assert res["resume_token"] == "token-123"
    assert any(event["type"] == "approval_gate" for event in published)


def test_execute_workflow_marks_failure_on_step_exception(monkeypatch):
    run = _base_run("running")
    fake = FakeSupabase({"workflow_runs": [run]})

    published = []
    monkeypatch.setattr(workflow_tasks, "get_supabase", lambda: fake)
    monkeypatch.setattr(workflow_tasks, "publish_event", lambda _uid, event: published.append(event))
    monkeypatch.setattr(
        workflow_tasks,
        "_call_step_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("step failed")),
    )

    res = workflow_tasks.execute_workflow.run("run-1")
    assert res["status"] == "failed"
    assert any(event["type"] == "step_failed" for event in published)
