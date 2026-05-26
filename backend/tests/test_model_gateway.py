"""Tests for ModelGateway raw LLM backends."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.adapters.openai import OpenAIAdapter
from app.agents.model_gateway import ModelGateway
from app.agents.model_gateway.claude import ClaudeBackend
from app.agents.model_gateway.openai import OpenAIBackend
from app.agents.types import ChatMessage, StreamChunk, ToolSpec


async def _collect(stream: AsyncIterator[StreamChunk]) -> list[StreamChunk]:
    return [chunk async for chunk in stream]


def _text(chunks: list[StreamChunk]) -> str:
    return "".join(chunk.text_delta or "" for chunk in chunks)


class FakeClaudeStream:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    async def __aenter__(self) -> FakeClaudeStream:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        for text in self._texts:
            yield text


class FakeClaudeMessages:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self.last_call_kwargs: dict[str, Any] = {}

    def stream(self, **kwargs: Any) -> FakeClaudeStream:
        self.last_call_kwargs = kwargs
        return FakeClaudeStream(self._texts)


class FakeClaudeClient:
    def __init__(self, texts: list[str]) -> None:
        self.messages = FakeClaudeMessages(texts)


class FakeOpenAIDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class FakeOpenAIChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = FakeOpenAIDelta(content)


class FakeOpenAIChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [FakeOpenAIChoice(content)]


class FakeOpenAIStream:
    def __init__(self, contents: list[str | None]) -> None:
        self._contents = contents

    async def __aiter__(self) -> AsyncIterator[FakeOpenAIChunk]:
        for content in self._contents:
            yield FakeOpenAIChunk(content)


class FakeOpenAICompletions:
    def __init__(self, contents: list[str | None]) -> None:
        self._contents = contents
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> FakeOpenAIStream:
        self.last_call_kwargs = kwargs
        return FakeOpenAIStream(self._contents)


class FakeOpenAIChat:
    def __init__(self, contents: list[str | None]) -> None:
        self.completions = FakeOpenAICompletions(contents)


class FakeOpenAIClient:
    def __init__(self, contents: list[str | None]) -> None:
        self.chat = FakeOpenAIChat(contents)


def _assert_equivalent(
    legacy_chunks: list[StreamChunk],
    gateway_chunks: list[StreamChunk],
) -> None:
    assert [chunk.event_type for chunk in gateway_chunks] == [
        chunk.event_type for chunk in legacy_chunks
    ]
    assert _text(gateway_chunks) == _text(legacy_chunks)
    assert gateway_chunks[-1].total_blocks == legacy_chunks[-1].total_blocks


async def test_model_gateway_claude_matches_legacy_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.adapters.claude.settings",
        type("S", (), {"anthropic_api_key": "fake-key", "anthropic_base_url": ""})(),
    )
    monkeypatch.setattr(
        "app.agents.model_gateway.claude.settings",
        type("S", (), {"anthropic_api_key": "fake-key", "anthropic_base_url": ""})(),
    )
    clients = [FakeClaudeClient(["Hello", " Claude"]), FakeClaudeClient(["Hello", " Claude"])]
    monkeypatch.setattr(ClaudeBackend, "_create_client", lambda self: clients.pop(0))

    messages = [ChatMessage(role="user", content="hi")]
    legacy_chunks = await _collect(ClaudeAdapter(agent_id="test-claude").stream(messages))
    gateway_chunks = await _collect(
        ModelGateway("claude", agent_id="test-claude").stream(messages)
    )

    _assert_equivalent(legacy_chunks, gateway_chunks)


async def test_model_gateway_openai_matches_legacy_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.adapters.openai.settings",
        type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
    )
    monkeypatch.setattr(
        "app.agents.model_gateway.openai.settings",
        type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
    )
    clients = [FakeOpenAIClient(["Hello", " OpenAI"]), FakeOpenAIClient(["Hello", " OpenAI"])]
    monkeypatch.setattr(OpenAIBackend, "_create_client", lambda self: clients.pop(0))

    messages = [ChatMessage(role="user", content="hi")]
    legacy_chunks = await _collect(OpenAIAdapter(agent_id="test-openai").stream(messages))
    gateway_chunks = await _collect(
        ModelGateway("openai", agent_id="test-openai").stream(messages)
    )

    _assert_equivalent(legacy_chunks, gateway_chunks)


async def test_model_gateway_deepseek_uses_openai_compatible_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.adapters.openai.settings",
        type("S", (), {"deepseek_api_key": "fake-key", "deepseek_base_url": ""})(),
    )
    monkeypatch.setattr(
        "app.agents.model_gateway.openai.settings",
        type("S", (), {"deepseek_api_key": "fake-key", "deepseek_base_url": ""})(),
    )
    clients = [FakeOpenAIClient(["Hello", " DeepSeek"]), FakeOpenAIClient(["Hello", " DeepSeek"])]
    monkeypatch.setattr(OpenAIBackend, "_create_client", lambda self: clients.pop(0))

    messages = [ChatMessage(role="user", content="hi")]
    legacy_chunks = await _collect(DeepSeekAdapter(agent_id="test-deepseek").stream(messages))
    gateway_chunks = await _collect(
        ModelGateway("deepseek", agent_id="test-deepseek").stream(messages)
    )

    _assert_equivalent(legacy_chunks, gateway_chunks)


async def test_model_gateway_accepts_tools_without_passing_to_raw_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.model_gateway.openai.settings",
        type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
    )
    fake_client = FakeOpenAIClient(["ok"])
    monkeypatch.setattr(OpenAIBackend, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        ModelGateway("openai").stream(
            [ChatMessage(role="user", content="hi")],
            tools=[ToolSpec(name="read_file", parameters={"type": "object"})],
        )
    )

    assert chunks[-1].event_type == "done"
    assert "tools" not in fake_client.chat.completions.last_call_kwargs


async def test_model_gateway_missing_key_preserves_error_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.model_gateway.claude.settings",
        type("S", (), {"anthropic_api_key": "", "anthropic_base_url": ""})(),
    )

    chunks = await _collect(
        ModelGateway("claude").stream([ChatMessage(role="user", content="hi")])
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_api_key"
