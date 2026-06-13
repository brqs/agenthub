"""Tests for SSE tool_call/tool_result persistence."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import app.api.v1.stream as stream_module
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'tool-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest.fixture(autouse=True)
def workspace_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"tool_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"tool-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name="Tool Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                config={},
                is_builtin=True,
            )
        )
        await db.commit()
    return agent_id


async def _ensure_orchestrator_group_agents() -> None:
    specs = [
        {
            "id": "orchestrator",
            "name": "Orchestrator",
            "provider": "builtin",
            "avatar_url": "/avatars/orchestrator.png",
            "capabilities": ["task_decomposition", "coordination"],
            "config": {
                "model_backend": "claude",
                "answer_model_backend": "deepseek",
                "planner_model_backend": "claude",
                "managed_agent_ids": [
                    "claude-code",
                    "codex-helper",
                    "opencode-helper",
                ],
            },
        },
        {
            "id": "claude-code",
            "name": "Claude Code",
            "provider": "claude_code",
            "avatar_url": "/avatars/claude.png",
            "capabilities": ["coding", "files", "analysis"],
            "config": {"api_key": "should-not-leak", "env": {"TOKEN": "hidden"}},
        },
        {
            "id": "codex-helper",
            "name": "Codex Helper",
            "provider": "codex",
            "avatar_url": "/avatars/openai.png",
            "capabilities": ["coding", "sandbox"],
            "config": {
                "runtime": "cli",
                "qa_model_backend": "deepseek",
                "qa_model": "deepseek-chat",
                "cli_args": ["--secret", "hidden"],
            },
        },
        {
            "id": "opencode-helper",
            "name": "OpenCode Helper",
            "provider": "opencode",
            "avatar_url": "/avatars/opencode.png",
            "capabilities": ["coding", "cli", "files"],
            "config": {"sdk_options": {"token": "hidden"}},
        },
    ]
    async with SessionFactory() as db:
        for spec in specs:
            agent = await db.get(Agent, spec["id"])
            if agent is None:
                db.add(Agent(**spec, is_builtin=True))
                continue
            agent.name = spec["name"]
            agent.provider = spec["provider"]
            agent.avatar_url = spec["avatar_url"]
            agent.capabilities = spec["capabilities"]
            agent.config = spec["config"]
            agent.is_builtin = True
        await db.commit()


async def _create_conversation(
    client: AsyncClient,
    headers: dict[str, str],
) -> dict[str, Any]:
    agent_id = await _insert_agent()
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Tool stream test",
            "mode": "single",
            "agent_ids": [agent_id],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_group_conversation(
    client: AsyncClient,
    headers: dict[str, str],
    agent_ids: list[str],
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Group memory stream test",
            "mode": "group",
            "agent_ids": agent_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    *,
    target_agent_id: str | None = None,
    text: str = "please use a tool",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if target_agent_id is not None:
        payload["target_agent_id"] = target_agent_id
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _stream_message(
    client: AsyncClient,
    headers: dict[str, str],
    agent_message_id: str,
) -> tuple[int, str]:
    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        body = (await response.aread()).decode()
    return response.status_code, body


async def _stored_message(agent_message_id: str) -> Message:
    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
    assert message is not None
    return message


async def test_stream_chunk_tool_events_to_sse() -> None:
    call = StreamChunk(
        event_type="tool_call",
        call_id="c-1",
        tool_name="write_file",
        tool_arguments={"path": "App.tsx"},
    )
    result = StreamChunk(
        event_type="tool_result",
        call_id="c-1",
        tool_status="ok",
        tool_output="wrote file",
    )

    assert call.to_sse()["event"] == "tool_call"
    assert result.to_sse()["event"] == "tool_result"
    assert '"tool_name":"write_file"' in call.to_sse()["data"]
    assert '"tool_status":"ok"' in result.to_sse()["data"]


async def test_stream_persists_tool_call_block_ok(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "src/App.tsx", "content": "hello"},
                agent_id="claude-code",
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="ok",
                tool_output="wrote 5 bytes",
            )
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert message.status == "done"
    assert message.content == [
        {
            "type": "tool_call",
            "agent_id": "claude-code",
            "call_id": "c-1",
            "tool_name": "write_file",
            "arguments": {"path": "src/App.tsx", "content": "hello"},
            "status": "ok",
            "output_preview": "wrote 5 bytes",
            "output_truncated": False,
        }
    ]


async def test_stream_orchestrator_group_agents_uses_conversation_members(
    client: AsyncClient,
) -> None:
    await _ensure_orchestrator_group_agents()
    _, headers = await _register(client)
    conversation_response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Orchestrator group members",
            "mode": "group",
            "agent_ids": [
                "orchestrator",
                "claude-code",
                "codex-helper",
                "opencode-helper",
            ],
        },
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation = conversation_response.json()
    message_response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "@orchestrator 当前群聊有哪些 agent"}],
            "target_agent_id": "orchestrator",
        },
    )
    assert message_response.status_code == 201, message_response.text
    agent_message_id = message_response.json()["agent_message"]["id"]

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)
    text = "\n".join(
        block.get("text", "") for block in message.content if block.get("type") == "text"
    )

    assert status_code == 200
    assert "event: delta" in body
    assert message.status == "done"
    assert "当前群聊包含 4 个 agent" in text
    assert "Orchestrator" in text
    assert "Claude Code" in text
    assert "Codex Helper" in text
    assert "OpenCode Helper" in text
    assert "Planner" not in text
    assert "Specialist Agents" not in text


async def test_stream_orchestrator_group_models_uses_safe_agent_context(
    client: AsyncClient,
) -> None:
    await _ensure_orchestrator_group_agents()
    _, headers = await _register(client)
    conversation_response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Orchestrator group models",
            "mode": "group",
            "agent_ids": [
                "orchestrator",
                "claude-code",
                "codex-helper",
                "opencode-helper",
            ],
        },
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation = conversation_response.json()
    message_response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "@orchestrator 当前群聊有哪些模型"}],
            "target_agent_id": "orchestrator",
        },
    )
    assert message_response.status_code == 201, message_response.text
    agent_message_id = message_response.json()["agent_message"]["id"]

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)
    text = "\n".join(
        block.get("text", "") for block in message.content if block.get("type") == "text"
    )

    assert status_code == 200
    assert "event: delta" in body
    assert message.status == "done"
    assert "可见的模型/运行时配置" in text
    assert "Orchestrator" in text
    assert "answer_model_backend: deepseek" in text
    assert "planner_model_backend: claude" in text
    assert "Claude Code" in text
    assert "执行模型: 未在 AgentHub 配置中暴露" in text
    assert "Codex Helper" in text
    assert "runtime: cli" in text
    assert "qa_model_backend: deepseek" in text
    assert "qa_model: deepseek-chat" in text
    assert "OpenCode Helper" in text
    assert "api_key" not in text
    assert "should-not-leak" not in text
    assert "TOKEN" not in text
    assert "cli_args" not in text
    assert "sdk_options" not in text
    assert "GPT-4" not in text
    assert "Gemini" not in text
    assert "Llama" not in text
    assert "Mistral" not in text


async def test_stream_orchestrator_combined_group_agents_and_self_model(
    client: AsyncClient,
) -> None:
    await _ensure_orchestrator_group_agents()
    _, headers = await _register(client)
    conversation_response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Orchestrator combined platform facts",
            "mode": "group",
            "agent_ids": [
                "orchestrator",
                "claude-code",
                "codex-helper",
                "opencode-helper",
            ],
        },
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation = conversation_response.json()
    message_response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={
            "content": [
                {
                    "type": "text",
                    "text": "@orchestrator 当前群聊有哪些agent，你又是什么模型",
                }
            ],
            "target_agent_id": "orchestrator",
        },
    )
    assert message_response.status_code == 201, message_response.text
    agent_message_id = message_response.json()["agent_message"]["id"]

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)
    text = "\n".join(
        block.get("text", "") for block in message.content if block.get("type") == "text"
    )

    assert status_code == 200
    assert "event: delta" in body
    assert message.status == "done"
    assert "当前群聊包含 4 个 agent" in text
    assert "Claude Code" in text
    assert "Codex Helper" in text
    assert "OpenCode Helper" in text
    assert "我是 AgentHub Orchestrator" in text
    assert "direct answer backend: deepseek" in text
    assert "planner backend: claude" in text
    assert "可见的模型/运行时配置" not in text


async def test_stream_heartbeat_is_sse_only_not_persisted(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="heartbeat",
                agent_id="tool-agent",
                metadata={
                    "elapsed_seconds": 15,
                    "idle_seconds": 15,
                    "max_runtime_seconds": 600,
                    "idle_timeout_seconds": 180,
                },
            )
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert "event: heartbeat" in body
    assert message.status == "done"
    assert message.content == []


async def test_group_stream_passes_shared_memory_with_agent_labels(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    agent_a = await _insert_agent()
    agent_b = await _insert_agent()
    conversation = await _create_group_conversation(client, headers, [agent_a, agent_b])
    captured: dict[str, list[Any]] = {}

    class FakeAdapter:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id

        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            _ = system_prompt, config, workspace_path, tool_specs
            captured[self.agent_id] = messages
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta=f"{self.agent_id} stored AgentHub detail",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter(agent_id)

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    first = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id=agent_a,
        text="Remember: AgentHub backend uses FastAPI.",
    )
    status_code, _ = await _stream_message(
        client,
        headers,
        first["agent_message"]["id"],
    )
    assert status_code == 200

    second = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id=agent_b,
        text="What did the first agent say?",
    )
    status_code, _ = await _stream_message(
        client,
        headers,
        second["agent_message"]["id"],
    )

    assert status_code == 200
    joined = "\n".join(message.content for message in captured[agent_b])
    assert f"You are Agent: {agent_b}" in joined
    assert "observing a group conversation" in joined
    assert "not your own statements" in joined
    assert f"[Agent: {agent_a}]" in joined
    assert f"{agent_a} stored AgentHub detail" in joined
    assert "What did the first agent say?" in joined


async def test_orchestrator_group_stream_keeps_observer_prompt_before_memory(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_orchestrator_group_agents()
    _, headers = await _register(client)
    conversation = await _create_group_conversation(
        client,
        headers,
        ["orchestrator", "claude-code", "codex-helper"],
    )
    captured: dict[str, Any] = {}

    async with SessionFactory() as db:
        base_time = datetime.now(UTC)
        db.add_all(
            [
                Message(
                    conversation_id=UUID(conversation["id"]),
                    role="user",
                    content=[{"type": "text", "text": "Please compare prior work."}],
                    status="done",
                    created_at=base_time,
                ),
                Message(
                    conversation_id=UUID(conversation["id"]),
                    role="agent",
                    agent_id="claude-code",
                    content=[
                        {
                            "type": "text",
                            "text": "Claude prepared the FastAPI route contract.",
                        }
                    ],
                    status="done",
                    created_at=base_time + timedelta(seconds=1),
                ),
            ]
        )
        await db.commit()

    class FakeOrchestratorAdapter(BaseAgentAdapter):
        provider = "fake"

        def __init__(self) -> None:
            super().__init__(agent_id="orchestrator")

        async def stream(
            self,
            messages: list[ChatMessage],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            captured["messages"] = messages
            captured["config"] = config
            _ = system_prompt, workspace_path, tool_specs
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="orchestrator saw observer context",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeOrchestratorAdapter:
        assert agent_id == "orchestrator"
        return FakeOrchestratorAdapter()

    async def fake_memory_context(
        db: Any,
        conversation_id: UUID,
        *,
        recent_runs: int,
        max_chars: int,
    ) -> ChatMessage:
        _ = db, conversation_id, recent_runs, max_chars
        return ChatMessage(
            role="system",
            content="Previous Orchestrator structured memory:\n- task-a @claude-code succeeded",
        )

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)
    monkeypatch.setattr(
        "app.api.v1.stream_orchestrator_context.build_orchestrator_memory_context",
        fake_memory_context,
    )

    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id="orchestrator",
        text="@orchestrator continue from Claude's prior work",
    )
    status_code, _ = await _stream_message(
        client,
        headers,
        messages["agent_message"]["id"],
    )

    assert status_code == 200
    received = captured["messages"]
    contents = [message.content for message in received]
    assert received[0].role == "system"
    assert "You are Agent: orchestrator" in received[0].content
    assert "observing a group conversation" in received[0].content
    assert "not your own statements" in received[0].content
    memory_index = contents.index(
        "Previous Orchestrator structured memory:\n- task-a @claude-code succeeded"
    )
    latest_user_index = contents.index("@orchestrator continue from Claude's prior work")
    assert 0 < memory_index < latest_user_index
    joined = "\n".join(contents)
    assert "[Agent: claude-code]\nClaude prepared the FastAPI route contract." in joined
    assert captured["config"]["orchestrator_platform_tool_executor"] is not None


async def test_orchestrator_context_skips_unauthenticated_claude_code(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_orchestrator_group_agents()
    _, headers = await _register(client)
    conversation = await _create_group_conversation(
        client,
        headers,
        ["orchestrator", "claude-code"],
    )
    captured: dict[str, Any] = {}

    class FakeOrchestratorAdapter(BaseAgentAdapter):
        provider = "fake"

        def __init__(self) -> None:
            super().__init__(agent_id="orchestrator")

        async def stream(
            self,
            messages: list[ChatMessage],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            captured["config"] = config
            _ = messages, system_prompt, workspace_path, tool_specs
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=0)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeOrchestratorAdapter:
        _ = db
        assert agent_id == "orchestrator"
        return FakeOrchestratorAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)
    monkeypatch.setattr(
        "app.api.v1.stream_orchestrator_context.claude_code_runtime_status",
        lambda _config=None: ("unavailable", "Claude Code runtime is not authenticated"),
    )

    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id="orchestrator",
        text="@orchestrator build a page",
    )
    status_code, _ = await _stream_message(
        client,
        headers,
        messages["agent_message"]["id"],
    )

    assert status_code == 200
    assert captured["config"]["available_agents"] == []
    assert captured["config"]["managed_agent_ids"] == []
    assert captured["config"]["planning_agent_ids"] == []
    assert captured["config"]["available_agents_authoritative"] is True
    assert captured["config"]["conversation_scoped_agents"] is True
    claude_context = captured["config"]["conversation_agents"][1]
    assert claude_context["id"] == "claude-code"
    assert claude_context["runtime_available"] is False
    assert claude_context["runtime_status"] == "unavailable"


async def test_orchestrator_group_scope_overrides_global_default_sub_agents(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_orchestrator_group_agents()
    _, headers = await _register(client)
    conversation = await _create_group_conversation(
        client,
        headers,
        ["orchestrator", "claude-code", "codex-helper"],
    )
    captured: dict[str, Any] = {}

    class FakeOrchestratorAdapter(BaseAgentAdapter):
        provider = "fake"

        def __init__(self) -> None:
            super().__init__(
                agent_id="orchestrator",
                default_config={
                    "available_agents_authoritative": False,
                    "managed_agent_ids": [
                        "claude-code",
                        "opencode-helper",
                        "codex-helper",
                    ],
                },
            )

        async def stream(
            self,
            messages: list[ChatMessage],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            captured["config"] = config
            _ = messages, system_prompt, workspace_path, tool_specs
            yield StreamChunk(event_type="start", agent_id=self.agent_id)
            yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=0)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeOrchestratorAdapter:
        _ = db
        assert agent_id == "orchestrator"
        return FakeOrchestratorAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        target_agent_id="orchestrator",
        text="@orchestrator build a page",
    )
    status_code, _ = await _stream_message(
        client,
        headers,
        messages["agent_message"]["id"],
    )

    assert status_code == 200
    assert captured["config"]["available_agents_authoritative"] is True
    assert captured["config"]["conversation_scoped_agents"] is True
    assert captured["config"]["managed_agent_ids"] == [
        "claude-code",
        "codex-helper",
    ]
    assert [
        agent["id"] for agent in captured["config"]["available_agents"]
    ] == ["claude-code", "codex-helper"]
    assert all(
        agent["id"] != "opencode-helper"
        for agent in captured["config"]["conversation_agents"]
    )


async def test_stream_persists_tool_call_block_error(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "../escape.txt"},
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="error",
                tool_output="path escapes workspace",
                error_code="workspace_violation",
            )
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, _ = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert message.status == "done"
    assert message.content[0]["status"] == "error"
    assert message.content[0]["error_code"] == "workspace_violation"
    assert message.content[0]["output_preview"] == "path escapes workspace"


async def test_stream_persists_tool_result_error_code_from_metadata(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="bash",
                tool_arguments={"command": "cat ../outside.txt"},
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="error",
                tool_output="bash path escapes workspace",
                metadata={"error_code": "workspace_violation"},
            )
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, _ = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert message.content[0]["status"] == "error"
    assert message.content[0]["error_code"] == "workspace_violation"


async def test_stream_truncates_tool_output_and_arguments(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]
    long_text = "x" * 3000

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "huge.txt", "content": long_text},
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="ok",
                tool_output=long_text,
            )
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, _ = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)
    block = message.content[0]

    assert status_code == 200
    assert len(block["output_preview"]) == 2048
    assert block["output_truncated"] is True
    assert len(block["arguments"]["content"]) < len(long_text)
    assert block["arguments"]["content"].endswith("...[truncated]")


async def test_stream_tool_result_without_call_marks_error(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_result",
                call_id="missing",
                tool_status="ok",
                tool_output="orphan",
            )

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert "tool_call_orphan" in body
    assert message.status == "error"
    assert message.content == [
        {
            "type": "text",
            "text": "tool_call_orphan: tool_result without matching tool_call: missing",
        }
    ]


async def test_stream_pending_tool_call_marks_message_error(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "App.tsx"},
            )
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, _ = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert message.status == "error"
    assert message.content[0]["status"] == "error"
    assert message.content[0]["error_code"] == "tool_call_orphan"


async def test_stream_passes_workspace_path_to_adapter(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]
    seen_workspace_path: Path | None = None

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            nonlocal seen_workspace_path
            seen_workspace_path = workspace_path
            yield StreamChunk(event_type="start")
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, _ = await _stream_message(client, headers, agent_message_id)

    assert status_code == 200
    assert seen_workspace_path is not None
    assert seen_workspace_path == Path(settings.workspace_base_dir) / conversation["id"]
    assert seen_workspace_path.exists()


async def test_stream_rejects_non_pending_agent_message(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
        assert message is not None
        message.status = "done"
        await db.commit()

    status_code, body = await _stream_message(client, headers, agent_message_id)

    assert status_code == 409
    assert "MESSAGE_NOT_STREAMABLE" in body


async def test_streaming_message_without_runtime_session_stays_recoverable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stream_module, "ORPHANED_STREAM_RECOVERY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(stream_module, "ORPHANED_STREAM_RECOVERY_POLL_SECONDS", 0.001)

    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
        assert message is not None
        message.status = "streaming"
        await db.commit()

    status_code, body = await _stream_message(client, headers, agent_message_id)

    assert status_code == 200
    assert "stream_session_lost" not in body
    assert "Agent stream was interrupted before completion" not in body
    message = await _stored_message(agent_message_id)
    assert message.status == "streaming"
    assert message.content == []


async def test_streaming_message_without_runtime_session_recovers_done(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stream_module, "ORPHANED_STREAM_RECOVERY_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(stream_module, "ORPHANED_STREAM_RECOVERY_POLL_SECONDS", 0.01)

    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
        assert message is not None
        message.status = "streaming"
        message.content = []
        await db.commit()

    request_task = asyncio.create_task(_stream_message(client, headers, agent_message_id))
    await asyncio.sleep(0.05)

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
        assert message is not None
        message.status = "done"
        message.content = [{"type": "text", "text": "finished"}]
        await db.commit()

    status_code, body = await asyncio.wait_for(request_task, timeout=2)

    assert status_code == 200
    assert "event: done" in body
    assert "stream_session_lost" not in body
    assert "Agent stream was interrupted before completion" not in body
    message = await _stored_message(agent_message_id)
    assert message.status == "done"
    assert message.content == [{"type": "text", "text": "finished"}]


async def test_stream_passes_runtime_context_to_adapter(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]
    seen_config: dict[str, Any] | None = None

    class FakeAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            nonlocal seen_config
            _ = messages, system_prompt, workspace_path, tool_specs
            seen_config = config
            yield StreamChunk(event_type="start")
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, _ = await _stream_message(client, headers, agent_message_id)

    assert status_code == 200
    assert seen_config is not None
    assert seen_config["runtime_context"] == {
        "conversation_id": conversation["id"],
        "agent_message_id": agent_message_id,
        "agent_id": messages["agent_message"]["agent_id"],
    }


async def test_openapi_includes_tool_call_block(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert "ToolCallBlock" in schemas
    assert "WorkflowBlock" in schemas
    for schema_name in (
        "TextBlock",
        "CodeBlock",
        "DiffBlock",
        "WebPreviewBlock",
        "FileBlock",
        "DeploymentStatusBlock",
        "WorkflowBlock",
        "ToolCallBlock",
    ):
        assert schemas[schema_name]["properties"]["agent_id"] == {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "title": "Agent Id",
        }
        assert "agent_id" not in schemas[schema_name].get("required", [])
    type_schema = schemas["ToolCallBlock"]["properties"]["type"]
    assert type_schema.get("const") == "tool_call" or type_schema.get("enum") == [
        "tool_call"
    ]
