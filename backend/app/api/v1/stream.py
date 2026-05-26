"""SSE stream endpoint — Owner: B1.

This is the ★ critical integration point ★ between B1 (routing/persistence) and
B2 (Agent layer). B1 calls `agents.registry.get_adapter()` and pipes the
resulting AsyncIterator[StreamChunk] into SSE events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
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
from app.services.workspace_service import WorkspaceService

router = APIRouter()

TOOL_PREVIEW_MAX_CHARS = 2048


class _ContentAccumulator:
    """Accumulates streaming chunks into final ContentBlock list for DB persistence."""

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.pending_tool_calls: dict[str, dict[str, Any]] = {}
        self.has_orphaned_tool_call = False

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

    def feed(self, chunk: StreamChunk) -> StreamChunk | None:
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
        elif chunk.event_type == "tool_call":
            return self._feed_tool_call(chunk)
        elif chunk.event_type == "tool_result":
            return self._feed_tool_result(chunk)
        return None

    def _feed_tool_call(self, chunk: StreamChunk) -> StreamChunk | None:
        self._finalize_current()
        if not chunk.call_id or not chunk.tool_name:
            return _tool_call_orphan_error("tool_call missing call_id or tool_name")
        if chunk.call_id in self.pending_tool_calls:
            return _tool_call_orphan_error(f"duplicate tool_call: {chunk.call_id}")

        block = {
            "type": "tool_call",
            "call_id": chunk.call_id,
            "tool_name": chunk.tool_name,
            "arguments": _preview_jsonish(chunk.tool_arguments or {}),
            "status": "pending",
        }
        self.blocks.append(block)
        self.pending_tool_calls[chunk.call_id] = block
        return None

    def _feed_tool_result(self, chunk: StreamChunk) -> StreamChunk | None:
        self._finalize_current()
        if not chunk.call_id or chunk.call_id not in self.pending_tool_calls:
            return _tool_call_orphan_error(
                f"tool_result without matching tool_call: {chunk.call_id or '<missing>'}"
            )

        block = self.pending_tool_calls.pop(chunk.call_id)
        status = chunk.tool_status or "ok"
        block["status"] = status
        if chunk.tool_output is not None:
            output_preview, output_truncated = _preview_text(
                chunk.tool_output,
                already_truncated=bool(chunk.tool_output_truncated),
            )
            block["output_preview"] = output_preview
            block["output_truncated"] = output_truncated
        elif chunk.tool_output_truncated is not None:
            block["output_truncated"] = chunk.tool_output_truncated
        if status == "error":
            block["error_code"] = chunk.error_code or "tool_call_failed"
        return None

    def finalize_orphaned_tools(self) -> bool:
        self._finalize_current()
        if not self.pending_tool_calls:
            return False
        for block in self.pending_tool_calls.values():
            block["status"] = "error"
            block["error_code"] = "tool_call_orphan"
        self.pending_tool_calls.clear()
        self.has_orphaned_tool_call = True
        return True

    def to_list(self) -> list[dict[str, Any]]:
        self._finalize_current()
        return self.blocks


def _preview_text(
    value: str,
    *,
    already_truncated: bool = False,
) -> tuple[str, bool]:
    if len(value) <= TOOL_PREVIEW_MAX_CHARS:
        return value, already_truncated
    return value[:TOOL_PREVIEW_MAX_CHARS], True


def _preview_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        preview, truncated = _preview_text(value)
        if truncated:
            return f"{preview}...[truncated]"
        return preview
    if isinstance(value, dict):
        return {str(key): _preview_jsonish(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_preview_jsonish(item) for item in value]
    return value


def _tool_call_orphan_error(message: str) -> StreamChunk:
    return StreamChunk(event_type="error", error_code="tool_call_orphan", error=message)


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
        workspace = await WorkspaceService().get_or_create(db, message.conversation_id)

        # Mark streaming
        message.status = "streaming"
        await db.commit()

        disconnected = False
        async for chunk in adapter.stream(
            history,
            workspace_path=Path(workspace.root_path),
            tool_specs=None,
        ):
            if await request.is_disconnected():
                disconnected = True
                break
            accumulator_error = accumulator.feed(chunk)
            if accumulator_error is not None:
                message.content = accumulator.to_list()
                message.status = "error"
                await db.commit()
                yield accumulator_error.to_sse()
                return
            yield chunk.to_sse()
            if chunk.event_type == "error":
                message.content = accumulator.to_list()
                message.status = "error"
                await db.commit()
                return

        # Persist
        has_orphaned_tool_call = accumulator.finalize_orphaned_tools()
        message.content = accumulator.to_list()
        message.status = "error" if disconnected or has_orphaned_tool_call else "done"
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
