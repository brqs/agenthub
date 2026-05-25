"""Tests for ClaudeAdapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.types import ChatMessage, StreamChunk


async def _collect(adapter: ClaudeAdapter, **kwargs: Any) -> list[StreamChunk]:
    """Consume the adapter stream into a list."""
    return [chunk async for chunk in adapter.stream(**kwargs)]


def _blocks_from_chunks(chunks: list[StreamChunk]) -> list[dict[str, Any]]:
    """Aggregate sequential chunks into block dicts for easy assertion."""
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for c in chunks:
        if c.event_type == "block_start":
            current = {
                "index": c.block_index,
                "type": c.block_type,
                "text": "",
                "code": "",
                "metadata": c.metadata or {},
            }
        elif c.event_type == "delta" and current is not None:
            if c.text_delta:
                current["text"] += c.text_delta
            if c.code_delta:
                current["code"] += c.code_delta
        elif c.event_type == "block_end" and current is not None:
            blocks.append(current)
            current = None
    return blocks


# ─── Fake Anthropic client infrastructure ───


class FakeStream:
    """Simulates anthropic AsyncMessageStream."""

    def __init__(self, texts: list[str] | None = None) -> None:
        self._texts = texts or []

    async def __aenter__(self) -> FakeStream:
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


class FakeMessages:
    def __init__(
        self,
        texts: list[str] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._texts = texts or []
        self._exc = exc
        self.last_call_kwargs: dict[str, Any] = {}

    def stream(self, **kwargs: Any) -> FakeStream:
        self.last_call_kwargs = kwargs
        if self._exc:
            raise self._exc
        return FakeStream(self._texts)


class FakeClient:
    def __init__(
        self,
        texts: list[str] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.messages = FakeMessages(texts, exc)


class FakeRateLimitError(Exception):
    pass


class FakeAPIError(Exception):
    pass


# ─── Fixtures ───


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> ClaudeAdapter:
    monkeypatch.setattr(
        "app.agents.adapters.claude.settings",
        type("S", (), {"anthropic_api_key": "fake-key", "anthropic_base_url": ""})(),
    )
    return ClaudeAdapter(agent_id="test-claude")


# ─── Streaming tests ───


class TestClaudeAdapterStream:
    async def test_stream_plain_text(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(texts=["Hello", " world", "!"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        events = [c.event_type for c in chunks]
        assert events == [
            "start",
            "block_start",
            "delta",
            "delta",
            "delta",
            "block_end",
            "done",
        ]

        assert chunks[0].event_type == "start"
        assert chunks[0].agent_id == "test-claude"

        text_deltas = [
            c.text_delta for c in chunks if c.event_type == "delta"
        ]
        assert "".join(filter(None, text_deltas)) == "Hello world!"

        done = chunks[-1]
        assert done.event_type == "done"
        assert done.agent_id == "test-claude"
        assert done.total_blocks == 1

    async def test_stream_code_block_uses_artifact_parser(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        text = "Here is code:\n\n```python\nprint(1)\n```\n\nDone"
        fake_client = FakeClient(texts=[text])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="code pls")],
        )

        blocks = _blocks_from_chunks(chunks)
        assert len(blocks) == 3
        assert blocks[0]["type"] == "text"
        assert "Here is code:" in blocks[0]["text"]
        assert blocks[1]["type"] == "code"
        assert blocks[1]["metadata"].get("language") == "python"
        assert "print(1)" in blocks[1]["code"]
        assert blocks[2]["type"] == "text"
        assert "Done" in blocks[2]["text"]

        done = [c for c in chunks if c.event_type == "done"][0]
        assert done.total_blocks == 3

    async def test_stream_split_fence_across_deltas(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(
            texts=["hello\n``", "`python\nprint(1)\n", "``", "`\nworld"],
        )
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="split")],
        )

        for c in chunks:
            if c.event_type == "delta":
                assert "```" not in (c.text_delta or "")
                assert "```" not in (c.code_delta or "")

        blocks = _blocks_from_chunks(chunks)
        assert len(blocks) == 3
        assert blocks[0]["type"] == "text"
        assert "hello" in blocks[0]["text"]
        assert blocks[1]["type"] == "code"
        assert "print(1)" in blocks[1]["code"]
        assert blocks[2]["type"] == "text"
        assert "world" in blocks[2]["text"]


# ─── Error handling tests ───


class TestClaudeAdapterErrors:
    async def test_missing_api_key_yields_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.claude.settings",
            type("S", (), {"anthropic_api_key": "", "anthropic_base_url": ""})(),
        )
        adapter = ClaudeAdapter(agent_id="test-claude")

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert chunks[0].event_type == "start"
        assert chunks[1].event_type == "error"
        assert chunks[1].error_code == "missing_api_key"
        assert "not configured" in (chunks[1].error or "")
        assert len(chunks) == 2

    async def test_rate_limit_yields_error(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.claude.anthropic.RateLimitError",
            FakeRateLimitError,
        )
        fake_client = FakeClient(exc=FakeRateLimitError("rate limited"))
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        error_chunks = [c for c in chunks if c.event_type == "error"]
        assert len(error_chunks) == 1
        assert error_chunks[0].error_code == "rate_limit"
        assert "rate limited" in (error_chunks[0].error or "")

    async def test_api_error_yields_upstream_error(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.claude.anthropic.APIError",
            FakeAPIError,
        )
        fake_client = FakeClient(exc=FakeAPIError("upstream down"))
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        error_chunks = [c for c in chunks if c.event_type == "error"]
        assert len(error_chunks) == 1
        assert error_chunks[0].error_code == "upstream_error"
        assert "upstream down" in (error_chunks[0].error or "")


# ─── Config / message transformation tests ───


class TestClaudeAdapterConfig:
    async def test_system_messages_are_merged_into_system_prompt(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(texts=["ok"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        messages = [
            ChatMessage(role="system", content="Be helpful"),
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="system", content="Be concise"),
        ]
        await _collect(
            adapter,
            messages=messages,
            system_prompt="Base prompt",
        )

        kwargs = fake_client.messages.last_call_kwargs
        assert "system" in kwargs
        assert "Base prompt" in kwargs["system"]
        assert "Be helpful" in kwargs["system"]
        assert "Be concise" in kwargs["system"]

        anthropic_messages = kwargs["messages"]
        assert all(m["role"] != "system" for m in anthropic_messages)
        assert anthropic_messages == [{"role": "user", "content": "hi"}]

    async def test_empty_config_uses_defaults(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(texts=["ok"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={},
        )

        kwargs = fake_client.messages.last_call_kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 4096

    async def test_temperature_none_fallback(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(texts=["ok"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"temperature": None},
        )

        assert fake_client.messages.last_call_kwargs["temperature"] == 0.7

    async def test_temperature_zero_preserved(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(texts=["ok"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"temperature": 0},
        )

        assert fake_client.messages.last_call_kwargs["temperature"] == 0

    async def test_max_tokens_none_fallback(
        self,
        adapter: ClaudeAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(texts=["ok"])
        monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"max_tokens": None},
        )

        assert fake_client.messages.last_call_kwargs["max_tokens"] == 4096
