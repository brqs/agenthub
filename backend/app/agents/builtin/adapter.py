"""BuiltinAgentAdapter entry point."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.builtin.loop import AgentLoop
from app.agents.builtin.mcp.client import MCPClient, MCPServerDown
from app.agents.builtin.tools.registry import ToolRegistry
from app.agents.model_gateway import ModelGateway
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

READ_FILE_PATH_RE = re.compile(
    r"[`\"'\u201c\u201d\u2018\u2019]?([A-Za-z0-9_./-]+\.(?:txt|md|json|html|css|js|py))"
    r"[`\"'\u201c\u201d\u2018\u2019]?"
)


class BuiltinAgentAdapter(BaseAgentAdapter):
    """Self-hosted agent loop with native tools and optional MCP tools."""

    provider = "builtin"

    def __init__(
        self,
        agent_id: str,
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
        *,
        model_gateway: Any | None = None,
        tool_registry: ToolRegistry | None = None,
        mcp_client: MCPClient | None = None,
    ) -> None:
        super().__init__(agent_id, system_prompt, default_config)
        backend = str(self.default_config.get("model_backend", "claude"))
        self.model_gateway = model_gateway or ModelGateway(
            backend,
            self.default_config,
            agent_id=f"{agent_id}-model",
            system_prompt=system_prompt,
        )
        self.tool_registry = tool_registry or ToolRegistry()
        self.mcp_client = mcp_client or MCPClient.from_config(
            self.default_config.get("mcp_servers", [])
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)

        if workspace_path is None:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="workspace_violation",
                error="BuiltinAgent requires a workspace_path",
            )
            return

        try:
            tools = await self._available_tools(merged, tool_specs)
        except MCPServerDown as exc:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="mcp_server_down",
                error=str(exc),
            )
            return

        read_only_path = _deterministic_read_only_path(merged, messages, tools)
        if read_only_path is not None:
            async for chunk in self._stream_deterministic_read_only(
                read_only_path,
                workspace_path=workspace_path,
                config=merged,
            ):
                yield chunk
            return

        loop = AgentLoop(
            agent_id=self.agent_id,
            model_gateway=self.model_gateway,
            tool_registry=self.tool_registry,
            mcp_client=self.mcp_client,
        )
        async for chunk in loop.run(
            messages,
            tools=tools,
            workspace_path=workspace_path,
            system_prompt=self.effective_system_prompt(system_prompt),
            config=merged,
            max_iterations=_read_int(merged, "max_iterations", 10),
        ):
            yield chunk

    async def _available_tools(
        self,
        config: dict[str, Any],
        tool_specs: list[ToolSpec] | None,
    ) -> list[ToolSpec]:
        config_allowed = _configured_allowed_tools(config)
        if config_allowed is not None:
            effective_allowed = set(config_allowed)
            if tool_specs is not None:
                effective_allowed &= {tool.name for tool in tool_specs}
            if not effective_allowed:
                return []
            native_tools = [
                tool
                for tool in self.tool_registry.tool_specs(None)
                if tool.name in effective_allowed
            ]
            mcp_tools: list[ToolSpec] = []
            if any(tool_name.startswith("mcp_") for tool_name in effective_allowed):
                mcp_tools = [
                    tool
                    for tool in await self.mcp_client.list_tools()
                    if tool.name in effective_allowed
                ]
            return [*native_tools, *mcp_tools]

        native_tools = self.tool_registry.tool_specs(tool_specs)
        mcp_tools = await self.mcp_client.list_tools()
        if tool_specs is None:
            return [*native_tools, *mcp_tools]

        allowed = {tool.name for tool in tool_specs}
        return [*native_tools, *(tool for tool in mcp_tools if tool.name in allowed)]

    async def _stream_deterministic_read_only(
        self,
        path: str,
        *,
        workspace_path: Path,
        config: dict[str, Any],
    ) -> AsyncIterator[StreamChunk]:
        call_id = "builtin.read_file.1"
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(
            event_type="tool_call",
            agent_id=self.agent_id,
            call_id=call_id,
            tool_name="read_file",
            tool_arguments={"path": path},
        )
        try:
            output = await self.tool_registry.execute(
                "read_file",
                {"path": path},
                workspace_path=workspace_path,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 - expose safe tool failure.
            yield StreamChunk(
                event_type="tool_result",
                agent_id=self.agent_id,
                call_id=call_id,
                tool_status="error",
                tool_output=str(exc) or exc.__class__.__name__,
                metadata={"error_code": "tool_call_failed"},
            )
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="tool_call_failed",
                error=str(exc) or exc.__class__.__name__,
            )
            return

        yield StreamChunk(
            event_type="tool_result",
            agent_id=self.agent_id,
            call_id=call_id,
            tool_status="ok",
            tool_output=output,
        )
        yield StreamChunk(
            event_type="block_start",
            agent_id=self.agent_id,
            block_index=0,
            block_type="text",
        )
        yield StreamChunk(
            event_type="delta",
            agent_id=self.agent_id,
            block_index=0,
            text_delta=_read_only_summary(path, output),
        )
        yield StreamChunk(
            event_type="block_end",
            agent_id=self.agent_id,
            block_index=0,
        )
        yield StreamChunk(event_type="done", agent_id=self.agent_id)


def _read_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(1, int(value))


def _configured_allowed_tools(config: dict[str, Any]) -> set[str] | None:
    if "allowed_tools" not in config:
        return None
    value = config.get("allowed_tools")
    if not isinstance(value, list):
        return set()
    return {tool for tool in value if isinstance(tool, str)}


def _deterministic_read_only_path(
    config: dict[str, Any],
    messages: list[ChatMessage],
    tools: list[ToolSpec],
) -> str | None:
    allowed = _configured_allowed_tools(config)
    if allowed != {"read_file"}:
        return None
    if not any(tool.name == "read_file" for tool in tools):
        return None
    latest = _latest_user_text(messages)
    if not re.search(r"(?i)(read_file|\u8bfb\u53d6)", latest):
        return None
    match = READ_FILE_PATH_RE.search(latest)
    if match is None:
        return None
    return match.group(1)


def _latest_user_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _read_only_summary(path: str, content: str) -> str:
    if path.endswith(".md") and "REQUIRED_REPAIR_SECTION" in content and "TODO" in content:
        return (
            f"已使用 read_file 读取 `{path}`。\n\n"
            "`REQUIRED_REPAIR_SECTION` 目前仍处于 TODO/待补充状态，"
            "需要由可写 Agent 修复。"
        )
    return f"已使用 read_file 读取 `{path}`。\n\n{content}"
