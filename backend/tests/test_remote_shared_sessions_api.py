"""Remote backend shared-session API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'remote-shared-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": f"remote_shared_{uuid4().hex[:16]}",
            "password": "P@ssw0rd!",
            "device_name": "Windows desktop",
            "platform": "desktop",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _create_conversation(client: AsyncClient, headers: dict[str, str]) -> str:
    agent_id = f"remote-shared-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                user_id=None,
                name="Remote Shared Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                system_prompt=None,
                config={},
                is_builtin=True,
            )
        )
        await db.commit()
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Shared conversation", "mode": "single", "agent_ids": [agent_id]},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_refresh_token_rotation_and_device_session_listing(client: AsyncClient) -> None:
    body, headers = await _register(client)
    assert body["refresh_token"]
    assert body["session"]["platform"] == "desktop"

    sessions = await client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions.status_code == 200, sessions.text
    assert sessions.json()["items"][0]["is_current"] is True

    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"] != body["refresh_token"]

    reused = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert reused.status_code == 401

    logout = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert logout.status_code == 204


async def test_read_only_share_filters_internal_blocks_by_default(client: AsyncClient) -> None:
    _body, headers = await _register(client)
    conversation_id = await _create_conversation(client, headers)
    async with SessionFactory() as db:
        db.add(
            Message(
                conversation_id=UUID(conversation_id),
                role="agent",
                agent_id="orchestrator",
                status="done",
                content=[
                    {"type": "text", "text": "公开摘要"},
                    {"type": "tool_call", "tool_name": "bash", "call_id": "secret", "status": "ok"},
                    {
                        "type": "file",
                        "filename": "secret.zip",
                        "url": "/api/v1/uploads/secret/download",
                        "size": 123,
                        "mime_type": "application/zip",
                    },
                ],
            )
        )
        await db.commit()

    created = await client.post(
        f"/api/v1/conversations/{conversation_id}/shares",
        headers=headers,
        json={"include_artifacts": False},
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]

    public = await client.get(f"/api/v1/conversation-shares/{token}")
    assert public.status_code == 200, public.text
    blocks = public.json()["messages"][0]["content"]
    assert [block["type"] for block in blocks] == ["text"]
    assert blocks[0]["text"] == "公开摘要"


async def test_local_runtime_connector_is_disabled_for_hosted_backend(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _body, headers = await _register(client)
    monkeypatch.setattr(settings, "agenthub_deployment_mode", "hosted")

    status_response = await client.get("/api/v1/local-runtime-connectors/status", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["enabled"] is False

    register = await client.post(
        "/api/v1/local-runtime-connectors/register",
        headers=headers,
        json={
            "name": "Desktop",
            "endpoint_url": "http://127.0.0.1:49100",
            "bearer_token": "local-connector-token-123456",
            "runtime_ids": ["claude-code"],
        },
    )
    assert register.status_code == 403
