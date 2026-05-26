"""B1 P4 workspace edit-flow and AgentRegistry v2 contract tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.agents.types import StreamChunk
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message
from app.models.workspace import Workspace

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'edit-flow-agent-%'"))
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
    username = f"edit_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"edit-flow-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name="Workspace Edit Flow Agent",
                provider="mock",
                avatar_url="/avatars/edit-flow.png",
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
            "title": "Workspace edit flow",
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
    text: str = "continue from the edited workspace file",
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": [{"type": "text", "text": text}]},
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


async def test_monaco_edit_roundtrip_then_agent_reads_updated_file(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    initial_content = b"export const marker = 'INITIAL_VERSION';\n"
    edited_content = b"export const marker = 'MONACO_EDITED_VERSION';\n"

    initial_put = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
        headers=headers,
        content=initial_content,
    )
    edit_put = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
        headers=headers,
        content=edited_content,
    )
    read_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
        headers=headers,
    )
    tree_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/tree",
        headers=headers,
    )
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    class RegistryV2StyleAdapter:
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
            assert tool_specs is None
            current_file = (workspace_path / "src" / "App.tsx").read_text(
                encoding="utf-8"
            )
            assert "MONACO_EDITED_VERSION" in current_file

            yield StreamChunk(event_type="start")
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta=f"Agent saw workspace marker: {current_file.strip()}",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> RegistryV2StyleAdapter:
        return RegistryV2StyleAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert initial_put.status_code == 204, initial_put.text
    assert edit_put.status_code == 204, edit_put.text
    assert read_response.status_code == 200, read_response.text
    assert read_response.content == edited_content
    assert "INITIAL_VERSION" not in read_response.text
    assert tree_response.status_code == 200, tree_response.text
    src_node = next(
        child
        for child in tree_response.json()["tree"]["children"]
        if child["name"] == "src"
    )
    assert any(child["name"] == "App.tsx" for child in src_node["children"])

    assert status_code == 200
    assert "event: done" in body
    assert "MONACO_EDITED_VERSION" in body
    assert message.status == "done"
    assert message.content[0]["type"] == "text"
    assert "MONACO_EDITED_VERSION" in message.content[0]["text"]


async def test_put_overwrite_keeps_workspace_idempotent(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    for content in [b"one", b"two", b"three"]:
        response = await client.put(
            f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
            headers=headers,
            content=content,
        )
        assert response.status_code == 204, response.text

    read_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
        headers=headers,
    )
    async with SessionFactory() as db:
        workspaces = (
            await db.execute(
                select(Workspace).where(
                    Workspace.conversation_id == UUID(conversation["id"])
                )
            )
        ).scalars().all()

    assert read_response.status_code == 200, read_response.text
    assert read_response.content == b"three"
    assert len(workspaces) == 1


async def test_stream_accepts_registry_v2_style_adapter(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]
    seen: dict[str, Any] = {}

    class RegistryV2StyleAdapter:
        async def stream(
            self,
            messages: list[Any],
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
        ) -> AsyncIterator[StreamChunk]:
            seen["messages"] = messages
            seen["workspace_path"] = workspace_path
            seen["tool_specs"] = tool_specs
            yield StreamChunk(event_type="start")
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="Registry v2 compatible adapter streamed successfully.",
            )
            yield StreamChunk(event_type="block_end", block_index=0)
            yield StreamChunk(event_type="done")

    async def mock_get_adapter(agent_id: str, db: Any) -> RegistryV2StyleAdapter:
        return RegistryV2StyleAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

    status_code, body = await _stream_message(client, headers, agent_message_id)
    message = await _stored_message(agent_message_id)

    assert status_code == 200
    assert "event: done" in body
    assert seen["messages"]
    assert seen["workspace_path"] == Path(settings.workspace_base_dir) / conversation["id"]
    assert seen["workspace_path"].exists()
    assert seen["tool_specs"] is None
    assert message.status == "done"
    assert "Registry v2 compatible" in message.content[0]["text"]


async def test_edited_html_artifact_keeps_security_headers(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    initial_put = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/index.html",
        headers=headers,
        content=b"<h1>Initial</h1>",
    )
    edited_put = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/index.html",
        headers=headers,
        content=b"<h1>Edited in Monaco</h1>",
    )
    response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/index.html",
        headers=headers,
    )

    assert initial_put.status_code == 204, initial_put.text
    assert edited_put.status_code == 204, edited_put.text
    assert response.status_code == 200, response.text
    assert response.content == b"<h1>Edited in Monaco</h1>"
    assert response.headers["content-type"].startswith("text/html")
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["x-content-type-options"] == "nosniff"
