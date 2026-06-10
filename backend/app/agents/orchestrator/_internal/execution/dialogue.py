"""Dynamic dialogue session helpers for Orchestrator-managed turn taking."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage

DEFAULT_MAX_DIALOGUE_TURNS = 8
MIN_DEBATE_ATTACK_DEFENSE_TURNS = 4

_HANDOFF_RE = re.compile(
    r"@[\w-]+|你继续|请(?:你)?回应|请(?:你)?反驳|反驳一下|接招|轮到你|继续辩论|继续回应"
)
_EXPLICIT_SHORT_RE = re.compile(
    r"只要.{0,8}(?:双方|每人|各自|各).{0,4}(?:一句|一轮)|"
    r"(?:双方|每人|各自|各).{0,4}(?:一句即可|各说一句|一轮即可)|"
    r"只(?:进行|要).{0,4}一轮|只需.{0,4}一轮"
)
_EXPLICIT_ROUNDS_RE = re.compile(r"([2-8二三四五六七八])\s*轮")


def dialogue_requires_sequential(tasks: Sequence[SubTask]) -> bool:
    """Return true when tasks are an Orchestrator-managed dialogue session."""

    dialogue_tasks = [task for task in tasks if task.task_type == "dialogue_turn"]
    if len(dialogue_tasks) < 2:
        return False
    return len(dialogue_tasks) == len(tasks)


def maybe_next_dialogue_turn(
    *,
    messages: Sequence[ChatMessage],
    task_sequence: Sequence[SubTask],
    task_index: int,
    completed_task: SubTask,
    completed_result: TaskResult,
    run_context: OrchestratorRunContext,
) -> SubTask | None:
    """Create the next dynamic dialogue turn when the session should continue."""

    if completed_task.task_type != "dialogue_turn":
        return None
    if completed_result.final_state != TaskState.SUCCEEDED:
        return None
    if _has_pending_planned_dialogue_turn(task_sequence, task_index):
        return None

    user_request = _latest_user_request(messages)
    dialogue_tasks = [task for task in task_sequence if task.task_type == "dialogue_turn"]
    participants = _participant_order(dialogue_tasks)
    if len(participants) < 2:
        return None

    completed_turns = _completed_dialogue_tasks(task_sequence, run_context)
    turn_count = len(completed_turns)
    max_turns = _max_dialogue_turns(user_request, len(participants))
    if turn_count >= max_turns:
        return None
    if _explicit_short_dialogue(user_request) and turn_count >= len(participants):
        return None

    current_text = _final_attempt_text(completed_result)
    debate = _is_debate_dialogue(user_request, dialogue_tasks)
    if _should_continue_dialogue(
        user_request=user_request,
        current_text=current_text,
        completed_turns=completed_turns,
        participants=participants,
        debate=debate,
    ):
        return _build_next_turn(
            user_request=user_request,
            previous_task=completed_task,
            participants=participants,
            next_turn_number=turn_count + 1,
            max_turns=max_turns,
            debate=debate,
        )
    return None


def compute_debate_judgement(
    *,
    messages: Sequence[ChatMessage],
    tasks: Sequence[SubTask],
    run_context: OrchestratorRunContext,
) -> dict[str, Any] | None:
    """Score debate sides from public agent summaries/text without an LLM judge."""

    user_request = _latest_user_request(messages)
    dialogue_tasks = [task for task in tasks if task.task_type == "dialogue_turn"]
    if not _is_debate_dialogue(user_request, dialogue_tasks):
        return None

    side_texts: dict[str, list[str]] = {"pro": [], "con": []}
    side_agents: dict[str, list[str]] = {"pro": [], "con": []}
    for task in dialogue_tasks:
        result = run_context.results.get(task.task_id)
        if result is not None and result.final_state != TaskState.SUCCEEDED:
            return None
        side = _task_side(task)
        if side is None:
            continue
        if result is None or result.final_state != TaskState.SUCCEEDED:
            continue
        text = _final_attempt_text(result)
        if not text:
            continue
        side_texts[side].append(text)
        if task.agent_id not in side_agents[side]:
            side_agents[side].append(task.agent_id)

    if not side_texts["pro"] or not side_texts["con"]:
        return None

    pro_score = _score_debate_side("\n".join(side_texts["pro"]))
    con_score = _score_debate_side("\n".join(side_texts["con"]))
    difference = pro_score - con_score
    if abs(difference) <= 1:
        winner = "draw"
        winner_label = "势均力敌"
    elif difference > 0:
        winner = "pro"
        winner_label = "正方更有说服力"
    else:
        winner = "con"
        winner_label = "反方更有说服力"

    return {
        "type": "debate_judgement",
        "winner": winner,
        "winner_label": winner_label,
        "scores": {"pro": pro_score, "con": con_score},
        "participants": side_agents,
        "reason": _judgement_reason(winner, pro_score, con_score),
    }


def debate_judgement_line(judgement: Mapping[str, Any]) -> str:
    winner = str(judgement.get("winner_label") or "势均力敌")
    reason = str(judgement.get("reason") or "").strip()
    scores = judgement.get("scores")
    score_text = ""
    if isinstance(scores, Mapping):
        pro = scores.get("pro")
        con = scores.get("con")
        if isinstance(pro, int) and isinstance(con, int):
            score_text = f"（正方 {pro} / 反方 {con}）"
    return f"辩论评判：{winner}{score_text}。{reason}".strip()


def _has_pending_planned_dialogue_turn(
    task_sequence: Sequence[SubTask],
    task_index: int,
) -> bool:
    for task in task_sequence[task_index + 1 :]:
        if task.task_type == "dialogue_turn":
            return True
        if task.task_type not in {"review", "repair"}:
            return False
    return False


def _should_continue_dialogue(
    *,
    user_request: str,
    current_text: str,
    completed_turns: Sequence[SubTask],
    participants: Sequence[str],
    debate: bool,
) -> bool:
    turn_count = len(completed_turns)
    if turn_count < len(participants):
        return True
    if not debate:
        if _explicit_round_count_requested(user_request):
            return True
        if _asks_for_continued_debate(user_request) and turn_count < len(participants) * 2:
            return True
        return False
    if debate and turn_count < min(MIN_DEBATE_ATTACK_DEFENSE_TURNS, DEFAULT_MAX_DIALOGUE_TURNS):
        return True
    if debate and not _explicit_round_count_requested(user_request):
        return False
    if _handoff_requested(current_text):
        return True
    if _asks_for_continued_debate(user_request) and turn_count < len(participants) * 2:
        return True
    return False


def _build_next_turn(
    *,
    user_request: str,
    previous_task: SubTask,
    participants: Sequence[str],
    next_turn_number: int,
    max_turns: int,
    debate: bool,
) -> SubTask:
    participant_index = (next_turn_number - 1) % len(participants)
    agent_id = participants[participant_index]
    topic = _dialogue_topic(user_request)
    role = _dialogue_turn_role(topic, debate=debate, participant_index=participant_index)
    task_id = f"dialogue-turn-{next_turn_number}"
    title = f"第 {next_turn_number} 轮发言：{role['title']}"
    next_agent = participants[next_turn_number % len(participants)]
    instruction = (
        "你正在 AgentHub 群聊中参加 Orchestrator 托管的动态多 Agent 接力对话。"
        "\n本轮只允许你代表自己发言；不要代写其他 Agent 的完整回复。"
        "\n不要主持、不要邀请别人登场、不要复述任务、不要只说已完成。"
        "\n不要生成文件、不要写报告、不要要求平台工具。"
        f"\n\n主题：{topic}"
        f"\n本轮轮次：{next_turn_number}/{max_turns}（可能根据交锋质量提前结束）"
        f"\n你的角色/立场：{role['description']}"
        "\n上一轮发言摘录会由 Orchestrator 作为上下文提供；"
        "本轮必须明确回应、补充或反驳上一轮，不要重新开场。"
        "\n输出要求：中文、群聊口吻、1-3 段。直接给出你的观点、理由和例子。"
    )
    if next_turn_number < max_turns:
        instruction += (
            f"\n你可以在结尾点名 @{next_agent} 作为交接提示，"
            "但真正调度由 Orchestrator 负责。"
        )
    instruction += f"\n\n原始用户请求：\n{user_request}"
    return SubTask(
        task_id=task_id,
        agent_id=agent_id,
        title=title,
        instruction=instruction,
        depends_on=(previous_task.task_id,),
        priority=previous_task.priority + 1,
        expected_output="",
        task_type="dialogue_turn",
    )


def _completed_dialogue_tasks(
    task_sequence: Sequence[SubTask],
    run_context: OrchestratorRunContext,
) -> list[SubTask]:
    completed: list[SubTask] = []
    for task in task_sequence:
        if task.task_type != "dialogue_turn":
            continue
        result = run_context.results.get(task.task_id)
        if result is not None and result.final_state == TaskState.SUCCEEDED:
            completed.append(task)
    return completed


def _participant_order(tasks: Sequence[SubTask]) -> list[str]:
    participants: list[str] = []
    for task in tasks:
        if task.agent_id and task.agent_id not in participants:
            participants.append(task.agent_id)
    return participants


def _max_dialogue_turns(user_request: str, participant_count: int) -> int:
    if _explicit_short_dialogue(user_request):
        return participant_count
    match = _EXPLICIT_ROUNDS_RE.search(user_request)
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
        return max(participant_count, min(value * participant_count, DEFAULT_MAX_DIALOGUE_TURNS))
    return DEFAULT_MAX_DIALOGUE_TURNS


def _explicit_short_dialogue(user_request: str) -> bool:
    if any(
        marker in user_request
        for marker in ("只要双方各说一句", "双方各说一句", "各说一句", "每人一句即可")
    ):
        return True
    return bool(_EXPLICIT_SHORT_RE.search(user_request))


def _explicit_round_count_requested(user_request: str) -> bool:
    return bool(_EXPLICIT_ROUNDS_RE.search(user_request))


def _asks_for_continued_debate(user_request: str) -> bool:
    return any(
        marker in user_request
        for marker in ("展开辩论", "回应对方", "反驳", "接力", "继续")
    )


def _handoff_requested(text: str) -> bool:
    return bool(_HANDOFF_RE.search(text))


def _is_debate_dialogue(user_request: str, tasks: Sequence[SubTask]) -> bool:
    if "辩论" in user_request or "debate" in user_request.lower():
        return True
    return any("正方" in task.title or "反方" in task.title for task in tasks)


def _task_side(task: SubTask) -> str | None:
    combined = f"{task.title}\n{task.instruction}"
    role_match = re.search(r"你的角色/立场[:：]\s*([^\n]+)", combined)
    role_text = role_match.group(1) if role_match else task.title
    if "反方" in role_text:
        return "con"
    if "正方" in role_text:
        return "pro"
    if "反方" in task.title:
        return "con"
    if "正方" in task.title:
        return "pro"
    if "弊大于利" in role_text and "利大于弊" not in role_text:
        return "con"
    if "利大于弊" in role_text and "弊大于利" not in role_text:
        return "pro"
    return None


def _score_debate_side(text: str) -> int:
    score = 0
    dimensions = (
        ("针对", "回应", "反驳", "你说", "你提到", "上一轮", "刚才"),
        ("数据", "例子", "案例", "AlphaFold", "DeepMind", "研究", "医院", "企业"),
        ("风险", "监管", "治理", "安全", "隐私", "就业", "偏见", "幻觉"),
        ("因为", "所以", "因此", "首先", "其次", "最后", "如果", "但是"),
        ("正方", "反方", "不同意", "承认", "反过来", "代价", "收益"),
    )
    for markers in dimensions:
        if any(marker in text for marker in markers):
            score += 1
    if re.search(r"\d", text):
        score += 1
    if len(text) >= 240:
        score += 1
    return score


def _judgement_reason(winner: str, pro_score: int, con_score: int) -> str:
    if winner == "draw":
        return "双方都给出了回应和理由，分差很小，因此判为势均力敌。"
    if winner == "pro":
        return "正方在回应针对性、证据具体性和逻辑连贯度上略占优势。"
    return "反方在回应针对性、风险覆盖和逻辑连贯度上略占优势。"


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
    return cleaned[:80] or "本次讨论主题"


def _latest_user_request(messages: Sequence[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _final_attempt_text(result: TaskResult) -> str:
    if not result.attempts:
        return ""
    return result.attempts[-1].text_preview.strip()
