from __future__ import annotations

import json

from flask import g

import services.gateway_service as gateway_service


def test_parse_args_and_describe_tool():
    assert gateway_service._parse_args('{"a":1}') == {"a": 1}
    assert gateway_service._parse_args("{bad") == {}

    dispatch, complete = gateway_service._describe_tool(
        "memory_read", {"date": "2026-03-06"}
    )
    assert "Reading memory file" in dispatch
    assert "Memory file retrieved" in complete(None)


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


def test_runtime_aliases_exist():
    assert gateway_service.gateway is gateway_service.llm_runtime
    assert gateway_service.Gateway is gateway_service.LLMRuntime
