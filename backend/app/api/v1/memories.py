"""MemoryHub routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DbSession, get_current_user
from app.models.memory import Memory
from app.models.user import User
from app.schemas.memory import (
    MemoryKind,
    MemoryList,
    MemoryOut,
    MemoryScopeType,
    MemoryStatus,
    UpdateMemoryRequest,
)
from app.services.memory_hub import MemoryHubService

router = APIRouter()


@router.get("", response_model=MemoryList)
async def list_memories(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    scope_type: MemoryScopeType | None = Query(default=None),
    scope_id: UUID | None = Query(default=None),
    kind: MemoryKind | None = Query(default=None),
    status_filter: MemoryStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryList:
    items, total = await MemoryHubService().list_memories(
        db,
        owner_user_id=user.id,
        scope_type=scope_type,
        scope_id=scope_id,
        kind=kind,
        status=status_filter,
        limit=limit,
    )
    return MemoryList(
        items=[MemoryOut.model_validate(item) for item in items],
        total=total,
    )


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: UUID,
    payload: UpdateMemoryRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> MemoryOut:
    memory = await _get_owned_memory(db, user.id, memory_id)
    updated = await MemoryHubService().update_memory(
        db,
        memory,
        content=payload.content,
        importance=payload.importance,
        status=payload.status,
        kind=payload.kind,
        valid_until=payload.valid_until,
        metadata=payload.metadata,
    )
    await db.commit()
    await db.refresh(updated)
    return MemoryOut.model_validate(updated)


@router.delete("/{memory_id}", response_model=MemoryOut)
async def forget_memory(
    memory_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> MemoryOut:
    memory = await _get_owned_memory(db, user.id, memory_id)
    updated = await MemoryHubService().forget_memory(db, memory)
    await db.commit()
    await db.refresh(updated)
    return MemoryOut.model_validate(updated)


async def _get_owned_memory(db: DbSession, user_id: UUID, memory_id: UUID) -> Memory:
    memory = await db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "MEMORY_NOT_FOUND", "message": "Not found"}},
        )
    if memory.owner_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}},
        )
    return memory
