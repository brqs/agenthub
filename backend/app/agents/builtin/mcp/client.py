"""Minimal stdio MCP JSON-RPC client."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from app.agents.types import ToolSpec

MCP_TOOL_SEPARATOR = "__"


class MCPServerDown(RuntimeError):  # noqa: N818 - matches spec wording.
    """Raised when an MCP stdio server cannot be started or used."""


class MCPToolCallError(RuntimeError):
    """Raised when an MCP tool call fails but the server is not considered down."""


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: tuple[str, ...] = ()
    timeout_seconds: float = 15.0


class MCPClient:
    """Single-process stdio MCP client with static server config."""

    def __init__(self, servers: list[MCPServerConfig] | None = None) -> None:
        self.servers = servers or []
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self._request_id = 0

    @classmethod
    def from_config(cls, raw_servers: Any) -> MCPClient:
        if not isinstance(raw_servers, list):
            return cls()

        servers: list[MCPServerConfig] = []
        for raw_server in raw_servers:
            if not isinstance(raw_server, dict):
                continue
            name = raw_server.get("name")
            command = raw_server.get("command")
            raw_args = raw_server.get("args", [])
            if not isinstance(name, str) or not isinstance(command, str):
                continue
            args = (
                tuple(arg for arg in raw_args if isinstance(arg, str))
                if isinstance(raw_args, list)
                else ()
            )
            timeout = raw_server.get("timeout_seconds", 15.0)
            timeout_seconds = float(timeout) if isinstance(timeout, (int, float)) else 15.0
            servers.append(
                MCPServerConfig(
                    name=name,
                    command=command,
                    args=args,
                    timeout_seconds=max(0.1, timeout_seconds),
                )
            )
        return cls(servers)

    async def list_tools(self) -> list[ToolSpec]:
        tools: list[ToolSpec] = []
        for server in self.servers:
            response = await self._request(server, "tools/list", {})
            for raw_tool in _raw_tools(response):
                name = raw_tool.get("name")
                if not isinstance(name, str):
                    continue
                tools.append(
                    ToolSpec(
                        name=f"mcp_{server.name}{MCP_TOOL_SEPARATOR}{name}",
                        description=_optional_str(raw_tool.get("description")),
                        parameters=_tool_schema(raw_tool),
                    )
                )
        return tools

    def is_mcp_tool(self, tool_name: str) -> bool:
        return tool_name.startswith("mcp_") and MCP_TOOL_SEPARATOR in tool_name

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        server, remote_tool = self._parse_tool_name(tool_name)
        response = await self._request(
            server,
            "tools/call",
            {"name": remote_tool, "arguments": arguments},
        )
        return _format_tool_response(response)

    async def aclose(self) -> None:
        for process in self.processes.values():
            if process.returncode is None:
                process.terminate()
                await process.wait()
        self.processes.clear()

    async def _request(
        self,
        server: MCPServerConfig,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        process = await self._ensure_process(server)
        if process.stdin is None or process.stdout is None:
            raise MCPServerDown(f"MCP server {server.name} stdio unavailable")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        try:
            process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
            await process.stdin.drain()
            line = await asyncio.wait_for(process.stdout.readline(), timeout=server.timeout_seconds)
        except TimeoutError as exc:
            if method == "tools/call":
                raise MCPToolCallError("MCP tool call timed out") from exc
            raise MCPServerDown(f"MCP server {server.name} is down") from exc
        except (BrokenPipeError, ConnectionError) as exc:
            raise MCPServerDown(f"MCP server {server.name} is down") from exc

        if not line:
            raise MCPServerDown(f"MCP server {server.name} is down")

        try:
            payload = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPServerDown(f"MCP server {server.name} returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise MCPServerDown(f"MCP server {server.name} returned invalid payload")
        error = payload.get("error")
        if error is not None:
            raise MCPServerDown(f"MCP server {server.name} error: {error}")
        result = payload.get("result", {})
        if not isinstance(result, dict):
            return {"value": result}
        return result

    async def _ensure_process(self, server: MCPServerConfig) -> asyncio.subprocess.Process:
        existing = self.processes.get(server.name)
        if existing is not None and existing.returncode is None:
            return existing
        try:
            process = await asyncio.create_subprocess_exec(
                server.command,
                *server.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise MCPServerDown(f"MCP server {server.name} failed to start") from exc
        self.processes[server.name] = process
        return process

    def _parse_tool_name(self, tool_name: str) -> tuple[MCPServerConfig, str]:
        namespace, remote_tool = tool_name.split(MCP_TOOL_SEPARATOR, 1)
        server_name = namespace.removeprefix("mcp_")
        for server in self.servers:
            if server.name == server_name:
                return server, remote_tool
        raise MCPServerDown(f"MCP server not configured: {server_name}")


def _raw_tools(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_tools = response.get("tools", [])
    if not isinstance(raw_tools, list):
        return []
    return [tool for tool in raw_tools if isinstance(tool, dict)]


def _tool_schema(raw_tool: dict[str, Any]) -> dict[str, Any]:
    schema = raw_tool.get("inputSchema") or raw_tool.get("parameters") or {}
    return schema if isinstance(schema, dict) else {}


def _format_tool_response(response: dict[str, Any]) -> str:
    content = response.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    value = response.get("value", response)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
