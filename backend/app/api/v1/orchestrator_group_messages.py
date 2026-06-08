"""Child message persistence for Orchestrator group-chat streams."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import StreamChunk
from app.api.v1.stream_accumulator import StreamContentAccumulator
from app.models.message import Message

ERROR_TEXT_MAX_CHARS = 1200
GENERIC_CHILD_ERROR_TEXT = (
    "该 Agent 在当前阶段未能完成。Orchestrator 会尝试改派其他可用 Agent；"
    "如果持续失败，可以重试或检查该 Agent 的运行配置。"
)


class OrchestratorGroupMessageWriter:
    """Create and persist per-agent child messages during one Orchestrator run."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        conversation_id: UUID,
        parent_message_id: UUID,
        user_message_id: UUID | None,
        lock: asyncio.Lock | None = None,
    ) -> None:
        self.db = db
        self.conversation_id = conversation_id
        self.parent_message_id = parent_message_id
        self.user_message_id = user_message_id
        self._states: dict[str, _ChildMessageState] = {}
        self._lock = lock or asyncio.Lock()

    async def start_message(
        self,
        *,
        agent_id: str,
    ) -> StreamChunk:
        async with self._lock:
            return await self._start_message_unlocked(agent_id=agent_id)

    async def _start_message_unlocked(self, *, agent_id: str) -> StreamChunk:
        message = Message(
            conversation_id=self.conversation_id,
            role="agent",
            agent_id=agent_id,
            content=[],
            reply_to_id=self.user_message_id,
            status="streaming",
        )
        self.db.add(message)
        await self.db.flush()
        if message.created_at is None:
            message.created_at = datetime.now(UTC)
        message_id = str(message.id)
        self._states[message_id] = _ChildMessageState(
            message_id=message.id,
            agent_id=agent_id,
            accumulator=StreamContentAccumulator(),
        )
        await self.db.commit()
        return StreamChunk(
            event_type="message_start",
            message_id=message_id,
            conversation_id=str(self.conversation_id),
            reply_to_id=str(self.user_message_id) if self.user_message_id else None,
            created_at=message.created_at.isoformat(),
            status="streaming",
            agent_id=agent_id,
        )

    async def feed(self, chunk: StreamChunk) -> StreamChunk | None:
        async with self._lock:
            message_id = chunk.message_id
            if not message_id or message_id == str(self.parent_message_id):
                return None
            if chunk.event_type in {
                "message_start",
                "message_done",
                "message_error",
                "message_interrupted",
            }:
                return None

            state = self._states.get(message_id)
            if state is None:
                return None
            accumulator_error = state.accumulator.feed(chunk)
            if accumulator_error is None:
                return None
            return await self._finish_message_unlocked(
                message_id,
                status="error",
                error=accumulator_error.error or accumulator_error.error_code,
                error_code=accumulator_error.error_code,
            )

    async def finish_message(
        self,
        message_id: str,
        *,
        status: str = "done",
        error: str | None = None,
        error_code: str | None = None,
    ) -> StreamChunk | None:
        async with self._lock:
            return await self._finish_message_unlocked(
                message_id,
                status=status,
                error=error,
                error_code=error_code,
            )

    async def _finish_message_unlocked(
        self,
        message_id: str,
        *,
        status: str = "done",
        error: str | None = None,
        error_code: str | None = None,
    ) -> StreamChunk | None:
        state = self._states.pop(message_id, None)
        if state is None:
            return None

        message = await self.db.get(Message, state.message_id)
        if message is None:
            return None

        if status == "interrupted":
            state.accumulator.finalize_interrupted()
            has_orphaned_tool_call = False
        else:
            has_orphaned_tool_call = state.accumulator.finalize_orphaned_tools()
        content = state.accumulator.to_list()
        if status == "interrupted":
            final_status = "interrupted"
        else:
            final_status = "error" if status == "error" or has_orphaned_tool_call else "done"
        if final_status == "error" and not content:
            content = [
                {
                    "type": "text",
                    "agent_id": state.agent_id,
                    "text": _safe_error_text(error),
                }
            ]
        if final_status == "interrupted" and not content:
            content = [
                {
                    "type": "text",
                    "agent_id": state.agent_id,
                    "text": "已打断本次回复，可以继续补充要求。",
                }
            ]
        message.content = content
        message.status = final_status
        await self.db.commit()

        if final_status == "interrupted":
            return StreamChunk(
                event_type="message_interrupted",
                message_id=message_id,
                conversation_id=str(self.conversation_id),
                reply_to_id=str(self.user_message_id) if self.user_message_id else None,
                status="interrupted",
                agent_id=state.agent_id,
                total_blocks=len(content),
            )
        if final_status == "error":
            return StreamChunk(
                event_type="message_error",
                message_id=message_id,
                conversation_id=str(self.conversation_id),
                reply_to_id=str(self.user_message_id) if self.user_message_id else None,
                status="error",
                agent_id=state.agent_id,
                error_code=error_code or ("tool_call_orphan" if has_orphaned_tool_call else None),
                error=_safe_error_text(error),
            )
        return StreamChunk(
            event_type="message_done",
            message_id=message_id,
            conversation_id=str(self.conversation_id),
            reply_to_id=str(self.user_message_id) if self.user_message_id else None,
            status="done",
            agent_id=state.agent_id,
            total_blocks=len(content),
        )

    async def fail_open_messages(self, error: str) -> list[StreamChunk]:
        async with self._lock:
            chunks: list[StreamChunk] = []
            for message_id in list(self._states):
                chunk = await self._finish_message_unlocked(
                    message_id,
                    status="error",
                    error=error,
                )
                if chunk is not None:
                    chunks.append(chunk)
            return chunks

    async def interrupt_open_messages(self) -> list[StreamChunk]:
        async with self._lock:
            chunks: list[StreamChunk] = []
            for message_id in list(self._states):
                chunk = await self._finish_message_unlocked(
                    message_id,
                    status="interrupted",
                )
                if chunk is not None:
                    chunks.append(chunk)
            return chunks


