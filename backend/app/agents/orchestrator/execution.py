"""Static task execution and attempt-state helpers for Orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from app.agents.orchestrator.adapters import get_sub_adapter as _get_sub_adapter
from app.agents.orchestrator.artifacts import (
    check_attempt_artifacts as _check_attempt_artifacts,
)
from app.agents.orchestrator.artifacts import (
    extract_artifact_paths_from_mapping as _extract_artifact_paths_from_mapping,
)
from app.agents.orchestrator.artifacts import (
    extract_artifact_paths_from_text as _extract_artifact_paths_from_text,
)
from app.agents.orchestrator.artifacts import (
    finalize_artifact_candidates as _finalize_artifact_candidates,
)
from app.agents.orchestrator.memory_hooks import (
    finish_run as _memory_finish_run,
)
from app.agents.orchestrator.memory_hooks import (
    record_task_result as _memory_record_task_result,
)
from app.agents.orchestrator.memory_hooks import (
    record_task_started as _memory_record_task_started,
)
from app.agents.orchestrator.streams import remapped_sub_stream as _remapped_sub_stream
from app.agents.orchestrator.summary import summary_text as _summary_text
from app.agents.orchestrator.summary import (
    task_result_context_message as _task_result_context_message,
)
from app.agents.orchestrator.summary import (
    truncate_preserving_edges as _truncate_preserving_edges,
)
from app.agents.orchestrator.types import (
    DEFAULT_MAX_TASK_ATTEMPTS,
    DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS,
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    MAX_TASK_ATTEMPTS_LIMIT,
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

ARTIFACT_OUTPUT_TOOL_NAMES = {
    "edit",
    "multi_edit",
    "replace",
    "write",
    "write_file",
}


def _dependencies_satisfied(
    task: SubTask,
    task_states: Mapping[str, TaskState],
) -> bool:
    return all(
        task_states.get(task_id) == TaskState.SUCCEEDED
        for task_id in task.depends_on
    )


def _agent_switch(task: SubTask, agent_id: str | None = None) -> StreamChunk:
    target_agent_id = agent_id or task.agent_id
    return StreamChunk(
        event_type="agent_switch",
        from_agent="orchestrator",
        to_agent=target_agent_id,
        task=task.title,
    )


def _text_block(
    block_index: int, text: str
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(event_type="block_start", block_index=block_index, block_type="text"),
        StreamChunk(event_type="delta", block_index=block_index, text_delta=text),
        StreamChunk(event_type="block_end", block_index=block_index),
    )


def _text_block_with_next(
    block_index: int,
    text: str,
) -> tuple[tuple[StreamChunk, int], ...]:
    next_block_index = block_index + 1
    return tuple((chunk, next_block_index) for chunk in _text_block(block_index, text))


def _agent_header_text(task: SubTask, agent_id: str | None = None) -> str:
    _ = task
    return f"@{agent_id or task.agent_id}\n\n"


def _failure_text(task: SubTask, reason: str, agent_id: str | None = None) -> str:
    _ = task
    return f"@{agent_id or task.agent_id} failed: {reason}\n"



async def _run_static_tasks(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_context: OrchestratorRunContext | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_states = {task.task_id: TaskState.PENDING for task in tasks}
    run_context = run_context or OrchestratorRunContext()
    for task in tasks:
        if not _dependencies_satisfied(task, task_states):
            task_states[task.task_id] = TaskState.SKIPPED
            skipped_result = TaskResult(
                task_id=task.task_id,
                title=task.title,
                final_state=TaskState.SKIPPED,
            )
            run_context.record(skipped_result)
            await _memory_record_task_result(config, run_context, task, skipped_result)
            continue

        async for chunk, updated_block_index in _run_task(
            config,
            task,
            messages,
            next_block_index,
            run_context,
            workspace_path,
            tool_specs,
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index
        task_states[task.task_id] = run_context.results[task.task_id].final_state

    final_summary = _summary_text(tasks, task_states, run_context)
    await _memory_finish_run(config, run_context, "done", final_summary)
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        final_summary,
    ):
        yield chunk, updated_block_index



async def _run_task(
    config: Mapping[str, Any],
    task: SubTask,
    messages: list[ChatMessage],
    next_block_index: int,
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    *,
    call_id_prefix: str | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_result = TaskResult(task_id=task.task_id, title=task.title)
    fallback_agents = _task_fallback_agent_ids(config)
    max_attempts = _max_task_attempts(config)
    attempted_agents: set[str] = set()

    for attempt_index in range(1, max_attempts + 1):
        agent_id = _agent_for_attempt(task, fallback_agents, attempted_agents)
        if agent_id is None:
            break
        attempted_agents.add(agent_id)

        attempt = TaskAttempt(attempt_index=attempt_index, agent_id=agent_id)
        task_result.attempts.append(attempt)
        await _memory_record_task_started(
            config,
            run_context,
            task,
            agent_id,
            attempt_index,
        )

        yield _agent_switch(task, agent_id), next_block_index
        for chunk, updated_block_index in _text_block_with_next(
            next_block_index,
            _agent_header_text(task, agent_id),
        ):
            yield chunk, updated_block_index
        next_block_index += 1

        try:
            sub_adapter = await _get_sub_adapter(config, agent_id)
        except Exception as exc:
            attempt.state = TaskState.FAILED
            attempt.error = str(exc)
            for chunk, updated_block_index in _text_block_with_next(
                next_block_index,
                _failure_text(task, str(exc), agent_id),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index
        else:
            sub_messages = _task_messages(
                task,
                messages,
                run_context,
                config,
                previous_attempt=task_result.attempts[-2]
                if len(task_result.attempts) > 1
                else None,
            )
            task_failed = False
            async for chunk, updated_block_index, subtask_failed in _remapped_sub_stream(
                sub_adapter,
                task,
                agent_id,
                _attempt_call_id_prefix(
                    task.task_id,
                    attempt_index,
                    call_id_prefix=call_id_prefix,
                ),
                sub_messages,
                next_block_index,
                workspace_path,
                tool_specs,
                attempt,
                text_block=_text_block,
                failure_text=_failure_text,
                error_reason=_error_reason,
                accumulate_text_event=_accumulate_text_event,
                accumulate_tool_event=_accumulate_tool_event,
            ):
                next_block_index = updated_block_index
                task_failed = subtask_failed
                yield chunk, updated_block_index
            if task_failed:
                attempt.state = TaskState.FAILED
            else:
                _finalize_artifact_candidates(attempt, task)
                _check_attempt_artifacts(attempt, workspace_path)

        task_result.final_state = attempt.state
        if attempt.state == TaskState.SUCCEEDED:
            break
        if not _can_retry_task(task_result, fallback_agents, max_attempts):
            break

    if not task_result.attempts:
        task_result.final_state = TaskState.FAILED
        task_result.attempts.append(
            TaskAttempt(
                attempt_index=1,
                agent_id=task.agent_id,
                state=TaskState.FAILED,
                error="no fallback agent available",
            )
        )
    run_context.record(task_result)
    await _memory_record_task_result(config, run_context, task, task_result)


def _task_messages(
    task: SubTask,
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    config: Mapping[str, Any],
    *,
    previous_attempt: TaskAttempt | None = None,
) -> list[ChatMessage]:
    task_message = ChatMessage(role="user", content=task.instruction)
    context_message = _task_result_context_message(
        run_context,
        task,
        context_max_chars=_task_result_context_max_chars(config),
        item_max_chars=_task_result_item_max_chars(config),
        previous_attempt=previous_attempt,
    )
    base_messages = [*messages] if task.include_history else []
    if context_message is not None:
        base_messages.append(context_message)
    base_messages.append(task_message)
    return base_messages


def _task_fallback_agent_ids(config: Mapping[str, Any]) -> list[str]:
    value = config.get("task_fallback_agent_ids")
    if not isinstance(value, list):
        return []
    allowed_agent_ids = _allowed_fallback_agent_ids(config)
    return _dedupe_strings(
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and item.strip() != "orchestrator"
        and (not allowed_agent_ids or item.strip() in allowed_agent_ids)
    )


def _allowed_fallback_agent_ids(config: Mapping[str, Any]) -> set[str]:
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        ids = {
            agent_id
            for item in available_agents
            if isinstance(item, Mapping)
            and isinstance((agent_id := item.get("agent_id", item.get("id"))), str)
            and agent_id.strip()
            and agent_id.strip() != "orchestrator"
        }
        if ids:
            return {agent_id.strip() for agent_id in ids}
    for key in ("managed_agent_ids", "default_sub_agents"):
        value = config.get(key)
        if isinstance(value, list):
            ids = {
                item.strip()
                for item in value
                if isinstance(item, str)
                and item.strip()
                and item.strip() != "orchestrator"
            }
            if ids:
                return ids
    return set()


def _max_task_attempts(config: Mapping[str, Any]) -> int:
    value = config.get("max_task_attempts", DEFAULT_MAX_TASK_ATTEMPTS)
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_MAX_TASK_ATTEMPTS
    return int(min(max(value, 1), MAX_TASK_ATTEMPTS_LIMIT))


def _task_result_context_max_chars(config: Mapping[str, Any]) -> int:
    return _positive_int_config(
        config,
        "task_result_context_max_chars",
        DEFAULT_TASK_RESULT_CONTEXT_MAX_CHARS,
    )


def _task_result_item_max_chars(config: Mapping[str, Any]) -> int:
    return _positive_int_config(
        config,
        "task_result_item_max_chars",
        DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    )


def _positive_int_config(
    config: Mapping[str, Any],
    key: str,
    default: int,
) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return int(value)


def _agent_for_attempt(
    task: SubTask,
    fallback_agents: list[str],
    attempted_agents: set[str],
) -> str | None:
    if not attempted_agents:
        return task.agent_id
    for agent_id in fallback_agents:
        if agent_id not in attempted_agents:
            return agent_id
    return None


def _can_retry_task(
    result: TaskResult,
    fallback_agents: list[str],
    max_attempts: int,
) -> bool:
    if not fallback_agents or len(result.attempts) >= max_attempts:
        return False
    return result.final_state in {TaskState.FAILED, TaskState.ARTIFACT_MISSING}


def _attempt_call_id_prefix(
    task_id: str,
    attempt_index: int,
    *,
    call_id_prefix: str | None = None,
) -> str:
    base = call_id_prefix or task_id
    if attempt_index == 1:
        return base
    return f"{base}.attempt-{attempt_index}"


def _accumulate_text_event(attempt: TaskAttempt, chunk: StreamChunk) -> None:
    if chunk.text_delta:
        attempt.text_preview = _append_limited(
            attempt.text_preview,
            chunk.text_delta,
            DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
        )
    if chunk.code_delta:
        attempt.text_preview = _append_limited(
            attempt.text_preview,
            chunk.code_delta,
            DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
        )
    if chunk.metadata:
        attempt.artifact_paths.extend(_extract_artifact_paths_from_mapping(chunk.metadata))


def _accumulate_tool_event(attempt: TaskAttempt, chunk: StreamChunk) -> None:
    if chunk.event_type == "tool_call":
        summary = _tool_call_summary(chunk)
        if summary:
            attempt.tool_summaries.append(summary)
        if chunk.tool_arguments and _is_artifact_output_tool(chunk.tool_name):
            attempt.artifact_paths.extend(
                _extract_artifact_paths_from_mapping(chunk.tool_arguments)
            )
    elif chunk.event_type == "tool_result":
        summary = _tool_result_summary(chunk)
        if summary:
            attempt.tool_summaries.append(summary)
        if chunk.tool_output:
            attempt.artifact_paths.extend(
                _extract_artifact_paths_from_text(chunk.tool_output)
            )


def _tool_call_summary(chunk: StreamChunk) -> str:
    name = chunk.tool_name or "tool"
    path_bits = []
    if chunk.tool_arguments:
        path_bits = _extract_artifact_paths_from_mapping(chunk.tool_arguments)
    if path_bits:
        return f"{name}({', '.join(path_bits[:3])})"
    return name


def _is_artifact_output_tool(tool_name: str | None) -> bool:
    return (tool_name or "").lower() in ARTIFACT_OUTPUT_TOOL_NAMES


def _tool_result_summary(chunk: StreamChunk) -> str:
    status = chunk.tool_status or "unknown"
    output = _truncate_preserving_edges(chunk.tool_output or "", 160)
    if output:
        return f"result {status}: {output}"
    return f"result {status}"


def _append_limited(existing: str, addition: str, max_chars: int) -> str:
    combined = f"{existing}{addition}"
    return _truncate_preserving_edges(combined, max_chars)


def _dedupe_strings(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output



def _error_reason(chunk: StreamChunk) -> str:
    return chunk.error or chunk.error_code or "unknown error"


def _error_code(exc: ValueError) -> str:
    return str(exc).split(":", maxsplit=1)[0]
