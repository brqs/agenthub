"""Summary and context text formatting for Orchestrator execution."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage


def planning_text(tasks: list[SubTask]) -> str:
    lines = [f"Planned {len(tasks)} sub-task(s) via {plan_source(tasks)}:"]
    for index, task in enumerate(tasks, 1):
        lines.append(f"{index}. @{task.agent_id} - {task.title}")
    return "\n".join(lines) + "\n"


def plan_source(tasks: list[SubTask]) -> str:
    if all(task.task_id.startswith("auto-") for task in tasks):
        return "legacy template"
    if all(task.task_id.startswith("direct-") for task in tasks):
        return "direct routing"
    return "LLM planner/config"


def fallback_summary_text() -> str:
    return "Execution summary\n\n- fallback: single agent mode\n"


def summary_text(
    tasks: list[SubTask],
    task_states: Mapping[str, TaskState],
    run_context: OrchestratorRunContext | None = None,
) -> str:
    lines = ["Execution summary", ""]
    for task in tasks:
        state = task_states[task.task_id]
        result = run_context.results.get(task.task_id) if run_context else None
        if result is None or not result.attempts:
            lines.append(f"- {state.value}: @{task.agent_id} - {task.title}")
            continue

        final_attempt = result.attempts[-1]
        lines.append(f"- {state.value}: @{final_attempt.agent_id} - {task.title}")
        artifacts = _dedupe_strings(
            path for attempt in result.attempts for path in attempt.artifact_paths
        )
        missing = _dedupe_strings(
            path
            for attempt in result.attempts
            for path in attempt.missing_artifact_paths
        )
        if artifacts:
            lines.append(f"  artifacts: {', '.join(artifacts)}")
        if missing and state == TaskState.ARTIFACT_MISSING:
            lines.append(f"  missing: {', '.join(missing)}")
        if len(result.attempts) > 1 or state in {
            TaskState.FAILED,
            TaskState.ARTIFACT_MISSING,
        }:
            lines.append("  attempts:")
            for attempt in result.attempts:
                detail = (
                    f"  - attempt {attempt.attempt_index} "
                    f"@{attempt.agent_id}: {attempt.state.value}"
                )
                if attempt.error:
                    detail += f" - {attempt.error}"
                elif attempt.missing_artifact_paths:
                    detail += f" - missing {', '.join(attempt.missing_artifact_paths)}"
                lines.append(detail)
    return "\n".join(lines) + "\n"


def task_result_context_message(
    run_context: OrchestratorRunContext,
    task: SubTask,
    *,
    context_max_chars: int,
    item_max_chars: int,
    previous_attempt: TaskAttempt | None = None,
) -> ChatMessage | None:
    result_ids = _context_result_ids(run_context, task)
    lines: list[str] = []
    if result_ids:
        lines.append("Previous sub-agent results:")
        lines.append("")
        for task_id in result_ids:
            result = run_context.results.get(task_id)
            if result is None:
                continue
            item = format_task_result_context(task_id, result, item_max_chars)
            if item:
                lines.append(item)
    if previous_attempt is not None:
        if lines:
            lines.append("")
        lines.append("Previous attempt failure:")
        lines.append(format_attempt_context(previous_attempt, item_max_chars))
    if not lines:
        return None
    content = truncate_preserving_edges("\n".join(lines), context_max_chars)
    return ChatMessage(role="system", content=content)


def format_task_result_context(
    task_id: str,
    result: TaskResult,
    max_chars: int,
) -> str:
    if not result.attempts:
        return truncate_preserving_edges(
            f"- {task_id} {result.final_state.value}",
            max_chars,
        )
    final_attempt = result.attempts[-1]
    lines = [
        f"- {task_id} @{final_attempt.agent_id} {result.final_state.value}",
    ]
    if final_attempt.text_preview:
        lines.append(f"  Text: {final_attempt.text_preview}")
    if final_attempt.tool_summaries:
        lines.append(f"  Tools: {'; '.join(final_attempt.tool_summaries[:4])}")
    if final_attempt.artifact_paths:
        lines.append(f"  Artifacts: {', '.join(final_attempt.artifact_paths)}")
    if final_attempt.error:
        lines.append(f"  Error: {final_attempt.error}")
    if final_attempt.missing_artifact_paths:
        lines.append(f"  Missing: {', '.join(final_attempt.missing_artifact_paths)}")
    return truncate_preserving_edges("\n".join(lines), max_chars)


def format_attempt_context(attempt: TaskAttempt, max_chars: int) -> str:
    text = (
        f"- attempt {attempt.attempt_index} @{attempt.agent_id} "
        f"{attempt.state.value}"
    )
    if attempt.error:
        text += f": {attempt.error}"
    elif attempt.missing_artifact_paths:
        text += f": missing {', '.join(attempt.missing_artifact_paths)}"
    return truncate_preserving_edges(text, max_chars)


def truncate_preserving_edges(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 20:
        return normalized[:max_chars]
    head_len = max_chars // 2
    tail_len = max_chars - head_len - 5
    return f"{normalized[:head_len].rstrip()} ... {normalized[-tail_len:].lstrip()}"


def _context_result_ids(
    run_context: OrchestratorRunContext,
    task: SubTask,
) -> list[str]:
    if task.depends_on:
        return [task_id for task_id in task.depends_on if task_id in run_context.results]
    return [
        task_id
        for task_id in run_context.result_order
        if run_context.results[task_id].final_state != TaskState.PENDING
    ]


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
