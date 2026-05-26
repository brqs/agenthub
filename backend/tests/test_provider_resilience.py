"""Provider resilience behavior tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.adapters.custom import CustomAdapter
from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.adapters.openai import OpenAIAdapter
from app.agents.adapters.resilience import parse_resilience_config
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


async def _collect(adapter: BaseAgentAdapter, **kwargs: Any) -> list[StreamChunk]:
    return [chunk async for chunk in adapter.stream(**kwargs)]


class FakeAPIError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


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
    def __init__(
        self,
        contents: list[str | None],
        exc_after: Exception | None = None,
    ) -> None:
        self._contents = contents
        self._exc_after = exc_after

    def __aiter__(self) -> AsyncIterator[FakeOpenAIChunk]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[FakeOpenAIChunk]:
        for content in self._contents:
            yield FakeOpenAIChunk(content)
        if self._exc_after is not None:
            raise self._exc_after


class FakeOpenAICompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.call_count = 0
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> FakeOpenAIStream:
        self.call_count += 1
        self.last_call_kwargs = kwargs
        outcome = self._outcomes.pop(0)
        if outcome == "timeout":
            await asyncio.sleep(1)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeOpenAIChat:
    def __init__(self, outcomes: list[Any]) -> None:
        self.completions = FakeOpenAICompletions(outcomes)


class FakeOpenAIClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.chat = FakeOpenAIChat(outcomes)


class FakeClaudeStream:
    def __init__(
        self,
        texts: list[str],
        exc_after: Exception | None = None,
    ) -> None:
        self._texts = texts
        self._exc_after = exc_after
        self.aenter_count = 0
        self.aexit_count = 0

    async def __aenter__(self) -> FakeClaudeStream:
        self.aenter_count += 1
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.aexit_count += 1
        return None

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        for text in self._texts:
            yield text
        if self._exc_after is not None:
            raise self._exc_after


class FakeClaudeMessages:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.call_count = 0
        self.last_call_kwargs: dict[str, Any] = {}

    def stream(self, **kwargs: Any) -> FakeClaudeStream:
        self.call_count += 1
        self.last_call_kwargs = kwargs
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClaudeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.messages = FakeClaudeMessages(outcomes)


class FakeCustomUpstreamAdapter(BaseAgentAdapter):
    provider = "fake-upstream"
    instances: list[FakeCustomUpstreamAdapter] = []

    def __init__(
        self,
        agent_id: str,
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(agent_id, system_prompt, default_config)
        self.stream_call_count = 0
        FakeCustomUpstreamAdapter.instances.append(self)

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.stream_call_count += 1
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(
            event_type="error",
            agent_id=self.agent_id,
            error_code="rate_limit",
            error="upstream rate limited",
            metadata={"provider": "openai", "attempts": 1, "retryable": False},
        )


@pytest.fixture
def openai_adapter(monkeypatch: pytest.MonkeyPatch) -> OpenAIAdapter:
    monkeypatch.setattr(
        "app.agents.adapters.openai.settings",
        type("S", (), {"openai_api_key": "fake-key", "openai_base_url": ""})(),
    )
    monkeypatch.setattr("app.agents.adapters.openai.openai.APIError", FakeAPIError)
    monkeypatch.setattr(
        "app.agents.adapters.openai.openai.RateLimitError",
        FakeRateLimitError,
    )
    return OpenAIAdapter(agent_id="test-openai")


@pytest.fixture
def claude_adapter(monkeypatch: pytest.MonkeyPatch) -> ClaudeAdapter:
    monkeypatch.setattr(
        "app.agents.adapters.claude.settings",
        type("S", (), {"anthropic_api_key": "fake-key", "anthropic_base_url": ""})(),
    )
    monkeypatch.setattr("app.agents.adapters.claude.anthropic.APIError", FakeAPIError)
    monkeypatch.setattr(
        "app.agents.adapters.claude.anthropic.RateLimitError",
        FakeRateLimitError,
    )
    return ClaudeAdapter(agent_id="test-claude")


async def test_openai_retries_setup_transient_error_then_succeeds(
    openai_adapter: OpenAIAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        [FakeAPIError("temporary"), FakeOpenAIStream(["Hello"])]
    )
    monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        openai_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 1, "retry_backoff_seconds": 0},
    )

    assert fake_client.chat.completions.call_count == 2
    assert [chunk.event_type for chunk in chunks] == [
        "start",
        "block_start",
        "delta",
        "block_end",
        "done",
    ]
    assert "".join(chunk.text_delta or "" for chunk in chunks) == "Hello"
    assert not [chunk for chunk in chunks if chunk.event_type == "error"]


async def test_openai_does_not_retry_rate_limit_by_default(
    openai_adapter: OpenAIAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient([FakeRateLimitError("rate limited")])
    monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        openai_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 3, "retry_backoff_seconds": 0},
    )

    assert fake_client.chat.completions.call_count == 1
    assert chunks[1].event_type == "error"
    assert chunks[1].error_code == "rate_limit"
    assert chunks[1].metadata == {
        "provider": "openai",
        "attempts": 1,
        "retryable": False,
    }


async def test_openai_timeout_maps_to_timeout_error(
    openai_adapter: OpenAIAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(["timeout"])
    monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        openai_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 0, "request_timeout_seconds": 0.001},
    )

    assert fake_client.chat.completions.call_count == 1
    assert chunks[1].event_type == "error"
    assert chunks[1].error_code == "timeout"


async def test_openai_connection_error_maps_to_connection_error(
    openai_adapter: OpenAIAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient([ConnectionError("connection reset")])
    monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        openai_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 0},
    )

    assert fake_client.chat.completions.call_count == 1
    assert chunks[1].event_type == "error"
    assert chunks[1].error_code == "connection_error"


async def test_openai_stream_error_after_content_flushes_then_errors(
    openai_adapter: OpenAIAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeOpenAIClient(
        [FakeOpenAIStream(["```python\nprint(1)\n"], FakeAPIError("stream failed"))]
    )
    monkeypatch.setattr(OpenAIAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        openai_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 3, "retry_backoff_seconds": 0},
    )

    assert fake_client.chat.completions.call_count == 1
    assert [chunk.event_type for chunk in chunks] == [
        "start",
        "block_start",
        "delta",
        "block_end",
        "error",
    ]
    assert chunks[1].block_type == "code"
    assert chunks[2].code_delta == "print(1)\n"
    assert chunks[-1].error_code == "upstream_error"
    assert chunks[-1].metadata == {
        "provider": "openai",
        "attempts": 1,
        "retryable": False,
    }


async def test_claude_retries_setup_transient_error_then_succeeds(
    claude_adapter: ClaudeAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeClaudeClient(
        [FakeAPIError("temporary"), FakeClaudeStream(["Hello"])]
    )
    monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        claude_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 1, "retry_backoff_seconds": 0},
    )

    assert fake_client.messages.call_count == 2
    assert [chunk.event_type for chunk in chunks] == [
        "start",
        "block_start",
        "delta",
        "block_end",
        "done",
    ]
    assert "".join(chunk.text_delta or "" for chunk in chunks) == "Hello"


async def test_claude_rate_limit_does_not_retry_by_default(
    claude_adapter: ClaudeAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeClaudeClient([FakeRateLimitError("rate limited")])
    monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        claude_adapter,
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 3, "retry_backoff_seconds": 0},
    )

    assert fake_client.messages.call_count == 1
    assert chunks[1].event_type == "error"
    assert chunks[1].error_code == "rate_limit"
    assert chunks[1].metadata == {
        "provider": "claude",
        "attempts": 1,
        "retryable": False,
    }


async def test_claude_aclose_closes_open_stream_once(
    claude_adapter: ClaudeAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stream = FakeClaudeStream(["Hello"])
    fake_client = FakeClaudeClient([fake_stream])
    monkeypatch.setattr(ClaudeAdapter, "_create_client", lambda self: fake_client)

    stream = claude_adapter.stream(
        messages=[ChatMessage(role="user", content="hi")],
    )
    chunks = [await stream.__anext__(), await stream.__anext__(), await stream.__anext__()]

    assert [chunk.event_type for chunk in chunks] == ["start", "block_start", "delta"]
    assert fake_stream.aenter_count == 1

    await stream.aclose()

    assert fake_stream.aexit_count == 1


async def test_deepseek_inherits_openai_resilience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.adapters.openai.settings",
        type(
            "S",
            (),
            {
                "deepseek_api_key": "fake-key",
                "deepseek_base_url": "https://api.deepseek.com",
            },
        )(),
    )
    fake_client = FakeOpenAIClient([ConnectionError("connection reset")])
    monkeypatch.setattr(DeepSeekAdapter, "_create_client", lambda self: fake_client)

    chunks = await _collect(
        DeepSeekAdapter(agent_id="test-deepseek"),
        messages=[ChatMessage(role="user", content="hi")],
        config={"max_retries": 0},
    )

    assert fake_client.chat.completions.call_count == 1
    assert chunks[1].event_type == "error"
    assert chunks[1].error_code == "connection_error"
    assert chunks[1].metadata == {
        "provider": "deepseek",
        "attempts": 1,
        "retryable": True,
    }


async def test_custom_adapter_does_not_double_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeCustomUpstreamAdapter.instances.clear()
    monkeypatch.setattr(
        "app.agents.adapters.custom.UPSTREAM_ADAPTERS",
        {"openai": FakeCustomUpstreamAdapter},
    )

    chunks = await _collect(
        CustomAdapter(agent_id="test-custom"),
        messages=[ChatMessage(role="user", content="hi")],
        config={"upstream_provider": "openai", "max_retries": 3},
    )

    assert len(FakeCustomUpstreamAdapter.instances) == 1
    assert FakeCustomUpstreamAdapter.instances[0].stream_call_count == 1
    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "rate_limit"
    assert chunks[1].metadata == {
        "provider": "openai",
        "attempts": 1,
        "retryable": False,
    }


def test_resilience_config_defaults() -> None:
    config = parse_resilience_config({})

    assert config.max_retries == 1
    assert config.retry_backoff_seconds == 0.25
    assert config.request_timeout_seconds == 30.0
    assert config.retry_on_rate_limit is False


def test_resilience_config_invalid_values_fall_back() -> None:
    config = parse_resilience_config(
        {
            "max_retries": "many",
            "retry_backoff_seconds": object(),
            "request_timeout_seconds": "fast",
            "retry_on_rate_limit": "yes",
        }
    )

    assert config.max_retries == 1
    assert config.retry_backoff_seconds == 0.25
    assert config.request_timeout_seconds == 30.0
    assert config.retry_on_rate_limit is False


def test_resilience_config_clamps_bounds() -> None:
    high_config = parse_resilience_config(
        {
            "max_retries": 99,
            "retry_backoff_seconds": -1,
            "request_timeout_seconds": -5,
            "retry_on_rate_limit": True,
        }
    )
    low_config = parse_resilience_config({"max_retries": -1})

    assert high_config.max_retries == 3
    assert high_config.retry_backoff_seconds == 0
    assert high_config.request_timeout_seconds == 30.0
    assert high_config.retry_on_rate_limit is True
    assert low_config.max_retries == 0
