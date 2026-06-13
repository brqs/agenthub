"""Generic legacy fallback task templates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator._internal.planning.routing import (
    agent_id_list,
    derive_direct_agent_tasks,
    explicit_agent_mentions,
    latest_user_request,
)
from app.agents.orchestrator._internal.planning.templates.common import (
    available_orchestrator_agent_ids,
    preferred_agent,
)
from app.agents.orchestrator._internal.planning.templates.delivery import (
    derive_fullstack_delivery_tasks,
)
from app.agents.orchestrator._internal.planning.turn_taking import (
    pure_dialogue_requested,
    turn_taking_requested,
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
DIALOGUE_AGENT_PREFERENCE = (
    "claude-code",
    "opencode-helper",
    "codex-helper",
)
DIALOGUE_REQUEST_MARKERS = (
    "辩论",
    "对话场景",
    "角色扮演",
    "圆桌讨论",
    "群组内",
    "群聊辩论",
    "头脑风暴",
    "观点对比",
    "群聊讨论",
    "讨论一下",
    "分析这组数据",
    "分析数据",
    "数据分析",
    "协作分析",
    "brainstorm",
    "debate",
    "role-play",
    "roleplay",
    "roundtable",
    "panel",
)
NO_ARTIFACT_DIALOGUE_MARKERS = (
    "不需要生成文件",
    "不生成文件",
    "不要生成文件",
    "无需生成文件",
    "不用生成文件",
    "不需要写文件",
    "不要写文件",
    "直接以对话",
    "直接用对话",
    "直接对话",
    "对话形式输出",
    "聊天形式输出",
    "no file",
    "no files",
    "without files",
)


def derive_tasks(config: Mapping[str, Any], messages: list[ChatMessage]) -> list[SubTask]:
    user_request = latest_user_request(messages)
    agent_ids = _template_agent_ids(config, user_request)
    if not agent_ids:
        raise ValueError(
            "missing_task_plan: config.tasks or config.managed_agent_ids is required"
        )
    direct_tasks = derive_direct_agent_tasks(agent_ids, user_request)
    if direct_tasks and not turn_taking_requested(user_request):
        return direct_tasks
    turn_tasks = _turn_taking_dialogue_tasks(agent_ids, user_request)
    if turn_tasks:
        return turn_tasks
    dialogue_tasks = _dialogue_tasks(agent_ids, user_request)
    if dialogue_tasks:
        return dialogue_tasks
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


def _template_agent_ids(config: Mapping[str, Any], user_request: str) -> list[str]:
    if _dialogue_template_requested(user_request):
        group_ids = agent_id_list(
            config.get("managed_agent_ids", config.get("default_sub_agents"))
        )
        if group_ids:
            return group_ids
    return available_orchestrator_agent_ids(config)


def _dialogue_template_requested(user_request: str) -> bool:
    normalized = user_request.lower()
    return bool(
        pure_dialogue_requested(user_request)
        or turn_taking_requested(user_request)
        or (
            _has_any(normalized, DIALOGUE_REQUEST_MARKERS)
            and _has_any(normalized, NO_ARTIFACT_DIALOGUE_MARKERS)
        )
    )


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


def _dialogue_tasks(agent_ids: list[str], user_request: str) -> list[SubTask]:
    normalized = user_request.lower()
    if not _dialogue_template_requested(user_request):
        return []
    ordered = _dialogue_agent_order(agent_ids, user_request)
    if not ordered:
        return []

    topic = _dialogue_topic(user_request)
    debate = "辩论" in user_request or "debate" in normalized
    pro_agent = ordered[0]
    con_agent = ordered[1] if len(ordered) > 1 else ordered[0]
    first_title = (
        f"正方发言：{topic}利大于弊"
        if debate
        else f"第一位成员发言：{topic}"
    )
    second_title = (
        f"反方发言：{topic}弊大于利"
        if debate
        else f"第二位成员发言：{topic}"
    )
    first_role = (
        f"立场：{topic}利大于弊。"
        if debate
        else "角色：第一位讨论成员，给出建设性观点、理由和具体建议。"
    )
    second_role = (
        f"立场：{topic}弊大于利。"
        if debate
        else "角色：第二位讨论成员，从不同角度补充、质疑或提出替代方案。"
    )
    tasks = [
        SubTask(
            task_id="dialogue-pro",
            agent_id=pro_agent,
            title=first_title,
            instruction=(
                "你正在 AgentHub 群聊中参与一场公开对话。请直接以分配给你的身份发言，"
                "不要主持、不要邀请别人登场、不要复述任务、不要只说已完成。"
                "\n不要生成文件、不要写报告、不要要求平台工具。"
                f"\n\n主题：{topic}"
                f"\n{first_role}"
                "\n输出要求：中文、对话口吻、像群聊现场发言；用 3-5 段短发言给出"
                "观点、理由、例子，并回应潜在反驳或补充角度。"
                f"\n\n原始用户请求：\n{user_request}"
            ),
            priority=0,
            expected_output="",
            task_type="conversation",
        )
    ]
    if con_agent != pro_agent:
        tasks.append(
            SubTask(
                task_id="dialogue-con",
                agent_id=con_agent,
                title=second_title,
                instruction=(
                    "你正在 AgentHub 群聊中参与一场公开对话。请直接以分配给你的身份发言，"
                    "不要主持、不要邀请别人登场、不要复述任务、不要只说已完成。"
                    "\n不要生成文件、不要写报告、不要要求平台工具。"
                    f"\n\n主题：{topic}"
                    f"\n{second_role}"
                    "\n输出要求：中文、对话口吻、像群聊现场发言；用 3-5 段短发言给出"
                    "观点、理由、例子，并明确回应或补充上一位成员的观点。"
                    f"\n\n原始用户请求：\n{user_request}"
                ),
                depends_on=("dialogue-pro",),
                priority=1,
                expected_output="",
                task_type="conversation",
            )
        )
    return tasks


def _dialogue_agent_order(agent_ids: list[str], user_request: str = "") -> list[str]:
    return _dialogue_agent_order_for_request(agent_ids, user_request)


def _dialogue_agent_order_for_request(agent_ids: list[str], user_request: str) -> list[str]:
    remaining = list(dict.fromkeys(agent_ids))
    ordered: list[str] = []
    for agent_id in explicit_agent_mentions(agent_ids, user_request):
        if agent_id not in remaining:
            continue
        ordered.append(agent_id)
        remaining.remove(agent_id)
    for preference in DIALOGUE_AGENT_PREFERENCE:
        if preference not in remaining:
            continue
        ordered.append(preference)
        remaining.remove(preference)
    ordered.extend(remaining)
    return ordered


def _turn_taking_dialogue_tasks(
    agent_ids: list[str],
    user_request: str,
) -> list[SubTask]:
    normalized = user_request.lower()
    if not turn_taking_requested(user_request):
        return []
    if not (
        _has_any(normalized, DIALOGUE_REQUEST_MARKERS)
        or _has_any(normalized, NO_ARTIFACT_DIALOGUE_MARKERS)
    ):
        return []
    ordered = _dialogue_agent_order_for_request(agent_ids, user_request)
    if len(ordered) < 2:
        return []

    topic = _dialogue_topic(user_request)
    debate = "辩论" in user_request or "debate" in normalized
    participants = ordered[: min(len(ordered), _requested_participant_count(user_request))]
    total_turns = _requested_total_turns(user_request, len(participants))
    tasks: list[SubTask] = []
    for index in range(total_turns):
        agent_id = participants[index % len(participants)]
        turn_number = index + 1
        role = _dialogue_turn_role(
            topic,
            debate=debate,
            participant_index=index % len(participants),
        )
        previous_task_id = tasks[-1].task_id if tasks else None
        task_id = f"dialogue-turn-{turn_number}"
        title = f"第 {turn_number} 轮发言：{role['title']}"
        instruction = (
            "你正在 AgentHub 群聊中参加 Orchestrator 托管的多 Agent 接力对话。"
            "\n本轮只允许你代表自己发言；不要代写其他 Agent 的完整回复。"
            "\n不要主持、不要邀请别人登场、不要复述任务、不要只说已完成。"
            "\n不要生成文件、不要写报告、不要要求平台工具。"
            f"\n\n主题：{topic}"
            f"\n本轮轮次：{turn_number}/{total_turns}"
            f"\n你的角色/立场：{role['description']}"
            "\n输出要求：中文、群聊口吻、1-3 段。直接给出你的观点、理由和例子。"
        )
        if previous_task_id:
            instruction += (
                "\n上一轮发言摘录会由 Orchestrator 作为上下文提供；"
                "本轮必须明确回应、补充或反驳上一轮，不要重新开场。"
            )
        else:
            instruction += "\n这是第一轮，请直接开场陈述你的立场。"
        if turn_number < total_turns:
            next_agent = participants[turn_number % len(participants)]
            instruction += (
                f"\n你可以在结尾点名 @{next_agent} 作为交接提示，"
                "但真正调度由 Orchestrator 负责。"
            )
        instruction += f"\n\n原始用户请求：\n{user_request}"
        tasks.append(
            SubTask(
                task_id=task_id,
                agent_id=agent_id,
                title=title,
                instruction=instruction,
                depends_on=(previous_task_id,) if previous_task_id else (),
                priority=index,
                expected_output="",
                task_type="dialogue_turn",
            )
        )
    return tasks


def _dialogue_turn_role(
    topic: str,
    *,
    debate: bool,
    participant_index: int,
) -> dict[str, str]:
    if debate:
        if participant_index % 2 == 0:
            return {
                "title": f"正方：{topic}利大于弊",
                "description": f"正方，主张 {topic}利大于弊。",
            }
        return {
            "title": f"反方：{topic}弊大于利",
            "description": f"反方，主张 {topic}弊大于利。",
        }
    if participant_index == 0:
        return {
            "title": f"第一位成员：{topic}",
            "description": "第一位讨论成员，给出清晰观点、理由和具体建议。",
        }
    return {
        "title": f"回应成员：{topic}",
        "description": "后续讨论成员，从不同角度补充、质疑或提出替代方案。",
    }


def _requested_participant_count(user_request: str) -> int:
    if any(marker in user_request for marker in ("三个智能体", "3个智能体", "三位")):
        return 3
    return 2


def _requested_total_turns(user_request: str, participant_count: int) -> int:
    if any(marker in user_request for marker in ("一人一句", "每人一句")):
        return participant_count
    match = re.search(r"([2-8二三四五六七八])\s*轮", user_request)
    if match:
        raw = match.group(1)
        value = {
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
        }.get(raw, int(raw) if raw.isdigit() else 2)
        return max(participant_count, min(value * participant_count, 8))
    return participant_count


def _dialogue_topic(user_request: str) -> str:
    patterns = (
        r"论题是(.+?)(?:[？?。.!！]|$)",
        r"主题是(.+?)(?:[？?。.!！]|$)",
        r"围绕(.+?)(?:开展|进行|讨论|辩论|[？?。.!！]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_request)
        if match:
            topic = match.group(1).strip(" ：:，,。.!！?？")
            if topic:
                return topic[:80]
    cleaned = re.sub(r"@[\w-]+", "", user_request).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:80] or "本次讨论主题")


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
