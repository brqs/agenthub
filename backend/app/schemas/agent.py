"""Agent schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.config_fields import numeric_field
from app.schemas.common import OffsetPagination

AgentProvider = Literal[
    "claude_code",
    "codex",
    "opencode",
    "builtin",
    "mock",
    "claude",
    "deepseek",
    "openai",
    "custom",
]
CreatableAgentProvider = Literal["claude_code", "codex", "opencode", "builtin"]
ModelBackend = Literal["claude", "deepseek", "openai"]


class AgentConfig(BaseModel):
    model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for builtin agents.",
    )
    answer_model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for orchestrator direct answers.",
    )
    planner_model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for orchestrator LLM planning.",
    )
    llm_planning: bool | None = None
    planner_fallback_to_template: bool | None = None
    orchestrator_llm_config: dict[str, Any] | None = None
    max_iterations: int | None = Field(
        default=None,
        ge=numeric_field("max_iterations").minimum,
        le=numeric_field("max_iterations").maximum,
    )
    react_enabled: bool | None = None
    react_trace_visible: bool | None = None
    react_decision_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("react_decision_max_tokens").minimum,
        le=numeric_field("react_decision_max_tokens").maximum,
    )
    mcp_servers: list[dict[str, Any]] | None = None
    allowed_tools: list[str] | None = Field(
        default=None,
        description=(
            "Maximum builtin native/MCP tools this agent may receive. "
            "Omit to keep legacy behavior; [] means no tools."
        ),
    )
    command: str | list[str] | None = None
    args: list[str] | None = None
    timeout_seconds: float | None = Field(
        default=None,
        ge=numeric_field("timeout_seconds").minimum,
        le=numeric_field("timeout_seconds").maximum,
    )
    max_runtime_seconds: float | None = Field(
        default=None,
        ge=numeric_field("max_runtime_seconds").minimum,
        le=numeric_field("max_runtime_seconds").maximum,
    )
    idle_timeout_seconds: float | None = Field(
        default=None,
        ge=numeric_field("idle_timeout_seconds").minimum,
        le=numeric_field("idle_timeout_seconds").maximum,
    )
    heartbeat_interval_seconds: float | None = Field(
        default=None,
        ge=numeric_field("heartbeat_interval_seconds").minimum,
        le=numeric_field("heartbeat_interval_seconds").maximum,
    )
    qa_short_circuit_enabled: bool | None = None
    qa_model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for external direct chat.",
    )
    qa_model: str | None = None
    qa_classifier_model: str | None = None
    qa_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("qa_max_tokens").minimum,
        le=numeric_field("qa_max_tokens").maximum,
    )
    qa_classifier_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("qa_classifier_max_tokens").minimum,
        le=numeric_field("qa_classifier_max_tokens").maximum,
    )
    qa_temperature: float | None = Field(
        default=None,
        ge=numeric_field("qa_temperature").minimum,
        le=numeric_field("qa_temperature").maximum,
    )
    qa_request_timeout_seconds: float | None = Field(
        default=None,
        ge=numeric_field("qa_request_timeout_seconds").minimum,
        le=numeric_field("qa_request_timeout_seconds").maximum,
    )
    task_fallback_agent_ids: list[str] | None = None
    max_task_attempts: int | None = Field(
        default=None,
        ge=numeric_field("max_task_attempts").minimum,
        le=numeric_field("max_task_attempts").maximum,
    )
    task_result_context_max_chars: int | None = Field(
        default=None,
        ge=numeric_field("task_result_context_max_chars").minimum,
        le=numeric_field("task_result_context_max_chars").maximum,
    )
    task_result_item_max_chars: int | None = Field(
        default=None,
        ge=numeric_field("task_result_item_max_chars").minimum,
        le=numeric_field("task_result_item_max_chars").maximum,
    )
    orchestrator_memory_enabled: bool | None = None
    orchestrator_memory_recent_runs: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_memory_recent_runs").minimum,
        le=numeric_field("orchestrator_memory_recent_runs").maximum,
    )
    orchestrator_memory_context_max_chars: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_memory_context_max_chars").minimum,
        le=numeric_field("orchestrator_memory_context_max_chars").maximum,
    )
    orchestrator_tool_calling_enabled: bool | None = None
    orchestrator_tool_trace_visible: bool | None = None
    orchestrator_tool_max_iterations: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_tool_max_iterations").minimum,
        le=numeric_field("orchestrator_tool_max_iterations").maximum,
    )
    orchestrator_tool_result_max_chars: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_tool_result_max_chars").minimum,
        le=numeric_field("orchestrator_tool_result_max_chars").maximum,
    )
    orchestrator_tool_read_max_bytes: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_tool_read_max_bytes").minimum,
        le=numeric_field("orchestrator_tool_read_max_bytes").maximum,
    )
    orchestrator_group_messages_enabled: bool | None = None
    orchestrator_process_block_enabled: bool | None = None
    orchestrator_response_polish_enabled: bool | None = None
    orchestrator_response_polish_model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for Orchestrator final response polish.",
    )
    orchestrator_response_polish_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_response_polish_max_tokens").minimum,
        le=numeric_field("orchestrator_response_polish_max_tokens").maximum,
    )
    orchestrator_parallel_enabled: bool | None = None
    orchestrator_parallel_max_concurrency: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_parallel_max_concurrency").minimum,
        le=numeric_field("orchestrator_parallel_max_concurrency").maximum,
    )
    orchestrator_evaluation_enabled: bool | None = None
    orchestrator_evaluation_read_max_bytes: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_evaluation_read_max_bytes").minimum,
        le=numeric_field("orchestrator_evaluation_read_max_bytes").maximum,
    )
    orchestrator_test_runner_enabled: bool | None = None
    orchestrator_test_command_allowlist: list[str] | None = None

    # 允许额外 provider 专属字段
    model_config = ConfigDict(extra="allow")


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: AgentProvider
    avatar_url: str = ""
    capabilities: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    is_builtin: bool = False
    created_at: datetime


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    provider: CreatableAgentProvider
    avatar_url: str = ""
    capabilities: list[str] = Field(default_factory=list, max_length=10)
    system_prompt: str | None = Field(default=None, max_length=8192)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_url: str | None = None
    capabilities: list[str] | None = Field(default=None, max_length=10)
    system_prompt: str | None = Field(default=None, max_length=8192)
    config: dict[str, Any] | None = None


class AgentList(OffsetPagination[AgentOut]):
    pass
