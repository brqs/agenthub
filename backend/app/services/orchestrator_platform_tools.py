"""Platform tool executor used by Orchestrator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.tools import OrchestratorToolResult
from app.services.browser_preview_verifier import (
    BrowserPreviewVerifier,
    BrowserPreviewVerifyDisabledError,
    BrowserPreviewVerifyError,
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

PLATFORM_TOOL_NAMES = {"start_workspace_preview", "verify_web_preview"}


class OrchestratorPlatformToolExecutor:
    """Execute platform-owned tools on behalf of Orchestrator."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        conversation_id: UUID,
        preview_service: WorkspacePreviewService | None = None,
        browser_verifier: BrowserPreviewVerifier | None = None,
    ) -> None:
        self._db = db
        self._conversation_id = conversation_id
        self._preview_service = preview_service or WorkspacePreviewService()
        self._browser_verifier = browser_verifier or BrowserPreviewVerifier()

    async def __call__(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> OrchestratorToolResult:
        if tool_name == "start_workspace_preview":
            return await self._start_workspace_preview(arguments)
        if tool_name == "verify_web_preview":
            return await self._verify_web_preview(arguments)
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


def _required_str(value: object, field: str) -> str | OrchestratorToolResult:
    if not isinstance(value, str) or not value.strip():
        return _tool_error(f"{field} must be a non-empty string", "invalid_arguments")
    return value.strip()


def _optional_port(value: object) -> int | None | OrchestratorToolResult:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return _tool_error("requested_port must be an integer", "invalid_arguments")
    if not 1 <= value <= 65535:
        return _tool_error("requested_port must be between 1 and 65535", "invalid_arguments")
    return value


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
