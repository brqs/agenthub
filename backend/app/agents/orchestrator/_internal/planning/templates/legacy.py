"""Generic legacy fallback task templates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.planning.routing import (
    agent_id_list,
    derive_direct_agent_tasks,
    latest_user_request,
)
from app.agents.orchestrator._internal.planning.templates.delivery import (
    derive_frontend_deploy_tasks,
    derive_fullstack_delivery_tasks,
)
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage


def derive_tasks(config: Mapping[str, Any], messages: list[ChatMessage]) -> list[SubTask]:
    agent_ids = agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
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
    frontend_tasks = derive_frontend_deploy_tasks(agent_ids, user_request)
    if frontend_tasks:
        return frontend_tasks

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
