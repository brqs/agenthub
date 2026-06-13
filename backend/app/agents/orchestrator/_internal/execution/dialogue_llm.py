"""LLM controller for Orchestrator-managed no-artifact dialogue sessions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator._internal.execution.dialogue import (
    _completed_dialogue_tasks,
    _explicit_short_dialogue,
    _final_attempt_text,
    _has_pending_planned_dialogue_turn,
    _is_debate_dialogue,
    _latest_user_request,
    _max_dialogue_turns,
    _participant_order,
)
from app.agents.orchestrator._internal.llm_control import record_llm_control_point
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskResult,
    TaskState,
)
from app.agents.types import ChatMessage, ToolSpec
from app.services.context.compression import truncate_text

DIALOGUE_DECISION_TOOL_NAME = "submit_dialogue_decision"
DIALOGUE_JUDGEMENT_TOOL_NAME = "submit_dialogue_judgement"
DEFAULT_DIALOGUE_LLM_MAX_TOKENS = 2048
MAX_TRANSCRIPT_CHARS = 12000

DIALOGUE_CONTROL_SYSTEM_PROMPT = """You are AgentHub's Orchestrator dialogue moderator.
Control no-artifact multi-agent dialogue. Use only the provided participant agent ids.
Never create file, code, preview, deploy, or tool tasks. Keep each next turn assigned
to exactly one agent. The child agent will speak for itself; do not script every agent.
Return structured tool output only when a tool is available; otherwise output JSON only.
"""

DIALOGUE_JUDGEMENT_SYSTEM_PROMPT = """You are AgentHub's Orchestrator dialogue judge.
Review the completed no-artifact dialogue transcript. For debates, judge whether pro,
con, or neither side is more persuasive. For roundtables or panels, summarize consensus,
disagreements, and useful next steps. Do not invent workspace files or tool results.
Return structured tool output only when a tool is available; otherwise output JSON only.
"""


@dataclass(frozen=True, slots=True)
class DialogueDecision:
    task: SubTask | None
    payload: dict[str, Any]


def dialogue_llm_control_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("orchestrator_dialogue_llm_control_enabled", True) is not False


async def maybe_next_dialogue_turn_with_model(
    *,
    config: Mapping[str, Any],
    messages: Sequence[ChatMessage],
    task_sequence: Sequence[SubTask],
    task_index: int,
    completed_task: SubTask,
    completed_result: TaskResult,
    run_context: OrchestratorRunContext,
) -> DialogueDecision | None:
    if not dialogue_llm_control_enabled(config):
        return None
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
        return DialogueDecision(
            task=None,
            payload={
                "action": "stop",
                "reason": "max_dialogue_turns_reached",
                "turn_count": turn_count,
                "max_turns": max_turns,
            },
        )
    if _explicit_short_dialogue(user_request) and turn_count >= len(participants):
        return DialogueDecision(
            task=None,
            payload={
                "action": "stop",
                "reason": "explicit_short_dialogue_satisfied",
                "turn_count": turn_count,
                "max_turns": max_turns,
            },
        )

    try:
        payload = await _dialogue_tool_payload(
            config,
            messages=[
                ChatMessage(
                    role="user",
                    content=_decision_prompt(
                        user_request=user_request,
                        participants=participants,
                        task_sequence=task_sequence,
                        completed_turns=completed_turns,
                        completed_task=completed_task,
                        completed_result=completed_result,
                        run_context=run_context,
                        turn_count=turn_count,
                        max_turns=max_turns,
                    ),
                )
            ],
            system_prompt=DIALOGUE_CONTROL_SYSTEM_PROMPT,
            tool=_dialogue_decision_tool(participants),
            tool_name=DIALOGUE_DECISION_TOOL_NAME,
            agent_id="orchestrator-dialogue-controller",
        )
    except Exception as exc:
        await record_llm_control_point(
            config,
            run_context,
            phase="dialogue_controller",
            status="failed",
            used_llm=True,
            fallback_reason=_safe_failure_reason(exc),
            decision_summary="Dialogue controller failed while choosing the next turn.",
        )
        return None

    decision = _decision_from_payload(
        payload,
        user_request=user_request,
        participants=participants,
        task_sequence=task_sequence,
        completed_task=completed_task,
        turn_count=turn_count,
        max_turns=max_turns,
    )
    if decision is None:
        await record_llm_control_point(
            config,
            run_context,
            phase="dialogue_controller",
            status="failed",
            used_llm=True,
            fallback_reason="invalid_dialogue_decision",
            decision_summary="Dialogue controller returned an unusable next-turn decision.",
        )
        return None
    await record_llm_control_point(
        config,
        run_context,
        phase="dialogue_controller",
        status="succeeded",
        used_llm=True,
        decision_summary=_dialogue_decision_summary(decision),
    )
    return decision


async def compute_dialogue_judgement_with_model(
    *,
    config: Mapping[str, Any],
    messages: Sequence[ChatMessage],
    tasks: Sequence[SubTask],
    run_context: OrchestratorRunContext,
) -> dict[str, Any] | None:
    if not dialogue_llm_control_enabled(config):
        return None
    dialogue_tasks = [task for task in tasks if task.task_type == "dialogue_turn"]
    if len(dialogue_tasks) < 2:
        return None
    for task in dialogue_tasks:
        result = run_context.results.get(task.task_id)
        if result is None or result.final_state != TaskState.SUCCEEDED:
            return None
    user_request = _latest_user_request(messages)
    participants = _participant_order(dialogue_tasks)
    transcript = _dialogue_transcript(dialogue_tasks, run_context)
    if not transcript:
        return None
    debate = _is_debate_dialogue(user_request, dialogue_tasks)
    try:
        payload = await _dialogue_tool_payload(
            config,
            messages=[
                ChatMessage(
                    role="user",
                    content=_judgement_prompt(
                        user_request=user_request,
                        participants=participants,
                        transcript=transcript,
                        debate=debate,
                    ),
                )
            ],
            system_prompt=DIALOGUE_JUDGEMENT_SYSTEM_PROMPT,
            tool=_dialogue_judgement_tool(debate),
            tool_name=DIALOGUE_JUDGEMENT_TOOL_NAME,
            agent_id="orchestrator-dialogue-judge",
        )
    except Exception as exc:
        await record_llm_control_point(
            config,
            run_context,
            phase="dialogue_controller",
            status="failed",
            used_llm=True,
            fallback_reason=_safe_failure_reason(exc),
            decision_summary="Dialogue controller failed while judging the completed dialogue.",
        )
        return None
    judgement = _judgement_from_payload(payload, debate=debate, participants=participants)
    if judgement is None:
        await record_llm_control_point(
            config,
            run_context,
            phase="dialogue_controller",
            status="failed",
            used_llm=True,
            fallback_reason="invalid_dialogue_judgement",
            decision_summary="Dialogue controller returned an unusable final judgement.",
        )
        return None
    await record_llm_control_point(
        config,
        run_context,
        phase="dialogue_controller",
        status="succeeded",
        used_llm=True,
        decision_summary="Dialogue controller produced the final dialogue judgement.",
    )
    return judgement


async def _dialogue_tool_payload(
    config: Mapping[str, Any],
    *,
    messages: list[ChatMessage],
    system_prompt: str,
    tool: ToolSpec,
    tool_name: str,
    agent_id: str,
) -> dict[str, Any]:
    gateway = _dialogue_gateway(config, agent_id=agent_id, system_prompt=system_prompt)
    text_parts: list[str] = []
    tool_payload: dict[str, Any] | None = None
    async for chunk in gateway.stream(
        messages,
        system_prompt=system_prompt,
        config=_dialogue_model_config(config, tool_name=tool_name),
        tools=[tool],
    ):
        if chunk.event_type == "tool_call" and chunk.tool_name == tool_name:
            tool_payload = chunk.tool_arguments or {}
        elif chunk.event_type == "delta":
            text_parts.append(chunk.text_delta or chunk.code_delta or "")
        elif chunk.event_type == "error":
            raise ValueError(chunk.error or chunk.error_code or "dialogue_llm_error")
    if tool_payload is not None:
        return tool_payload
    text = "".join(text_parts).strip()
    if not text:
        raise ValueError("empty_dialogue_llm_output")
    payload = _json_payload_from_text(text)
    if not isinstance(payload, dict):
        raise ValueError("dialogue_llm_output_must_be_object")
    return payload


def _dialogue_gateway(
    config: Mapping[str, Any],
    *,
    agent_id: str,
    system_prompt: str,
) -> Any:
    gateway = config.get("orchestrator_dialogue_gateway", config.get("dialogue_gateway"))
    if gateway is not None:
        return gateway
    backend = config.get(
        "dialogue_model_backend",
        config.get("planner_model_backend", config.get("model_backend", "claude")),
    )
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("dialogue model backend must be a string")
    return ModelGateway(
        backend,
        default_config=_dialogue_model_config(config),
        agent_id=agent_id,
        system_prompt=system_prompt,
    )


def _dialogue_model_config(
    config: Mapping[str, Any],
    *,
    tool_name: str | None = None,
) -> dict[str, Any]:
    raw_config = config.get("orchestrator_llm_config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raw_config = {}
    model_config: dict[str, Any] = {
        "temperature": 0.2,
        "max_tokens": DEFAULT_DIALOGUE_LLM_MAX_TOKENS,
        "tool_choice": {"type": "tool", "name": tool_name}
        if tool_name
        else {"type": "auto"},
    }
    model_config.update(dict(raw_config))
    for key in ("model", "max_retries", "request_timeout_seconds"):
        if key in config and key not in model_config:
            model_config[key] = config[key]
    return model_config


def _decision_prompt(
    *,
    user_request: str,
    participants: Sequence[str],
    task_sequence: Sequence[SubTask],
    completed_turns: Sequence[SubTask],
    completed_task: SubTask,
    completed_result: TaskResult,
    run_context: OrchestratorRunContext,
    turn_count: int,
    max_turns: int,
) -> str:
    planned = "\n".join(
        f"- {task.task_id}: @{task.agent_id} {task.title}"
        for task in task_sequence
        if task.task_type == "dialogue_turn"
    )
    transcript = _dialogue_transcript(completed_turns, run_context)
    if not transcript:
        transcript = _single_turn_transcript(completed_task, completed_result)
    return (
        "Decide whether the Orchestrator-moderated no-artifact dialogue should continue.\n\n"
        f"User request:\n{user_request}\n\n"
        f"Allowed participant agent ids: {', '.join(participants)}\n"
        f"Completed turns: {turn_count}/{max_turns}\n"
        f"Planned dialogue turns:\n{planned}\n\n"
        f"Latest completed turn:\n{_single_turn_transcript(completed_task, completed_result)}\n\n"
        f"Dialogue transcript excerpt:\n{transcript}\n\n"
        "If the core opposing views have both been heard and no explicit extra rounds are "
        "needed, stop. If continuing would improve the exchange, choose one allowed "
        "participant and write a focused next-turn instruction. The next instruction "
        "must forbid file/artifact/tool/deploy/preview work."
    )


def _judgement_prompt(
    *,
    user_request: str,
    participants: Sequence[str],
    transcript: str,
    debate: bool,
) -> str:
    mode = "debate" if debate else "roundtable"
    return (
        f"Judge this completed AgentHub no-artifact {mode}.\n\n"
        f"User request:\n{user_request}\n\n"
        f"Participants: {', '.join(participants)}\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Use the actual transcript only. For a debate, decide pro, con, or draw. "
        "For non-debate dialogue, use winner=not_applicable and summarize consensus, "
        "disagreements, and next steps."
    )


def _decision_from_payload(
    payload: Mapping[str, Any],
    *,
    user_request: str,
    participants: Sequence[str],
    task_sequence: Sequence[SubTask],
    completed_task: SubTask,
    turn_count: int,
    max_turns: int,
) -> DialogueDecision | None:
    action = _clean_text(payload.get("action")).lower()
    if action not in {"continue", "stop"}:
        return None
    reason = _clean_text(payload.get("reason")) or "llm_dialogue_decision"
    if action == "stop":
        return DialogueDecision(
            task=None,
            payload={
                "action": "stop",
                "reason": reason,
                "turn_count": turn_count,
                "max_turns": max_turns,
            },
        )
    next_agent_id = _clean_text(payload.get("next_agent_id"))
    if next_agent_id not in participants:
        return None
    next_turn_number = turn_count + 1
    task_id = _unique_dialogue_task_id(task_sequence, f"dialogue-turn-{next_turn_number}")
    title = _clean_text(payload.get("title")) or f"第 {next_turn_number} 轮发言"
    instruction = _clean_text(payload.get("instruction"))
    if not instruction:
        return None
    instruction = _guard_dialogue_instruction(instruction, user_request)
    task = SubTask(
        task_id=task_id,
        agent_id=next_agent_id,
        title=title[:160],
        instruction=instruction,
        depends_on=(completed_task.task_id,),
        priority=completed_task.priority + 1,
        expected_output="",
        task_type="dialogue_turn",
    )
    return DialogueDecision(
        task=task,
        payload={
            "action": "continue",
            "next_agent_id": next_agent_id,
            "title": task.title,
            "reason": reason,
            "turn_count": turn_count,
            "max_turns": max_turns,
        },
    )


def _judgement_from_payload(
    payload: Mapping[str, Any],
    *,
    debate: bool,
    participants: Sequence[str],
) -> dict[str, Any] | None:
    summary = _clean_text(payload.get("summary"))
    reason = _clean_text(payload.get("reason"))
    if not summary and not reason:
        return None
    winner = _clean_text(payload.get("winner")).lower()
    allowed_winners = {"pro", "con", "draw"} if debate else {"not_applicable", "draw"}
    if winner not in allowed_winners:
        winner = "draw" if debate else "not_applicable"
    default_label = {
        "pro": "正方更有说服力",
        "con": "反方更有说服力",
        "draw": "势均力敌",
        "not_applicable": "已完成圆桌总结",
    }[winner]
    return {
        "type": "llm_dialogue_judgement",
        "mode": "debate" if debate else "roundtable",
        "winner": winner,
        "winner_label": _clean_text(payload.get("winner_label")) or default_label,
        "summary": summary,
        "reason": reason or summary,
        "key_points": _clean_string_list(payload.get("key_points")),
        "pro_strengths": _clean_string_list(payload.get("pro_strengths")),
        "con_strengths": _clean_string_list(payload.get("con_strengths")),
        "weaknesses": _clean_string_list(payload.get("weaknesses")),
        "participants": list(participants),
        "source": "orchestrator_llm",
    }


def _dialogue_decision_tool(participants: Sequence[str]) -> ToolSpec:
    return ToolSpec(
        name=DIALOGUE_DECISION_TOOL_NAME,
        description="Decide whether to continue an Orchestrator-moderated dialogue.",
        parameters={
            "type": "object",
            "required": ["action", "reason"],
            "properties": {
                "action": {"type": "string", "enum": ["continue", "stop"]},
                "next_agent_id": {"type": "string", "enum": list(participants)},
                "title": {"type": "string"},
                "instruction": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
    )


def _dialogue_judgement_tool(debate: bool) -> ToolSpec:
    winners = ["pro", "con", "draw"] if debate else ["not_applicable", "draw"]
    return ToolSpec(
        name=DIALOGUE_JUDGEMENT_TOOL_NAME,
        description="Submit final judgement or synthesis for a completed dialogue.",
        parameters={
            "type": "object",
            "required": ["winner", "summary", "reason"],
            "properties": {
                "winner": {"type": "string", "enum": winners},
                "winner_label": {"type": "string"},
                "summary": {"type": "string"},
                "reason": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "pro_strengths": {"type": "array", "items": {"type": "string"}},
                "con_strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
            },
        },
    )


def _dialogue_transcript(
    tasks: Sequence[SubTask],
    run_context: OrchestratorRunContext,
) -> str:
    lines: list[str] = []
    for task in tasks:
        result = run_context.results.get(task.task_id)
        if result is None or not result.attempts:
            continue
        text = _final_attempt_text(result)
        if not text:
            continue
        lines.append(f"[{task.task_id} @{result.attempts[-1].agent_id} | {task.title}]\n{text}")
    return truncate_text("\n\n".join(lines), MAX_TRANSCRIPT_CHARS)


def _single_turn_transcript(task: SubTask, result: TaskResult) -> str:
    text = _final_attempt_text(result)
    return truncate_text(f"[{task.task_id} @{task.agent_id} | {task.title}]\n{text}", 3000)


def _guard_dialogue_instruction(instruction: str, user_request: str) -> str:
    guard = (
        "No-artifact dialogue guard: speak only for yourself in this AgentHub group "
        "dialogue turn. Do not create, edit, or request files, code artifacts, reports, "
        "previews, deployments, or platform tools. Do not script another Agent's full "
        "reply; respond to the prior turn and advance your assigned role."
    )
    if "No-artifact dialogue guard:" in instruction:
        return instruction
    return f"{instruction}\n\n{guard}\n\nOriginal user request:\n{user_request}"


def _unique_dialogue_task_id(tasks: Sequence[SubTask], desired: str) -> str:
    existing = {task.task_id for task in tasks}
    if desired not in existing:
        return desired
    index = 2
    while f"{desired}-{index}" in existing:
        index += 1
    return f"{desired}-{index}"


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", "").split()).strip()


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value for text in [_clean_text(item)] if text][:8]


def _dialogue_decision_summary(decision: DialogueDecision) -> str:
    action = str(decision.payload.get("action") or "unknown")
    if decision.task is None:
        return f"Dialogue controller chose to {action}."
    return (
        "Dialogue controller scheduled the next turn for "
        f"{decision.task.agent_id}."
    )


def _safe_failure_reason(exc: Exception) -> str:
    if not isinstance(exc, ValueError):
        return exc.__class__.__name__
    text = str(exc).strip()
    if not text:
        return exc.__class__.__name__
    return text[:180]


def _json_payload_from_text(text: str) -> Any:
    stripped = _strip_json_fence(text)
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "{[":
            continue
        try:
            payload, _ = decoder.raw_decode(stripped[index:])
            return payload
        except json.JSONDecodeError:
            continue
    raise ValueError("dialogue_llm_invalid_json")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    first_newline = stripped.find("\n")
    last_fence = stripped.rfind("```")
    if first_newline == -1 or last_fence <= first_newline:
        return stripped
    return stripped[first_newline + 1 : last_fence].strip()
