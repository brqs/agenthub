"""Persistent queued user turns for busy conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_queue import MessageQueueEntry


@dataclass(frozen=True)
class QueuedDispatch:
    user_message: Message
    agent_message: Message
    queue_remaining_count: int


async def get_active_agent_message(db: AsyncSession, conv_id: UUID) -> Message | None:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .where(Message.role == "agent")
        .where(Message.status.in_(("pending", "streaming")))
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def queue_position(db: AsyncSession, entry: MessageQueueEntry) -> int:
    stmt = (
        select(func.count())
        .select_from(MessageQueueEntry)
        .where(MessageQueueEntry.conversation_id == entry.conversation_id)
        .where(MessageQueueEntry.state == "queued")
        .where(MessageQueueEntry.created_at <= entry.created_at)
    )
    return int((await db.execute(stmt)).scalar_one())


async def queued_count(db: AsyncSession, conv_id: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(MessageQueueEntry)
        .where(MessageQueueEntry.conversation_id == conv_id)
        .where(MessageQueueEntry.state == "queued")
    )
    return int((await db.execute(stmt)).scalar_one())


async def enqueue_user_message(
    db: AsyncSession,
    *,
    conversation: Conversation,
    target_agent_id: str,
    content: list[dict[str, Any]],
) -> tuple[Message, MessageQueueEntry, int]:
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=content,
        status="queued",
    )
    db.add(user_msg)
    await db.flush()

    entry = MessageQueueEntry(
        conversation_id=conversation.id,
        user_message_id=user_msg.id,
        target_agent_id=target_agent_id,
        state="queued",
    )
    db.add(entry)
    conversation.last_message_at = datetime.now(UTC)
    await db.flush()
    position = await queue_position(db, entry)
    return user_msg, entry, position


async def get_queue_entry_for_user_message(
    db: AsyncSession,
    *,
    user_message_id: UUID,
) -> MessageQueueEntry | None:
    stmt = select(MessageQueueEntry).where(
        MessageQueueEntry.user_message_id == user_message_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_queued_user_message(
    db: AsyncSession,
    *,
    user_message: Message,
    queue_entry: MessageQueueEntry,
    content: list[dict[str, Any]] | None = None,
    target_agent_id: str | None = None,
) -> int:
    if content is not None:
        user_message.content = content
    if target_agent_id is not None:
        queue_entry.target_agent_id = target_agent_id
    await db.flush()
    return await queue_position(db, queue_entry)


async def delete_queued_user_message(
    db: AsyncSession,
    *,
    user_message: Message,
    queue_entry: MessageQueueEntry,
) -> None:
    _ = queue_entry
    await db.delete(user_message)
    await db.flush()


async def dispatch_next_queued_message(
    db: AsyncSession,
    *,
    conversation_id: UUID,
) -> QueuedDispatch | None:
    conversation = await _lock_conversation(db, conversation_id)
    if conversation is None:
        return None
    active_message = await get_active_agent_message(db, conversation_id)
    if active_message is not None:
        return None

    last_terminal_dispatch: QueuedDispatch | None = None
    while True:
        entry = await _lock_next_queue_entry(db, conversation_id)
        if entry is None:
            return last_terminal_dispatch
        user_message = await db.get(Message, entry.user_message_id)
        if user_message is None or user_message.status != "queued":
            entry.state = "dispatched"
            entry.dispatched_at = datetime.now(UTC)
            await db.flush()
            continue

        user_message.status = "done"
        if entry.target_agent_id not in conversation.agent_ids:
            agent_message = _queued_target_missing_message(
                conversation_id=conversation_id,
                user_message_id=user_message.id,
                target_agent_id=entry.target_agent_id,
            )
        else:
            agent_message = Message(
                conversation_id=conversation_id,
                role="agent",
                agent_id=entry.target_agent_id,
                content=[],
                reply_to_id=user_message.id,
                status="pending",
            )
        db.add(agent_message)
        await db.flush()
        entry.state = "dispatched"
        entry.dispatched_agent_message_id = agent_message.id
        entry.dispatched_at = datetime.now(UTC)
        conversation.last_message_at = datetime.now(UTC)
        await db.flush()
        remaining = await queued_count(db, conversation_id)
        dispatch = QueuedDispatch(
            user_message=user_message,
            agent_message=agent_message,
            queue_remaining_count=remaining,
        )
        if agent_message.status == "error":
            last_terminal_dispatch = dispatch
            continue
        return dispatch


async def _lock_conversation(db: AsyncSession, conversation_id: UUID) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _lock_next_queue_entry(
    db: AsyncSession,
    conversation_id: UUID,
) -> MessageQueueEntry | None:
    stmt = (
        select(MessageQueueEntry)
        .where(MessageQueueEntry.conversation_id == conversation_id)
        .where(MessageQueueEntry.state == "queued")
        .order_by(MessageQueueEntry.created_at.asc(), MessageQueueEntry.id.asc())
        .limit(1)
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _queued_target_missing_message(
    *,
    conversation_id: UUID,
    user_message_id: UUID,
    target_agent_id: str,
) -> Message:
    return Message(
        conversation_id=conversation_id,
        role="agent",
        agent_id=target_agent_id,
        content=[
            {
                "type": "text",
                "text": (
                    "Queued target Agent is no longer available in this conversation. "
                    "Please send the request again with an available Agent."
                ),
            }
        ],
        reply_to_id=user_message_id,
        status="error",
    )
