"""Agent review task expansion helpers for orchestrator planning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.planning.routing import agent_id_list
from app.agents.orchestrator._internal.planning.templates.common import (
    available_orchestrator_agent_ids,
)
from app.agents.orchestrator.types import SubTask

ARTIFACT_TASK_MARKERS = (
    "create",
    "generate",
    "write",
    "implement",
    "build",
    "file",
    "artifact",
    "html",
    "创建",
    "生成",
    "编写",
    "实现",
    "文件",
    "产物",
)
REVIEW_TASK_MARKERS = (
    "review",
    "verify",
    "check",
    "refine",
    "quality",
    "复核",
    "审核",
    "检查",
    "确认",
    "质疑",
)


def expand_agent_review_tasks(
    config: Mapping[str, Any],
    tasks: list[SubTask],
) -> list[SubTask]:
    if not _agent_review_enabled(config) or len(tasks) < 1:
        return tasks

    existing_ids = {task.task_id for task in tasks}
    reviewed_ids = {
        reviewed_id
        for task in tasks
        if task.task_type == "review"
        for reviewed_id in (task.review_of or task.depends_on)
    }
    expanded: list[SubTask] = []
    for task in tasks:
        expanded.append(task)
        if not _should_auto_review_task(task, reviewed_ids):
            continue
        reviewer = _review_agent_for_task(config, tasks, task)
        if reviewer is None:
            continue
        review_task_id = _unique_task_id(f"{task.task_id}-review", existing_ids)
        existing_ids.add(review_task_id)
        reviewed_ids.add(task.task_id)
        expanded.append(
            SubTask(
                task_id=review_task_id,
                agent_id=reviewer,
                title=f"Review {task.title}",
                instruction=_review_instruction(task),
                depends_on=(task.task_id,),
                priority=task.priority + 1,
                include_history=True,
                task_type="review",
                review_of=(task.task_id,),
                handoff_reason=(
                    f"Review handoff after @{task.agent_id} completed {task.title}"
                ),
            )
        )
    return expanded


def _agent_review_enabled(config: Mapping[str, Any]) -> bool:
    return (
        config.get("orchestrator_agent_review_enabled") is True
        or config.get("agent_to_agent_review_enabled") is True
    )


def _should_auto_review_task(task: SubTask, reviewed_ids: set[str]) -> bool:
    if task.task_id in reviewed_ids or task.task_type != "implementation":
        return False
    if task.agent_id == "orchestrator":
        return False
    text = f"{task.title}\n{task.instruction}".lower()
    if any(marker in text for marker in REVIEW_TASK_MARKERS):
        return False
    if task.expected_output:
        return True
    return any(marker in text for marker in ARTIFACT_TASK_MARKERS)


def _review_agent_for_task(
    config: Mapping[str, Any],
    tasks: list[SubTask],
    task: SubTask,
) -> str | None:
    preferred = agent_id_list(
        config.get("orchestrator_review_agent_ids", config.get("review_agent_ids"))
    )
    agent_ids = preferred or _review_candidate_agent_ids(config, tasks)
    for agent_id in agent_ids:
        if agent_id != task.agent_id and agent_id != "orchestrator":
            return agent_id
    return None


def _review_candidate_agent_ids(
    config: Mapping[str, Any],
    tasks: list[SubTask],
) -> list[str]:
    ids: list[str] = []
    for agent_id in available_orchestrator_agent_ids(config):
        ids.append(agent_id)
    sub_adapters = config.get("sub_adapters")
    if isinstance(sub_adapters, Mapping):
        ids.extend(str(agent_id) for agent_id in sub_adapters if isinstance(agent_id, str))
    ids.extend(task.agent_id for task in tasks)
    return _dedupe_agent_ids(ids)


def _dedupe_agent_ids(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        agent_id = value.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        output.append(agent_id)
    return output


def _unique_task_id(base: str, existing_ids: set[str]) -> str:
    if base not in existing_ids:
        return base
    index = 2
    while f"{base}-{index}" in existing_ids:
        index += 1
    return f"{base}-{index}"


def _review_instruction(task: SubTask) -> str:
    expected = (
        f"\nExpected artifact contract: {task.expected_output}"
        if task.expected_output
        else ""
    )
    return (
        "Agent-to-Agent Review Thread. Review the previous sub-agent handoff from "
        f"@{task.agent_id} for task `{task.task_id}` / {task.title}.\n\n"
        "Use the injected Previous sub-agent results plus any workspace artifact paths, "
        "file changes/diff summaries, tool results, evaluation output, or deployment "
        "status available in context. Reference concrete evidence by artifact path, "
        "diff/file-change summary, tool result, or deployment URL/status when present."
        f"{expected}\n\n"
        "Return exactly one explicit outcome line first: "
        "`review_outcome: passed`, `review_outcome: failed`, or "
        "`review_outcome: needs_repair`. Then list findings, questions, and the "
        "handoff confirmation. Do not create a new primary artifact unless a small "
        "review note is explicitly required; if repair is needed, describe the repair "
        "instructions for the original implementation agent."
    )
