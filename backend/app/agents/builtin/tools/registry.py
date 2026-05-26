"""Builtin native tool registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.builtin.tools.bash import run_bash
from app.agents.builtin.tools.exceptions import ToolExecutionError
from app.agents.builtin.tools.workspace_tools import read_file, write_file
from app.agents.types import ToolSpec

TOOLS: dict[str, ToolSpec] = {
    "read_file": ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file from the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to workspace root",
                },
            },
            "required": ["path"],
        },
    ),
    "write_file": ToolSpec(
        name="write_file",
        description="Write or overwrite a UTF-8 text file in the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    "bash": ToolSpec(
        name="bash",
        description="Run a whitelisted command in the workspace.",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    ),
}


class ToolRegistry:
    """Registry and dispatcher for native BuiltinAgent tools."""

    def tool_specs(self, allowed: list[ToolSpec] | None = None) -> list[ToolSpec]:
        if allowed is None:
            return list(TOOLS.values())

        allowed_names = {tool.name for tool in allowed}
        return [tool for name, tool in TOOLS.items() if name in allowed_names]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        workspace_path: Path,
        config: dict[str, Any],
    ) -> str:
        if tool_name == "read_file":
            return await read_file(workspace_path, _str_arg(arguments, "path"))
        if tool_name == "write_file":
            return await write_file(
                workspace_path,
                _str_arg(arguments, "path"),
                _str_arg(arguments, "content"),
            )
        if tool_name == "bash":
            return await run_bash(
                workspace_path,
                _str_arg(arguments, "command"),
                timeout_seconds=_float_config(config, "bash_timeout_seconds", 30.0),
            )
        raise ToolExecutionError(f"unknown tool: {tool_name}")


def _str_arg(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        raise ToolExecutionError(f"missing or invalid argument: {key}")
    return value


def _float_config(config: dict[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0.1, float(value))
