"""Task planning and request-routing helpers for AgentHub Orchestrator."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
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
    fullstack_delivery_tasks_from_request as _fullstack_delivery_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.templates import (
    preserve_explicit_requirements as _preserve_explicit_requirements,
)
from app.agents.orchestrator._internal.planning.templates import (
    workspace_conflict_tasks_from_request as _workspace_conflict_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.turn_taking import (
    pure_dialogue_requested,
    turn_taking_requested,
)
from app.agents.orchestrator.availability import scoped_runnable_agent_ids
from app.agents.orchestrator.planner import llm_planning_enabled, plan_task_payload
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage

PLANNER_PROTOCOL_ERROR_MARKERS = (
    "invalid_json",
    "empty_planner_output",
    "empty_planner_tasks",
    "config.tasks must be a non-empty list",
    "planner failed",
)
EMPTY_PLANNER_TASKS_ERROR = "missing_task_plan: empty_planner_tasks"
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
CANONICAL_FULLSTACK_DELIVERY_FILES = frozenset(
    {
        "planning.md",
        "index.html",
        "styles.css",
        "app.js",
        "backend_app.py",
        "api.md",
        "backend_tests.md",
        "review.md",
    }
)
EXPLICIT_ARTIFACT_RE = re.compile(
    r"(?<![\w./-])([\w./-]+\.(?:md|html|css|js|py|ya?ml|json|csv|txt))(?![\w./-])",
    re.I,
)
MULTI_AGENT_DISTRIBUTION_MARKERS = (
    "至少两个智能体",
    "两个智能体",
    "多个智能体",
    "多智能体",
    "双智能体",
    "交由两个智能体",
    "并行开发",
    "并行执行",
    "分工协作",
    "至少两个可用 agent",
    "至少两个 agent",
    "两个可用 agent",
    "两个 agent",
    "多个可用 agent",
    "多个 agent",
    "多 agent",
    "multi-agent",
    "multi agent",
    "真实 agent 群聊",
    "真实群聊",
    "群聊",
    "独立消息",
    "自己的独立消息",
)
PREFERRED_MULTI_AGENT_ORDER = (
    "claude-code",
    "opencode-helper",
    "codex-helper",
)
PLANNING_OR_REVIEW_TASK_MARKERS = (
    "architecture",
    "architect",
    "plan",
    "planning",
    "strategy",
    "document",
    "review",
    "audit",
    "验收",
    "审阅",
    "审核",
    "评审",
    "规划",
    "方案",
    "设计文档",
    "文档",
)
IMPLEMENTATION_TASK_MARKERS = (
    "implement",
    "implementation",
    "build",
    "code",
    "frontend",
    "page",
    "html",
    "css",
    "javascript",
    "app.js",
    "index.html",
    "styles.css",
    "实现",
    "开发",
    "代码",
    "前端",
    "页面",
    "网页",
    "交互",
    "样式",
    "适配",
)
PLATFORM_FIRST_DEPLOYMENT_MARKERS = (
    "首次容器部署前",
    "first container deployment",
    "before first container",
)
PLATFORM_FIRST_NO_EDIT_MARKERS = (
    "不要修改",
    "不要让子 agent 先修复",
    "不要让子 Agent 先修复",
    "do not modify",
    "don't modify",
    "without modifying",
)
PLATFORM_DEPLOYMENT_REPAIR_MARKERS = (
    "create_deployment(kind=container)",
    "deployment_health",
    "container deployment",
    "容器部署",
)
SEQUENTIAL_PLANNING_ORDER_MARKERS = (
    "先",
    "first",
    "before implementation",
    "before development",
)
SEQUENTIAL_FOLLOWUP_ORDER_MARKERS = (
    "然后",
    "再",
    "之后",
    "随后",
    "then",
    "after",
)
REQUEST_PLANNING_MARKERS = (
    "planning.md",
    "plan.md",
    "规划",
    "方案",
    "设计文档",
    "架构",
    "document",
    "specification",
    "project plan",
)
PLANNING_BARRIER_TASK_MARKERS = (
    "planning.md",
    "plan.md",
    "规划文档",
    "架构规划",
    "方案文档",
    "技术方案",
    "项目方案",
    "project plan",
    "architecture plan",
    "technical plan",
    "specification document",
)
REVIEW_TASK_MARKERS = (
    "review",
    "审阅",
    "评审",
    "复核",
    "验收",
)
REPAIR_TASK_MARKERS = (
    "repair",
    "fix",
    "修复",
    "整改",
)


class PlannerResolutionError(ValueError):
    """Raised when LLM planner output cannot be used as a task plan."""


async def resolve_tasks(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[SubTask]:
    raw_tasks = config.get("tasks")
    if isinstance(raw_tasks, list) and not raw_tasks:
        raw_tasks = None
    if raw_tasks is None:
        user_request = latest_user_request(messages)
        scoped_ids = scoped_runnable_agent_ids(config)
        if scoped_ids == [] and has_task_intent(user_request):
            raise PlannerResolutionError(
                "no_runnable_agent: no executable agent is available in current conversation"
            )
        if _platform_first_deployment_repair_request(user_request):
            return []
        dialogue_requested = pure_dialogue_requested(user_request)
        direct_tasks = _direct_tasks_from_request(config, messages)
        if direct_tasks and not dialogue_requested:
            return direct_tasks
        if _llm_first_control_enabled(config):
            return await _resolve_tasks_llm_first(
                config,
                messages,
                system_prompt,
                user_request,
                dialogue_requested,
            )
        return await _resolve_tasks_auto(
            config,
            messages,
            system_prompt,
            user_request,
            dialogue_requested,
        )

    return _parse_task_list(raw_tasks)


async def _resolve_tasks_llm_first(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    user_request: str,
    dialogue_requested: bool,
) -> list[SubTask]:
    if llm_planning_enabled(config):
        try:
            tasks = await _plan_tasks_with_model(config, messages, system_prompt)
            if dialogue_requested:
                return _dialogue_control_tasks(tasks, config, user_request)
            return tasks
        except ValueError as exc:
            if planner_fallback_to_template(
                config
            ) or (
                _is_empty_task_list_error(exc)
                and should_fallback_to_template_after_planner_failure(user_request)
            ):
                return _legacy_template_tasks(config, messages, user_request)
            raise PlannerResolutionError(str(exc)) from exc
    return _legacy_template_tasks(config, messages, user_request)


async def _resolve_tasks_auto(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
    user_request: str,
    dialogue_requested: bool,
) -> list[SubTask]:
    if (
        dialogue_requested
        and _dialogue_llm_control_enabled(config)
        and llm_planning_enabled(config)
    ):
        try:
            tasks = await _plan_tasks_with_model(config, messages, system_prompt)
            return _dialogue_control_tasks(tasks, config, user_request)
        except ValueError as exc:
            if not _should_fallback_dialogue_planner(config, user_request, exc):
                raise PlannerResolutionError(str(exc)) from exc
    if dialogue_requested:
        tasks = _derive_tasks(config, messages)
        if tasks and all(
            task.task_type in {"conversation", "dialogue_turn"} for task in tasks
        ):
            return _preserve_explicit_requirements(tasks, user_request)
    conflict_tasks = _workspace_conflict_tasks_from_request(config, messages)
    if conflict_tasks:
        return conflict_tasks
    explicit_artifact_tasks = _explicit_agent_artifact_tasks_from_request(
        config,
        user_request,
    )
    if explicit_artifact_tasks:
        return explicit_artifact_tasks
    if not _should_skip_fullstack_template(config, user_request):
        fullstack_tasks = _fullstack_delivery_tasks_from_request(config, messages)
        if fullstack_tasks:
            return fullstack_tasks
    if llm_planning_enabled(config):
        try:
            return await _plan_tasks_with_model(config, messages, system_prompt)
        except ValueError as exc:
            if planner_fallback_to_template(
                config
            ) or should_fallback_to_template_after_planner_failure(
                user_request
            ) or _is_empty_task_list_error(exc):
                tasks = _derive_tasks(config, messages)
                tasks = balance_requested_multi_agent_plan(
                    tasks,
                    config,
                    user_request,
                )
                return _preserve_explicit_requirements(tasks, user_request)
            raise PlannerResolutionError(str(exc)) from exc
    tasks = _derive_tasks(config, messages)
    tasks = balance_requested_multi_agent_plan(tasks, config, user_request)
    return _preserve_explicit_requirements(tasks, user_request)


def _legacy_template_tasks(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    user_request: str,
) -> list[SubTask]:
    if dialogue_requested := pure_dialogue_requested(user_request):
        tasks = _derive_tasks(config, messages)
        if tasks and all(
            task.task_type in {"conversation", "dialogue_turn"} for task in tasks
        ):
            return _preserve_explicit_requirements(tasks, user_request)
        if dialogue_requested:
            return _preserve_explicit_requirements(tasks, user_request)
    conflict_tasks = _workspace_conflict_tasks_from_request(config, messages)
    if conflict_tasks:
        return conflict_tasks
    explicit_artifact_tasks = _explicit_agent_artifact_tasks_from_request(
        config,
        user_request,
    )
    if explicit_artifact_tasks:
        return explicit_artifact_tasks
    fullstack_tasks = _fullstack_delivery_tasks_from_request(config, messages)
    if fullstack_tasks:
        return fullstack_tasks
    tasks = _derive_tasks(config, messages)
    tasks = balance_requested_multi_agent_plan(tasks, config, user_request)
    return _preserve_explicit_requirements(tasks, user_request)


def _platform_first_deployment_repair_request(user_request: str) -> bool:
    normalized = user_request.lower()
    return (
        any(marker.lower() in normalized for marker in PLATFORM_FIRST_DEPLOYMENT_MARKERS)
        and any(marker.lower() in normalized for marker in PLATFORM_FIRST_NO_EDIT_MARKERS)
        and any(marker.lower() in normalized for marker in PLATFORM_DEPLOYMENT_REPAIR_MARKERS)
    )


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


def _should_skip_fullstack_template(
    config: Mapping[str, Any],
    user_request: str,
) -> bool:
    if not llm_planning_enabled(config):
        return False
    allowed_agent_ids = _allowed_agent_ids_from_config(config)
    if len(explicit_agent_mentions(list(allowed_agent_ids), user_request)) < 2:
        return False
    explicit_files = _explicit_artifact_filenames(user_request)
    if len(explicit_files) < 2:
        return False
    return bool(explicit_files - CANONICAL_FULLSTACK_DELIVERY_FILES)


def _explicit_agent_artifact_tasks_from_request(
    config: Mapping[str, Any],
    user_request: str,
) -> list[SubTask]:
    allowed_agent_ids = _configured_agent_order(config)
    if not allowed_agent_ids:
        return []
    explicit_files = _explicit_artifact_filenames(user_request)
    if len(explicit_files) < 2:
        return []
    if not explicit_files - CANONICAL_FULLSTACK_DELIVERY_FILES:
        return []

    assigned: list[tuple[str, str, int]] = []
    seen_files: set[str] = set()
    for segment_index, segment in enumerate(_request_segments(user_request)):
        segment_files = _explicit_artifact_filenames(segment)
        if not segment_files:
            continue
        mentioned_agents = explicit_agent_mentions(allowed_agent_ids, segment)
        for agent_id in mentioned_agents[:1]:
            for filename in sorted(segment_files):
                if filename in seen_files:
                    continue
                assigned.append((agent_id, filename, segment_index))
                seen_files.add(filename)

    if len(assigned) < 2:
        return []

    review_files = [
        filename
        for filename in sorted(explicit_files - seen_files)
        if "review" in filename or "审阅" in filename or "复核" in filename
    ]
    review_agent = _default_review_agent(allowed_agent_ids, assigned)
    for filename in review_files:
        assigned.append((review_agent, filename, len(assigned)))
        seen_files.add(filename)

    tasks: list[SubTask] = []
    plan_task_ids: list[str] = []
    for index, (agent_id, filename, _segment_index) in enumerate(
        sorted(assigned, key=lambda item: item[2])
    ):
        task_id = _unique_task_id(tasks, _task_id_from_filename(filename))
        is_review = _is_review_artifact(filename)
        is_plan = _is_plan_artifact(filename)
        depends_on: tuple[str, ...]
        if is_review:
            depends_on = tuple(task.task_id for task in tasks)
        elif plan_task_ids:
            depends_on = tuple(plan_task_ids)
        else:
            depends_on = ()
        task_type = "review" if is_review else "implementation"
        tasks.append(
            SubTask(
                task_id=task_id,
                agent_id=agent_id,
                title=f"Create {filename}",
                instruction=(
                    f"Create `{filename}` in the workspace root. Preserve the "
                    "explicit agent assignment, filename, current group scope, "
                    "no-preview/no-deploy constraints, attribution evidence, and "
                    "acceptance requirements from the original user request.\n\n"
                    f"Original user request:\n{user_request}"
                ),
                depends_on=depends_on,
                priority=index,
                expected_output=filename,
                task_type=task_type,
                review_of=depends_on if is_review else (),
            )
        )
        if is_plan:
            plan_task_ids.append(task_id)
    return tasks if len(tasks) >= 2 else []


def _explicit_artifact_filenames(text: str) -> set[str]:
    filenames: set[str] = set()
    for match in EXPLICIT_ARTIFACT_RE.finditer(text):
        raw = match.group(1).strip().strip("`'\"，。；;、")
        if not raw:
            continue
        filenames.add(raw.rsplit("/", 1)[-1].lower())
    return filenames


def _request_segments(text: str) -> list[str]:
    return [
        segment.strip()
        for segment in re.split(r"[\n。；;]+", text)
        if segment.strip()
    ]


def _task_id_from_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")
    return normalized or "artifact"


def _is_review_artifact(filename: str) -> bool:
    normalized = filename.lower()
    return "review" in normalized or "审阅" in normalized or "复核" in normalized


def _is_plan_artifact(filename: str) -> bool:
    normalized = filename.lower()
    return "plan" in normalized or "planning" in normalized or "方案" in normalized


def _default_review_agent(
    allowed_agent_ids: list[str],
    assigned: list[tuple[str, str, int]],
) -> str:
    if "codex-helper" in allowed_agent_ids:
        return "codex-helper"
    assigned_agents = {agent_id for agent_id, _, _ in assigned}
    return next(
        (agent_id for agent_id in allowed_agent_ids if agent_id not in assigned_agents),
        allowed_agent_ids[0],
    )


def _is_empty_task_list_error(exc: ValueError) -> bool:
    message = str(exc)
    return (
        "empty_planner_tasks" in message
        or "config.tasks must be a non-empty list" in message
    )


def planner_fallback_to_template(config: Mapping[str, Any]) -> bool:
    return config.get("planner_fallback_to_template") is True


def _llm_first_control_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_control_mode") == "llm_first"


def should_fallback_to_template_after_planner_failure(user_request: str) -> bool:
    normalized = user_request.lower()
    explicit_markers = (
        *MULTI_AGENT_DISTRIBUTION_MARKERS,
        "代码产物",
        "产物",
        "文档",
        "方案",
        "设计文档",
        "document",
        "diff",
        "部署",
        "发布",
        "上线",
        "deploy",
        "预览",
        "端口",
        "preview",
        "port",
        "浏览器",
        "质量验收",
        "移动端",
        "按钮",
        "交互",
        "review",
    )
    return any(marker in normalized for marker in explicit_markers)


def _dialogue_llm_control_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_dialogue_llm_control_enabled", True) is not False


def _should_fallback_dialogue_planner(
    config: Mapping[str, Any],
    user_request: str,
    exc: ValueError,
) -> bool:
    return (
        planner_fallback_to_template(config)
        or pure_dialogue_requested(user_request)
        or _is_planner_protocol_error(exc)
    )


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
    tasks = _normalize_planner_task_agents(
        tasks,
        config,
        user_request,
        planner_output.allowed_agent_ids,
    )
    invalid_agent_ids = _invalid_planned_agent_ids(tasks, planner_output.allowed_agent_ids)
    if invalid_agent_ids:
        retry_messages = _planner_retry_messages(
            messages,
            allowed_agent_ids=planner_output.allowed_agent_ids,
            invalid_agent_ids=invalid_agent_ids,
        )
        retry_output = await plan_task_payload(
            config,
            retry_messages,
            system_prompt,
            user_request,
        )
        retry_tasks = _tasks_from_planner_payload(retry_output.payload)
        retry_tasks = _normalize_planner_task_agents(
            retry_tasks,
            config,
            user_request,
            retry_output.allowed_agent_ids,
        )
        retry_invalid_ids = _invalid_planned_agent_ids(
            retry_tasks,
            retry_output.allowed_agent_ids,
        )
        if retry_invalid_ids:
            tasks = _remap_invalid_planned_agents(
                retry_tasks,
                config,
                user_request,
                retry_output.allowed_agent_ids,
            )
            planner_output = retry_output
        else:
            tasks = retry_tasks
            planner_output = retry_output
    _validate_planned_tasks(tasks, planner_output.allowed_agent_ids)
    tasks = _remove_port_service_tasks(tasks)
    tasks = balance_requested_multi_agent_plan(
        tasks,
        config,
        user_request,
        planner_output.allowed_agent_ids,
    )
    tasks = _preserve_explicit_primary_agent_assignment(
        tasks,
        user_request,
        planner_output.allowed_agent_ids,
    )
    tasks = normalize_llm_planned_dependencies(tasks, user_request)
    tasks = _preserve_explicit_requirements(tasks, user_request)
    _validate_planned_tasks(tasks, planner_output.allowed_agent_ids)
    return tasks


def _invalid_planned_agent_ids(
    tasks: list[SubTask],
    allowed_agent_ids: set[str],
) -> list[str]:
    invalid: list[str] = []
    seen: set[str] = set()
    for task in tasks:
        if task.agent_id in allowed_agent_ids or task.agent_id in seen:
            continue
        seen.add(task.agent_id)
        invalid.append(task.agent_id)
    return invalid


def _planner_retry_messages(
    messages: list[ChatMessage],
    *,
    allowed_agent_ids: set[str],
    invalid_agent_ids: list[str],
) -> list[ChatMessage]:
    allowed = ", ".join(sorted(allowed_agent_ids)) or "none"
    invalid = ", ".join(invalid_agent_ids)
    retry_instruction = (
        "Planner retry required: the previous task plan used agent ids that are "
        f"not in the current group scope: {invalid}. The only legal agent ids for "
        f"this conversation are: {allowed}. Return a corrected task plan using "
        "only those legal ids. Do not include unavailable or historical agents."
    )
    return [*messages, ChatMessage(role="assistant", content=retry_instruction)]


def _remap_invalid_planned_agents(
    tasks: list[SubTask],
    config: Mapping[str, Any],
    user_request: str,
    allowed_agent_ids: set[str],
) -> list[SubTask]:
    ordered_agents = _ordered_allowed_agent_ids(config, allowed_agent_ids, user_request)
    if not ordered_agents:
        raise ValueError(
            "no_runnable_agent: no executable agent is available in current conversation"
        )
    return [
        (
            replace(
                task,
                agent_id=_replacement_agent_for_orchestrator_task(task, ordered_agents),
            )
            if task.agent_id not in allowed_agent_ids
            else task
        )
        for task in tasks
    ]


def _tasks_from_planner_payload(payload: Any) -> list[SubTask]:
    raw_tasks = payload.get("tasks") if isinstance(payload, Mapping) else payload
    if isinstance(raw_tasks, list) and not raw_tasks:
        raise ValueError(EMPTY_PLANNER_TASKS_ERROR)
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


def _normalize_planner_task_agents(
    tasks: list[SubTask],
    config: Mapping[str, Any],
    user_request: str,
    allowed_agent_ids: set[str],
) -> list[SubTask]:
    if not any(task.agent_id == "orchestrator" for task in tasks):
        return tasks
    ordered_agents = _ordered_allowed_agent_ids(config, allowed_agent_ids, user_request)
    if not ordered_agents:
        return tasks
    return [
        (
            replace(
                task,
                agent_id=_replacement_agent_for_orchestrator_task(task, ordered_agents),
            )
            if task.agent_id == "orchestrator"
            else task
        )
        for task in tasks
    ]


def _replacement_agent_for_orchestrator_task(
    task: SubTask,
    ordered_agents: list[str],
) -> str:
    task_text = f"{task.task_type}\n{task.title}\n{task.instruction}".lower()
    if _is_review_task(task) or any(marker in task_text for marker in REVIEW_TASK_MARKERS):
        if "codex-helper" in ordered_agents:
            return "codex-helper"
    if _is_planning_barrier_task(task):
        if "codex-helper" in ordered_agents:
            return "codex-helper"
    if any(marker in task_text for marker in ("verify", "verification", "验收", "验证")):
        if "opencode-helper" in ordered_agents:
            return "opencode-helper"
    if _is_repair_task(task):
        if "claude-code" in ordered_agents:
            return "claude-code"
    if any(marker in task_text for marker in IMPLEMENTATION_TASK_MARKERS):
        for agent_id in ("claude-code", "opencode-helper"):
            if agent_id in ordered_agents:
                return agent_id
    return ordered_agents[0]


def _dialogue_control_tasks(
    tasks: list[SubTask],
    config: Mapping[str, Any],
    user_request: str,
) -> list[SubTask]:
    allowed_agents = _allowed_agent_ids_from_config(config)
    ordered_agents = _ordered_allowed_agent_ids(config, allowed_agents, user_request)
    dialogue_tasks = [
        task for task in tasks if task.task_type in {"conversation", "dialogue_turn"}
    ]
    if not dialogue_tasks and tasks:
        dialogue_tasks = list(tasks)
    if not dialogue_tasks:
        raise ValueError("invalid_task_plan: dialogue planner returned no dialogue tasks")

    normalized: list[SubTask] = []
    existing: list[SubTask] = []
    previous_task_id: str | None = None
    for index, task in enumerate(dialogue_tasks):
        agent_id = task.agent_id if task.agent_id in allowed_agents else ""
        if not agent_id and ordered_agents:
            agent_id = ordered_agents[index % len(ordered_agents)]
        if not agent_id:
            raise ValueError("invalid_task_plan: dialogue task has no allowed agent")
        task_id = task.task_id or f"dialogue-turn-{index + 1}"
        if any(item.task_id == task_id for item in existing):
            task_id = _unique_task_id(existing, f"dialogue-turn-{index + 1}")
        depends_on = task.depends_on
        if previous_task_id and not depends_on:
            depends_on = (previous_task_id,)
        instruction = _no_artifact_dialogue_instruction(task.instruction, user_request)
        normalized_task = replace(
            task,
            task_id=task_id,
            agent_id=agent_id,
            instruction=instruction,
            depends_on=depends_on,
            priority=index,
            expected_output="",
            task_type="dialogue_turn",
        )
        normalized.append(normalized_task)
        existing.append(normalized_task)
        previous_task_id = task_id

    if len(normalized) == 1 and len(ordered_agents) >= 2:
        normalized = _split_single_dialogue_turn_task(normalized[0], ordered_agents)
    _validate_planned_tasks(normalized, allowed_agents)
    return normalized


def _no_artifact_dialogue_instruction(instruction: str, user_request: str) -> str:
    guard = (
        "No-artifact dialogue guard: this is a pure group dialogue turn. "
        "Do not create, edit, or request workspace files, reports, code artifacts, "
        "previews, deployments, or platform tools. Speak only for yourself in the "
        "assigned role, respond to prior turns when relevant, and do not script "
        "another Agent's full reply."
    )
    if "No-artifact dialogue guard:" in instruction:
        return instruction
    return f"{instruction}\n\n{guard}\n\nOriginal user request:\n{user_request}"


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
    if not _has_port_service_marker(text):
        return False
    return not any(marker in text for marker in ARTIFACT_TASK_MARKERS)


def _has_port_service_marker(text: str) -> bool:
    for marker in PORT_SERVICE_TASK_MARKERS:
        if marker in {"port", "server", "service", "preview", "deploy"}:
            if re.search(rf"\b{re.escape(marker)}\b", text):
                return True
            continue
        if marker in text:
            return True
    return False


def normalize_llm_planned_dependencies(
    tasks: list[SubTask],
    user_request: str,
) -> list[SubTask]:
    """Add conservative graph edges when the LLM omits obvious workflow order."""
    if len(tasks) < 2:
        return tasks

    updated = list(tasks)
    planning_ids = [
        task.task_id for task in updated if _is_planning_barrier_task(task)
    ]
    if planning_ids and _sequential_planning_requested(user_request):
        planning_id_set = set(planning_ids)
        updated = [
            (
                replace(task, depends_on=(), review_of=())
                if task.task_id in planning_id_set
                else task
            )
            for task in updated
        ]
        updated = [
            (
                _with_added_dependencies(task, planning_ids)
                if _should_follow_planning_barrier(task, planning_ids)
                else task
            )
            for task in updated
        ]

    updated = [
        replace(task, review_of=()) if task.review_of and not _is_review_task(task) else task
        for task in updated
    ]

    review_ids = [task.task_id for task in updated if _is_review_task(task)]
    raw_generation_ids = [
        task.task_id
        for task in updated
        if not _is_review_task(task)
        and not _is_repair_task(task)
        and task.task_type not in {"conversation", "dialogue_turn"}
    ]
    generation_ids = [
        *planning_ids,
        *[
            task_id
            for task_id in raw_generation_ids
            if task_id not in set(planning_ids)
        ],
    ]
    if generation_ids:
        updated = [
            (
                _with_added_dependencies(task, generation_ids)
                if _is_review_task(task) and not task.review_of
                else task
            )
            for task in updated
        ]
        updated = [
            (
                replace(task, review_of=tuple(generation_ids))
                if _is_review_task(task) and not task.review_of
                else task
            )
            for task in updated
        ]

    if review_ids:
        updated = [
            (
                _with_added_dependencies(task, review_ids)
                if _is_repair_task(task)
                and not _has_dependency_from(task, set(review_ids))
                else task
            )
            for task in updated
        ]

    if planning_ids and _sequential_planning_requested(user_request):
        planning_id_set = set(planning_ids)
        updated = [
            (
                replace(task, depends_on=(), review_of=())
                if task.task_id in planning_id_set
                else task
            )
            for task in updated
        ]

    return updated


_normalize_llm_planned_dependencies = normalize_llm_planned_dependencies


def _sequential_planning_requested(user_request: str) -> bool:
    normalized = user_request.lower()
    return (
        any(marker in normalized for marker in SEQUENTIAL_PLANNING_ORDER_MARKERS)
        and any(marker in normalized for marker in SEQUENTIAL_FOLLOWUP_ORDER_MARKERS)
        and any(marker in normalized for marker in REQUEST_PLANNING_MARKERS)
    )


def _is_planning_barrier_task(task: SubTask) -> bool:
    text = "\n".join(
        part
        for part in (
            task.title,
            task.expected_output or "",
        )
        if part
    ).lower()
    return any(marker in text for marker in PLANNING_BARRIER_TASK_MARKERS)


def _should_follow_planning_barrier(
    task: SubTask,
    planning_ids: list[str],
) -> bool:
    if task.task_id in planning_ids:
        return False
    if task.task_type in {"conversation", "dialogue_turn"}:
        return False
    return task.task_type in {"implementation", "review", "repair"} or _is_review_task(
        task
    ) or _is_repair_task(task)


def _is_review_task(task: SubTask) -> bool:
    if task.task_type == "repair":
        return False
    if task.task_type == "review":
        return True
    text = _task_label_text(task)
    return any(marker in text for marker in REVIEW_TASK_MARKERS)


def _is_repair_task(task: SubTask) -> bool:
    if task.task_type == "review":
        return False
    if task.task_type == "repair":
        return True
    text = _task_label_text(task)
    return any(marker in text for marker in REPAIR_TASK_MARKERS)


def _task_label_text(task: SubTask) -> str:
    return "\n".join(
        part
        for part in (
            task.title,
            task.expected_output or "",
        )
        if part
    ).lower()


def _with_added_dependencies(
    task: SubTask,
    dependency_ids: list[str],
) -> SubTask:
    deps = list(task.depends_on)
    for dependency_id in dependency_ids:
        if dependency_id == task.task_id or dependency_id in deps:
            continue
        deps.append(dependency_id)
    if tuple(deps) == task.depends_on:
        return task
    return replace(task, depends_on=tuple(deps))


def _has_dependency_from(task: SubTask, dependency_ids: set[str]) -> bool:
    return any(dependency_id in dependency_ids for dependency_id in task.depends_on)


def balance_requested_multi_agent_plan(
    tasks: list[SubTask],
    config: Mapping[str, Any],
    user_request: str,
    allowed_agent_ids: set[str] | None = None,
) -> list[SubTask]:
    allowed_agent_ids = allowed_agent_ids or _allowed_agent_ids_from_config(config)
    ordered_agents = _ordered_allowed_agent_ids(config, allowed_agent_ids, user_request)
    if _explicit_primary_agent_id(user_request, allowed_agent_ids):
        return _avoid_self_review_tasks(tasks, ordered_agents)
    if len(tasks) == 1 and _explicit_multi_agent_distribution_requested(user_request):
        if tasks[0].task_type in {"conversation", "dialogue_turn"} and len(
            ordered_agents
        ) >= 2:
            if turn_taking_requested(user_request):
                return _split_single_dialogue_turn_task(tasks[0], ordered_agents)
            return _split_single_conversation_task(tasks[0], ordered_agents)
        split_tasks = _split_single_parallel_implementation_task(
            tasks,
            0,
            ordered_agents,
        )
        if split_tasks is not tasks:
            return _avoid_self_review_tasks(split_tasks, ordered_agents)
    if len(tasks) < 2:
        return tasks
    if not _explicit_multi_agent_distribution_requested(user_request):
        return _avoid_self_review_tasks(tasks, ordered_agents)
    if len(ordered_agents) < 2:
        return _avoid_self_review_tasks(tasks, ordered_agents)

    implementation_indices = [
        index for index, task in enumerate(tasks) if _is_parallel_implementation_task(task)
    ]
    if len(implementation_indices) == 1:
        split_tasks = _split_single_parallel_implementation_task(
            tasks,
            implementation_indices[0],
            ordered_agents,
        )
        if split_tasks is not tasks:
            return _avoid_self_review_tasks(split_tasks, ordered_agents)
    if len({task.agent_id for task in tasks if task.agent_id != "orchestrator"}) > 1:
        return _avoid_self_review_tasks(tasks, ordered_agents)
    if len(implementation_indices) < 2:
        return _avoid_self_review_tasks(tasks, ordered_agents)

    redistributed = list(tasks)
    for offset, task_index in enumerate(implementation_indices):
        task = redistributed[task_index]
        redistributed[task_index] = replace(
            task,
            agent_id=ordered_agents[offset % len(ordered_agents)],
        )
    return _avoid_self_review_tasks(redistributed, ordered_agents)


def _split_single_conversation_task(
    task: SubTask,
    ordered_agents: list[str],
) -> list[SubTask]:
    first_agent, second_agent = ordered_agents[:2]
    return [
        replace(
            task,
            agent_id=first_agent,
            title=f"{task.title} - first participant",
            instruction=(
                f"{task.instruction}\n\n"
                "Conversation split: speak as the first participant in the group "
                "dialogue. Directly contribute your own substantive points. Do not "
                "host, invite another participant, restate the assignment, or only "
                "say the task is done. Do not create files or workspace artifacts."
            ),
            expected_output="",
            task_type="conversation",
        ),
        replace(
            task,
            task_id=_unique_task_id([task], f"{task.task_id}-participant-2"),
            agent_id=second_agent,
            title=f"{task.title} - second participant",
            instruction=(
                f"{task.instruction}\n\n"
                "Conversation split: speak as the second participant and respond "
                "to the opposing view. Directly contribute your own substantive "
                "points. Do not host, invite another participant, restate the "
                "assignment, or only say the task is done. Do not create files or "
                "workspace artifacts."
            ),
            depends_on=(task.task_id,),
            priority=task.priority + 1,
            expected_output="",
            task_type="conversation",
        ),
    ]


def _split_single_dialogue_turn_task(
    task: SubTask,
    ordered_agents: list[str],
) -> list[SubTask]:
    first_agent, second_agent = ordered_agents[:2]
    first = replace(
        task,
        agent_id=first_agent,
        title=f"{task.title} - turn 1",
        instruction=(
            f"{task.instruction}\n\n"
            "Dialogue turn split: this is turn 1. Speak only for yourself. "
            "Directly state your own role, position, reasoning, and one concrete "
            "example. Do not host, invite another participant, restate the "
            "assignment, or script another Agent's full reply. Do not create "
            "files or workspace artifacts."
        ),
        expected_output="",
        task_type="dialogue_turn",
    )
    second = replace(
        task,
        task_id=_unique_task_id([task], f"{task.task_id}-turn-2"),
        agent_id=second_agent,
        title=f"{task.title} - turn 2",
        instruction=(
            f"{task.instruction}\n\n"
            "Dialogue turn split: this is turn 2. Respond to the previous turn "
            "with your own position, reasoning, and one concrete example. Do not "
            "host, invite another participant, restate the assignment, or script "
            "another Agent's full reply. Do not create files or workspace "
            "artifacts."
        ),
        depends_on=(task.task_id,),
        priority=task.priority + 1,
        expected_output="",
        task_type="dialogue_turn",
    )
    return [first, second]


def _is_parallel_implementation_task(task: SubTask) -> bool:
    if task.task_type != "implementation":
        return False
    text = f"{task.title}\n{task.instruction}".lower()
    if any(marker in text for marker in IMPLEMENTATION_TASK_MARKERS):
        return True
    return not any(marker in text for marker in PLANNING_OR_REVIEW_TASK_MARKERS)


def _split_single_parallel_implementation_task(
    tasks: list[SubTask],
    task_index: int,
    ordered_agents: list[str],
) -> list[SubTask]:
    implementation_agents = [
        agent_id
        for agent_id in ordered_agents
        if agent_id in {"claude-code", "opencode-helper"}
    ]
    if len(implementation_agents) < 2:
        return tasks

    task = tasks[task_index]
    first_agent, second_agent = implementation_agents[:2]
    second_task_id = _unique_task_id(tasks, f"{task.task_id}-parallel-2")
    first = replace(
        task,
        agent_id=first_agent,
        title=f"{task.title} - primary implementation",
        instruction=(
            f"{task.instruction}\n\n"
            "Parallel implementation split: take the primary implementation slice. "
            "Create or update the main workspace artifacts needed by this task. "
            "Do not contact other agents; coordinate only through files and the "
            "Orchestrator handoff."
        ),
    )
    second = replace(
        task,
        task_id=second_task_id,
        agent_id=second_agent,
        title=f"{task.title} - parallel implementation",
        instruction=(
            f"{task.instruction}\n\n"
            "Parallel implementation split: take a complementary implementation, "
            "polish, responsive behavior, interaction, or verification slice. "
            "Do not contact other agents; coordinate only through files and the "
            "Orchestrator handoff."
        ),
        depends_on=task.depends_on,
        priority=task.priority + 1,
    )
    updated: list[SubTask] = []
    for index, current in enumerate(tasks):
        if index == task_index:
            updated.extend([first, second])
            continue
        depends_on = current.depends_on
        if task.task_id in depends_on and second_task_id not in depends_on:
            depends_on = (*depends_on, second_task_id)
        review_of = current.review_of
        if task.task_id in review_of and second_task_id not in review_of:
            review_of = (*review_of, second_task_id)
        updated.append(replace(current, depends_on=depends_on, review_of=review_of))
    return updated


def _unique_task_id(tasks: list[SubTask], desired: str) -> str:
    existing = {task.task_id for task in tasks}
    if desired not in existing:
        return desired
    index = 2
    while f"{desired}-{index}" in existing:
        index += 1
    return f"{desired}-{index}"


def _avoid_self_review_tasks(
    tasks: list[SubTask],
    ordered_agents: list[str],
) -> list[SubTask]:
    if not ordered_agents:
        return tasks
    by_id = {task.task_id: task for task in tasks}
    updated = list(tasks)
    for index, task in enumerate(updated):
        if task.task_type != "review":
            continue
        reviewed_ids = task.review_of or task.depends_on
        reviewed_agents = {
            by_id[task_id].agent_id for task_id in reviewed_ids if task_id in by_id
        }
        if not reviewed_agents or task.agent_id not in reviewed_agents:
            continue
        replacement = next(
            (agent_id for agent_id in ordered_agents if agent_id not in reviewed_agents),
            None,
        )
        if replacement is None:
            continue
        updated[index] = replace(task, agent_id=replacement)
    return updated


def _explicit_multi_agent_distribution_requested(user_request: str) -> bool:
    normalized = user_request.lower()
    return any(marker in normalized for marker in MULTI_AGENT_DISTRIBUTION_MARKERS)


def _explicit_primary_agent_id(
    user_request: str,
    allowed_agent_ids: set[str],
) -> str | None:
    mentioned = explicit_agent_mentions(list(allowed_agent_ids), user_request)
    if len(mentioned) != 1:
        return None
    normalized = user_request.lower()
    strong_primary_markers = (
        "planned agent 必须是",
        "planned agent must be",
        "task card 的 planned agent",
        "必须先把",
        "先把任务",
        "明确交给",
        "首选 agent",
        "首选成员",
        "优先处理",
        "优先交给",
        "primary agent",
        "primary task",
    )
    if not any(marker in normalized for marker in strong_primary_markers):
        return None
    return mentioned[0]


def _preserve_explicit_primary_agent_assignment(
    tasks: list[SubTask],
    user_request: str,
    allowed_agent_ids: set[str],
) -> list[SubTask]:
    target_agent_id = _explicit_primary_agent_id(user_request, allowed_agent_ids)
    if not target_agent_id or not tasks:
        return tasks
    primary_index = next(
        (
            index
            for index, task in enumerate(tasks)
            if task.task_type not in {"conversation", "dialogue_turn"}
            and not _is_review_task(task)
            and not _is_repair_task(task)
        ),
        0,
    )
    primary_task = tasks[primary_index]
    if primary_task.agent_id == target_agent_id:
        return tasks
    updated = list(tasks)
    updated[primary_index] = replace(primary_task, agent_id=target_agent_id)
    return updated


def _ordered_allowed_agent_ids(
    config: Mapping[str, Any],
    allowed_agent_ids: set[str],
    user_request: str = "",
) -> list[str]:
    mentioned = explicit_agent_mentions(list(allowed_agent_ids), user_request)
    if len(mentioned) >= 2:
        return mentioned

    configured_ids = _configured_agent_order(config)
    preferred = [
        agent_id
        for agent_id in PREFERRED_MULTI_AGENT_ORDER
        if agent_id in allowed_agent_ids
    ]
    ordered = preferred + [
        agent_id
        for agent_id in configured_ids
        if agent_id in allowed_agent_ids and agent_id not in preferred
    ]
    if not ordered:
        ordered = sorted(allowed_agent_ids)
    seen: set[str] = set()
    result: list[str] = []
    for agent_id in ordered:
        if agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result


def _allowed_agent_ids_from_config(config: Mapping[str, Any]) -> set[str]:
    return set(_configured_agent_order(config))


def _configured_agent_order(config: Mapping[str, Any]) -> list[str]:
    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return list(scoped_ids)

    planning_agent_ids = agent_id_list(config.get("planning_agent_ids"))
    if planning_agent_ids:
        return planning_agent_ids

    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        agent_ids: list[str] = []
        for item in available_agents:
            if not isinstance(item, Mapping):
                continue
            raw_id = item.get("agent_id", item.get("id"))
            if isinstance(raw_id, str) and raw_id.strip():
                agent_ids.append(raw_id.strip())
        if agent_ids:
            return agent_ids

    return agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))


def _ensure_unique_task_ids(tasks: list[SubTask]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.task_id in seen:
            raise ValueError(f"invalid_task_plan: duplicate task_id {task.task_id!r}")
        seen.add(task.task_id)
