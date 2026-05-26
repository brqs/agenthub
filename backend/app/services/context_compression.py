"""Conversation memory compression utilities."""

from __future__ import annotations

import math
import re
from typing import Any

from app.core.config import settings
from app.models.message import Message
from app.services.model_gateway import (
    CompressionModelGateway,
    ModelGatewayUnavailableError,
)

RULES_ALGORITHM_VERSION = "rules-v2"
HYBRID_ALGORITHM_VERSION = "hybrid-llm-v1"
ALGORITHM_VERSION = HYBRID_ALGORITHM_VERSION
TOTAL_TOKEN_BUDGET = 8_000
CRITICAL_FACT_TOKEN_BUDGET = 600
PINNED_TOKEN_BUDGET = 2_000
RECENT_QUERY_LIMIT = 50
COMPRESS_TOKEN_THRESHOLD = 6_000
COMPRESS_MESSAGE_THRESHOLD = 30
COMPRESSED_PIN_TOKEN_LIMIT = 240
SUMMARY_TITLE = "【会话历史摘要】"
SUMMARY_SECTIONS = (
    "用户目标",
    "已确认约束",
    "关键进展",
    "重要代码/文件/错误",
    "未解决问题",
)
KEY_FACT_KEYWORDS = (
    "请记住",
    "记住",
    "我的项目叫",
    "项目叫",
    "项目名称",
    "后端",
    "技术栈",
    "数据库",
    "必须",
    "要求",
    "不要忘记",
)
SUMMARY_PROMPT = """你是 AgentHub 的上下文压缩器。
请压缩以下会话历史，目标是让后续 AI 能正确继续对话。

必须保留：
- 用户目标
- 项目事实
- 技术栈
- 已确认约束
- 已做决策
- 关键代码/文件/错误
- 未解决问题
- 用户明确要求“记住”的内容

禁止：
- 编造信息
- 删除关键事实
- 把重复测试内容大量保留
- 输出无关寒暄

输出格式：

【会话历史摘要】
- 用户目标：
- 关键事实：
- 已确认约束：
- 关键进展：
- 重要代码/文件/错误：
- 未解决问题：
"""


class CompressionUnavailableError(RuntimeError):
    """Raised when LLM compression cannot be used and rules fallback should run."""


def estimate_tokens(text: str) -> int:
    """Cheap token estimator for mixed Chinese/English text."""
    if not text:
        return 0
    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    non_space_chars = sum(1 for char in text if not char.isspace())
    latin_chars = max(non_space_chars - cjk_chars, 0)
    mixed_estimate = (cjk_chars / 1.5) + (latin_chars / 4)
    fallback_estimate = len(text) / 3
    return max(1, math.ceil(max(mixed_estimate, fallback_estimate)))


def truncate_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    head = normalized[: max_chars // 2].rstrip()
    tail = normalized[-max_chars // 2 :].lstrip()
    return f"{head} ... {tail}"


def blocks_to_text(blocks: list[dict[str, Any]]) -> str:
    """Flatten ContentBlocks to plain text for LLM consumption."""
    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "code":
            language = block.get("language", "")
            parts.append(f"```{language}\n{block.get('code', '')}\n```")
        elif block_type == "diff":
            parts.append(
                f"--- {block.get('filename')}\n{block.get('before')}\n+++\n{block.get('after')}"
            )
        elif block_type == "web_preview":
            title = block.get("title")
            parts.append(f"[Web Preview: {title or block.get('url')}]")
        elif block_type == "file":
            parts.append(f"[File: {block.get('filename')}]")
    return "\n".join(part for part in parts if part)


def _summarize_text(text: str, max_chars: int = 360) -> str:
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？；;])\s*", text)
        if part.strip()
    ]
    if not sentences:
        return truncate_text(text, max_chars)
    if len(sentences) == 1:
        return truncate_text(sentences[0], max_chars)
    joined = f"{sentences[0]} {sentences[-1]}"
    return truncate_text(joined, max_chars)


def _split_fact_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [
        sentence.strip(" -：:。.!?；;")
        for sentence in re.split(r"(?<=[。！？；;.!?])\s*|\n+", normalized)
        if sentence.strip(" -：:。.!?；;")
    ]


