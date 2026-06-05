"""Static task execution and attempt-state helpers for Orchestrator."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.orchestrator._internal.execution.adapters import get_sub_adapter as _get_sub_adapter
from app.agents.orchestrator._internal.execution.artifacts import (
    artifact_file_blocks as _artifact_file_blocks,
)
from app.agents.orchestrator._internal.execution.attempts import (
    agent_for_attempt as _agent_for_attempt,
)
from app.agents.orchestrator._internal.execution.attempts import (
    attempt_call_id_prefix as _attempt_call_id_prefix,
)
from app.agents.orchestrator._internal.execution.attempts import (
    can_retry_task as _can_retry_task,
)
from app.agents.orchestrator._internal.execution.attempts import (
    changes_for_attempt_artifacts as _changes_for_attempt_artifacts,
)
from app.agents.orchestrator._internal.execution.attempts import (
    max_task_attempts as _max_task_attempts,
)
from app.agents.orchestrator._internal.execution.attempts import (
    parallel_enabled as _parallel_enabled,
)
from app.agents.orchestrator._internal.execution.attempts import (
    parallel_max_concurrency as _parallel_max_concurrency,
)
from app.agents.orchestrator._internal.execution.attempts import (
    task_fallback_agent_ids as _task_fallback_agent_ids,
)
from app.agents.orchestrator._internal.execution.attempts import (
    task_messages as _task_messages,
)
from app.agents.orchestrator._internal.execution.evaluation import (
    run_attempt_evaluation as _run_attempt_evaluation,
)
from app.agents.orchestrator._internal.execution.events import (
    accumulate_text_event as _accumulate_text_event,
)
from app.agents.orchestrator._internal.execution.events import (
    accumulate_tool_event as _accumulate_tool_event,
)
from app.agents.orchestrator._internal.execution.events import (
    error_reason as _error_reason,
)
from app.agents.orchestrator._internal.execution.events import (
    refresh_and_record_workspace_conflicts as _refresh_and_record_workspace_conflicts,
)
from app.agents.orchestrator._internal.execution.review import (
    review_outcome as _review_outcome,
)
from app.agents.orchestrator._internal.execution.review import (
    review_repair_task as _review_repair_task,
)
from app.agents.orchestrator._internal.execution.summary import summary_text as _summary_text
from app.agents.orchestrator._internal.memory import (
    finish_run as _memory_finish_run,
)
from app.agents.orchestrator._internal.memory import (
    record_event as _memory_record_event,
)
from app.agents.orchestrator._internal.memory import (
    record_task_result as _memory_record_task_result,
)
from app.agents.orchestrator._internal.memory import (
    record_task_started as _memory_record_task_started,
)
from app.agents.orchestrator._internal.streams import remapped_sub_stream as _remapped_sub_stream
from app.agents.orchestrator.artifacts import (
    check_attempt_artifacts as _check_attempt_artifacts,
)
from app.agents.orchestrator.artifacts import (
    finalize_artifact_candidates as _finalize_artifact_candidates,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.orchestrator.workspace_changes import (
    diff_workspace_snapshots,
    refresh_workspace_conflicts,
    snapshot_workspace,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


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
    block_index: int,
    text: str,
    *,
    agent_id: str = "orchestrator",
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="delta",
            block_index=block_index,
            text_delta=text,
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="block_end",
            block_index=block_index,
            agent_id=agent_id,
        ),
    )


def _text_block_with_next(
    block_index: int,
    text: str,
    *,
    agent_id: str = "orchestrator",
) -> tuple[tuple[StreamChunk, int], ...]:
    next_block_index = block_index + 1
    return tuple(
        (chunk, next_block_index)
        for chunk in _text_block(block_index, text, agent_id=agent_id)
    )


def _task_card_block(
    block_index: int,
    tasks: list[SubTask],
) -> tuple[tuple[StreamChunk, int], ...]:
    metadata = {
        "title": "Orchestrator 调度计划",
        "tasks": [
            {
                "id": task.task_id,
                "agent_id": task.agent_id,
                "title": task.title,
                "status": "pending",
            }
            for task in sorted(tasks, key=lambda item: (item.priority, item.task_id))
        ],
    }
    next_block_index = block_index + 1
    return (
        (
            StreamChunk(
                event_type="block_start",
                block_index=block_index,
                block_type="task_card",
                agent_id="orchestrator",
                metadata=metadata,
            ),
            next_block_index,
        ),
        (
            StreamChunk(
                event_type="block_end",
                block_index=block_index,
                agent_id="orchestrator",
            ),
            next_block_index,
        ),
    )


def _failure_text(task: SubTask, reason: str, agent_id: str | None = None) -> str:
    _ = task
    _ = agent_id
    return f"failed: {reason}\n"


@dataclass(slots=True)
class _ParallelTaskEvent:
    task_id: str
    chunk: StreamChunk | None = None
    error: Exception | None = None
    done: bool = False



async def _run_static_tasks(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_context: OrchestratorRunContext | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    if _parallel_enabled(config):
        async for chunk, updated_block_index in _run_parallel_tasks(
            config,
            tasks,
            messages,
            next_block_index,
            workspace_path,
            tool_specs,
            run_context,
        ):
            yield chunk, updated_block_index
        return

    task_sequence = list(tasks)
    task_states = {task.task_id: TaskState.PENDING for task in task_sequence}
    run_context = run_context or OrchestratorRunContext()
    repaired_review_task_ids: set[str] = set()
    task_index = 0
    while task_index < len(task_sequence):
        task = task_sequence[task_index]
        if not _dependencies_satisfied(task, task_states):
            task_states[task.task_id] = TaskState.SKIPPED
            skipped_result = TaskResult(
                task_id=task.task_id,
                title=task.title,
                final_state=TaskState.SKIPPED,
            )
            run_context.record(skipped_result)
            await _memory_record_task_result(config, run_context, task, skipped_result)
            task_index += 1
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
        task_result = run_context.results[task.task_id]
        task_states[task.task_id] = task_result.final_state
        repair_task = None
        if task.task_id not in repaired_review_task_ids:
            repair_task = await _review_repair_task(
                config,
                task_sequence,
                task,
                task_result,
                run_context,
            )
        if repair_task is not None:
            repaired_review_task_ids.add(task.task_id)
            task_sequence.insert(task_index + 1, repair_task)
            task_states[repair_task.task_id] = TaskState.PENDING
        await _refresh_and_record_workspace_conflicts(config, run_context)
        task_index += 1

    refresh_workspace_conflicts(run_context)
    final_summary = _summary_text(task_sequence, task_states, run_context)
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
        before_snapshot = snapshot_workspace(workspace_path)
        await _memory_record_task_started(
            config,
            run_context,
            task,
            agent_id,
            attempt_index,
        )
        await _memory_record_event(
            config,
            run_context,
            event_type="workspace_snapshot",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "stage": "before",
                "attempt_index": attempt_index,
                "file_count": len(before_snapshot),
            },
        )

        yield _agent_switch(task, agent_id), next_block_index

        try:
            sub_adapter = await _get_sub_adapter(config, agent_id)
        except Exception as exc:
            attempt.state = TaskState.FAILED
            attempt.error = str(exc)
            for chunk, updated_block_index in _text_block_with_next(
                next_block_index,
                _failure_text(task, str(exc), agent_id),
                agent_id=agent_id,
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
            stream_config = _sub_agent_stream_config(
                config,
                task,
                agent_id,
                attempt_index,
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
                stream_config=stream_config,
                text_visible=config.get("orchestrator_subagent_text_visible") is True,
            ):
                next_block_index = updated_block_index
                task_failed = subtask_failed
                yield chunk, updated_block_index
            if task_failed:
                attempt.state = TaskState.FAILED
            else:
                if task.task_type == "review":
                    attempt.state = TaskState.SUCCEEDED
                else:
                    _finalize_artifact_candidates(attempt, task)
                    _check_attempt_artifacts(attempt, workspace_path)
                    if attempt.state == TaskState.SUCCEEDED:
                        await _run_attempt_evaluation(
                            config,
                            task,
                            attempt,
                            run_context,
                            workspace_path,
                            agent_id,
                        )
                    artifact_chunks, next_block_index = await _artifact_file_blocks(
                        config,
                        workspace_path,
                        task,
                        attempt,
                        run_context,
                        next_block_index,
                        agent_id,
                    )
                    for artifact_chunk in artifact_chunks:
                        yield artifact_chunk, next_block_index

        after_snapshot = snapshot_workspace(workspace_path)
        attempt.file_changes = _changes_for_attempt_artifacts(
            diff_workspace_snapshots(before_snapshot, after_snapshot),
            attempt.artifact_paths,
        )
        if task.task_type == "review":
            attempt.review_outcome = _review_outcome(attempt.text_preview, attempt.state)
            await _memory_record_event(
                config,
                run_context,
                event_type="agent_review_completed",
                task_id=task.task_id,
                agent_id=agent_id,
                payload={
                    "review_of": list(task.review_of or task.depends_on),
                    "handoff_reason": task.handoff_reason,
                    "outcome": attempt.review_outcome,
                    "attempt_index": attempt_index,
                },
            )
        await _memory_record_event(
            config,
            run_context,
            event_type="workspace_snapshot",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "stage": "after",
                "attempt_index": attempt_index,
                "file_count": len(after_snapshot),
            },
        )
        await _memory_record_event(
            config,
            run_context,
            event_type="workspace_file_changes",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "attempt_index": attempt_index,
                "changes": attempt.file_changes,
            },
        )
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
    refresh_workspace_conflicts(run_context)
    await _refresh_and_record_workspace_conflicts(config, run_context)
    await _memory_record_task_result(config, run_context, task, task_result)


def _sub_agent_stream_config(
    config: Mapping[str, Any],
    task: SubTask,
    agent_id: str,
    attempt_index: int,
) -> dict[str, Any]:
    stream_config = dict(config)
    raw_runtime_context = stream_config.get("runtime_context")
    runtime_context = (
        dict(raw_runtime_context) if isinstance(raw_runtime_context, Mapping) else {}
    )
    for key in ("conversation_id", "agent_message_id"):
        value = stream_config.get(key)
        if value is not None and key not in runtime_context:
            runtime_context[key] = str(value)
    runtime_context.update(
        {
            "agent_id": agent_id,
            "orchestrator_task_id": task.task_id,
            "orchestrator_task_title": task.title,
            "orchestrator_attempt_index": str(attempt_index),
        }
    )
    stream_config["runtime_context"] = runtime_context
    return stream_config


async def _run_parallel_tasks(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_context: OrchestratorRunContext | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_states = {task.task_id: TaskState.PENDING for task in tasks}
    pending = {task.task_id for task in tasks}
    task_sequence = list(tasks)
    task_by_id = {task.task_id: task for task in task_sequence}
    run_context = run_context or OrchestratorRunContext()
    max_concurrency = _parallel_max_concurrency(config)
    repaired_review_task_ids: set[str] = set()

    while pending:
        runnable = [
            task_by_id[task_id]
            for task_id in pending
            if _dependencies_satisfied(task_by_id[task_id], task_states)
        ]
        if not runnable:
            for task_id in sorted(pending):
                task = task_by_id[task_id]
                task_states[task_id] = TaskState.SKIPPED
                skipped_result = TaskResult(
                    task_id=task.task_id,
                    title=task.title,
                    final_state=TaskState.SKIPPED,
                )
                run_context.record(skipped_result)
                await _memory_record_task_result(config, run_context, task, skipped_result)
            break

        batch = sorted(runnable, key=lambda task: (task.priority, task.task_id))[
            :max_concurrency
        ]
        async for chunk, updated_block_index in _stream_parallel_batch(
            config,
            batch,
            messages,
            run_context,
            workspace_path,
            tool_specs,
            next_block_index,
        ):
            next_block_index = updated_block_index
            yield chunk, updated_block_index

        for task in batch:
            pending.discard(task.task_id)
            task_result = run_context.results[task.task_id]
            task_states[task.task_id] = task_result.final_state
            repair_task = None
            if task.task_id not in repaired_review_task_ids:
                repair_task = await _review_repair_task(
                    config,
                    task_sequence,
                    task,
                    task_result,
                    run_context,
                )
            if repair_task is not None:
                repaired_review_task_ids.add(task.task_id)
                task_sequence.append(repair_task)
                task_by_id[repair_task.task_id] = repair_task
                task_states[repair_task.task_id] = TaskState.PENDING
                pending.add(repair_task.task_id)
        await _refresh_and_record_workspace_conflicts(config, run_context)

    refresh_workspace_conflicts(run_context)
    final_summary = _summary_text(task_sequence, task_states, run_context)
    await _memory_finish_run(config, run_context, "done", final_summary)
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        final_summary,
    ):
        yield chunk, updated_block_index


async def _stream_parallel_batch(
    config: Mapping[str, Any],
    batch: list[SubTask],
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    next_block_index: int,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    queue: asyncio.Queue[_ParallelTaskEvent] = asyncio.Queue()
    workers = [
        asyncio.create_task(
            _produce_parallel_task_events(
                queue,
                config,
                task,
                messages,
                run_context,
                workspace_path,
                tool_specs,
            )
        )
        for task in batch
    ]
    index_maps: dict[str, dict[int, int]] = {}
    active_workers = len(workers)
    try:
        while active_workers:
            event = await queue.get()
            if event.error is not None:
                raise event.error
            if event.done:
                active_workers -= 1
                continue
            if event.chunk is None:
                continue
            remapped, next_block_index = _remap_parallel_chunk(
                event.task_id,
                event.chunk,
                next_block_index,
                index_maps,
            )
            yield remapped, next_block_index
    finally:
        await _cancel_parallel_workers(workers)


async def _produce_parallel_task_events(
    queue: asyncio.Queue[_ParallelTaskEvent],
    config: Mapping[str, Any],
    task: SubTask,
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
) -> None:
    try:
        async for chunk, _updated_block_index in _run_task(
            config,
            task,
            messages,
            0,
            run_context,
            workspace_path,
            tool_specs,
        ):
            await queue.put(_ParallelTaskEvent(task_id=task.task_id, chunk=chunk))
    except Exception as exc:
        await queue.put(_ParallelTaskEvent(task_id=task.task_id, error=exc))
        return
    await queue.put(_ParallelTaskEvent(task_id=task.task_id, done=True))


def _remap_parallel_chunk(
    task_id: str,
    chunk: StreamChunk,
    next_block_index: int,
    index_maps: dict[str, dict[int, int]],
) -> tuple[StreamChunk, int]:
    if chunk.block_index is None:
        return chunk, next_block_index
    index_map = index_maps.setdefault(task_id, {})
    source_index = chunk.block_index
    if source_index not in index_map:
        index_map[source_index] = next_block_index
        next_block_index += 1
    return chunk.model_copy(update={"block_index": index_map[source_index]}), next_block_index


async def _cancel_parallel_workers(workers: list[asyncio.Task[None]]) -> None:
    pending_workers = [worker for worker in workers if not worker.done()]
    for worker in pending_workers:
        worker.cancel()
    if pending_workers:
        await asyncio.gather(*pending_workers, return_exceptions=True)
