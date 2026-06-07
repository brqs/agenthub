"""Shared AgentConfig field metadata.

This module keeps numeric config ranges in one place for validation and API
schemas. It intentionally contains no provider behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

SUPPORTED_UPSTREAM_PROVIDERS: set[str] = {"claude", "deepseek", "openai"}
TOP_LEVEL_PROVIDERS: set[str] = {
    "claude_code",
    "codex",
    "opencode",
    "builtin",
    "mock",
}
CODEX_RUNTIMES: set[str] = {"cli", "sdk"}
CODEX_SANDBOX_MODES: set[str] = {"read-only", "workspace-write", "danger-full-access"}


@dataclass(frozen=True)
class NumericConfigField:
    key: str
    minimum: int | float
    maximum: int | float
    allow_float: bool = True


EXTERNAL_RUNTIME_BUDGET_FIELDS: tuple[NumericConfigField, ...] = (
    NumericConfigField("timeout_seconds", 1, 3600),
    NumericConfigField("max_runtime_seconds", 1, 3600),
    NumericConfigField("idle_timeout_seconds", 1, 3600),
    NumericConfigField("heartbeat_interval_seconds", 1, 3600),
)

EXTERNAL_DIRECT_CHAT_FIELDS: tuple[NumericConfigField, ...] = (
    NumericConfigField("qa_max_tokens", 1, 32000, allow_float=False),
    NumericConfigField("qa_classifier_max_tokens", 1, 1024, allow_float=False),
    NumericConfigField("qa_temperature", 0, 2),
    NumericConfigField("qa_request_timeout_seconds", 1, 120),
)

BUILTIN_ORCHESTRATOR_FIELDS: tuple[NumericConfigField, ...] = (
    NumericConfigField("max_iterations", 1, 50, allow_float=False),
    NumericConfigField("react_decision_max_tokens", 1, 4096, allow_float=False),
    NumericConfigField("max_task_attempts", 1, 3, allow_float=False),
    NumericConfigField("task_result_context_max_chars", 1, 32000, allow_float=False),
    NumericConfigField("task_result_item_max_chars", 1, 8000, allow_float=False),
    NumericConfigField("orchestrator_memory_recent_runs", 1, 10, allow_float=False),
    NumericConfigField("orchestrator_memory_context_max_chars", 1, 32000, allow_float=False),
    NumericConfigField("auto_clarification_max_questions", 0, 8, allow_float=False),
    NumericConfigField("grill_max_questions", 1, 12, allow_float=False),
    NumericConfigField("orchestrator_tool_max_iterations", 1, 50, allow_float=False),
    NumericConfigField("orchestrator_tool_result_max_chars", 1, 32000, allow_float=False),
    NumericConfigField("orchestrator_tool_read_max_bytes", 1, 1048576, allow_float=False),
    NumericConfigField("orchestrator_parallel_max_concurrency", 1, 10, allow_float=False),
    NumericConfigField(
        "orchestrator_response_polish_max_tokens",
        1,
        4096,
        allow_float=False,
    ),
    NumericConfigField(
        "orchestrator_evaluation_read_max_bytes",
        1,
        1048576,
        allow_float=False,
    ),
)

NUMERIC_CONFIG_FIELDS: dict[str, NumericConfigField] = {
    field.key: field
    for group in (
        EXTERNAL_RUNTIME_BUDGET_FIELDS,
        EXTERNAL_DIRECT_CHAT_FIELDS,
        BUILTIN_ORCHESTRATOR_FIELDS,
    )
    for field in group
}


def numeric_field(key: str) -> NumericConfigField:
    return NUMERIC_CONFIG_FIELDS[key]


EXTERNAL_DIRECT_CHAT_DEFAULTS: dict[str, object] = {
    "qa_short_circuit_enabled": True,
    "qa_model_backend": "deepseek",
    "qa_max_tokens": 2048,
    "qa_classifier_max_tokens": 128,
    "qa_temperature": 0.2,
    "qa_request_timeout_seconds": 20,
}

ORCHESTRATOR_DEFAULTS: dict[str, object] = {
    "model_backend": "claude",
    "answer_model_backend": "deepseek",
    "planner_model_backend": "deepseek",
    "llm_planning": settings.orchestrator_llm_planning_default,
    "react_enabled": True,
    "react_trace_visible": False,
    "direct_answer_on_planner_failure": True,
    "task_fallback_agent_ids": ["claude-code", "opencode-helper", "codex-helper"],
    "max_task_attempts": 3,
    "max_iterations": 10,
    "orchestrator_memory_enabled": True,
    "orchestrator_memory_recent_runs": 3,
    "orchestrator_memory_context_max_chars": 6000,
    "clarification_gate_enabled": True,
    "auto_clarification_max_questions": 3,
    "grill_max_questions": 8,
    "workspace_docs_enabled": True,
    "orchestrator_tool_calling_enabled": False,
    "orchestrator_tool_trace_visible": True,
    "orchestrator_tool_max_iterations": 12,
    "orchestrator_tool_result_max_chars": 4000,
    "orchestrator_tool_read_max_bytes": 65536,
    "orchestrator_group_messages_enabled": True,
    "orchestrator_process_block_enabled": True,
    "orchestrator_response_polish_enabled": True,
    "orchestrator_response_polish_model_backend": None,
    "orchestrator_response_polish_max_tokens": 900,
    "orchestrator_parallel_enabled": settings.orchestrator_parallel_enabled_default,
    "orchestrator_parallel_max_concurrency": (
        settings.orchestrator_parallel_max_concurrency_default
    ),
    "orchestrator_evaluation_enabled": True,
    "orchestrator_evaluation_read_max_bytes": 65536,
    "orchestrator_test_runner_enabled": False,
    "orchestrator_test_command_allowlist": [],
}