class _ChildMessageState:
    def __init__(
        self,
        *,
        message_id: UUID,
        agent_id: str,
        accumulator: StreamContentAccumulator,
    ) -> None:
        self.message_id = message_id
        self.agent_id = agent_id
        self.accumulator = accumulator


def _safe_error_text(text: str | None) -> str:
    raw = " ".join(str(text or "").replace("\x00", "").split())
    if not raw:
        return GENERIC_CHILD_ERROR_TEXT
    lowered = raw.lower()
    if any(
        marker in lowered
        for marker in (
            "permission denied",
            "[errno",
            ".claude.json",
            "/root/.agenthub",
            "not authenticated",
            "unauthorized",
            "credential",
            "api key",
            "auth",
        )
    ):
        cleaned = (
            "该 Agent 在当前阶段未能完成。运行时认证或权限配置需要检查。"
            "Orchestrator 会尝试改派其他可用 Agent；如果持续失败，可以重试。"
        )
    elif any(marker in lowered for marker in ("quota", "rate limit", "too many requests")):
        cleaned = (
            "该 Agent 在当前阶段未能完成。当前运行额度或速率限制需要注意。"
            "Orchestrator 会尝试改派其他可用 Agent；如果持续失败，可以稍后重试。"
        )
    elif any(marker in lowered for marker in ("timeout", "timed out", "idle timeout")):
        cleaned = (
            "该 Agent 在当前阶段未能完成。执行超时，可能需要缩小任务或稍后重试。"
            "Orchestrator 会尝试改派其他可用 Agent。"
        )
    elif "output_incomplete" in lowered:
        reason = re.sub(
            r"\boutput_incomplete\s*:\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()
        if reason:
            cleaned = (
                f"该 Agent 的输出没有满足本阶段要求：{reason}"
                "Orchestrator 会尝试纠偏或改派其他可用 Agent。"
            )
        else:
            cleaned = (
                "该 Agent 的输出没有满足本阶段要求。"
                "Orchestrator 会尝试纠偏或改派其他可用 Agent。"
            )
    elif _looks_like_raw_runtime_error(raw, lowered):
        cleaned = (
            "该 Agent 在当前阶段未能完成。外部运行时返回异常，"
            "Orchestrator 会尝试改派其他可用 Agent；如果持续失败，"
            "请检查该 Agent 的运行配置。"
        )
    elif "no html entry file" in lowered:
        cleaned = "该 Agent 未生成可预览的 HTML 入口文件，Orchestrator 会尝试补齐或改派。"
    else:
        cleaned = raw
    cleaned = _strip_internal_error_terms(cleaned)
    if not cleaned:
        cleaned = GENERIC_CHILD_ERROR_TEXT
    if len(cleaned) > ERROR_TEXT_MAX_CHARS:
        return f"{cleaned[:ERROR_TEXT_MAX_CHARS]}..."
    return cleaned


def _looks_like_raw_runtime_error(raw: str, lowered: str) -> bool:
    raw_markers = (
        "/workspaces/",
        "OpenAI Codex",
        "Codex CLI exited",
        "Reading additional input from stdin",
    )
    lowered_markers = (
        "workdir:",
        "approval:",
        "sandbox:",
        "unknownerror",
        "external_runtime_error",
        "runtime_idle_timeout",
        "cli exited",
        "{'name':",
        '"name":',
        "provider_error",
    )
    return any(marker in raw for marker in raw_markers) or any(
        marker in lowered for marker in lowered_markers
    )


def _strip_internal_error_terms(text: str) -> str:
    cleaned = re.sub(r"\bcall[_-][A-Za-z0-9_.-]+", "调用记录", text)
    cleaned = re.sub(r"/workspaces/\S+", "workspace 路径", cleaned)
    cleaned = re.sub(r"/root/\.agenthub/\S+", "本地认证配置", cleaned)
    cleaned = cleaned.replace(".claude.json", "认证配置")
    cleaned = re.sub(r"OpenAI Codex[^\n。；;]*", "外部 Agent 运行时", cleaned)
    cleaned = re.sub(r"\bworkdir:\s*\S+", "workspace 路径", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bapproval:\s*\S+", "运行审批配置", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bsandbox:\s*\S+", "运行沙箱配置", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bexternal_runtime_error\b", "外部运行异常", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bUnknownError\b", "运行异常", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[Errno\s+\d+\]", "系统错误", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Permission denied", "权限配置异常", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Traceback.*", "运行过程异常。", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bstderr\b", "错误输出", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())
