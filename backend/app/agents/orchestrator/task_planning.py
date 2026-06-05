"""Task planning and request-routing helpers for AgentHub Orchestrator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from app.agents.orchestrator._internal.planning.reviews import (
    expand_agent_review_tasks as expand_agent_review_tasks,
)
from app.agents.orchestrator._internal.planning.routing import agent_id_list as agent_id_list
from app.agents.orchestrator._internal.planning.routing import (
    direct_answer_on_planner_failure as _direct_answer_on_planner_failure,
)
from app.agents.orchestrator._internal.planning.routing import (
    direct_tasks_from_request as _direct_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.routing import (
    explicit_agent_mentions as explicit_agent_mentions,
)
from app.agents.orchestrator._internal.planning.routing import has_task_intent as has_task_intent
from app.agents.orchestrator._internal.planning.routing import (
    latest_user_request as latest_user_request,
)
from app.agents.orchestrator._internal.planning.routing import (
    strip_orchestrator_mention as strip_orchestrator_mention,
)
from app.agents.orchestrator._internal.planning.templates import derive_tasks as _derive_tasks
from app.agents.orchestrator._internal.planning.templates import (
    frontend_deploy_tasks_from_request as _frontend_deploy_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.templates import (
    fullstack_delivery_tasks_from_request as _fullstack_delivery_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.templates import (
    preserve_explicit_requirements as _preserve_explicit_requirements,
)
from app.agents.orchestrator._internal.planning.templates import (
    stabilize_frontend_deploy_tasks as _stabilize_frontend_deploy_tasks,
)
from app.agents.orchestrator._internal.planning.templates import (
    workspace_conflict_tasks_from_request as _workspace_conflict_tasks_from_request,
)
from app.agents.orchestrator.availability import scoped_runnable_agent_ids
from app.agents.orchestrator.planner import llm_planning_enabled, plan_task_payload
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage

PLANNER_PROTOCOL_ERROR_MARKERS = (
    "invalid_json",
    "empty_planner_output",
    "planner failed",
)
PORT_SERVICE_TASK_MARKERS = (
    "preview",
    "deploy",
    "port",
    "server",
    "service",
    "808",
    "预览",
    "部署",
    "端口",
    "服务",
)
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


class PlannerResolutionError(ValueError):
    """Raised when LLM planner output cannot be used as a task plan."""


async def resolve_tasks(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[SubTask]:
    raw_tasks = config.get("tasks")
    if raw_tasks is None:
        user_request = latest_user_request(messages)
        scoped_ids = scoped_runnable_agent_ids(config)
        if scoped_ids == [] and has_task_intent(user_request):
            raise PlannerResolutionError(
                "no_runnable_agent: no executable agent is available in current conversation"
            )
        direct_tasks = _direct_tasks_from_request(config, messages)
        if direct_tasks:
            return direct_tasks
        conflict_tasks = _workspace_conflict_tasks_from_request(config, messages)
        if conflict_tasks:
            return conflict_tasks
        fullstack_tasks = _fullstack_delivery_tasks_from_request(config, messages)
        if fullstack_tasks:
            return fullstack_tasks
        if not llm_planning_enabled(config):
            frontend_tasks = _frontend_deploy_tasks_from_request(config, messages)
            if frontend_tasks:
                return frontend_tasks
        if llm_planning_enabled(config):
            try:
                return await _plan_tasks_with_model(config, messages, system_prompt)
            except ValueError as exc:
                if _is_planner_protocol_error(exc):
                    frontend_tasks = _frontend_deploy_tasks_from_request(config, messages)
                    if frontend_tasks:
                        return frontend_tasks
                if planner_fallback_to_template(config):
                    return _derive_tasks(config, messages)
                raise PlannerResolutionError(str(exc)) from exc
        return _derive_tasks(config, messages)

    return _parse_task_list(raw_tasks)


def should_direct_answer_after_planner_error(
    config: Mapping[str, Any],
    exc: PlannerResolutionError,
    user_request: str | None = None,
) -> bool:
    if not _direct_answer_on_planner_failure(config):
        return False
    if user_request and has_task_intent(user_request):
        return False
    message = str(exc)
    return any(marker in message for marker in PLANNER_PROTOCOL_ERROR_MARKERS)


def _is_planner_protocol_error(exc: ValueError) -> bool:
    message = str(exc)
    return any(marker in message for marker in PLANNER_PROTOCOL_ERROR_MARKERS)


def planner_fallback_to_template(config: Mapping[str, Any]) -> bool:
    return config.get("planner_fallback_to_template") is True


def _parse_task_list(raw_tasks: object) -> list[SubTask]:
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("missing_task_plan: config.tasks must be a non-empty list")

    tasks: list[SubTask] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, Mapping):
            raise ValueError("invalid_task_plan: each task must be an object")
        tasks.append(SubTask.from_mapping(cast(Mapping[str, Any], raw_task)))
    _ensure_unique_task_ids(tasks)
    return sorted(tasks, key=lambda task: task.priority)


async def _plan_tasks_with_model(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[SubTask]:
    user_request = latest_user_request(messages)
    planner_output = await plan_task_payload(
        config,
        messages,
        system_prompt,
        user_request,
    )
    tasks = _tasks_from_planner_payload(planner_output.payload)
    _validate_planned_tasks(tasks, planner_output.allowed_agent_ids)
    tasks = _remove_port_service_tasks(tasks)
    tasks = _preserve_explicit_requirements(tasks, user_request)
    return _stabilize_frontend_deploy_tasks(
        tasks,
        user_request,
        sorted(planner_output.allowed_agent_ids),
    )


def _tasks_from_planner_payload(payload: Any) -> list[SubTask]:
    raw_tasks = payload.get("tasks") if isinstance(payload, Mapping) else payload
    return _parse_task_list(raw_tasks)


def _validate_planned_tasks(tasks: list[SubTask], allowed_agent_ids: set[str]) -> None:
    task_ids = {task.task_id for task in tasks}
    for task in tasks:
        if task.agent_id not in allowed_agent_ids:
            raise ValueError(
                f"invalid_task_plan: unknown agent_id {task.agent_id!r}"
            )
        missing_deps = [dep for dep in task.depends_on if dep not in task_ids]
        if missing_deps:
            raise ValueError(
                f"invalid_task_plan: unknown depends_on task_id {missing_deps[0]!r}"
            )


def _remove_port_service_tasks(tasks: list[SubTask]) -> list[SubTask]:
    depended_on = {dependency for task in tasks for dependency in task.depends_on}
    kept = [
        task
        for task in tasks
        if task.task_id in depended_on or not _is_port_service_task(task)
    ]
    return kept or tasks


def _is_port_service_task(task: SubTask) -> bool:
    text = f"{task.title}\n{task.instruction}".lower()
    if not any(marker in text for marker in PORT_SERVICE_TASK_MARKERS):
        return False
    return not any(marker in text for marker in ARTIFACT_TASK_MARKERS)


def _ensure_unique_task_ids(tasks: list[SubTask]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.task_id in seen:
            raise ValueError(f"invalid_task_plan: duplicate task_id {task.task_id!r}")
        seen.add(task.task_id)
