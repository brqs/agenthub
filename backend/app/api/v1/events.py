"""User-scoped realtime event stream."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.core.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.events import UserEventList
from app.services.event_service import event_service

router = APIRouter()


@router.get("", response_model=UserEventList)
async def list_events(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    cursor: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> UserEventList:
    items = await event_service.list_since(db, user_id=user.id, cursor=cursor, limit=limit)
    return UserEventList(items=items, next_cursor=items[-1].cursor if items else cursor)


@router.get("/stream")
async def stream_events(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    cursor: int | None = Query(default=None, ge=0),
) -> EventSourceResponse:
    async def generate():
        catchup = await event_service.list_since(db, user_id=user.id, cursor=cursor, limit=500)
        for event in catchup:
            yield {
                "event": event.event_type,
                "id": str(event.cursor),
                "data": event.model_dump_json(),
            }
        async for event in event_service.subscribe(user.id):
            if await request.is_disconnected():
                break
            yield {
                "event": event.event_type,
                "id": str(event.cursor),
                "data": event.model_dump_json(),
            }
            await asyncio.sleep(0)

    return EventSourceResponse(generate(), ping=20)
