"""B1 backend quality regression tests."""

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
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

import app.api.v1.stream as stream_module
from app.agents.types import StreamChunk
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message
from app.models.orchestrator_memory import OrchestratorRun
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


async def _send_message_after_marking_error(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    failed_message_id: UUID,
    target_agent_id: str,
) -> dict[str, Any]:
    async with SessionFactory() as db:
        failed_message = await db.get(Message, failed_message_id)
        assert failed_message is not None
        failed_message.status = "error"
        failed_message.content = [{"type": "text", "text": "failed"}]
        await db.commit()
    return await _send_message(client, headers, conversation_id, target_agent_id)


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class _HangingAdapter:
    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, workspace_path, tool_specs
        yield StreamChunk(event_type="start", agent_id="test-agent")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="partial")
        await asyncio.Event().wait()


class _CountingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, workspace_path, tool_specs
        self.calls += 1
        yield StreamChunk(event_type="start", agent_id="test-agent")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="hello")
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="test-agent", total_blocks=1)


class _GatedAdapter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, system_prompt, config, workspace_path, tool_specs
        yield StreamChunk(event_type="start", agent_id="test-agent")
        self.started.set()
        await self.release.wait()
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="hello")
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="test-agent", total_blocks=1)


async def _insert_messages(
    conversation_id: str,
    count: int,
    *,
    last_status: str = "done",
) -> list[Message]:
    base_time = datetime.now(UTC) - timedelta(minutes=count)
    messages: list[Message] = []
    async with SessionFactory() as db:
        for index in range(count):
            message = Message(
                conversation_id=UUID(conversation_id),
                role="agent" if index % 2 else "user",
                agent_id="test-agent" if index % 2 else None,
                content=[{"type": "text", "text": f"message {index:02d}"}],
                status=last_status if index == count - 1 else "done",
                created_at=base_time + timedelta(seconds=index),
            )
            db.add(message)
            messages.append(message)
        await db.commit()
        for message in messages:
            await db.refresh(message)
    return messages


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


async def test_list_messages_defaults_to_recent_page_in_ascending_order(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    await _insert_messages(conversation["id"], 35)

    response = await client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    texts = [item["content"][0]["text"] for item in body["items"]]
    assert len(texts) == 30
    assert texts[0] == "message 05"
    assert texts[-1] == "message 34"
    assert texts == sorted(texts)
    assert body["has_more"] is True
    assert body["next_cursor"] == body["items"][0]["id"]


async def test_list_messages_before_cursor_loads_older_page(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    await _insert_messages(conversation["id"], 35)

    recent = (
        await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=headers,
            params={"limit": 30},
        )
    ).json()
    older = await client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        params={"limit": 30, "cursor": recent["next_cursor"], "direction": "before"},
    )

    assert older.status_code == 200
    body = older.json()
    texts = [item["content"][0]["text"] for item in body["items"]]
    assert texts == [f"message {index:02d}" for index in range(5)]
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_list_messages_keeps_latest_streaming_message_in_default_page(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _insert_messages(conversation["id"], 35, last_status="streaming")

    response = await client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][-1]["id"] == str(messages[-1].id)
    assert body["items"][-1]["status"] == "streaming"
    assert body["items"][-1]["content"][0]["text"] == "message 34"


