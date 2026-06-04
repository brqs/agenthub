"""Tool-calling value types and shared limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_TOOL_RESULT_MAX_CHARS = 4000
DEFAULT_TOOL_READ_MAX_BYTES = 65536


@dataclass(frozen=True, slots=True)
class OrchestratorToolResult:
    status: str
    output: str
    error_code: str | None = None
    output_truncated: bool = False
    needs_user_input: bool = False


@dataclass(frozen=True, slots=True)
class OrchestratorToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
