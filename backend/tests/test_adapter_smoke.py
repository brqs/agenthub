"""Smoke tests for Agent Adapters — verify stream contract and B1 accumulator consumption."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

import pytest

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.adapters.custom import CustomAdapter
from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.adapters.openai import OpenAIAdapter
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class _ContentAccumulatorProtocol(Protocol):
    def feed(self, chunk: StreamChunk) -> None: ...

    def to_list(self) -> object: ...


def _new_content_accumulator() -> _ContentAccumulatorProtocol:
    stream_module = import_module("app.api.v1.stream")
    accumulator_name = "_ContentAccumulator"
    factory = cast(
        Callable[[], _ContentAccumulatorProtocol],
        getattr(stream_module, accumulator_name),
    )
    return factory()

# ─── Fake upstream clients ───


class FakeClaudeStream:
    """Simulates anthropic AsyncMessageStream."""

    def __init__(self, texts: list[str] | None = None) -> None:
        self._texts = texts or []

    async def __aenter__(self) -> FakeClaudeStream:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def _text_iterator(self) -> AsyncIterator[str]:
        for text in self._texts:
            yield text

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._text_iterator()

    async def close(self) -> None:
        pass


class FakeClaudeMessages:
    def __init__(
        self,
        texts: list[str] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._texts = texts or []
        self._exc = exc

    def stream(self, **kwargs: Any) -> FakeClaudeStream:
        if self._exc:
            raise self._exc
        return FakeClaudeStream(self._texts)


class FakeClaudeClient:
    def __init__(
        self,
        texts: list[str] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.messages = FakeClaudeMessages(texts, exc)


class FakeOpenAIDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class FakeOpenAIChoice:
    def __init__(self, delta: FakeOpenAIDelta) -> None:
        self.delta = delta


class FakeOpenAIChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [FakeOpenAIChoice(FakeOpenAIDelta(content))]


class FakeOpenAIStream:
    def __init__(self, contents: list[str | None]) -> None:
        self._contents = contents

    async def __aiter__(self) -> AsyncIterator[FakeOpenAIChunk]:
        for content in self._contents:
            yield FakeOpenAIChunk(content)


class FakeOpenAICompletions:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._contents = contents or []
        self._exc = exc

    async def create(self, **kwargs: Any) -> FakeOpenAIStream:
        if self._exc:
            raise self._exc
        return FakeOpenAIStream(self._contents)


class FakeOpenAIChat:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.completions = FakeOpenAICompletions(contents, exc)


class FakeOpenAIClient:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.chat = FakeOpenAIChat(contents, exc)


# ─── Helpers ───


async def collect_chunks(
    adapter: BaseAgentAdapter,
    messages: list[ChatMessage],
    config: dict[str, Any] | None = None,
) -> list[StreamChunk]:
    return [chunk async for chunk in adapter.stream(messages, config=config)]


def assert_stream_contract(chunks: list[StreamChunk]) -> None:
    assert len(chunks) >= 1
    assert chunks[0].event_type == "start"

    last = chunks[-1]
    assert last.event_type in ("done", "error")

    open_blocks: set[int] = set()
    block_count = 0
    has_error = any(c.event_type == "error" for c in chunks)

    for chunk in chunks:
        sse = chunk.to_sse()
        assert "event" in sse
        assert "data" in sse

        if chunk.event_type == "block_start":
            assert chunk.block_index is not None
            assert len(open_blocks) == 0, (
                f"block_start while blocks still open: {open_blocks}"
            )
            open_blocks.add(chunk.block_index)
            block_count += 1
        elif chunk.event_type == "block_end":
            assert chunk.block_index is not None
            assert chunk.block_index in open_blocks
            open_blocks.remove(chunk.block_index)
        elif chunk.event_type == "delta":
            assert chunk.block_index is not None
            assert chunk.block_index in open_blocks

    assert len(open_blocks) == 0, f"Unclosed blocks: {open_blocks}"

    if last.event_type == "done":
        assert not has_error, "error chunk appeared before done"
        assert last.total_blocks == block_count


def accumulate_content(chunks: list[StreamChunk]) -> list[dict[str, Any]]:
    acc = _new_content_accumulator()
    for chunk in chunks:
        acc.feed(chunk)
    return cast(list[dict[str, Any]], acc.to_list())


# ─── Tests ───


class TestClaudeAdapterSmoke:
    async def test_claude_adapter_smoke_accumulates_text_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.claude.settings",
            type("S", (), {"anthropic_api_key": "fake-key", "anthropic_base_url": ""})(),
        )
        adapter = ClaudeAdapter(agent_id="test-claude")
        fake_client = FakeClaudeClient(texts=["Hello", " world"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        chunks = await collect_chunks(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert_stream_contract(chunks)
        blocks = accumulate_content(chunks)
        assert any(b.get("type") == "text" and b.get("text") for b in blocks)
        assert len(blocks) == chunks[-1].total_blocks


class TestOpenAIAdapterSmoke:
    async def test_openai_adapter_smoke_accumulates_text_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.openai.settings",
            type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
        )
        adapter = OpenAIAdapter(agent_id="test-openai")
        fake_client = FakeOpenAIClient(contents=["Hello", None, "", " world"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        chunks = await collect_chunks(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert_stream_contract(chunks)
        blocks = accumulate_content(chunks)
        assert any(b.get("type") == "text" and b.get("text") for b in blocks)
        assert len(blocks) == chunks[-1].total_blocks


class TestDeepSeekAdapterSmoke:
    async def test_deepseek_adapter_smoke_uses_openai_compatible_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.openai.settings",
            type("S", (), {"deepseek_api_key": "fake-key", "deepseek_base_url": ""})(),
        )
        adapter = DeepSeekAdapter(agent_id="test-deepseek")
        fake_client = FakeOpenAIClient(contents=["DeepSeek", " response"])
        monkeypatch.setattr(DeepSeekAdapter, "_create_client", lambda self: fake_client)

        chunks = await collect_chunks(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert_stream_contract(chunks)
        blocks = accumulate_content(chunks)
        assert any(b.get("type") == "text" and b.get("text") for b in blocks)
        assert len(blocks) == chunks[-1].total_blocks


class TestCustomAdapterSmoke:
    async def test_custom_adapter_smoke_forwards_upstream_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        upstream_chunks = [
            StreamChunk(event_type="start", agent_id="test-custom"),
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(event_type="delta", block_index=0, text_delta="hello"),
            StreamChunk(event_type="block_end", block_index=0),
            StreamChunk(event_type="done", agent_id="test-custom", total_blocks=1),
        ]

        class FakeUpstream(BaseAgentAdapter):
            provider = "fake-upstream"

            async def stream(
                self,
                messages: list[ChatMessage],
                *,
                system_prompt: str | None = None,
                config: dict[str, Any] | None = None,
                workspace_path: Path | None = None,
                tool_specs: list[Any] | None = None,
            ) -> AsyncIterator[StreamChunk]:
                for chunk in upstream_chunks:
                    yield chunk

        monkeypatch.setattr(
            "app.agents.adapters.custom.UPSTREAM_ADAPTERS",
            {"claude": FakeUpstream},
        )

        adapter = CustomAdapter(agent_id="test-custom")
        chunks = await collect_chunks(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert_stream_contract(chunks)
        blocks = accumulate_content(chunks)
        assert any(
            b.get("type") == "text" and b.get("text") == "hello" for b in blocks
        )
        assert len(blocks) == chunks[-1].total_blocks


class TestAdapterErrorSmoke:
    async def test_adapter_error_smoke_has_no_dirty_content(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.claude.settings",
            type("S", (), {"anthropic_api_key": "", "anthropic_base_url": ""})(),
        )
        adapter = ClaudeAdapter(agent_id="test-claude")
        chunks = await collect_chunks(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert len(chunks) == 2
        assert chunks[0].event_type == "start"
        assert chunks[1].event_type == "error"
        assert chunks[1].error_code == "missing_api_key"

        blocks = accumulate_content(chunks)
        assert len(blocks) == 0
