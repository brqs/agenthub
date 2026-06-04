"""Agent review outcome parsing and repair task scheduling."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.execution.summary import (
    truncate_preserving_edges as _truncate_preserving_edges,
)
from app.agents.orchestrator._internal.memory import (
    record_event as _memory_record_event,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)


async def review_repair_task(
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
    source_task = review_source_task(tasks, review_task)
    repair_agent = repair_agent_for_review(tasks, review_task, source_task)
    if repair_agent is None:
        return None
    task_id = unique_dynamic_task_id(f"{review_task.task_id}-repair", tasks)
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


def review_source_task(tasks: list[SubTask], review_task: SubTask) -> SubTask | None:
    reviewed_ids = review_task.review_of or review_task.depends_on
    if not reviewed_ids:
        return None
    reviewed_id = reviewed_ids[0]
    for task in tasks:
        if task.task_id == reviewed_id:
            return task
    return None


def repair_agent_for_review(
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


def review_outcome(text: str, state: TaskState) -> str:
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


def unique_dynamic_task_id(base: str, tasks: list[SubTask]) -> str:
    existing = {task.task_id for task in tasks}
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"
