"""Summary and context text formatting for Orchestrator execution."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator.evaluation import (
    evaluation_results_payload,
    failed_evaluation_lines,
    reflection_payload,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage


def planning_text(tasks: list[SubTask]) -> str:
    lines = [f"I'll handle this in {len(tasks)} step(s):"]
    for index, task in enumerate(tasks, 1):
        lines.append(f"{index}. {task.title}")
    return "\n".join(lines) + "\n"


def plan_source(tasks: list[SubTask]) -> str:
    if tasks and all(task.task_type == "conversation" for task in tasks):
        return "dialogue template"
    if all(task.task_id.startswith("auto-") for task in tasks):
        return "legacy template"
    if all(task.task_id.startswith("direct-") for task in tasks):
        return "direct routing"
    if all(task.task_id.startswith("frontend-") for task in tasks):
        return "frontend quality plan"
    return "LLM planner/config"


def fallback_summary_text() -> str:
    return (
        "I could not build a full task plan for this request, so I routed it to "
        "one available agent and returned its result.\n"
    )


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
        if task.task_type in {"review", "repair"}:
            reviewed_ids = task.review_of or task.depends_on
            if reviewed_ids:
                lines.append(f"  review_of: {', '.join(reviewed_ids)}")
            if task.handoff_reason:
                lines.append(f"  handoff: {task.handoff_reason}")
            if final_attempt.review_outcome:
                lines.append(f"  review outcome: {final_attempt.review_outcome}")
        if artifacts:
            lines.append(f"  artifacts: {', '.join(artifacts)}")
        if missing and state == TaskState.ARTIFACT_MISSING:
            lines.append(f"  missing: {', '.join(missing)}")
        conflicts = _dedupe_strings(
            path
            for attempt in result.attempts
            for path in attempt.conflict_paths
        )
        if conflicts:
            lines.append(f"  conflicts: {', '.join(conflicts)}")
        evaluation_lines = failed_evaluation_lines(final_attempt.evaluation_results)
        if final_attempt.evaluation_results:
            passed_count = sum(
                1
                for result in evaluation_results_payload(final_attempt.evaluation_results)
                if result.get("passed") is True and result.get("status") != "skipped"
            )
            failed_count = len(evaluation_lines)
            lines.append(
                f"  evaluation: {passed_count} passed"
                + (f", {failed_count} failed" if failed_count else "")
            )
        for line in _workflow_dry_run_summary_lines(final_attempt.evaluation_results):
            lines.append(f"  {line}")
        for line in _manual_review_summary_lines(final_attempt.evaluation_results):
            lines.append(f"  {line}")
        if evaluation_lines:
            for line in evaluation_lines[:6]:
                lines.append(f"  evaluation issue: {line}")
        if len(result.attempts) > 1 or state in {
            TaskState.FAILED,
            TaskState.ARTIFACT_MISSING,
            TaskState.EVALUATION_FAILED,
        } or conflicts:
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
                if attempt.conflict_paths:
                    detail += f" - conflicts {', '.join(attempt.conflict_paths)}"
                attempt_evaluation_lines = failed_evaluation_lines(
                    attempt.evaluation_results
                )
                if attempt_evaluation_lines:
                    detail += f" - evaluation {attempt_evaluation_lines[0]}"
                lines.append(detail)
    conflict_lines = _workspace_conflict_summary(run_context)
    if conflict_lines:
        lines.extend(["", "Workspace conflicts:", *conflict_lines])
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
    if final_attempt.review_outcome:
        lines.append(f"  Review outcome: {final_attempt.review_outcome}")
    if final_attempt.artifact_paths:
        lines.append(f"  Artifacts: {', '.join(final_attempt.artifact_paths)}")
    if final_attempt.error:
        lines.append(f"  Error: {final_attempt.error}")
    if final_attempt.missing_artifact_paths:
        lines.append(f"  Missing: {', '.join(final_attempt.missing_artifact_paths)}")
    if final_attempt.conflict_paths:
        lines.append(f"  Conflicts: {', '.join(final_attempt.conflict_paths)}")
    evaluation_lines = failed_evaluation_lines(final_attempt.evaluation_results)
    if evaluation_lines:
        lines.append(f"  Evaluation: {'; '.join(evaluation_lines[:4])}")
    for line in _manual_review_summary_lines(final_attempt.evaluation_results):
        lines.append(f"  {line}")
    reflection = reflection_payload(final_attempt.reflection)
    if reflection:
        repair_instruction = reflection.get("repair_instruction")
        if isinstance(repair_instruction, str) and repair_instruction:
            lines.append(f"  Repair: {repair_instruction}")
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
    if attempt.conflict_paths:
        text += f": conflicts {', '.join(attempt.conflict_paths)}"
    evaluation_lines = failed_evaluation_lines(attempt.evaluation_results)
    if evaluation_lines:
        text += f": evaluation {evaluation_lines[0]}"
    reflection = reflection_payload(attempt.reflection)
    if reflection:
        repair_instruction = reflection.get("repair_instruction")
        if isinstance(repair_instruction, str) and repair_instruction:
            text += f": repair {repair_instruction}"
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


def _workspace_conflict_summary(
    run_context: OrchestratorRunContext | None,
) -> list[str]:
    if run_context is None:
        return []
    conflicts: dict[str, list[str]] = {}
    for result in run_context.results.values():
        for conflict in result.workspace_conflicts:
            path = str(conflict.get("path") or "")
            if not path:
                continue
            writers = conflict.get("writers")
            if not isinstance(writers, list):
                continue
            labels = []
            for writer in writers:
                if not isinstance(writer, dict):
                    continue
                agent_id = writer.get("agent_id")
                task_id = writer.get("task_id")
                if isinstance(agent_id, str) and isinstance(task_id, str):
                    labels.append(f"@{agent_id}/{task_id}")
            conflicts[path] = _dedupe_strings(labels)
    return [
        f"- {path}: {', '.join(labels)}"
        for path, labels in sorted(conflicts.items())
    ]


def _workflow_dry_run_summary_lines(results: list[Any]) -> list[str]:
    lines: list[str] = []
    for payload in evaluation_results_payload(results):
        if payload.get("evaluator") != "workflow_dry_run":
            continue
        checked = payload.get("checked_artifacts")
        path = checked[0] if isinstance(checked, list) and checked else "workflow"
        status = payload.get("dry_run_status") or payload.get("status") or "unknown"
        run_id = payload.get("run_id")
        suffix = f" (run {run_id})" if isinstance(run_id, str) and run_id else ""
        lines.append(f"workflow dry-run: {path} {status}{suffix}")
    return lines


def _manual_review_summary_lines(results: list[Any]) -> list[str]:
    lines: list[str] = []
    for payload in evaluation_results_payload(results):
        if payload.get("evaluator") != "manual_review_required":
            continue
        checked = payload.get("checked_artifacts")
        artifacts = ", ".join(str(item) for item in checked) if isinstance(checked, list) else ""
        lines.append(f"manual review required: {artifacts or 'artifact'}")
    return lines
