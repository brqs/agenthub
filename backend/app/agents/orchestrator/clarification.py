"""Clarification gate and Matt Pocock-style grill commands for Orchestrator."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from app.agents.model_gateway import ModelGateway
from app.agents.orchestrator._internal.memory import (
    finish_run,
    record_event,
    start_run,
)
from app.agents.orchestrator.types import OrchestratorRunContext
from app.agents.types import ChatMessage, StreamChunk

ClarificationMode = Literal[
    "auto",
    "requirement_alignment",
    "previous_output_followup",
    "grill_me",
    "grill_with_docs",
    "setup_matt_pocock_skills",
]
ClarificationReplyRoute = Literal[
    "answer_current",
    "reference_context",
    "new_topic",
    "explicit_switch",
    "control",
    "repeat_current",
    "ambiguous",
]

COMMAND_RE = re.compile(
    r"^\s*(?:@orchestrator\s+)?/(?P<command>grill-me|grill-with-docs|setup-matt-pocock-skills)\b(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)
CLARIFICATION_STATE_PREFIX = "[Clarification state] "
CLARIFICATION_SKIP_MARKERS = (
    "不要追问",
    "不用追问",
    "别追问",
    "不需要追问",
    "不用问",
    "别问",
    "no questions",
    "don't ask",
)
BYPASS_MARKERS = (
    *CLARIFICATION_SKIP_MARKERS,
    "直接做",
    "直接实现",
    "按默认",
    "使用默认",
    "你决定",
    "你来定",
    "use defaults",
)
CANCEL_MARKERS = ("取消", "先不用", "停止", "不用了", "cancel", "stop")
NEGATION_MARKERS = (
    "不要",
    "不用",
    "别",
    "不想",
    "不能",
    "还没",
    "尚未",
    "没有确认",
    "未确认",
    "no ",
    "not ",
    "don't",
    "do not",
)
DEFAULT_MARKERS = (
    "按默认",
    "使用默认",
    "默认方案",
    "你决定",
    "你来定",
    "使用推荐",
    "推荐答案",
    "推荐默认",
    "推荐配置",
    "use defaults",
)
DIRECT_PROCEED_MARKERS = (
    "按这个做",
    "按这个开始",
    "开始实现",
    "开始执行",
    "确认开始",
    "确认执行",
    "直接做",
    "直接实现",
    "继续执行",
    "go ahead",
    "proceed",
)
DEFAULT_PROCEED_MARKERS = (
    "按默认开始",
    "按默认实现",
    "按默认执行",
    "使用默认开始",
    "使用推荐开始",
    "按推荐开始",
    "use defaults and proceed",
)
SETUP_CONFIRM_MARKERS = (
    "使用推荐配置",
    "确认使用推荐",
    "确认初始化",
    "确认写入",
    "按推荐写入",
    "写入推荐配置",
)
DOCS_CONFIRM_MARKERS = (
    "记录",
    "写入",
    "保存",
    "更新 context",
    "更新context",
    "确认使用此定义",
    "确认使用这个定义",
    "使用这个定义",
    "用这个定义",
)
REFERENCE_MARKERS = ("参考", "借鉴", "类似", "像", "对标", "作为参考", "作为例子")
SWITCH_MARKERS = (
    "先不做",
    "先别做",
    "暂停",
    "放弃",
    "改做",
    "改成",
    "换成",
    "切换到",
    "转到",
    "instead",
    "switch to",
)
QUESTION_MARKERS = ("?", "？", "怎么", "如何", "为什么", "能不能", "可不可以", "吗")

BUILD_MARKERS = (
    "build",
    "create",
    "generate",
    "implement",
    "design",
    "make",
    "写",
    "做",
    "设计",
    "制作",
    "开发",
    "实现",
    "生成",
)
ARTIFACT_MARKERS = (
    "web",
    "html",
    "css",
    "js",
    "react",
    "page",
    "component",
    "game",
    "网页",
    "网页版",
    "页面",
    "组件",
    "游戏",
    "文件",
    "产物",
)

DISCUSSION_MARKERS = (
    "辩论",
    "讨论",
    "群聊",
    "对话",
    "正方",
    "反方",
    "主持",
    "总结",
    "debate",
    "discussion",
    "conversation",
)
DOCUMENT_MARKERS = (
    "文档",
    "文章",
    "报告",
    "说明",
    "方案",
    "规范",
    "spec",
    "doc",
    "report",
)
ANALYSIS_MARKERS = (
    "分析",
    "比较",
    "评估",
    "判断",
    "可行性",
    "优缺点",
    "对比",
    "analysis",
    "compare",
    "evaluate",
)
CODE_CHANGE_MARKERS = (
    "修改代码",
    "修复 bug",
    "修复bug",
    "改代码",
    "重构",
    "补测试",
    "review",
    "fix",
    "refactor",
    "test",
)
SMALL_TALK_MARKERS = (
    "你好",
    "您好",
    "你是谁",
    "有哪些 agent",
    "有哪些agent",
    "help",
    "hello",
    "hi",
)

GRILL_QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "audience_goal",
        "question": "这个需求最重要的目标用户和成功标准是什么？",
        "reason": "先锁定使用场景，后续 Agent 才不会只做一个看起来能跑、但不贴合目标的产物。",
        "recommended_answer": (
            "面向普通用户，优先做一个可直接打开、交互清晰、"
            "移动端和桌面端都稳定的版本。"
        ),
        "options": ["使用推荐答案", "强调移动端", "强调视觉精致"],
    },
    {
        "id": "interaction_scope",
        "question": "核心交互范围要做到哪一档？",
        "reason": "交互边界会直接决定文件结构、状态管理、验收标准和需要调用的执行 Agent。",
        "recommended_answer": (
            "做到完整主流程：开始、操作、反馈、失败/完成、重新开始，"
            "以及基础异常状态。"
        ),
        "options": ["完整主流程", "先做最小可用", "做得更精致"],
    },
    {
        "id": "visual_direction",
        "question": "视觉方向和信息密度有什么偏好？",
        "reason": "前端产物不能只满足功能，需要提前约束视觉风格，避免实现阶段返工。",
        "recommended_answer": (
            "克制但精致，界面层次清楚，避免大面积单色和装饰性渐变，"
            "内容优先可读。"
        ),
        "options": ["克制精致", "游戏感更强", "偏工具化"],
    },
    {
        "id": "acceptance",
        "question": "你希望这次交付用什么标准验收？",
        "reason": "验收标准越具体，Orchestrator 越能判断何时可以调度、何时需要修复。",
        "recommended_answer": (
            "产物包含明确入口文件，可直接预览；无明显 JS 错误；"
            "桌面和移动宽度下不重叠。"
        ),
        "options": ["使用推荐验收", "增加代码说明", "增加测试/检查"],
    },
)

AUTO_QUESTION = {
    "id": "delivery_defaults",
    "question": "这个构建请求目前规格偏宽，你希望我按什么默认交付边界开始？",
    "reason": "先确认默认边界，可以避免 Orchestrator 过早调用执行 Agent 后产物方向偏掉。",
    "recommended_answer": (
        "按可直接运行的静态前端产物开始：包含入口文件、核心交互、"
        "基础响应式和无明显运行错误。"
    ),
    "options": ["使用推荐默认", "更重视觉", "更重功能"],
}

DOCS_QUESTION = {
    "id": "term_definition",
    "question": "当前需求或项目里，哪个词最容易被 Agent 误解？请给出它在本会话里的准确定义。",
    "reason": (
        "这个定义会写入当前 Workspace 的 CONTEXT.md，"
        "后续 Orchestrator 和执行 Agent 会优先使用它。"
    ),
    "recommended_answer": "先定义本轮最关键的产物或领域词，例如“精致”“可玩”“完成态”的具体含义。",
    "options": ["使用推荐方向", "定义产物词", "定义验收词"],
}

SETUP_CONFIRM_QUESTION = {
    "id": "setup_confirm",
    "question": "是否使用推荐配置初始化本会话 Workspace 的 Agent 协作文档？",
    "reason": "这只会写入当前会话 Workspace，不会修改 AgentHub 主项目仓库。",
    "recommended_answer": (
        "使用推荐配置：本地 markdown issue tracker、默认 triage label、"
        "单一 CONTEXT.md 文档布局。"
    ),
    "options": ["使用推荐配置", "自定义配置", "取消"],
}


@dataclass(slots=True)
class ClarificationOutcome:
    chunks: tuple[StreamChunk, ...]
    next_block_index: int
    done: bool
    continue_messages: list[ChatMessage] | None = None


async def maybe_handle_clarification(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    latest_user_request: Callable[[list[ChatMessage]], str],
    has_task_intent: Callable[[str], bool],
    allow_auto_start: bool = True,
) -> ClarificationOutcome | None:
    if config.get("clarification_gate_enabled", True) is False:
        return None

    user_request = latest_user_request(messages)
    command = _parse_command(user_request)
    pending = _latest_pending_clarification(messages)

    if pending is not None and command is None:
        if _mode(pending) == "previous_output_followup":
            return None
        return await _handle_pending_answer(
            config,
            messages,
            next_block_index,
            workspace_path,
            user_request=user_request,
            state=pending,
            has_task_intent=has_task_intent,
        )

    if command is not None:
        return await _start_command(
            config,
            next_block_index,
            workspace_path,
            mode=command["mode"],
            original_request=command["body"],
        )

    if allow_auto_start and _should_auto_clarify(config, user_request, has_task_intent):
        question = await _requirement_alignment_question(config, messages, user_request)
        return await _ask_question(
            config,
            next_block_index,
            mode="requirement_alignment",
            title=_requirement_alignment_title(config, "Orchestrator 需求对齐"),
            question=question,
            original_request=user_request,
            question_count=1,
            max_questions=_positive_int(config, "auto_clarification_max_questions", 3),
        )

    return None


def _parse_command(text: str) -> dict[str, str] | None:
    match = COMMAND_RE.match(text)
    if match is None:
        return None
    command = match.group("command").lower()
    mode: ClarificationMode
    if command == "grill-me":
        mode = "grill_me"
    elif command == "grill-with-docs":
        mode = "grill_with_docs"
    else:
        mode = "setup_matt_pocock_skills"
    return {"mode": mode, "body": match.group("body").strip()}


async def _start_command(
    config: Mapping[str, Any],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    mode: str,
    original_request: str,
) -> ClarificationOutcome:
    if mode == "setup_matt_pocock_skills":
        return await _ask_question(
            config,
            next_block_index,
            mode="setup_matt_pocock_skills",
            title="Matt Pocock Skills 初始化",
            question=SETUP_CONFIRM_QUESTION,
            original_request=original_request or "setup matt pocock skills",
            question_count=1,
            max_questions=3,
        )
    if mode == "grill_with_docs":
        docs_summary = _workspace_docs_summary(workspace_path)
        question = {
            **DOCS_QUESTION,
            "reason": f"{DOCS_QUESTION['reason']} 当前可读文档：{docs_summary}",
        }
        return await _ask_question(
            config,
            next_block_index,
            mode="grill_with_docs",
            title="带文档的需求澄清",
            question=question,
            original_request=original_request or "grill with docs",
            question_count=1,
            max_questions=3,
        )

    question = GRILL_QUESTIONS[0]
    return await _ask_question(
        config,
        next_block_index,
        mode="grill_me",
        title="需求追问",
        question=question,
        original_request=original_request or "grill me",
        question_count=1,
        max_questions=_positive_int(config, "grill_max_questions", 8),
    )


async def _handle_pending_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    user_request: str,
    state: dict[str, Any],
    has_task_intent: Callable[[str], bool],
) -> ClarificationOutcome | None:
    if _contains_any(user_request, CANCEL_MARKERS):
        agent_id = _clarification_agent_id_from_state(state)
        chunks = _clarification_block_chunks(
            next_block_index,
            agent_id=agent_id,
            mode=_mode(state),
            title=str(state.get("title") or "需求澄清"),
            status="cancelled",
            question=_answered_question(state, user_request, status="skipped"),
            questions=_answered_questions_with_current(state, user_request, status="skipped"),
            summary="已取消本次澄清。",
            metadata={**_metadata(state), "cancelled_by_user": True},
        )
        await _record_clarification(config, "clarification_cancelled", state, user_request)
        return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 1, done=True)

    route = classify_pending_clarification_reply(state, user_request)
    if _is_topic_route_state(state):
        routed = await _handle_topic_route_answer(
            config,
            messages,
            next_block_index,
            workspace_path,
            state=state,
            user_request=user_request,
            route=route,
            has_task_intent=has_task_intent,
        )
        if routed is not None:
            return routed
    if route == "explicit_switch":
        return await _switch_clarification_topic(
            config,
            messages,
            next_block_index,
            workspace_path,
            state=state,
            user_request=_switch_request_text(user_request),
            has_task_intent=has_task_intent,
        )
    if route == "repeat_current":
        return await _repeat_current_clarification(
            config,
            next_block_index,
            state=state,
            user_request=user_request,
        )
    if route in {"new_topic", "ambiguous"}:
        return await _ask_topic_route_confirmation(
            config,
            next_block_index,
            state=state,
            user_request=user_request,
            route=route,
        )

    mode = _mode(state)
    if mode == "setup_matt_pocock_skills":
        return await _handle_setup_answer(
            config,
            next_block_index,
            workspace_path,
            state=state,
            user_request=user_request,
        )
    if mode == "grill_with_docs":
        return await _handle_docs_answer(
            config,
            next_block_index,
            workspace_path,
            state=state,
            user_request=user_request,
        )

    if _should_continue_after_answer(user_request):
        resolved = _resolved_chunks(next_block_index, state, user_request)
        await _record_clarification(config, "clarification_resolved", state, user_request)
        return ClarificationOutcome(
            chunks=resolved,
            next_block_index=next_block_index + 1,
            done=False,
            continue_messages=_augmented_messages(messages, state, user_request),
        )

    if mode in {"auto", "requirement_alignment"}:
        return await _ask_proceed_confirmation(
            config,
            next_block_index,
            state=state,
            user_request=user_request,
        )

    question_count = _question_count(state)
    max_questions = min(_max_questions(state), len(GRILL_QUESTIONS))
    if mode == "grill_me" and question_count < max_questions:
        next_question = GRILL_QUESTIONS[question_count]
        return await _ask_question(
            config,
            next_block_index,
            mode="grill_me",
            title="需求追问",
            question=next_question,
            original_request=_original_request(state),
            question_count=question_count + 1,
            max_questions=_max_questions(state),
            answered_questions=_answered_questions_with_current(state, user_request),
        )

    summary = _requirements_brief(state, user_request)
    final_chunks = (
        *_clarification_block_chunks(
            next_block_index,
            agent_id=_clarification_agent_id_from_state(state),
            mode=mode,
            title=str(state.get("title") or "需求追问"),
            status="resolved",
            question=_answered_question(state, user_request),
            questions=_answered_questions_with_current(state, user_request),
            summary=summary,
            metadata={**_metadata(state), "resolved_by_user": True},
        ),
        *_text_block(
            next_block_index + 1,
            summary,
            agent_id=_clarification_agent_id_from_state(state),
        ),
    )
    await _record_clarification(config, "clarification_resolved", state, user_request)
    return ClarificationOutcome(
        chunks=final_chunks,
        next_block_index=next_block_index + 2,
        done=True,
    )


async def _handle_setup_answer(
    config: Mapping[str, Any],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    state: dict[str, Any],
    user_request: str,
) -> ClarificationOutcome:
    if _is_setup_custom_request(user_request):
        question = {
            "id": "setup_custom",
            "question": "请用一段话说明你想使用的 issue tracker、标签体系和领域文档布局。",
            "reason": "第一版会把你的自定义说明写进 docs/agents/*，后续可继续人工细化。",
            "recommended_answer": (
                "继续使用本地 markdown issue tracker；保留默认 triage label；"
                "使用单一 CONTEXT.md。"
            ),
            "options": ["使用这段自定义", "改用推荐配置"],
        }
        return await _ask_question(
            config,
            next_block_index,
            mode="setup_matt_pocock_skills",
            title="Matt Pocock Skills 初始化",
            question=question,
            original_request=_original_request(state),
            question_count=_question_count(state) + 1,
            max_questions=3,
            answered_questions=_answered_questions_with_current(state, user_request),
        )

    if not _is_confirm_setup_write(user_request):
        return await _ask_setup_write_confirmation(
            config,
            next_block_index,
            state=state,
            user_request=user_request,
        )

    answer = _answer_or_default(state, user_request)
    error = (
        "workspace docs are disabled"
        if config.get("workspace_docs_enabled", True) is False
        else _write_setup_docs(workspace_path, answer)
    )
    status: Literal["resolved", "cancelled"] = "resolved" if error is None else "cancelled"
    summary = (
        "已在当前 Workspace 写入 AGENTS.md 和 docs/agents/* 协作说明。"
        if error is None
        else f"Workspace 文档初始化失败：{error}"
    )
    chunks = (
        *_clarification_block_chunks(
            next_block_index,
            agent_id=_clarification_agent_id_from_config(config),
            mode="setup_matt_pocock_skills",
            title="Matt Pocock Skills 初始化",
            status=status,
            question=_answered_question(state, user_request),
            questions=_answered_questions_with_current(state, user_request),
            summary=summary,
            metadata={**_metadata(state), "workspace_docs": error is None},
        ),
        *_text_block(
            next_block_index + 1,
            summary,
            agent_id=_clarification_agent_id_from_config(config),
        ),
    )
    await _record_clarification(config, "clarification_resolved", state, user_request)
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 2, done=True)


async def _handle_docs_answer(
    config: Mapping[str, Any],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    state: dict[str, Any],
    user_request: str,
) -> ClarificationOutcome:
    if not _is_confirm_docs_write(user_request):
        return await _ask_docs_write_confirmation(
            config,
            next_block_index,
            state=state,
            user_request=user_request,
        )

    answer = _docs_answer_for_write(state, user_request)
    error = (
        "workspace docs are disabled"
        if config.get("workspace_docs_enabled", True) is False
        else _append_context_definition(workspace_path, answer)
    )
    summary = (
        "已把这条定义追加到当前 Workspace 的 CONTEXT.md。"
        if error is None
        else f"CONTEXT.md 更新失败：{error}"
    )
    chunks = (
        *_clarification_block_chunks(
            next_block_index,
            agent_id=_clarification_agent_id_from_config(config),
            mode="grill_with_docs",
            title="带文档的需求澄清",
            status="resolved" if error is None else "cancelled",
            question=_answered_question(state, user_request),
            questions=_answered_questions_with_current(state, user_request),
            summary=summary,
            metadata={**_metadata(state), "context_updated": error is None},
        ),
        *_text_block(
            next_block_index + 1,
            summary,
            agent_id=_clarification_agent_id_from_config(config),
        ),
    )
    await _record_clarification(config, "clarification_resolved", state, user_request)
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 2, done=True)


async def _ask_question(
    config: Mapping[str, Any],
    next_block_index: int,
    *,
    mode: str,
    title: str,
    question: Mapping[str, Any],
    original_request: str,
    question_count: int,
    max_questions: int,
    answered_questions: list[dict[str, Any]] | None = None,
) -> ClarificationOutcome:
    current_question = _question_payload(question)
    questions = [*(answered_questions or []), current_question]
    agent_id = _clarification_agent_id_from_config(config)
    metadata = {
        "original_request": original_request,
        "question_count": question_count,
        "max_questions": max_questions,
        "agent_id": agent_id,
    }
    chunks = _clarification_block_chunks(
        next_block_index,
        agent_id=agent_id,
        mode=_safe_mode(mode),
        title=title,
        status="waiting",
        question=current_question,
        questions=questions,
        summary=None,
        metadata=metadata,
    )
    await _record_clarification(
        config,
        "clarification_question_asked",
        {
            "mode": mode,
            "title": title,
            "current_question": current_question,
            "metadata": metadata,
        },
        "",
    )
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 1, done=True)


def _clarification_block_chunks(
    block_index: int,
    *,
    agent_id: str = "orchestrator",
    mode: ClarificationMode,
    title: str,
    status: Literal["waiting", "resolved", "cancelled"],
    question: dict[str, Any] | None,
    questions: list[dict[str, Any]],
    summary: str | None,
    metadata: dict[str, Any],
) -> tuple[StreamChunk, StreamChunk]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "mode": mode,
        "title": title,
        "status": status,
        "questions": questions,
        "metadata": metadata,
    }
    if question is not None:
        payload["current_question"] = question
    if summary is not None:
        payload["summary"] = summary
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="clarification",
            agent_id=agent_id,
            metadata=payload,
        ),
        StreamChunk(event_type="block_end", block_index=block_index, agent_id=agent_id),
    )


def _text_block(
    block_index: int,
    text: str,
    *,
    agent_id: str = "orchestrator",
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="delta",
            block_index=block_index,
            text_delta=text,
            agent_id=agent_id,
        ),
        StreamChunk(event_type="block_end", block_index=block_index, agent_id=agent_id),
    )


def _resolved_chunks(
    block_index: int,
    state: dict[str, Any],
    answer: str,
) -> tuple[StreamChunk, StreamChunk]:
    return _clarification_block_chunks(
        block_index,
        agent_id=_clarification_agent_id_from_state(state),
        mode=_mode(state),
        title=str(state.get("title") or "需求澄清"),
        status="resolved",
        question=_answered_question(state, answer),
        questions=_answered_questions_with_current(state, answer),
        summary="已确认澄清信息，继续进入任务规划。",
        metadata={**_metadata(state), "resolved_by_user": True},
    )


def classify_pending_clarification_reply(
    state: dict[str, Any],
    user_request: str,
) -> ClarificationReplyRoute:
    if _is_topic_route_state(state):
        if _is_switch_selection(user_request):
            return "explicit_switch"
        if _is_reference_selection(user_request):
            return "reference_context"
        if _is_continue_current_selection(user_request):
            return "control"
    if _should_continue_after_answer(user_request) or _is_confirm_setup_write(
        user_request
    ) or _is_confirm_docs_write(user_request):
        return "control"
    if _is_explicit_switch_request(user_request):
        return "explicit_switch"
    if _is_repeated_current_request(state, user_request):
        return "repeat_current"

    original = _original_request(state)
    current_question = state.get("current_question")
    question_text = (
        str(current_question.get("question") or "") if isinstance(current_question, dict) else ""
    )
    original_labels = _project_labels(f"{original} {question_text}")
    user_labels = _project_labels(user_request)
    mentions_other_project = bool(
        user_labels and (not original_labels or user_labels - original_labels)
    )
    if mentions_other_project and _contains_any(user_request, REFERENCE_MARKERS):
        return "reference_context"
    if mentions_other_project and _looks_like_question_or_task(user_request):
        return "new_topic"
    if _contains_any(user_request, REFERENCE_MARKERS):
        return "reference_context"
    if _looks_like_question_or_task(user_request) and not _looks_like_short_answer(user_request):
        return "ambiguous"
    return "answer_current"


async def _handle_topic_route_answer(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    state: dict[str, Any],
    user_request: str,
    route: ClarificationReplyRoute,
    has_task_intent: Callable[[str], bool],
) -> ClarificationOutcome | None:
    previous = _previous_clarification_state(state)
    pending_text = _pending_route_text(state) or user_request
    if route == "explicit_switch":
        return await _switch_clarification_topic(
            config,
            messages,
            next_block_index,
            workspace_path,
            state=previous or state,
            user_request=pending_text,
            has_task_intent=has_task_intent,
        )
    if previous is None:
        return None
    if route == "reference_context":
        reference_answer = pending_text
        if not _contains_any(reference_answer, REFERENCE_MARKERS):
            reference_answer = f"参考 {reference_answer}"
        return await _handle_pending_answer(
            config,
            messages,
            next_block_index,
            workspace_path,
            user_request=reference_answer,
            state=previous,
            has_task_intent=has_task_intent,
        )
    if _is_continue_current_selection(user_request):
        question = previous.get("current_question")
        if isinstance(question, dict):
            return await _ask_question(
                config,
                next_block_index,
                mode=_mode(previous),
                title=str(previous.get("title") or "需求澄清"),
                question=question,
                original_request=_original_request(previous),
                question_count=_question_count(previous),
                max_questions=_max_questions(previous),
                answered_questions=[
                    item
                    for item in previous.get("questions", [])
                    if isinstance(item, dict) and item.get("status") != "pending"
                ],
            )
    return None


async def _switch_clarification_topic(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
    *,
    state: dict[str, Any],
    user_request: str,
    has_task_intent: Callable[[str], bool],
) -> ClarificationOutcome:
    cancel_chunks = _clarification_block_chunks(
        next_block_index,
        agent_id=_clarification_agent_id_from_state(state),
        mode=_mode(state),
        title=str(state.get("title") or "需求澄清"),
        status="cancelled",
        question=_answered_question(state, user_request, status="skipped"),
        questions=_answered_questions_with_current(state, user_request, status="skipped"),
        summary="已暂停上一轮澄清，切换到新的请求。",
        metadata={**_metadata(state), "switched_by_user": True},
    )
    await _record_clarification(config, "clarification_cancelled", state, user_request)
    if _should_auto_clarify(config, user_request, has_task_intent):
        alignment_question = await _requirement_alignment_question(config, messages, user_request)
        question = await _ask_question(
            config,
            next_block_index + 1,
            mode="requirement_alignment",
            title=_requirement_alignment_title(config, "Orchestrator 需求对齐"),
            question=alignment_question,
            original_request=user_request,
            question_count=1,
            max_questions=_positive_int(config, "auto_clarification_max_questions", 3),
        )
        return ClarificationOutcome(
            chunks=(*cancel_chunks, *question.chunks),
            next_block_index=question.next_block_index,
            done=True,
        )
    return ClarificationOutcome(
        chunks=cancel_chunks,
        next_block_index=next_block_index + 1,
        done=False,
        continue_messages=[*messages[:-1], ChatMessage(role="user", content=user_request)],
    )


async def _ask_topic_route_confirmation(
    config: Mapping[str, Any],
    next_block_index: int,
    *,
    state: dict[str, Any],
    user_request: str,
    route: ClarificationReplyRoute,
) -> ClarificationOutcome:
    original = _original_request(state) or "当前需求"
    pending = user_request.strip()
    question = {
        "id": "topic_route",
        "question": (
            f"我现在还在澄清“{_short_text(original)}”。"
            "你是想继续这个需求、切换到新需求，还是把刚才内容作为参考？"
        ),
        "reason": "这样可以避免把项目 B 的问题误当成项目 A 的答案，也不会静默丢掉你的新意图。",
        "recommended_answer": f"继续澄清当前需求：{_short_text(original)}",
        "options": [
            f"继续澄清当前需求：{_short_text(original)}",
            f"切换到新需求：{_short_text(pending)}",
            f"把新内容作为当前需求参考：{_short_text(pending)}",
        ],
    }
    chunks = _clarification_block_chunks(
        next_block_index,
        agent_id=_clarification_agent_id_from_state(state),
        mode=_mode(state),
        title="确认澄清方向",
        status="waiting",
        question=_question_payload(question),
        questions=[
            *_answered_questions_with_current(state, user_request),
            _question_payload(question),
        ],
        summary=None,
        metadata={
            **_metadata(state),
            "route": route,
            "route_pending_user_request": pending,
            "previous_clarification_state": state,
        },
    )
    await _record_clarification(config, "clarification_question_asked", state, user_request)
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 1, done=True)


async def _repeat_current_clarification(
    config: Mapping[str, Any],
    next_block_index: int,
    *,
    state: dict[str, Any],
    user_request: str,
) -> ClarificationOutcome:
    raw_question = state.get("current_question")
    current_question = dict(raw_question) if isinstance(raw_question, dict) else None
    questions = [
        dict(item)
        for item in state.get("questions", [])
        if isinstance(item, dict)
    ]
    if current_question is not None and not any(
        item.get("id") == current_question.get("id") for item in questions
    ):
        questions.append(current_question)
    summary = (
        "我理解你仍在描述同一个需求；请直接选择推荐默认、补充交付边界，"
        "或发送“取消”。只有明确发送“按这个做”或“开始实现”后，我才会进入实现。"
    )
    chunks = (
        *_clarification_block_chunks(
            next_block_index,
            agent_id=_clarification_agent_id_from_state(state),
            mode=_mode(state),
            title=str(state.get("title") or "Orchestrator 需求澄清"),
            status="waiting",
            question=current_question,
            questions=questions,
            summary=summary,
            metadata={**_metadata(state), "repeated_request": user_request},
        ),
        *_text_block(
            next_block_index + 1,
            summary,
            agent_id=_clarification_agent_id_from_state(state),
        ),
    )
    await _record_clarification(
        config,
        "clarification_repeated_request",
        state,
        user_request,
    )
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 2, done=True)


async def _ask_proceed_confirmation(
    config: Mapping[str, Any],
    next_block_index: int,
    *,
    state: dict[str, Any],
    user_request: str,
) -> ClarificationOutcome:
    answer = _answer_or_default(state, user_request)
    summary = _requirements_brief(state, user_request)
    question = {
        "id": "confirm_proceed",
        "question": "我已整理这条补充。是否现在按这个方向进入实现？",
        "reason": "只有你明确确认后，我才会进入任务规划并调度执行 Agent。",
        "recommended_answer": "按这个做",
        "options": ["按这个做", "补充更多细节", "取消"],
    }
    answered_questions = _answered_questions_with_current(state, user_request)
    chunks = (
        *_clarification_block_chunks(
            next_block_index,
            agent_id=_clarification_agent_id_from_state(state),
            mode=_mode(state),
            title=str(state.get("title") or "需求澄清"),
            status="waiting",
            question=_question_payload(question),
            questions=[*answered_questions, _question_payload(question)],
            summary=summary,
            metadata={**_metadata(state), "pending_answer": answer},
        ),
        *_text_block(
            next_block_index + 1,
            summary,
            agent_id=_clarification_agent_id_from_state(state),
        ),
    )
    await _record_clarification(config, "clarification_question_asked", state, user_request)
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 2, done=True)


async def _ask_setup_write_confirmation(
    config: Mapping[str, Any],
    next_block_index: int,
    *,
    state: dict[str, Any],
    user_request: str,
) -> ClarificationOutcome:
    question = {
        "id": "setup_write_confirm",
        "question": "要现在把推荐配置写入当前 Workspace 吗？",
        "reason": "这会产生 AGENTS.md 和 docs/agents/* 文件，所以需要明确确认。",
        "recommended_answer": "确认使用推荐配置",
        "options": ["确认使用推荐配置", "自定义配置", "取消"],
    }
    chunks = _clarification_block_chunks(
        next_block_index,
        agent_id=_clarification_agent_id_from_state(state),
        mode="setup_matt_pocock_skills",
        title="Matt Pocock Skills 初始化",
        status="waiting",
        question=_question_payload(question),
        questions=[
            *_answered_questions_with_current(state, user_request),
            _question_payload(question),
        ],
        summary="尚未写入 Workspace；等待你确认。",
        metadata={**_metadata(state), "pending_setup_answer": user_request.strip()},
    )
    await _record_clarification(config, "clarification_question_asked", state, user_request)
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 1, done=True)


async def _ask_docs_write_confirmation(
    config: Mapping[str, Any],
    next_block_index: int,
    *,
    state: dict[str, Any],
    user_request: str,
) -> ClarificationOutcome:
    answer = _answer_or_default(state, user_request)
    question = {
        "id": "docs_write_confirm",
        "question": "要把这条定义写入当前 Workspace 的 CONTEXT.md 吗？",
        "reason": "写入后后续 Orchestrator 和执行 Agent 会把它当作本会话术语事实使用。",
        "recommended_answer": f"确认写入这条定义：{_short_text(answer)}",
        "options": ["确认写入", "继续修改定义", "取消"],
    }
    chunks = _clarification_block_chunks(
        next_block_index,
        agent_id=_clarification_agent_id_from_state(state),
        mode="grill_with_docs",
        title="带文档的需求澄清",
        status="waiting",
        question=_question_payload(question),
        questions=[
            *_answered_questions_with_current(state, user_request),
            _question_payload(question),
        ],
        summary="尚未更新 CONTEXT.md；等待你确认。",
        metadata={**_metadata(state), "pending_docs_answer": answer},
    )
    await _record_clarification(config, "clarification_question_asked", state, user_request)
    return ClarificationOutcome(chunks=chunks, next_block_index=next_block_index + 1, done=True)


def _latest_pending_clarification(messages: list[ChatMessage]) -> dict[str, Any] | None:
    for message in reversed(messages[:-1]):
        if message.role != "assistant":
            continue
        for line in reversed(message.content.splitlines()):
            index = line.find(CLARIFICATION_STATE_PREFIX)
            if index < 0:
                continue
            raw = line[index + len(CLARIFICATION_STATE_PREFIX) :].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if payload.get("status") == "waiting":
                return _normalize_pending_clarification(payload)
            return None
    return None


def _normalize_pending_clarification(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        payload["metadata"] = {}

    current_question = payload.get("current_question")
    if isinstance(current_question, dict):
        current = dict(current_question)
    elif any(
        payload.get(key) is not None
        for key in ("question_id", "question", "recommended_answer")
    ):
        current = {
            "id": str(payload.get("question_id") or "question"),
            "question": str(payload.get("question") or ""),
            "recommended_answer": str(payload.get("recommended_answer") or ""),
            "status": "pending",
        }
    else:
        current = None

    questions = payload.get("questions")
    normalized_questions = (
        [dict(question) for question in questions if isinstance(question, dict)]
        if isinstance(questions, list)
        else []
    )

    if current is not None:
        current["id"] = str(current.get("id") or "question")
        current["question"] = str(current.get("question") or "")
        if current.get("status") not in {"pending", "answered", "skipped"}:
            current["status"] = "pending"
        payload["current_question"] = current
        if not normalized_questions:
            normalized_questions = [dict(current)]
    payload["questions"] = normalized_questions
    return payload


def _should_auto_clarify(
    config: Mapping[str, Any],
    user_request: str,
    has_task_intent: Callable[[str], bool],
) -> bool:
    if config.get("tasks") is not None:
        return False
    if _requirement_alignment_mode(config) != "strict":
        return False
    if _is_bypass_request(user_request):
        return False
    task_kind = _alignment_task_kind(user_request)
    if task_kind == "small_talk":
        return False
    if task_kind == "other" and not has_task_intent(user_request):
        return False
    max_questions = _positive_int(config, "auto_clarification_max_questions", 3)
    if max_questions <= 0:
        return False
    return True


def _requirement_alignment_mode(config: Mapping[str, Any]) -> str:
    turn_options = config.get("turn_options")
    if isinstance(turn_options, Mapping):
        mode = turn_options.get("requirement_alignment")
    else:
        mode = None
    return mode if mode in {"off", "strict"} else "off"


def _clarification_agent_id_from_config(config: Mapping[str, Any]) -> str:
    value = config.get("clarification_agent_id")
    return value.strip() if isinstance(value, str) and value.strip() else "orchestrator"


def _clarification_agent_id_from_state(state: Mapping[str, Any]) -> str:
    metadata = state.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get("agent_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = state.get("agent_id")
    return value.strip() if isinstance(value, str) and value.strip() else "orchestrator"


def _requirement_alignment_title(config: Mapping[str, Any], default: str) -> str:
    value = config.get("requirement_alignment_title")
    return value.strip() if isinstance(value, str) and value.strip() else default


async def _requirement_alignment_question(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    user_request: str,
) -> dict[str, Any]:
    task_kind = _alignment_task_kind(user_request)
    if config.get("requirement_alignment_llm_enabled", True) is not False:
        llm_question = await _llm_requirement_alignment_question(
            config,
            messages,
            user_request,
            task_kind=task_kind,
        )
        if llm_question is not None:
            return llm_question
    return _fallback_alignment_question(user_request, task_kind)


async def _llm_requirement_alignment_question(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    user_request: str,
    *,
    task_kind: str,
) -> dict[str, Any] | None:
    backend = (
        config.get("requirement_alignment_model_backend")
        or config.get("qa_model_backend")
        or config.get("planner_model_backend")
        or config.get("model_backend")
        or "deepseek"
    )
    if not isinstance(backend, str) or not backend.strip():
        return None
    try:
        gateway = ModelGateway(
            backend,
            default_config={
                "temperature": 0,
                "max_tokens": 900,
                "request_timeout_seconds": 12,
            },
            agent_id=f"{_clarification_agent_id_from_config(config)}-requirement-alignment",
            system_prompt=(
                "You generate one concise requirement-alignment question before an "
                "agent starts execution or an orchestrator dispatches agents. "
                "Return only JSON with keys: id, question, reason, "
                "recommended_answer, options. The answer must be "
                "Chinese when the user writes Chinese. Do not recommend frontend "
                "static artifacts unless task_kind is frontend_artifact."
            ),
        )
        recent = "\n".join(
            f"{message.role}: {_short_text(message.content, 120)}"
            for message in messages[-6:]
            if message.content.strip()
        )
        prompt = (
            f"task_kind: {task_kind}\n"
            f"user_request: {user_request}\n\n"
            f"recent_context:\n{recent}\n\n"
            "Ask only the single question whose answer would most change execution. "
            "If the request is a debate/discussion, recommend a conversational debate "
            "format and no files. If it is frontend_artifact, recommend concrete "
            "artifact boundaries. Options must be short chips."
        )
        text = ""
        async for chunk in gateway.stream([ChatMessage(role="user", content=prompt)]):
            if chunk.event_type == "error":
                return None
            if chunk.text_delta:
                text += chunk.text_delta
        return _validated_alignment_question(text, task_kind)
    except Exception:  # noqa: BLE001
        return None


def _validated_alignment_question(raw: str, task_kind: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(_json_object_text(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    question = _question_payload(payload)
    if not question["question"] or not question["recommended_answer"]:
        return None
    recommended = question["recommended_answer"].lower()
    frontend_terms = ("静态前端", "index.html", "styles.css", "app.js", "html/css/js")
    if task_kind != "frontend_artifact" and any(term in recommended for term in frontend_terms):
        return None
    question["id"] = str(payload.get("id") or f"{task_kind}_alignment")
    question["options"] = question["options"][:3]
    if not question["options"]:
        question["options"] = ["使用推荐答案", "补充约束", "直接按默认开始"]
    return question


def _json_object_text(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        return stripped[start : end + 1]
    return stripped


def _alignment_task_kind(user_request: str) -> str:
    text = user_request.lower()
    if _contains_any(text, SMALL_TALK_MARKERS) and len(text.strip()) <= 32:
        return "small_talk"
    if _contains_any(text, DISCUSSION_MARKERS):
        return "discussion"
    if any(marker in text for marker in CODE_CHANGE_MARKERS):
        return "code_change"
    if any(marker in text for marker in ARTIFACT_MARKERS) and any(
        marker in text for marker in BUILD_MARKERS
    ):
        return "frontend_artifact"
    if any(marker in text for marker in DOCUMENT_MARKERS):
        return "document"
    if any(marker in text for marker in ANALYSIS_MARKERS):
        return "analysis"
    return "other"


def _fallback_alignment_question(user_request: str, task_kind: str) -> dict[str, Any]:
    short_request = _short_text(user_request, 42)
    if task_kind == "discussion":
        return {
            "id": "discussion_format",
            "question": "你希望这次讨论按什么主持结构进行？",
            "reason": (
                "先确认角色、轮次和总结方式，可以避免 Orchestrator "
                "把对话任务误当成文件产物任务。"
            ),
            "recommended_answer": (
                "按对话式辩论输出，不生成文件；由指定 Agent 分别代表立场，"
                "每方先开场，再进行两轮交锋，最后由 Orchestrator 中立总结。"
            ),
            "options": ["使用对话式辩论", "固定正反方", "自由选择立场"],
        }
    if task_kind == "frontend_artifact":
        return {
            "id": "frontend_delivery_boundary",
            "question": "这个构建请求目前规格偏宽，你希望我按什么交付边界开始？",
            "reason": "先确认产物形态和验收边界，可以避免执行 Agent 过早写出方向不对的文件。",
            "recommended_answer": (
                "按可直接运行的静态前端产物开始：包含入口文件、核心交互、"
                "基础响应式和无明显运行错误。"
            ),
            "options": ["使用推荐默认", "更重视觉", "更重功能"],
        }
    if task_kind == "document":
        return {
            "id": "document_output_shape",
            "question": "你希望文档按什么结构和语气输出？",
            "reason": "文档任务的结构、长度和语气会直接影响后续写作质量。",
            "recommended_answer": (
                "按清晰的标题层级输出：背景、目标、方案、风险、下一步；"
                "语气克制专业，长度以可直接交付为准。"
            ),
            "options": ["使用推荐结构", "更正式", "更口语"],
        }
    if task_kind == "analysis":
        return {
            "id": "analysis_dimensions",
            "question": "你希望这次分析重点比较哪些维度？",
            "reason": "先锁定分析维度和结论形式，可以避免泛泛而谈。",
            "recommended_answer": (
                "按背景、核心差异、优缺点、适用场景和结论建议来分析；"
                "需要比较时用表格辅助，但结论用自然语言说清楚。"
            ),
            "options": ["使用推荐维度", "更重结论", "增加表格"],
        }
    if task_kind == "code_change":
        return {
            "id": "code_change_scope",
            "question": "这次代码修改的范围和验收标准是什么？",
            "reason": "先确认改动边界和测试范围，可以避免 Agent 做无关重构。",
            "recommended_answer": (
                "只修改与当前问题直接相关的代码；保留现有架构风格；"
                "补充针对性测试，并跑受影响模块的检查。"
            ),
            "options": ["使用推荐范围", "只做最小修复", "包含测试补齐"],
        }
    return {
        "id": "execution_assumption",
        "question": "你希望我按什么默认假设推进这个请求？",
        "reason": "这个请求可以执行，但关键边界还不够明确；先确认一条默认假设能减少返工。",
        "recommended_answer": (
            f"围绕“{short_request}”直接给出可执行结果；"
            "不生成额外文件，除非后续明确需要。"
        ),
        "options": ["使用推荐假设", "先给简版", "补充更多细节"],
    }


def _is_bypass_request(text: str) -> bool:
    return not _has_negated_control(text) and _contains_any(text, BYPASS_MARKERS)


def _missing_spec_count(text: str) -> int:
    categories = (
        ("platform", ("web", "html", "react", "网页", "网页版", "页面", "网站", "站点", "静态")),
        ("interaction", ("键盘", "鼠标", "点击", "拖拽", "触屏", "玩法", "交互", "控制")),
        ("visual", ("精致", "视觉", "风格", "配色", "动效", "布局", "美观")),
        (
            "output",
            (
                "index.html",
                "styles.css",
                "app.js",
                "文件",
                "组件",
                "入口",
                "代码",
                "产物",
                "diff",
                "文档",
            ),
        ),
        ("acceptance", ("测试", "验收", "无错误", "响应式", "移动端", "桌面")),
    )
    return sum(1 for _name, markers in categories if not any(marker in text for marker in markers))


def _augmented_messages(
    messages: list[ChatMessage],
    state: dict[str, Any],
    answer: str,
) -> list[ChatMessage]:
    if not messages:
        return messages
    original = _original_request(state)
    if not original or original.lower().startswith(("grill me", "grill with docs")):
        original = messages[-1].content
    recommended = _recommended_answer(state)
    answer_text = _answer_for_planning(state, answer)
    augmented = (
        f"{original}\n\n"
        "Clarification resolved before planning:\n"
        f"- User answer: {answer_text}\n"
        f"- Recommended default: {recommended}\n"
        "- Proceed using these constraints without asking more clarification questions."
    )
    return [*messages[:-1], ChatMessage(role="user", content=augmented)]


def _question_payload(question: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(question.get("id") or "question"),
        "question": str(question.get("question") or ""),
        "reason": str(question.get("reason") or ""),
        "recommended_answer": str(question.get("recommended_answer") or ""),
        "options": [
            str(option)
            for option in question.get("options", [])
            if isinstance(option, str) and option.strip()
        ],
        "status": "pending",
    }


def _answered_question(
    state: dict[str, Any],
    answer: str,
    *,
    status: Literal["answered", "skipped"] = "answered",
) -> dict[str, Any]:
    question = state.get("current_question")
    if not isinstance(question, dict):
        question = {
            "id": state.get("question_id") or "question",
            "question": state.get("question") or "",
            "recommended_answer": state.get("recommended_answer") or "",
            "options": [],
        }
    return {
        "id": str(question.get("id") or state.get("question_id") or "question"),
        "question": str(question.get("question") or state.get("question") or ""),
        "reason": str(question.get("reason") or ""),
        "recommended_answer": str(
            question.get("recommended_answer") or state.get("recommended_answer") or ""
        ),
        "options": [
            str(option)
            for option in question.get("options", [])
            if isinstance(option, str) and option.strip()
        ],
        "status": status,
        "answer": _answer_or_default(state, answer),
    }


def _answered_questions_with_current(
    state: dict[str, Any],
    answer: str,
    *,
    status: Literal["answered", "skipped"] = "answered",
) -> list[dict[str, Any]]:
    question = state.get("current_question")
    current_id = question.get("id") if isinstance(question, dict) else None
    answered: list[dict[str, Any]] = []
    raw_questions = state.get("questions")
    if isinstance(raw_questions, list):
        for raw_question in raw_questions:
            if not isinstance(raw_question, dict):
                continue
            if current_id is not None and raw_question.get("id") == current_id:
                continue
            if raw_question.get("status") in {"answered", "skipped"}:
                answered.append(dict(raw_question))
    answered.append(_answered_question(state, answer, status=status))
    return answered


def _answer_or_default(state: dict[str, Any], answer: str) -> str:
    if _contains_default_answer(answer):
        return _recommended_answer(state)
    return answer.strip() or _recommended_answer(state)


def _answer_for_planning(state: dict[str, Any], answer: str) -> str:
    pending = _metadata(state).get("pending_answer")
    if isinstance(pending, str) and pending.strip() and _should_continue_after_answer(answer):
        return pending.strip()
    return _answer_or_default(state, answer)


def _requirements_brief(state: dict[str, Any], answer: str) -> str:
    return (
        "需求澄清摘要：\n"
        f"- 原始请求：{_original_request(state) or '未提供'}\n"
        f"- 最新回答：{_answer_or_default(state, answer)}\n"
        "- 下一步：如果要进入实现，请发送“开始实现”或“按这个做”。"
    )


def _should_continue_after_answer(answer: str) -> bool:
    if _has_negated_control(answer):
        return False
    return _contains_any(answer, DIRECT_PROCEED_MARKERS) or _contains_any(
        answer, DEFAULT_PROCEED_MARKERS
    )


def _contains_default_answer(answer: str) -> bool:
    return not _has_negated_control(answer) and _contains_any(answer, DEFAULT_MARKERS)


def _is_confirm_setup_write(answer: str) -> bool:
    return not _has_negated_control(answer) and _contains_any(answer, SETUP_CONFIRM_MARKERS)


def _is_confirm_docs_write(answer: str) -> bool:
    return not _has_negated_control(answer) and _contains_any(answer, DOCS_CONFIRM_MARKERS)


def _is_setup_custom_request(answer: str) -> bool:
    return "自定义" in answer or "custom" in answer.lower()


def _docs_answer_for_write(state: dict[str, Any], answer: str) -> str:
    pending = _metadata(state).get("pending_docs_answer")
    if isinstance(pending, str) and pending.strip() and _is_confirm_docs_write(answer):
        return pending.strip()
    return _answer_or_default(state, answer)


def _has_negated_control(text: str) -> bool:
    normalized = text.lower()
    for marker in CLARIFICATION_SKIP_MARKERS:
        normalized = normalized.replace(marker.lower(), "")
    return _contains_any(normalized, NEGATION_MARKERS)


def _is_topic_route_state(state: dict[str, Any]) -> bool:
    question = state.get("current_question")
    return isinstance(question, dict) and question.get("id") == "topic_route"


def _previous_clarification_state(state: dict[str, Any]) -> dict[str, Any] | None:
    previous = _metadata(state).get("previous_clarification_state")
    return dict(previous) if isinstance(previous, dict) else None


def _pending_route_text(state: dict[str, Any]) -> str:
    value = _metadata(state).get("route_pending_user_request")
    return value.strip() if isinstance(value, str) else ""


def _is_continue_current_selection(text: str) -> bool:
    return "继续澄清当前" in text or "继续当前" in text


def _is_switch_selection(text: str) -> bool:
    return "切换到新需求" in text or _is_explicit_switch_request(text)


def _is_reference_selection(text: str) -> bool:
    return "作为当前需求参考" in text or "作为参考" in text


def _is_explicit_switch_request(text: str) -> bool:
    return _contains_any(text, SWITCH_MARKERS)


def _switch_request_text(text: str) -> str:
    cleaned = re.sub(
        r"^\s*(?:切换到新需求[:：]?|先不做[^，。,.\n]*[，。,.\s]*|改(?:做|成)[:：]?)",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or text.strip()


def _looks_like_question_or_task(text: str) -> bool:
    normalized = text.lower()
    if _contains_any(normalized, QUESTION_MARKERS):
        return True
    return any(marker in normalized for marker in BUILD_MARKERS) and any(
        marker in normalized for marker in ARTIFACT_MARKERS
    )


def _looks_like_short_answer(text: str) -> bool:
    stripped = text.strip()
    if _looks_like_question_or_task(stripped):
        return False
    if len(stripped) <= 24 and not _contains_any(stripped, QUESTION_MARKERS):
        return True
    return _contains_any(stripped, ("使用推荐", "完整主流程", "克制精致", "移动端", "桌面端"))


COMMON_REQUEST_TERMS = (
    "please",
    "help",
    "me",
    "a",
    "an",
    "the",
    "build",
    "create",
    "generate",
    "implement",
    "design",
    "make",
    "write",
    "web",
    "website",
    "webpage",
    "page",
    "html",
    "css",
    "javascript",
    "js",
    "frontend",
    "game",
    "file",
    "files",
    "请你",
    "请",
    "帮我",
    "帮",
    "我",
    "设计",
    "制作",
    "开发",
    "做一个",
    "做",
    "生成",
    "创建",
    "写",
    "实现",
    "一个",
    "的",
    "网页版",
    "网页",
    "页面",
    "网站",
    "前端",
    "游戏",
    "文件",
)


def _is_repeated_current_request(state: dict[str, Any], user_request: str) -> bool:
    if not _looks_like_question_or_task(user_request):
        return False
    candidates = [_original_request(state)]
    pending = _metadata(state).get("pending_answer")
    if isinstance(pending, str):
        candidates.append(pending)
    return any(_same_request_intent(user_request, candidate) for candidate in candidates)


def _same_request_intent(left: str, right: str) -> bool:
    left_compact = _compact_request_text(left)
    right_compact = _compact_request_text(right)
    if not left_compact or not right_compact:
        return False
    if left_compact == right_compact:
        return True

    left_signature = _distinctive_request_signature(left_compact)
    right_signature = _distinctive_request_signature(right_compact)
    if left_signature and right_signature:
        if left_signature == right_signature:
            return True
        shorter, longer = sorted((left_signature, right_signature), key=len)
        if len(shorter) >= 3 and shorter in longer:
            return True
        return SequenceMatcher(None, left_signature, right_signature).ratio() >= 0.88

    return SequenceMatcher(None, left_compact, right_compact).ratio() >= 0.95


def _compact_request_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower(), flags=re.UNICODE)


def _distinctive_request_signature(compact_text: str) -> str:
    signature = compact_text
    for term in sorted(COMMON_REQUEST_TERMS, key=len, reverse=True):
        compact_term = _compact_request_text(term)
        if compact_term:
            signature = signature.replace(compact_term, "")
    return signature


def _project_labels(text: str) -> set[str]:
    return {
        match.group(1).lower()
        for match in re.finditer(
            r"(?:项目|project)\s*([a-zA-Z0-9一二三四五六七八九十甲乙丙丁]+)",
            text,
            flags=re.IGNORECASE,
        )
    }


def _short_text(text: str, limit: int = 36) -> str:
    stripped = " ".join(text.strip().split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "..."


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(marker.lower() in normalized for marker in markers)


def _positive_int(config: Mapping[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return default
    return value


def _mode(state: dict[str, Any]) -> ClarificationMode:
    return _safe_mode(str(state.get("mode") or "auto"))


def _safe_mode(value: str) -> ClarificationMode:
    if value in {
        "auto",
        "requirement_alignment",
        "grill_me",
        "grill_with_docs",
        "setup_matt_pocock_skills",
    }:
        return value  # type: ignore[return-value]
    return "auto"


def _metadata(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _original_request(state: dict[str, Any]) -> str:
    value = _metadata(state).get("original_request")
    return value if isinstance(value, str) else ""


def _question_count(state: dict[str, Any]) -> int:
    value = _metadata(state).get("question_count")
    return value if isinstance(value, int) and value > 0 else 1


def _max_questions(state: dict[str, Any]) -> int:
    value = _metadata(state).get("max_questions")
    return value if isinstance(value, int) and value > 0 else 3


def _recommended_answer(state: dict[str, Any]) -> str:
    question = state.get("current_question")
    if isinstance(question, dict) and isinstance(question.get("recommended_answer"), str):
        return str(question["recommended_answer"])
    value = state.get("recommended_answer")
    return value if isinstance(value, str) else ""


def _workspace_docs_summary(workspace_path: Path | None) -> str:
    if workspace_path is None:
        return "暂未连接 workspace"
    names: list[str] = []
    for rel_path in ("CONTEXT.md", "CONTEXT-MAP.md"):
        if (workspace_path / rel_path).is_file():
            names.append(rel_path)
    adr_dir = workspace_path / "docs" / "adr"
    if adr_dir.is_dir():
        count = len([item for item in adr_dir.glob("*.md") if item.is_file()])
        if count:
            names.append(f"docs/adr/*.md x{count}")
    return ", ".join(names) if names else "暂未发现 CONTEXT.md / ADR"


def _append_context_definition(workspace_path: Path | None, answer: str) -> str | None:
    if workspace_path is None:
        return "workspace_path is missing"
    try:
        path = _safe_workspace_path(workspace_path, "CONTEXT.md")
        existing = path.read_text(encoding="utf-8") if path.exists() else "# Context\n"
        entry = (
            "\n\n## Clarified Terms\n\n"
            f"- {answer.strip()}\n"
        )
        if answer.strip() in existing:
            return None
        path.write_text(existing.rstrip() + entry, encoding="utf-8")
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def _write_setup_docs(workspace_path: Path | None, custom_note: str) -> str | None:
    if workspace_path is None:
        return "workspace_path is missing"
    try:
        files = {
            "AGENTS.md": _agents_doc(),
            "docs/agents/issue-tracker.md": _issue_tracker_doc(custom_note),
            "docs/agents/triage-labels.md": _triage_labels_doc(),
            "docs/agents/domain.md": _domain_doc(),
        }
        for rel_path, content in files.items():
            path = _safe_workspace_path(workspace_path, rel_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def _safe_workspace_path(workspace_path: Path, rel_path: str) -> Path:
    root = workspace_path.expanduser().resolve()
    target = (root / rel_path).resolve(strict=False)
    target.relative_to(root)
    return target


def _agents_doc() -> str:
    return """# Workspace Agent Rules

