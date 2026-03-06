from __future__ import annotations

import json

from flask import g

import services.gateway_service as gateway_service


def test_parse_args_and_describe_tool():
    assert gateway_service._parse_args('{"a":1}') == {"a": 1}
    assert gateway_service._parse_args("{bad") == {}

    dispatch, complete = gateway_service._describe_tool(
        "workflow_run", {"workflow_name": "memory_consolidation"}
    )
    assert "Memory Consolidation" in dispatch
    assert "background worker" in complete(None)


def test_collect_tool_sources_includes_memory_document_and_integrations():
    all_sources = []
    seen = set()

    gateway_service.Gateway._collect_tool_sources(
        "document_read",
        {"filename": "report.pdf"},
        "{}",
        all_sources,
        seen,
    )
    gateway_service.Gateway._collect_tool_sources(
        "memory_search",
        {},
        json.dumps({"results": [{"source_file": "daily/2026-03-06.md"}]}),
        all_sources,
        seen,
    )
    gateway_service.Gateway._collect_tool_sources(
        "gmail_list_messages",
        {},
        "{}",
        all_sources,
        seen,
    )

    assert {"source_file": "documents/report.pdf", "score": 1.0} in all_sources
    assert {"source_file": "daily/2026-03-06.md", "score": 1.0} in all_sources
    assert {"source_file": "gmail/integration", "score": 1.0} in all_sources


def test_dispatch_tool_call_publishes_events(monkeypatch, request_context):
    published = []
    monkeypatch.setattr(gateway_service, "publish_event", lambda _uid, event: published.append(event))

    class _Registry:
        @staticmethod
        def execute(name, args):
            assert name == "memory_read"
            assert args == '{"date":"2026-03-06"}'
            return '{"ok":true}'

    monkeypatch.setattr(gateway_service, "tool_registry", _Registry())
    g.conversation_id = "conv-1"

    out = gateway_service.Gateway().dispatch_tool_call(
        "memory_read", '{"date":"2026-03-06"}', "user-1", "conv-1"
    )
    assert out == '{"ok":true}'
    assert published[0]["type"] == "tool_dispatch"
    assert published[1]["type"] == "tool_complete"


def test_build_workflow_context_and_events(monkeypatch):
    monkeypatch.setattr(
        gateway_service,
        "get_pending_approvals",
        lambda _user: [
            {
                "id": "run-1",
                "current_step_index": 0,
                "workflow_templates": {
                    "name": "monthly_close",
                    "steps": [{"approval": {"prompt": "Approve now"}}],
                },
            }
        ],
    )
    monkeypatch.setattr(
        gateway_service,
        "get_active_workflows",
        lambda _user: [
            {
                "id": "run-2",
                "status": "running",
                "current_step_index": 2,
                "workflow_templates": {"name": "sync_books"},
            }
        ],
    )

    ctx = gateway_service.Gateway().build_workflow_context("user-1")
    assert "[Pending Workflow Approvals]" in ctx
    assert "[Running Workflows]" in ctx

    events = gateway_service.Gateway.build_workflow_events(
        {"id": "run-3", "status": "paused", "resume_token": "abc", "workflow_templates": {"name": "x", "steps": [{"approval": {"prompt": "Go?"}}]}, "current_step_index": 0}
    )
    assert events[0]["type"] == "workflow_approval_needed"
