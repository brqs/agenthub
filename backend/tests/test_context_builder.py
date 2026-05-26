"""ContextBuilder memory and compression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.models.conversation import Conversation
from app.models.conversation_memory import ConversationMemory
from app.models.message import Message
from app.models.user import User
from app.services.context_builder import build_context
from app.services.context_compression import (
    CompressionUnavailableError,
    estimate_tokens,
)
from app.services.model_gateway import CompressionModelGateway

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
def use_rules_compression_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "context_compression_mode", "rules")
    monkeypatch.setattr(settings, "context_compression_provider", "deepseek")
    monkeypatch.setattr(settings, "context_compression_model", "deepseek-v4-flash")
    monkeypatch.setattr(settings, "context_compression_api_key", "")
    monkeypatch.setattr(settings, "context_compression_base_url", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")


async def _create_conversation() -> UUID:
    async with SessionFactory() as db:
        user = User(username=f"ctx_{uuid4().hex[:16]}", password_hash="hash")
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="Context test",
            mode="single",
            agent_ids=["test-agent"],
        )
        db.add(conversation)
        await db.commit()
        return conversation.id


async def _insert_text_messages(
    conversation_id: UUID,
    texts: list[tuple[str, str]],
    *,
    start: datetime | None = None,
) -> list[UUID]:
    start = start or datetime.now(UTC)
    ids: list[UUID] = []
    async with SessionFactory() as db:
        for index, (role, text) in enumerate(texts):
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=[{"type": "text", "text": text}],
                status="done",
                created_at=start + timedelta(seconds=index),
            )
            db.add(message)
            await db.flush()
            ids.append(message.id)
        await db.commit()
    return ids


async def test_small_history_returns_raw_messages_without_memory() -> None:
    conversation_id = await _create_conversation()
    await _insert_text_messages(
        conversation_id,
        [
            ("user", "My project is AgentHub."),
            ("agent", "I will remember AgentHub."),
            ("user", "The backend uses FastAPI."),
        ],
    )

    async with SessionFactory() as db:
        context = await build_context(db, conversation_id)
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is None
    assert [message.role for message in context] == ["user", "assistant", "user"]
    assert "AgentHub" in context[0].content
    assert "FastAPI" in context[-1].content


async def test_pending_and_error_messages_are_excluded() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        done = Message(
            conversation_id=conversation_id,
            role="user",
            content=[{"type": "text", "text": "keep me"}],
            status="done",
        )
        pending = Message(
            conversation_id=conversation_id,
            role="agent",
            content=[{"type": "text", "text": "pending should not appear"}],
            status="pending",
        )
        error = Message(
            conversation_id=conversation_id,
            role="agent",
            content=[{"type": "text", "text": "error should not appear"}],
            status="error",
        )
        db.add_all([done, pending, error])
        await db.commit()

    async with SessionFactory() as db:
        context = await build_context(db, conversation_id)

    joined = "\n".join(message.content for message in context)
    assert "keep me" in joined
    assert "pending should not appear" not in joined
    assert "error should not appear" not in joined


async def test_long_history_creates_summary_and_keeps_recent_messages() -> None:
    conversation_id = await _create_conversation()
    old_text = "用户要求：AgentHub 必须记住历史消息，并且后端使用 FastAPI。"
    recent_text = "最新问题：请继续基于刚才的方案回答。"
    texts = [
        ("user" if index % 2 == 0 else "agent", f"{old_text} 第 {index} 轮。" * 20)
        for index in range(34)
    ]
    texts.extend([("user", recent_text), ("agent", "我会继续。")])
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        context = await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.summary_text.startswith("【会话历史摘要】")
    assert memory.summarized_until_message_id is not None
    assert memory.source_message_count > 0
    assert memory.source_token_estimate > memory.summary_token_estimate
    assert context[0].role == "system"
    assert "Earlier compressed conversation memory" in context[0].content
    assert recent_text in "\n".join(message.content for message in context)


async def test_key_facts_survive_long_history_summary() -> None:
    conversation_id = await _create_conversation()
    texts = [
        (
            "user",
            "请记住：我的项目叫 AgentHub，后端技术栈是 FastAPI，数据库是 PostgreSQL。",
        )
    ]
    texts.extend(
        ("user" if index % 2 == 0 else "agent", f"这是普通上下文压缩测试内容 {index}。" * 20)
        for index in range(40)
    )
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.algorithm_version == "rules-v2"
    assert "AgentHub" in memory.summary_text
    assert "FastAPI" in memory.summary_text
    assert "PostgreSQL" in memory.summary_text


async def test_hybrid_compression_uses_deepseek_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "context_compression_mode", "hybrid")
    monkeypatch.setattr(settings, "context_compression_api_key", "sk-test")

    async def fake_summarize(
        self: CompressionModelGateway,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        _ = (self, system, user_prompt, max_tokens)
        return "\n".join(
            [
                "【会话历史摘要】",
                "- 用户目标：验证 AgentHub 长会话压缩",
                "- 关键事实：AgentHub 使用 FastAPI 和 PostgreSQL",
                "- 已确认约束：保留核心事实",
                "- 关键进展：AI 摘要压缩已执行",
                "- 重要代码/文件/错误：暂无",
                "- 未解决问题：暂无",
            ]
        )

    monkeypatch.setattr(CompressionModelGateway, "complete", fake_summarize)
    conversation_id = await _create_conversation()
    texts = [
        (
            "user",
            "请记住：我的项目叫 AgentHub，后端技术栈是 FastAPI，数据库是 PostgreSQL。",
        )
    ]
    texts.extend(
        ("user" if index % 2 == 0 else "agent", f"重复测试内容 {index}。" * 30)
        for index in range(40)
    )
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        context = await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.algorithm_version == "hybrid-llm-v1"
    assert memory.summary_token_estimate < memory.source_token_estimate
    assert "AI 摘要压缩已执行" in memory.summary_text
    joined = "\n".join(message.content for message in context)
    assert "Critical facts and constraints" in joined
    assert "AgentHub" in joined
    assert "FastAPI" in joined
    assert "PostgreSQL" in joined


async def test_hybrid_validator_restores_missing_key_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "context_compression_mode", "hybrid")
    monkeypatch.setattr(settings, "context_compression_api_key", "sk-test")

    async def fake_summarize(
        self: CompressionModelGateway,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        _ = (self, system, user_prompt, max_tokens)
        return "\n".join(
            [
                "【会话历史摘要】",
                "- 用户目标：验证 AgentHub 压缩",
                "- 关键事实：AgentHub 使用 FastAPI",
                "- 已确认约束：暂无",
                "- 关键进展：暂无",
                "- 重要代码/文件/错误：暂无",
                "- 未解决问题：暂无",
            ]
        )

    monkeypatch.setattr(CompressionModelGateway, "complete", fake_summarize)
    conversation_id = await _create_conversation()
    texts = [
        (
            "user",
            "请记住：我的项目叫 AgentHub，后端技术栈是 FastAPI，数据库是 PostgreSQL。",
        )
    ]
    texts.extend(
        ("user" if index % 2 == 0 else "agent", f"普通长对话内容 {index}。" * 30)
        for index in range(40)
    )
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.algorithm_version == "hybrid-llm-v1"
    assert "关键事实补充" in memory.summary_text
    assert "PostgreSQL" in memory.summary_text


async def test_hybrid_compression_falls_back_to_rules_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "context_compression_mode", "hybrid")
    monkeypatch.setattr(settings, "context_compression_api_key", "sk-test")

    async def fake_summarize(
        self: CompressionModelGateway,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        _ = (self, system, user_prompt, max_tokens)
        raise CompressionUnavailableError("upstream unavailable")

    monkeypatch.setattr(CompressionModelGateway, "complete", fake_summarize)
    conversation_id = await _create_conversation()
    texts = [
        (
            "user",
            "请记住：我的项目叫 AgentHub，后端技术栈是 FastAPI，数据库是 PostgreSQL。",
        )
    ]
    texts.extend(
        ("user" if index % 2 == 0 else "agent", f"兜底测试内容 {index}。" * 30)
        for index in range(40)
    )
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        context = await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.algorithm_version == "rules-v2"
    joined = "\n".join(message.content for message in context)
    assert "AgentHub" in joined
    assert "FastAPI" in joined
    assert "PostgreSQL" in joined


async def test_old_pinned_message_is_kept_with_memory_context() -> None:
    conversation_id = await _create_conversation()
    pinned_id = (
        await _insert_text_messages(
            conversation_id,
            [("user", "PIN: 项目名称是 AgentHub，数据库使用 PostgreSQL。")],
        )
    )[0]
    filler = [
        ("user" if index % 2 == 0 else "agent", f"普通长对话内容 {index}。" * 40)
        for index in range(36)
    ]
    await _insert_text_messages(
        conversation_id,
        filler,
        start=datetime.now(UTC) + timedelta(days=1),
    )

    async with SessionFactory() as db:
        pinned = await db.get(Message, pinned_id)
        assert pinned is not None
        pinned.is_pinned = True
        await db.commit()

    async with SessionFactory() as db:
        context = await build_context(db, conversation_id)

    joined = "\n".join(message.content for message in context)
    assert "项目名称是 AgentHub" in joined
    assert "PostgreSQL" in joined
    assert any(message.role == "system" for message in context)


async def test_existing_memory_does_not_resummarize_same_messages() -> None:
    conversation_id = await _create_conversation()
    texts = [
        ("user" if index % 2 == 0 else "agent", f"历史消息 {index}。" * 60)
        for index in range(36)
    ]
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        first_memory = await db.get(ConversationMemory, conversation_id)
        assert first_memory is not None
        first_count = first_memory.source_message_count
        first_until = first_memory.summarized_until_message_id

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        second_memory = await db.get(ConversationMemory, conversation_id)

    assert second_memory is not None
    assert second_memory.source_message_count == first_count
    assert second_memory.summarized_until_message_id == first_until


async def test_summary_update_does_not_nest_previous_summary() -> None:
    conversation_id = await _create_conversation()
    first_batch = [
        ("user" if index % 2 == 0 else "agent", f"第一批历史消息 {index}。" * 40)
        for index in range(36)
    ]
    await _insert_text_messages(conversation_id, first_batch)

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()

    second_batch = [
        ("user" if index % 2 == 0 else "agent", f"第二批历史消息 {index}。" * 40)
        for index in range(24)
    ]
    await _insert_text_messages(
        conversation_id,
        second_batch,
        start=datetime.now(UTC) + timedelta(days=1),
    )

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.summary_text.count("【会话历史摘要】") == 1
    assert "【会话历史摘要】 -" not in memory.summary_text


async def test_repeated_memory_text_is_deduplicated_in_summary() -> None:
    conversation_id = await _create_conversation()
    repeated = "这是上下文压缩测试内容，请不要忘记这些关键信息。"
    texts = [
        ("user" if index % 2 == 0 else "agent", repeated)
        for index in range(40)
    ]
    await _insert_text_messages(conversation_id, texts)

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert memory.summary_text.count(repeated.rstrip("。")) <= 2


async def test_multimodal_blocks_are_compressed_readably() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        for index in range(32):
            db.add(
                Message(
                    conversation_id=conversation_id,
                    role="user" if index % 2 == 0 else "agent",
                    content=[
                        {"type": "code", "language": "python", "code": "print('hello')\n" * 80},
                        {
                            "type": "diff",
                            "filename": "app.py",
                            "before": "old",
                            "after": "new",
                        },
                        {"type": "web_preview", "url": "https://example.com"},
                        {
                            "type": "file",
                            "filename": "notes.md",
                            "url": "/files/notes.md",
                            "size": 10,
                            "mime_type": "text/markdown",
                        },
                    ],
                    status="done",
                )
            )
        await db.commit()

    async with SessionFactory() as db:
        await build_context(db, conversation_id)
        await db.commit()
        memory = await db.get(ConversationMemory, conversation_id)

    assert memory is not None
    assert "code block in python" in memory.summary_text
    assert "diff for app.py" in memory.summary_text
    assert "web preview" in memory.summary_text
    assert "file attachment notes.md" in memory.summary_text


async def test_token_estimator_is_low_cost_and_non_zero() -> None:
    assert estimate_tokens("AgentHub uses FastAPI") > 0
    assert estimate_tokens("项目使用 FastAPI 和 PostgreSQL") > 0
