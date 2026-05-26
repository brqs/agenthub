"""B1 workspace artifact end-to-end contract tests."""

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
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'artifact-e2e-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest.fixture(autouse=True)
def workspace_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 1024 * 1024)


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"artifact_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"artifact-e2e-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name="Artifact E2E Agent",
                provider="mock",
                avatar_url="/avatars/artifact.png",
                capabilities=["workspace", "artifact"],
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
            "title": "Workspace artifact E2E",
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
        json={"content": [{"type": "text", "text": "build a hello html page"}]},
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


async def test_fake_agent_writes_html_artifact_end_to_end(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]
    html = b"<!doctype html><html><body><h1>Hello AgentHub</h1></body></html>"

    class FakeArtifactAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            assert workspace_path is not None
            artifact_path = workspace_path / "hello.html"
            artifact_path.write_bytes(html)

            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-write-html",
                tool_name="write_file",
                tool_arguments={
                    "path": "hello.html",
                    "content": html.decode(),
                },
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="c-write-html",
                tool_status="ok",
                tool_output="wrote hello.html",
            )
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="Created hello.html in the workspace.",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeArtifactAdapter:
        return FakeArtifactAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)
    tree_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/tree",
        headers=headers,
    )
    file_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/hello.html",
        headers=headers,
    )

    assert status_code == 200
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert "event: done" in body

    assert message.status == "done"
    assert [block["type"] for block in message.content] == ["tool_call", "text"]
    assert message.content[0]["tool_name"] == "write_file"
    assert message.content[0]["status"] == "ok"
    assert "Created hello.html" in message.content[1]["text"]

    assert tree_response.status_code == 200, tree_response.text
    assert any(
        child["name"] == "hello.html"
        for child in tree_response.json()["tree"]["children"]
    )

    assert file_response.status_code == 200, file_response.text
    assert file_response.content == html
    assert file_response.headers["content-type"].startswith("text/html")
    assert "sandbox" in file_response.headers["content-security-policy"]
    assert file_response.headers["x-frame-options"] == "SAMEORIGIN"
    assert file_response.headers["x-content-type-options"] == "nosniff"


async def test_fake_agent_workspace_violation_e2e(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class FakeFailingArtifactAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            assert workspace_path is not None
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="tool_call",
                call_id="c-escape",
                tool_name="write_file",
                tool_arguments={"path": "../escape.html"},
            )
            yield StreamChunk(
                event_type="tool_result",
                call_id="c-escape",
                tool_status="error",
                tool_output="path traversal is not allowed: ../escape.html",
                error_code="workspace_violation",
            )
            yield StreamChunk(
                event_type="error",
                error_code="workspace_violation",
                error="path traversal is not allowed: ../escape.html",
            )

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeFailingArtifactAdapter:
        return FakeFailingArtifactAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)
    escaped_path = Path(settings.workspace_base_dir) / "escape.html"

    assert status_code == 200
    assert "workspace_violation" in body
    assert message.status == "error"
    assert message.content[0]["type"] == "tool_call"
    assert message.content[0]["status"] == "error"
    assert message.content[0]["error_code"] == "workspace_violation"
    assert not escaped_path.exists()
