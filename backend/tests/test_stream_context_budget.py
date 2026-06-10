"""Stream context budget selection tests."""

from __future__ import annotations

from uuid import uuid4

import app.api.v1.stream as stream_module
from app.agents.types import ChatMessage
from app.api.v1 import stream_orchestrator_context as orchestrator_context_module


def test_configured_context_max_tokens_prefers_orchestrator_specific_budget() -> None:
    assert (
        stream_module._configured_context_max_tokens(
            "orchestrator",
            {
                "context_max_tokens": 32000,
                "orchestrator_context_max_tokens": 64000,
            },
        )
        == 64000
    )


def test_configured_context_max_tokens_uses_agent_budget_for_subagents() -> None:
    assert (
        stream_module._configured_context_max_tokens(
            "claude-code",
            {
                "context_max_tokens": 50000,
                "orchestrator_context_max_tokens": 64000,
            },
        )
        == 50000
    )


def test_configured_planner_context_max_tokens_defaults_and_caps() -> None:
    assert stream_module._configured_planner_context_max_tokens({}) == 128000
    assert (
        stream_module._configured_planner_context_max_tokens(
            {"planner_context_max_tokens": 256000}
        )
        == 256000
    )
    assert (
        stream_module._configured_planner_context_max_tokens(
            {"planner_context_max_tokens": 1000001}
        )
        == 1000000
    )


async def test_orchestrator_stream_context_injects_memory_into_planner_context(
    monkeypatch,
) -> None:
    class FakeMessage:
        agent_id = "orchestrator"
        conversation_id = uuid4()
        id = uuid4()
        reply_to_id = uuid4()

    class FakeAdapter:
        default_config = {"orchestrator_memory_enabled": True}

        def merged_config(self, stream_config):
            return {**self.default_config, **stream_config}

    async def fake_conversation_config(_db, _message):
        return {}

    async def fake_memory_message(_db, _conversation_id, _config):
        return ChatMessage(
            role="system",
            content="Previous Orchestrator structured memory:\n- prior decision",
        )

    monkeypatch.setattr(
        orchestrator_context_module,
        "_orchestrator_conversation_config",
        fake_conversation_config,
    )
    monkeypatch.setattr(
        orchestrator_context_module,
        "_orchestrator_memory_context_message",
        fake_memory_message,
    )

    history, stream_config = (
        await orchestrator_context_module.apply_orchestrator_stream_context(
            None,
            FakeMessage(),
            FakeAdapter(),
            [ChatMessage(role="user", content="current")],
            planner_context_messages=[
                ChatMessage(role="user", content="older context"),
                ChatMessage(role="user", content="current"),
            ],
        )
    )

    assert any("prior decision" in message.content for message in history)
    assert stream_config is not None
    planner_context = stream_config["planner_context_messages"]
    assert any("prior decision" in message.content for message in planner_context)
