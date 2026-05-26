"""Workspace filesystem sandbox service."""

from __future__ import annotations

import json
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workspace import Workspace


class WorkspaceViolation(RuntimeError):  # noqa: N818 - spec uses this public name.
    """Raised when a path or operation escapes workspace policy."""


class WorkspaceFileTooLarge(RuntimeError):  # noqa: N818 - spec uses this public name.
    """Raised when a file exceeds the configured read limit."""


class WorkspaceFileNotFound(RuntimeError):  # noqa: N818 - spec uses this public name.
    """Raised when a requested workspace file does not exist."""


FORBIDDEN_PATH_PARTS = {".agenthub", ".env", ".git", ".ssh", "secrets"}
TEXT_MIME_OVERRIDES = {
    ".css": "text/css",
    ".htm": "text/html",
    ".html": "text/html",
    ".js": "text/javascript",
    ".json": "application/json",
    ".jsx": "text/javascript",
    ".md": "text/markdown",
    ".mjs": "text/javascript",
    ".py": "text/x-python",
    ".ts": "text/typescript",
    ".tsx": "text/tsx",
    ".txt": "text/plain",
}


class WorkspaceService:
    """Create and guard per-conversation workspace directories."""

    async def get_or_create(self, db: AsyncSession, conversation_id: UUID) -> Workspace:
        stmt = select(Workspace).where(Workspace.conversation_id == conversation_id)
        workspace = (await db.execute(stmt)).scalar_one_or_none()
        root = self._workspace_root(conversation_id)
        if workspace is None:
            workspace = Workspace(conversation_id=conversation_id, root_path=str(root))
            db.add(workspace)
        else:
            workspace.root_path = str(root)
        self._initialize_directory(root, conversation_id)
        workspace.last_accessed_at = datetime.now(UTC)
        await db.flush()
        return workspace

    async def delete(self, db: AsyncSession, conversation_id: UUID) -> None:
        stmt = select(Workspace).where(Workspace.conversation_id == conversation_id)
        workspace = (await db.execute(stmt)).scalar_one_or_none()
        root = Path(workspace.root_path) if workspace else self._workspace_root(conversation_id)
        root = self._safe_workspace_delete_root(root)
        if workspace is not None:
            await db.delete(workspace)
            await db.flush()
        shutil.rmtree(root, ignore_errors=True)

    def validate_read_path(self, workspace_root: Path, user_path: str) -> Path:
        candidate = self._resolve_user_path(workspace_root, user_path)
        if not candidate.exists() or not candidate.is_file():
            raise WorkspaceFileNotFound(f"workspace file not found: {user_path}")
        if candidate.stat().st_size > settings.workspace_max_read_bytes:
            raise WorkspaceFileTooLarge(f"workspace file too large: {user_path}")
        return candidate

    def validate_write_path(self, workspace_root: Path, user_path: str) -> Path:
        candidate = self._resolve_user_path(workspace_root, user_path)
        if candidate.exists() and candidate.is_dir():
            raise WorkspaceViolation(f"cannot write to directory: {user_path}")
        return candidate

    def list_tree(self, workspace: Workspace, max_depth: int = 5) -> dict[str, Any]:
        root = Path(workspace.root_path).resolve()
        if not root.exists():
            return {"name": root.name, "path": "", "type": "directory", "children": []}
        return self._tree_node(root, root, max(max_depth, 0), current_depth=0)

    def read_file(self, workspace: Workspace, rel_path: str) -> tuple[bytes, str]:
        path = self.validate_read_path(Path(workspace.root_path), rel_path)
        return path.read_bytes(), self._mime_type(path)

    def write_file(self, workspace: Workspace, rel_path: str, content: bytes) -> None:
        path = self.validate_write_path(Path(workspace.root_path), rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _workspace_root(self, conversation_id: UUID) -> Path:
        base = Path(settings.workspace_base_dir).expanduser()
        return base / str(conversation_id)

    def _safe_workspace_delete_root(self, root: Path) -> Path:
        base = Path(settings.workspace_base_dir).expanduser().resolve()
        resolved_root = root.expanduser().resolve()
        try:
            resolved_root.relative_to(base)
        except ValueError as exc:
            raise WorkspaceViolation("workspace root escapes workspace base") from exc
        return resolved_root

    def _initialize_directory(self, root: Path, conversation_id: UUID) -> None:
        root.mkdir(parents=True, exist_ok=True)
        metadata_dir = root / ".agenthub"
        metadata_dir.mkdir(exist_ok=True)
        manifest_path = metadata_dir / "manifest.json"
        if not manifest_path.exists():
            manifest_path.write_text(
                json.dumps(
                    {
                        "conversation_id": str(conversation_id),
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
        readme_path = root / "README.md"
        if not readme_path.exists():
            readme_path.write_text(
                f"# AgentHub Workspace\n\nConversation: `{conversation_id}`\n",
                encoding="utf-8",
            )

    def _resolve_user_path(self, workspace_root: Path, user_path: str) -> Path:
        if not user_path or not user_path.strip():
            raise WorkspaceViolation("workspace path is empty")
        normalized_user_path = user_path.replace("\\", "/").strip()
        raw_path = Path(normalized_user_path)
        if raw_path.is_absolute() or PureWindowsPath(user_path).is_absolute():
            raise WorkspaceViolation(f"absolute path is not allowed: {user_path}")
        if PureWindowsPath(user_path).drive:
            raise WorkspaceViolation(f"drive path is not allowed: {user_path}")

        parts = [part for part in raw_path.parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise WorkspaceViolation(f"path traversal is not allowed: {user_path}")
        if any(part in FORBIDDEN_PATH_PARTS for part in parts):
            raise WorkspaceViolation(f"forbidden path component: {user_path}")

        root = workspace_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._reject_symlink_in_existing_path(root, parts)
        candidate = (root / Path(*parts)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise WorkspaceViolation(f"path escapes workspace: {user_path}") from exc
        return candidate

    def _reject_symlink_in_existing_path(self, root: Path, parts: list[str]) -> None:
        current = root
        for part in parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspaceViolation(f"symlink path component is not allowed: {part}")

    def _tree_node(
        self,
        path: Path,
        root: Path,
        max_depth: int,
        *,
        current_depth: int,
    ) -> dict[str, Any]:
        rel_path = "" if path == root else path.relative_to(root).as_posix()
        if path.is_file():
            return {
                "name": path.name,
                "path": rel_path,
                "type": "file",
                "size": path.stat().st_size,
                "mime_type": self._mime_type(path),
            }
        node: dict[str, Any] = {
            "name": path.name,
            "path": rel_path,
            "type": "directory",
            "children": [],
        }
        if current_depth >= max_depth:
            return node
        children: list[dict[str, Any]] = []
        for child in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name)):
            if child.name in FORBIDDEN_PATH_PARTS or child.is_symlink():
                continue
            children.append(
                self._tree_node(child, root, max_depth, current_depth=current_depth + 1)
            )
        node["children"] = children
        return node

    def _mime_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in TEXT_MIME_OVERRIDES:
            return TEXT_MIME_OVERRIDES[suffix]
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or "application/octet-stream"
