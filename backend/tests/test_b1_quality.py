"""B1 backend quality regression tests."""

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
from app.services.model_gateway import CompressionModelGateway

pytestmark = pytest.mark.asyncio(loop_scope="module")


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
        json={"title": "B1 quality test", "mode": "single", "agent_ids": agent_ids},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    target_agent_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": "hello"}]}
    if target_agent_id is not None:
        payload["target_agent_id"] = target_agent_id
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_conversation_rejects_missing_agent(client: AsyncClient) -> None:
    _, headers = await _register(client)
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "bad agent",
            "mode": "single",
            "agent_ids": ["missing-agent-id"],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "AGENT_NOT_FOUND"


async def test_create_conversation_rejects_other_users_agent(client: AsyncClient) -> None:
    owner, _ = await _register(client)
    _, other_headers = await _register(client)
    agent_id = await _insert_agent(user_id=UUID(owner["user"]["id"]), is_builtin=False)

    response = await client.post(
        "/api/v1/conversations",
        headers=other_headers,
        json={"title": "not mine", "mode": "single", "agent_ids": [agent_id]},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "AGENT_NOT_FOUND"


async def test_message_and_conversation_routes_forbid_other_user_resources(
    client: AsyncClient,
) -> None:
    _, owner_headers = await _register(client)
    _, other_headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, owner_headers, [agent_id])
    messages = await _send_message(client, owner_headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    blocked_requests = [
        client.get(f"/api/v1/conversations/{conversation['id']}", headers=other_headers),
        client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            headers=other_headers,
            json={"title": "not yours"},
        ),
        client.delete(
            f"/api/v1/conversations/{conversation['id']}",
            headers=other_headers,
        ),
        client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=other_headers,
        ),
        client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=other_headers,
            json={"content": [{"type": "text", "text": "nope"}]},
        ),
        client.patch(
            f"/api/v1/messages/{agent_message_id}",
            headers=other_headers,
            json={"is_pinned": True},
        ),
        client.delete(f"/api/v1/messages/{agent_message_id}", headers=other_headers),
        client.post(
            f"/api/v1/messages/{agent_message_id}/regenerate",
            headers=other_headers,
        ),
        client.get(f"/api/v1/messages/{agent_message_id}/stream", headers=other_headers),
    ]

    responses = [await request for request in blocked_requests]
    assert [response.status_code for response in responses] == [
        403,
        403,
        403,
        403,
        403,
        403,
        403,
        403,
        403,
    ]


async def test_send_message_rejects_agent_outside_conversation(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    outside_agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])

    response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "hello"}],
            "target_agent_id": outside_agent_id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "AGENT_NOT_FOUND"


async def test_password_over_bcrypt_limit_returns_422(client: AsyncClient) -> None:
    long_password = "a" * 73
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"username": f"user_{uuid4().hex[:16]}", "password": long_password},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": "anyone", "password": long_password},
    )

    assert register_response.status_code == 422
    assert login_response.status_code == 422


async def test_openapi_uses_http_bearer_security(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    security_schemes = response.json()["components"]["securitySchemes"]

    assert any(
        scheme.get("type") == "http" and scheme.get("scheme") == "bearer"
        for scheme in security_schemes.values()
    )
    assert all(scheme.get("type") != "oauth2" for scheme in security_schemes.values())


async def test_context_compression_config_can_be_read_and_updated(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "context_compression_mode", "hybrid")
    monkeypatch.setattr(settings, "context_compression_provider", "deepseek")
    monkeypatch.setattr(settings, "context_compression_model", "deepseek-v4-flash")
    monkeypatch.setattr(settings, "context_compression_api_key", "sk-test1234")

    read_response = await client.get(
        "/api/v1/context-compression/config",
        headers=headers,
    )
    update_response = await client.patch(
        "/api/v1/context-compression/config",
        headers=headers,
        json={"model": "deepseek-v4-pro", "summary_max_tokens": 900},
    )

    assert read_response.status_code == 200
    assert read_response.json()["provider"] == "deepseek"
    assert read_response.json()["model"] == "deepseek-v4-flash"
    assert read_response.json()["api_key_configured"] is True
    assert read_response.json()["api_key_preview"] == "sk-***1234"
    assert update_response.status_code == 200
    assert update_response.json()["model"] == "deepseek-v4-pro"
    assert update_response.json()["summary_max_tokens"] == 900


async def test_context_compression_config_rejects_unsupported_model(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    monkeypatch.setattr(settings, "environment", "development")

    response = await client.patch(
        "/api/v1/context-compression/config",
        headers=headers,
        json={"model": "deepseek-chat"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "UNSUPPORTED_COMPRESSION_MODEL"


async def test_context_compression_config_test_endpoint(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await _register(client)
    monkeypatch.setattr(settings, "environment", "development")

    async def fake_test_connection(
        self: CompressionModelGateway,
        *,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> str:
        assert provider == "openai_compatible"
        assert model == "custom-summary-model"
        assert api_key == "sk-test"
        assert base_url == "https://example.com/v1"
        return "ok"

    monkeypatch.setattr(CompressionModelGateway, "test_connection", fake_test_connection)

    response = await client.post(
        "/api/v1/context-compression/config/test",
        headers=headers,
        json={
            "provider": "openai_compatible",
            "model": "custom-summary-model",
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "openai_compatible",
        "model": "custom-summary-model",
        "error_code": None,
        "message": None,
    }


async def test_stream_success_marks_agent_message_done(client: AsyncClient) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        body = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert "event: done" in body
    assert message is not None
    assert message.status == "done"
    assert len(message.content) == 2


async def test_stream_error_marks_agent_message_error(client: AsyncClient) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"])
    agent_message_id = messages["agent_message"]["id"]

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))
        assert message is not None
        message.agent_id = "missing-agent-for-stream"
        await db.commit()

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        body = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert "event: error" in body
    assert message is not None
    assert message.status == "error"


async def test_stream_adapter_error_chunk_marks_message_error(
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
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
        ) -> AsyncIterator[Any]:
            from app.agents.types import StreamChunk

            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="block_start", block_index=0, block_type="text"
            )
            yield StreamChunk(
                event_type="delta", block_index=0, text_delta="partial"
            )
            yield StreamChunk(
                event_type="error",
                error_code="rate_limit",
                error="Rate limited",
            )

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr(
        "app.api.v1.stream.get_adapter", mock_get_adapter
    )

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        body = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert "event: error" in body
    assert "rate_limit" in body
    assert message is not None
    assert message.status == "error"
    assert len(message.content) >= 1
    assert message.content[0]["type"] == "text"
    assert message.content[0]["text"] == "partial"


async def test_stream_adapter_exception_marks_message_error_and_preserves_partial_content(
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
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
        ) -> AsyncIterator[Any]:
            from app.agents.types import StreamChunk

            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="block_start", block_index=0, block_type="text"
            )
            yield StreamChunk(
                event_type="delta", block_index=0, text_delta="partial"
            )
            raise RuntimeError("boom")

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        return FakeAdapter()

    monkeypatch.setattr(
        "app.api.v1.stream.get_adapter", mock_get_adapter
    )

    async with client.stream(
        "GET",
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    ) as response:
        body = (await response.aread()).decode()

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(agent_message_id))

    assert response.status_code == 200
    assert "event: error" in body
    assert "internal_error" in body
    assert message is not None
    assert message.status == "error"
    assert len(message.content) >= 1
    assert message.content[0]["type"] == "text"
    assert message.content[0]["text"] == "partial"
