"""Builtin tool exceptions."""

from __future__ import annotations


class WorkspaceViolation(PermissionError):  # noqa: N818 - matches workspace spec wording.
    """Raised when a tool attempts to escape the workspace."""


class ToolExecutionError(RuntimeError):
    """Raised when a tool fails without violating workspace boundaries."""

    def __init__(self, message: str, error_code: str = "tool_call_failed") -> None:
        super().__init__(message)
        self.error_code = error_code
