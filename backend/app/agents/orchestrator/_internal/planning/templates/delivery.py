"""Legacy template task derivation for orchestrator planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from app.agents.orchestrator._internal.planning.routing import (
    latest_user_request,
)
from app.agents.orchestrator._internal.planning.templates.common import (
    available_orchestrator_agent_ids,
    preferred_agent,
    requested_port,
)
from app.agents.orchestrator.types import SubTask
from app.agents.types import ChatMessage

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
FULLSTACK_MARKERS = (
    "前后端",
    "后端",
    "backend",
    "fullstack",
    "full-stack",
    "api.md",
    "backend_app.py",
)
ARCHITECT_AGENT_PREFERENCE = (
    "codex-helper",
    "claude-code",
    "opencode-helper",
)


def preserve_explicit_requirements(
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


def fullstack_delivery_tasks_from_request(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
) -> list[SubTask]:
    return derive_fullstack_delivery_tasks(
        available_orchestrator_agent_ids(config),
        latest_user_request(messages),
    )


def derive_fullstack_delivery_tasks(
    agent_ids: list[str],
    user_request: str,
) -> list[SubTask]:
    if not _is_fullstack_delivery_request(user_request):
        return []
    if not agent_ids:
        return []

    planner = preferred_agent(
        agent_ids,
        ARCHITECT_AGENT_PREFERENCE,
    )
    frontend_agent = preferred_agent(
        agent_ids,
        ("claude-code", "opencode-helper", "codex-helper"),
    )
    backend_agent = preferred_agent(
        agent_ids,
        ("opencode-helper", "claude-code", "codex-helper"),
    )
    review_agent = preferred_agent(
        agent_ids,
        ("codex-helper", "claude-code", "opencode-helper"),
    )
    if (
        planner is None
        or frontend_agent is None
        or backend_agent is None
        or review_agent is None
    ):
        return []

    port = requested_port(user_request)
    port_text = f" Requested preview port: {port}." if port else ""
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
        "- The visible page must reflect the product/theme and explicit sections "
        "requested by the user.\n"
        "- Include at least one clickable button wired to app.js. Clicking visible "
        "buttons must not produce JavaScript errors.\n"
        "- Do not automatically request same-origin API URLs in static preview. Seed "
        "the UI from local mock data that matches api.md by default, while keeping "
        "clearly named API helper functions for future backend integration.\n"
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
                "division, and acceptance criteria for the requested fullstack "
                "product or demo.\n\n"
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
                "endpoints described in planning.md. api.md must document the "
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
            task_type="review",
            review_of=("frontend_impl", "backend_impl"),
            handoff_reason="Fullstack implementation handoff requires independent review",
        ),
    ]


def _is_fullstack_delivery_request(user_request: str) -> bool:
    normalized = user_request.lower()
    return any(marker in normalized for marker in FULLSTACK_MARKERS)


def _has_explicit_requirements(user_request: str) -> bool:
    normalized = user_request.lower()
    return any(marker in normalized for marker in EXPLICIT_REQUIREMENT_MARKERS)