def extract_key_facts(text: str) -> list[str]:
    """Extract durable user facts from low-cost text rules."""
    facts: list[str] = []
    for sentence in _split_fact_sentences(text):
        if any(keyword in sentence for keyword in KEY_FACT_KEYWORDS):
            facts.append(truncate_text(sentence, 260))
    return _dedupe_items(facts)


class CriticalFactExtractor:
    """Extract facts that must survive lossy compression."""

    @staticmethod
    def from_messages(messages: list[Message]) -> list[str]:
        facts: list[str] = []
        for message in messages:
            if message.role != "user":
                continue
            facts.extend(extract_key_facts(blocks_to_text(message.content)))
        return _dedupe_items(facts)


class SummaryValidator:
    """Validate and repair summaries so critical facts are not lost."""

    _term_pattern = re.compile(r"\b[A-Za-z][A-Za-z0-9_.+-]{2,}\b")

    @classmethod
    def validate(cls, summary: str, critical_facts: list[str]) -> str:
        cleaned = summary.strip()
        if not cleaned:
            raise CompressionUnavailableError("empty summary")
        if not cleaned.startswith(SUMMARY_TITLE):
            cleaned = f"{SUMMARY_TITLE}\n{cleaned}"

        missing = [
            fact
            for fact in _dedupe_items(critical_facts)
            if not cls._summary_contains_fact(cleaned, fact)
        ]
        if missing:
            supplements = "；".join(truncate_text(fact, 220) for fact in missing[:8])
            cleaned += f"\n- 关键事实补充：{supplements}"
        return cleaned

    @classmethod
    def _summary_contains_fact(cls, summary: str, fact: str) -> bool:
        terms = cls._term_pattern.findall(fact)
        lower_summary = summary.lower()
        if terms:
            return all(term.lower() in lower_summary for term in terms)
        return _dedupe_key(fact) in _dedupe_key(summary)


class ContextCompressor:
    """Hybrid LLM compressor with deterministic rules fallback."""

    def __init__(
        self,
        summary_client: CompressionModelGateway | None = None,
        validator: SummaryValidator | None = None,
    ) -> None:
        self.summary_client = summary_client or CompressionModelGateway()
        self.validator = validator or SummaryValidator()

    async def compress(
        self,
        messages: list[Message],
        existing_summary: str = "",
    ) -> tuple[str, str]:
        critical_facts = _dedupe_items(
            CriticalFactExtractor.from_messages(messages)
            + extract_key_facts(existing_summary)
        )
        if settings.context_compression_mode.lower() == "hybrid":
            try:
                llm_summary = await self._summarize_with_llm(
                    messages,
                    critical_facts,
                    existing_summary,
                )
                return (
                    self.validator.validate(llm_summary, critical_facts),
                    HYBRID_ALGORITHM_VERSION,
                )
            except CompressionUnavailableError:
                pass

        return _summarize_messages(messages, existing_summary), RULES_ALGORITHM_VERSION

    async def _summarize_with_llm(
        self,
        messages: list[Message],
        critical_facts: list[str],
        existing_summary: str,
    ) -> str:
        facts_text = "\n".join(f"- {fact}" for fact in critical_facts) or "暂无"
        existing_text = existing_summary.strip() or "暂无"
        history_text = _format_messages_for_summary(messages)
        if not history_text:
            raise CompressionUnavailableError("empty history")

        user_prompt = (
            "不可丢失关键事实：\n"
            f"{facts_text}\n\n"
            "已有压缩摘要，如果有，请与新历史合并去重：\n"
            f"{existing_text}\n\n"
            "待压缩会话历史：\n"
            f"{history_text}"
        )
        try:
            return await self.summary_client.complete(
                system=SUMMARY_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.context_summary_max_tokens,
            )
        except ModelGatewayUnavailableError as exc:
            raise CompressionUnavailableError(str(exc)) from exc


def _format_messages_for_summary(messages: list[Message]) -> str:
    formatted: list[str] = []
    for message in messages:
        role = "assistant" if message.role == "agent" else message.role
        text = truncate_text(blocks_to_text(message.content), 1400)
        if not text:
            continue
        formatted.append(f"[{message.created_at:%Y-%m-%d %H:%M}] {role}: {text}")
    return "\n\n".join(formatted)


