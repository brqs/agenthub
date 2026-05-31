"""Task planning and request-routing helpers for AgentHub Orchestrator."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

from app.agents.orchestrator.artifacts import extract_artifact_paths_from_text
from app.agents.orchestrator.planner import llm_planning_enabled, plan_task_payload
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage

TASK_INTENT_MARKERS = (
    "生成",
    "创建",
    "写一个",
    "写入",
    "实现",
    "构建",
    "修改",
    "修复",
    "部署",
    "复核",
    "安排",
    "协调",
    "调用",
    "分别",
    "让 ",
    "让@",
    "build",
    "create",
    "generate",
    "write",
    "implement",
    "fix",
    "deploy",
    "review",
    "coordinate",
    "ask ",
)
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
EXPLICIT_REQUIREMENT_MARKERS = (
    "任务拆解",
    "代码产物",
    "网页预览",
    "diff",
    "验收",
    "必须",
    "需要",
    "包含",
    "带",
    "include",
    "must",
    "with",
)
FRONTEND_DEMO_MARKERS = (
    "前端",
    "网页",
    "页面",
    "html",
    "css",
    "javascript",
    "js",
    "frontend",
    "web",
)
FULLSTACK_MARKERS = (
    "前后端",
    "后端",
    "backend",
    "fullstack",
    "full-stack",
    "api.md",
    "backend_app.py",
)
PREVIEW_DEPLOY_MARKERS = (
    "部署",
    "发布",
    "上线",
    "端口",
    "预览",
    "preview",
    "deploy",
    "port",
)
QUALITY_MARKERS = (
    "浏览器",
    "质量验收",
    "移动端",
    "按钮",
    "交互",
    "browser",
    "quality",
    "mobile",
    "viewport",
)
FRONTEND_QUALITY_PLAN_MARKERS = (
    "前端开发演示",
    "任务拆解",
    "代码产物",
    "网页预览",
    "移动端适配",
    "frontend development demo",
    "front-end development demo",
    "code artifact",
    "task breakdown",
    "diff",
)
FRONTEND_AGENT_PREFERENCE = (
    "opencode-helper",
    "claude-code",
    "codex-helper",
    "web-designer",
)
FRONTEND_REVIEW_AGENT_PREFERENCE = (
    "opencode-helper",
    "codex-helper",
    "claude-code",
    "web-designer",
)
PORT_NUMBER_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")


class PlannerResolutionError(ValueError):
    """Raised when LLM planner output cannot be used as a task plan."""


async def resolve_tasks(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    system_prompt: str | None,
) -> list[SubTask]:
    raw_tasks = config.get("tasks")
    if raw_tasks is None:
        direct_tasks = _direct_tasks_from_request(config, messages)
        if direct_tasks:
            return direct_tasks
        conflict_tasks = _workspace_conflict_tasks_from_request(config, messages)
        if conflict_tasks:
            return conflict_tasks
        fullstack_tasks = _fullstack_delivery_tasks_from_request(config, messages)
        if fullstack_tasks:
            return fullstack_tasks
        if llm_planning_enabled(config):
            try:
                return await _plan_tasks_with_model(config, messages, system_prompt)
            except ValueError as exc:
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
) -> bool:
    if not _direct_answer_on_planner_failure(config):
        return False
    message = str(exc)
    return any(marker in message for marker in PLANNER_PROTOCOL_ERROR_MARKERS)


def strip_orchestrator_mention(text: str) -> str:
    return text.replace("@orchestrator", "").replace("＠orchestrator", "").strip()


def has_task_intent(text: str) -> bool:
    return any(marker in text for marker in TASK_INTENT_MARKERS)


def agent_id_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        agent_id = item.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result


def latest_user_request(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return "Handle the user's request."


def explicit_agent_mentions(agent_ids: list[str], user_request: str) -> list[str]:
    normalized = user_request.lower()
    available = set(agent_ids)
    positions: list[tuple[int, int, str]] = []

    for order, agent_id in enumerate(agent_ids):
        if agent_id not in available:
            continue
        position = _first_alias_position(normalized, _agent_aliases(agent_id))
        if position is not None:
            positions.append((position, order, agent_id))

    positions.sort()
    return [agent_id for _, _, agent_id in positions]


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


def _preserve_explicit_requirements(
    tasks: list[SubTask],
    user_request: str,
) -> list[SubTask]:
    if not _has_explicit_requirements(user_request):
        return tasks
    requirement_block = (
        "\n\nOriginal user request and acceptance requirements:\n"
        f"{user_request}\n\n"
        "Preserve every explicit deliverable in the original request. If this task "
        "creates or verifies frontend artifacts, the result must visibly satisfy any "
        "named sections/features from the request. Use the exact artifact filenames "
        "requested by the user; otherwise prefer a conventional static frontend "
        "structure. Do not create server.js, package.json server scripts, Express/"
        "Node/Vite/Next server files, or preview/server commands; platform preview "
        "handles requested ports."
    )
    return [
        replace(task, instruction=f"{task.instruction}{requirement_block}")
        for task in tasks
    ]


def _stabilize_frontend_deploy_tasks(
    tasks: list[SubTask],
    user_request: str,
    allowed_agent_ids: list[str],
) -> list[SubTask]:
    """Prefer a known-good file generation/review shape for preview quality gates."""

    fullstack_tasks = _derive_fullstack_delivery_tasks(allowed_agent_ids, user_request)
    if fullstack_tasks:
        return fullstack_tasks
    frontend_tasks = _derive_frontend_deploy_tasks(allowed_agent_ids, user_request)
    return frontend_tasks or tasks


def _frontend_deploy_tasks_from_request(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[SubTask]:
    return _derive_frontend_deploy_tasks(
        _available_orchestrator_agent_ids(config),
        latest_user_request(messages),
    )


def _workspace_conflict_tasks_from_request(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[SubTask]:
    return _derive_workspace_conflict_tasks(
        _available_orchestrator_agent_ids(config),
        latest_user_request(messages),
    )


def _fullstack_delivery_tasks_from_request(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[SubTask]:
    return _derive_fullstack_delivery_tasks(
        _available_orchestrator_agent_ids(config),
        latest_user_request(messages),
    )


def _derive_fullstack_delivery_tasks(
    agent_ids: list[str],
    user_request: str,
) -> list[SubTask]:
    if not _is_fullstack_delivery_request(user_request):
        return []
    if not agent_ids:
        return []

    planner = _preferred_agent(agent_ids, ("claude-code", "opencode-helper", "codex-helper"))
    frontend_agent = _preferred_agent(
        agent_ids,
        ("claude-code", "opencode-helper", "codex-helper"),
    )
    backend_agent = _preferred_agent(
        agent_ids,
        ("opencode-helper", "claude-code", "codex-helper"),
    )
    review_agent = _preferred_agent(
        agent_ids,
        ("codex-helper", "claude-code", "opencode-helper"),
    )
    if planner is None or frontend_agent is None or backend_agent is None or review_agent is None:
        return []

    requested_port = _requested_port(user_request)
    port_text = f" Requested preview port: {requested_port}." if requested_port else ""
    request_block = (
        "Original user request:\n"
        f"{user_request}\n\n"
        "Global rules:\n"
        "- Work only inside the current AgentHub workspace and use workspace-relative "
        "paths.\n"
        "- Do not start preview/deploy/backend servers and do not run long-lived "
        "commands such as npm run dev, vite --host, flask run, uvicorn, or "
        "python -m http.server. AgentHub platform tools own preview/deploy.\n"
        "- Preserve every explicit deliverable, exact filename, and acceptance "
        "requirement from the user request.\n"
        f"- Static preview publishes only the frontend entry on port 8082.{port_text}\n"
    )
    frontend_static_preview_rules = (
        "Static preview quality rules:\n"
        "- index.html must link styles.css and app.js.\n"
        "- The visible page must include the Chinese labels/sections: 任务拆解, "
        "代码产物, Diff, 网页预览, 按钮交互, 移动端适配.\n"
        "- Include at least one clickable button wired to app.js. Clicking visible "
        "buttons must not produce JavaScript errors.\n"
        "- Do not automatically request /api/okrs or other same-origin API URLs in "
        "static preview. Seed the UI from local mock OKR data by default, while "
        "keeping clearly named API helper functions that match api.md for future "
        "backend integration.\n"
        "- Avoid console.error, failed resource requests, external same-origin assets, "
        "and mobile horizontal overflow at a 390px viewport.\n"
    )
    return [
        SubTask(
            task_id="planning",
            agent_id=planner,
            title="Produce planning.md",
            instruction=(
                "Create planning.md in the workspace root. It must include product "
                "goal, page structure, backend API, data model, frontend/backend "
                "division, and acceptance criteria for the 团队 OKR 轻量看板 product.\n\n"
                f"{request_block}"
                "Use clear Markdown. Do not create implementation files in this task."
            ),
            expected_output="planning.md",
            include_history=False,
            priority=0,
        ),
        SubTask(
            task_id="frontend_impl",
            agent_id=frontend_agent,
            title="Implement frontend artifacts",
            instruction=(
                "Read planning.md, then implement the frontend static product. Create "
                "exactly these workspace root files: index.html, styles.css, app.js.\n\n"
                f"{request_block}\n{frontend_static_preview_rules}"
                "Return a concise summary listing the created files and the API helper "
                "functions implemented in app.js."
            ),
            depends_on=("planning",),
            expected_output="index.html\nstyles.css\napp.js",
            include_history=True,
            priority=1,
        ),
        SubTask(
            task_id="backend_impl",
            agent_id=backend_agent,
            title="Implement backend artifacts",
            instruction=(
                "Read planning.md, then implement the backend deliverables as code and "
                "documentation artifacts. Create exactly these workspace root files: "
                "backend_app.py, api.md, backend_tests.md.\n\n"
                f"{request_block}"
                "backend_app.py should be a compact Python API implementation for the "
                "OKR endpoints described in planning.md. api.md must document the "
                "endpoints and payloads. backend_tests.md must include CRUD and edge "
                "case test guidance. Do not start the backend service."
            ),
            depends_on=("planning",),
            expected_output="backend_app.py\napi.md\nbackend_tests.md",
            include_history=True,
            priority=1,
        ),
        SubTask(
            task_id="review",
            agent_id=review_agent,
            title="Review fullstack delivery",
            instruction=(
                "Read planning.md, index.html, styles.css, app.js, backend_app.py, "
                "api.md, and backend_tests.md. Create review.md in the workspace root.\n\n"
                f"{request_block}"
                "review.md must explicitly cover: file completeness, frontend/backend "
                "API consistency, code risks, test suggestions, preview readiness, and "
                "known limitation that the current platform only deploys the static "
                "frontend preview rather than a backend service."
            ),
            depends_on=("frontend_impl", "backend_impl"),
            expected_output="review.md",
            include_history=True,
            priority=2,
        ),
    ]


def _derive_workspace_conflict_tasks(
    agent_ids: list[str],
    user_request: str,
) -> list[SubTask]:
    normalized = user_request.lower()
    if not (
        "workspace conflict" in normalized
        or "冲突处理" in user_request
        or "冲突文件" in user_request
        or "同一文件" in user_request
        or "同一个 run" in normalized
    ):
        return []
    if len(agent_ids) < 2:
        return []
    paths = extract_artifact_paths_from_text(user_request)
    target_path = paths[0] if paths else "shared-conflict.md"
    creator = _preferred_agent(agent_ids, ("claude-code", "opencode-helper", "codex-helper"))
    first_modifier = _preferred_agent(
        agent_ids,
        ("claude-code", "codex-helper", "opencode-helper"),
    )
    remaining = [agent_id for agent_id in agent_ids if agent_id != first_modifier]
    second_modifier = _preferred_agent(
        remaining,
        ("opencode-helper", "codex-helper", "claude-code"),
    )
    if creator is None or first_modifier is None or second_modifier is None:
        return []
    return [
        SubTask(
            task_id="conflict-create",
            agent_id=creator,
            title=f"Create baseline {target_path}",
            instruction=(
                f"Create workspace file {target_path} with a short baseline section. "
                "Work only in the current workspace and do not create other files."
            ),
            priority=1,
            expected_output=target_path,
            include_history=False,
        ),
        SubTask(
            task_id="conflict-design",
            agent_id=first_modifier,
            title=f"Modify {target_path} from design perspective",
            instruction=(
                f"Modify the existing workspace file {target_path}. Add or replace "
                "content with the phrase 设计视角 and a concise design-oriented note. "
                "Do not create a new file."
            ),
            depends_on=("conflict-create",),
            priority=2,
            expected_output=target_path,
            include_history=False,
        ),
        SubTask(
            task_id="conflict-implementation",
            agent_id=second_modifier,
            title=f"Modify {target_path} from implementation perspective",
            instruction=(
                f"Modify the existing workspace file {target_path}. Add or replace "
                "content with the phrase 实现视角 and a concise implementation-oriented "
                "note. Do not create a new file."
            ),
            depends_on=("conflict-create",),
            priority=2,
            expected_output=target_path,
            include_history=False,
        ),
    ]


def _derive_frontend_deploy_tasks(
    agent_ids: list[str],
    user_request: str,
) -> list[SubTask]:
    if not _is_frontend_deploy_or_quality_request(user_request):
        return []
    if _is_fullstack_delivery_request(user_request):
        return []
    if not agent_ids:
        return []

    generator = _preferred_agent(agent_ids, FRONTEND_AGENT_PREFERENCE)
    if generator is None:
        return []
    reviewer = None
    if generator != "opencode-helper":
        reviewer = _preferred_agent(
            [agent_id for agent_id in agent_ids if agent_id != generator],
            FRONTEND_REVIEW_AGENT_PREFERENCE,
        )

    requested_port = _requested_port(user_request)
    port_text = f" The requested preview port is {requested_port}." if requested_port else ""
    common_requirements = (
        "Original user request:\n"
        f"{user_request}\n\n"
        "Hard requirements:\n"
        "- Preserve every explicit deliverable and acceptance requirement from the "
        "original user request.\n"
        "- Prefer a conventional static frontend structure for web apps.\n"
        "- Work only inside the current AgentHub workspace and use workspace-relative "
        "paths.\n"
        "- Do not enter plan mode, ask for approval, or wait for a human approval step. "
        "Create or edit the requested files directly.\n"
        "- Do not start preview/deploy servers and do not create server.js, Express, "
        "Vite, Next, or package.json start/dev/preview scripts. AgentHub platform "
        "owns preview/deploy."
        f"{port_text}\n"
        "- The final static app must use exactly these entry files at the workspace "
        "root: index.html, styles.css, app.js.\n"
        "- The page must visibly include the Chinese labels/sections: 任务拆解, "
        "代码产物, Diff, 网页预览, 按钮交互, 移动端适配.\n"
        "- Include at least one clickable button wired to app.js. Clicking visible "
        "buttons must not produce JavaScript errors.\n"
        "- Make the page responsive at a 390px mobile viewport with no horizontal "
        "overflow.\n"
        "- Avoid external same-origin assets unless you also create them in the "
        "workspace.\n"
    )
    tasks = [
        SubTask(
            task_id="frontend-build",
            agent_id=generator,
            title="Build static frontend demo artifacts",
            instruction=(
                "Create the complete static frontend demo now.\n\n"
                f"{common_requirements}\n"
                "Implement a polished random-theme frontend demo with task "
                "decomposition, code artifact, Diff, web preview, button interaction, "
                "and mobile adaptation sections. Return a concise summary and list "
                "the changed files."
            ),
            expected_output="index.html\nstyles.css\napp.js",
            include_history=False,
            priority=1,
        )
    ]
    if reviewer is not None:
        tasks.append(
            SubTask(
                task_id="frontend-review-refine",
                agent_id=reviewer,
                title="Review and refine frontend quality",
                instruction=(
                    "Inspect the existing static frontend files and fix any gaps before "
                    "platform browser verification runs.\n\n"
                    f"{common_requirements}\n"
                    "Verify that index.html links styles.css and app.js, required text "
                    "is visible, button interactions are implemented without console "
                    "errors, and mobile layout avoids horizontal overflow. If anything "
                    "is missing, edit the files directly."
                ),
                depends_on=("frontend-build",),
                expected_output="index.html\nstyles.css\napp.js",
                include_history=True,
                priority=2,
            )
        )
    return tasks


def _is_frontend_deploy_or_quality_request(user_request: str) -> bool:
    if not user_request:
        return False
    normalized = user_request.lower()
    is_frontend = any(marker in normalized for marker in FRONTEND_DEMO_MARKERS)
    wants_preview = any(marker in normalized for marker in PREVIEW_DEPLOY_MARKERS)
    wants_quality = any(marker in normalized for marker in QUALITY_MARKERS)
    has_demo_requirements = any(
        marker in normalized for marker in FRONTEND_QUALITY_PLAN_MARKERS
    )
    return is_frontend and (wants_quality or (wants_preview and has_demo_requirements))


def _is_fullstack_delivery_request(user_request: str) -> bool:
    normalized = user_request.lower()
    return any(marker in normalized for marker in FULLSTACK_MARKERS)


def _available_orchestrator_agent_ids(config: Mapping[str, Any]) -> list[str]:
    available_agents = config.get("available_agents")
    if isinstance(available_agents, list):
        ids: list[str] = []
        seen: set[str] = set()
        for item in available_agents:
            if not isinstance(item, Mapping):
                continue
            raw_id = item.get("agent_id", item.get("id"))
            if not isinstance(raw_id, str):
                continue
            agent_id = raw_id.strip()
            if not agent_id or agent_id == "orchestrator" or agent_id in seen:
                continue
            seen.add(agent_id)
            ids.append(agent_id)
        if ids:
            return ids
    return agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )


def _preferred_agent(agent_ids: list[str], preference: tuple[str, ...]) -> str | None:
    available = set(agent_ids)
    for agent_id in preference:
        if agent_id in available:
            return agent_id
    return agent_ids[0] if agent_ids else None


def _requested_port(text: str) -> int | None:
    match = PORT_NUMBER_RE.search(text)
    if match is None:
        return None
    port = int(match.group(1))
    if 1 <= port <= 65535:
        return port
    return None


def _has_explicit_requirements(user_request: str) -> bool:
    normalized = user_request.lower()
    return any(marker in normalized for marker in EXPLICIT_REQUIREMENT_MARKERS)


def _direct_tasks_from_request(
    config: Mapping[str, Any], messages: list[ChatMessage]
) -> list[SubTask]:
    agent_ids = agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    if not agent_ids:
        return []
    return _derive_direct_agent_tasks(agent_ids, latest_user_request(messages))


def _direct_answer_on_planner_failure(config: Mapping[str, Any]) -> bool:
    return config.get("direct_answer_on_planner_failure") is True


def _derive_tasks(config: Mapping[str, Any], messages: list[ChatMessage]) -> list[SubTask]:
    agent_ids = agent_id_list(
        config.get("managed_agent_ids", config.get("default_sub_agents"))
    )
    if not agent_ids:
        raise ValueError(
            "missing_task_plan: config.tasks or config.managed_agent_ids is required"
        )

    user_request = latest_user_request(messages)
    direct_tasks = _derive_direct_agent_tasks(agent_ids, user_request)
    if direct_tasks:
        return direct_tasks
    fullstack_tasks = _derive_fullstack_delivery_tasks(agent_ids, user_request)
    if fullstack_tasks:
        return fullstack_tasks
    frontend_tasks = _derive_frontend_deploy_tasks(agent_ids, user_request)
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


def _derive_direct_agent_tasks(agent_ids: list[str], user_request: str) -> list[SubTask]:
    targets = explicit_agent_mentions(agent_ids, user_request)
    if len(targets) < 2:
        return []

    message = _direct_broadcast_message(user_request)
    if message is None:
        return []
    return [
        SubTask(
            task_id=f"direct-{index + 1}",
            agent_id=agent_id,
            title="Direct request",
            instruction=_direct_agent_instruction(message),
            priority=index,
            include_history=False,
        )
        for index, agent_id in enumerate(targets)
    ]


def _direct_broadcast_message(user_request: str) -> str | None:
    quoted = _extract_quoted_message(user_request)
    if quoted is None:
        return None
    normalized = user_request.lower()
    broadcast_markers = (
        "same message",
        "send",
        "ask",
        "发送",
        "转发",
        "同一句",
        "同一条",
        "同样的问题",
    )
    if any(marker in normalized for marker in broadcast_markers):
        return quoted
    return None


def _agent_aliases(agent_id: str) -> tuple[str, ...]:
    if agent_id == "claude-code":
        return ("@claude-code", "claude-code", "claude code", "claudecode")
    if agent_id == "codex-helper":
        return ("@codex-helper", "codex-helper", "codex helper", "codex")
    if agent_id == "opencode-helper":
        return (
            "@opencode-helper",
            "opencode-helper",
            "opencode helper",
            "open code",
            "opencode",
        )
    if agent_id == "web-designer":
        return ("@web-designer", "web-designer", "web designer")
    return (f"@{agent_id}", agent_id)


def _first_alias_position(text: str, aliases: tuple[str, ...]) -> int | None:
    positions = [text.find(alias) for alias in aliases]
    matches = [position for position in positions if position >= 0]
    return min(matches) if matches else None


def _extract_quoted_message(user_request: str) -> str | None:
    quote_pairs = (("“", "”"), ('"', '"'), ("'", "'"))
    for open_quote, close_quote in quote_pairs:
        start = user_request.find(open_quote)
        if start < 0:
            continue
        end = user_request.find(close_quote, start + 1)
        if end <= start:
            continue
        quoted = user_request[start + 1 : end].strip()
        if quoted:
            return quoted
    return None


def _direct_agent_instruction(message: str) -> str:
    return (
        "You are receiving a direct request from AgentHub Orchestrator.\n"
        "Answer the message yourself only. Do not contact, invoke, or simulate "
        "other agents, CLIs, or APIs.\n"
        "If the message asks what model or runtime you are, answer from your own "
        "runtime identity.\n\n"
        f"Message:\n{message}\n\n"
        "Keep the response concise."
    )


def _ensure_unique_task_ids(tasks: list[SubTask]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.task_id in seen:
            raise ValueError(f"invalid_task_plan: duplicate task_id {task.task_id!r}")
        seen.add(task.task_id)
