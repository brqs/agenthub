"""Agent routes — Owner: B2 (with B1 assist for routing wiring)."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified

from app.agents.builtin.mcp.client import MCPClient
from app.agents.config_validation import (
    WRAPPER_BASE_PROVIDERS,
    WRAPPER_MODE,
    AgentConfigValidationError,
    merge_agent_config,
    validate_agent_config,
)
from app.agents.registry import get_adapter
from app.agents.types import ChatMessage
from app.api.v1.stream_accumulator import StreamContentAccumulator
from app.core.config import settings
from app.core.deps import DbSession, get_current_user
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.agent import (
    AgentAssetHistoryOut,
    AgentAssetsOut,
    AgentAssetUsageListOut,
    AgentConfig,
    AgentKnowledgeOut,
    AgentKnowledgeUsage,
    AgentList,
    AgentMCPHealthOut,
    AgentMCPServerHealthOut,
    AgentMCPToolOut,
    AgentOut,
    AgentProvider,
    AgentSkillOut,
    AgentTestRunOut,
    AgentTestRunRequest,
    CreateAgentRequest,
    UpdateAgentKnowledgeRequest,
    UpdateAgentRequest,
    UpdateAgentSkillRequest,
)
from app.services.agent_asset_service import agent_asset_service

router = APIRouter()


def _format_validation_error(exc: AgentConfigValidationError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }


WRAPPER_USER_CONFIG_KEYS = {"custom_agent_mode", "base_agent_id", "wrapper_profile"}
SAFE_BUILTIN_CUSTOM_TOOLS = {"read_file"}


def _config_payload_to_dict(config: AgentConfig | dict[str, Any] | None) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, AgentConfig):
        return config.model_dump(exclude_none=True)
    return dict(config)


def _reject_config_error(message: str, *, field: str, value: Any = None) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": {
                "code": "INVALID_AGENT_CONFIG",
                "message": message,
                "details": {"field": field, "value": value},
            }
        },
    )


def _assert_wrapper_create_config(provider: str, config: dict[str, Any]) -> None:
    unknown = sorted(set(config) - WRAPPER_USER_CONFIG_KEYS)
    if unknown:
        raise _reject_config_error(
            "Custom Agent wrappers may only configure base_agent_id and wrapper_profile",
            field=f"config.{unknown[0]}",
            value=config.get(unknown[0]),
        )
    if config.get("custom_agent_mode") != WRAPPER_MODE:
        raise _reject_config_error(
            "custom_agent_mode is required and must be 'server_agent_wrapper'",
            field="config.custom_agent_mode",
            value=config.get("custom_agent_mode"),
        )
    base_agent_id = config.get("base_agent_id")
    expected_provider = WRAPPER_BASE_PROVIDERS.get(str(base_agent_id))
    if expected_provider != provider:
        raise _reject_config_error(
            "base_agent_id does not match provider",
            field="config.base_agent_id",
            value=base_agent_id,
        )


def _assert_builtin_create_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    allowed_tools = normalized.get("allowed_tools")
    if allowed_tools is None:
        normalized["allowed_tools"] = []
        return normalized
    if not isinstance(allowed_tools, list) or not all(
        isinstance(item, str) for item in allowed_tools
    ):
        raise _reject_config_error(
            "allowed_tools must be a list of strings",
            field="config.allowed_tools",
            value=allowed_tools,
        )
    unsafe = sorted(set(allowed_tools) - SAFE_BUILTIN_CUSTOM_TOOLS)
    if unsafe:
        raise _reject_config_error(
            "User-created builtin Agents may only expose read_file",
            field="config.allowed_tools",
            value=unsafe,
        )
    normalized["allowed_tools"] = allowed_tools
    normalized.setdefault("mcp_servers", [])
    return normalized


def _wrapper_config_from_base(base_agent: Agent, config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(base_agent.config or {})
    normalized["custom_agent_mode"] = WRAPPER_MODE
    normalized["base_agent_id"] = base_agent.id
    normalized["wrapper_profile"] = config.get("wrapper_profile") or {}
    _sync_wrapper_planning_fields(normalized)
    return normalized


def _sync_wrapper_planning_fields(config: dict[str, Any]) -> None:
    profile = config.get("wrapper_profile")
    if not isinstance(profile, dict):
        return
    for key in (
        "planning_profile",
        "planning_strengths",
        "planning_weaknesses",
        "preferred_task_types",
    ):
        value = profile.get(key)
        if value:
            config[key] = value


async def _visible_agent(db: DbSession, user: User, agent_id: str) -> Agent:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            404,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": "Not found"}},
        )
    if not agent.is_builtin and agent.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "FORBIDDEN", "message": "Forbidden"}})
    return agent


def _raw_mcp_servers(agent: Agent) -> list[dict[str, Any]]:
    raw = (agent.config or {}).get("mcp_servers", [])
    if not isinstance(raw, list):
        return []
    return [server for server in raw if isinstance(server, dict)]


async def _health_for_mcp_server(raw_server: dict[str, Any]) -> AgentMCPServerHealthOut:
    name = raw_server.get("name")
    if not isinstance(name, str) or not name:
        return AgentMCPServerHealthOut(
            name="<unnamed>",
            status="unavailable",
            error="MCP server name is missing",
        )
    transport = raw_server.get("transport") or raw_server.get("type") or "stdio"
    command = raw_server.get("command")
    if transport != "stdio" or not isinstance(command, str) or not command:
        return AgentMCPServerHealthOut(
            name=name,
            status="unavailable",
            error="Only stdio MCP servers with a command can be health checked in this MVP",
        )
    if not settings.allow_user_stdio_mcp_health_checks:
        return AgentMCPServerHealthOut(
            name=name,
            status="unavailable",
            error="User-configured stdio MCP health checks are disabled.",
        )
    client = MCPClient.from_config([raw_server])
    try:
        tools = await client.list_tools()
    except Exception as exc:  # noqa: BLE001 - health must be diagnostic, not fatal.
        return AgentMCPServerHealthOut(name=name, status="unavailable", error=str(exc))
    finally:
        await client.aclose()
    return AgentMCPServerHealthOut(
        name=name,
        status="ready",
        tools=[AgentMCPToolOut(name=tool.name, description=tool.description) for tool in tools],
    )


def _safe_error_text(error: str | None) -> str:
    text = (error or "Agent test run failed.").strip()
    return text[:2000] or "Agent test run failed."


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
    else:
        # Mock agents are test/dev fixtures. They can still be queried explicitly
        # with provider=mock, but should not pollute the normal product list.
        stmt = stmt.where(Agent.provider != "mock")

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = (
        stmt.order_by(Agent.is_builtin.desc(), Agent.created_at.asc(), Agent.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
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
    payload_config = _config_payload_to_dict(payload.config)
    if payload.provider == "builtin":
        config = _assert_builtin_create_config(payload_config)
        try:
            normalized_config = validate_agent_config(
                provider=payload.provider,
                config=config,
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

    _assert_wrapper_create_config(payload.provider, payload_config)
    base_agent_id = str(payload_config["base_agent_id"])
    base_agent = await db.get(Agent, base_agent_id)
    if (
        base_agent is None
        or not base_agent.is_builtin
        or base_agent.provider != payload.provider
    ):
        raise _reject_config_error(
            "base_agent_id must reference a matching built-in server Agent",
            field="config.base_agent_id",
            value=base_agent_id,
        )
    config = _wrapper_config_from_base(base_agent, payload_config)
    try:
        normalized_config = validate_agent_config(
            provider=payload.provider,
            config=config,
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


@router.post("/{agent_id}/mcp/health-check", response_model=AgentMCPHealthOut)
async def check_agent_mcp_health(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentMCPHealthOut:
    agent = await _visible_agent(db, user, agent_id)
    servers = [_health_for_mcp_server(server) for server in _raw_mcp_servers(agent)]
    results = [await item for item in servers]
    overall = (
        "ready"
        if results and all(item.status == "ready" for item in results)
        else "unavailable"
    )
    return AgentMCPHealthOut(status=overall, servers=results)


@router.post("/{agent_id}/test-run", response_model=AgentTestRunOut)
async def test_run_agent(
    agent_id: str,
    payload: AgentTestRunRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentTestRunOut:
    await _visible_agent(db, user, agent_id)
    adapter = await get_adapter(agent_id, db)
    accumulator = StreamContentAccumulator()
    status_: str = "done"
    error: str | None = None
    error_code: str | None = None
    with TemporaryDirectory(prefix="agenthub-agent-test-") as temp_dir:
        async for chunk in adapter.stream(
            [ChatMessage(role="user", content=payload.prompt)],
            workspace_path=Path(temp_dir),
        ):
            orphan_error = accumulator.feed(chunk)
            if orphan_error is not None:
                status_ = "error"
                error = orphan_error.error
                error_code = orphan_error.error_code
            if chunk.event_type == "error":
                status_ = "error"
                error = chunk.error
                error_code = chunk.error_code
                break
            if chunk.event_type == "done":
                break
    if accumulator.finalize_orphaned_tools():
        status_ = "error"
        error = error or "Agent emitted an unfinished tool call."
        error_code = error_code or "tool_call_orphan"
    accumulator.finalize_task_cards(success=status_ == "done")
    content = accumulator.to_list()
    if status_ == "error" and not content:
        content = [{"type": "text", "text": _safe_error_text(error)}]
    if status_ == "done" and not content:
        content = [{"type": "text", "text": "The test run completed without visible output."}]
    return AgentTestRunOut(
        status=status_,  # type: ignore[arg-type]
        content=content,  # type: ignore[arg-type]
        error=error,
        error_code=error_code,
    )


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

    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "config" in updates:
        updates["config"] = _config_payload_to_dict(payload.config)

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
        if "config" in updates and (agent.config or {}).get("custom_agent_mode") == WRAPPER_MODE:
            patch_keys = set(patch_config or {})
            if patch_keys - {"wrapper_profile"}:
                first_key = sorted(patch_keys - {"wrapper_profile"})[0]
                raise _reject_config_error(
                    "Only wrapper_profile can be updated for server Agent wrappers",
                    field=f"config.{first_key}",
                    value=(patch_config or {}).get(first_key),
                )
        merged_config = merge_agent_config(
            agent.config, patch_config if patch_config is not None else {}
        )
        if merged_config.get("custom_agent_mode") == WRAPPER_MODE:
            _sync_wrapper_planning_fields(merged_config)
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


@router.get("/{agent_id}/assets", response_model=AgentAssetsOut)
async def list_agent_assets(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentAssetsOut:
    return await agent_asset_service.list_assets(
        db,
        user_id=user.id,
        agent_id=agent_id,
    )


@router.get("/{agent_id}/assets/history", response_model=AgentAssetHistoryOut)
async def list_agent_asset_history(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
) -> AgentAssetHistoryOut:
    return await agent_asset_service.list_history(
        db,
        user_id=user.id,
        agent_id=agent_id,
        limit=limit,
    )


@router.get("/{agent_id}/assets/usage", response_model=AgentAssetUsageListOut)
async def list_agent_asset_usage(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
) -> AgentAssetUsageListOut:
    return await agent_asset_service.list_usage(
        db,
        user_id=user.id,
        agent_id=agent_id,
        limit=limit,
    )


@router.post("/{agent_id}/knowledge", response_model=AgentKnowledgeOut, status_code=201)
async def create_agent_knowledge(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    label: Annotated[str | None, Form()] = None,
    usage: Annotated[AgentKnowledgeUsage, Form()] = "reference",
) -> AgentKnowledgeOut:
    _agent, item = await agent_asset_service.create_knowledge(
        db,
        user_id=user.id,
        agent_id=agent_id,
        file=file,
        label=label,
        usage=usage,
    )
    return item


@router.patch("/{agent_id}/knowledge/{upload_id}", response_model=AgentKnowledgeOut)
async def update_agent_knowledge(
    agent_id: str,
    upload_id: UUID,
    payload: UpdateAgentKnowledgeRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentKnowledgeOut:
    _agent, item = await agent_asset_service.update_knowledge(
        db,
        user_id=user.id,
        agent_id=agent_id,
        upload_id=upload_id,
        label=payload.label,
        usage=payload.usage,
    )
    return item


@router.delete("/{agent_id}/knowledge/{upload_id}", status_code=204)
async def delete_agent_knowledge(
    agent_id: str,
    upload_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await agent_asset_service.delete_knowledge(
        db,
        user_id=user.id,
        agent_id=agent_id,
        upload_id=upload_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{agent_id}/skills", response_model=AgentSkillOut, status_code=201)
async def create_agent_skill(
    agent_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
) -> AgentSkillOut:
    _agent, item = await agent_asset_service.create_skill(
        db,
        user_id=user.id,
        agent_id=agent_id,
        file=file,
        name=name,
        description=description,
    )
    return item


@router.patch("/{agent_id}/skills/{skill_id}", response_model=AgentSkillOut)
async def update_agent_skill(
    agent_id: str,
    skill_id: str,
    payload: UpdateAgentSkillRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AgentSkillOut:
    _agent, item = await agent_asset_service.update_skill(
        db,
        user_id=user.id,
        agent_id=agent_id,
        skill_id=skill_id,
        name=payload.name,
        description=payload.description,
    )
    return item


@router.delete("/{agent_id}/skills/{skill_id}", status_code=204)
async def delete_agent_skill(
    agent_id: str,
    skill_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await agent_asset_service.delete_skill(
        db,
        user_id=user.id,
        agent_id=agent_id,
        skill_id=skill_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    conversations = (
        await db.execute(select(Conversation).where(Conversation.user_id == user.id))
    ).scalars()
    for conversation in conversations:
        agent_ids = [item for item in conversation.agent_ids if isinstance(item, str)]
        if agent_id not in agent_ids:
            continue
        conversation.agent_ids = [item for item in agent_ids if item != agent_id]
        flag_modified(conversation, "agent_ids")
    await db.delete(agent)
