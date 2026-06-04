"""Platform preview autostart helpers for SSE streams."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import ChatMessage, StreamChunk
from app.models.message import Message
from app.services.context.compression import blocks_to_text
from app.services.workspace_preview import (
    WorkspacePreviewDisabledError,
    WorkspacePreviewService,
    WorkspacePreviewStartError,
)
from app.services.workspace_service import (
    WorkspaceFileNotFound,
    WorkspaceFileTooLarge,
    WorkspaceViolation,
)

DEPLOY_INTENT_RE = re.compile(
    r"(?i)(部署|发布|上线|端口|preview\s+(?:on|at|to)|deploy(?:ed|ment)?|port\s*\d{2,5})"
)
REQUESTED_PORT_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")
SKIP_DIR_NAMES = {".agenthub", ".git", ".venv", "__pycache__", "node_modules"}


async def maybe_autostart_platform_preview(
    *,
    db: AsyncSession,
    message: Message,
    history: list[ChatMessage],
    workspace_path: Path,
    block_index: int,
    existing_blocks: list[dict[str, Any]] | None = None,
) -> tuple[list[StreamChunk], int]:
    """Start a platform-managed preview when the user explicitly asked for one."""

    user_request = await _latest_user_request(db, message, history)
    if not _wants_platform_preview(user_request):
        return [], block_index
    if _has_platform_preview_tool_call(existing_blocks):
        return [], block_index

    entry_path = _find_preview_entry(workspace_path)
    call_id = f"platform-preview-{message.id}"
    requested_port = _requested_port(user_request)
    arguments: dict[str, Any] = {"mode": "static"}
    if entry_path is not None:
        arguments["entry_path"] = entry_path
    if requested_port is not None:
        arguments["requested_port"] = requested_port

    chunks = [
        StreamChunk(
            event_type="tool_call",
            agent_id=message.agent_id,
            call_id=call_id,
            tool_name="start_workspace_preview",
            tool_arguments=arguments,
        )
    ]
    if entry_path is None:
        output = _json_output(
            {
                "status": "error",
                "error": "no HTML entry file was found in the workspace",
            }
        )
        chunks.append(
            StreamChunk(
                event_type="tool_result",
                agent_id=message.agent_id,
                call_id=call_id,
                tool_status="error",
                tool_output=output,
                metadata={"error_code": "preview_entry_not_found"},
            )
        )
        chunks.extend(
            _text_block(
                block_index,
                "Platform preview was requested, but no HTML entry file was found.\n",
            )
        )
        return chunks, block_index + 1

    try:
        session = await WorkspacePreviewService().start(
            db,
            message.conversation_id,
            entry_path=entry_path,
            requested_port=requested_port,
        )
    except (
        WorkspacePreviewDisabledError,
        WorkspacePreviewStartError,
        WorkspaceViolation,
        WorkspaceFileNotFound,
        WorkspaceFileTooLarge,
    ) as exc:
        output = _json_output(
            {
                "status": "error",
                "entry_path": entry_path,
                "error": str(exc),
            }
        )
        chunks.append(
            StreamChunk(
                event_type="tool_result",
                agent_id=message.agent_id,
                call_id=call_id,
                tool_status="error",
                tool_output=output,
                metadata={"error_code": _preview_error_code(exc)},
            )
        )
        chunks.extend(
            _text_block(
                block_index,
                f"Platform preview failed for `{entry_path}`: {exc}\n",
            )
        )
        return chunks, block_index + 1

    output = _json_output(
        {
            "status": session.status,
            "mode": WorkspacePreviewService.mode,
            "entry_path": session.entry_path,
            "port": session.port,
            "url": session.url,
        }
    )
    chunks.append(
        StreamChunk(
            event_type="tool_result",
            agent_id=message.agent_id,
            call_id=call_id,
            tool_status="ok",
            tool_output=output,
        )
    )
    chunks.extend(
        _text_block(
            block_index,
            f"Platform preview deployed: {session.url}\n",
        )
    )
    block_index += 1
    chunks.append(
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="web_preview",
            metadata={
                "url": session.url,
                "title": f"Workspace preview: {session.entry_path}",
                "description": "AgentHub platform-managed static preview.",
            },
        )
    )
    chunks.append(StreamChunk(event_type="block_end", block_index=block_index))
    return chunks, block_index + 1


async def _latest_user_request(
    db: AsyncSession,
    message: Message,
    history: list[ChatMessage],
) -> str:
    if message.reply_to_id is not None:
        user_message = await db.get(Message, message.reply_to_id)
        if user_message is not None:
            text = blocks_to_text(user_message.content).strip()
            if text:
                return text
    for item in reversed(history):
        if item.role == "user" and item.content.strip():
            return item.content.strip()
    return ""


def _wants_platform_preview(text: str) -> bool:
    return bool(text and DEPLOY_INTENT_RE.search(text))


def _has_platform_preview_tool_call(blocks: list[dict[str, Any]] | None) -> bool:
    if not blocks:
        return False
    return any(
        block.get("type") == "tool_call"
        and block.get("tool_name") == "start_workspace_preview"
        for block in blocks
    )


def _requested_port(text: str) -> int | None:
    match = REQUESTED_PORT_RE.search(text)
    if match is None:
        return None
    port = int(match.group(1))
    if 1 <= port <= 65535:
        return port
    return None


def _find_preview_entry(workspace_path: Path) -> str | None:
    root = workspace_path.resolve()
    direct_index = root / "index.html"
    if direct_index.is_file():
        return "index.html"

    candidates: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".htm"}:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if _is_skipped(relative):
            continue
        candidates.append(relative)

    index_candidates = [path for path in candidates if path.name.lower() == "index.html"]
    if len(index_candidates) == 1:
        return index_candidates[0].as_posix()
    if candidates:
        return candidates[0].as_posix()
    return None


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES or part.startswith(".env") for part in path.parts)


def _text_block(block_index: int, text: str) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="block_start", block_index=block_index, block_type="text"),
        StreamChunk(event_type="delta", block_index=block_index, text_delta=text),
        StreamChunk(event_type="block_end", block_index=block_index),
    ]


def _json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _preview_error_code(exc: Exception) -> str:
    if isinstance(exc, WorkspacePreviewDisabledError):
        return "workspace_preview_disabled"
    if isinstance(exc, WorkspacePreviewStartError):
        return "workspace_preview_start_failed"
    if isinstance(exc, WorkspaceFileNotFound):
        return "preview_entry_not_found"
    if isinstance(exc, WorkspaceFileTooLarge):
        return "preview_entry_too_large"
    return "workspace_violation"
