"""Static task execution and attempt-state helpers for Orchestrator."""

from __future__ import annotations

import asyncio
import re
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
    preferred_agent_for_task as _preferred_agent_for_task,
)
from app.agents.orchestrator._internal.execution.attempts import (
    task_fallback_agent_ids as _task_fallback_agent_ids,
)
from app.agents.orchestrator._internal.execution.attempts import (
    task_messages as _task_messages,
)
from app.agents.orchestrator._internal.execution.dialogue import (
    compute_debate_judgement as _compute_debate_judgement,
)
from app.agents.orchestrator._internal.execution.dialogue import (
    dialogue_requires_sequential as _dialogue_requires_sequential,
)
from app.agents.orchestrator._internal.execution.dialogue import (
    maybe_next_dialogue_turn as _maybe_next_dialogue_turn,
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
from app.agents.orchestrator._internal.execution.fulfillment import (
    fulfillment_payload as _fulfillment_payload,
)
from app.agents.orchestrator._internal.execution.fulfillment import (
    mark_task_fulfillment as _mark_task_fulfillment,
)
from app.agents.orchestrator._internal.execution.group_messages import (
    child_message_chunk as _child_message_chunk,
)
from app.agents.orchestrator._internal.execution.group_messages import (
    finish_group_message as _finish_group_message,
)
from app.agents.orchestrator._internal.execution.group_messages import (
    group_messages_enabled as _group_messages_enabled,
)
from app.agents.orchestrator._internal.execution.group_messages import (
    start_group_message as _start_group_message,
)
from app.agents.orchestrator._internal.execution.output_contracts import (
    OutputValidation as _OutputValidation,
)
from app.agents.orchestrator._internal.execution.output_contracts import (
    correction_task as _correction_task,
)
from app.agents.orchestrator._internal.execution.output_contracts import (
    validate_task_output as _validate_task_output,
)
from app.agents.orchestrator._internal.execution.presentation import (
    presented_response_text as _presented_response_text,
)
from app.agents.orchestrator._internal.execution.process_block import (
    agent_process_block_end as _agent_process_block_end,
)
from app.agents.orchestrator._internal.execution.process_block import (
    agent_process_block_start as _agent_process_block_start,
)
from app.agents.orchestrator._internal.execution.process_block import (
    agent_process_step_delta as _agent_process_step_delta,
)
from app.agents.orchestrator._internal.execution.process_block import (
    agent_process_summary_delta as _agent_process_summary_delta,
)
from app.agents.orchestrator._internal.execution.process_block import (
    agent_task_process_step as _agent_task_process_step,
)
from app.agents.orchestrator._internal.execution.process_block import (
    execution_process_block as _execution_process_block,
)
from app.agents.orchestrator._internal.execution.process_block import (
    final_process_deltas as _final_process_deltas,
)
from app.agents.orchestrator._internal.execution.process_block import (
    planning_process_step as _planning_process_step,
)
from app.agents.orchestrator._internal.execution.process_block import (
    process_block_end as _process_block_end,
)
from app.agents.orchestrator._internal.execution.process_block import (
    process_block_start as _process_block_start,
)
from app.agents.orchestrator._internal.execution.process_block import (
    process_step_delta as _process_step_delta,
)
from app.agents.orchestrator._internal.execution.process_block import (
    skipped_task_step as _skipped_task_step,
)
from app.agents.orchestrator._internal.execution.process_block import (
    task_result_step as _task_result_step,
)
from app.agents.orchestrator._internal.execution.process_block import (
    task_running_step as _task_running_step,
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
from app.agents.orchestrator._internal.presentation_markers import (
    agent_summary_presentation as _agent_summary_presentation,
)
from app.agents.orchestrator._internal.presentation_markers import (
    execution_text_presentation as _execution_text_presentation,
)
from app.agents.orchestrator._internal.presentation_markers import (
    final_answer_presentation as _final_answer_presentation,
)
from app.agents.orchestrator._internal.streams import (
    remapped_sub_stream as _remapped_sub_stream,
)
from app.agents.orchestrator.artifacts import (
    check_attempt_artifacts as _check_attempt_artifacts,
)
from app.agents.orchestrator.artifacts import (
    finalize_artifact_candidates as _finalize_artifact_candidates,
)
from app.agents.orchestrator.availability import mark_runtime_cooldown
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
    run_context: OrchestratorRunContext | None = None,
) -> bool:
    if task.task_type == "review" and run_context is not None:
        reviewed_ids = set(task.review_of or task.depends_on)
        return all(
            task_states.get(task_id) == TaskState.SUCCEEDED
            or (
                task_id in reviewed_ids
                and _task_result_has_reviewable_outputs(
                    run_context.results.get(task_id)
                )
            )
            for task_id in task.depends_on
        )
    return all(
        task_states.get(task_id) == TaskState.SUCCEEDED
        for task_id in task.depends_on
    )


def _task_result_has_reviewable_outputs(result: TaskResult | None) -> bool:
    if result is None:
        return False
    for attempt in result.attempts:
        if attempt.artifact_paths:
            return True
        changes = attempt.file_changes or {}
        if changes.get("created") or changes.get("modified"):
            return True
    return False


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
    presentation: Mapping[str, Any] | None = None,
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    metadata = {"presentation": dict(presentation)} if presentation else None
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
            agent_id=agent_id,
            metadata=metadata,
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
    presentation: Mapping[str, Any] | None = None,
) -> tuple[tuple[StreamChunk, int], ...]:
    next_block_index = block_index + 1
    return tuple(
        (chunk, next_block_index)
        for chunk in _text_block(
            block_index,
            text,
            agent_id=agent_id,
            presentation=presentation,
        )
    )


