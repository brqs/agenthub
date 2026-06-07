"""Conversation API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskResult, TaskState
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_queue import MessageQueueEntry
from app.services.orchestrator_memory import OrchestratorMemoryStore
from app.services.queued_messages import dispatch_next_queued_message

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'conv-api-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"conv_api_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"conv-api-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                user_id=None,
                name="Conversation API Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                system_prompt=None,
                config={},
                is_builtin=True,
            )
        )
        await db.commit()
    return agent_id


async def _create_group_conversation(
    client: AsyncClient,
    headers: dict[str, str],
) -> str:
    agent_a = await _insert_agent()
    agent_b = await _insert_agent()
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Capability profile API",
            "mode": "group",
            "agent_ids": [agent_a, agent_b],
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _create_single_conversation(
    client: AsyncClient,
    headers: dict[str, str],
) -> tuple[str, str]:
    agent_id = await _insert_agent()
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Queued single chat",
            "mode": "single",
            "agent_ids": [agent_id],
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), agent_id


async def _seed_profile_run(conversation_id: str, agent_id: str) -> None:
    async with SessionFactory() as db:
        store = OrchestratorMemoryStore(
            db,
            conversation_id=UUID(conversation_id),
            agent_message_id=None,
            user_message_id=None,
        )
        task = SubTask(
            task_id="api-profile-task",
            agent_id=agent_id,
            title="Write API profile report",
            instruction="Write api-profile.md",
            expected_output="api-profile.md",
        )
        run_id = await store.start_run(
            user_request="Write API profile report",
            plan_source="LLM planner/config",
            tasks=[task],
        )
        result = TaskResult(
            task_id=task.task_id,
            title=task.title,
            final_state=TaskState.SUCCEEDED,
        )
        result.attempts.append(
            TaskAttempt(
                attempt_index=1,
                agent_id=agent_id,
                state=TaskState.SUCCEEDED,
                artifact_paths=["api-profile.md"],
                text_preview="Created api-profile.md",
            )
        )
        await store.record_task_result(run_id=run_id, task=task, result=result)
        await store.finish_run(
            run_id=run_id,
            status="done",
            final_summary="Execution summary\n- succeeded",
        )
        await db.commit()


async def test_queue_message_requires_active_agent_response(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation_id, _agent_id = await _create_single_conversation(client, headers)

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/queued-messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "next"}]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "NO_ACTIVE_AGENT_RESPONSE"


async def test_queue_message_can_be_updated_and_deleted(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation_id, _agent_id = await _create_single_conversation(client, headers)
    send_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "first"}]},
    )
    assert send_response.status_code == 201, send_response.text

    queue_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/queued-messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "second"}]},
    )
    assert queue_response.status_code == 201, queue_response.text
    queued = queue_response.json()["queued_message"]
    assert queued["status"] == "queued"
    assert queue_response.json()["queue_position"] == 1

    update_response = await client.patch(
        f"/api/v1/queued-messages/{queued['id']}",
        headers=headers,
        json={"content": [{"type": "text", "text": "second edited"}]},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["queued_message"]["content"][0]["text"] == "second edited"

    delete_response = await client.delete(
        f"/api/v1/queued-messages/{queued['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204
    list_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    assert queued["id"] not in {item["id"] for item in list_response.json()["items"]}


async def test_dispatch_next_queued_message_after_terminal_turn(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation_id, agent_id = await _create_single_conversation(client, headers)
    send_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "first"}]},
    )
    assert send_response.status_code == 201, send_response.text
    active_agent_id = send_response.json()["agent_message"]["id"]
    queue_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/queued-messages",
        headers=headers,
        json={"content": [{"type": "text", "text": "queued next"}]},
    )
    assert queue_response.status_code == 201, queue_response.text
    queued_user_id = queue_response.json()["queued_message"]["id"]

    async with SessionFactory() as db:
        active_agent = await db.get(Message, UUID(active_agent_id))
        assert active_agent is not None
        active_agent.status = "done"
        active_agent.content = [{"type": "text", "text": "done"}]
        await db.commit()
        dispatch = await dispatch_next_queued_message(db, conversation_id=UUID(conversation_id))
        assert dispatch is not None
        await db.commit()
        assert dispatch.user_message.id == UUID(queued_user_id)
        assert dispatch.user_message.status == "done"
        assert dispatch.agent_message.agent_id == agent_id
        assert dispatch.agent_message.reply_to_id == UUID(queued_user_id)
        assert dispatch.agent_message.status == "pending"
        queue_entry = (
            await db.execute(
                select(MessageQueueEntry).where(
                    MessageQueueEntry.user_message_id == UUID(queued_user_id)
                )
            )
        ).scalar_one()
        assert queue_entry.state == "dispatched"
        assert queue_entry.dispatched_agent_message_id == dispatch.agent_message.id


async def test_dispatch_skips_removed_target_and_continues_queue(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    invalid_agent_id = await _insert_agent()
    valid_agent_id = await _insert_agent()
    create_response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Queued group chat",
            "mode": "group",
            "agent_ids": [invalid_agent_id, valid_agent_id],
        },
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]
    send_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "first"}],
            "target_agent_id": valid_agent_id,
        },
    )
    assert send_response.status_code == 201, send_response.text
    active_agent_id = send_response.json()["agent_message"]["id"]
    invalid_queue_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/queued-messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "invalid target"}],
            "target_agent_id": invalid_agent_id,
        },
    )
    valid_queue_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/queued-messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "valid target"}],
            "target_agent_id": valid_agent_id,
        },
    )
    assert invalid_queue_response.status_code == 201, invalid_queue_response.text
    assert valid_queue_response.status_code == 201, valid_queue_response.text
    invalid_user_id = UUID(invalid_queue_response.json()["queued_message"]["id"])
    valid_user_id = UUID(valid_queue_response.json()["queued_message"]["id"])

    async with SessionFactory() as db:
        conversation = await db.get(Conversation, UUID(conversation_id))
        assert conversation is not None
        conversation.agent_ids = [valid_agent_id]
        active_agent = await db.get(Message, UUID(active_agent_id))
        assert active_agent is not None
        active_agent.status = "done"
        active_agent.content = [{"type": "text", "text": "done"}]
        await db.commit()

        dispatch = await dispatch_next_queued_message(db, conversation_id=UUID(conversation_id))
        assert dispatch is not None
        await db.commit()

        assert dispatch.user_message.id == valid_user_id
        assert dispatch.agent_message.agent_id == valid_agent_id
        assert dispatch.agent_message.status == "pending"
        invalid_error = (
            await db.execute(
                select(Message)
                .where(Message.reply_to_id == invalid_user_id)
                .where(Message.status == "error")
            )
        ).scalar_one()
        assert invalid_error.agent_id == invalid_agent_id
        invalid_entry = (
            await db.execute(
                select(MessageQueueEntry).where(
                    MessageQueueEntry.user_message_id == invalid_user_id
                )
            )
        ).scalar_one()
        valid_entry = (
            await db.execute(
                select(MessageQueueEntry).where(MessageQueueEntry.user_message_id == valid_user_id)
            )
        ).scalar_one()
        assert invalid_entry.state == "dispatched"
        assert valid_entry.state == "dispatched"


async def test_agent_capability_profile_api_returns_items_for_owner(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation_id = await _create_group_conversation(client, headers)
    await _seed_profile_run(conversation_id, "conv-api-agent-api-profile")

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/agent-capability-profile",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["agent_id"] == "conv-api-agent-api-profile"
    assert item["task_count"] == 1
    assert item["success_count"] == 1
    assert item["artifact_kinds"] == {"document": 1}


async def test_agent_capability_profile_v2_api_returns_user_scope_profile(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation_id = await _create_group_conversation(client, headers)
    await _seed_profile_run(conversation_id, "conv-api-agent-api-profile-v2")

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/agent-capability-profile-v2",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "user"
    assert body["total"] == 1
    assert body["runs_considered"] == 1
    assert body["source_conversation_count"] == 1
    assert body["generated_at"]
    assert body["preferences"]["runs_considered"] == 1
    item = body["items"][0]
    assert item["agent_id"] == "conv-api-agent-api-profile-v2"
    assert item["scope"] == "user"
    assert item["conversation_count"] == 1
    assert item["success_count"] == 1
    assert item["success_rate"] == 1.0
    assert item["score_reasons"]


async def test_agent_capability_profile_v2_api_forbids_other_users(
    client: AsyncClient,
) -> None:
    _, owner_headers = await _register(client)
    _, other_headers = await _register(client)
    conversation_id = await _create_group_conversation(client, owner_headers)

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/agent-capability-profile-v2",
        headers=other_headers,
    )

    assert response.status_code == 403


async def test_agent_capability_profile_api_forbids_other_users(
    client: AsyncClient,
) -> None:
    _, owner_headers = await _register(client)
    _, other_headers = await _register(client)
    conversation_id = await _create_group_conversation(client, owner_headers)

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/agent-capability-profile",
        headers=other_headers,
    )

    assert response.status_code == 403


async def test_openapi_includes_agent_capability_profile_contract() -> None:
    route = "/api/v1/conversations/{conversation_id}/agent-capability-profile"
    route_v2 = "/api/v1/conversations/{conversation_id}/agent-capability-profile-v2"
    runtime_document = app.openapi()
    shared_path = Path(__file__).parents[1] / ".." / "shared" / "openapi.yaml"
    shared_document = yaml.safe_load(shared_path.resolve().read_text(encoding="utf-8"))

    for document in (runtime_document, shared_document):
        assert route in document["paths"]
        assert route_v2 in document["paths"]
        response = document["paths"][route]["get"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AgentCapabilityProfileOut"
        }
        schemas = document["components"]["schemas"]
        assert "AgentCapabilityProfileOut" in schemas
        assert "AgentCapabilityProfileItemOut" in schemas
        response_v2 = document["paths"][route_v2]["get"]["responses"]["200"]
        assert response_v2["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AgentCapabilityProfileV2Out"
        }
        assert "AgentCapabilityProfileV2Out" in schemas
        assert "AgentCapabilityProfileV2ItemOut" in schemas
        assert "UserPreferenceMemoryOut" in schemas
