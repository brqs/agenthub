"""In-process stream runtime ownership shared by SSE and interrupt routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.models.message import Message

StreamRunner = Callable[["StreamRunSession"], Coroutine[object, object, None]]


@dataclass
class StreamRunSession:
    message_id: UUID
    conversation_id: UUID
    events: list[dict[str, str]] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)
    interrupt_requested_at: datetime | None = None
    interrupt_reason: str | None = None
    terminal: bool = False
    task: asyncio.Task[None] | None = None

    async def wait_terminal(self, timeout: float | None = None) -> bool:
        """Wait until this stream reaches any terminal event."""
        async with self.condition:
            if self.terminal:
                return True
            try:
                await asyncio.wait_for(
                    self.condition.wait_for(lambda: self.terminal),
                    timeout=timeout,
                )
            except TimeoutError:
                return False
            return True


class StreamRunManager:
    """Owns agent runtime tasks while allowing multiple SSE subscribers."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, StreamRunSession] = {}
        self._lock = asyncio.Lock()

    async def get(self, message_id: UUID) -> StreamRunSession | None:
        async with self._lock:
            return self._sessions.get(message_id)

    async def start(
        self,
        message: Message,
        runner: StreamRunner,
    ) -> StreamRunSession:
        async with self._lock:
            existing = self._sessions.get(message.id)
            if existing is not None:
                return existing
            session = StreamRunSession(
                message_id=message.id,
                conversation_id=message.conversation_id,
            )
            session.task = asyncio.create_task(runner(session))
            self._sessions[message.id] = session
            return session

    async def publish(
        self,
        session: StreamRunSession,
        event: dict[str, str],
    ) -> None:
        async with session.condition:
            session.events.append(event)
            session.condition.notify_all()

    async def publish_turn_control_event(
        self,
        message_id: UUID,
        turn_control: dict[str, object],
    ) -> bool:
        session = await self.get(message_id)
        if session is None:
            return False
        await self.publish(
            session,
            {
                "event": "turn_control",
                "data": _json_turn_control(turn_control),
            },
        )
        return True

    async def subscribe(
        self,
        session: StreamRunSession,
    ) -> AsyncIterator[dict[str, str]]:
        index = 0
        while True:
            async with session.condition:
                while index >= len(session.events) and not session.terminal:
                    await session.condition.wait()
                if index < len(session.events):
                    event = session.events[index]
                    index += 1
                else:
                    return
            yield event

    async def request_interrupt(
        self,
        message_id: UUID,
        *,
        reason: str = "user_interrupt",
    ) -> StreamRunSession | None:
        async with self._lock:
            session = self._sessions.get(message_id)
            if session is None:
                return None
            if not session.interrupt_event.is_set():
                session.interrupt_requested_at = datetime.now(UTC)
                session.interrupt_reason = reason
                session.interrupt_event.set()
            return session

    async def terminalize(self, session: StreamRunSession) -> None:
        async with session.condition:
            session.terminal = True
            session.condition.notify_all()

    async def finish(self, session: StreamRunSession) -> None:
        await self.terminalize(session)
        async with self._lock:
            current = self._sessions.get(session.message_id)
            if current is session:
                self._sessions.pop(session.message_id, None)


stream_run_manager = StreamRunManager()


def _json_turn_control(turn_control: dict[str, object]) -> str:
    return json.dumps({"turn_control": turn_control}, default=str, ensure_ascii=False)
