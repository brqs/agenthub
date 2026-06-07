"""Upload API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message
from app.models.upload import MessageAttachment
from app.services.upload_service import upload_service

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'upload-api-agent-%'"))
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


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"upload_api_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"upload-api-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                user_id=None,
                name="Upload API Agent",
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


async def _create_single_conversation(
    client: AsyncClient,
    headers: dict[str, str],
) -> tuple[str, str]:
    agent_id = await _insert_agent()
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Upload single chat",
            "mode": "single",
            "agent_ids": [agent_id],
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), agent_id


async def _upload_text_file(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    conversation_id: str,
    content: bytes = b"hello upload",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/uploads",
        headers=headers,
        data={"purpose": "message_attachment", "conversation_id": conversation_id},
        files={"file": ("note.txt", content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_upload_can_be_downloaded_and_deleted(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation_id, _agent_id = await _create_single_conversation(client, headers)
    uploaded = await _upload_text_file(
        client,
        headers,
        conversation_id=conversation_id,
        content=b"hello from upload",
    )

    assert uploaded["filename"] == "note.txt"
    assert uploaded["status"] == "ready"
    assert uploaded["safety_status"] == "passed"
    assert uploaded["preview"]["kind"] == "text"
    assert uploaded["preview"]["text_preview"] == "hello from upload"

    download = await client.get(
        f"/api/v1/uploads/{uploaded['id']}/download",
        headers=headers,
    )
    assert download.status_code == 200, download.text
    assert download.content == b"hello from upload"

    delete = await client.delete(f"/api/v1/uploads/{uploaded['id']}", headers=headers)
    assert delete.status_code == 204
    deleted_download = await client.get(
        f"/api/v1/uploads/{uploaded['id']}/download",
        headers=headers,
    )
    assert deleted_download.status_code == 410


async def test_send_message_persists_attachment_block(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation_id, _agent_id = await _create_single_conversation(client, headers)
    uploaded = await _upload_text_file(client, headers, conversation_id=conversation_id)

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "content": [{"type": "text", "text": "please read this"}],
            "attachment_ids": [uploaded["id"]],
        },
    )

    assert response.status_code == 201, response.text
    user_message = response.json()["user_message"]
    assert [block["type"] for block in user_message["content"]] == ["text", "attachment"]
    attachment_block = user_message["content"][1]
    assert attachment_block["upload_id"] == uploaded["id"]
    assert attachment_block["filename"] == "note.txt"
    assert attachment_block["purpose"] == "message_attachment"

    async with SessionFactory() as db:
        message = await db.get(Message, UUID(user_message["id"]))
        assert message is not None
        link = (
            await db.execute(
                select(MessageAttachment).where(MessageAttachment.message_id == message.id)
            )
        ).scalar_one()
        assert str(link.upload_id) == uploaded["id"]


async def test_upload_from_another_user_cannot_be_attached(
    client: AsyncClient,
) -> None:
    _, owner_headers = await _register(client)
    _, other_headers = await _register(client)
    owner_conversation_id, _owner_agent_id = await _create_single_conversation(
        client,
        owner_headers,
    )
    other_conversation_id, _other_agent_id = await _create_single_conversation(
        client,
        other_headers,
    )
    uploaded = await _upload_text_file(
        client,
        owner_headers,
        conversation_id=owner_conversation_id,
    )

    response = await client.post(
        f"/api/v1/conversations/{other_conversation_id}/messages",
        headers=other_headers,
        json={
            "content": [{"type": "text", "text": "steal attachment"}],
            "attachment_ids": [uploaded["id"]],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "UPLOAD_NOT_FOUND"
