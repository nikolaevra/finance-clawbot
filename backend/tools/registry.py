"""
Extensible tool registry for OpenAI function calling.

Tools are registered as Python callables with an associated JSON Schema
describing their parameters. The registry converts them to the format
expected by the OpenAI Chat Completions API and exposes a read-only
catalog for the frontend.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    label: str = ""
    category: str = "general"
    requires_approval: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        label: str = "",
        category: str = "general",
        requires_approval: bool = False,
    ) -> Callable:
        """Decorator to register a tool function."""

        def decorator(fn: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                fn=fn,
                label=label or name.replace("_", " ").title(),
                category=category,
                requires_approval=requires_approval,
            )
            return fn

        return decorator

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def needs_approval(self, name: str) -> bool:
        """Return True if the named tool requires user approval before execution."""
        tool = self._tools.get(name)
        return tool.requires_approval if tool else False

    def execute(self, name: str, arguments: str | dict) -> str:
        """Execute a tool by name with JSON arguments. Returns a string result."""
        tool = self._tools.get(name)
        if tool is None:
            log.warning("tool_execute_unknown name=%s", name)
            return json.dumps({"error": f"Unknown tool: {name}"})

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                log.warning("tool_execute_invalid_json name=%s", name)
                return json.dumps({"error": "Invalid JSON arguments"})

        try:
            log.info("tool_execute_start name=%s", name)
            result = tool.fn(**arguments)
            if isinstance(result, str):
                log.info("tool_execute_done name=%s result_type=str", name)
                return result
            log.info("tool_execute_done name=%s result_type=json", name)
            return json.dumps(result)
        except Exception as e:
            log.exception("tool_execute_failed name=%s", name)
            return json.dumps({"error": str(e)})

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Convert registered tools to OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def to_catalog(self) -> list[dict[str, Any]]:
        """Return a read-only catalog of all registered tools for the frontend."""
        return [
            {
                "name": t.name,
                "label": t.label,
                "description": t.description,
                "category": t.category,
                "requires_approval": t.requires_approval,
            }
            for t in self._tools.values()
        ]

    @property
    def has_tools(self) -> bool:
        return len(self._tools) > 0


# Global registry instance
tool_registry = ToolRegistry()
