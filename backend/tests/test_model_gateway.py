"""Tests for ModelGateway raw LLM backends."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
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
    def __init__(
        self,
        texts: list[str] | None = None,
        events: list[SimpleNamespace] | None = None,
    ) -> None:
        self._texts = texts or []
        self._events = events or []

    async def __aiter__(self) -> AsyncIterator[SimpleNamespace]:
        for event in self._events:
            yield event

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
    def __init__(
        self,
        texts: list[str] | None = None,
        events: list[SimpleNamespace] | None = None,
    ) -> None:
        self._texts = texts
        self._events = events
        self.last_call_kwargs: dict[str, Any] = {}

    def stream(self, **kwargs: Any) -> FakeClaudeStream:
        self.last_call_kwargs = kwargs
        return FakeClaudeStream(self._texts, self._events)


class FakeClaudeClient:
    def __init__(
        self,
        texts: list[str] | None = None,
        events: list[SimpleNamespace] | None = None,
    ) -> None:
        self.messages = FakeClaudeMessages(texts, events)


class FakeOpenAIDelta:
    def __init__(
        self,
        content: str | None,
        tool_calls: list[SimpleNamespace] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls


class FakeOpenAIChoice:
    def __init__(
        self,
        content: str | None,
        tool_calls: list[SimpleNamespace] | None = None,
    ) -> None:
        self.delta = FakeOpenAIDelta(content, tool_calls)


class FakeOpenAIChunk:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[SimpleNamespace] | None = None,
    ) -> None:
        self.choices = [FakeOpenAIChoice(content, tool_calls)]


class FakeOpenAIStream:
    def __init__(self, chunks: list[FakeOpenAIChunk]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[FakeOpenAIChunk]:
        for chunk in self._chunks:
            yield chunk


class FakeOpenAICompletions:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        chunks: list[FakeOpenAIChunk] | None = None,
    ) -> None:
        self._chunks = chunks or [FakeOpenAIChunk(content) for content in contents or []]
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> FakeOpenAIStream:
        self.last_call_kwargs = kwargs
        return FakeOpenAIStream(self._chunks)


class FakeOpenAIChat:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        chunks: list[FakeOpenAIChunk] | None = None,
    ) -> None:
        self.completions = FakeOpenAICompletions(contents, chunks)


class FakeOpenAIClient:
    def __init__(
        self,
        contents: list[str | None] | None = None,
        chunks: list[FakeOpenAIChunk] | None = None,
    ) -> None:
        self.chat = FakeOpenAIChat(contents, chunks)


def _event(event_type: str, **kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(type=event_type, **kwargs)


def _openai_tool_delta(
    *,
    index: int,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


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


async def test_model_gateway_claude_passes_tools_and_maps_tool_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.model_gateway.claude.settings",
        type("S", (), {"anthropic_api_key": "fake-key", "anthropic_base_url": ""})(),
    )
    fake_client = FakeClaudeClient(
        events=[
            _event(
                "content_block_start",
                index=0,
                content_block=_event(
                    "tool_use",
                    id="tool-1",
                    name="read_file",
                    input={},
                ),
            ),
            _event(
                "content_block_delta",
                index=0,
                delta=_event("input_json_delta", partial_json='{"path":"notes.txt"}'),
            ),
            _event("content_block_stop", index=0),
        ]
    )
    monkeypatch.setattr(ClaudeBackend, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        ModelGateway("claude").stream(
            [ChatMessage(role="user", content="read notes")],
            tools=[
                ToolSpec(
                    name="read_file",
                    description="Read a file",
                    parameters={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                )
            ],
        )
    )

    kwargs = fake_client.messages.last_call_kwargs
    assert kwargs["tools"] == [
        {
            "name": "read_file",
            "description": "Read a file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        }
    ]
    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    assert tool_call.call_id == "tool-1"
    assert tool_call.tool_name == "read_file"
    assert tool_call.tool_arguments == {"path": "notes.txt"}
    assert chunks[-1].event_type == "done"


async def test_model_gateway_openai_passes_tools_and_maps_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.model_gateway.openai.settings",
        type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
    )
    fake_client = FakeOpenAIClient(
        chunks=[
            FakeOpenAIChunk(
                tool_calls=[
                    _openai_tool_delta(
                        index=0,
                        call_id="call-1",
                        name="read_file",
                        arguments='{"path"',
                    )
                ]
            ),
            FakeOpenAIChunk(
                tool_calls=[
                    _openai_tool_delta(index=0, arguments=':"notes.txt"}')
                ]
            ),
        ]
    )
    monkeypatch.setattr(OpenAIBackend, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        ModelGateway("openai").stream(
            [ChatMessage(role="user", content="hi")],
            config={"tool_choice": {"type": "tool", "name": "read_file"}},
            tools=[
                ToolSpec(
                    name="read_file",
                    description="Read a file",
                    parameters={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                )
            ],
        )
    )

    kwargs = fake_client.chat.completions.last_call_kwargs
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }
    ]
    assert kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "read_file"},
    }
    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    assert tool_call.call_id == "call-1"
    assert tool_call.tool_name == "read_file"
    assert tool_call.tool_arguments == {"path": "notes.txt"}
    assert chunks[-1].event_type == "done"


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
