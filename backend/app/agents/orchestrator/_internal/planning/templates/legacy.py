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

    contract = _generic_contract(user_request)
    titles = ("Analyze request", "Produce solution", "Review and refine")
    instructions = (
        "Analyze the user's request and propose the implementation approach."
        f"{contract['planning_instruction']}\n\nRequest:\n{user_request}",
        "Implement or draft the requested result. Include concrete artifacts when useful."
        f"{contract['implementation_instruction']}\n\nRequest:\n{user_request}",
        "Review the result for gaps, risks, and next steps. Keep the answer concise."
        f"{contract['review_instruction']}\n\nRequest:\n{user_request}",
    )
    expected_outputs = (
        contract["planning_expected_output"],
        contract["implementation_expected_output"],
        contract["review_expected_output"],
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
                expected_output=expected_outputs[index]
                if index < len(expected_outputs)
                else "",
                depends_on=_generic_depends_on(index, contract),
                review_of=_generic_review_of(index, contract),
                task_type=_generic_task_type(index, contract),
            )
        )
    return tasks


def _generic_contract(user_request: str) -> dict[str, Any]:
    normalized = user_request.lower()
    wants_document = _has_any(
        normalized,
        ("文档", "方案", "设计文档", "planning.md", "plan.md", "document", "doc"),
    )
    wants_web = _has_any(
        normalized,
        (
            "网站",
            "站点",
            "网页",
            "前端",
            "html",
            "css",
            "javascript",
            "app.js",
            "index.html",
            "styles.css",
            "website",
            "site",
            "frontend",
        ),
    )
    wants_diff = _has_any(normalized, ("diff", "差异", "变更摘要"))
    wants_review = _has_any(normalized, ("审阅", "评审", "复核", "review"))

    planning_instruction = ""
    planning_expected_output = ""
    if wants_document:
        planning_instruction = (
            "\n\nCreate a workspace Markdown planning document named planning.md. "
            "Include goals, deliverables, file ownership, acceptance criteria, "
            "and risks. Do not stop at analysis-only text."
        )
        planning_expected_output = "planning.md"

    implementation_instruction = ""
    implementation_expected = []
    if wants_web:
        implementation_instruction += (
            "\n\nCreate static frontend artifacts in the workspace root: "
            "index.html, styles.css, and app.js. Do not create a server or "
            "long-running preview command; AgentHub platform owns preview/deploy."
        )
        implementation_expected.extend(["index.html", "styles.css", "app.js"])
    if wants_diff:
        implementation_instruction += (
            "\n\nCreate diff.md or an equivalent concise change summary that "
            "explains the meaningful differences produced by this task."
        )
        implementation_expected.append("diff.md")

    review_instruction = ""
    review_expected_output = ""
    if wants_review:
        review_instruction = (
            "\n\nCreate review.md in the workspace. Verify the generated artifacts "
            "against the original request and state pass/fail with concrete gaps."
        )
        review_expected_output = "review.md"

    return {
        "wants_review": wants_review,
        "planning_instruction": planning_instruction,
        "planning_expected_output": planning_expected_output,
        "implementation_instruction": implementation_instruction,
        "implementation_expected_output": "\n".join(implementation_expected),
        "review_instruction": review_instruction,
        "review_expected_output": review_expected_output,
    }


def _generic_depends_on(index: int, contract: Mapping[str, Any]) -> tuple[str, ...]:
    if index == 2 and contract.get("wants_review") is True:
        return ("auto-1", "auto-2")
    return ()


def _generic_review_of(index: int, contract: Mapping[str, Any]) -> tuple[str, ...]:
    if index == 2 and contract.get("wants_review") is True:
        return ("auto-1", "auto-2")
    return ()


def _generic_task_type(index: int, contract: Mapping[str, Any]) -> str:
    if index == 2 and contract.get("wants_review") is True:
        return "review"
    return "implementation"


def _has_any(normalized: str, markers: tuple[str, ...]) -> bool:
    return any(marker in normalized for marker in markers)


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
