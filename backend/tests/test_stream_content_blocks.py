"""Tests for SSE stream persistence of diff and web_preview ContentBlocks."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.agents.types import StreamChunk
from app.api.v1.stream_accumulator import StreamContentAccumulator
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_stream_accumulator_persists_deployment_status_block() -> None:
    accumulator = StreamContentAccumulator()
    accumulator.feed(
        StreamChunk(
            event_type="block_start",
            block_index=0,
            block_type="deployment_status",
            metadata={
                "deployment_id": "deployment-1",
                "kind": "static_site",
                "status": "published",
                "title": "Static site deployment",
                "url": "http://127.0.0.1:8082/index.html",
            },
        )
    )
    accumulator.feed(StreamChunk(event_type="block_end", block_index=0))

    assert accumulator.to_list() == [
        {
            "type": "deployment_status",
            "deployment_id": "deployment-1",
            "kind": "static_site",
            "status": "published",
            "title": "Static site deployment",
            "url": "http://127.0.0.1:8082/index.html",
        }
    ]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'test-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"user_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent(*, user_id: UUID | None = None, is_builtin: bool = True) -> str:
    agent_id = f"test-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                user_id=user_id,
                name="Test Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                system_prompt=None,
                config={},
                is_builtin=is_builtin,
            )
        )
        await db.commit()
    return agent_id


async def _create_conversation(
    client: AsyncClient,
    headers: dict[str, str],
    agent_ids: list[str],
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "B2 content block test", "mode": "single", "agent_ids": agent_ids},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    target_agent_id: str | None = None,
    content_text: str = "hello",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": content_text}]}
    if target_agent_id is not None:
        payload["target_agent_id"] = target_agent_id
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_stream_persists_diff_block(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
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
        ) -> AsyncIterator[Any]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="block_start",
                block_index=0,
                block_type="diff",
                metadata={"filename": "changes.diff"},
            )
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done"
    assert len(message.content) == 1
    assert message.content[0]["type"] == "diff"
    assert message.content[0]["filename"] == "app.py"
    assert "old" in message.content[0]["before"]
    assert "new" in message.content[0]["after"]


async def test_stream_persists_web_preview_block(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
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
        ) -> AsyncIterator[Any]:
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="block_start",
                block_index=0,
                block_type="web_preview",
                metadata={"url": "https://example.com"},
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done"
    assert len(message.content) == 1
    assert message.content[0]["type"] == "web_preview"
    assert message.content[0]["url"] == "https://example.com"


async def test_stream_autostarts_platform_preview_for_deploy_request(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    preview_port = _free_port()
    monkeypatch.setattr(settings, "preview_enabled", True)
    monkeypatch.setattr(settings, "preview_port_start", preview_port)
    monkeypatch.setattr(settings, "preview_port_end", preview_port)
    monkeypatch.setattr(settings, "preview_public_base_url", "http://127.0.0.1")
    monkeypatch.setattr(settings, "preview_start_timeout_seconds", 5)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        content_text=f"请生成一个网页并部署到端口{preview_port}",
    )
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
        ) -> AsyncIterator[Any]:
            assert workspace_path is not None
            (workspace_path / "index.html").write_text(
                "<!doctype html><title>Preview</title><h1>ok</h1>",
                encoding="utf-8",
            )
            yield StreamChunk(event_type="start")
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="Created index.html",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done", total_blocks=1)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        sse_text = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done", sse_text
    assert "start_workspace_preview" in sse_text
    assert any(
        block.get("type") == "tool_call"
        and block.get("tool_name") == "start_workspace_preview"
        and block.get("status") == "ok"
        for block in message.content
    )
    preview_blocks = [block for block in message.content if block.get("type") == "web_preview"]
    assert len(preview_blocks) == 1
    assert preview_blocks[0]["url"].startswith(f"http://127.0.0.1:{preview_port}/")

    preview = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["entry_path"] == "index.html"
    assert preview.json()["port"] == preview_port

    await client.delete(
        f"/api/v1/workspaces/{conversation['id']}/preview",
        headers=headers,
    )


async def test_stream_preview_fallback_skips_when_formal_tool_called(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    preview_port = _free_port()
    monkeypatch.setattr(settings, "preview_enabled", True)
    monkeypatch.setattr(settings, "preview_port_start", preview_port)
    monkeypatch.setattr(settings, "preview_port_end", preview_port)
    monkeypatch.setattr(settings, "preview_public_base_url", "http://127.0.0.1")
    monkeypatch.setattr(settings, "preview_start_timeout_seconds", 5)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(
        client,
        headers,
        conversation["id"],
        content_text=f"请生成一个网页并部署到端口{preview_port}",
    )
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
        ) -> AsyncIterator[Any]:
            assert workspace_path is not None
            (workspace_path / "index.html").write_text(
                "<!doctype html><title>Preview</title><h1>ok</h1>",
                encoding="utf-8",
            )
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="orch.quality.preview",
                tool_name="start_workspace_preview",
                tool_arguments={"entry_path": "index.html", "requested_port": preview_port},
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="orch.quality.preview",
                tool_status="ok",
                tool_output='{"status":"running","url":"http://127.0.0.1/fake"}',
            )
            yield StreamChunk(event_type="done", total_blocks=0)

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        sse_text = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert message is not None
    assert message.status == "done", sse_text
    assert sse_text.count("start_workspace_preview") == 1
    assert "platform-preview-" not in sse_text
    preview = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 404


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