async def test_mark_stream_error_terminalizes_claimed_message(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        accumulator = stream_module._ContentAccumulator()
        await stream_module._mark_stream_error(
            db,
            message,
            accumulator,
            "Stream was cancelled before the Agent finished.",
        )

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "error"
        assert message.content
        assert "cancelled" in message.content[0]["text"].lower()


async def test_mark_stream_error_recovers_invalid_transaction(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        with pytest.raises(SQLAlchemyError):
            await db.execute(text("SELECT * FROM table_that_does_not_exist"))
        await stream_module._mark_stream_error(
            db,
            message,
            stream_module._ContentAccumulator(),
            "Stream was cancelled before the Agent finished.",
        )

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "error"
        assert "cancelled" in message.content[0]["text"].lower()


async def test_stream_idle_timeout_marks_message_error_and_yields_sse_error(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    monkeypatch.setattr(settings, "agent_stream_idle_timeout_seconds", 0.01)
    monkeypatch.setattr(settings, "agent_stream_hard_timeout_seconds", 30)

    async def fake_get_adapter(agent_id: str, db: Any) -> _HangingAdapter:
        _ = agent_id, db
        return _HangingAdapter()

    monkeypatch.setattr(stream_module, "get_adapter", fake_get_adapter)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    events: list[dict[str, str]] = []
    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        async for event in stream_module._event_generator(
            db,
            _ConnectedRequest(),
            message,
        ):
            events.append(event)
            if event["event"] == "error":
                break

    assert [event["event"] for event in events] == [
        "start",
        "block_start",
        "delta",
        "error",
    ]
    assert "stream_idle_timeout" in events[-1]["data"]

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "error"
        assert message.content[0]["text"] == "partial"
        assert "timed out" in message.content[1]["text"]


async def test_stream_run_manager_reuses_runtime_for_multiple_subscribers(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    adapter = _CountingAdapter()

    async def fake_get_adapter(agent_id: str, db: Any) -> _CountingAdapter:
        _ = agent_id, db
        return adapter

    monkeypatch.setattr(stream_module, "get_adapter", fake_get_adapter)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        message.status = "streaming"
        await db.commit()
        session = await stream_module.stream_run_manager.start(
            message,
            stream_module._run_stream_session,
        )
        reused = await stream_module.stream_run_manager.start(
            message,
            stream_module._run_stream_session,
        )

    assert reused is session
    first = stream_module.stream_run_manager.subscribe(session).__aiter__()
    second = stream_module.stream_run_manager.subscribe(session).__aiter__()

    first_event = await anext(first)
    second_event = await anext(second)
    assert first_event["event"] == "start"
    assert second_event["event"] == "start"

    await session.task
    assert adapter.calls == 1

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "done"
        assert message.content == [{"type": "text", "text": "hello"}]


async def test_stream_endpoint_existing_session_releases_message_lock(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    adapter = _GatedAdapter()

    async def fake_get_adapter(agent_id: str, db: Any) -> _GatedAdapter:
        _ = agent_id, db
        return adapter

    monkeypatch.setattr(stream_module, "get_adapter", fake_get_adapter)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        message.status = "streaming"
        await db.commit()
        session = await stream_module.stream_run_manager.start(
            message,
            stream_module._run_stream_session,
        )

    await asyncio.wait_for(adapter.started.wait(), timeout=2)
    subscriber = asyncio.create_task(
        client.get(f"/api/v1/messages/{agent_message_id}/stream", headers=headers)
    )
    await asyncio.sleep(0.05)
    adapter.release.set()
    response = await asyncio.wait_for(subscriber, timeout=5)

    assert response.status_code == 200
    assert "event: done" in response.text
    await asyncio.wait_for(session.task, timeout=2)
    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "done"
        assert message.content == [{"type": "text", "text": "hello"}]


async def test_interrupt_pending_agent_message_marks_interrupted_and_releases_busy(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = messages["agent_message"]["id"]

    response = await client.post(
        f"/api/v1/messages/{agent_message_id}/interrupt",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "interrupted"
    assert body["message"]["status"] == "interrupted"
    assert body["message"]["content"][0]["text"].startswith("已打断")

    next_messages = await _send_message(client, headers, conversation["id"], agent_id)
    assert next_messages["agent_message"]["status"] == "pending"


async def test_interrupt_streaming_message_without_session_marks_interrupted(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        message.status = "streaming"
        message.content = []
        await db.commit()

    response = await client.post(
        f"/api/v1/messages/{agent_message_id}/interrupt",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "interrupted"
    assert body["message"]["status"] == "interrupted"
    assert body["message"]["content"][0]["text"].startswith("已打断")

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "interrupted"
        assert "Agent stream was interrupted before completion" not in str(message.content)


async def test_interrupt_streaming_agent_message_stops_runtime_and_preserves_partial_content(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))

    async def fake_get_adapter(agent_id: str, db: Any) -> _HangingAdapter:
        _ = agent_id, db
        return _HangingAdapter()

    monkeypatch.setattr(stream_module, "get_adapter", fake_get_adapter)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        message.status = "streaming"
        await db.commit()
        session = await stream_module.stream_run_manager.start(
            message,
            stream_module._run_stream_session,
        )

    subscription = stream_module.stream_run_manager.subscribe(session).__aiter__()
    assert (await anext(subscription))["event"] == "start"
    assert (await anext(subscription))["event"] == "block_start"
    assert (await anext(subscription))["event"] == "delta"

    response = await client.post(
        f"/api/v1/messages/{agent_message_id}/interrupt",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "interrupted"
    assert body["message"]["status"] == "interrupted"
    assert body["message"]["content"][0]["type"] == "text"
    assert body["message"]["content"][0]["text"] == "partial"

    interrupted_event = await anext(subscription)
    assert interrupted_event["event"] == "interrupted"
    await session.task

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "interrupted"
        assert message.content == [{"type": "text", "text": "partial"}]


async def test_interrupt_user_message_is_rejected(client: AsyncClient) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    user_message_id = messages["user_message"]["id"]

    response = await client.post(
        f"/api/v1/messages/{user_message_id}/interrupt",
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "NOT_AGENT_MESSAGE"


async def test_streaming_message_without_manager_stays_recoverable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stream_module, "ORPHANED_STREAM_RECOVERY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(stream_module, "ORPHANED_STREAM_RECOVERY_POLL_SECONDS", 0.001)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    messages = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(messages["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        message.status = "streaming"
        message.content = []
        await db.commit()

    response = await client.get(
        f"/api/v1/messages/{agent_message_id}/stream",
        headers=headers,
    )

    assert response.status_code == 200
    assert "stream_session_lost" not in response.text
    assert "Agent stream was interrupted before completion" not in response.text

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        assert message.status == "streaming"
        assert message.content == []


async def test_send_message_cleans_stale_stream_before_busy_check(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_stream_stale_seconds", 1)

    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    stale_pair = await _send_message(client, headers, conversation["id"], agent_id)
    stale_message_id = UUID(stale_pair["agent_message"]["id"])

    async with SessionFactory() as db:
        stale_message = await db.get(Message, stale_message_id)
        assert stale_message is not None
        stale_message.status = "streaming"
        stale_message.content = []
        stale_message.created_at = datetime.now(UTC) - timedelta(seconds=30)
        await db.commit()

    fresh_pair = await _send_message(client, headers, conversation["id"], agent_id)

    assert fresh_pair["agent_message"]["status"] == "pending"
    async with SessionFactory() as db:
        stale_message = await db.get(Message, stale_message_id)
        assert stale_message is not None
        assert stale_message.status == "error"
        assert stale_message.content[0]["text"].startswith("Agent stream expired")


async def test_message_list_reconciles_terminal_orchestrator_parent(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    pair = await _send_message(client, headers, conversation["id"], agent_id)
    agent_message_id = UUID(pair["agent_message"]["id"])

    async with SessionFactory() as db:
        message = await db.get(Message, agent_message_id)
        assert message is not None
        message.status = "streaming"
        message.content = []
        db.add(
            OrchestratorRun(
                conversation_id=UUID(conversation["id"]),
                agent_message_id=agent_message_id,
                user_message_id=UUID(pair["user_message"]["id"]),
                status="done",
                user_request="Build a demo",
                plan_source="test",
                final_summary="Execution summary\n\n- succeeded: @agent - task",
            )
        )
        await db.commit()

    response = await client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    agent_message = next(item for item in items if item["id"] == str(agent_message_id))
    assert agent_message["status"] == "done"
    assert "Execution summary" in agent_message["content"][0]["text"]


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


async def test_send_message_rejects_when_agent_response_pending(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    first = await _send_message(client, headers, conversation["id"])

    response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "你是什么模型"}]},
    )

    body = response.json()
    assert response.status_code == 409
    assert body["detail"]["error"]["code"] == "CONVERSATION_BUSY"
    assert body["detail"]["error"]["details"]["message_id"] == first["agent_message"]["id"]
    assert body["detail"]["error"]["details"]["status"] == "pending"

    async with SessionFactory() as db:
        messages = (
            await db.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conversation["id"])
                )
            )
        ).scalars().all()

    assert [message.role for message in messages] == ["user", "agent"]


async def test_regenerate_rejects_when_conversation_busy(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    agent_id = await _insert_agent()
    conversation = await _create_conversation(client, headers, [agent_id])
    failed_pair = await _send_message(client, headers, conversation["id"], agent_id)
    busy_pair = await _send_message_after_marking_error(
        client,
        headers,
        conversation["id"],
        UUID(failed_pair["agent_message"]["id"]),
        agent_id,
    )

    response = await client.post(
        f"/api/v1/messages/{failed_pair['agent_message']['id']}/regenerate",
        headers=headers,
    )

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["code"] == "CONVERSATION_BUSY"
    assert body["detail"]["error"]["details"]["message_id"] == busy_pair["agent_message"]["id"]


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
    assert message.content
    assert message.content[0]["type"] == "text"
    assert "agent_not_found" in message.content[0]["text"]


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
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
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
    assert len(message.content) == 2
    assert message.content[0]["type"] == "text"
    assert message.content[0]["text"] == "partial"
    assert "rate_limit" in message.content[1]["text"]
    assert "Rate limited" in message.content[1]["text"]


async def test_stream_adapter_error_chunk_without_content_persists_visible_text(
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
            _ = messages, system_prompt, config, workspace_path, tool_specs
            yield StreamChunk(event_type="start")
            yield StreamChunk(
                event_type="error",
                error_code="no_runnable_agent",
                error="当前会话没有可用执行 Agent：@claude-code 未认证",
            )

    async def mock_get_adapter(agent_id: str, db: Any) -> FakeAdapter:
        _ = agent_id, db
        return FakeAdapter()

    monkeypatch.setattr("app.api.v1.stream.get_adapter", mock_get_adapter)

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
    assert message.content == [
        {
            "type": "text",
            "text": "no_runnable_agent: 当前会话没有可用执行 Agent：@claude-code 未认证",
        }
    ]


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
            *,
            system_prompt: str | None = None,
            config: dict[str, Any] | None = None,
            workspace_path: Path | None = None,
            tool_specs: list[Any] | None = None,
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
    assert "boom" in message.content[1]["text"]
