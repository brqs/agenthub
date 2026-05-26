"""Minimal builtin agent loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.agents.builtin.mcp.client import MCPClient, MCPServerDown, MCPToolCallError
from app.agents.builtin.tools.exceptions import ToolExecutionError, WorkspaceViolation
from app.agents.builtin.tools.registry import ToolRegistry
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

MAX_TOOL_OUTPUT_CHARS = 2000


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    status: str
    output: str
    error_code: str | None = None


class AgentLoop:
    """Sequential model/tool loop for BuiltinAgent MVP."""

    def __init__(
        self,
        *,
        agent_id: str,
        model_gateway: Any,
        tool_registry: ToolRegistry,
        mcp_client: MCPClient,
    ) -> None:
        self.agent_id = agent_id
        self.model_gateway = model_gateway
        self.tool_registry = tool_registry
        self.mcp_client = mcp_client

    async def run(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec],
        workspace_path: Path,
        system_prompt: str | None,
        config: dict[str, Any],
        max_iterations: int,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        current_messages = list(messages)

        for iteration in range(1, max_iterations + 1):
            tool_calls: list[ToolCall] = []
            try:
                async for chunk in self._model_stream(
                    current_messages,
                    tools,
                    system_prompt,
                    config,
                ):
                    if chunk.event_type == "tool_call":
                        call = self._normalize_tool_call(chunk, iteration, len(tool_calls) + 1)
                        tool_calls.append(call)
                        yield chunk.model_copy(
                            update={
                                "call_id": call.call_id,
                                "tool_name": call.name,
                                "tool_arguments": call.arguments,
                            }
                        )
                        continue

                    if chunk.event_type == "error":
                        for call in tool_calls:
                            yield _tool_result_chunk(
                                _skipped_tool_result(call, "model stream returned error")
                            )
                        yield chunk
                        return

                    if chunk.event_type not in {"start", "done"}:
                        yield chunk
            except Exception as exc:
                for call in tool_calls:
                    yield _tool_result_chunk(
                        _skipped_tool_result(call, "model stream failed before tool execution")
                    )
                yield StreamChunk(
                    event_type="error",
                    agent_id=self.agent_id,
                    error_code="upstream_error",
                    error=str(exc) or exc.__class__.__name__,
                )
                return

            if not tool_calls:
                yield StreamChunk(event_type="done", agent_id=self.agent_id)
                return

            results: list[ToolResult] = []
            for call_index, call in enumerate(tool_calls):
                result = await self._execute_tool(call, workspace_path, tools, config)
                results.append(result)
                yield _tool_result_chunk(result)
                if result.error_code == "workspace_violation":
                    for skipped_call in tool_calls[call_index + 1 :]:
                        yield _tool_result_chunk(
                            _skipped_tool_result(
                                skipped_call,
                                "skipped after workspace_violation",
                            )
                        )
                    yield StreamChunk(
                        event_type="error",
                        agent_id=self.agent_id,
                        error_code="workspace_violation",
                        error=result.output,
                    )
                    return

            current_messages = _append_tool_results(current_messages, tool_calls, results)

        yield StreamChunk(
            event_type="error",
            agent_id=self.agent_id,
            error_code="loop_max_iterations",
            error=f"agent loop exceeded {max_iterations} iterations",
        )

    def _model_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system_prompt: str | None,
        config: dict[str, Any],
    ) -> AsyncIterator[StreamChunk]:
        return cast(
            AsyncIterator[StreamChunk],
            self.model_gateway.stream(
                messages,
                system_prompt=system_prompt,
                config=config,
                tools=tools,
            ),
        )

    def _normalize_tool_call(
        self,
        chunk: StreamChunk,
        iteration: int,
        call_number: int,
    ) -> ToolCall:
        call_id = chunk.call_id or f"c-{iteration}-{call_number}"
        tool_name = chunk.tool_name or ""
        arguments = chunk.tool_arguments or {}
        return ToolCall(call_id=call_id, name=tool_name, arguments=arguments)

    async def _execute_tool(
        self,
        call: ToolCall,
        workspace_path: Path,
        tools: list[ToolSpec],
        config: dict[str, Any],
    ) -> ToolResult:
        allowed_tool_names = {tool.name for tool in tools}
        if call.name not in allowed_tool_names:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output=f"tool is not allowed: {call.name}",
                error_code="tool_call_failed",
            )

        try:
            if self.mcp_client.is_mcp_tool(call.name):
                output = await self.mcp_client.call_tool(call.name, call.arguments)
            else:
                output = await self.tool_registry.execute(
                    call.name,
                    call.arguments,
                    workspace_path=workspace_path,
                    config=config,
                )
            return ToolResult(call_id=call.call_id, status="ok", output=output)
        except WorkspaceViolation as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output=str(exc),
                error_code="workspace_violation",
            )
        except MCPServerDown as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output=str(exc),
                error_code="mcp_server_down",
            )
        except MCPToolCallError as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output=str(exc),
                error_code="tool_call_failed",
            )
        except ToolExecutionError as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output=str(exc),
                error_code=exc.error_code,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output=str(exc) or exc.__class__.__name__,
                error_code="tool_call_failed",
            )


def _tool_result_chunk(result: ToolResult) -> StreamChunk:
    output, truncated = _truncate(result.output)
    metadata = {"error_code": result.error_code} if result.error_code else None
    return StreamChunk(
        event_type="tool_result",
        call_id=result.call_id,
        tool_status="ok" if result.status == "ok" else "error",
        tool_output=output,
        tool_output_truncated=truncated,
        metadata=metadata,
    )


def _skipped_tool_result(call: ToolCall, reason: str) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        status="error",
        output=f"tool call skipped: {reason}",
        error_code="tool_call_failed",
    )


def _append_tool_results(
    messages: list[ChatMessage],
    calls: list[ToolCall],
    results: list[ToolResult],
) -> list[ChatMessage]:
    result_lines = [
        f"Tool {call.name} ({call.call_id}) {result.status}: {result.output}"
        for call, result in zip(calls, results, strict=True)
    ]
    return [*messages, ChatMessage(role="assistant", content="\n".join(result_lines))]


def _truncate(output: str) -> tuple[str, bool]:
    if len(output) <= MAX_TOOL_OUTPUT_CHARS:
        return output, False
    return output[:MAX_TOOL_OUTPUT_CHARS], True
