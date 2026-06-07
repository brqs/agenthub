"""Conversation control-plane helpers for guidance and side chat."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.models.message import Message
from app.models.turn_control import ConversationTurnControl
from app.services.queued_messages import queued_count
from app.services.stream_run_manager import stream_run_manager

GUIDANCE_SUPPORTED_AGENT_IDS = {"orchestrator"}
PENDING_GUIDANCE_STATES = {"received", "waiting_safe_point"}


async def create_guidance_control(
    db: AsyncSession,
    *,
    active_message: Message,
    body: str,
    source_content: list[dict[str, Any]],
    created_by_message: Message | None = None,
) -> tuple[ConversationTurnControl, Message]:
    if active_message.agent_id not in GUIDANCE_SUPPORTED_AGENT_IDS:
        raise ValueError("GUIDANCE_NOT_SUPPORTED")

    user_message = created_by_message or Message(
        conversation_id=active_message.conversation_id,
        role="user",
        content=[*source_content],
        status="done",
    )
    if created_by_message is None:
        db.add(user_message)
        await db.flush()

    control = ConversationTurnControl(
        conversation_id=active_message.conversation_id,
        active_agent_message_id=active_message.id,
        created_by_message_id=user_message.id,
        kind="guidance",
        state="waiting_safe_point",
        payload={
            "title": "Guidance received",
            "body": body,
            "source_message_ids": [str(user_message.id)],
        },
    )
    db.add(control)
    await db.flush()
    user_message.content = [
        *source_content,
        turn_control_block(control, title="Guidance received", body=body),
    ]
    await db.flush()
    await publish_turn_control(control)
    return control, user_message


async def create_side_chat_control(
    db: AsyncSession,
    *,
    active_message: Message,
    body: str,
    source_content: list[dict[str, Any]],
) -> tuple[ConversationTurnControl, Message, Message]:
    user_message = Message(
        conversation_id=active_message.conversation_id,
        role="user",
        content=[*source_content],
        status="done",
    )
    db.add(user_message)
    await db.flush()

    answer = await _side_chat_answer(db, active_message, body)
    control = ConversationTurnControl(
        conversation_id=active_message.conversation_id,
        active_agent_message_id=active_message.id,
        created_by_message_id=user_message.id,
        kind="side_chat",
        state="answered",
        payload={
            "title": "Side chat answered",
            "body": body,
            "answer": answer,
            "source_message_ids": [str(user_message.id)],
        },
        applied_at=datetime.now(UTC),
    )
    db.add(control)
    await db.flush()
    user_message.content = [
        *source_content,
        turn_control_block(control, title="Side chat", body=body),
    ]
    agent_message = Message(
        conversation_id=active_message.conversation_id,
        role="agent",
        agent_id=active_message.agent_id,
        reply_to_id=user_message.id,
        content=[
            {
                "type": "turn_control",
                "kind": "side_chat",
                "status": "answered",
                "control_id": str(control.id),
                "active_agent_message_id": str(active_message.id),
                "title": "Side chat answered",
                "body": answer,
                "source_message_ids": [str(user_message.id)],
                "metadata": {"side_chat": True},
            },
            {"type": "text", "text": answer},
        ],
        status="done",
    )
    db.add(agent_message)
    await db.flush()
    await publish_turn_control(control)
    return control, user_message, agent_message


async def poll_pending_guidance_for_message(
    active_message_id: UUID,
    *,
    safe_point: str,
) -> str | None:
    async with SessionFactory() as db:
        stmt = (
            select(ConversationTurnControl)
            .where(ConversationTurnControl.active_agent_message_id == active_message_id)
            .where(ConversationTurnControl.kind == "guidance")
            .where(ConversationTurnControl.state.in_(PENDING_GUIDANCE_STATES))
            .order_by(ConversationTurnControl.created_at.asc())
            .limit(1)
            .with_for_update()
        )
        control = (await db.execute(stmt)).scalar_one_or_none()
        if control is None:
            return None
        control.state = "applied"
        control.applied_at = datetime.now(UTC)
        control.payload = {
            **dict(control.payload or {}),
            "safe_point": safe_point,
        }
        await db.flush()
        await _sync_created_message_block(db, control)
        await db.commit()
        await db.refresh(control)
        await publish_turn_control(control)
        body = str((control.payload or {}).get("body") or "").strip()
        return body or None


async def expire_pending_controls(active_message_id: UUID) -> None:
    async with SessionFactory() as db:
        stmt = (
            select(ConversationTurnControl)
            .where(ConversationTurnControl.active_agent_message_id == active_message_id)
            .where(ConversationTurnControl.kind == "guidance")
            .where(ConversationTurnControl.state.in_(PENDING_GUIDANCE_STATES))
            .with_for_update()
        )
        controls = list((await db.execute(stmt)).scalars().all())
        for control in controls:
            control.state = "expired"
            control.payload = {
                **dict(control.payload or {}),
                "expired_reason": "active_turn_terminal",
            }
            await _sync_created_message_block(db, control)
        if controls:
            await db.commit()
            for control in controls:
                await publish_turn_control(control)


async def publish_turn_control(control: ConversationTurnControl) -> None:
    await stream_run_manager.publish_turn_control_event(
        control.active_agent_message_id,
        turn_control_block(control),
    )


def turn_control_block(
    control: ConversationTurnControl,
    *,
    title: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    payload = dict(control.payload or {})
    source_ids = [
        str(item)
        for item in payload.get("source_message_ids", [])
        if isinstance(item, str)
    ]
    return {
        "type": "turn_control",
        "kind": control.kind,
        "status": control.state,
        "control_id": str(control.id),
        "active_agent_message_id": str(control.active_agent_message_id),
        "title": title or str(payload.get("title") or _default_title(control.kind, control.state)),
        "body": body if body is not None else payload.get("body"),
        "source_message_ids": source_ids,
        "metadata": {
            key: value
            for key, value in payload.items()
            if key not in {"title", "body", "source_message_ids"}
        },
    }


async def _sync_created_message_block(
    db: AsyncSession,
    control: ConversationTurnControl,
) -> None:
    if control.created_by_message_id is None:
        return
    message = await db.get(Message, control.created_by_message_id)
    if message is None:
        return
    next_block = turn_control_block(control)
    content: list[dict[str, Any]] = []
    replaced = False
    for block in message.content:
        if (
            isinstance(block, dict)
            and block.get("type") == "turn_control"
            and str(block.get("control_id")) == str(control.id)
        ):
            content.append(next_block)
            replaced = True
        else:
            content.append(block)
    if not replaced:
        content.append(next_block)
    message.content = content


async def _side_chat_answer(
    db: AsyncSession,
    active_message: Message,
    body: str,
) -> str:
    queue_total = await queued_count(db, active_message.conversation_id)
    status = active_message.status
    agent = active_message.agent_id or "agent"
    question = " ".join(body.split())[:160]
    return (
        f"Current active turn is handled by @{agent} and is {status}. "
        f"There are {queue_total} queued next-turn message(s). "
        f"Your side question was: {question}"
    )


def _default_title(kind: str, state: str) -> str:
    if kind == "guidance":
        if state == "applied":
            return "Guidance applied"
        if state == "expired":
            return "Guidance expired"
        return "Guidance received"
    if kind == "side_chat":
        return "Side chat"
    if kind == "stop_and_run":
        return "Stop and run"
    return "Queue action"
