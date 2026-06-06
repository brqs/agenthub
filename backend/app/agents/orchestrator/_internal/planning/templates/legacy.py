"""Generic legacy fallback task templates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.planning.routing import (
    derive_direct_agent_tasks,
    latest_user_request,
)
from app.agents.orchestrator._internal.planning.templates.common import (
    available_orchestrator_agent_ids,
    preferred_agent,
)
from app.agents.orchestrator._internal.planning.templates.delivery import (
    derive_fullstack_delivery_tasks,
)
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage

GENERIC_ARCHITECT_AGENT_PREFERENCE = (
    "codex-helper",
    "claude-code",
    "opencode-helper",
)
GENERIC_PRODUCER_AGENT_PREFERENCE = (
    "claude-code",
    "opencode-helper",
    "codex-helper",
)
GENERIC_REVIEW_AGENT_PREFERENCE = (
    "opencode-helper",
    "claude-code",
    "codex-helper",
)


def derive_tasks(config: Mapping[str, Any], messages: list[ChatMessage]) -> list[SubTask]:
    agent_ids = available_orchestrator_agent_ids(config)
    if not agent_ids:
        raise ValueError(
            "missing_task_plan: config.tasks or config.managed_agent_ids is required"
        )

    user_request = latest_user_request(messages)
    direct_tasks = derive_direct_agent_tasks(agent_ids, user_request)
    if direct_tasks:
        return direct_tasks
    fullstack_tasks = derive_fullstack_delivery_tasks(agent_ids, user_request)
    if fullstack_tasks:
        return fullstack_tasks

    agent_ids = _generic_fallback_agent_order(agent_ids)

    titles = (
        "Analyze request",
        "Produce solution",
        "Review and refine",
    )
    instructions = (
        "Analyze the user's request and propose the implementation approach."
        f"\n\nRequest:\n{user_request}",
        "Implement or draft the requested result. Include concrete artifacts when useful."
        f"\n\nRequest:\n{user_request}",
        "Review the result for gaps, risks, and next steps. Keep the answer concise."
        f"\n\nRequest:\n{user_request}",
    )

    tasks: list[SubTask] = []
    for index, agent_id in enumerate(agent_ids[:3]):
        title = titles[index] if index < len(titles) else f"Subtask {index + 1}"
        instruction = instructions[index] if index < len(instructions) else user_request
        tasks.append(
            SubTask(
                task_id=f"auto-{index + 1}",
                agent_id=agent_id,
                title=title,
                instruction=instruction,
                priority=index,
            )
        )
    return tasks


def _generic_fallback_agent_order(agent_ids: list[str]) -> list[str]:
    remaining = list(dict.fromkeys(agent_ids))
    ordered: list[str] = []
    for preference in (
        GENERIC_ARCHITECT_AGENT_PREFERENCE,
        GENERIC_PRODUCER_AGENT_PREFERENCE,
        GENERIC_REVIEW_AGENT_PREFERENCE,
    ):
        selected = preferred_agent(remaining, preference)
        if selected is None:
            continue
        ordered.append(selected)
        remaining = [agent_id for agent_id in remaining if agent_id != selected]
    ordered.extend(remaining)
    return ordered
