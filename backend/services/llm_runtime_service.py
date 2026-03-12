"""Single-model runtime service exports.

This module is the canonical import location for runtime orchestration.
"""
from services.gateway_service import (
    LLMRuntime,
    llm_runtime,
    dispatch_tool_call,
)

