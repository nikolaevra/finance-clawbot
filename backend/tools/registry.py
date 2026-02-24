"""
Extensible tool registry for OpenAI function calling.

Tools are registered as Python callables with an associated JSON Schema
describing their parameters. The registry converts them to the format
expected by the OpenAI Chat Completions API and exposes a read-only
catalog for the frontend.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    label: str = ""
    category: str = "general"


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
            )
            return fn

        return decorator

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def execute(self, name: str, arguments: str | dict) -> str:
        """Execute a tool by name with JSON arguments. Returns a string result."""
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return json.dumps({"error": "Invalid JSON arguments"})

        try:
            result = tool.fn(**arguments)
            if isinstance(result, str):
                return result
            return json.dumps(result)
        except Exception as e:
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

    def to_catalog(self) -> list[dict[str, str]]:
        """Return a read-only catalog of all registered tools for the frontend."""
        return [
            {
                "name": t.name,
                "label": t.label,
                "description": t.description,
                "category": t.category,
            }
            for t in self._tools.values()
        ]

    @property
    def has_tools(self) -> bool:
        return len(self._tools) > 0


# Global registry instance
tool_registry = ToolRegistry()
