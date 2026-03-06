from __future__ import annotations

import json

from tools.registry import ToolRegistry


def test_execute_handles_unknown_and_invalid_json():
    registry = ToolRegistry()

    assert json.loads(registry.execute("missing", {}))["error"].startswith("Unknown tool")
    assert json.loads(registry.execute("missing", "{bad"))["error"].startswith("Unknown tool")


def test_execute_returns_string_or_json_and_maps_exceptions():
    registry = ToolRegistry()

    @registry.register(
        name="echo",
        description="Echo value",
        parameters={"type": "object"},
    )
    def _echo(value: str):
        return {"value": value}

    @registry.register(
        name="stringer",
        description="Return a string",
        parameters={"type": "object"},
    )
    def _stringer():
        return "ok"

    @registry.register(
        name="broken",
        description="Raise error",
        parameters={"type": "object"},
    )
    def _broken():
        raise RuntimeError("boom")

    assert json.loads(registry.execute("echo", {"value": "x"})) == {"value": "x"}
    assert registry.execute("stringer", {}) == "ok"
    assert json.loads(registry.execute("broken", {}))["error"] == "boom"


def test_catalog_and_openai_tool_shapes_include_approval_flag():
    registry = ToolRegistry()

    @registry.register(
        name="needs_approval",
        description="Important tool",
        parameters={"type": "object"},
        label="Important",
        category="finance",
        requires_approval=True,
    )
    def _tool():
        return {}

    catalog = registry.to_catalog()
    openai_tools = registry.to_openai_tools()

    assert catalog == [
        {
            "name": "needs_approval",
            "label": "Important",
            "description": "Important tool",
            "category": "finance",
            "requires_approval": True,
        }
    ]
    assert openai_tools[0]["function"]["name"] == "needs_approval"
    assert registry.needs_approval("needs_approval") is True
