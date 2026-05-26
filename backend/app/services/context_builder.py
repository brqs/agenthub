"""Build compressed conversation context for agent adapters."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import ChatMessage
from app.core.config import settings
from app.models.conversation_memory import ConversationMemory
from app.models.message import Message
from app.services.context_compression import (
    ALGORITHM_VERSION,
    COMPRESS_MESSAGE_THRESHOLD,
    COMPRESS_TOKEN_THRESHOLD,
    COMPRESSED_PIN_TOKEN_LIMIT,
    CRITICAL_FACT_TOKEN_BUDGET,
    HYBRID_ALGORITHM_VERSION,
    PINNED_TOKEN_BUDGET,
    RECENT_QUERY_LIMIT,
    RULES_ALGORITHM_VERSION,
    TOTAL_TOKEN_BUDGET,
    ContextCompressor,
    CriticalFactExtractor,
    blocks_to_text,
    estimate_tokens,
    truncate_text,
)
from app.services.model_gateway import has_configured_compression_api_key


def _message_role(message: Message) -> str | None:
    role = "assistant" if message.role == "agent" else message.role
    if role not in ("user", "assistant", "system"):
        return None
    return role


def _message_to_chat(message: Message, *, compressed_pin: bool = False) -> ChatMessage | None:
    role = _message_role(message)
    if role is None:
        return None
    text = blocks_to_text(message.content)
    if compressed_pin:
        text = (
            "[Pinned message summary] "
            f"{truncate_text(text, COMPRESSED_PIN_TOKEN_LIMIT * 3)}"
        )
    return ChatMessage(role=role, content=text)


async def _get_or_create_memory(
    db: AsyncSession, conversation_id: UUID
) -> ConversationMemory:
    memory = await db.get(ConversationMemory, conversation_id)
    if memory:
        return memory
    memory = ConversationMemory(
        conversation_id=conversation_id,
        summary_text="",
        source_message_count=0,
        source_token_estimate=0,
        summary_token_estimate=0,
        algorithm_version=ALGORITHM_VERSION,
    )
    db.add(memory)
    await db.flush()
    return memory


def _message_position(messages: list[Message], message_id: UUID | None) -> int:
    if message_id is None:
        return -1
    for index, message in enumerate(messages):
        if message.id == message_id:
            return index
    return -1


async def _refresh_memory_if_needed(
    db: AsyncSession,
    conversation_id: UUID,
    messages: list[Message],
) -> ConversationMemory | None:
    recent_raw_keep = max(settings.context_recent_raw_keep, 1)
    if len(messages) <= recent_raw_keep:
        return await db.get(ConversationMemory, conversation_id)

    memory = await _get_or_create_memory(db, conversation_id)
    wants_hybrid_upgrade = (
        settings.context_compression_mode.lower() == "hybrid"
        and has_configured_compression_api_key()
        and memory.algorithm_version != HYBRID_ALGORITHM_VERSION
    )
    is_algorithm_upgrade = (
        memory.algorithm_version not in {RULES_ALGORITHM_VERSION, HYBRID_ALGORITHM_VERSION}
        or wants_hybrid_upgrade
    )
    start_index = (
        0
        if is_algorithm_upgrade
        else _message_position(messages, memory.summarized_until_message_id) + 1
    )
    end_index = max(len(messages) - recent_raw_keep, start_index)
    candidates = messages[start_index:end_index]
    candidate_tokens = sum(
        estimate_tokens(blocks_to_text(message.content)) for message in candidates
    )

    should_compress = (
        bool(candidates)
        and (
            candidate_tokens >= COMPRESS_TOKEN_THRESHOLD
            or len(messages) >= COMPRESS_MESSAGE_THRESHOLD
        )
    )
    if not should_compress:
        return memory

    existing_summary = "" if is_algorithm_upgrade else memory.summary_text
    summary_text, algorithm_version = await ContextCompressor().compress(
        candidates,
        existing_summary,
    )
    memory.summary_text = summary_text
    memory.summarized_until_message_id = candidates[-1].id
    memory.source_message_count = (
        len(candidates)
        if is_algorithm_upgrade
        else memory.source_message_count + len(candidates)
    )
    memory.source_token_estimate = (
        candidate_tokens
        if is_algorithm_upgrade
        else memory.source_token_estimate + candidate_tokens
    )
    memory.summary_token_estimate = estimate_tokens(memory.summary_text)
    memory.algorithm_version = algorithm_version
    await db.flush()
    return memory


def _append_with_budget(
    output: list[ChatMessage],
    message: ChatMessage,
    used_tokens: int,
    token_budget: int,
) -> int:
    tokens = estimate_tokens(message.content)
    if used_tokens + tokens <= token_budget or not output:
        output.append(message)
        return used_tokens + tokens
    return used_tokens


async def build_context(
    db: AsyncSession,
    conversation_id: UUID,
    max_tokens: int = TOTAL_TOKEN_BUDGET,
) -> list[ChatMessage]:
    """Build compressed context from memory, pinned messages, and recent messages."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.status.in_(["done", "streaming"]))
        .order_by(Message.created_at.asc())
    )
    messages = list((await db.execute(stmt)).scalars().all())
    memory = await _refresh_memory_if_needed(db, conversation_id, messages)
    critical_facts = CriticalFactExtractor.from_messages(messages)

    context: list[ChatMessage] = []
    used_tokens = 0

    if memory and memory.summary_text.strip():
        summary_budget = min(max_tokens, max(settings.context_summary_max_tokens, 1))
        summary = truncate_text(memory.summary_text, summary_budget * 3)
        summary_message = ChatMessage(
            role="system",
            content=f"Earlier compressed conversation memory:\n{summary}",
        )
        used_tokens = _append_with_budget(
            context, summary_message, used_tokens, summary_budget
        )

    if critical_facts:
        facts_text = "\n".join(f"- {fact}" for fact in critical_facts[-12:])
        facts_message = ChatMessage(
            role="system",
            content=(
                "Critical facts and constraints that must not be lost:\n"
                f"{facts_text}"
            ),
        )
        used_tokens = _append_with_budget(
            context,
            facts_message,
            used_tokens,
            min(max_tokens, used_tokens + CRITICAL_FACT_TOKEN_BUDGET),
        )

    summarized_until = memory.summarized_until_message_id if memory else None
    recent_floor = _message_position(messages, summarized_until)
    recent_candidates = messages[max(recent_floor + 1, len(messages) - RECENT_QUERY_LIMIT) :]
    recent_ids = {message.id for message in recent_candidates}

    pinned_messages = [
        message
        for message in messages
        if message.is_pinned and message.id not in recent_ids
    ]
    pinned_used = 0
    for message in pinned_messages:
        chat_message = _message_to_chat(message)
        if chat_message is None:
            continue
        tokens = estimate_tokens(chat_message.content)
        if pinned_used + tokens <= PINNED_TOKEN_BUDGET:
            context.append(chat_message)
            pinned_used += tokens
            used_tokens += tokens
            continue
        compressed = _message_to_chat(message, compressed_pin=True)
        if compressed is not None:
            context.append(compressed)
            compressed_tokens = estimate_tokens(compressed.content)
            pinned_used += compressed_tokens
            used_tokens += compressed_tokens

    remaining_budget = max(max_tokens - used_tokens, 1)
    recent_context: list[ChatMessage] = []
    recent_used = 0
    for message in reversed(recent_candidates):
        if message.is_pinned and message.id not in recent_ids:
            continue
        chat_message = _message_to_chat(message)
        if chat_message is None:
            continue
        tokens = estimate_tokens(chat_message.content)
        if recent_used + tokens > remaining_budget and recent_context:
            break
        recent_context.insert(0, chat_message)
        recent_used += tokens

    context.extend(recent_context)
    return context
