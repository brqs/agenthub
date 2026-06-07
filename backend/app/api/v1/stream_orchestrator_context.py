"""Orchestrator-specific context wiring for the SSE stream endpoint."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgentAdapter
from app.agents.external.claude_code import claude_code_runtime_status
from app.agents.external.opencode import opencode_runtime_status
from app.agents.orchestrator.availability import is_runnable_agent_context
from app.agents.registry import ORCHESTRATOR_AGENT_ID
from app.agents.types import ChatMessage
from app.api.v1.orchestrator_group_messages import OrchestratorGroupMessageWriter
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.orchestrator_memory import (
    DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS,
    DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS,
    OrchestratorMemoryStore,
    build_orchestrator_memory_context,
    inject_orchestrator_memory_context,
)
from app.services.orchestrator_platform_tools import OrchestratorPlatformToolExecutor
from app.services.workspace_workflow_runtime import WorkspaceWorkflowRuntimeService


def _agent_context(agent: Agent) -> dict[str, Any]:
    capabilities = agent.capabilities if isinstance(agent.capabilities, list) else []
    context: dict[str, Any] = {
        "id": agent.id,
        "name": agent.name,
        "provider": agent.provider,
        "capabilities": [item for item in capabilities if isinstance(item, str)],
        "is_builtin": agent.is_builtin,
    }
    if isinstance(agent.config, dict):
        for key in (
            "model_backend",
            "answer_model_backend",
            "planner_model_backend",
            "qa_model_backend",
            "qa_model",
            "runtime",
        ):
            value = agent.config.get(key)
            if isinstance(value, str) and value.strip():
                context[key] = value.strip()
    if agent.provider == "opencode":
        status, error = opencode_runtime_status(
            agent.config if isinstance(agent.config, dict) else None
        )
        context["runtime_status"] = status
        context["runtime_available"] = status == "ready"
        if error:
            context["runtime_error"] = error
    if agent.provider == "claude_code":
        status, error = claude_code_runtime_status(
            agent.config if isinstance(agent.config, dict) else None
        )
        context["runtime_status"] = status
        context["runtime_available"] = status == "ready"
        if error:
            context["runtime_error"] = error
    return context


async def _orchestrator_conversation_config(
    db: AsyncSession,
    message: Message,
) -> dict[str, Any] | None:
    if message.agent_id != ORCHESTRATOR_AGENT_ID:
        return None

    conversation = await db.get(Conversation, message.conversation_id)
    if conversation is None or conversation.mode != "group":
        return None

    agent_ids = [agent_id for agent_id in conversation.agent_ids if isinstance(agent_id, str)]
    if not agent_ids:
        return None

    result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
    agents_by_id = {agent.id: agent for agent in result.scalars().all()}
    conversation_agents = [
        _agent_context(agent)
        for agent_id in agent_ids
        if (agent := agents_by_id.get(agent_id)) is not None
    ]
    if not conversation_agents:
        return None

    available_agents = [
        agent
        for agent in conversation_agents
        if agent.get("id") != ORCHESTRATOR_AGENT_ID
        and is_runnable_agent_context(agent)
    ]
    managed_agent_ids = [
        agent["id"]
        for agent in available_agents
        if isinstance(agent.get("id"), str)
    ]
    config: dict[str, Any] = {
        "conversation_agents": conversation_agents,
        "available_agents": available_agents,
        "available_agents_authoritative": True,
        "conversation_scoped_agents": True,
        "managed_agent_ids": managed_agent_ids,
        "orchestrator_include_group_agents_in_planning": True,
    }
    return config


async def apply_orchestrator_stream_context(
    db: AsyncSession,
    message: Message,
    adapter: BaseAgentAdapter,
    history: list[ChatMessage],
) -> tuple[list[ChatMessage], dict[str, Any] | None]:
    stream_config = await _orchestrator_conversation_config(db, message)
    if message.agent_id != ORCHESTRATOR_AGENT_ID:
        return history, stream_config

    stream_config = stream_config or {}
    merged_config = adapter.merged_config(stream_config)
    db_lock = asyncio.Lock()
    stream_config["orchestrator_db_lock"] = db_lock
    memory_message = await _orchestrator_memory_context_message(
        db,
        message.conversation_id,
        merged_config,
    )
    history = inject_orchestrator_memory_context(history, memory_message)
    if _orchestrator_memory_enabled(merged_config):
        stream_config["orchestrator_memory_writer"] = OrchestratorMemoryStore(
            db,
            conversation_id=message.conversation_id,
            agent_message_id=message.id,
            user_message_id=message.reply_to_id,
        )
        stream_config["orchestrator_memory_lock"] = db_lock
    if (
        stream_config.get("conversation_scoped_agents") is True
        and merged_config.get("orchestrator_group_messages_enabled", True) is not False
    ):
        stream_config["orchestrator_group_message_writer"] = OrchestratorGroupMessageWriter(
            db,
            conversation_id=message.conversation_id,
            parent_message_id=message.id,
            user_message_id=message.reply_to_id,
            lock=db_lock,
        )
    stream_config["conversation_id"] = message.conversation_id
    stream_config["orchestrator_db_session"] = db
    stream_config["orchestrator_artifact_manifest_lock"] = asyncio.Lock()
    stream_config["orchestrator_workflow_runtime_lock"] = asyncio.Lock()
    stream_config["orchestrator_workflow_runtime_service"] = WorkspaceWorkflowRuntimeService()
    stream_config["orchestrator_platform_tool_executor"] = OrchestratorPlatformToolExecutor(
        db=db,
        conversation_id=message.conversation_id,
    )
    return history, stream_config


def _orchestrator_memory_enabled(config: dict[str, Any]) -> bool:
    return config.get("orchestrator_memory_enabled", True) is not False


def _positive_int_config(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


async def _orchestrator_memory_context_message(
    db: AsyncSession,
    conversation_id: UUID,
    config: dict[str, Any],
) -> Any:
    if not _orchestrator_memory_enabled(config):
        return None
    try:
        return await build_orchestrator_memory_context(
            db,
            conversation_id,
            recent_runs=_positive_int_config(
                config,
                "orchestrator_memory_recent_runs",
                DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS,
            ),
            max_chars=_positive_int_config(
                config,
                "orchestrator_memory_context_max_chars",
                DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS,
            ),
        )
    except Exception:  # noqa: BLE001
        return None


async def cancel_orchestrator_run(config: dict[str, Any] | None) -> None:
    if not config:
        return
    writer = config.get("orchestrator_memory_writer")
    cancel = getattr(writer, "cancel_active_run", None)
    if cancel is None:
        return
    try:
        await cancel()
    except Exception:  # noqa: BLE001
        return


async def interrupt_orchestrator_run(config: dict[str, Any] | None) -> None:
    if not config:
        return
    writer = config.get("orchestrator_memory_writer")
    interrupt = getattr(writer, "interrupt_active_run", None)
    if interrupt is None:
        return
    try:
        await interrupt()
    except Exception:  # noqa: BLE001
        return
