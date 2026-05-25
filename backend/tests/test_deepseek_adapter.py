"""Tests for DeepSeekAdapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.types import ChatMessage, StreamChunk


async def _collect(adapter: DeepSeekAdapter, **kwargs: Any) -> list[StreamChunk]:
    return [chunk async for chunk in adapter.stream(**kwargs)]


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
    def __init__(self, contents: list[str | None]) -> None:
        self._contents = contents
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> FakeStream:
        self.last_call_kwargs = kwargs
        return FakeStream(self._contents)


class FakeChat:
    def __init__(self, contents: list[str | None]) -> None:
        self.completions = FakeCompletions(contents)


class FakeClient:
    def __init__(self, contents: list[str | None]) -> None:
        self.chat = FakeChat(contents)


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> DeepSeekAdapter:
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
    return DeepSeekAdapter(agent_id="test-deepseek")


class TestDeepSeekAdapter:
    async def test_stream_plain_text(
        self,
        adapter: DeepSeekAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["你好", " DeepSeek"])
        monkeypatch.setattr(DeepSeekAdapter, "_create_client", lambda self: fake_client)

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert [chunk.event_type for chunk in chunks] == [
            "start",
            "block_start",
            "delta",
            "delta",
            "block_end",
            "done",
        ]
        assert "".join(chunk.text_delta or "" for chunk in chunks) == "你好 DeepSeek"
        assert chunks[-1].event_type == "done"
        assert chunks[-1].agent_id == "test-deepseek"

    async def test_missing_api_key_yields_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.agents.adapters.openai.settings",
            type("S", (), {"deepseek_api_key": "", "deepseek_base_url": ""})(),
        )
        adapter = DeepSeekAdapter(agent_id="test-deepseek")

        chunks = await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
        )

        assert chunks[0].event_type == "start"
        assert chunks[1].event_type == "error"
        assert chunks[1].error_code == "missing_api_key"
        assert "DeepSeek API key" in (chunks[1].error or "")

    async def test_defaults_to_deepseek_flash_model(
        self,
        adapter: DeepSeekAdapter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = FakeClient(contents=["ok"])
        monkeypatch.setattr(DeepSeekAdapter, "_create_client", lambda self: fake_client)

        await _collect(
            adapter,
            messages=[ChatMessage(role="user", content="hi")],
            config={},
        )

        assert fake_client.chat.completions.last_call_kwargs["model"] == "deepseek-v4-flash"

    def test_create_client_uses_deepseek_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        class FakeAsyncOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)

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
        monkeypatch.setattr("app.agents.adapters.openai.openai.AsyncOpenAI", FakeAsyncOpenAI)

        DeepSeekAdapter(agent_id="test-deepseek")._create_client()

        assert captured == {
            "api_key": "fake-key",
            "base_url": "https://api.deepseek.com",
        }
