"""Agent schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agents.config_fields import numeric_field
from app.schemas.common import OffsetPagination
from app.schemas.message import ContentBlock

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
ModelProfileSource = Literal["agenthub_default", "user_account"]
AgentKnowledgeUsage = Literal["reference", "policy", "template", "example"]
AgentAssetKind = Literal["knowledge", "skill"]
AgentAssetStatus = Literal["active", "unbound"]
AgentAssetVersionAction = Literal["created", "updated", "unbound", "materialized"]
AgentAssetUsageStatus = Literal["injected", "skipped", "failed"]
AgentMemoryPolicy = Literal["none", "conversation", "project", "user"]
AgentClarificationPolicy = Literal["ask_first", "balanced", "decide_with_defaults"]
AgentPermissionCommandPolicy = Literal["never", "ask", "auto_low_risk"]
AgentPermissionNetworkPolicy = Literal["never", "ask", "allowlisted"]
AgentPermissionAskPolicy = Literal["never", "ask"]
AgentMCPHealthStatus = Literal["ready", "unavailable"]
AgentTestRunStatus = Literal["done", "error"]


class AgentBuilderProfile(BaseModel):
    role: str | None = Field(default=None, max_length=400)
    purpose: str | None = Field(default=None, max_length=400)
    goals: list[str] = Field(default_factory=list, max_length=12)
    tone: str | None = Field(default=None, max_length=160)
    do_not_do: list[str] = Field(default_factory=list, max_length=12)
    clarification_policy: AgentClarificationPolicy = "balanced"
    output_style: str | None = Field(default=None, max_length=400)
    starters: list[str] = Field(default_factory=list, max_length=8)


class AgentPermissions(BaseModel):
    workspace_read: bool = False
    workspace_write: bool = False
    run_commands: AgentPermissionCommandPolicy = "never"
    network: AgentPermissionNetworkPolicy = "never"
    deploy: AgentPermissionAskPolicy = "never"
    external_accounts: AgentPermissionAskPolicy = "never"


class AgentModelProfile(BaseModel):
    source: ModelProfileSource = "agenthub_default"
    account_id: UUID | None = None
    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=160)


class AgentConfig(BaseModel):
    model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for builtin agents.",
    )
    model_profile: AgentModelProfile | None = Field(
        default=None,
        description="User-facing model selection for builtin custom agents.",
    )
    answer_model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for orchestrator direct answers.",
    )
    planner_model_backend: ModelBackend | None = Field(
        default=None,
        description="ModelGateway backend for orchestrator LLM planning.",
    )
    context_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("context_max_tokens").minimum,
        le=numeric_field("context_max_tokens").maximum,
        description="Maximum conversation context tokens passed to this agent.",
    )
    orchestrator_context_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_context_max_tokens").minimum,
        le=numeric_field("orchestrator_context_max_tokens").maximum,
        description="Maximum context tokens used by the Orchestrator main flow.",
    )
    orchestrator_subagent_context_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_subagent_context_max_tokens").minimum,
        le=numeric_field("orchestrator_subagent_context_max_tokens").maximum,
        description="Maximum context tokens passed from Orchestrator to sub-agents.",
    )
    llm_planning: bool | None = None
    planner_fallback_to_template: bool | None = None
    available_agents_authoritative: bool | None = None
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
    builder_profile: AgentBuilderProfile | None = None
    permissions: AgentPermissions | None = None
    memory_policy: AgentMemoryPolicy | None = None
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
    orchestrator_tool_max_tokens: int | None = Field(
        default=None,
        ge=numeric_field("orchestrator_tool_max_tokens").minimum,
        le=numeric_field("orchestrator_tool_max_tokens").maximum,
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
    clarification_gate_enabled: bool | None = None
    auto_clarification_max_questions: int | None = Field(
        default=None,
        ge=numeric_field("auto_clarification_max_questions").minimum,
        le=numeric_field("auto_clarification_max_questions").maximum,
    )
    requirement_alignment_llm_enabled: bool | None = None
    grill_max_questions: int | None = Field(
        default=None,
        ge=numeric_field("grill_max_questions").minimum,
        le=numeric_field("grill_max_questions").maximum,
    )
    workspace_docs_enabled: bool | None = None
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


class AgentKnowledgeOut(BaseModel):
    upload_id: UUID
    filename: str
    label: str
    usage: AgentKnowledgeUsage = "reference"
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class UpdateAgentKnowledgeRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=160)
    usage: AgentKnowledgeUsage | None = None


class AgentSkillOut(BaseModel):
    skill_id: str
    upload_id: UUID
    name: str
    description: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentSkillRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=240)


class AgentAssetBindingOut(BaseModel):
    id: UUID
    agent_id: str
    kind: AgentAssetKind
    status: AgentAssetStatus
    upload_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    label: str | None = None
    usage: AgentKnowledgeUsage | None = None
    skill_id: str | None = None
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    unbound_at: datetime | None = None


class AgentAssetsOut(BaseModel):
    knowledge: list[AgentKnowledgeOut] = Field(default_factory=list)
    skills: list[AgentSkillOut] = Field(default_factory=list)
    bindings: list[AgentAssetBindingOut] = Field(default_factory=list)


class AgentAssetVersionOut(BaseModel):
    id: UUID
    binding_id: UUID
    version: int
    action: AgentAssetVersionAction
    snapshot: dict[str, Any] = Field(default_factory=dict)
    actor_user_id: UUID | None = None
    created_at: datetime


class AgentAssetHistoryOut(BaseModel):
    items: list[AgentAssetVersionOut] = Field(default_factory=list)
    total: int


class AgentAssetUsageEventOut(BaseModel):
    id: UUID
    binding_id: UUID | None = None
    agent_id: str
    upload_id: UUID | None = None
    conversation_id: UUID | None = None
    run_id: str | None = None
    event_type: str
    status: AgentAssetUsageStatus
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentAssetUsageListOut(BaseModel):
    items: list[AgentAssetUsageEventOut] = Field(default_factory=list)
    total: int


class AgentTemplateOut(BaseModel):
    id: str
    name: str
    description: str
    category: str
    capabilities: list[str] = Field(default_factory=list)
    builder_profile: AgentBuilderProfile
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    memory_policy: AgentMemoryPolicy = "conversation"
    model_backend: ModelBackend = "deepseek"


class AgentTemplateListOut(BaseModel):
    items: list[AgentTemplateOut] = Field(default_factory=list)


class AgentMCPToolOut(BaseModel):
    name: str
    description: str | None = None


class AgentMCPServerHealthOut(BaseModel):
    name: str
    status: AgentMCPHealthStatus
    tools: list[AgentMCPToolOut] = Field(default_factory=list)
    error: str | None = None


class AgentMCPHealthOut(BaseModel):
    status: AgentMCPHealthStatus
    servers: list[AgentMCPServerHealthOut] = Field(default_factory=list)


class AgentTestRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class AgentTestRunOut(BaseModel):
    status: AgentTestRunStatus
    content: list[ContentBlock] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None


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
