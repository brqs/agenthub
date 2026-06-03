"""Static task execution and attempt-state helpers for Orchestrator."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

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
from app.agents.orchestrator.evaluation import (
    evaluate_attempt as _evaluate_attempt,
)
from app.agents.orchestrator.evaluation import (
    evaluation_results_payload as _evaluation_results_payload,
)
from app.agents.orchestrator.evaluation import (
    reflection_payload as _reflection_payload,
)
from app.agents.orchestrator.memory_hooks import (
    finish_run as _memory_finish_run,
)
from app.agents.orchestrator.memory_hooks import (
    record_event as _memory_record_event,
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
from app.agents.orchestrator.workspace_changes import (
    diff_workspace_snapshots,
    refresh_workspace_conflicts,
    snapshot_workspace,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.services.artifact_manifest import (
    ArtifactManifestService,
    evaluation_results_for_artifact,
    evaluation_status_for_artifact,
)
from app.services.artifact_metadata import build_artifact_metadata
from app.services.workspace_workflow_runtime import (
    WorkspaceWorkflowRuntimeService,
)

ARTIFACT_OUTPUT_TOOL_NAMES = {
    "edit",
    "multi_edit",
    "replace",
    "write",
    "write_file",
}
logger = logging.getLogger(__name__)
artifact_manifest_service = ArtifactManifestService()


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


def _failure_text(task: SubTask, reason: str, agent_id: str | None = None) -> str:
    _ = task
    _ = agent_id
    return f"failed: {reason}\n"



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
        collected = await asyncio.gather(
            *[
                _collect_task_chunks(
                    config,
                    task,
                    messages,
                    run_context,
                    workspace_path,
                    tool_specs,
                )
                for task in batch
            ]
        )
        for task, chunks in collected:
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
            remapped, next_block_index = _remap_collected_chunks(chunks, next_block_index)
            for chunk in remapped:
                yield chunk, next_block_index
        await _refresh_and_record_workspace_conflicts(config, run_context)

    refresh_workspace_conflicts(run_context)
    final_summary = _summary_text(task_sequence, task_states, run_context)
    await _memory_finish_run(config, run_context, "done", final_summary)
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        final_summary,
    ):
        yield chunk, updated_block_index


async def _collect_task_chunks(
    config: Mapping[str, Any],
    task: SubTask,
    messages: list[ChatMessage],
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
) -> tuple[SubTask, list[StreamChunk]]:
    chunks: list[StreamChunk] = []
    async for chunk, _updated_block_index in _run_task(
        config,
        task,
        messages,
        0,
        run_context,
        workspace_path,
        tool_specs,
    ):
        chunks.append(chunk)
    return task, chunks


def _remap_collected_chunks(
    chunks: list[StreamChunk],
    next_block_index: int,
) -> tuple[list[StreamChunk], int]:
    index_map: dict[int, int] = {}
    remapped: list[StreamChunk] = []
    for chunk in chunks:
        if chunk.block_index is None:
            remapped.append(chunk)
            continue
        source_index = chunk.block_index
        if source_index not in index_map:
            index_map[source_index] = next_block_index
            next_block_index += 1
        remapped.append(chunk.model_copy(update={"block_index": index_map[source_index]}))
    return remapped, next_block_index


async def _refresh_and_record_workspace_conflicts(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
) -> None:
    conflicts = refresh_workspace_conflicts(run_context)
    for conflict in conflicts:
        path = str(conflict.get("path") or "")
        writers = conflict.get("writers")
        writer_keys = []
        if isinstance(writers, list):
            for writer in writers:
                if not isinstance(writer, dict):
                    continue
                task_id = writer.get("task_id")
                agent_id = writer.get("agent_id")
                if isinstance(task_id, str) and isinstance(agent_id, str):
                    writer_keys.append(f"{task_id}:{agent_id}")
        event_key = f"{path}|{'|'.join(sorted(writer_keys))}"
        if not path or event_key in run_context.workspace_conflict_event_keys:
            continue
        run_context.workspace_conflict_event_keys.add(event_key)
        await _memory_record_event(
            config,
            run_context,
            event_type="workspace_conflict_detected",
            payload=conflict,
        )


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


async def _review_repair_task(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    review_task: SubTask,
    review_result: TaskResult,
    run_context: OrchestratorRunContext,
) -> SubTask | None:
    if review_task.task_type != "review" or not review_result.attempts:
        return None
    final_attempt = review_result.attempts[-1]
    if final_attempt.review_outcome not in {"failed", "needs_repair"}:
        return None
    source_task = _review_source_task(tasks, review_task)
    repair_agent = _repair_agent_for_review(tasks, review_task, source_task)
    if repair_agent is None:
        return None
    task_id = _unique_dynamic_task_id(f"{review_task.task_id}-repair", tasks)
    reviewed_ids = review_task.review_of or review_task.depends_on
    title = (
        f"Repair {source_task.title} after review"
        if source_task is not None
        else f"Repair {review_task.title} outcome"
    )
    review_text = _truncate_preserving_edges(final_attempt.text_preview, 1600)
    expected_output = source_task.expected_output if source_task is not None else None
    repair_task = SubTask(
        task_id=task_id,
        agent_id=repair_agent,
        title=title,
        instruction=(
            "Agent-to-Agent Repair Thread. A review agent completed a handoff review "
            f"for task(s) {', '.join(reviewed_ids)} and returned "
            f"review_outcome: {final_attempt.review_outcome}.\n\n"
            f"Review findings: {review_text}\n\n"
            "Repair the concrete issues in the existing workspace artifacts. Use the "
            "Previous sub-agent results context to locate artifacts, diffs/file "
            "changes, tool outputs, evaluation results, or deployment status. Return "
            "the repaired files and a concise confirmation. Do not introduce unrelated "
            "deliverables."
        ),
        depends_on=(review_task.task_id,),
        priority=review_task.priority + 1,
        expected_output=expected_output,
        include_history=True,
        task_type="repair",
        review_of=tuple(reviewed_ids),
        handoff_reason=(
            f"Repair requested by @{final_attempt.agent_id} review "
            f"({final_attempt.review_outcome})"
        ),
    )
    await _memory_record_event(
        config,
        run_context,
        event_type="agent_review_repair_scheduled",
        task_id=review_task.task_id,
        agent_id=repair_agent,
        payload={
            "repair_task_id": task_id,
            "review_of": list(reviewed_ids),
            "outcome": final_attempt.review_outcome,
        },
    )
    return repair_task


def _review_source_task(tasks: list[SubTask], review_task: SubTask) -> SubTask | None:
    reviewed_ids = review_task.review_of or review_task.depends_on
    if not reviewed_ids:
        return None
    reviewed_id = reviewed_ids[0]
    for task in tasks:
        if task.task_id == reviewed_id:
            return task
    return None


def _repair_agent_for_review(
    tasks: list[SubTask],
    review_task: SubTask,
    source_task: SubTask | None,
) -> str | None:
    if source_task is not None and source_task.agent_id != "orchestrator":
        return source_task.agent_id
    for task in tasks:
        if task.agent_id not in {"orchestrator", review_task.agent_id}:
            return task.agent_id
    return None


def _review_outcome(text: str, state: TaskState) -> str:
    if state != TaskState.SUCCEEDED:
        return "failed"
    normalized = text.strip().lower()
    match = re.search(
        r"(?im)^\s*review[_ -]?outcome\s*[:：]\s*([^\n]+)", normalized
    )
    value = match.group(1).strip() if match else normalized
    if any(
        marker in value
        for marker in ("needs_repair", "needs repair", "repair", "需修复", "需要修复")
    ):
        return "needs_repair"
    if any(marker in value for marker in ("failed", "fail", "不通过", "未通过")):
        return "failed"
    if any(marker in value for marker in ("passed", "pass", "approved", "通过")):
        return "passed"
    return "unknown"


def _unique_dynamic_task_id(base: str, tasks: list[SubTask]) -> str:
    existing = {task.task_id for task in tasks}
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


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


def _parallel_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_parallel_enabled") is True


def _parallel_max_concurrency(config: Mapping[str, Any]) -> int:
    value = config.get("orchestrator_parallel_max_concurrency", 3)
    if isinstance(value, bool) or not isinstance(value, int):
        return 3
    return max(1, min(value, 10))


def _changes_for_attempt_artifacts(
    changes: dict[str, list[str]],
    artifact_paths: list[str],
) -> dict[str, list[str]]:
    if not artifact_paths:
        return changes
    allowed = set(artifact_paths)
    return {
        key: [path for path in paths if path in allowed]
        for key, paths in changes.items()
    }


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
    return result.final_state in {
        TaskState.FAILED,
        TaskState.ARTIFACT_MISSING,
        TaskState.EVALUATION_FAILED,
    }


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


async def _artifact_file_blocks(
    config: Mapping[str, Any],
    workspace_path: Path | None,
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    next_block_index: int,
    agent_id: str,
) -> tuple[list[StreamChunk], int]:
    if workspace_path is None or not attempt.artifact_paths:
        return [], next_block_index
    conversation_id = config.get("conversation_id")
    blocks: list[StreamChunk] = []
    for artifact_path in attempt.artifact_paths:
        target = _safe_workspace_file(workspace_path, artifact_path)
        if target is None:
            continue
        metadata = build_artifact_metadata(target, artifact_path)
        if metadata.artifact_kind not in {"document", "ppt", "image", "archive"}:
            continue
        evaluation_payloads = _evaluation_results_payload(attempt.evaluation_results)
        artifact_evaluation_results = evaluation_results_for_artifact(
            metadata.path,
            evaluation_payloads,
        )
        evaluation_status = evaluation_status_for_artifact(
            metadata.path,
            evaluation_payloads,
        )
        payload: dict[str, Any] = {
            "path": metadata.path,
            "filename": metadata.filename,
            "url": _workspace_file_url(conversation_id, metadata.path),
            "size": metadata.size,
            "mime_type": metadata.mime_type,
            "artifact_kind": metadata.artifact_kind,
            "metadata": metadata.metadata,
        }
        if metadata.preview_text is not None:
            payload["preview_text"] = metadata.preview_text
            payload["preview_truncated"] = metadata.preview_truncated
        await _upsert_artifact_manifest_entry(
            config,
            workspace_path,
            task,
            attempt,
            run_context,
            agent_id,
            payload,
            evaluation_status=evaluation_status,
            evaluation_results=artifact_evaluation_results,
        )
        blocks.extend(
            [
                StreamChunk(
                    event_type="block_start",
                    block_index=next_block_index,
                    block_type="file",
                    metadata=payload,
                    agent_id=agent_id,
                ),
                StreamChunk(
                    event_type="block_end",
                    block_index=next_block_index,
                    agent_id=agent_id,
                ),
            ]
        )
        next_block_index += 1
    return blocks, next_block_index


async def _upsert_artifact_manifest_entry(
    config: Mapping[str, Any],
    workspace_path: Path,
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    agent_id: str,
    payload: dict[str, Any],
    *,
    evaluation_status: str,
    evaluation_results: list[dict[str, Any]],
) -> None:
    service_raw = config.get("orchestrator_artifact_manifest_service")
    service = (
        service_raw
        if isinstance(service_raw, ArtifactManifestService)
        else artifact_manifest_service
    )
    entry = {
        **payload,
        "agent_id": agent_id,
        "task_id": task.task_id,
        "run_id": str(run_context.memory_run_id) if run_context.memory_run_id else None,
        "preview_text": payload.get("preview_text"),
        "preview_truncated": payload.get("preview_truncated"),
        "evaluation_status": evaluation_status,
        "evaluation_results": evaluation_results,
    }
    try:
        lock = config.get("orchestrator_artifact_manifest_lock")
        if lock is None:
            service.upsert_entry(workspace_path, entry)
        else:
            async with cast(Any, lock):
                service.upsert_entry(workspace_path, entry)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "artifact_manifest_update_failed path=%s task_id=%s agent_id=%s",
            payload.get("path"),
            task.task_id,
            agent_id,
            exc_info=True,
        )
        await _memory_record_event(
            config,
            run_context,
            event_type="artifact_manifest_update_failed",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "attempt_index": attempt.attempt_index,
                "path": str(payload.get("path") or ""),
                "error": str(exc),
            },
        )


def _safe_workspace_file(workspace_path: Path, artifact_path: str) -> Path | None:
    parts = tuple(part for part in artifact_path.replace("\\", "/").split("/") if part)
    if not parts or ".." in parts:
        return None
    root = workspace_path.resolve()
    target = (root / Path(*parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None


def _workspace_file_url(conversation_id: Any, path: str) -> str:
    if not isinstance(conversation_id, UUID):
        return ""
    return f"/api/v1/workspaces/{conversation_id}/files/{quote(path, safe='/')}"


async def _run_attempt_evaluation(
    config: Mapping[str, Any],
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
    agent_id: str,
) -> None:
    if config.get("orchestrator_evaluation_enabled", True) is False:
        return
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_started",
        task_id=task.task_id,
        agent_id=agent_id,
        payload={
            "attempt_index": attempt.attempt_index,
            "artifact_paths": attempt.artifact_paths,
        },
    )
    outcome = await _evaluate_attempt(config, task, attempt, workspace_path)
    attempt.evaluation_results = list(outcome.results)
    await _run_workflow_dry_runs(config, task, attempt, run_context, agent_id)
    attempt.reflection = outcome.reflection
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_result",
        task_id=task.task_id,
        agent_id=agent_id,
        payload={
            "attempt_index": attempt.attempt_index,
            "results": _evaluation_results_payload(attempt.evaluation_results),
        },
    )
    if outcome.reflection is not None:
        reflection = _reflection_payload(outcome.reflection)
        await _memory_record_event(
            config,
            run_context,
            event_type="reflection_created",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "attempt_index": attempt.attempt_index,
                "reflection": reflection,
            },
        )
        if outcome.failed:
            attempt.state = TaskState.EVALUATION_FAILED
            attempt.error = (
                str(reflection.get("repair_instruction"))
                if reflection
                else "evaluation failed"
            )
    await _memory_record_event(
        config,
        run_context,
        event_type="evaluation_finished",
        task_id=task.task_id,
        agent_id=agent_id,
        payload={
            "attempt_index": attempt.attempt_index,
            "status": attempt.state.value,
        },
    )


async def _run_workflow_dry_runs(
    config: Mapping[str, Any],
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    agent_id: str,
) -> None:
    paths = _workflow_validation_passed_paths(attempt.evaluation_results)
    if not paths:
        return
    db = config.get("orchestrator_db_session")
    conversation_id = config.get("conversation_id")
    if not isinstance(conversation_id, UUID) or db is None:
        return
    service_raw = config.get("orchestrator_workflow_runtime_service")
    service = (
        service_raw
        if isinstance(service_raw, WorkspaceWorkflowRuntimeService)
        else WorkspaceWorkflowRuntimeService()
    )
    for path in paths:
        try:
            lock = config.get("orchestrator_workflow_runtime_lock")
            if lock is None:
                run = await service.dry_run(db, conversation_id, path=path, inputs={})
            else:
                async with cast(Any, lock):
                    run = await service.dry_run(db, conversation_id, path=path, inputs={})
            payload = {
                "evaluator": "workflow_dry_run",
                "status": "passed" if run.status == "passed" else "failed",
                "passed": run.status == "passed",
                "severity": "info" if run.status == "passed" else "major",
                "issues": []
                if run.status == "passed"
                else [
                    {
                        "code": "workflow_dry_run_failed",
                        "message": run.error or "workflow dry-run failed",
                        "evidence": path,
                        "repair_hint": "Fix the workflow runtime nodes or assertions.",
                    }
                ],
                "checked_artifacts": [path],
                "run_id": str(run.id),
                "dry_run_status": run.dry_run_status,
                "health_status": run.health_status,
            }
            attempt.evaluation_results.append(payload)
            await _memory_record_event(
                config,
                run_context,
                event_type="workflow_dry_run_completed",
                task_id=task.task_id,
                agent_id=agent_id,
                payload={
                    "path": path,
                    "run_id": str(run.id),
                    "status": run.status,
                    "runtime_status": run.runtime_status,
                    "dry_run_status": run.dry_run_status,
                    "health_status": run.health_status,
                    "node_results": run.node_results,
                },
            )
            if run.status != "passed":
                attempt.state = TaskState.EVALUATION_FAILED
                attempt.error = run.error or "workflow dry-run failed"
        except Exception as exc:  # noqa: BLE001
            attempt.evaluation_results.append(
                {
                    "evaluator": "workflow_dry_run",
                    "status": "failed",
                    "passed": False,
                    "severity": "major",
                    "issues": [
                        {
                            "code": "workflow_dry_run_error",
                            "message": str(exc),
                            "evidence": path,
                            "repair_hint": "Fix the workflow artifact and rerun dry-run.",
                        }
                    ],
                    "checked_artifacts": [path],
                    "dry_run_status": "failed",
                    "health_status": "failed",
                }
            )
            attempt.state = TaskState.EVALUATION_FAILED
            attempt.error = str(exc)


def _workflow_validation_passed_paths(results: list[Any]) -> list[str]:
    paths: list[str] = []
    for payload in _evaluation_results_payload(results):
        if payload.get("evaluator") != "workflow_validation":
            continue
        if payload.get("passed") is not True or payload.get("status") != "passed":
            continue
        checked = payload.get("checked_artifacts")
        if isinstance(checked, list):
            paths.extend(item for item in checked if isinstance(item, str) and item)
    return list(dict.fromkeys(paths))


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
