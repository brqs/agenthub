"""Orchestrator memory prompt sanitization tests."""

from __future__ import annotations

from app.services._orchestrator_memory.capability_v1 import (
    safe_failure_reason_summary,
)
from app.services._orchestrator_memory.context import (
    _format_agent_capability_profile_v2,
)
from app.services._orchestrator_memory.types import AgentCapabilityProfileV2Item


def test_runtime_failure_reason_summary_removes_raw_cli_trace() -> None:
    raw_error = (
        "Codex CLI exited with code 1: stderr: Reading additional input from stdin... "
        "OpenAI Codex v0.137.0 -------- workdir: /workspaces/example "
        "model: gpt-5.5 provider: openai approval: never "
        "sandbox: danger-full-access System: AgentHub workspace rules"
    )

    assert safe_failure_reason_summary(raw_error) == (
        "external_runtime_error: exit_code_1"
    )


def test_capability_profile_formatting_sanitizes_failure_reasons() -> None:
    raw_error = (
        "OpenAI Codex v0.137.0 workdir: /workspaces/demo "
        "approval: never sandbox: danger-full-access"
    )
    profile_text = _format_agent_capability_profile_v2(
        [
            AgentCapabilityProfileV2Item(
                agent_id="codex-helper",
                recent_failure_reasons=[
                    raw_error,
                    "document_quality: api.md has headings without section content.",
                ],
            )
        ]
    )

    assert "external_runtime_error" in profile_text
    assert "document_quality: api.md has headings without section content." in profile_text
    for forbidden in (
        "OpenAI Codex",
        "workdir:",
        "/workspaces/",
        "approval:",
        "sandbox:",
    ):
        assert forbidden not in profile_text
