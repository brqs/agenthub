"""Native tool-calling loop for AgentHub Orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator.tools import (
    DEFAULT_TOOL_READ_MAX_BYTES,
    DEFAULT_TOOL_RESULT_MAX_CHARS,
    OrchestratorToolResult,
    available_agent_ids,
    execute_workspace_tool,
    orchestrator_tool_specs,
)
from app.agents.orchestrator.types import OrchestratorRunContext, SubTask, TaskResult
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEFAULT_TOOL_MAX_ITERATIONS = 12
MAX_TOOL_MAX_ITERATIONS = 50

RunTask = Callable[
    [
        Mapping[str, Any],
        SubTask,
        list[ChatMessage],
        int,
        OrchestratorRunContext,
        Path | None,
        list[ToolSpec] | None,
    ],
    AsyncIterator[tuple[StreamChunk, int]],
]
TextBlockWithNext = Callable[[int, str], Iterable[tuple[StreamChunk, int]]]
LatestUserRequest = Callable[[list[ChatMessage]], str]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]
FormatTaskResultContext = Callable[[str, TaskResult, int], str]


class RunTaskWithPrefix(Protocol):
    def __call__(
        self,
        config: Mapping[str, Any],
        task: SubTask,
        messages: list[ChatMessage],
        next_block_index: int,
        run_context: OrchestratorRunContext,
        workspace_path: Path | None,
        tool_specs: list[ToolSpec] | None,
        *,
        call_id_prefix: str | None = None,
    ) -> AsyncIterator[tuple[StreamChunk, int]]: ...


@dataclass(frozen=True, slots=True)
class OrchestratorToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


async def run_orchestrator_tool_loop(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    child_tool_specs: list[ToolSpec] | None,
    *,
    run_context: OrchestratorRunContext | None = None,
    run_task: RunTaskWithPrefix,
    text_block_with_next: TextBlockWithNext,
    latest_user_request: LatestUserRequest,
    positive_int_config: PositiveIntConfig,
    format_task_result_context: FormatTaskResultContext,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    run_context = run_context or OrchestratorRunContext()
    await _start_memory_run(config, run_context, latest_user_request(messages))

    current_messages = [*messages]
    gateway = _tool_gateway(config)
    model_config = _tool_model_config(config)
    tools = orchestrator_tool_specs()
    max_iterations = _max_iterations(config, positive_int_config)
    result_max_chars = _result_max_chars(config, positive_int_config)
    read_max_bytes = _read_max_bytes(config, positive_int_config)
    visible_trace = tool_trace_visible(config)
    final_text_parts: list[str] = []

    for iteration in range(1, max_iterations + 1):
        tool_calls: list[OrchestratorToolCall] = []
        open_block_index: int | None = None
        index_map: dict[int, int] = {}
        try:
            async for chunk in gateway.stream(
                _tool_messages(config, current_messages),
                system_prompt=_tool_system_prompt(config),
                config=model_config,
                tools=tools,
            ):
                if chunk.event_type in {"start", "done"}:
                    continue
                if chunk.event_type == "tool_call":
                    call = _normalize_tool_call(chunk, iteration, len(tool_calls) + 1)
                    tool_calls.append(call)
                    if visible_trace:
                        yield _tool_call_chunk(call), next_block_index
                    continue
                if chunk.event_type == "error":
                    if open_block_index is not None:
                        yield StreamChunk(
                            event_type="block_end",
                            block_index=open_block_index,
                        ), next_block_index
                    await _finish_memory_run(
                        config,
                        run_context,
                        "error",
                        chunk.error or "tool loop model error",
                    )
                    yield chunk, next_block_index
                    return
                if chunk.event_type == "heartbeat":
                    yield chunk, next_block_index
                    continue
                if chunk.event_type not in {"block_start", "delta", "block_end"}:
                    continue
                if chunk.text_delta:
                    final_text_parts.append(chunk.text_delta)
                remapped, next_block_index = _remap_block_index(
                    chunk,
                    index_map,
                    next_block_index,
                )
                if remapped.event_type == "block_start":
                    open_block_index = remapped.block_index
                elif remapped.event_type == "block_end":
                    open_block_index = None
                yield remapped, next_block_index
        except Exception as exc:
            if open_block_index is not None:
                yield StreamChunk(
                    event_type="block_end",
                    block_index=open_block_index,
                ), next_block_index
            await _finish_memory_run(config, run_context, "error", str(exc))
            yield StreamChunk(
                event_type="error",
                agent_id="orchestrator",
                error_code="upstream_error",
                error=str(exc) or exc.__class__.__name__,
            ), next_block_index
            return

        if not tool_calls:
            final_summary = "".join(final_text_parts).strip() or "Tool calling completed."
            if not final_text_parts:
                for chunk, updated_block_index in text_block_with_next(
                    next_block_index,
                    final_summary,
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
            await _finish_memory_run(config, run_context, "done", final_summary)
            return

        result_lines: list[str] = []
        for call in tool_calls:
            if call.name == "dispatch_agent":
                task_or_result = _dispatch_task_from_call(call, config)
                if isinstance(task_or_result, OrchestratorToolResult):
                    result = task_or_result
                else:
                    async for chunk, updated_block_index in run_task(
                        config,
                        task_or_result,
                        current_messages,
                        next_block_index,
                        run_context,
                        workspace_path,
                        child_tool_specs,
                        call_id_prefix=f"{call.call_id}.child",
                    ):
                        next_block_index = updated_block_index
                        yield chunk, updated_block_index
                    result = _dispatch_observation_result(
                        task_or_result.task_id,
                        run_context,
                        result_max_chars=result_max_chars,
                        format_task_result_context=format_task_result_context,
                    )
            else:
                result = await execute_workspace_tool(
                    call.name,
                    call.arguments,
                    workspace_path=workspace_path,
                    result_max_chars=result_max_chars,
                    read_max_bytes=read_max_bytes,
                )
            await _record_tool_event(config, run_context, call, result)
            result_lines.append(_tool_result_message(call, result))
            if visible_trace:
                yield _tool_result_chunk(call, result), next_block_index

        current_messages.append(ChatMessage(role="assistant", content="\n".join(result_lines)))

    message = f"orchestrator tool loop exceeded {max_iterations} iterations"
    await _finish_memory_run(config, run_context, "error", message)
    yield StreamChunk(
        event_type="error",
        agent_id="orchestrator",
        error_code="loop_max_iterations",
        error=message,
    ), next_block_index


def tool_calling_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_tool_calling_enabled") is True


def tool_trace_visible(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_tool_trace_visible", True) is not False


def _dispatch_task_from_call(
    call: OrchestratorToolCall,
    config: Mapping[str, Any],
) -> SubTask | OrchestratorToolResult:
    agent_id = _required_str(call.arguments.get("agent_id"))
    title = _required_str(call.arguments.get("title"))
    instruction = _required_str(call.arguments.get("instruction"))
    if agent_id is None or title is None or instruction is None:
        return OrchestratorToolResult(
            status="error",
            output="dispatch_agent requires agent_id, title, and instruction",
            error_code="invalid_arguments",
        )
    allowed_agents = set(available_agent_ids(config))
    if agent_id == "orchestrator" or agent_id not in allowed_agents:
        return OrchestratorToolResult(
            status="error",
            output=f"agent is not available for this conversation: {agent_id}",
            error_code="agent_not_allowed",
        )
    task_id = _task_id(call.arguments.get("task_id"), call.call_id)
    return SubTask(
        task_id=task_id,
        agent_id=agent_id,
        title=title,
        instruction=instruction,
        expected_output=_optional_str(call.arguments.get("expected_output")),
        include_history=_optional_bool(call.arguments.get("include_history"), True),
    )


def _dispatch_observation_result(
    task_id: str,
    run_context: OrchestratorRunContext,
    *,
    result_max_chars: int,
    format_task_result_context: FormatTaskResultContext,
) -> OrchestratorToolResult:
    result = run_context.results.get(task_id)
    if result is None:
        return OrchestratorToolResult(
            status="error",
            output="dispatch_agent did not produce a task result",
            error_code="dispatch_failed",
        )
    output = _truncate(
        _format_dispatch_observation(task_id, result, format_task_result_context),
        result_max_chars,
    )
    return OrchestratorToolResult(
        status="ok" if result.final_state.value == "succeeded" else "error",
        output=output[0],
        error_code=None if result.final_state.value == "succeeded" else result.final_state.value,
        output_truncated=output[1],
    )


def _tool_gateway(config: Mapping[str, Any]) -> Any:
    gateway = config.get("orchestrator_tool_gateway")
    if gateway is not None:
        return gateway
    backend = config.get("planner_model_backend", config.get("model_backend", "claude"))
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("invalid_tool_config: planner model backend must be a string")
    return ModelGateway(
        backend,
        default_config=_tool_model_config(config),
        agent_id="orchestrator-tool-loop",
        system_prompt=_tool_system_prompt(config),
    )


def _tool_model_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = config.get("orchestrator_tool_config", config.get("orchestrator_llm_config", {}))
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise ValueError("invalid_tool_config: orchestrator_tool_config must be an object")
    model_config: dict[str, Any] = {
        "temperature": 0.2,
        "max_tokens": 2048,
        "tool_choice": {"type": "auto"},
    }
    model_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in model_config:
            model_config[key] = config[key]
    return model_config


def _tool_system_prompt(config: Mapping[str, Any]) -> str:
    agents = ", ".join(available_agent_ids(config)) or "(none)"
    return (
        "You are AgentHub Orchestrator running in native tool-calling mode.\n"
        "Use tools for execution. Do not fabricate sub-agent results or workspace facts.\n"
        "Dispatch only these available agent ids: "
        f"{agents}.\n"
        "Do not dispatch orchestrator to itself. Do not request preview/deploy/server "
        "long-running commands. Use read_artifact, inspect_workspace, and validate_html "
        "to verify workspace artifacts when useful. Final answers must be based on tool "
        "results. Keep user-visible text concise and do not reveal hidden reasoning."
    )


def _tool_messages(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[ChatMessage]:
    _ = config
    return messages


def _normalize_tool_call(
    chunk: StreamChunk,
    iteration: int,
    call_number: int,
) -> OrchestratorToolCall:
    raw_call_id = chunk.call_id or f"{iteration}.{call_number}"
    call_id = raw_call_id if raw_call_id.startswith("orch.") else f"orch.{iteration}.{call_number}"
    return OrchestratorToolCall(
        call_id=call_id,
        name=chunk.tool_name or "",
        arguments=chunk.tool_arguments or {},
    )


def _tool_call_chunk(call: OrchestratorToolCall) -> StreamChunk:
    return StreamChunk(
        event_type="tool_call",
        agent_id="orchestrator",
        call_id=call.call_id,
        tool_name=call.name,
        tool_arguments=call.arguments,
    )


def _tool_result_chunk(
    call: OrchestratorToolCall,
    result: OrchestratorToolResult,
) -> StreamChunk:
    metadata: dict[str, Any] = {}
    if result.error_code:
        metadata["error_code"] = result.error_code
    if result.needs_user_input:
        metadata["needs_user_input"] = True
    return StreamChunk(
        event_type="tool_result",
        agent_id="orchestrator",
        call_id=call.call_id,
        tool_status="ok" if result.status == "ok" else "error",
        tool_output=result.output,
        tool_output_truncated=result.output_truncated,
        metadata=metadata or None,
    )


def _tool_result_message(
    call: OrchestratorToolCall,
    result: OrchestratorToolResult,
) -> str:
    return f"Tool {call.name} ({call.call_id}) {result.status}: {result.output}"


def _format_dispatch_observation(
    task_id: str,
    result: TaskResult,
    format_task_result_context: FormatTaskResultContext,
) -> str:
    return format_task_result_context(task_id, result, DEFAULT_TOOL_RESULT_MAX_CHARS)


def _remap_block_index(
    chunk: StreamChunk,
    index_map: dict[int, int],
    next_block_index: int,
) -> tuple[StreamChunk, int]:
    if chunk.block_index is None:
        return chunk, next_block_index
    source_index = chunk.block_index
    if source_index not in index_map:
        index_map[source_index] = next_block_index
        next_block_index += 1
    return chunk.model_copy(update={"block_index": index_map[source_index]}), next_block_index


async def _start_memory_run(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    user_request: str,
) -> None:
    if run_context.memory_run_id is not None:
        return
    writer = config.get("orchestrator_memory_writer")
    start_run = getattr(writer, "start_run", None)
    if start_run is None:
        return
    try:
        run_context.memory_run_id = await start_run(
            user_request=user_request,
            plan_source="tool_calling",
            tasks=[],
        )
    except Exception:  # noqa: BLE001
        run_context.memory_run_id = None


async def _record_tool_event(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    call: OrchestratorToolCall,
    result: OrchestratorToolResult,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = config.get("orchestrator_memory_writer")
    record_event = getattr(writer, "record_event", None)
    if record_event is None:
        return
    try:
        await record_event(
            run_id=run_context.memory_run_id,
            event_type="tool_call",
            payload={
                "call_id": call.call_id,
                "tool_name": call.name,
                "arguments": call.arguments,
                "status": result.status,
                "output": result.output,
                "error_code": result.error_code,
                "needs_user_input": result.needs_user_input,
            },
        )
    except Exception:  # noqa: BLE001
        return


async def _finish_memory_run(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    status: str,
    final_summary: str,
) -> None:
    if run_context.memory_run_id is None:
        return
    writer = config.get("orchestrator_memory_writer")
    finish_run = getattr(writer, "finish_run", None)
    if finish_run is None:
        return
    try:
        await finish_run(
            run_id=run_context.memory_run_id,
            status=status,
            final_summary=final_summary,
        )
    except Exception:  # noqa: BLE001
        return


def _max_iterations(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    return min(
        positive_int_config(
            config,
            "orchestrator_tool_max_iterations",
            DEFAULT_TOOL_MAX_ITERATIONS,
        ),
        MAX_TOOL_MAX_ITERATIONS,
    )


def _result_max_chars(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    return positive_int_config(
        config,
        "orchestrator_tool_result_max_chars",
        DEFAULT_TOOL_RESULT_MAX_CHARS,
    )


def _read_max_bytes(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    return positive_int_config(
        config,
        "orchestrator_tool_read_max_bytes",
        DEFAULT_TOOL_READ_MAX_BYTES,
    )


def _task_id(value: object, call_id: str) -> str:
    if isinstance(value, str) and value.strip():
        return _safe_task_id(value.strip())
    return _safe_task_id(call_id)


def _safe_task_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in value)
    return safe.strip(".-") or "tool-task"


def _required_str(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _optional_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
