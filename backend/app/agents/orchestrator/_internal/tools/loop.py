"""Native tool-calling loop for AgentHub Orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator._internal.execution.presentation import (
    ToolResultFact,
    presented_response_text,
)
from app.agents.orchestrator._internal.execution.process_block import (
    execution_process_block,
    final_process_deltas,
    process_block_end,
    process_block_start,
    process_step_delta,
    task_result_step,
    task_running_step,
)
from app.agents.orchestrator._internal.presentation_markers import (
    final_answer_presentation,
)
from app.agents.orchestrator._internal.streams import attach_agent_id
from app.agents.orchestrator._internal.tools.catalog import (
    available_agent_ids,
    orchestrator_tool_specs,
)
from app.agents.orchestrator._internal.tools.dispatch import (
    _dispatch_observation_result,
    _dispatch_task_from_call,
)
from app.agents.orchestrator._internal.tools.streaming import (
    _deployment_status_card,
    _normalize_tool_call,
    _tool_call_chunk,
    _tool_result_chunk,
    _tool_result_message,
    truncate,
)
from app.agents.orchestrator._internal.tools.types import (
    DEFAULT_TOOL_READ_MAX_BYTES,
    DEFAULT_TOOL_RESULT_MAX_CHARS,
    OrchestratorToolCall,
    OrchestratorToolResult,
)
from app.agents.orchestrator._internal.tools.workspace import execute_workspace_tool
from app.agents.orchestrator.types import OrchestratorRunContext, SubTask, TaskResult
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEFAULT_TOOL_MAX_ITERATIONS = 12
MAX_TOOL_MAX_ITERATIONS = 50
DEFAULT_TOOL_MAX_TOKENS = 8192
MAX_TOOL_MAX_TOKENS = 32000
PLATFORM_TOOL_NAMES = {
    "start_workspace_preview",
    "verify_web_preview",
    "create_custom_agent",
    "create_deployment",
    "get_deployment_status",
    "stop_deployment",
    "package_workspace_source",
}
DEPLOYMENT_TOOL_NAMES = {
    "create_deployment",
    "get_deployment_status",
    "stop_deployment",
    "package_workspace_source",
}

LatestUserRequest = Callable[[list[ChatMessage]], str]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]
FormatTaskResultContext = Callable[[str, TaskResult, int], str]


class TextBlockWithNext(Protocol):
    def __call__(
        self,
        block_index: int,
        text: str,
        *,
        agent_id: str = "orchestrator",
        presentation: Mapping[str, Any] | None = None,
    ) -> Iterable[tuple[StreamChunk, int]]: ...


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
    dispatched_tasks: list[SubTask] = []
    tool_result_facts: list[ToolResultFact] = []
    process_block_index: int | None = None
    process_start = process_block_start(
        config,
        next_block_index,
        execution_process_block(messages, dispatched_tasks, {}, run_context),
    )
    if process_start is not None:
        process_chunk, next_block_index = process_start
        process_block_index = process_chunk.block_index
        yield process_chunk, next_block_index
        planning_chunk = process_step_delta(
            config,
            process_block_index,
            {
                "id": "tool-planning",
                "label": "选择工具执行路径",
                "kind": "planning",
                "status": "done",
                "detail": "通过平台或工作区工具处理本次请求。",
            },
        )
        if planning_chunk is not None:
            yield planning_chunk, next_block_index

    for iteration in range(1, max_iterations + 1):
        tool_calls: list[OrchestratorToolCall] = []
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
                    await _finish_memory_run(
                        config,
                        run_context,
                        "error",
                        chunk.error or "tool loop model error",
                    )
                    yield attach_agent_id(chunk, "orchestrator"), next_block_index
                    return
                if chunk.event_type == "heartbeat":
                    yield attach_agent_id(chunk, "orchestrator"), next_block_index
                    continue
                if chunk.text_delta:
                    final_text_parts.append(chunk.text_delta)
        except Exception as exc:
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
            presented_summary = await presented_response_text(
                config,
                messages,
                dispatched_tasks,
                {},
                run_context,
                final_summary,
                tool_results=tool_result_facts,
            )
            task_states = {
                task.task_id: run_context.results[task.task_id].final_state
                for task in dispatched_tasks
                if task.task_id in run_context.results
            }
            final_process_payload = execution_process_block(
                messages,
                dispatched_tasks,
                task_states,
                run_context,
                tool_results=tool_result_facts,
            )
            for chunk in final_process_deltas(config, process_block_index, final_process_payload):
                yield chunk, next_block_index
            process_end = process_block_end(config, process_block_index)
            if process_end is not None:
                yield process_end, next_block_index
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                presented_summary,
                presentation=final_answer_presentation(),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
            await _finish_memory_run(config, run_context, "done", final_summary)
            return

        result_lines: list[str] = []
        for call_index, call in enumerate(tool_calls, start=1):
            tool_step_id = f"tool-{iteration}-{call_index}"
            tool_start_chunk = process_step_delta(
                config,
                process_block_index,
                {
                    "id": tool_step_id,
                    "label": f"调用 {_friendly_tool_label(call.name)}",
                    "kind": "tool" if call.name != "dispatch_agent" else "dispatch",
                    "status": "running",
                    "detail": "正在执行。",
                },
            )
            if tool_start_chunk is not None:
                yield tool_start_chunk, next_block_index
            if call.name == "dispatch_agent":
                task_or_result = _dispatch_task_from_call(call, config)
                if isinstance(task_or_result, OrchestratorToolResult):
                    result = task_or_result
                else:
                    dispatched_tasks.append(task_or_result)
                    task_start_chunk = process_step_delta(
                        config,
                        process_block_index,
                        task_running_step(task_or_result),
                    )
                    if task_start_chunk is not None:
                        yield task_start_chunk, next_block_index
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
                    task_result = run_context.results.get(task_or_result.task_id)
                    if task_result is not None:
                        task_done_chunk = process_step_delta(
                            config,
                            process_block_index,
                            task_result_step(
                                task_or_result,
                                task_result.final_state,
                                task_result,
                            ),
                        )
                        if task_done_chunk is not None:
                            yield task_done_chunk, next_block_index
                    result = _dispatch_observation_result(
                        task_or_result.task_id,
                        run_context,
                        result_max_chars=result_max_chars,
                        format_task_result_context=format_task_result_context,
                    )
            else:
                result = await _execute_non_dispatch_tool(
                    config,
                    call,
                    workspace_path=workspace_path,
                    result_max_chars=result_max_chars,
                    read_max_bytes=read_max_bytes,
                )
            tool_result_facts.append(
                ToolResultFact(
                    tool_name=call.name,
                    status=result.status,
                    output=result.output,
                    arguments=call.arguments,
                )
            )
            await _record_tool_event(config, run_context, call, result)
            tool_done_chunk = process_step_delta(
                config,
                process_block_index,
                {
                    "id": tool_step_id,
                    "label": f"调用 {_friendly_tool_label(call.name)}",
                    "kind": "tool" if call.name != "dispatch_agent" else "dispatch",
                    "status": "error" if result.status == "error" else "done",
                    "detail": (
                        "工具结果需要注意。" if result.status == "error" else "工具调用完成。"
                    ),
                },
            )
            if tool_done_chunk is not None:
                yield tool_done_chunk, next_block_index
            result_lines.append(_tool_result_message(call, result))
            if visible_trace:
                yield _tool_result_chunk(call, result), next_block_index
            if call.name in DEPLOYMENT_TOOL_NAMES:
                status_card = _deployment_status_card(result)
                if status_card is not None:
                    yield StreamChunk(
                        event_type="block_start",
                        block_index=next_block_index,
                        block_type="deployment_status",
                        metadata=status_card,
                        agent_id="orchestrator",
                    ), next_block_index + 1
                    yield StreamChunk(
                        event_type="block_end",
                        block_index=next_block_index,
                        agent_id="orchestrator",
                    ), next_block_index + 1
                    next_block_index += 1

        current_messages.append(ChatMessage(role="assistant", content="\n".join(result_lines)))

    message = f"orchestrator tool loop exceeded {max_iterations} iterations"
    await _finish_memory_run(config, run_context, "error", message)
    timeout_summary = process_step_delta(
        config,
        process_block_index,
        {
            "id": "tool-loop-limit",
            "label": "工具执行轮次达到上限",
            "kind": "summary",
            "status": "error",
            "detail": "本次工具执行未能在限制内完成。",
        },
    )
    if timeout_summary is not None:
        yield timeout_summary, next_block_index
    process_end = process_block_end(config, process_block_index)
    if process_end is not None:
        yield process_end, next_block_index
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


def _friendly_tool_label(name: str) -> str:
    return name.replace("_", " ").strip() or "tool"


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
        "max_tokens": _configured_positive_int(
            config,
            "orchestrator_tool_max_tokens",
            DEFAULT_TOOL_MAX_TOKENS,
            MAX_TOOL_MAX_TOKENS,
        ),
        "tool_choice": {"type": "auto"},
    }
    model_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in model_config:
            model_config[key] = config[key]
    return model_config

def _configured_positive_int(
    config: Mapping[str, Any],
    key: str,
    default: int,
    maximum: int,
) -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if value < 1:
        return default
    return min(value, maximum)

def _tool_system_prompt(config: Mapping[str, Any]) -> str:
    agents = ", ".join(available_agent_ids(config)) or "(none)"
    return (
        "You are AgentHub Orchestrator running in native tool-calling mode.\n"
        "Use tools for execution. Do not fabricate sub-agent results or workspace facts.\n"
        "Dispatch only these available agent ids: "
        f"{agents}.\n"
        "Do not dispatch orchestrator to itself. Do not request preview/deploy/server "
        "long-running commands from sub-agents. For preview-only requests, use "
        "start_workspace_preview after files exist, then verify_web_preview for browser "
        "quality. For deploy/publish/go-live requests, call create_deployment with "
        "kind=static_site after files exist. For source download requests, call "
        "package_workspace_source. For container deployment or backend service deploy "
        "requests, call create_deployment with kind=container after Dockerfile exists; "
        "include container_port and health_path when known. "
        "Use create_custom_agent when the user asks to create a new Agent. "
        "Use read_artifact, inspect_workspace, and validate_html when useful. "
        "Final answers must be based on tool results. Keep user-visible text concise "
        "and do not reveal hidden reasoning."
    )

async def _execute_non_dispatch_tool(
    config: Mapping[str, Any],
    call: OrchestratorToolCall,
    *,
    workspace_path: Path | None,
    result_max_chars: int,
    read_max_bytes: int,
) -> OrchestratorToolResult:
    if call.name in PLATFORM_TOOL_NAMES:
        executor = config.get("orchestrator_platform_tool_executor")
        if executor is None:
            return OrchestratorToolResult(
                status="error",
                output=f"platform tool executor is not available: {call.name}",
                error_code="platform_tool_unavailable",
            )
        result = cast(OrchestratorToolResult, await executor(call.name, call.arguments))
        if result.output_truncated:
            return result
        output, truncated = truncate(result.output, result_max_chars)
        return OrchestratorToolResult(
            status=result.status,
            output=output,
            error_code=result.error_code,
            output_truncated=truncated,
            needs_user_input=result.needs_user_input,
        )
    return await execute_workspace_tool(
        call.name,
        call.arguments,
        workspace_path=workspace_path,
        result_max_chars=result_max_chars,
        read_max_bytes=read_max_bytes,
    )

def _tool_messages(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[ChatMessage]:
    _ = config
    return messages

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
