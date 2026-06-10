"""Supermemory-style local semantic memory hub.

This service owns long-term semantic memories and per-turn dynamic mounts. It
does not replace Orchestrator run/task/attempt tables, which remain the
authoritative execution facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import ChatMessage
from app.models.conversation import Conversation
from app.models.memory import Memory, MemoryMount
from app.models.message import Message
from app.services.context.compression import message_to_text, truncate_text

ACTIVE_MEMORY_STATUSES = {"active", "candidate"}
PERSISTENT_MEMORY_MARKERS = (
    "请记住",
    "记住：",
    "以后默认",
    "从今以后",
    "我喜欢",
    "我偏好",
    "每次都",
    "始终",
    "永远",
)
PERSISTENT_CONSTRAINT_PATTERNS = (
    re.compile(r"(?:所有|任何|以后|始终).{0,20}(?:必须|不能|不要|只能)"),
    re.compile(r"(?:必须|不能|不要|只能).{0,20}(?:所有|任何|以后|始终)"),
)
CANDIDATE_MEMORY_MARKERS = (
    "项目目标是",
    "本项目使用",
    "项目采用",
    "我们决定",
    "已经确认",
    "术语定义",
)
ONE_OFF_REQUEST_PREFIXES = (
    "帮我",
    "请你",
    "能不能",
    "可不可以",
    "麻烦",
    "给我",
    "改一下",
)
NON_MEMORY_TEXT_MARKERS = (
    "execution summary",
    "planned ",
    "tool call",
    "调用失败",
    "正在处理",
    "正在组织回复",
    "对不起",
    "抱歉",
)
SECRET_MARKERS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "密码",
    "密钥",
    "access key",
    "authorization",
    "bearer ",
)
TEMPORAL_MARKERS = ("今天", "明天", "刚刚", "这次", "本次", "临时", "暂时")
LANGUAGE_MEMORY_KEY = "preference:response_language"
MAX_MEMORY_CONTENT_CHARS = 800
MAX_MOUNTED_MEMORIES = 8


@dataclass(frozen=True)
class MemoryCandidate:
    scope_type: str
    scope_id: UUID | None
    kind: str
    content: str
    importance: str
    confidence: float
    status: str
    normalized_key: str | None
    valid_until: datetime | None
    source_type: str
    source_id: UUID | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RecalledMemory:
    memory: Memory
    score: float
    reason: str


class MemoryHubService:
    """Local MemoryHub provider with deterministic extraction and recall."""

    async def list_memories(
        self,
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        scope_type: str | None = None,
        scope_id: UUID | None = None,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Memory], int]:
        stmt = select(Memory).where(Memory.owner_user_id == owner_user_id)
        if scope_type:
            stmt = stmt.where(Memory.scope_type == scope_type)
        if scope_id:
            stmt = stmt.where(Memory.scope_id == scope_id)
        if kind:
            stmt = stmt.where(Memory.kind == kind)
        if status:
            stmt = stmt.where(Memory.status == status)
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(desc(Memory.updated_at), desc(Memory.created_at)).limit(limit)
            )
        ).scalars().all()
        return list(rows), total

    async def list_conversation_memory_hub(
        self,
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        conversation: Conversation,
        limit: int = 100,
    ) -> dict[str, list[Memory]]:
        limit = max(1, min(limit, 200))
        scoped_tags = {
            _container_tag(
                "conversation",
                conversation.id,
                owner_user_id=owner_user_id,
            ),
            _container_tag(
                "workspace",
                conversation.id,
                owner_user_id=owner_user_id,
            ),
        }
        if conversation.mode == "group":
            scoped_tags.add(
                _container_tag(
                    "group",
                    conversation.id,
                    owner_user_id=owner_user_id,
                )
            )
        scoped_rows = list(
            (
                await db.execute(
                    select(Memory)
                    .where(Memory.owner_user_id == owner_user_id)
                    .where(Memory.status.in_(("active", "candidate")))
                    .where(Memory.container_tag.in_(scoped_tags))
                    .order_by(desc(Memory.updated_at), desc(Memory.created_at))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        user_rows = list(
            (
                await db.execute(
                    select(Memory)
                    .where(Memory.owner_user_id == owner_user_id)
                    .where(Memory.status.in_(("active", "candidate")))
                    .where(Memory.scope_type == "user")
                    .order_by(desc(Memory.updated_at), desc(Memory.created_at))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return {
            "scoped_active": [
                item for item in scoped_rows if item.status == "active"
            ],
            "scoped_candidates": [
                item for item in scoped_rows if item.status == "candidate"
            ],
            "user_active": [
                item for item in user_rows if item.status == "active"
            ],
            "user_candidates": [
                item for item in user_rows if item.status == "candidate"
            ],
        }

    async def update_memory(
        self,
        db: AsyncSession,
        memory: Memory,
        *,
        content: str | None = None,
        importance: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        valid_until: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        if content is not None:
            memory.content = truncate_text(content.strip(), MAX_MEMORY_CONTENT_CHARS)
            memory.normalized_key = memory.normalized_key or _normalized_key(
                kind or memory.kind,
                memory.content,
            )
        if importance is not None:
            memory.importance = importance
        if status is not None:
            memory.status = status
        if kind is not None:
            memory.kind = kind
        if valid_until is not None:
            memory.valid_until = valid_until
        if metadata is not None:
            memory.memory_metadata = metadata
        await db.flush()
        return memory

    async def forget_memory(self, db: AsyncSession, memory: Memory) -> Memory:
        memory.status = "forgotten"
        await db.flush()
        return memory

    async def extract_candidates_for_terminal_message(
        self,
        db: AsyncSession,
        *,
        agent_message: Message,
    ) -> list[Memory]:
        conversation = await db.get(Conversation, agent_message.conversation_id)
        if conversation is None:
            return []

        source_messages: list[Message] = []
        if agent_message.reply_to_id:
            parent = await db.get(Message, agent_message.reply_to_id)
            if parent is not None and parent.role == "user":
                source_messages.append(parent)

        created: list[Memory] = []
        for source_message in source_messages:
            text = message_to_text(source_message, include_agent_label=False)
            for candidate in self.extract_candidates_from_text(
                text,
                owner_user_id=conversation.user_id,
                conversation_id=conversation.id,
                source_type="message",
                source_id=source_message.id,
            ):
                memory = await self._upsert_candidate(db, candidate, conversation)
                if memory is not None:
                    created.append(memory)
        return created

    def extract_candidates_from_text(
        self,
        text: str,
        *,
        owner_user_id: UUID,
        conversation_id: UUID,
        source_type: str,
        source_id: UUID | None,
    ) -> list[MemoryCandidate]:
        cleaned = _clean_memory_text(text)
        if not cleaned:
            return []
        sentences = _candidate_sentences(cleaned)
        candidates: list[MemoryCandidate] = []
        for sentence in sentences:
            if _looks_sensitive(sentence):
                continue
            if _looks_like_non_memory(sentence):
                continue
            is_persistent = _has_persistent_memory_marker(sentence)
            if not is_persistent and not any(
                marker in sentence for marker in CANDIDATE_MEMORY_MARKERS
            ):
                continue
            kind, importance, normalized = _classify_sentence(sentence)
            status = "active" if is_persistent else "candidate"
            if status == "candidate" and importance in {"critical", "high"}:
                importance = "normal"
            valid_until = (
                datetime.now(UTC) + timedelta(days=2)
                if any(marker in sentence for marker in TEMPORAL_MARKERS)
                else None
            )
            candidates.append(
                MemoryCandidate(
                    scope_type="user" if kind == "preference" else "conversation",
                    scope_id=None if kind == "preference" else conversation_id,
                    kind=kind,
                    content=truncate_text(sentence, MAX_MEMORY_CONTENT_CHARS),
                    importance=importance,
                    confidence=0.85 if status == "active" else 0.55,
                    status=status,
                    normalized_key=normalized or _normalized_key(kind, sentence),
                    valid_until=valid_until,
                    source_type=source_type,
                    source_id=source_id,
                    metadata={
                        "extractor": "rules-v1",
                        "container_tag": _container_tag(
                            "user" if kind == "preference" else "conversation",
                            None if kind == "preference" else conversation_id,
                            owner_user_id=owner_user_id,
                        ),
                    },
                )
            )
        return candidates[:5]

    async def build_mount_context(
        self,
        db: AsyncSession,
        *,
        conversation: Conversation,
        query: str,
        current_agent_id: str | None = None,
        agent_message_id: UUID | None = None,
        max_memories: int = MAX_MOUNTED_MEMORIES,
    ) -> ChatMessage | None:
        recalled = await self.recall(
            db,
            owner_user_id=conversation.user_id,
            query=query,
            conversation_id=conversation.id,
            conversation_mode=conversation.mode,
            current_agent_id=current_agent_id,
            limit=max_memories,
        )
        if not recalled:
            return None
        if agent_message_id is not None:
            for item in recalled:
                db.add(
                    MemoryMount(
                        conversation_id=conversation.id,
                        agent_message_id=agent_message_id,
                        memory_id=item.memory.id,
                        mount_reason=item.reason,
                        rank_score=item.score,
                    )
                )
            await db.flush()
        content = _format_mount_context(recalled)
        return ChatMessage(role="system", content=content)

    async def recall(
        self,
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        query: str,
        conversation_id: UUID,
        conversation_mode: str,
        current_agent_id: str | None = None,
        limit: int = MAX_MOUNTED_MEMORIES,
    ) -> list[RecalledMemory]:
        now = datetime.now(UTC)
        allowed_tags = {
            _container_tag("user", None, owner_user_id=owner_user_id),
            _container_tag("conversation", conversation_id, owner_user_id=owner_user_id),
            _container_tag("workspace", conversation_id, owner_user_id=owner_user_id),
        }
        if conversation_mode == "group":
            allowed_tags.add(_container_tag("group", conversation_id, owner_user_id=owner_user_id))
        if current_agent_id:
            allowed_tags.add(f"agenthub:agent:{current_agent_id}")

        stmt = (
            select(Memory)
            .where(Memory.owner_user_id == owner_user_id)
            .where(Memory.status == "active")
            .where(Memory.container_tag.in_(allowed_tags))
            .where(or_(Memory.valid_until.is_(None), Memory.valid_until > now))
            .order_by(desc(Memory.importance), desc(Memory.updated_at))
            .limit(100)
        )
        memories = list((await db.execute(stmt)).scalars().all())
        scored = [
            RecalledMemory(
                memory=memory,
                score=_rank_memory(query, memory),
                reason=_mount_reason(query, memory),
            )
            for memory in memories
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return [item for item in scored if item.score > 0][:limit]

    async def list_mounts(
        self,
        db: AsyncSession,
        *,
        conversation_id: UUID,
        limit: int = 50,
    ) -> tuple[list[MemoryMount], int]:
        stmt = (
            select(MemoryMount)
            .where(MemoryMount.conversation_id == conversation_id)
        )
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await db.execute(stmt.order_by(desc(MemoryMount.created_at)).limit(limit))
        ).scalars().all()
        return list(rows), total

    async def _upsert_candidate(
        self,
        db: AsyncSession,
        candidate: MemoryCandidate,
        conversation: Conversation,
    ) -> Memory | None:
        if not candidate.content.strip():
            return None
        existing: Memory | None = None
        if candidate.normalized_key:
            existing = (
                await db.execute(
                    select(Memory)
                    .where(Memory.owner_user_id == conversation.user_id)
                    .where(Memory.normalized_key == candidate.normalized_key)
                    .where(Memory.status == "active")
                    .order_by(desc(Memory.updated_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
        supersedes_id: UUID | None = None
        if existing is not None and existing.content.strip() != candidate.content.strip():
            existing.status = "archived"
            supersedes_id = existing.id
        elif existing is not None:
            return existing

        memory = Memory(
            owner_user_id=conversation.user_id,
            scope_type=candidate.scope_type,
            scope_id=candidate.scope_id,
            container_tag=_container_tag(
                candidate.scope_type,
                candidate.scope_id,
                owner_user_id=conversation.user_id,
            ),
            kind=candidate.kind,
            content=candidate.content,
            importance=candidate.importance,
            confidence=candidate.confidence,
            status=candidate.status,
            normalized_key=candidate.normalized_key,
            valid_until=candidate.valid_until,
            supersedes_memory_id=supersedes_id,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            memory_metadata=candidate.metadata,
        )
        db.add(memory)
        await db.flush()
        return memory


def _container_tag(scope_type: str, scope_id: UUID | None, *, owner_user_id: UUID) -> str:
    if scope_type == "user":
        return f"agenthub:user:{owner_user_id}"
    if scope_id is not None:
        return f"agenthub:{scope_type}:{scope_id}"
    return f"agenthub:{scope_type}:global"


def _clean_memory_text(text: str) -> str:
    return " ".join(str(text or "").replace("\x00", " ").split())


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return True
    return bool(re.search(r"(sk-[a-zA-Z0-9_-]{16,}|[A-Za-z0-9_=-]{32,})", text))


def _has_persistent_memory_marker(text: str) -> bool:
    return any(marker in text for marker in PERSISTENT_MEMORY_MARKERS) or any(
        pattern.search(text) is not None for pattern in PERSISTENT_CONSTRAINT_PATTERNS
    )


def _looks_like_non_memory(text: str) -> bool:
    normalized = text.strip()
    lowered = normalized.lower()
    if any(marker in lowered for marker in NON_MEMORY_TEXT_MARKERS):
        return True
    if normalized.endswith(("?", "？")):
        return True
    if any(
        normalized.startswith(prefix)
        for prefix in ONE_OFF_REQUEST_PREFIXES
    ) and not _has_persistent_memory_marker(normalized):
        return True
    if normalized.count("#") >= 3 or normalized.count("|") >= 6:
        return True
    return False


def _candidate_sentences(text: str) -> list[str]:
    rough = re.split(r"[。！？!?;\n]+", text)
    return [segment.strip(" -\t") for segment in rough if 8 <= len(segment.strip()) <= 500]


def _classify_sentence(sentence: str) -> tuple[str, str, str | None]:
    if "英文" in sentence and ("回复" in sentence or "回答" in sentence):
        return "preference", "high", LANGUAGE_MEMORY_KEY
    if "中文" in sentence and ("回复" in sentence or "回答" in sentence):
        return "preference", "high", LANGUAGE_MEMORY_KEY
    if any(
        pattern.search(sentence) is not None
        for pattern in PERSISTENT_CONSTRAINT_PATTERNS
    ):
        return "constraint", "critical", None
    if any(marker in sentence for marker in ("已经确认", "我们决定", "就按")):
        return "decision", "high", None
    if any(
        marker in sentence
        for marker in ("我喜欢", "我偏好", "以后默认", "从今以后")
    ):
        return "preference", "high", None
    return "fact", "normal", None


def _normalized_key(kind: str, content: str) -> str:
    tokens = sorted(_tokens(content))
    return f"{kind}:{'-'.join(tokens[:8])}"[:192] if tokens else kind


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", text)
        if len(token.strip()) >= 2
    }


def _rank_memory(query: str, memory: Memory) -> float:
    query_tokens = _tokens(query)
    memory_tokens = _tokens(memory.content)
    overlap = len(query_tokens & memory_tokens)
    importance_boost = {"critical": 5.0, "high": 3.0, "normal": 1.5, "low": 0.5}.get(
        memory.importance,
        1.0,
    )
    if not query_tokens:
        overlap = 1
    score = overlap * 2.0 + importance_boost + float(memory.confidence)
    if memory.scope_type in {"conversation", "workspace", "group"}:
        score += 1.0
    return score


def _mount_reason(query: str, memory: Memory) -> str:
    if memory.importance in {"critical", "high"}:
        return f"important_{memory.kind}"
    if _tokens(query) & _tokens(memory.content):
        return "query_overlap"
    return "profile_context"


def _format_mount_context(recalled: list[RecalledMemory]) -> str:
    important: list[str] = []
    dynamic: list[str] = []
    for item in recalled:
        line = (
            f"- [{item.memory.scope_type}/{item.memory.kind}/"
            f"{item.memory.importance}] {item.memory.content}"
        )
        if item.memory.importance in {"critical", "high"}:
            important.append(line)
        else:
            dynamic.append(line)

    sections = [
        "MemoryHub mounted context:",
        (
            "These semantic memories are preferences/background only. They must not "
            "override current user instructions, current group-scoped agent "
            "membership, or authoritative Orchestrator run/task facts."
        ),
    ]
    if important:
        sections.append("Important memories:\n" + "\n".join(important))
    if dynamic:
        sections.append("Dynamically mounted related memories:\n" + "\n".join(dynamic))
    sections.append(
        "Authoritative execution facts still come from local messages, "
        "workspace state, and Orchestrator structured memory."
    )
    return "\n\n".join(sections)