def _summarize_blocks(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "text":
            parts.append(_summarize_text(block.get("text", "")))
        elif block_type == "code":
            language = block.get("language") or "plain"
            code = block.get("code", "")
            parts.append(
                f"code block in {language}, about {estimate_tokens(code)} estimated tokens"
            )
        elif block_type == "diff":
            parts.append(f"diff for {block.get('filename') or 'unknown file'}")
        elif block_type == "web_preview":
            parts.append(f"web preview {block.get('title') or block.get('url')}")
        elif block_type == "file":
            parts.append(f"file attachment {block.get('filename')}")
    return "; ".join(part for part in parts if part)


def _dedupe_key(text: str) -> str:
    text = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.strip(" -：:。.!?；;")


def _dedupe_items(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_summary_item(item)
        if not cleaned:
            continue
        key = _dedupe_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _clean_summary_item(item: str) -> str:
    cleaned = re.sub(r"\s+", " ", item).strip()
    cleaned = cleaned.replace(SUMMARY_TITLE, "").strip(" -：:;；")
    section_names = "|".join(re.escape(section) for section in SUMMARY_SECTIONS)
    cleaned = re.sub(rf"^-?\s*({section_names}|关键事实)[：:]\s*", "", cleaned).strip()
    if not cleaned or cleaned == "暂无":
        return ""
    if SUMMARY_TITLE in cleaned or re.search(rf"-\s*({section_names}|关键事实)[：:]", cleaned):
        return ""
    return cleaned


def _empty_summary_sections() -> dict[str, list[str]]:
    return {section: [] for section in SUMMARY_SECTIONS}


def _parse_existing_summary(existing_summary: str) -> dict[str, list[str]]:
    sections = _empty_summary_sections()
    if not existing_summary.strip():
        return sections

    sections["已确认约束"].extend(extract_key_facts(existing_summary))
    section_names = "|".join(re.escape(section) for section in SUMMARY_SECTIONS)
    for line in existing_summary.splitlines():
        match = re.match(rf"^-\s*({section_names}|关键事实)[：:]\s*(.*)$", line.strip())
        if not match:
            continue
        section, body = match.groups()
        target_section = "已确认约束" if section == "关键事实" else section
        sections[target_section].extend(body.split("；"))
    return {section: _dedupe_items(items) for section, items in sections.items()}


def _append_summary_item(
    sections: dict[str, list[str]],
    section: str,
    item: str,
) -> None:
    cleaned = _clean_summary_item(item)
    if cleaned:
        sections[section].append(cleaned)


def _has_summary_item(sections: dict[str, list[str]], item: str) -> bool:
    key = _dedupe_key(item)
    return any(
        _dedupe_key(existing) == key
        for values in sections.values()
        for existing in values
    )


def _summarize_messages(messages: list[Message], existing_summary: str = "") -> str:
    sections = _parse_existing_summary(existing_summary)

    for message in messages:
        raw_text = blocks_to_text(message.content)
        summary = _summarize_blocks(message.content)
        if not summary:
            continue
        prefix = f"{message.created_at:%Y-%m-%d %H:%M} "
        lowered = summary.lower()
        if message.role == "user":
            _append_summary_item(sections, "用户目标", prefix + summary)
            for fact in extract_key_facts(raw_text):
                _append_summary_item(sections, "已确认约束", fact)
            if "?" in summary or "？" in summary:
                _append_summary_item(sections, "未解决问题", summary)
        elif message.role == "agent":
            if not _has_summary_item(sections, summary):
                _append_summary_item(sections, "关键进展", prefix + summary)
            if any(word in lowered for word in ("error", "exception", "file", "diff", "code")):
                _append_summary_item(sections, "重要代码/文件/错误", summary)

    def join_limited(items: list[str], max_items: int, max_chars: int) -> str:
        deduped = _dedupe_items(items)
        text = "；".join(truncate_text(item, max_chars) for item in deduped[-max_items:])
        return text or "暂无"

    return "\n".join(
        [
            SUMMARY_TITLE,
            f"- 用户目标：{join_limited(sections['用户目标'], 8, 220)}",
            f"- 已确认约束：{join_limited(sections['已确认约束'], 8, 220)}",
            f"- 关键进展：{join_limited(sections['关键进展'], 8, 220)}",
            f"- 重要代码/文件/错误：{join_limited(sections['重要代码/文件/错误'], 6, 180)}",
            f"- 未解决问题：{join_limited(sections['未解决问题'], 5, 180)}",
        ]
    )
