"""SSE stream endpoint — Owner: B1.

This is the ★ critical integration point ★ between B1 (routing/persistence) and
B2 (Agent layer). B1 calls `agents.registry.get_adapter()` and pipes the
resulting AsyncIterator[StreamChunk] into SSE events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.registry import AgentNotFoundError, get_adapter
from app.agents.types import StreamChunk
from app.api.v1.conversations import _get_owned_conversation
from app.core.deps import DbSession, get_current_user
from app.models.message import Message
from app.models.user import User
from app.services.context_builder import build_context

router = APIRouter()


class _ContentAccumulator:
    """Accumulates streaming chunks into final ContentBlock list for DB persistence."""

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None

    @staticmethod
    def _parse_diff(raw: str) -> tuple[str, str, str]:
        """Extract (filename, before, after) from unified diff text."""
        lines = raw.splitlines(keepends=True)
        filename = "changes.diff"
        before_lines: list[str] = []
        after_lines: list[str] = []

        for line in lines:
            stripped = line.rstrip("\n")
            if stripped.startswith("+++ b/"):
                filename = stripped[6:]
            elif stripped.startswith("diff --git "):
                parts = stripped.split()
                if len(parts) >= 4 and parts[2].startswith("a/") and parts[3].startswith("b/"):
                    filename = parts[3][2:]

            if stripped.startswith("diff --git") or stripped.startswith("index "):
                continue
            if stripped.startswith("---") or stripped.startswith("+++"):
                continue
            if stripped.startswith("@@"):
                continue

            if stripped.startswith("-"):
                before_lines.append(stripped[1:])
            elif stripped.startswith("+"):
                after_lines.append(stripped[1:])
            else:
                before_lines.append(stripped)
                after_lines.append(stripped)

        return filename, "\n".join(before_lines), "\n".join(after_lines)

    def _finalize_current(self) -> None:
        """Convert the current accumulating block into a persistable dict."""
        if self.current is None:
            return
        if self.current.get("type") == "diff":
            raw_diff = self.current.get("diff", "")
            try:
                filename, before, after = self._parse_diff(raw_diff)
            except Exception:  # noqa: BLE001
                filename = self.current.get("filename", "changes.diff")
                before = raw_diff
                after = ""
            self.current = {
                "type": "diff",
                "filename": filename,
                "before": before,
                "after": after,
            }
        self.blocks.append(self.current)
        self.current = None

    def feed(self, chunk: StreamChunk) -> None:
        if chunk.event_type == "block_start":
            self.current = {"type": chunk.block_type or "text"}
            if chunk.block_type == "text":
                self.current["text"] = ""
            elif chunk.block_type == "code":
                self.current["code"] = ""
                self.current["language"] = (chunk.metadata or {}).get("language", "text")
            elif chunk.block_type == "diff":
                self.current["diff"] = ""
                self.current["filename"] = (chunk.metadata or {}).get("filename", "changes.diff")
            elif chunk.block_type == "web_preview":
                meta = chunk.metadata or {}
                self.current["url"] = meta.get("url", "")
                if "title" in meta:
                    self.current["title"] = meta["title"]
                if "description" in meta:
                    self.current["description"] = meta["description"]
                if "thumbnail_url" in meta:
                    self.current["thumbnail_url"] = meta["thumbnail_url"]
        elif chunk.event_type == "delta" and self.current is not None:
            if chunk.text_delta:
                if self.current.get("type") == "diff":
                    self.current["diff"] = self.current.get("diff", "") + chunk.text_delta
                else:
                    self.current["text"] = self.current.get("text", "") + chunk.text_delta
            if chunk.code_delta:
                self.current["code"] = self.current.get("code", "") + chunk.code_delta
        elif chunk.event_type == "block_end" and self.current is not None:
            self._finalize_current()

    def to_list(self) -> list[dict[str, Any]]:
        self._finalize_current()
        return self.blocks


async def _event_generator(
    db: AsyncSession,
    request: Request,
    message: Message,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-formatted events for a pending agent message."""
    accumulator = _ContentAccumulator()
    try:
        if not message.agent_id:
            message.status = "error"
            await db.commit()
            yield StreamChunk(
                event_type="error",
                error_code="missing_agent",
                error="Message has no agent_id",
            ).to_sse()
            return

        adapter = await get_adapter(message.agent_id, db)
        history = await build_context(db, message.conversation_id)

        # Mark streaming
        message.status = "streaming"
        await db.commit()

        disconnected = False
        async for chunk in adapter.stream(history):
            if await request.is_disconnected():
                disconnected = True
                break
            accumulator.feed(chunk)
            yield chunk.to_sse()
            if chunk.event_type == "error":
                message.content = accumulator.to_list()
                message.status = "error"
                await db.commit()
                return

        # Persist
        message.content = accumulator.to_list()
        message.status = "error" if disconnected else "done"
        await db.commit()
    except AgentNotFoundError as e:
        message.status = "error"
        await db.commit()
        yield StreamChunk(
            event_type="error", error_code="agent_not_found", error=str(e)
        ).to_sse()
    except Exception as e:  # noqa: BLE001
        message.content = accumulator.to_list()
        message.status = "error"
        await db.commit()
        yield StreamChunk(
            event_type="error", error_code="internal_error", error=str(e)
        ).to_sse()


@router.get("/messages/{msg_id}/stream")
async def stream_message(
    msg_id: UUID,
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> EventSourceResponse:
    """SSE stream for an agent message."""
    message = await db.get(Message, msg_id)
    if not message:
        raise HTTPException(
            404,
            detail={"error": {"code": "MESSAGE_NOT_FOUND", "message": "Not found"}},
        )

    # Ownership check via parent conversation
    await _get_owned_conversation(db, user.id, message.conversation_id)

    if message.role != "agent":
        raise HTTPException(
            400,
            detail={
                "error": {
                    "code": "NOT_AGENT_MESSAGE",
                    "message": "Only agent messages can be streamed",
                }
            },
        )

    return EventSourceResponse(_event_generator(db, request, message))
