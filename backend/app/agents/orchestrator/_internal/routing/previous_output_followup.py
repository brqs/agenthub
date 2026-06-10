"""Resolve terse requests that modify the previous Orchestrator output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.availability import runnable_agent_ids
from app.agents.types import ChatMessage, StreamChunk
from app.models.message import Message
from app.services.context.compression import blocks_to_text, truncate_text
from app.services.orchestrator_memory import (
    get_orchestrator_run_detail,
    list_orchestrator_runs,
)

PREVIOUS_OUTPUT_FOLLOWUP_HEADER = "Previous output follow-up context:"
MAX_FOLLOWUP_CONTEXT_CHARS = 12_000
MAX_ARTIFACT_CHARS = 8_000
TEXT_ARTIFACT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".htm",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".markdown",
    ".py",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
FOLLOWUP_MARKERS = (
    "改一下",
    "改改",
    "修改",
    "润色",
    "优化",
    "完善",
    "继续",
    "接着",
    "换个风格",
    "更厉害",
    "厉害一点",
    "再狠一点",
    "再强一点",
    "加强",
    "基于刚刚",
    "刚刚那个",
    "上一版",
    "上一个",
    "revise",
    "rewrite",
    "improve",
    "continue",
    "make it more",
)
EXPLICIT_REFERENCE_MARKERS = (
    "刚刚",
    "之前",
    "上一",
    "那个",
    "这版",
    "这个",
    "继续",
    "接着",
    "再",
)
PRIMARY_TASK_TYPES = {"implementation", "conversation", "dialogue_turn"}
TERMINAL_RUN_STATUSES = {"done", "partial", "completed", "success", "succeeded"}
SUCCESS_TASK_STATES = {"done", "completed", "success", "succeeded"}
CLARIFICATION_STATE_PREFIX = "[Clarification state] "


@dataclass(slots=True)
class PreviousOutputFollowupOutcome:
    messages: list[ChatMessage] | None = None
    chunks: tuple[StreamChunk, ...] = ()
    next_block_index: int = 0
    done: bool = False


@dataclass(slots=True)
class _FollowupCandidate:
    title: str
    agent_id: str
    task_type: str
    artifacts: list[str]
    source_text: str
    summary: str


async def resolve_previous_output_followup(
    config: Mapping[str, Any],
    messages: list[ChatMessage],
    next_block_index: int,
    workspace_path: Path | None,
) -> PreviousOutputFollowupOutcome | None:
    request = _latest_user_request(messages)
    pending_selection = _pending_followup_selection(messages)
    if pending_selection is None and not _looks_like_followup(request):
        return None
    db = config.get("orchestrator_db_session")
    conversation_id = _conversation_uuid(config.get("conversation_id"))
    if not isinstance(db, AsyncSession) or conversation_id is None:
        return None

    candidates = await _load_candidates(
        db,
        conversation_id,
        workspace_path=workspace_path,
    )
    if not candidates:
        return _clarification_outcome(
            next_block_index,
            question="我没有在当前会话找到可继续修改的上一轮正文或文本文件。你想修改哪一项？",
            reason="省略型修改只会关联当前会话，避免误改其他会话的内容。",
            options=["补充要修改的内容", "重新描述完整需求", "取消"],
        )
    if len(candidates) > 1:
        if pending_selection is not None:
            selected = _select_candidate(candidates, request)
            if selected is not None:
                candidates = [selected]
            else:
                return _clarification_outcome(
                    next_block_index,
                    question="我还不能确定你选择的是哪一个结果，请点选或输入完整任务标题。",
                    reason="修改对象必须明确，系统不会静默猜测。",
                    options=[candidate.title[:48] for candidate in candidates[:3]],
                    mode="previous_output_followup",
                    original_request=str(
                        pending_selection.get("original_request") or request
                    ),
                    candidate_titles=[candidate.title for candidate in candidates],
                )
        else:
            options = [candidate.title[:48] for candidate in candidates[:3]]
            return _clarification_outcome(
                next_block_index,
                question="当前会话最近一次执行有多个可修改结果，你指的是哪一个？",
                reason="先确认修改对象，避免把风格要求应用到错误的产物。",
                options=options,
                mode="previous_output_followup",
                original_request=request,
                candidate_titles=[candidate.title for candidate in candidates],
            )

    candidate = candidates[0]
    effective_request = (
        str(pending_selection.get("original_request") or request)
        if pending_selection is not None
        else request
    )
    preferred_agent = (
        candidate.agent_id
        if candidate.agent_id in runnable_agent_ids(config.get("available_agents"))
        else ""
    )
    context = _followup_context(candidate, effective_request, preferred_agent)
    expanded = _expanded_request(candidate, effective_request, preferred_agent)
    return PreviousOutputFollowupOutcome(
        messages=_inject_context_and_replace_request(messages, context, expanded),
        next_block_index=next_block_index,
    )


def _looks_like_followup(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized or len(normalized) > 160:
        return False
    if not any(marker in normalized for marker in FOLLOWUP_MARKERS):
        return False
    return len(normalized) <= 48 or any(
        marker in normalized for marker in EXPLICIT_REFERENCE_MARKERS
    )


async def _load_candidates(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    workspace_path: Path | None,
) -> list[_FollowupCandidate]:
    runs = await list_orchestrator_runs(db, conversation_id, limit=5)
    for run in runs:
        if str(run.status).lower() not in TERMINAL_RUN_STATUSES:
            continue
        detail = await get_orchestrator_run_detail(db, conversation_id, run.id)
        if detail is None:
            continue
        _, tasks, attempts, _ = detail
        attempts_by_task: dict[UUID, list[Any]] = {}
        for attempt in attempts:
            attempts_by_task.setdefault(attempt.task_row_id, []).append(attempt)
        candidates: list[_FollowupCandidate] = []
        for task in tasks:
            if task.task_type not in PRIMARY_TASK_TYPES:
                continue
            if str(task.final_state).lower() not in SUCCESS_TASK_STATES:
                continue
            task_attempts = sorted(
                attempts_by_task.get(task.id, []),
                key=lambda item: item.attempt_index,
            )
            final_attempt = task_attempts[-1] if task_attempts else None
            artifacts = list(final_attempt.artifact_paths) if final_attempt else []
            source_text = _read_artifacts(workspace_path, artifacts)
            if not source_text and final_attempt is not None:
                source_text = str(final_attempt.text_preview or "").strip()
            agent_id = (
                str(final_attempt.agent_id)
                if final_attempt is not None
                else str(task.agent_id)
            )
            if not source_text and run.user_message_id is not None:
                source_text = await _child_agent_text(
                    db,
                    conversation_id,
                    run.user_message_id,
                    agent_id,
                )
            if not source_text:
                source_text = "\n".join(
                    item
                    for item in (task.title, run.user_request, run.final_summary)
                    if item
                )
            if source_text.strip():
                candidates.append(
                    _FollowupCandidate(
                        title=task.title,
                        agent_id=agent_id,
                        task_type=task.task_type,
                        artifacts=artifacts,
                        source_text=truncate_text(source_text, MAX_ARTIFACT_CHARS),
                        summary=truncate_text(run.final_summary or "", 800),
                    )
                )
        if candidates:
            return candidates
    return []


def _read_artifacts(workspace_path: Path | None, paths: list[str]) -> str:
    if workspace_path is None:
        return ""
    try:
        root = workspace_path.resolve()
    except OSError:
        return ""
    parts: list[str] = []
    remaining = MAX_ARTIFACT_CHARS
    for raw_path in paths[:8]:
        if remaining <= 0:
            break
        candidate = (root / raw_path).resolve()
        if root != candidate and root not in candidate.parents:
            continue
        if candidate.suffix.lower() not in TEXT_ARTIFACT_SUFFIXES or not candidate.is_file():
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = content[:remaining]
        parts.append(f"Artifact {raw_path}:\n{excerpt}")
        remaining -= len(excerpt)
    return "\n\n".join(parts)


async def _child_agent_text(
    db: AsyncSession,
    conversation_id: UUID,
    user_message_id: UUID,
    agent_id: str,
) -> str:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.reply_to_id == user_message_id)
        .where(Message.role == "agent")
        .where(Message.agent_id == agent_id)
        .where(Message.status == "done")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    message = result.scalar_one_or_none()
    return blocks_to_text(message.content).strip() if message is not None else ""


def _followup_context(
    candidate: _FollowupCandidate,
    request: str,
    preferred_agent: str,
) -> str:
    lines = [
        PREVIOUS_OUTPUT_FOLLOWUP_HEADER,
        f"Task: {candidate.title}",
        f"Task type: {candidate.task_type}",
        f"Previous agent: {candidate.agent_id}",
        f"Preferred agent for continuity: {preferred_agent or 'none'}",
        f"Artifacts: {', '.join(candidate.artifacts[:8]) or 'none'}",
        "Acceptance state: succeeded",
        f"Current follow-up request: {request}",
    ]
    if candidate.summary:
        lines.append(f"Previous summary: {candidate.summary}")
    lines.append(f"Previous output:\n{candidate.source_text}")
    return truncate_text("\n".join(lines), MAX_FOLLOWUP_CONTEXT_CHARS)


def _expanded_request(
    candidate: _FollowupCandidate,
    request: str,
    preferred_agent: str,
) -> str:
    preference = (
        f" 优先继续使用 @{preferred_agent}，但仅当其仍属于当前会话且可运行。"
        if preferred_agent
        else ""
    )
    return (
        f"修改上一轮任务“{candidate.title}”的输出。用户本轮要求：{request}。"
        f"保留上一轮主题、事实约束和已通过的验收条件，只调整用户点名的部分。{preference}"
    )


def _inject_context_and_replace_request(
    messages: list[ChatMessage],
    context: str,
    expanded_request: str,
) -> list[ChatMessage]:
    updated = list(messages)
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].role == "user":
            updated[index] = ChatMessage(role="user", content=expanded_request)
            updated.insert(index, ChatMessage(role="system", content=context))
            return updated
    return [*updated, ChatMessage(role="system", content=context)]


def _clarification_outcome(
    block_index: int,
    *,
    question: str,
    reason: str,
    options: list[str],
    mode: str = "auto",
    original_request: str = "",
    candidate_titles: list[str] | None = None,
) -> PreviousOutputFollowupOutcome:
    question_payload = {
        "id": "previous_output_target",
        "question": question,
        "reason": reason,
        "recommended_answer": options[0] if options else "",
        "options": options,
        "status": "pending",
    }
    metadata = {
        "source": "previous_output_followup",
        "requires_explicit_selection": True,
        "original_request": original_request,
        "candidate_titles": candidate_titles or [],
    }
    return PreviousOutputFollowupOutcome(
        chunks=(
            StreamChunk(
                event_type="block_start",
                block_index=block_index,
                block_type="clarification",
                metadata={
                    "mode": mode,
                    "title": "确认上一轮修改对象",
                    "status": "waiting",
                    "current_question": question_payload,
                    "questions": [question_payload],
                    "metadata": metadata,
                },
            ),
            StreamChunk(event_type="block_end", block_index=block_index),
        ),
        next_block_index=block_index + 1,
        done=True,
    )


def _latest_user_request(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()
    return ""


def _conversation_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _pending_followup_selection(messages: list[ChatMessage]) -> dict[str, Any] | None:
    for message in reversed(messages[:-1]):
        if message.role != "assistant":
            continue
        for line in reversed(message.content.splitlines()):
            index = line.find(CLARIFICATION_STATE_PREFIX)
            if index < 0:
                continue
            try:
                payload = json.loads(
                    line[index + len(CLARIFICATION_STATE_PREFIX) :].strip()
                )
            except json.JSONDecodeError:
                continue
            if (
                payload.get("status") == "waiting"
                and payload.get("mode") == "previous_output_followup"
            ):
                metadata = payload.get("metadata")
                return metadata if isinstance(metadata, dict) else {}
            return None
    return None


def _select_candidate(
    candidates: list[_FollowupCandidate],
    selection: str,
) -> _FollowupCandidate | None:
    normalized = " ".join(selection.lower().split())
    matches = [
        candidate
        for candidate in candidates
        if normalized == " ".join(candidate.title.lower().split())
        or normalized in candidate.title.lower()
        or candidate.title.lower() in normalized
    ]
    return matches[0] if len(matches) == 1 else None
