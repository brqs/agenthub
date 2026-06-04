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
from sqlalchemy import text

from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskResult, TaskState
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.services.orchestrator_memory import OrchestratorMemoryStore

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
    runtime_document = app.openapi()
    shared_path = Path(__file__).parents[1] / ".." / "shared" / "openapi.yaml"
    shared_document = yaml.safe_load(shared_path.resolve().read_text(encoding="utf-8"))

    for document in (runtime_document, shared_document):
        assert route in document["paths"]
        response = document["paths"][route]["get"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AgentCapabilityProfileOut"
        }
        schemas = document["components"]["schemas"]
        assert "AgentCapabilityProfileOut" in schemas
        assert "AgentCapabilityProfileItemOut" in schemas
