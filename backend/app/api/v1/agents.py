"""Agent routes — Owner: B2 (with B1 assist for routing wiring)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.agents.config_validation import (
    AgentConfigValidationError,
    merge_agent_config,
    validate_agent_config,
)
from app.core.deps import DbSession, get_current_user
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import (
    AgentList,
    AgentOut,
    AgentProvider,
    CreateAgentRequest,
    UpdateAgentRequest,
)

router = APIRouter()


def _format_validation_error(exc: AgentConfigValidationError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }


@router.get("", response_model=AgentList)
async def list_agents(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    builtin: bool | None = Query(default=None),
    provider: AgentProvider | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> AgentList:
    # Show builtin + this user's agents
    stmt = select(Agent).where(or_(Agent.is_builtin.is_(True), Agent.user_id == user.id))
    if builtin is not None:
        stmt = stmt.where(Agent.is_builtin.is_(builtin))
    if provider:
        stmt = stmt.where(Agent.provider == provider)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Agent.is_builtin.desc(), Agent.created_at.asc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return AgentList(
        items=[AgentOut.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: CreateAgentRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentOut:
    try:
        normalized_config = validate_agent_config(
            provider=payload.provider,
            config=payload.config,
            system_prompt=payload.system_prompt,
        )
    except AgentConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc

    agent = Agent(
        id=Agent.new_id(),
        user_id=user.id,
        name=payload.name,
        provider=payload.provider,
        avatar_url=payload.avatar_url,
        capabilities=payload.capabilities,
        system_prompt=payload.system_prompt,
        config=normalized_config,
        is_builtin=False,
    )
    db.add(agent)
    await db.flush()
    return AgentOut.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentOut:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            404,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": "Not found"}},
        )
    if not agent.is_builtin and agent.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}})
    return AgentOut.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str,
    payload: UpdateAgentRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentOut:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            404,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": "Not found"}},
        )
    if agent.is_builtin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "CANNOT_MODIFY_BUILTIN",
                    "message": "Built-in agents are read-only",
                }
            },
        )
    if agent.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}})

    updates = payload.model_dump(exclude_unset=True)

    # Re-validate whenever config or system_prompt is being updated
    if "config" in updates or "system_prompt" in updates:
        patch_config = updates.get("config")
        if patch_config is None and "config" in updates:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "INVALID_AGENT_CONFIG",
                        "message": "config cannot be null",
                    }
                },
            )
        merged_config = merge_agent_config(
            agent.config, patch_config if patch_config is not None else {}
        )
        effective_system_prompt = updates.get("system_prompt", agent.system_prompt)
        try:
            normalized_config = validate_agent_config(
                provider=agent.provider,
                config=merged_config,
                system_prompt=effective_system_prompt,
            )
        except AgentConfigValidationError as exc:
            raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc
        updates["config"] = normalized_config

    for field, value in updates.items():
        setattr(agent, field, value)
    await db.flush()
    return AgentOut.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            404,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": "Not found"}},
        )
    if agent.is_builtin:
        raise HTTPException(
            403,
            detail={
                "error": {
                    "code": "CANNOT_DELETE_BUILTIN",
                    "message": "Built-in agents are read-only",
                }
            },
        )
    if agent.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}})
    await db.delete(agent)
