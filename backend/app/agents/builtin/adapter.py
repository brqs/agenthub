"""BuiltinAgentAdapter entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.builtin.loop import AgentLoop
from app.agents.builtin.mcp.client import MCPClient, MCPServerDown
from app.agents.builtin.tools.registry import ToolRegistry
from app.agents.model_gateway import ModelGateway
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


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
            tools = await self._available_tools(tool_specs)
        except MCPServerDown as exc:
            yield StreamChunk(
                event_type="error",
                agent_id=self.agent_id,
                error_code="mcp_server_down",
                error=str(exc),
            )
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

    async def _available_tools(self, tool_specs: list[ToolSpec] | None) -> list[ToolSpec]:
        native_tools = self.tool_registry.tool_specs(tool_specs)
        mcp_tools = await self.mcp_client.list_tools()
        if tool_specs is None:
            return [*native_tools, *mcp_tools]

        allowed = {tool.name for tool in tool_specs}
        return [*native_tools, *(tool for tool in mcp_tools if tool.name in allowed)]


def _read_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(1, int(value))
