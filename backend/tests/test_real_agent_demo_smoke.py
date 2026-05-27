"""Fake real-agent demo smoke for B2-20 final wiring."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.agents.base import BaseAgentAdapter
from app.agents.external.claude_code import ClaudeCodeAdapter
from app.agents.external.codex import CodexAdapter
from app.agents.external.opencode import OpenCodeAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message

pytestmark = pytest.mark.asyncio(loop_scope="module")

LIVE_RUNTIME_PROVIDERS = ("claude_code", "codex", "opencode")
LIVE_RUNTIME_TIMEOUT_SECONDS = 60.0


@pytest_asyncio.fixture(scope="module")
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'demo-smoke-%'"))
        await db.commit()
    await engine.dispose()


@pytest.fixture(autouse=True)
def workspace_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=cast(Any, app))
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


class FakeRuntimeAdapter(BaseAgentAdapter):
    provider = "claude_code"

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, tool_specs
        assert workspace_path is not None
        html = "<html><body><h1>Hello AgentHub</h1></body></html>"
        (workspace_path / "hello.html").write_text(html, encoding="utf-8")
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(
            event_type="tool_call",
            call_id="c-1",
            tool_name="write_file",
            tool_arguments={"path": "hello.html", "content": html},
        )
        yield StreamChunk(
            event_type="tool_result",
            call_id="c-1",
            tool_status="ok",
            tool_output="wrote hello.html",
        )
        yield StreamChunk(event_type="done", agent_id=self.agent_id)


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"demo_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_orchestrator_agent(agent_id: str) -> None:
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name="Orchestrator",
                provider="builtin",
                avatar_url="/avatars/orchestrator.png",
                capabilities=["task_decomposition", "coordination"],
                config={"model_backend": "claude"},
                is_builtin=True,
            )
        )
        await db.commit()


async def _stored_message(agent_message_id: str) -> Message:
    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
    assert message is not None
    return message


async def test_fake_real_agent_demo_smoke_writes_hello_html(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    ensure_tables: None,
) -> None:
    _ = ensure_tables
    orchestrator_agent_id = f"demo-smoke-orchestrator-{uuid4().hex}"
    await _insert_orchestrator_agent(orchestrator_agent_id)
    _, headers = await _register(client)
    conversation_response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Demo smoke", "mode": "single", "agent_ids": [orchestrator_agent_id]},
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation = conversation_response.json()
    message_response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "generate hello.html"}]},
    )
    assert message_response.status_code == 201, message_response.text
    agent_message_id = message_response.json()["agent_message"]["id"]

    async def fake_get_adapter(agent_id: str, db: Any) -> OrchestratorAdapter:
        _ = db
        assert agent_id == orchestrator_agent_id
        return OrchestratorAdapter(
            agent_id=orchestrator_agent_id,
            default_config={
                "tasks": [
                    {
                        "task_id": "demo",
                        "agent_id": "claude-code",
                        "title": "Generate hello.html",
                        "instruction": "Generate hello.html in the workspace.",
                    }
                ],
                "sub_adapters": {"claude-code": FakeRuntimeAdapter(agent_id="claude-code")},
            },
        )

    monkeypatch.setattr("app.api.v1.stream.get_adapter", fake_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        body = (await response.aread()).decode()

    file_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/hello.html",
        headers=headers,
    )
    message = await _stored_message(agent_message_id)

    assert response.status_code == 200
    assert "event: agent_switch" in body
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert file_response.status_code == 200, file_response.text
    assert file_response.headers["content-type"].startswith("text/html")
    assert b"Hello AgentHub" in file_response.content
    assert message.status == "done"
    tool_blocks = [block for block in message.content if block.get("type") == "tool_call"]
    assert tool_blocks == [
        {
            "type": "tool_call",
            "call_id": "demo.c-1",
            "tool_name": "write_file",
            "arguments": {
                "path": "hello.html",
                "content": "<html><body><h1>Hello AgentHub</h1></body></html>",
            },
            "status": "ok",
            "output_preview": "wrote hello.html",
            "output_truncated": False,
        }
    ]


@pytest.mark.slow
@pytest.mark.parametrize("provider", LIVE_RUNTIME_PROVIDERS)
async def test_live_runtime_smoke_is_opt_in(provider: str, tmp_path: Path) -> None:
    if os.getenv("AGENTHUB_RUN_LIVE_RUNTIME_TESTS") != "1":
        pytest.skip("set AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1 to run live runtime smoke")

    selected_providers = _selected_live_runtime_providers()
    if provider not in selected_providers:
        pytest.skip(f"{provider} is not selected in AGENTHUB_LIVE_RUNTIME_PROVIDERS")

    adapter, config = _live_runtime_adapter(provider)
    chunks = await _collect_live_runtime_chunks(adapter, tmp_path / provider, config)

    assert chunks[0].event_type == "start"
    assert chunks[-1].event_type == "done"
    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert any(chunk.text_delta for chunk in chunks)


def _selected_live_runtime_providers() -> set[str]:
    raw = os.getenv("AGENTHUB_LIVE_RUNTIME_PROVIDERS")
    if not raw:
        return set(LIVE_RUNTIME_PROVIDERS)

    providers = {provider.strip() for provider in raw.split(",") if provider.strip()}
    unknown = providers.difference(LIVE_RUNTIME_PROVIDERS)
    if unknown:
        raise ValueError(f"Unknown live runtime provider(s): {sorted(unknown)}")
    return providers


def _live_runtime_adapter(provider: str) -> tuple[BaseAgentAdapter, dict[str, Any]]:
    if provider == "claude_code":
        return ClaudeCodeAdapter(agent_id="claude-code-live"), {}
    if provider == "codex":
        return CodexAdapter(agent_id="codex-live"), {"timeout_seconds": 30}
    if provider == "opencode":
        command = os.getenv("AGENTHUB_OPENCODE_COMMAND", "opencode")
        command_parts = shlex.split(command, posix=os.name != "nt")
        if not command_parts or shutil.which(command_parts[0]) is None:
            pytest.skip("OpenCode CLI is not installed")

        args = shlex.split(os.getenv("AGENTHUB_OPENCODE_ARGS", ""), posix=os.name != "nt")
        return OpenCodeAdapter(agent_id="opencode-live"), {
            "command": command_parts,
            "args": args,
            "timeout_seconds": 30,
        }
    raise ValueError(f"Unknown live runtime provider: {provider}")


async def _collect_live_runtime_chunks(
    adapter: BaseAgentAdapter,
    workspace_path: Path,
    config: dict[str, Any],
) -> list[StreamChunk]:
    workspace_path.mkdir(parents=True, exist_ok=True)
    messages = [
        ChatMessage(
            role="user",
            content="Reply with a short AgentHub live runtime smoke confirmation.",
        )
    ]
    async with asyncio.timeout(LIVE_RUNTIME_TIMEOUT_SECONDS):
        return [
            chunk
            async for chunk in adapter.stream(
                messages,
                config=config,
                workspace_path=workspace_path,
            )
        ]
