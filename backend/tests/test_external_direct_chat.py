"""Tests for external direct-chat routing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

import app.agents.external.direct_chat as direct_chat_module
from app.agents.external.direct_chat import maybe_stream_direct_chat
from app.agents.types import ChatMessage, StreamChunk


class FakeModelGateway:
    streams: list[list[StreamChunk]] = []
    calls: list[dict[str, Any]] = []

    def __init__(
        self,
        backend: str,
        default_config: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.backend = backend
        self.default_config = default_config or {}
        self.agent_id = agent_id or ""
        self.system_prompt = system_prompt

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: object | None = None,
    ) -> AsyncIterator[StreamChunk]:
        FakeModelGateway.calls.append(
            {
                "backend": self.backend,
                "agent_id": self.agent_id,
                "messages": messages,
                "system_prompt": system_prompt,
                "config": config,
                "tools": tools,
            }
        )
        for chunk in FakeModelGateway.streams.pop(0):
            yield chunk


@pytest.fixture(autouse=True)
def fake_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeModelGateway.streams = []
    FakeModelGateway.calls = []
    monkeypatch.setattr(direct_chat_module, "ModelGateway", FakeModelGateway)


async def _decision_chunks(config: dict[str, Any] | None = None) -> list[StreamChunk]:
    decision = await maybe_stream_direct_chat(
        agent_id="codex-helper",
        provider="codex",
        messages=[ChatMessage(role="user", content="Explain React effects")],
        system_prompt="You are Codex Helper.",
        config=config or {},
    )
    assert decision.route == "direct_chat"
    assert decision.stream is not None
    return [chunk async for chunk in decision.stream]


async def test_direct_chat_classifier_returns_answer_stream_without_internal_start() -> None:
    FakeModelGateway.streams = [
        [
            StreamChunk(event_type="start", agent_id="external-direct-chat-classifier"),
            StreamChunk(
                event_type="block_start",
                block_index=0,
                block_type="text",
            ),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta='{"route":"direct_chat","confidence":0.9,"reason":"qa"}',
            ),
            StreamChunk(event_type="block_end", block_index=0),
            StreamChunk(event_type="done", agent_id="external-direct-chat-classifier"),
        ],
        [
            StreamChunk(event_type="start", agent_id="model-gateway-deepseek"),
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(event_type="delta", block_index=0, text_delta="Use cleanup."),
            StreamChunk(event_type="block_end", block_index=0),
            StreamChunk(event_type="done", agent_id="model-gateway-deepseek", total_blocks=1),
        ],
    ]

    chunks = await _decision_chunks()

    assert [chunk.event_type for chunk in chunks] == [
        "block_start",
        "delta",
        "block_end",
        "done",
    ]
    assert chunks[-1].agent_id == "codex-helper"
    assert FakeModelGateway.calls[0]["agent_id"] == "external-direct-chat-classifier"
    assert FakeModelGateway.calls[1]["agent_id"] == "codex-helper"


@pytest.mark.parametrize(
    "classifier_text",
    [
        '{"route":"runtime","confidence":0.99,"reason":"needs files"}',
        '{"route":"direct_chat","confidence":0.2,"reason":"unsure"}',
        "```json\n{\"route\":\"direct_chat\"}\n```",
    ],
)
async def test_classifier_runtime_invalid_or_low_confidence_falls_back(
    classifier_text: str,
) -> None:
    FakeModelGateway.streams = [
        [
            StreamChunk(event_type="start", agent_id="external-direct-chat-classifier"),
            StreamChunk(event_type="delta", text_delta=classifier_text),
            StreamChunk(event_type="done", agent_id="external-direct-chat-classifier"),
        ],
    ]

    decision = await maybe_stream_direct_chat(
        agent_id="codex-helper",
        provider="codex",
        messages=[ChatMessage(role="user", content="Generate snake.html")],
        system_prompt=None,
        config={},
    )

    assert decision.route == "runtime"
    assert len(FakeModelGateway.calls) == 1


async def test_classifier_error_falls_back_to_runtime() -> None:
    FakeModelGateway.streams = [
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="classifier timeout",
            ),
        ],
    ]

    decision = await maybe_stream_direct_chat(
        agent_id="codex-helper",
        provider="codex",
        messages=[ChatMessage(role="user", content="Explain timeouts")],
        system_prompt=None,
        config={},
    )

    assert decision.route == "runtime"


async def test_direct_chat_answer_error_does_not_fallback_to_runtime() -> None:
    FakeModelGateway.streams = [
        [
            StreamChunk(
                event_type="delta",
                text_delta='{"route":"direct_chat","confidence":0.99,"reason":"qa"}',
            ),
            StreamChunk(event_type="done", agent_id="external-direct-chat-classifier"),
        ],
        [
            StreamChunk(event_type="start", agent_id="model-gateway-deepseek"),
            StreamChunk(event_type="error", error_code="timeout", error="answer timeout"),
        ],
    ]

    chunks = await _decision_chunks()

    assert [chunk.event_type for chunk in chunks] == ["error"]
    assert chunks[0].agent_id == "codex-helper"
    assert chunks[0].error_code == "timeout"
    assert len(FakeModelGateway.calls) == 2
