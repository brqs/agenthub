"""Tests for CustomAdapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.agents.adapters.custom import CustomAdapter
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


async def _collect(adapter: BaseAgentAdapter, **kwargs: Any) -> list[StreamChunk]:
    """Consume the adapter stream into a list."""
    return [chunk async for chunk in adapter.stream(**kwargs)]


class _FakeBase(BaseAgentAdapter):
    """Shared fake logic for recording constructor and stream arguments."""

    instances: list[_FakeBase] = []
    _chunks_for_next: list[StreamChunk] = []

    def __init__(
        self,
        agent_id: str,
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(agent_id, system_prompt, default_config)
        _FakeBase.instances.append(self)
        self.received_messages: list[ChatMessage] = []
        self.received_system_prompt: str | None = None
        self.received_stream_config: dict[str, Any] | None = None
        self._chunks: list[StreamChunk] = list(_FakeBase._chunks_for_next)
        _FakeBase._chunks_for_next = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        self.received_stream_config = config
        for chunk in self._chunks:
            yield chunk


class FakeClaudeAdapter(_FakeBase):
    provider = "fake-claude"


class FakeOpenAIAdapter(_FakeBase):
    provider = "fake-openai"


@pytest.fixture
def fake_map(monkeypatch: pytest.MonkeyPatch) -> dict[str, type[BaseAgentAdapter]]:
    """Replace UPSTREAM_ADAPTERS with distinguishable fakes for claude and openai."""
    _FakeBase.instances.clear()
    _FakeBase._chunks_for_next = []
    fake_map: dict[str, type[BaseAgentAdapter]] = {
        "claude": FakeClaudeAdapter,
        "openai": FakeOpenAIAdapter,
    }
    monkeypatch.setattr(
        "app.agents.adapters.custom.UPSTREAM_ADAPTERS",
        fake_map,
    )
    return fake_map


# ─── Delegation tests ───


class TestCustomAdapterDelegation:
    async def test_defaults_to_claude(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert len(_FakeBase.instances) == 1
        assert isinstance(_FakeBase.instances[0], FakeClaudeAdapter)
        assert chunks == []

    async def test_delegates_to_openai(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"upstream_provider": "openai"},
        )

        assert len(_FakeBase.instances) == 1
        assert isinstance(_FakeBase.instances[0], FakeOpenAIAdapter)
        assert chunks == []

    async def test_per_call_config_overrides_default_config(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(
            agent_id="test-custom",
            default_config={"upstream_provider": "claude"},
        )
        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"upstream_provider": "openai"},
        )

        assert len(_FakeBase.instances) == 1
        assert isinstance(_FakeBase.instances[0], FakeOpenAIAdapter)
        assert chunks == []


# ─── Config forwarding tests ───


class TestCustomAdapterConfig:
    async def test_upstream_provider_is_not_forwarded(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={
                "upstream_provider": "claude",
                "model": "gpt-4o",
                "temperature": 0.5,
                "max_tokens": 1024,
            },
        )

        instance = _FakeBase.instances[0]
        assert "upstream_provider" not in instance.default_config
        assert instance.default_config.get("model") == "gpt-4o"
        assert instance.default_config.get("temperature") == 0.5
        assert instance.default_config.get("max_tokens") == 1024

    async def test_system_prompt_injected(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(
            agent_id="test-custom",
            system_prompt="custom prompt",
        )
        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        instance = _FakeBase.instances[0]
        assert instance.system_prompt == "custom prompt"
        assert instance.received_system_prompt == "custom prompt"

    async def test_system_prompt_override_wins(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(
            agent_id="test-custom",
            system_prompt="default prompt",
        )
        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            system_prompt="override prompt",
        )

        instance = _FakeBase.instances[0]
        assert instance.received_system_prompt == "override prompt"

    async def test_messages_are_forwarded_unchanged(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        messages = [
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi there"),
        ]
        await _collect(adapter, messages=messages)

        instance = _FakeBase.instances[0]
        assert instance.received_messages == messages


# ─── Chunk forwarding tests ───


class TestCustomAdapterChunkForwarding:
    async def test_chunks_are_forwarded_unchanged(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        expected_chunks = [
            StreamChunk(event_type="start", agent_id="test-custom"),
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(event_type="delta", block_index=0, text_delta="hello"),
            StreamChunk(event_type="block_end", block_index=0),
            StreamChunk(event_type="done", agent_id="test-custom", total_blocks=1),
        ]
        _FakeBase._chunks_for_next = list(expected_chunks)

        adapter = CustomAdapter(agent_id="test-custom")
        chunks = await _collect(adapter, messages=[ChatMessage(role="user", content="hi")])

        assert len(chunks) == len(expected_chunks)
        for actual, expected in zip(chunks, expected_chunks, strict=True):
            assert actual.event_type == expected.event_type
            assert actual.agent_id == expected.agent_id
            assert actual.block_index == expected.block_index
            assert actual.block_type == expected.block_type
            assert actual.text_delta == expected.text_delta

    async def test_upstream_error_chunk_is_forwarded(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        _FakeBase._chunks_for_next = [
            StreamChunk(event_type="start", agent_id="test-custom"),
            StreamChunk(
                event_type="error",
                agent_id="test-custom",
                error_code="rate_limit",
                error="too many requests",
            ),
        ]

        adapter = CustomAdapter(agent_id="test-custom")
        chunks = await _collect(adapter, messages=[ChatMessage(role="user", content="hi")])

        assert len(chunks) == 2
        assert chunks[0].event_type == "start"
        assert chunks[1].event_type == "error"
        assert chunks[1].error_code == "rate_limit"
        assert chunks[1].error == "too many requests"


# ─── Error handling tests ───


class TestCustomAdapterErrors:
    async def test_unsupported_upstream_provider_yields_error(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"upstream_provider": "bad-provider"},
        )

        assert len(_FakeBase.instances) == 0
        assert chunks[0].event_type == "start"
        assert chunks[1].event_type == "error"
        assert chunks[1].error_code == "unsupported_upstream_provider"
        assert "bad-provider" in (chunks[1].error or "")

    async def test_upstream_provider_case_insensitive(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"upstream_provider": "OpenAI"},
        )

        assert len(_FakeBase.instances) == 1
        assert isinstance(_FakeBase.instances[0], FakeOpenAIAdapter)


# ─── Edge cases ───


class TestCustomAdapterEdgeCases:
    async def test_none_upstream_provider_defaults_to_claude(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"upstream_provider": None},
        )

        assert len(_FakeBase.instances) == 1
        assert isinstance(_FakeBase.instances[0], FakeClaudeAdapter)

    async def test_empty_string_upstream_provider_defaults_to_claude(
        self,
        fake_map: dict[str, type[BaseAgentAdapter]],
    ) -> None:
        adapter = CustomAdapter(agent_id="test-custom")
        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={"upstream_provider": ""},
        )

        assert len(_FakeBase.instances) == 1
        assert isinstance(_FakeBase.instances[0], FakeClaudeAdapter)
