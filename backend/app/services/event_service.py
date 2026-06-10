"""User-scoped event outbox and lightweight in-process fanout."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import UserEvent
from app.schemas.events import UserEventOut


class UserEventService:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[UserEventOut]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def record(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        event_type: str,
        resource_type: str,
        resource_id: str | UUID,
        conversation_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> UserEventOut:
        event = UserEvent(
            user_id=user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=str(resource_id),
            conversation_id=conversation_id,
            payload=_json_safe(payload or {}),
        )
        db.add(event)
        await db.flush()
        out = UserEventOut.model_validate(event)
        await self.publish(out, user_id=user_id)
        return out

    async def list_since(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        cursor: int | None,
        limit: int = 100,
    ) -> list[UserEventOut]:
        stmt = select(UserEvent).where(UserEvent.user_id == user_id)
        if cursor is not None:
            stmt = stmt.where(UserEvent.cursor > cursor)
        stmt = stmt.order_by(UserEvent.cursor).limit(limit)
        return [UserEventOut.model_validate(row) for row in (await db.execute(stmt)).scalars()]

    async def publish(self, event: UserEventOut, *, user_id: UUID) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(user_id, ()))
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow clients can reconnect with their cursor and catch up from DB.
                pass

    async def subscribe(self, user_id: UUID) -> AsyncIterator[UserEventOut]:
        queue: asyncio.Queue[UserEventOut] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[user_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers[user_id].discard(queue)
                if not self._subscribers[user_id]:
                    self._subscribers.pop(user_id, None)


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


event_service = UserEventService()
