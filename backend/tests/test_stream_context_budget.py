"""Stream context budget selection tests."""

from __future__ import annotations

import app.api.v1.stream as stream_module


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
