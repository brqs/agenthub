"""MemoryHub semantic memory and dynamic mount tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.conversation import Conversation
from app.models.memory import Memory, MemoryMount
from app.models.message import Message
from app.models.user import User
from app.services.context_builder import build_context
from app.services.memory_hub import MemoryHubService

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _register(client: AsyncClient) -> tuple[dict[str, object], dict[str, str]]:
    username = f"memory_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _create_conversation() -> tuple[User, Conversation]:
    async with SessionFactory() as db:
        user = User(username=f"memory_user_{uuid4().hex[:16]}", password_hash="hash")
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="MemoryHub test",
            mode="single",
            agent_ids=["test-agent"],
        )
        db.add(conversation)
        await db.commit()
        return user, conversation


async def test_extracts_active_preference_and_filters_secrets() -> None:
    user, conversation = await _create_conversation()
    async with SessionFactory() as db:
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=[
                {
                    "type": "text",
                    "text": (
                        "请记住：以后默认用中文回复我。"
                        "我的 API_KEY 是 sk-this-should-not-store-1234567890"
                    ),
                }
            ],
            status="done",
        )
        db.add(user_message)
        await db.flush()
        agent_message = Message(
            conversation_id=conversation.id,
            role="agent",
            agent_id="test-agent",
            reply_to_id=user_message.id,
            content=[{"type": "text", "text": "好的。"}],
            status="done",
        )
        db.add(agent_message)
        await db.flush()

        memories = await MemoryHubService().extract_candidates_for_terminal_message(
            db,
            agent_message=agent_message,
        )
        await db.commit()

    assert memories
    assert any(memory.status == "active" for memory in memories)
    assert any("中文" in memory.content for memory in memories)
    assert all("API_KEY" not in memory.content for memory in memories)
    assert all(memory.owner_user_id == user.id for memory in memories)


async def test_memoryhub_mount_replaces_legacy_summary_when_available() -> None:
    user, conversation = await _create_conversation()
    async with SessionFactory() as db:
        memory = Memory(
            owner_user_id=user.id,
            scope_type="user",
            scope_id=None,
            container_tag=f"agenthub:user:{user.id}",
            kind="preference",
            content="以后默认输出精致的中文界面文案。",
            importance="high",
            confidence=0.9,
            status="active",
            normalized_key="preference:ui-language",
            source_type="manual",
            source_id=None,
            memory_metadata={},
        )
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=[{"type": "text", "text": "帮我做一个网页游戏"}],
            status="done",
        )
        agent_message = Message(
            conversation_id=conversation.id,
            role="agent",
            agent_id="test-agent",
            reply_to_id=user_message.id,
            content=[],
            status="streaming",
        )
        db.add_all([memory, user_message, agent_message])
        await db.flush()
        context = await build_context(
            db,
            conversation.id,
            current_agent_id="test-agent",
            agent_message_id=agent_message.id,
        )
        mounts = (await db.execute(MemoryMount.__table__.select())).all()

    assert any("MemoryHub mounted context" in message.content for message in context)
    assert any("精致的中文界面文案" in message.content for message in context)
    assert not any(
        "Earlier compressed conversation memory" in message.content
        for message in context
    )
    assert mounts


async def test_forgetting_memory_removes_it_from_recall() -> None:
    user, conversation = await _create_conversation()
    async with SessionFactory() as db:
        memory = Memory(
            owner_user_id=user.id,
            scope_type="user",
            scope_id=None,
            container_tag=f"agenthub:user:{user.id}",
            kind="preference",
            content="以后默认使用英文回复。",
            importance="high",
            confidence=0.9,
            status="active",
            normalized_key="preference:response_language",
            source_type="manual",
            source_id=None,
            memory_metadata={},
        )
        db.add(memory)
        await db.flush()
        await MemoryHubService().forget_memory(db, memory)
        recalled = await MemoryHubService().recall(
            db,
            owner_user_id=user.id,
            query="请回复语言偏好是什么",
            conversation_id=conversation.id,
            conversation_mode=conversation.mode,
            current_agent_id="test-agent",
        )

    assert recalled == []


async def test_memory_api_lists_updates_and_forgets(client: AsyncClient) -> None:
    body, headers = await _register(client)
    user_id = UUID(body["user"]["id"])
    async with SessionFactory() as db:
        memory = Memory(
            owner_user_id=user_id,
            scope_type="user",
            scope_id=None,
            container_tag=f"agenthub:user:{user_id}",
            kind="preference",
            content="以后默认做移动端优先的设计。",
            importance="normal",
            confidence=0.7,
            status="candidate",
            normalized_key="preference:mobile-first",
            source_type="manual",
            source_id=None,
            memory_metadata={},
        )
        db.add(memory)
        await db.commit()
        memory_id = str(memory.id)

    list_response = await client.get("/api/v1/memories?status=candidate", headers=headers)
    assert list_response.status_code == 200, list_response.text
    assert any(item["id"] == memory_id for item in list_response.json()["items"])

    patch_response = await client.patch(
        f"/api/v1/memories/{memory_id}",
        headers=headers,
        json={"status": "active", "importance": "high"},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["status"] == "active"
    assert patch_response.json()["importance"] == "high"

    delete_response = await client.delete(f"/api/v1/memories/{memory_id}", headers=headers)
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["status"] == "forgotten"


async def test_memory_mounts_hide_forgotten_memory_content(client: AsyncClient) -> None:
    body, headers = await _register(client)
    user_id = UUID(body["user"]["id"])
    async with SessionFactory() as db:
        conversation = Conversation(
            user_id=user_id,
            title="Memory mount visibility",
            mode="single",
            agent_ids=["test-agent"],
        )
        db.add(conversation)
        await db.flush()
        memory = Memory(
            owner_user_id=user_id,
            scope_type="user",
            scope_id=None,
            container_tag=f"agenthub:user:{user_id}",
            kind="preference",
            content="以后默认使用中文回复。",
            importance="high",
            confidence=0.9,
            status="active",
            normalized_key="preference:response_language",
            source_type="manual",
            source_id=None,
            memory_metadata={},
        )
        db.add(memory)
        await db.flush()
        mount = MemoryMount(
            conversation_id=conversation.id,
            agent_message_id=None,
            memory_id=memory.id,
            mount_reason="important_preference",
            rank_score=5.0,
        )
        db.add(mount)
        await db.commit()
        conversation_id = str(conversation.id)
        memory_id = str(memory.id)

    before_forget = await client.get(
        f"/api/v1/conversations/{conversation_id}/memory-mounts",
        headers=headers,
    )
    assert before_forget.status_code == 200, before_forget.text
    assert before_forget.json()["items"][0]["memory"]["content"] == "以后默认使用中文回复。"

    delete_response = await client.delete(f"/api/v1/memories/{memory_id}", headers=headers)
    assert delete_response.status_code == 200, delete_response.text

    after_forget = await client.get(
        f"/api/v1/conversations/{conversation_id}/memory-mounts",
        headers=headers,
    )
    assert after_forget.status_code == 200, after_forget.text
    item = after_forget.json()["items"][0]
    assert item["memory_id"] == memory_id
    assert item["memory"] is None