Before writing code for a vague product or build request, ask for the missing
requirement that would most change the implementation. Prefer one question at a
time.

Use `CONTEXT.md` for project language and definitions. Use `docs/adr/` only for
decisions that are hard to reverse, surprising, and based on a real tradeoff.

Do not modify files outside this conversation workspace.
"""


def _issue_tracker_doc(custom_note: str) -> str:
    return f"""# Issue Tracker

Default: use local markdown notes inside this workspace. Do not assume GitHub,
Linear, Jira, or another external tracker unless the user explicitly provides
one.

User setup note:
{custom_note.strip() or "Use the recommended local markdown issue tracker."}
"""


def _triage_labels_doc() -> str:
    return """# Triage Labels

- bug: user-visible incorrect behavior
- enhancement: new capability or workflow improvement
- clarification: requirement needs user input before implementation
- docs: workspace documentation or context change
- blocked: cannot proceed without external state or credentials
"""


def _domain_doc() -> str:
    return """# Domain Documentation

Use a single `CONTEXT.md` at the workspace root for the current conversation's
durable language and project definitions.

Create ADRs in `docs/adr/` only when a decision is hard to reverse, surprising,
and based on a real tradeoff.
"""


async def _record_clarification(
    config: Mapping[str, Any],
    event_type: str,
    state: Mapping[str, Any],
    user_answer: str,
) -> None:
    writer = config.get("orchestrator_memory_writer")
    if writer is None:
        return
    run_context = OrchestratorRunContext()
    try:
        await start_run(
            config,
            run_context,
            user_request=_original_request(dict(state)) or user_answer,
            plan_source=f"clarification:{state.get('mode', 'auto')}",
            tasks=[],
        )
        await record_event(
            config,
            run_context,
            event_type=event_type,
            agent_id="orchestrator",
            payload={
                "state": dict(state),
                "user_answer": user_answer,
            },
        )
        await finish_run(
            config,
            run_context,
            status="done" if event_type != "clarification_cancelled" else "cancelled",
            final_summary=event_type,
        )
    except Exception:  # noqa: BLE001
        return
