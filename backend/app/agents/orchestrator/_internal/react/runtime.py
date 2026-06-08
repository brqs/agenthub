"""ReAct dynamic task-graph execution runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from app.agents.orchestrator._internal.execution.presentation import (
    presented_response_text,
)
from app.agents.orchestrator._internal.execution.process_block import (
    execution_process_block,
    final_process_deltas,
    planning_process_step,
    process_block_end,
    process_block_start,
    process_step_delta,
    task_result_step,
    task_running_step,
)
from app.agents.orchestrator._internal.presentation_markers import (
    final_answer_presentation,
)
from app.agents.orchestrator._internal.react.decision import _react_decision
from app.agents.orchestrator._internal.react.graph import _apply_react_decision
from app.agents.orchestrator._internal.react.types import ReactDecision, ReactDecisionError
from app.agents.orchestrator.types import (
    DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

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
SummaryText = Callable[[list[SubTask], Mapping[str, TaskState], OrchestratorRunContext], str]
FormatTaskResultContext = Callable[[str, TaskResult, int], str]
LatestUserRequest = Callable[[list[ChatMessage]], str]
PositiveIntConfig = Callable[[Mapping[str, Any], str, int], int]
AgentIdList = Callable[[object], list[str]]
ErrorReason = Callable[[StreamChunk], str]


class TextBlockWithNext(Protocol):
    def __call__(
        self,
        block_index: int,
        text: str,
        *,
        agent_id: str = "orchestrator",
        presentation: Mapping[str, Any] | None = None,
    ) -> Iterable[tuple[StreamChunk, int]]: ...


async def run_react_loop(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    tool_specs: list[ToolSpec] | None,
    *,
    run_context: OrchestratorRunContext | None = None,
    run_task: RunTask,
    text_block_with_next: TextBlockWithNext,
    summary_text: SummaryText,
    format_task_result_context: FormatTaskResultContext,
    latest_user_request: LatestUserRequest,
    positive_int_config: PositiveIntConfig,
    agent_id_list: AgentIdList,
    error_reason: ErrorReason,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    task_graph = list(tasks)
    task_states = {task.task_id: TaskState.PENDING for task in task_graph}
    run_context = run_context or OrchestratorRunContext()
    max_iterations = _max_iterations(config, positive_int_config)
    finish_reason: str | None = None
    process_block_index: int | None = None
    process_start = process_block_start(
        config,
        next_block_index,
        execution_process_block(messages, task_graph, task_states, run_context),
    )
    if process_start is not None:
        process_chunk, next_block_index = process_start
        process_block_index = process_chunk.block_index
        yield process_chunk, next_block_index
        planning_chunk = process_step_delta(
            config,
            process_block_index,
            planning_process_step(task_graph),
        )
        if planning_chunk is not None:
            yield planning_chunk, next_block_index

    for iteration in range(1, max_iterations + 1):
        task = _next_runnable_task(task_graph, task_states)
        observation = "No runnable task is currently available."

        if task is not None:
            running_chunk = process_step_delta(
                config,
                process_block_index,
                task_running_step(task),
            )
            if running_chunk is not None:
                yield running_chunk, next_block_index
            task_config = dict(config)
            if config.get("react_disable_task_auto_fallback") is True:
                task_config["task_auto_fallback_enabled"] = False
            async for chunk, updated_block_index in run_task(
                task_config,
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
            result_chunk = process_step_delta(
                config,
                process_block_index,
                task_result_step(
                    task,
                    run_context.results[task.task_id].final_state,
                    run_context.results[task.task_id],
                ),
            )
            if result_chunk is not None:
                yield result_chunk, next_block_index
            observation = _react_observation_text(
                task,
                run_context.results[task.task_id],
                format_task_result_context,
            )
        elif _all_tasks_terminal(task_states):
            observation = "All known tasks are terminal."

        if iteration >= max_iterations:
            finish_reason = f"max_iterations reached ({max_iterations})"
            if react_trace_visible(config):
                for chunk, updated_block_index in text_block_with_next(
                    next_block_index,
                    _react_trace_text(iteration, observation, finish_reason),
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
            break

        try:
            decision = await _react_decision(
                config,
                messages,
                task_graph,
                task_states,
                run_context,
                iteration,
                max_iterations,
                observation,
                format_task_result_context=format_task_result_context,
                latest_user_request=latest_user_request,
                positive_int_config=positive_int_config,
                agent_id_list=agent_id_list,
                error_reason=error_reason,
            )
            await _record_react_decision_event(
                config,
                run_context,
                iteration,
                observation,
                decision,
            )
            decision_chunk = process_step_delta(
                config,
                process_block_index,
                {
                    "id": "react-decision",
                    "label": "选择下一步动作",
                    "kind": "planning",
                    "status": "done",
                    "detail": _public_react_action_summary(decision),
                },
            )
            if decision_chunk is not None:
                yield decision_chunk, next_block_index
            task_graph, task_states, finish_reason = _apply_react_decision(
                decision,
                task_graph,
                task_states,
                config,
                agent_id_list,
            )
        except ReactDecisionError as exc:
            can_continue = _next_runnable_task(task_graph, task_states) is not None
            finish_reason = (
                f"ReAct replanner unavailable: {exc}; continuing existing task graph"
                if can_continue
                else f"ReAct replanner stopped: {exc}"
            )
            if react_trace_visible(config):
                for chunk, updated_block_index in text_block_with_next(
                    next_block_index,
                    _react_trace_text(iteration, observation, finish_reason),
                ):
                    next_block_index = updated_block_index
                    yield chunk, updated_block_index
            if can_continue:
                finish_reason = None
                continue
            break

        if react_trace_visible(config):
            for chunk, updated_block_index in text_block_with_next(
                next_block_index,
                _react_trace_text(
                    iteration,
                    observation,
                    _react_action_summary(decision),
                ),
            ):
                next_block_index = updated_block_index
                yield chunk, updated_block_index

        if finish_reason is not None:
            break
        if not decision.actions and _all_tasks_terminal(task_states):
            finish_reason = "all tasks are terminal"
            break

    final_summary = summary_text(task_graph, task_states, run_context)
    await _finish_memory_run(config, run_context, final_summary)
    presented_summary = await presented_response_text(
        config,
        messages,
        task_graph,
        task_states,
        run_context,
        final_summary,
    )
    final_process_payload = execution_process_block(messages, task_graph, task_states, run_context)
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
        yield chunk, updated_block_index

def react_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("react_enabled") is True

def _next_runnable_task(
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
) -> SubTask | None:
    for task in sorted(tasks, key=lambda item: item.priority):
        if task_states.get(task.task_id) != TaskState.PENDING:
            continue
        if _dependencies_satisfied(task, task_states):
            return task
    return None

def _dependencies_satisfied(
    task: SubTask,
    task_states: Mapping[str, TaskState],
) -> bool:
    return all(task_states.get(dependency) == TaskState.SUCCEEDED for dependency in task.depends_on)

def _all_tasks_terminal(task_states: Mapping[str, TaskState]) -> bool:
    return all(state != TaskState.PENDING for state in task_states.values())

def react_trace_visible(config: Mapping[str, Any]) -> bool:
    return config.get("react_trace_visible", False) is True

async def _record_react_decision_event(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
    iteration: int,
    observation: str,
    decision: ReactDecision,
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
            event_type="react_decision",
            payload={
                "iteration": iteration,
                "observation": observation,
                "actions": [dict(action) for action in decision.actions],
                "summary": decision.summary,
            },
        )
    except Exception:  # noqa: BLE001
        return

async def _finish_memory_run(
    config: Mapping[str, Any],
    run_context: OrchestratorRunContext,
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
            status="done",
            final_summary=final_summary,
        )
    except Exception:  # noqa: BLE001
        return

def _max_iterations(
    config: Mapping[str, Any],
    positive_int_config: PositiveIntConfig,
) -> int:
    return positive_int_config(config, "max_iterations", 10)

def _react_observation_text(
    task: SubTask,
    result: TaskResult,
    format_task_result_context: FormatTaskResultContext,
) -> str:
    return format_task_result_context(
        task.task_id,
        result,
        DEFAULT_TASK_RESULT_ITEM_MAX_CHARS,
    )

def _react_trace_text(iteration: int, observation: str, action_summary: str) -> str:
    lines = [
        f"ReAct step {iteration}",
        f"Observation: {observation}",
        f"Action: {action_summary}",
    ]
    return "\n".join(lines) + "\n"

def _react_action_summary(decision: ReactDecision) -> str:
    summaries: list[str] = []
    for action in decision.actions:
        action_type = action.get("type")
        if action_type == "add_task" and isinstance(action.get("task"), Mapping):
            task = action["task"]
            task_id = task.get("task_id", "<unknown>")
            agent_id = task.get("agent_id", "<unknown>")
            summaries.append(f"add_task {task_id} -> @{agent_id}")
        elif action_type == "update_task":
            summaries.append(f"update_task {action.get('task_id', '<unknown>')}")
        elif action_type == "skip_task":
            summaries.append(f"skip_task {action.get('task_id', '<unknown>')}")
        elif action_type == "finish":
            summaries.append(f"finish: {action.get('reason', 'done')}")
        else:
            summaries.append(str(action_type or "unknown"))
    return "; ".join(summaries) if summaries else "continue"


def _public_react_action_summary(decision: ReactDecision) -> str:
    if not decision.actions:
        return "继续按当前任务图执行。"
    action_types = {str(action.get("type") or "") for action in decision.actions}
    if "finish" in action_types:
        return "判断当前执行可以收尾。"
    if "add_task" in action_types:
        return "根据已完成结果补充后续公开执行步骤。"
    if "skip_task" in action_types or "update_task" in action_types:
        return "根据已完成结果调整后续公开执行步骤。"
    return "根据当前结果选择后续公开执行步骤。"