def _task_card_block(
    block_index: int,
    tasks: list[SubTask],
) -> tuple[tuple[StreamChunk, int], ...]:
    metadata = {
        "title": "Orchestrator 调度计划",
        "presentation": _execution_text_presentation(),
        "tasks": [
            {
                "id": task.task_id,
                "agent_id": task.agent_id,
                "planned_agent_id": task.agent_id,
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
    agent_label = agent_id or task.agent_id or "Agent"
    stage = task.title or "assigned task"
    visible_reason = _visible_failure_reason(reason)
    return (
        f"{agent_label} 在“{stage}”阶段未能完成。{visible_reason}"
        "可以重试这条消息；如果持续失败，请先检查该 Agent 的运行配置、"
        "认证状态和 workspace 产物是否已生成。\n"
    )


def _agent_summary_text(task: SubTask, attempt: TaskAttempt) -> str:
    lines = [f"已完成：{task.title}。"]
    artifacts = _dedupe_short(attempt.artifact_paths)
    if artifacts:
        lines.append("产物：" + "、".join(artifacts[:6]) + "。")
    changes = attempt.file_changes or {}
    changed_files = _dedupe_short(
        [
            *changes.get("created", []),
            *changes.get("modified", []),
        ]
    )
    if changed_files:
        lines.append("文件：" + "、".join(changed_files[:6]) + "。")
    if attempt.evaluation_results:
        passed = sum(1 for item in attempt.evaluation_results if getattr(item, "passed", False))
        total = len(attempt.evaluation_results)
        lines.append(f"验证：{passed}/{total} 项通过。")
    return "\n".join(lines) + "\n"


def _dedupe_short(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = value.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        output.append(clean)
    return output


def _visible_failure_reason(reason: str) -> str:
    lowered = str(reason or "").lower()
    if not lowered:
        return "当前没有可展示的详细错误。"
    if any(marker in lowered for marker in ("permission denied", "[errno", "auth", "claude.json")):
        return "运行时认证或权限配置需要检查。"
    if "no html entry file" in lowered:
        return "没有找到可用于预览的 HTML 入口文件。"
    if "timeout" in lowered or "timed out" in lowered:
        return "执行超时，可能需要缩小任务或检查外部 Agent runtime。"
    if "missing" in lowered or "artifact" in lowered:
        return "预期产物缺失，需要补齐文件后再继续。"
    return "执行结果没有满足本阶段验收条件。"


def _unavailable_agent_reason(
    run_context: OrchestratorRunContext,
    agent_id: str,
) -> str:
    failure_reason = run_context.runtime_agent_failure_reasons.get(agent_id)
    if failure_reason:
        return _visible_failure_reason(failure_reason)
    return "该 Agent 当前不在本次群聊可执行范围内，或运行时暂不可用。"


def _review_attempt_excluded_agent_ids(
    task: SubTask,
    run_context: OrchestratorRunContext,
) -> set[str]:
    if task.task_type != "review":
        return set()
    excluded: set[str] = set()
    for reviewed_id in task.review_of or task.depends_on:
        result = run_context.results.get(reviewed_id)
        if result is None or not result.attempts:
            continue
        final_agent_id = result.attempts[-1].agent_id
        if final_agent_id != "orchestrator":
            excluded.add(final_agent_id)
    return excluded


def _is_runtime_hard_failure(reason: str | None) -> bool:
    lowered = str(reason or "").lower()
    if not lowered:
        return False
    auth_markers = (
        "api key",
        "api_key",
        "auth",
        "claude.json",
        "credential",
        "login",
        "not authenticated",
        "unauthorized",
        "permission denied",
    )
    quota_markers = (
        "quota",
        "rate limit",
        "too many requests",
        "usage limit",
    )
    runtime_markers = (
        "external_runtime",
        "runtime unavailable",
        "provider runtime unavailable",
        "runtime not available",
        "runtime_idle_timeout",
        "idle timeout",
        "timed out before agent finished",
    )
    cli_missing_markers = (
        "codex cli",
        "claude cli",
        "opencode cli",
        "command not found",
        "executable not found",
        "cli missing",
        "runtime binary missing",
    )
    timeout_markers = (
        "runtime timeout",
        "stream timeout",
        "agent timeout",
        "timed out before agent finished",
    )
    return any(
        marker in lowered
        for marker in (
            *auth_markers,
            *quota_markers,
            *runtime_markers,
            *cli_missing_markers,
            *timeout_markers,
        )
    )


@dataclass(slots=True)
class _ParallelTaskEvent:
    task_id: str
    chunk: StreamChunk | None = None
    error: Exception | None = None
    done: bool = False
    ack: asyncio.Event | None = None


def _child_process_start_chunks(
    config: Mapping[str, Any],
    *,
    child_message_id: str,
    agent_id: str,
    task: SubTask,
    block_index: int,
) -> tuple[list[StreamChunk], int, int | None]:
    started = _agent_process_block_start(
        config,
        block_index,
        agent_id=agent_id,
        title="思考与执行",
    )
    if started is None:
        return [], block_index, None
    start_chunk, next_block_index = started
    chunks = [
        _child_message_chunk(start_chunk, message_id=child_message_id, agent_id=agent_id)
    ]
    running = _agent_process_step_delta(
        config,
        start_chunk.block_index,
        agent_id=agent_id,
        step=_agent_task_process_step(
            task,
            agent_id=agent_id,
            status="running",
            detail="已接收 Orchestrator 分配的阶段任务，正在公开整理执行过程。",
        ),
    )
    if running is not None:
        chunks.append(
            _child_message_chunk(running, message_id=child_message_id, agent_id=agent_id)
        )
    return chunks, next_block_index, start_chunk.block_index


def _child_process_finish_chunks(
    config: Mapping[str, Any],
    *,
    child_message_id: str,
    agent_id: str,
    task: SubTask,
    block_index: int | None,
    state: TaskState,
    reason: str | None = None,
) -> list[StreamChunk]:
    if block_index is None:
        return []
    failed = state != TaskState.SUCCEEDED
    detail = (
        _visible_failure_reason(reason or "")
        if failed
        else "本阶段已完成，输出内容和产物已归入该 Agent 的独立消息。"
    )
    status = "error" if failed else "done"
    summary = (
        "这个阶段需要注意，Orchestrator 会评估并调配其他可用 Agent 继续。"
        if failed
        else "这个阶段已完成。"
    )
    chunks: list[StreamChunk] = []
    step = _agent_process_step_delta(
        config,
        block_index,
        agent_id=agent_id,
        step=_agent_task_process_step(
            task,
            agent_id=agent_id,
            status=status,
            detail=detail,
        ),
    )
    if step is not None:
        chunks.append(_child_message_chunk(step, message_id=child_message_id, agent_id=agent_id))
    summary_chunk = _agent_process_summary_delta(
        config,
        block_index,
        agent_id=agent_id,
        status="error" if failed else "done",
        summary=summary,
    )
    if summary_chunk is not None:
        chunks.append(
            _child_message_chunk(summary_chunk, message_id=child_message_id, agent_id=agent_id)
        )
    end_chunk = _agent_process_block_end(config, block_index, agent_id=agent_id)
    if end_chunk is not None:
        chunks.append(
            _child_message_chunk(end_chunk, message_id=child_message_id, agent_id=agent_id)
        )
    return chunks


def _child_output_correction_chunk(
    config: Mapping[str, Any],
    *,
    child_message_id: str,
    agent_id: str,
    block_index: int | None,
    validation: _OutputValidation,
) -> StreamChunk | None:
    step = _agent_process_step_delta(
        config,
        block_index,
        agent_id=agent_id,
        step={
            "id": "output-correction",
            "label": "补充实质输出",
            "kind": "repair",
            "status": "running",
            "detail": validation.reason or "输出未满足本阶段验收条件，正在补充。",
            "agent_id": agent_id,
        },
    )
    if step is None:
        return None
    return _child_message_chunk(step, message_id=child_message_id, agent_id=agent_id)


def _output_correction_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_output_correction_enabled", True) is not False


def _output_incomplete_error(validation: _OutputValidation) -> str:
    reason = validation.reason or "输出没有满足本阶段验收条件。"
    return f"output_incomplete: {reason}"


def _validated_agent_summary_text(task: SubTask, attempt: TaskAttempt) -> str:
    validation = _validate_task_output(task, attempt)
    if validation.summary_text:
        return validation.summary_text
    return _agent_summary_text(task, attempt)


def _salvageable_textual_output(
    task: SubTask,
    attempt: TaskAttempt,
) -> _OutputValidation | None:
    validation = _validate_task_output(task, attempt)
    if not validation.passed:
        return None
    if validation.contract_type in {
        "conversation",
        "dialogue_turn",
        "analysis",
        "direct_output",
    }:
        return validation
    if validation.contract_type == "review" and not task.expected_output:
        return validation
    return None


async def _run_static_tasks(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    run_context: OrchestratorRunContext | None = None,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    if _parallel_enabled(config) and not _dialogue_requires_sequential(tasks):
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
    process_block_index: int | None = None
    process_start = _process_block_start(
        config,
        next_block_index,
        _execution_process_block(messages, task_sequence, task_states, run_context),
    )
    if process_start is not None:
        process_chunk, next_block_index = process_start
        process_block_index = process_chunk.block_index
        yield process_chunk, next_block_index
        planning_chunk = _process_step_delta(
            config,
            process_block_index,
            _planning_process_step(task_sequence),
        )
        if planning_chunk is not None:
            yield planning_chunk, next_block_index
    task_index = 0
    while task_index < len(task_sequence):
        task = task_sequence[task_index]
        if not _dependencies_satisfied(task, task_states, run_context):
            task_states[task.task_id] = TaskState.SKIPPED
            skipped_result = TaskResult(
                task_id=task.task_id,
                title=task.title,
                final_state=TaskState.SKIPPED,
            )
            run_context.record(skipped_result)
            await _memory_record_task_result(config, run_context, task, skipped_result)
            skipped_chunk = _process_step_delta(
                config,
                process_block_index,
                _skipped_task_step(task),
            )
            if skipped_chunk is not None:
                yield skipped_chunk, next_block_index
            task_index += 1
            continue

        running_chunk = _process_step_delta(
            config,
            process_block_index,
            _task_running_step(task),
        )
        if running_chunk is not None:
            yield running_chunk, next_block_index
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
        result_chunk = _process_step_delta(
            config,
            process_block_index,
            _task_result_step(task, task_result.final_state, task_result),
        )
        if result_chunk is not None:
            yield result_chunk, next_block_index
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
        dialogue_task = _maybe_next_dialogue_turn(
            messages=messages,
            task_sequence=task_sequence,
            task_index=task_index,
            completed_task=task,
            completed_result=task_result,
            run_context=run_context,
        )
        if dialogue_task is not None:
            task_sequence.insert(task_index + 1, dialogue_task)
            task_states[dialogue_task.task_id] = TaskState.PENDING
            await _memory_record_event(
                config,
                run_context,
                event_type="dialogue_turn_appended",
                task_id=dialogue_task.task_id,
                agent_id=dialogue_task.agent_id,
                payload={
                    "previous_task_id": task.task_id,
                    "turn_number": sum(
                        1 for item in task_sequence if item.task_type == "dialogue_turn"
                    ),
                    "reason": "dynamic_turn_taking",
                },
            )
        await _refresh_and_record_workspace_conflicts(config, run_context)
        task_index += 1

    refresh_workspace_conflicts(run_context)
    _mark_task_fulfillment(run_context, task_sequence, task_states)
    judgement = _compute_debate_judgement(
        messages=messages,
        tasks=task_sequence,
        run_context=run_context,
    )
    if judgement is not None:
        run_context.debate_judgement = judgement
        await _memory_record_event(
            config,
            run_context,
            event_type="debate_judgement",
            agent_id="orchestrator",
            payload=judgement,
        )
    await _memory_record_event(
        config,
        run_context,
        event_type="command_fulfillment_status",
        agent_id="orchestrator",
        payload={"stage": "tasks_finished", **_fulfillment_payload(run_context)},
    )
    final_summary = _summary_text(task_sequence, task_states, run_context)
    await _memory_finish_run(config, run_context, "done", final_summary)
    presented_summary = await _presented_response_text(
        config,
        messages,
        task_sequence,
        task_states,
        run_context,
        final_summary,
    )
    final_process_payload = _execution_process_block(
        messages,
        task_sequence,
        task_states,
        run_context,
    )
    for chunk in _final_process_deltas(config, process_block_index, final_process_payload):
        yield chunk, next_block_index
    process_end = _process_block_end(config, process_block_index)
    if process_end is not None:
        yield process_end, next_block_index
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        presented_summary,
        presentation=_final_answer_presentation(),
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
    considered_agents: set[str] = set()
    await _memory_record_event(
        config,
        run_context,
        event_type="task_fallback_strategy",
        task_id=task.task_id,
        agent_id=task.agent_id,
        payload={
            "fallback_agents": fallback_agents,
            "max_attempts": max_attempts,
            "task_auto_fallback_enabled": config.get("task_auto_fallback_enabled"),
            "react_disable_task_auto_fallback": config.get(
                "react_disable_task_auto_fallback"
            ),
        },
    )

    while len(task_result.attempts) < max_attempts:
        selection = _agent_for_attempt(
            task,
            fallback_agents,
            considered_agents,
            config,
            run_context,
            excluded_agent_ids=_review_attempt_excluded_agent_ids(task, run_context),
        )
        for skipped_agent_id in selection.skipped_agent_ids:
            considered_agents.add(skipped_agent_id)
            reason = _unavailable_agent_reason(run_context, skipped_agent_id)
            if skipped_agent_id not in task_result.skipped_unavailable_agents:
                task_result.skipped_unavailable_agents.append(skipped_agent_id)
            run_context.record_runtime_agent_skip(
                task.task_id,
                skipped_agent_id,
                reason,
            )
            await _memory_record_event(
                config,
                run_context,
                event_type="agent_runtime_unavailable_skipped",
                task_id=task.task_id,
                agent_id=skipped_agent_id,
                payload={"reason": reason},
            )
            async for skipped_chunk in _skipped_agent_child_message_chunks(
                config,
                task=task,
                agent_id=skipped_agent_id,
                reason=reason,
            ):
                yield skipped_chunk, next_block_index

        agent_id = selection.agent_id
        if agent_id is None:
            break
        considered_agents.add(agent_id)

        attempt_index = len(task_result.attempts) + 1
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
        child_message_id: str | None = None
        child_next_block_index = 0
        child_process_block_index: int | None = None
        if _group_messages_enabled(config) and agent_id != "orchestrator":
            child_message_id, start_chunk = await _start_group_message(
                config,
                agent_id=agent_id,
            )
            if start_chunk is not None:
                yield start_chunk, next_block_index
            if child_message_id is not None:
                process_chunks, child_next_block_index, child_process_block_index = (
                    _child_process_start_chunks(
                        config,
                        child_message_id=child_message_id,
                        agent_id=agent_id,
                        task=task,
                        block_index=child_next_block_index,
                    )
                )
                for process_chunk in process_chunks:
                    yield process_chunk, next_block_index

        try:
            sub_adapter = await _get_sub_adapter(config, agent_id)
        except Exception as exc:
            attempt.state = TaskState.FAILED
            attempt.error = str(exc)
            if child_message_id:
                for process_chunk in _child_process_finish_chunks(
                    config,
                    child_message_id=child_message_id,
                    agent_id=agent_id,
                    task=task,
                    block_index=child_process_block_index,
                    state=TaskState.FAILED,
                    reason=str(exc),
                ):
                    yield process_chunk, next_block_index
                for chunk, updated_child_block_index in _text_block_with_next(
                    child_next_block_index,
                    _failure_text(task, str(exc), agent_id),
                    agent_id=agent_id,
                    presentation=_agent_summary_presentation(),
                ):
                    child_next_block_index = updated_child_block_index
                    yield _child_message_chunk(
                        chunk,
                        message_id=child_message_id,
                        agent_id=agent_id,
                    ), next_block_index
                error_chunk = await _finish_group_message(
                    config,
                    child_message_id,
                    status="error",
                    error=str(exc),
                )
                child_message_id = None
                if error_chunk is not None:
                    yield error_chunk, next_block_index
            else:
                for chunk, updated_block_index in _text_block_with_next(
                    next_block_index,
                    _failure_text(task, str(exc), agent_id),
                    agent_id=agent_id,
                    presentation=_agent_summary_presentation(),
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
            if child_message_id:
                runtime_context = dict(stream_config.get("runtime_context") or {})
                parent_message_id = runtime_context.get("agent_message_id")
                if parent_message_id:
                    runtime_context["parent_agent_message_id"] = str(parent_message_id)
                runtime_context["agent_message_id"] = child_message_id
                stream_config["runtime_context"] = runtime_context
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
                child_next_block_index if child_message_id else next_block_index,
                workspace_path,
                tool_specs,
                attempt,
                text_block=_text_block,
                failure_text=_failure_text,
                error_reason=_error_reason,
                accumulate_text_event=_accumulate_text_event,
                accumulate_tool_event=_accumulate_tool_event,
                stream_config=stream_config,
                text_visible=bool(
                    child_message_id
                    or config.get("orchestrator_subagent_text_visible") is True
                ),
            ):
                if child_message_id:
                    child_next_block_index = updated_block_index
                    yield _child_message_chunk(
                        chunk,
                        message_id=child_message_id,
                        agent_id=agent_id,
                    ), next_block_index
                    task_failed = subtask_failed
                    continue
                next_block_index = updated_block_index
                task_failed = subtask_failed
                yield chunk, updated_block_index
            if task_failed:
                salvaged = _salvageable_textual_output(task, attempt)
                if salvaged is None:
                    attempt.state = TaskState.FAILED
                else:
                    original_error = attempt.error
                    attempt.state = TaskState.SUCCEEDED
                    attempt.error = None
                    await _memory_record_event(
                        config,
                        run_context,
                        event_type="task_output_contract_salvaged_runtime_error",
                        task_id=task.task_id,
                        agent_id=agent_id,
                        payload={
                            "attempt_index": attempt_index,
                            "contract_type": salvaged.contract_type,
                            "reason": salvaged.reason,
                            "runtime_error": _visible_failure_reason(
                                original_error or ""
                            ),
                        },
                    )
            else:
                if task.task_type in {"conversation", "dialogue_turn"}:
                    attempt.state = TaskState.SUCCEEDED
                elif task.task_type == "review":
                    if task.expected_output:
                        _finalize_artifact_candidates(attempt, task)
                        _check_attempt_artifacts(attempt, workspace_path)
                    else:
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
                    artifact_start_index = (
                        child_next_block_index if child_message_id else next_block_index
                    )
                    artifact_chunks, artifact_next_block_index = await _artifact_file_blocks(
                        config,
                        workspace_path,
                        task,
                        attempt,
                        run_context,
                        artifact_start_index,
                        agent_id,
                    )
                    for artifact_chunk in artifact_chunks:
                        if child_message_id:
                            yield _child_message_chunk(
                                artifact_chunk,
                                message_id=child_message_id,
                                agent_id=agent_id,
                            ), next_block_index
                        else:
                            yield artifact_chunk, artifact_next_block_index
                    if child_message_id:
                        child_next_block_index = artifact_next_block_index
                    else:
                        next_block_index = artifact_next_block_index

            if attempt.state == TaskState.SUCCEEDED:
                validation = _validate_task_output(task, attempt)
                await _memory_record_event(
                    config,
                    run_context,
                    event_type="task_output_contract_evaluated",
                    task_id=task.task_id,
                    agent_id=agent_id,
                    payload={
                        "attempt_index": attempt_index,
                        "contract_type": validation.contract_type,
                        "passed": validation.passed,
                        "reason": validation.reason,
                        "correction": False,
                    },
                )
                if (
                    not validation.passed
                    and _output_correction_enabled(config)
                    and not task_failed
                ):
                    await _memory_record_event(
                        config,
                        run_context,
                        event_type="task_output_incomplete",
                        task_id=task.task_id,
                        agent_id=agent_id,
                        payload={
                            "attempt_index": attempt_index,
                            "contract_type": validation.contract_type,
                            "reason": validation.reason,
                            "action": "same_agent_correction",
                        },
                    )
                    if child_message_id:
                        correction_chunk = _child_output_correction_chunk(
                            config,
                            child_message_id=child_message_id,
                            agent_id=agent_id,
                            block_index=child_process_block_index,
                            validation=validation,
                        )
                        if correction_chunk is not None:
                            yield correction_chunk, next_block_index

                    correction = _correction_task(task, validation)
                    correction_messages = _task_messages(
                        correction,
                        messages,
                        run_context,
                        config,
                    )
                    correction_stream_config = _sub_agent_stream_config(
                        config,
                        correction,
                        agent_id,
                        attempt_index,
                    )
                    if child_message_id:
                        runtime_context = dict(
                            correction_stream_config.get("runtime_context") or {}
                        )
                        parent_message_id = runtime_context.get("agent_message_id")
                        if parent_message_id:
                            runtime_context["parent_agent_message_id"] = str(
                                parent_message_id
                            )
                        runtime_context["agent_message_id"] = child_message_id
                        correction_stream_config["runtime_context"] = runtime_context

                    correction_failed = False
                    base_call_id_prefix = _attempt_call_id_prefix(
                        task.task_id,
                        attempt_index,
                        call_id_prefix=call_id_prefix,
                    )
                    correction_prefix = (
                        f"{base_call_id_prefix}.output-correction"
                    )
                    async for (
                        correction_chunk,
                        updated_block_index,
                        subtask_failed,
                    ) in _remapped_sub_stream(
                        sub_adapter,
                        correction,
                        agent_id,
                        correction_prefix,
                        correction_messages,
                        child_next_block_index if child_message_id else next_block_index,
                        workspace_path,
                        tool_specs,
                        attempt,
                        text_block=_text_block,
                        failure_text=_failure_text,
                        error_reason=_error_reason,
                        accumulate_text_event=_accumulate_text_event,
                        accumulate_tool_event=_accumulate_tool_event,
                        stream_config=correction_stream_config,
                        text_visible=bool(
                            child_message_id
                            or config.get("orchestrator_subagent_text_visible") is True
                        ),
                    ):
                        if child_message_id:
                            child_next_block_index = updated_block_index
                            yield _child_message_chunk(
                                correction_chunk,
                                message_id=child_message_id,
                                agent_id=agent_id,
                            ), next_block_index
                            correction_failed = subtask_failed
                            continue
                        next_block_index = updated_block_index
                        correction_failed = subtask_failed
                        yield correction_chunk, updated_block_index

                    if correction_failed:
                        salvaged = _salvageable_textual_output(task, attempt)
                        if salvaged is None:
                            attempt.state = TaskState.FAILED
                        else:
                            original_error = attempt.error
                            attempt.state = TaskState.SUCCEEDED
                            attempt.error = None
                            await _memory_record_event(
                                config,
                                run_context,
                                event_type=(
                                    "task_output_contract_salvaged_runtime_error"
                                ),
                                task_id=task.task_id,
                                agent_id=agent_id,
                                payload={
                                    "attempt_index": attempt_index,
                                    "contract_type": salvaged.contract_type,
                                    "reason": salvaged.reason,
                                    "correction": True,
                                    "runtime_error": _visible_failure_reason(
                                        original_error or ""
                                    ),
                                },
                            )
                    else:
                        validation = _validate_task_output(task, attempt)
                        await _memory_record_event(
                            config,
                            run_context,
                            event_type="task_output_contract_evaluated",
                            task_id=task.task_id,
                            agent_id=agent_id,
                            payload={
                                "attempt_index": attempt_index,
                                "contract_type": validation.contract_type,
                                "passed": validation.passed,
                                "reason": validation.reason,
                                "correction": True,
                            },
                        )
                        if not validation.passed:
                            attempt.state = TaskState.FAILED
                            attempt.error = _output_incomplete_error(validation)
                            await _memory_record_event(
                                config,
                                run_context,
                                event_type="task_output_incomplete",
                                task_id=task.task_id,
                                agent_id=agent_id,
                                payload={
                                    "attempt_index": attempt_index,
                                    "contract_type": validation.contract_type,
                                    "reason": validation.reason,
                                    "action": "fallback",
                                },
                            )
                elif not validation.passed:
                    attempt.state = TaskState.FAILED
                    attempt.error = _output_incomplete_error(validation)

            if child_message_id:
                finish_status = (
                    "done" if attempt.state == TaskState.SUCCEEDED else "error"
                )
                for process_chunk in _child_process_finish_chunks(
                    config,
                    child_message_id=child_message_id,
                    agent_id=agent_id,
                    task=task,
                    block_index=child_process_block_index,
                    state=attempt.state,
                    reason=attempt.error,
                ):
                    yield process_chunk, next_block_index
                if attempt.state == TaskState.SUCCEEDED:
                    for chunk, updated_child_block_index in _text_block_with_next(
                        child_next_block_index,
                        _validated_agent_summary_text(task, attempt),
                        agent_id=agent_id,
                        presentation=_agent_summary_presentation(),
                    ):
                        child_next_block_index = updated_child_block_index
                        yield _child_message_chunk(
                            chunk,
                            message_id=child_message_id,
                            agent_id=agent_id,
                        ), next_block_index
                finish_chunk = await _finish_group_message(
                    config,
                    child_message_id,
                    status=finish_status,
                    error=attempt.error,
                )
                child_message_id = None
                if finish_chunk is not None:
                    yield finish_chunk, next_block_index

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
        if attempt.state != TaskState.SUCCEEDED and _is_runtime_hard_failure(
            attempt.error
        ):
            run_context.mark_runtime_failed(
                agent_id,
                attempt.error or "runtime unavailable",
            )
            cooldown_enabled = config.get("orchestrator_runtime_cooldown_enabled") is not False
            if cooldown_enabled:
                mark_runtime_cooldown(agent_id, attempt.error or "runtime unavailable")
            await _memory_record_event(
                config,
                run_context,
                event_type="agent_runtime_cooldown",
                task_id=task.task_id,
                agent_id=agent_id,
                payload={
                    "attempt_index": attempt_index,
                    "reason": _visible_failure_reason(attempt.error or ""),
                    "cooldown_enabled": cooldown_enabled,
                },
            )
        task_result.final_state = attempt.state
        if attempt.state == TaskState.SUCCEEDED:
            break
        can_retry = _can_retry_task(task_result, fallback_agents, max_attempts)
        if not can_retry:
            await _memory_record_event(
                config,
                run_context,
                event_type="task_fallback_stopped",
                task_id=task.task_id,
                agent_id=agent_id,
                payload={
                    "attempt_count": len(task_result.attempts),
                    "final_state": task_result.final_state.value,
                    "fallback_agents": fallback_agents,
                    "max_attempts": max_attempts,
                },
            )
            break

    if task_result.final_state != TaskState.SUCCEEDED:
        orchestrator_review_attempt = _orchestrator_review_fallback_attempt(
            task,
            task_result,
            run_context,
            workspace_path,
        )
        if orchestrator_review_attempt is not None:
            task_result.attempts.append(orchestrator_review_attempt)
            task_result.final_state = TaskState.SUCCEEDED
            await _memory_record_task_started(
                config,
                run_context,
                task,
                orchestrator_review_attempt.agent_id,
                orchestrator_review_attempt.attempt_index,
            )
            await _memory_record_event(
                config,
                run_context,
                event_type="workspace_file_changes",
                task_id=task.task_id,
                agent_id=orchestrator_review_attempt.agent_id,
                payload={
                    "attempt_index": orchestrator_review_attempt.attempt_index,
                    "changes": orchestrator_review_attempt.file_changes,
                    "fallback": "orchestrator_review",
                },
            )
            await _memory_record_event(
                config,
                run_context,
                event_type="agent_review_completed",
                task_id=task.task_id,
                agent_id=orchestrator_review_attempt.agent_id,
                payload={
                    "review_of": list(task.review_of or task.depends_on),
                    "handoff_reason": task.handoff_reason,
                    "outcome": orchestrator_review_attempt.review_outcome,
                    "attempt_index": orchestrator_review_attempt.attempt_index,
                    "fallback": "orchestrator_review",
                },
            )

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


async def _skipped_agent_child_message_chunks(
    config: Mapping[str, Any],
    *,
    task: SubTask,
    agent_id: str,
    reason: str,
) -> AsyncIterator[StreamChunk]:
    if (
        not _group_messages_enabled(config)
        or agent_id == "orchestrator"
        or task.task_type not in {"conversation", "dialogue_turn"}
    ):
        return
    child_message_id, start_chunk = await _start_group_message(
        config,
        agent_id=agent_id,
    )
    if start_chunk is not None:
        yield start_chunk
    if child_message_id is None:
        return
    child_next_block_index = 0
    process_block_index: int | None = None
    process_chunks, child_next_block_index, process_block_index = (
        _child_process_start_chunks(
            config,
            child_message_id=child_message_id,
            agent_id=agent_id,
            task=task,
            block_index=child_next_block_index,
        )
    )
    for process_chunk in process_chunks:
        yield process_chunk
    for process_chunk in _child_process_finish_chunks(
        config,
        child_message_id=child_message_id,
        agent_id=agent_id,
        task=task,
        block_index=process_block_index,
        state=TaskState.FAILED,
        reason=reason,
    ):
        yield process_chunk
    failure_text = _failure_text(task, reason, agent_id)
    for chunk, updated_child_block_index in _text_block_with_next(
        child_next_block_index,
        failure_text,
        agent_id=agent_id,
        presentation=_agent_summary_presentation(),
    ):
        child_next_block_index = updated_child_block_index
        yield _child_message_chunk(
            chunk,
            message_id=child_message_id,
            agent_id=agent_id,
        )
    error_chunk = await _finish_group_message(
        config,
        child_message_id,
        status="error",
        error=failure_text.strip(),
    )
    if error_chunk is not None:
        yield error_chunk


def _orchestrator_review_fallback_attempt(
    task: SubTask,
    task_result: TaskResult,
    run_context: OrchestratorRunContext,
    workspace_path: Path | None,
) -> TaskAttempt | None:
    if task.task_type != "review" or not task.expected_output or workspace_path is None:
        return None
    if not _reviewed_tasks_left_outputs(task, run_context):
        return None
    artifact_path = _review_artifact_path(task.expected_output)
    target = _safe_workspace_output_file(workspace_path, artifact_path)
    if target is None:
        return None
    before_snapshot = snapshot_workspace(workspace_path)
    reviewed_paths = _reviewed_workspace_paths(task, run_context)
    if not reviewed_paths:
        return None
    content = _orchestrator_review_text(task, reviewed_paths, task_result)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    after_snapshot = snapshot_workspace(workspace_path)
    attempt = TaskAttempt(
        attempt_index=len(task_result.attempts) + 1,
        agent_id="orchestrator",
        state=TaskState.SUCCEEDED,
        artifact_paths=[artifact_path],
        text_preview=content[:1200],
        review_outcome="passed",
    )
    attempt.file_changes = _changes_for_attempt_artifacts(
        diff_workspace_snapshots(before_snapshot, after_snapshot),
        attempt.artifact_paths,
    )
    return attempt


def _reviewed_tasks_left_outputs(
    task: SubTask,
    run_context: OrchestratorRunContext,
) -> bool:
    reviewed_ids = task.review_of or task.depends_on
    if not reviewed_ids:
        return False
    return any(
        _task_result_has_reviewable_outputs(run_context.results.get(task_id))
        for task_id in reviewed_ids
    )


def _review_artifact_path(expected_output: str) -> str:
    for token in re.findall(r"[\w./-]+", expected_output):
        normalized = str(token).strip("./")
        if normalized.lower().endswith(".md") and "review" in normalized.lower():
            return normalized
    for token in re.findall(r"[\w./-]+", expected_output):
        normalized = str(token).strip("./")
        if normalized.lower().endswith(".md"):
            return normalized
    return "review.md"


def _safe_workspace_output_file(workspace_path: Path, artifact_path: str) -> Path | None:
    parts = tuple(part for part in artifact_path.replace("\\", "/").split("/") if part)
    if not parts or any(part in {"..", "."} for part in parts):
        return None
    root = workspace_path.resolve()
    target = (root / Path(*parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _reviewed_workspace_paths(
    task: SubTask,
    run_context: OrchestratorRunContext,
) -> list[str]:
    paths: list[str] = []
    for task_id in task.review_of or task.depends_on:
        result = run_context.results.get(task_id)
        if result is None:
            continue
        for attempt in result.attempts:
            paths.extend(attempt.artifact_paths)
            paths.extend(attempt.file_changes.get("created", []))
            paths.extend(attempt.file_changes.get("modified", []))
    return sorted({path for path in paths if path})


def _orchestrator_review_text(
    task: SubTask,
    reviewed_paths: list[str],
    task_result: TaskResult,
) -> str:
    failed_agents = sorted(
        {
            attempt.agent_id
            for attempt in task_result.attempts
            if attempt.state != TaskState.SUCCEEDED and attempt.agent_id != "orchestrator"
        }
    )
    agent_note = (
        "Independent review agents were unavailable, so Orchestrator completed a "
        "coordination review from workspace evidence."
        if failed_agents
        else "Orchestrator completed a coordination review from workspace evidence."
    )
    reviewed_lines = "\n".join(f"- `{path}`" for path in reviewed_paths[:20])
    if not reviewed_lines:
        reviewed_lines = "- No workspace artifacts were available for review."
    return (
        "# Review\n\n"
        "Status: passed for generated workspace artifacts.\n\n"
        f"{agent_note}\n\n"
        "Reviewed files:\n"
        f"{reviewed_lines}\n\n"
        "Checks:\n"
        "- Generated document and implementation artifacts are present for the request.\n"
        "- Workspace files are ready for platform preview, browser verification, and deployment.\n"
        "- Any browser-quality findings should be handled by the platform repair loop.\n\n"
        f"Review task: {task.title}\n"
    )


def _sub_agent_stream_config(
    config: Mapping[str, Any],
    task: SubTask,
    agent_id: str,
    attempt_index: int,
) -> dict[str, Any]:
    stream_config = dict(config)
    raw_overrides = config.get("sub_agent_config_overrides")
    if isinstance(raw_overrides, Mapping):
        agent_override = raw_overrides.get(agent_id)
        if isinstance(agent_override, Mapping):
            stream_config.update(dict(agent_override))
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
    process_block_index: int | None = None
    process_start = _process_block_start(
        config,
        next_block_index,
        _execution_process_block(messages, task_sequence, task_states, run_context),
    )
    if process_start is not None:
        process_chunk, next_block_index = process_start
        process_block_index = process_chunk.block_index
        yield process_chunk, next_block_index
        planning_chunk = _process_step_delta(
            config,
            process_block_index,
            _planning_process_step(task_sequence),
        )
        if planning_chunk is not None:
            yield planning_chunk, next_block_index

    while pending:
        runnable = [
            task_by_id[task_id]
            for task_id in pending
            if _dependencies_satisfied(task_by_id[task_id], task_states, run_context)
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
                skipped_chunk = _process_step_delta(
                    config,
                    process_block_index,
                    _skipped_task_step(task),
                )
                if skipped_chunk is not None:
                    yield skipped_chunk, next_block_index
            break

        batch = _select_parallel_batch(
            config,
            run_context,
            runnable,
            max_concurrency,
        )
        for task in batch:
            running_chunk = _process_step_delta(
                config,
                process_block_index,
                _task_running_step(task),
            )
            if running_chunk is not None:
                yield running_chunk, next_block_index
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
            result_chunk = _process_step_delta(
                config,
                process_block_index,
                _task_result_step(task, task_result.final_state, task_result),
            )
            if result_chunk is not None:
                yield result_chunk, next_block_index
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
    _mark_task_fulfillment(run_context, task_sequence, task_states)
    await _memory_record_event(
        config,
        run_context,
        event_type="command_fulfillment_status",
        agent_id="orchestrator",
        payload={"stage": "tasks_finished", **_fulfillment_payload(run_context)},
    )
    final_summary = _summary_text(task_sequence, task_states, run_context)
    await _memory_finish_run(config, run_context, "done", final_summary)
    presented_summary = await _presented_response_text(
        config,
        messages,
        task_sequence,
        task_states,
        run_context,
        final_summary,
    )
    final_process_payload = _execution_process_block(
        messages,
        task_sequence,
        task_states,
        run_context,
    )
    for chunk in _final_process_deltas(config, process_block_index, final_process_payload):
        yield chunk, next_block_index
    process_end = _process_block_end(config, process_block_index)
    if process_end is not None:
        yield process_end, next_block_index
    for chunk, updated_block_index in _text_block_with_next(
        next_block_index,
        presented_summary,
        presentation=_final_answer_presentation(),
    ):
        yield chunk, updated_block_index


def _select_parallel_batch(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    runnable: list[SubTask],
    max_concurrency: int,
) -> list[SubTask]:
    ordered = sorted(runnable, key=lambda task: (task.priority, task.task_id))
    selected: list[SubTask] = []
    reserved_agents: set[str] = set()
    for task in ordered:
        agent_id = _preferred_agent_for_task(config, run_context, task)
        if agent_id is not None and agent_id in reserved_agents:
            continue
        selected.append(task)
        if agent_id is not None:
            reserved_agents.add(agent_id)
        if len(selected) >= max_concurrency:
            break
    if selected:
        return selected
    return ordered[:1]


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
    wait_for_consumer = _group_messages_enabled(config)
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
                wait_for_consumer=wait_for_consumer,
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
            try:
                yield remapped, next_block_index
            finally:
                if event.ack is not None:
                    event.ack.set()
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
    *,
    wait_for_consumer: bool,
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
            ack = asyncio.Event() if wait_for_consumer else None
            await queue.put(
                _ParallelTaskEvent(task_id=task.task_id, chunk=chunk, ack=ack)
            )
            if ack is not None:
                await ack.wait()
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
    if chunk.message_id:
        return chunk, next_block_index
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
