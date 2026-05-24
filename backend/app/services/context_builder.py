"""
ContextBuilder — assembles conversation history into Adapter input.

TODO(B1):
  - Implement sliding window with token estimation.
  - Always include pinned messages.
  - Compress old context (later).

Reference: docs/tech-architecture.md § 4.4
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import ChatMessage
from app.models.message import Message


def _blocks_to_text(blocks: list[dict[str, Any]]) -> str:
    """Flatten ContentBlocks to plain text for LLM consumption."""
    parts: list[str] = []
    for b in blocks:
        bt = b.get("type")
        if bt == "text":
            parts.append(b.get("text", ""))
        elif bt == "code":
            lang = b.get("language", "")
            parts.append(f"```{lang}\n{b.get('code', '')}\n```")
        elif bt == "diff":
            parts.append(f"--- {b.get('filename')}\n{b.get('before')}\n+++\n{b.get('after')}")
        elif bt == "web_preview":
            parts.append(f"[Web Preview: {b.get('url')}]")
        elif bt == "file":
            parts.append(f"[File: {b.get('filename')}]")
    return "\n".join(parts)


async def build_context(
    db: AsyncSession,
    conversation_id: UUID,
    max_chars: int = 24_000,  # ~8K tokens
) -> list[ChatMessage]:
    """Build a ChatMessage list from DB history, respecting char budget."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.status.in_(["done", "streaming"]))
        .order_by(Message.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    result: list[ChatMessage] = []
    total = 0
    # walk backward, keep most recent
    for m in reversed(list(rows)):
        text = _blocks_to_text(m.content)
        if total + len(text) > max_chars and result:
            break
        role = "assistant" if m.role == "agent" else m.role
        # Type-cast role to chat message accepted values
        if role not in ("user", "assistant", "system"):
            continue
        result.insert(0, ChatMessage(role=role, content=text))  # type: ignore[arg-type]
        total += len(text)
    return result
