"""Local runtime connector routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.local_runtime_connector import (
    LocalRuntimeConnectorOut,
    LocalRuntimeConnectorStatusOut,
    RegisterLocalRuntimeConnectorRequest,
)
from app.services.local_runtime_connector_service import local_runtime_connector_service

router = APIRouter()


@router.get("/status", response_model=LocalRuntimeConnectorStatusOut)
async def get_local_runtime_connector_status(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> LocalRuntimeConnectorStatusOut:
    return await local_runtime_connector_service.status(db, user_id=user.id)


@router.post("/register", response_model=LocalRuntimeConnectorOut, status_code=201)
async def register_local_runtime_connector(
    payload: RegisterLocalRuntimeConnectorRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> LocalRuntimeConnectorOut:
    connector = await local_runtime_connector_service.register(
        db,
        user_id=user.id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(connector)
    return local_runtime_connector_service.to_out(connector)


@router.delete("/{connector_id}", response_model=LocalRuntimeConnectorOut)
async def revoke_local_runtime_connector(
    connector_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> LocalRuntimeConnectorOut:
    connector = await local_runtime_connector_service.revoke(
        db,
        user_id=user.id,
        connector_id=connector_id,
    )
    await db.commit()
    await db.refresh(connector)
    return local_runtime_connector_service.to_out(connector)
