"""Custom Agent knowledge/skill API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.services.agent_asset_service import build_agent_asset_context
from app.services.upload_service import upload_service

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'agent-asset-api-%'"))
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    previous_storage_dir = settings.upload_storage_dir
    previous_service_dir = upload_service.storage_dir
    settings.upload_storage_dir = str(tmp_path / "uploads")
    upload_service.storage_dir = Path(settings.upload_storage_dir)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    settings.upload_storage_dir = previous_storage_dir
    upload_service.storage_dir = previous_service_dir


async def _register(client: AsyncClient) -> dict[str, str]:
    username = f"agent_asset_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _ensure_opencode_base_agent() -> None:
    async with SessionFactory() as db:
        existing = await db.get(Agent, "opencode-helper")
        if existing is None:
            db.add(
                Agent(
                    id="opencode-helper",
                    user_id=None,
                    name="OpenCode Helper",
                    provider="opencode",
                    avatar_url="",
                    capabilities=["coding", "files"],
                    system_prompt="OpenCode base agent for wrapper tests.",
                    config={
                        "command": "opencode",
                        "args": [],
                        "max_runtime_seconds": 600,
                        "idle_timeout_seconds": 360,
                        "heartbeat_interval_seconds": 15,
                    },
                    is_builtin=True,
                )
            )
            await db.commit()


async def _create_custom_agent(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    await _ensure_opencode_base_agent()
    response = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "name": "Asset Agent",
            "provider": "opencode",
            "avatar_url": "",
            "capabilities": ["skills"],
            "system_prompt": "Use uploaded context carefully.",
            "config": {
                "custom_agent_mode": "server_agent_wrapper",
                "base_agent_id": "opencode-helper",
                "wrapper_profile": {
                    "role": "Asset Agent",
                    "purpose": "Use uploaded context carefully.",
                    "planning_profile": "Use this wrapper when uploaded Skills are relevant.",
                    "planning_strengths": ["asset_context"],
                    "planning_weaknesses": [],
                    "preferred_task_types": ["implementation"],
                    "capabilities": ["skills"],
                    "output_style": "Concise",
                    "boundaries": [],
                },
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _insert_builtin_agent() -> str:
    agent_id = f"agent-asset-api-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                user_id=None,
                name="Builtin Asset Agent",
                provider="mock",
                avatar_url="",
                capabilities=["testing"],
                system_prompt=None,
                config={},
                is_builtin=True,
            )
        )
        await db.commit()
    return agent_id


async def test_upload_markdown_knowledge_updates_agent_config(client: AsyncClient) -> None:
    headers = await _register(client)
    agent = await _create_custom_agent(client, headers)

    response = await client.post(
        f"/api/v1/agents/{agent['id']}/knowledge",
        headers=headers,
        data={"label": "产品规则", "usage": "policy"},
        files={"file": ("rules.md", b"# Rules\nAlways cite sources.", "text/markdown")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "rules.md"
    assert body["label"] == "产品规则"
    assert body["usage"] == "policy"

    refreshed = await client.get(f"/api/v1/agents/{agent['id']}", headers=headers)
    assert refreshed.status_code == 200
    knowledge = refreshed.json()["config"]["knowledge"]
    assert knowledge[0]["upload_id"] == body["upload_id"]

    assets = await client.get(f"/api/v1/agents/{agent['id']}/assets", headers=headers)
    assert assets.status_code == 200, assets.text
    assert assets.json()["knowledge"][0]["upload_id"] == body["upload_id"]
    assert assets.json()["bindings"][0]["kind"] == "knowledge"

    patch = await client.patch(
        f"/api/v1/agents/{agent['id']}/knowledge/{body['upload_id']}",
        headers=headers,
        json={"label": "更新后的规则", "usage": "template"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["label"] == "更新后的规则"
    assert patch.json()["usage"] == "template"

    async with SessionFactory() as db:
        agent_model = await db.get(Agent, agent["id"])
        assert agent_model is not None
        context = await build_agent_asset_context(db, agent_model)
        assert "Always cite sources." in context
        await db.commit()

    usage = await client.get(f"/api/v1/agents/{agent['id']}/assets/usage", headers=headers)
    assert usage.status_code == 200, usage.text
    assert usage.json()["items"][0]["status"] == "injected"

    history = await client.get(f"/api/v1/agents/{agent['id']}/assets/history", headers=headers)
    assert history.status_code == 200, history.text
    assert [item["action"] for item in history.json()["items"]][:2] == ["updated", "created"]


async def test_builtin_agent_rejects_knowledge_upload(client: AsyncClient) -> None:
    headers = await _register(client)
    agent_id = await _insert_builtin_agent()

    response = await client.post(
        f"/api/v1/agents/{agent_id}/knowledge",
        headers=headers,
        data={"usage": "reference"},
        files={"file": ("rules.md", b"# Rules", "text/markdown")},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "CANNOT_MODIFY_BUILTIN"


async def test_upload_and_delete_skill_binding(client: AsyncClient) -> None:
    headers = await _register(client)
    agent = await _create_custom_agent(client, headers)

    response = await client.post(
        f"/api/v1/agents/{agent['id']}/skills",
        headers=headers,
        files={
            "file": (
                "SKILL.md",
                b"---\nname: Reviewer\ndescription: Review uploaded drafts.\n---\n# Reviewer\n",
                "text/markdown",
            )
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Reviewer"
    assert body["description"] == "Review uploaded drafts."

    patch = await client.patch(
        f"/api/v1/agents/{agent['id']}/skills/{body['skill_id']}",
        headers=headers,
        json={"name": "Draft Reviewer", "description": "Review draft Markdown files."},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["name"] == "Draft Reviewer"
    assert patch.json()["description"] == "Review draft Markdown files."

    delete = await client.delete(
        f"/api/v1/agents/{agent['id']}/skills/{body['skill_id']}",
        headers=headers,
    )
    assert delete.status_code == 204

    refreshed = await client.get(f"/api/v1/agents/{agent['id']}", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["config"]["skills"] == []

    history = await client.get(f"/api/v1/agents/{agent['id']}/assets/history", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["action"] == "unbound"


async def test_upload_skill_requires_name_and_description(client: AsyncClient) -> None:
    headers = await _register(client)
    agent = await _create_custom_agent(client, headers)

    response = await client.post(
        f"/api/v1/agents/{agent['id']}/skills",
        headers=headers,
        files={"file": ("skill.md", b"plain text without metadata", "text/markdown")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "INVALID_SKILL_METADATA"


async def test_delete_custom_agent_removes_conversation_references(client: AsyncClient) -> None:
    headers = await _register(client)
    agent = await _create_custom_agent(client, headers)
    conversation = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Agent asset chat", "mode": "single", "agent_ids": [agent["id"]]},
    )
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["id"]

    delete = await client.delete(f"/api/v1/agents/{agent['id']}", headers=headers)
    assert delete.status_code == 204

    refreshed = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert refreshed.status_code == 200
    assert agent["id"] not in refreshed.json()["agent_ids"]
