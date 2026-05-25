"""Tests for OpenAIAdapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.agents.adapters.openai import OpenAIAdapter
from app.agents.types import ChatMessage, StreamChunk


async def _collect(adapter: OpenAIAdapter, **kwargs: Any) -> list[StreamChunk]:
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


# ─── Fake OpenAI client infrastructure ───


class FakeDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, delta: FakeDelta) -> None:
        self.delta = delta


class FakeChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [FakeChoice(FakeDelta(content))]


class FakeStream:
    def __init__(self, contents: list[str | None]) -> None:
        self._contents = contents

    async def __aiter__(self) -> AsyncIterator[FakeChunk]:
        for content in self._contents:
            yield FakeChunk(content)


class FakeCompletions:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._contents = contents or []
        self._exc = exc
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> FakeStream:
        self.last_call_kwargs = kwargs
        if self._exc:
            raise self._exc
        return FakeStream(self._contents)


class FakeChat:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.completions = FakeCompletions(contents, exc)


class FakeClient:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.chat = FakeChat(contents, exc)


class FakeRateLimitError(Exception):
    pass


class FakeAPIError(Exception):
    pass


# ─── Fixtures ───


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> OpenAIAdapter:
    monkeypatch.setattr(
        "app.agents.adapters.openai.settings",
        type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
    )
    return OpenAIAdapter(agent_id="test-openai")


# ─── Streaming tests ───


class TestOpenAIAdapterStream:
    async def test_stream_plain_text(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["Hello", " world", "!"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

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
        assert chunks[0].agent_id == "test-openai"

        text_deltas = [c.text_delta for c in chunks if c.event_type == "delta"]
        assert "".join(filter(None, text_deltas)) == "Hello world!"

        done = chunks[-1]
        assert done.event_type == "done"
        assert done.agent_id == "test-openai"
        assert done.total_blocks == 1

    async def test_stream_code_block_uses_artifact_parser(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        text = "Here is code:\n\n```python\nprint(1)\n```\n\nDone"
        fake_client = FakeClient(contents=[text])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

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
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(
            contents=["hello\n``", "`python\nprint(1)\n", "``", "`\nworld"],
        )
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

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

    async def test_skips_empty_delta_content(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["Hello", None, "", " world"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        text_deltas = [c.text_delta for c in chunks if c.event_type == "delta"]
        assert "".join(filter(None, text_deltas)) == "Hello world"


# ─── Error handling tests ───


class TestOpenAIAdapterErrors:
    async def test_missing_api_key_yields_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.openai.settings",
            type("S", (), {"openai_api_key": "", "openai_base_url": ""})(),
        )
        adapter = OpenAIAdapter(agent_id="test-openai")

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
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.openai.openai.RateLimitError",
            FakeRateLimitError,
        )
        fake_client = FakeClient(exc=FakeRateLimitError("rate limited"))
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

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
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.openai.openai.APIError",
            FakeAPIError,
        )
        fake_client = FakeClient(exc=FakeAPIError("upstream down"))
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        error_chunks = [c for c in chunks if c.event_type == "error"]
        assert len(error_chunks) == 1
        assert error_chunks[0].error_code == "upstream_error"
        assert "upstream down" in (error_chunks[0].error or "")


# ─── Config / message transformation tests ───


class TestOpenAIAdapterConfig:
    async def test_system_messages_are_merged_into_system_prompt(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["ok"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        messages = [
            ChatMessage(role="system", content="Be helpful"),
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="assistant", content="hello"),
            ChatMessage(role="system", content="Be concise"),
        ]
        await _collect(
            adapter,
            messages=messages,
            system_prompt="Base prompt",
        )

        kwargs = fake_client.chat.completions.last_call_kwargs
        openai_messages = kwargs["messages"]
        assert openai_messages[0]["role"] == "system"
        assert "Base prompt" in openai_messages[0]["content"]
        assert "Be helpful" in openai_messages[0]["content"]
        assert "Be concise" in openai_messages[0]["content"]
        assert openai_messages[1:] == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

    async def test_empty_config_uses_defaults(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["ok"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={},
        )

        kwargs = fake_client.chat.completions.last_call_kwargs
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 4096

    async def test_temperature_none_fallback(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["ok"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"temperature": None},
        )

        assert fake_client.chat.completions.last_call_kwargs["temperature"] == 0.7

    async def test_temperature_zero_preserved(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["ok"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"temperature": 0},
        )

        assert fake_client.chat.completions.last_call_kwargs["temperature"] == 0

    async def test_max_tokens_none_fallback(
        self,
        adapter: OpenAIAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["ok"])
        monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"max_tokens": None},
        )

        assert fake_client.chat.completions.last_call_kwargs["max_tokens"] == 4096
