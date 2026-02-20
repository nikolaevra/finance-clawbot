"""
Extensible tool registry for OpenAI function calling.

Tools are registered as Python callables with an associated JSON Schema
describing their parameters. The registry converts them to the format
expected by the OpenAI Chat Completions API.

To add a new tool:
    from tools.registry import tool_registry

    @tool_registry.register(
        name="my_tool",
        description="Does something useful",
        parameters={
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "First argument"},
            },
            "required": ["arg1"],
        },
    )
    def my_tool(arg1: str) -> str:
        return f"Result for {arg1}"
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


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> Callable:
        """Decorator to register a tool function."""

        def decorator(fn: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                fn=fn,
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

    @property
    def has_tools(self) -> bool:
        return len(self._tools) > 0


# Global registry instance
tool_registry = ToolRegistry()
