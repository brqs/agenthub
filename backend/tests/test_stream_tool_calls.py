"""Tests for SSE tool_call/tool_result persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.agents.types import StreamChunk
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


async def _send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "please use a tool"}]},
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
            "call_id": "c-1",
            "tool_name": "write_file",
            "arguments": {"path": "src/App.tsx", "content": "hello"},
            "status": "ok",
            "output_preview": "wrote 5 bytes",
            "output_truncated": False,
        }
    ]


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
    assert message.content == []


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


async def test_openapi_includes_tool_call_block(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert "ToolCallBlock" in schemas
    type_schema = schemas["ToolCallBlock"]["properties"]["type"]
    assert type_schema.get("const") == "tool_call" or type_schema.get("enum") == [
        "tool_call"
    ]
