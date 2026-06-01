"""Platform tool executor used by Orchestrator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.config_validation import AgentConfigValidationError, validate_agent_config
from app.agents.orchestrator.tools import OrchestratorToolResult
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.services.browser_preview_verifier import (
    BrowserPreviewVerifier,
    BrowserPreviewVerifyDisabledError,
    BrowserPreviewVerifyError,
)
from app.services.workspace_deployment import (
    WorkspaceDeploymentDisabledError,
    WorkspaceDeploymentError,
    WorkspaceDeploymentNotFoundError,
    WorkspaceDeploymentService,
)
from app.services.workspace_preview import (
    WorkspacePreviewDisabledError,
    WorkspacePreviewService,
    WorkspacePreviewStartError,
)
from app.services.workspace_service import (
    WorkspaceFileNotFound,
    WorkspaceFileTooLarge,
    WorkspaceViolation,
)

PLATFORM_TOOL_NAMES = {
    "start_workspace_preview",
    "verify_web_preview",
    "create_custom_agent",
    "create_deployment",
    "get_deployment_status",
    "package_workspace_source",
}
CREATABLE_PROVIDERS = {"builtin", "claude_code", "codex", "opencode"}


class OrchestratorPlatformToolExecutor:
    """Execute platform-owned tools on behalf of Orchestrator."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        conversation_id: UUID,
        preview_service: WorkspacePreviewService | None = None,
        browser_verifier: BrowserPreviewVerifier | None = None,
        deployment_service: WorkspaceDeploymentService | None = None,
    ) -> None:
        self._db = db
        self._conversation_id = conversation_id
        self._preview_service = preview_service or WorkspacePreviewService()
        self._browser_verifier = browser_verifier or BrowserPreviewVerifier()
        self._deployment_service = deployment_service or WorkspaceDeploymentService(
            preview_service=self._preview_service
        )

    async def __call__(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        if tool_name == "start_workspace_preview":
            return await self._start_workspace_preview(arguments)
        if tool_name == "verify_web_preview":
            return await self._verify_web_preview(arguments)
        if tool_name == "create_custom_agent":
            return await self._create_custom_agent(arguments)
        if tool_name == "create_deployment":
            return await self._create_deployment(arguments)
        if tool_name == "get_deployment_status":
            return await self._get_deployment_status(arguments)
        if tool_name == "package_workspace_source":
            return await self._package_workspace_source(arguments)
        return OrchestratorToolResult(
            status="error",
            output=f"platform tool is not allowed: {tool_name}",
            error_code="tool_not_allowed",
        )

    async def _start_workspace_preview(
        self,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        mode = arguments.get("mode", "static")
        if mode != "static":
            return _tool_error("only static preview mode is supported", "invalid_arguments")
        entry_path = _required_str(arguments.get("entry_path"), "entry_path")
        if isinstance(entry_path, OrchestratorToolResult):
            return entry_path
        requested_port = _optional_port(arguments.get("requested_port"))
        if isinstance(requested_port, OrchestratorToolResult):
            return requested_port
        try:
            session = await self._preview_service.start(
                self._db,
                self._conversation_id,
                entry_path=entry_path,
                requested_port=requested_port,
            )
        except (
            WorkspacePreviewDisabledError,
            WorkspacePreviewStartError,
            WorkspaceViolation,
            WorkspaceFileNotFound,
            WorkspaceFileTooLarge,
        ) as exc:
            return _tool_error(str(exc), _preview_error_code(exc))
        return OrchestratorToolResult(
            status="ok",
            output=_json_output(
                {
                    "status": session.status,
                    "mode": WorkspacePreviewService.mode,
                    "entry_path": session.entry_path,
                    "port": session.port,
                    "url": session.url,
                }
            ),
        )

    async def _create_deployment(
        self,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        kind = _required_str(arguments.get("kind"), "kind")
        if isinstance(kind, OrchestratorToolResult):
            return kind
        if kind not in {"static_site", "source_zip", "container"}:
            return _tool_error(
                "kind must be one of: static_site, source_zip, container",
                "invalid_deployment_kind",
            )
        requested_port = _optional_port(arguments.get("requested_port"))
        if isinstance(requested_port, OrchestratorToolResult):
            return requested_port
        entry_path = _optional_str(arguments.get("entry_path"))
        try:
            deployment = await self._deployment_service.create(
                self._db,
                self._conversation_id,
                kind=kind,
                entry_path=entry_path,
                requested_port=requested_port,
            )
        except (
            WorkspaceDeploymentDisabledError,
            WorkspaceDeploymentError,
            WorkspaceDeploymentNotFoundError,
            WorkspaceViolation,
            WorkspaceFileNotFound,
            WorkspaceFileTooLarge,
        ) as exc:
            return _tool_error(str(exc), _deployment_error_code(exc))
        return OrchestratorToolResult(
            status="ok",
            output=_json_output(_deployment_payload(deployment.summary())),
        )

    async def _get_deployment_status(
        self,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        deployment_id = _uuid_value(arguments.get("deployment_id"), "deployment_id")
        if isinstance(deployment_id, OrchestratorToolResult):
            return deployment_id
        deployment = await self._deployment_service.get(
            self._db,
            self._conversation_id,
            deployment_id,
        )
        if deployment is None:
            return _tool_error("workspace deployment not found", "deployment_not_found")
        return OrchestratorToolResult(
            status="ok",
            output=_json_output(_deployment_payload(deployment.summary())),
        )

    async def _package_workspace_source(
        self,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        fmt = arguments.get("format", "zip")
        if fmt != "zip":
            return _tool_error("only zip source exports are supported", "invalid_arguments")
        try:
            deployment = await self._deployment_service.package_source_zip(
                self._db,
                self._conversation_id,
            )
        except (
            WorkspaceDeploymentDisabledError,
            WorkspaceDeploymentError,
            WorkspaceViolation,
            WorkspaceFileNotFound,
            WorkspaceFileTooLarge,
        ) as exc:
            return _tool_error(str(exc), _deployment_error_code(exc))
        return OrchestratorToolResult(
            status="ok",
            output=_json_output(_deployment_payload(deployment.summary())),
        )

    async def _verify_web_preview(
        self,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        session = await self._preview_service.get(self._db, self._conversation_id)
        if session is None:
            return _tool_error("workspace preview session not found", "workspace_preview_not_found")
        if session.status != "running":
            return _tool_error("workspace preview session is not running", "preview_not_running")
        try:
            report = await self._browser_verifier.verify(
                conversation_id=self._conversation_id,
                url=session.url,
                required_text=_string_list(arguments.get("required_text")),
                viewports=_string_list(arguments.get("viewports")),
                click_buttons=arguments.get("click_buttons") is not False,
                max_clicks=_int_value(arguments.get("max_clicks"), default=5),
            )
        except (BrowserPreviewVerifyDisabledError, BrowserPreviewVerifyError) as exc:
            return _tool_error(str(exc), _browser_verify_error_code(exc))
        return OrchestratorToolResult(
            status="ok" if report.get("passed") is True else "error",
            output=_json_output(report),
            error_code=None if report.get("passed") is True else "browser_verification_failed",
        )

    async def _create_custom_agent(
        self,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        missing = [
            field
            for field in ("name", "provider", "system_prompt")
            if not isinstance(arguments.get(field), str) or not arguments.get(field, "").strip()
        ]
        if missing:
            return OrchestratorToolResult(
                status="error",
                output=_json_output(
                    {
                        "status": "error",
                        "error": "missing required fields for custom agent",
                        "missing_fields": missing,
                    }
                ),
                error_code="missing_required_agent_fields",
                needs_user_input=True,
            )

        name = str(arguments["name"]).strip()
        provider = str(arguments["provider"]).strip()
        system_prompt = str(arguments["system_prompt"]).strip()
        if provider not in CREATABLE_PROVIDERS:
            return _tool_error(
                "provider must be one of: builtin, claude_code, codex, opencode",
                "invalid_provider",
            )
        capabilities = _string_list(arguments.get("capabilities"))
        raw_config = arguments.get("config", {})
        if not isinstance(raw_config, Mapping):
            return _tool_error("config must be an object", "invalid_arguments")
        config = dict(raw_config)
        try:
            normalized_config = validate_agent_config(
                provider=provider,
                config=config,
                system_prompt=system_prompt,
            )
        except AgentConfigValidationError as exc:
            return _tool_error(exc.message, exc.code)

        conversation = await self._db.get(Conversation, self._conversation_id)
        if conversation is None:
            return _tool_error("conversation not found", "conversation_not_found")

        agent = Agent(
            id=Agent.new_id(),
            user_id=conversation.user_id,
            name=name,
            provider=provider,
            avatar_url=_optional_str(arguments.get("avatar_url")) or "",
            capabilities=capabilities,
            system_prompt=system_prompt,
            config=normalized_config,
            is_builtin=False,
        )
        self._db.add(agent)
        add_to_conversation = arguments.get("add_to_conversation") is True
        if add_to_conversation and conversation.mode == "group":
            agent_ids = [
                item for item in conversation.agent_ids if isinstance(item, str)
            ]
            if agent.id not in agent_ids:
                conversation.agent_ids = [*agent_ids, agent.id]
                flag_modified(conversation, "agent_ids")
        await self._db.flush()
        return OrchestratorToolResult(
            status="ok",
            output=_json_output(
                {
                    "status": "ok",
                    "agent": {
                        "id": agent.id,
                        "name": agent.name,
                        "provider": agent.provider,
                        "capabilities": agent.capabilities,
                        "is_builtin": agent.is_builtin,
                    },
                    "added_to_conversation": add_to_conversation
                    and conversation.mode == "group",
                }
            ),
        )


def _required_str(value: object, field: str) -> str | OrchestratorToolResult:
    if not isinstance(value, str) or not value.strip():
        return _tool_error(f"{field} must be a non-empty string", "invalid_arguments")
    return value.strip()


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _optional_port(value: object) -> int | None | OrchestratorToolResult:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return _tool_error("requested_port must be an integer", "invalid_arguments")
    if not 1 <= value <= 65535:
        return _tool_error("requested_port must be between 1 and 65535", "invalid_arguments")
    return value


def _uuid_value(value: object, field: str) -> UUID | OrchestratorToolResult:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or not value.strip():
        return _tool_error(f"{field} must be a UUID string", "invalid_arguments")
    try:
        return UUID(value.strip())
    except ValueError:
        return _tool_error(f"{field} must be a UUID string", "invalid_arguments")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _int_value(value: object, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _tool_error(message: str, error_code: str) -> OrchestratorToolResult:
    return OrchestratorToolResult(
        status="error",
        output=_json_output({"error": message, "status": "error"}),
        error_code=error_code,
    )


def _json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _preview_error_code(exc: Exception) -> str:
    if isinstance(exc, WorkspacePreviewDisabledError):
        return "workspace_preview_disabled"
    if isinstance(exc, WorkspacePreviewStartError):
        return "workspace_preview_start_failed"
    if isinstance(exc, WorkspaceFileNotFound):
        return "preview_entry_not_found"
    if isinstance(exc, WorkspaceFileTooLarge):
        return "preview_entry_too_large"
    return "workspace_violation"


def _browser_verify_error_code(exc: Exception) -> str:
    if isinstance(exc, BrowserPreviewVerifyDisabledError):
        return "browser_preview_verify_disabled"
    return "browser_preview_verify_failed"


def _deployment_error_code(exc: Exception) -> str:
    if isinstance(exc, WorkspaceDeploymentDisabledError):
        return "workspace_deployment_disabled"
    if isinstance(exc, WorkspaceDeploymentNotFoundError):
        return "deployment_not_found"
    if isinstance(exc, WorkspaceFileNotFound):
        return "deployment_entry_not_found"
    if isinstance(exc, WorkspaceFileTooLarge):
        return "deployment_artifact_too_large"
    if isinstance(exc, WorkspaceViolation):
        return "workspace_violation"
    return "workspace_deployment_failed"


def _deployment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["status_card"] = {
        "type": "deployment_status",
        "deployment_id": payload.get("deployment_id", ""),
        "kind": payload.get("kind", "static_site"),
        "status": payload.get("status", "failed"),
        "title": _deployment_title(payload),
        "url": payload.get("url"),
        "download_url": payload.get("download_url"),
        "error": payload.get("error"),
        "logs_preview": payload.get("logs_preview"),
        "size_bytes": payload.get("size_bytes"),
    }
    return payload


def _deployment_title(payload: Mapping[str, Any]) -> str:
    kind = payload.get("kind")
    status = payload.get("status")
    if kind == "source_zip":
        return "Workspace source archive"
    if kind == "container":
        return "Container deployment"
    return "Static site deployment" if status != "not_supported" else "Deployment"
