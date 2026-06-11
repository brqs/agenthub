"""Native tool catalog and available-agent lookup."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.orchestrator.availability import scoped_runnable_agent_ids
from app.agents.types import ToolSpec


def orchestrator_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="dispatch_agent",
            description=(
                "Dispatch a task to one available AgentHub group member and return "
                "its observed result."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "title": {"type": "string"},
                    "instruction": {"type": "string"},
                    "expected_output": {"type": "string"},
                    "include_history": {"type": "boolean"},
                    "task_type": {
                        "type": "string",
                        "enum": [
                            "implementation",
                            "review",
                            "repair",
                            "conversation",
                            "dialogue_turn",
                        ],
                    },
                },
                "required": ["agent_id", "title", "instruction"],
            },
        ),
        ToolSpec(
            name="inspect_workspace",
            description="List workspace files and directories with metadata.",
            parameters={
                "type": "object",
                "properties": {
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
                    "path": {"type": "string"},
                },
            },
        ),
        ToolSpec(
            name="read_artifact",
            description="Read a text artifact from the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
        ),
        ToolSpec(
            name="validate_html",
            description="Validate that an HTML artifact contains expected static elements.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "required_title": {"type": "string"},
                    "require_input": {"type": "boolean"},
                    "require_button": {"type": "boolean"},
                    "require_script": {"type": "boolean"},
                    "required_text": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["path"],
            },
        ),
        ToolSpec(
            name="start_workspace_preview",
            description=(
                "Start or reuse a platform-managed static preview for a workspace HTML "
                "artifact. Use this for user preview/deploy/port requests."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "entry_path": {"type": "string"},
                    "mode": {"type": "string", "enum": ["static"], "default": "static"},
                    "requested_port": {"type": "integer", "minimum": 1, "maximum": 65535},
                },
                "required": ["entry_path"],
            },
        ),
        ToolSpec(
            name="verify_web_preview",
            description=(
                "Run browser-level quality verification against the current platform "
                "preview, including desktop/mobile rendering, JS errors, resources, "
                "visible text, screenshots, and basic button interactions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "required_text": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "viewports": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["desktop", "mobile"]},
                    },
                    "click_buttons": {"type": "boolean", "default": True},
                    "max_clicks": {"type": "integer", "minimum": 0, "maximum": 10},
                },
            },
        ),
        ToolSpec(
            name="create_custom_agent",
            description=(
                "Create a user-owned AgentHub custom agent as a wrapper around "
                "claude-code, codex-helper, or opencode-helper. Use this only "
                "after the user explicitly confirms creation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "provider": {
                        "type": "string",
                        "enum": ["claude_code", "codex", "opencode", "builtin"],
                    },
                    "system_prompt": {"type": "string"},
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "config": {
                        "type": "object",
                        "properties": {
                            "custom_agent_mode": {
                                "type": "string",
                                "const": "server_agent_wrapper",
                            },
                            "base_agent_id": {
                                "type": "string",
                                "enum": [
                                    "claude-code",
                                    "codex-helper",
                                    "opencode-helper",
                                ],
                            },
                            "wrapper_profile": {"type": "object"},
                            "model_backend": {
                                "type": "string",
                                "enum": ["claude", "deepseek", "openai"],
                            },
                            "allowed_tools": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": ["read_file"],
                                },
                            },
                        },
                    },
                    "add_to_conversation": {"type": "boolean", "default": True},
                },
                "required": ["name", "provider", "system_prompt", "config"],
            },
        ),
        ToolSpec(
            name="create_deployment",
            description=(
                "Create a platform-managed workspace deployment. Use static_site "
                "for deploy/publish/go-live requests, source_zip for source export, "
                "and container for platform-managed Docker/Podman deployment when enabled."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["static_site", "source_zip", "container"],
                    },
                    "entry_path": {"type": "string"},
                    "requested_port": {"type": "integer", "minimum": 1, "maximum": 65535},
                    "container_port": {"type": "integer", "minimum": 1, "maximum": 65535},
                    "health_path": {"type": "string"},
                    "start_command": {"type": "string"},
                    "wait_for_terminal": {"type": "boolean"},
                    "wait_timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 600,
                    },
                },
                "required": ["kind"],
            },
        ),
        ToolSpec(
            name="get_deployment_status",
            description="Read the status of a platform-managed deployment.",
            parameters={
                "type": "object",
                "properties": {"deployment_id": {"type": "string"}},
                "required": ["deployment_id"],
            },
        ),
        ToolSpec(
            name="stop_deployment",
            description="Stop a platform-managed deployment and release its resources.",
            parameters={
                "type": "object",
                "properties": {"deployment_id": {"type": "string"}},
                "required": ["deployment_id"],
            },
        ),
        ToolSpec(
            name="package_workspace_source",
            description="Package the current workspace into a downloadable source zip.",
            parameters={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["zip"], "default": "zip"}
                },
            },
        ),
        ToolSpec(
            name="ask_user",
            description="Stop and ask the user for missing information.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["question"],
            },
        ),
    ]

def available_agent_ids(config: Mapping[str, Any]) -> list[str]:
    scoped_ids = scoped_runnable_agent_ids(config)
    if scoped_ids is not None:
        return scoped_ids

    ids = _agent_ids_from_available_agents(config.get("available_agents"))
    if ids:
        return ids
    return _agent_id_list(config.get("managed_agent_ids", config.get("default_sub_agents")))

def _agent_ids_from_available_agents(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("agent_id", item.get("id"))
        if not isinstance(raw_id, str):
            continue
        agent_id = raw_id.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        ids.append(agent_id)
    return ids

def _agent_id_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        agent_id = item.strip()
        if not agent_id or agent_id == "orchestrator" or agent_id in seen:
            continue
        seen.add(agent_id)
        result.append(agent_id)
    return result
