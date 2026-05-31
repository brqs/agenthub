"""Tests for Orchestrator platform-owned tools."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base, SessionFactory, engine
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.user import User
from app.services.orchestrator_platform_tools import OrchestratorPlatformToolExecutor

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


async def _conversation() -> Conversation:
    async with SessionFactory() as db:
        user = User(
            username=f"platform_tool_{uuid4().hex[:16]}",
            password_hash="hash",
        )
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="Platform tools",
            mode="group",
            agent_ids=["orchestrator"],
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation


async def test_create_custom_agent_tool_creates_agent_and_adds_to_group() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {
                "name": "Copy Agent",
                "provider": "builtin",
                "system_prompt": "You write concise product copy.",
                "capabilities": ["writing", "copy"],
                "config": {"model_backend": "claude", "mcp_servers": []},
                "add_to_conversation": True,
            },
        )
        await db.commit()

        assert result.status == "ok"
        payload = json.loads(result.output)
        agent_id = payload["agent"]["id"]
        agent = await db.get(Agent, agent_id)
        updated_conversation = await db.get(Conversation, conversation.id)

        assert agent is not None
        assert agent.user_id == conversation.user_id
        assert agent.provider == "builtin"
        assert agent.system_prompt == "You write concise product copy."
        assert updated_conversation is not None
        assert agent_id in updated_conversation.agent_ids


async def test_create_custom_agent_tool_requires_key_fields() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {"name": "Incomplete Agent", "provider": "builtin"},
        )

        assert result.status == "error"
        assert result.error_code == "missing_required_agent_fields"
        assert result.needs_user_input is True
        assert json.loads(result.output)["missing_fields"] == ["system_prompt"]


async def test_create_custom_agent_tool_rejects_invalid_provider() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {
                "name": "Legacy Agent",
                "provider": "custom",
                "system_prompt": "nope",
            },
        )

        assert result.status == "error"
        assert result.error_code == "invalid_provider"


async def test_create_custom_agent_tool_rejects_invalid_config() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {
                "name": "Bad Agent",
                "provider": "builtin",
                "system_prompt": "bad config",
                "config": {"model_backend": "local"},
            },
        )

        assert result.status == "error"
        assert result.error_code == "INVALID_MODEL_BACKEND"


async def test_create_custom_agent_tool_does_not_create_on_error() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        await executor(
            "create_custom_agent",
            {"name": "No Prompt", "provider": "builtin"},
        )
        count = (
            await db.execute(
                select(Agent).where(
                    Agent.user_id == conversation.user_id,
                    Agent.name == "No Prompt",
                )
            )
        ).scalars().all()

        assert count == []
