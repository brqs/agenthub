"""Conversation routes — Owner: B1.

TODO(B1): full implementation. This is a skeleton.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DbSession, get_current_user
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.conversation_memory import ConversationMemory
from app.models.memory import Memory
from app.models.message import Message
from app.models.user import User
from app.schemas.conversation import (
    AgentCapabilityProfileItemOut,
    AgentCapabilityProfileOut,
    AgentCapabilityProfileV2ItemOut,
    AgentCapabilityProfileV2Out,
    ConversationList,
    ConversationMemoryOut,
    ConversationOut,
    CreateConversationRequest,
    OrchestratorRunDetailOut,
    OrchestratorRunEventOut,
    OrchestratorRunList,
    OrchestratorRunOut,
    OrchestratorTaskAttemptOut,
    OrchestratorTaskOut,
    UpdateConversationRequest,
    UserPreferenceMemoryOut,
)
from app.schemas.memory import (
    ConversationMemoryHubOut,
    MemoryMountList,
    MemoryMountOut,
    MemoryOut,
)
from app.services.event_service import event_service
from app.services.memory_hub import MemoryHubService
from app.services.orchestrator_memory import (
    build_agent_capability_profile,
    build_agent_capability_profile_v2,
    get_orchestrator_run_detail,
    list_orchestrator_runs,
)
from app.services.workspace_deployment import WorkspaceDeploymentService
from app.services.workspace_preview import WorkspacePreviewService
from app.services.workspace_service import WorkspaceService

router = APIRouter()


def _raise_agent_count_error(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": {"code": "INVALID_AGENT_COUNT", "message": message}},
    )


async def _validate_visible_agent_ids(
    db: AsyncSession,
    user_id: UUID,
    agent_ids: list[str],
) -> None:
    requested = set(agent_ids)
    if not requested:
        _raise_agent_count_error("agent_ids must not be empty")

    stmt = select(Agent.id).where(
        Agent.id.in_(requested),
        or_(Agent.is_builtin.is_(True), Agent.user_id == user_id),
    )
    found = set((await db.execute(stmt)).scalars().all())
    missing = sorted(requested - found)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": "One or more agents were not found",
                    "details": {"agent_ids": missing},
                }
            },
        )


async def _validate_conversation_agents(
    db: AsyncSession,
    user_id: UUID,
    mode: str,
    agent_ids: list[str],
) -> None:
    unique_agent_count = len(set(agent_ids))
    if len(agent_ids) != unique_agent_count:
        _raise_agent_count_error("agent_ids must be unique")
    if mode == "single" and unique_agent_count != 1:
        _raise_agent_count_error("single conversations require exactly one agent")
    if mode == "group" and unique_agent_count < 2:
        _raise_agent_count_error("group conversations require at least two agents")
    await _validate_visible_agent_ids(db, user_id, agent_ids)


@router.get("", response_model=ConversationList)
async def list_conversations(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    archived: bool = Query(default=False),
    pinned_only: bool = Query(default=False),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationList:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if not archived:
        stmt = stmt.where(Conversation.is_archived.is_(False))
    if pinned_only:
        stmt = stmt.where(Conversation.is_pinned.is_(True))
    if search:
        stmt = stmt.where(Conversation.title.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = (
        stmt.order_by(desc(Conversation.is_pinned), desc(Conversation.last_message_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()

    return ConversationList(
        items=[ConversationOut.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: CreateConversationRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationOut:
    await _validate_conversation_agents(db, user.id, payload.mode, payload.agent_ids)
    conv = Conversation(
        user_id=user.id,
        title=payload.title,
        mode=payload.mode,
        agent_ids=payload.agent_ids,
    )
    db.add(conv)
    await db.flush()
    await event_service.record(
        db,
        user_id=user.id,
        event_type="conversation.created",
        resource_type="conversation",
        resource_id=conv.id,
        conversation_id=conv.id,
    )
    return ConversationOut.model_validate(conv)


async def _get_owned_conversation(
    db: AsyncSession,
    user_id: UUID,
    conv_id: UUID,
) -> Conversation:
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Not found"}},
        )
    if conv.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}},
        )
    return conv


@router.get("/{conv_id}", response_model=ConversationOut)
async def get_conversation(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationOut:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    return ConversationOut.model_validate(conv)


@router.get("/{conv_id}/memory", response_model=ConversationMemoryOut)
async def get_conversation_memory(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationMemoryOut:
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user.id, conv_id)
    memory = await db.get(ConversationMemory, conv_id)
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "MEMORY_NOT_FOUND", "message": "Not found"}},
        )
    return ConversationMemoryOut.model_validate(memory)


@router.get(
    "/{conversation_id}/agent-capability-profile",
    response_model=AgentCapabilityProfileOut,
)
async def get_conversation_agent_capability_profile(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    recent_runs: int = Query(default=20, ge=1, le=100),
) -> AgentCapabilityProfileOut:
    await _get_owned_conversation(db, user.id, conversation_id)
    items = await build_agent_capability_profile(
        db,
        conversation_id,
        recent_runs=recent_runs,
    )
    return AgentCapabilityProfileOut(
        items=[AgentCapabilityProfileItemOut.model_validate(item) for item in items],
        total=len(items),
    )


@router.get(
    "/{conversation_id}/agent-capability-profile-v2",
    response_model=AgentCapabilityProfileV2Out,
)
async def get_conversation_agent_capability_profile_v2(
    conversation_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    recent_runs: int = Query(default=60, ge=1, le=100),
    half_life_days: float = Query(default=30.0, ge=1.0, le=365.0),
    limit: int = Query(default=10, ge=1, le=100),
) -> AgentCapabilityProfileV2Out:
    await _get_owned_conversation(db, user.id, conversation_id)
    profile = await build_agent_capability_profile_v2(
        db,
        user.id,
        conversation_id=conversation_id,
        recent_runs=recent_runs,
        half_life_days=half_life_days,
        limit=limit,
    )
    return AgentCapabilityProfileV2Out(
        items=[
            AgentCapabilityProfileV2ItemOut.model_validate(item)
            for item in profile.items
        ],
        preferences=UserPreferenceMemoryOut.model_validate(profile.preferences),
        scope=profile.scope,
        source_conversation_count=profile.source_conversation_count,
        runs_considered=profile.runs_considered,
        generated_at=profile.generated_at,
        total=len(profile.items),
    )


@router.get("/{conv_id}/memory-mounts", response_model=MemoryMountList)
async def list_conversation_memory_mounts(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryMountList:
    conversation = await _get_owned_conversation(db, user.id, conv_id)
    mounts, total = await MemoryHubService().list_mounts(
        db,
        conversation_id=conv_id,
        limit=limit,
    )
    memory_ids = [mount.memory_id for mount in mounts]
    memories = {}
    if memory_ids:
        rows = (
            await db.execute(
                select(Memory)
                .where(Memory.id.in_(memory_ids))
                .where(Memory.owner_user_id == user.id)
                .where(Memory.status != "forgotten")
            )
        ).scalars().all()
        memories = {memory.id: memory for memory in rows}
    latest_agent_query = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .where(Message.role == "agent")
    )
    if conversation.mode == "group" and "orchestrator" in conversation.agent_ids:
        latest_agent_query = latest_agent_query.where(
            Message.agent_id == "orchestrator"
        )
    latest_agent_message = (
        await db.execute(
            latest_agent_query.order_by(desc(Message.created_at)).limit(1)
        )
    ).scalar_one_or_none()
    recall_state = (
        "not_attempted"
        if latest_agent_message is None
        else (
            "mounted"
            if any(
                mount.agent_message_id == latest_agent_message.id
                for mount in mounts
            )
            else "no_match"
        )
    )
    return MemoryMountList(
        items=[
            MemoryMountOut(
                id=mount.id,
                conversation_id=mount.conversation_id,
                agent_message_id=mount.agent_message_id,
                memory_id=mount.memory_id,
                mount_reason=mount.mount_reason,
                rank_score=mount.rank_score,
                created_at=mount.created_at,
                memory=(
                    MemoryOut.model_validate(memories[mount.memory_id])
                    if mount.memory_id in memories
                    else None
                ),
            )
            for mount in mounts
        ],
        total=total,
        recall_state=recall_state,
        latest_agent_message_id=(
            latest_agent_message.id if latest_agent_message is not None else None
        ),
        latest_agent_id=(
            latest_agent_message.agent_id if latest_agent_message is not None else None
        ),
        latest_agent_status=(
            latest_agent_message.status if latest_agent_message is not None else None
        ),
    )


@router.get("/{conv_id}/memory-hub", response_model=ConversationMemoryHubOut)
async def get_conversation_memory_hub(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=100, ge=1, le=200),
) -> ConversationMemoryHubOut:
    conversation = await _get_owned_conversation(db, user.id, conv_id)
    groups = await MemoryHubService().list_conversation_memory_hub(
        db,
        owner_user_id=user.id,
        conversation=conversation,
        limit=limit,
    )
    return ConversationMemoryHubOut(
        **{
            key: [MemoryOut.model_validate(item) for item in items]
            for key, items in groups.items()
        }
    )


@router.get("/{conv_id}/orchestrator-runs", response_model=OrchestratorRunList)
async def list_conversation_orchestrator_runs(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100),
) -> OrchestratorRunList:
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user.id, conv_id)
    runs = await list_orchestrator_runs(db, conv_id, limit=limit)
    return OrchestratorRunList(
        items=[OrchestratorRunOut.model_validate(run) for run in runs],
        total=len(runs),
    )


@router.get(
    "/{conv_id}/orchestrator-runs/{run_id}",
    response_model=OrchestratorRunDetailOut,
)
async def get_conversation_orchestrator_run(
    conv_id: UUID,
    run_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> OrchestratorRunDetailOut:
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Not found"}},
        )
    await _get_owned_conversation(db, user.id, conv_id)
    detail = await get_orchestrator_run_detail(db, conv_id, run_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ORCHESTRATOR_RUN_NOT_FOUND", "message": "Not found"}},
        )
    run, tasks, attempts, events = detail
    return OrchestratorRunDetailOut(
        run=OrchestratorRunOut.model_validate(run),
        tasks=[OrchestratorTaskOut.model_validate(task) for task in tasks],
        attempts=[
            OrchestratorTaskAttemptOut.model_validate(attempt)
            for attempt in attempts
        ],
        events=[OrchestratorRunEventOut.model_validate(event) for event in events],
    )


@router.patch("/{conv_id}", response_model=ConversationOut)
async def update_conversation(
    conv_id: UUID,
    payload: UpdateConversationRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ConversationOut:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    if payload.title is not None:
        conv.title = payload.title
    if payload.is_pinned is not None:
        conv.is_pinned = payload.is_pinned
    if payload.is_archived is not None:
        conv.is_archived = payload.is_archived
    await db.flush()
    await event_service.record(
        db,
        user_id=user.id,
        event_type="conversation.updated",
        resource_type="conversation",
        resource_id=conv.id,
        conversation_id=conv.id,
        payload={
            "title": conv.title,
            "is_pinned": conv.is_pinned,
            "is_archived": conv.is_archived,
        },
    )
    return ConversationOut.model_validate(conv)


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    conv = await _get_owned_conversation(db, user.id, conv_id)
    await WorkspacePreviewService().stop(db, conv_id)
    await WorkspaceDeploymentService().cleanup_for_conversation(db, conv_id)
    await WorkspaceService().delete(db, conv_id)
    await db.delete(conv)
    await event_service.record(
        db,
        user_id=user.id,
        event_type="conversation.deleted",
        resource_type="conversation",
        resource_id=conv_id,
        conversation_id=conv_id,
    )
