"""Build guarded static snapshots from workspace web artifacts."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.services.workspace_service import (
    WorkspaceFileNotFound,
    WorkspaceFileTooLarge,
    WorkspaceViolation,
)

STATIC_SNAPSHOT_EXCLUDED_PARTS = {
    ".agenthub",
    ".env",
    ".git",
    ".ssh",
    ".venv",
    "__pycache__",
    "node_modules",
    "secrets",
}
STATIC_SNAPSHOT_ALLOWED_SUFFIXES = {
    ".css",
    ".eot",
    ".gif",
    ".htm",
    ".html",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mjs",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".txt",
    ".wasm",
    ".webmanifest",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
}


@dataclass(frozen=True)
class StaticSnapshot:
    """Metadata for a guarded static snapshot."""

    root: Path
    entry_path: str
    artifact_digest: str
    file_count: int
    size_bytes: int


class WorkspaceStaticSnapshotService:
    """Copy public web artifacts into an isolated immutable directory."""

    def build(self, workspace_root: Path, target: Path, *, entry_path: str) -> StaticSnapshot:
        root = workspace_root.expanduser().resolve()
        entry = self._validate_entry(root, entry_path)
        normalized_entry = entry.relative_to(root).as_posix()
        staging = target.parent / f".{target.name}.tmp-{uuid4().hex}"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=False)
        digest = hashlib.sha256()
        file_count = 0
        size_bytes = 0
        try:
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                if self._is_excluded(relative):
                    continue
                if path.is_symlink():
                    raise WorkspaceViolation(
                        f"static snapshot cannot include symlink: {relative.as_posix()}"
                    )
                if (
                    not path.is_file()
                    or path.suffix.lower() not in STATIC_SNAPSHOT_ALLOWED_SUFFIXES
                ):
                    continue
                stat = path.stat()
                if stat.st_size > settings.static_snapshot_max_single_file_bytes:
                    raise WorkspaceFileTooLarge(
                        f"static snapshot file is too large: {relative.as_posix()}"
                    )
                file_count += 1
                if file_count > settings.static_snapshot_max_file_count:
                    raise WorkspaceFileTooLarge("static snapshot contains too many files")
                size_bytes += stat.st_size
                if size_bytes > settings.static_snapshot_max_total_bytes:
                    raise WorkspaceFileTooLarge("static snapshot is too large")
                content = path.read_bytes()
                relative_text = relative.as_posix()
                digest.update(relative_text.encode("utf-8"))
                digest.update(b"\0")
                digest.update(content)
                digest.update(b"\0")
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            if not (staging / normalized_entry).is_file():
                raise WorkspaceFileNotFound(
                    f"static snapshot entry was not copied: {normalized_entry}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            old = target.parent / f".{target.name}.old-{uuid4().hex}"
            if target.exists():
                target.rename(old)
            try:
                staging.rename(target)
            except Exception:
                if old.exists():
                    old.rename(target)
                raise
            shutil.rmtree(old, ignore_errors=True)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return StaticSnapshot(
            root=target,
            entry_path=normalized_entry,
            artifact_digest=digest.hexdigest(),
            file_count=file_count,
            size_bytes=size_bytes,
        )

    def remove(self, target: Path, *, allowed_root: Path) -> None:
        """Remove a snapshot directory below a configured snapshot root."""
        root = allowed_root.expanduser().resolve()
        resolved = target.expanduser().resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise WorkspaceViolation(f"snapshot path escapes managed root: {target}") from exc
        if resolved == root:
            raise WorkspaceViolation(f"refusing to remove snapshot root: {target}")
        shutil.rmtree(resolved, ignore_errors=True)

    def _validate_entry(self, root: Path, entry_path: str) -> Path:
        normalized = entry_path.replace("\\", "/").strip()
        candidate = Path(normalized)
        if not normalized or candidate.is_absolute() or ".." in candidate.parts:
            raise WorkspaceViolation(f"invalid static snapshot entry: {entry_path}")
        if self._is_excluded(candidate):
            raise WorkspaceViolation(f"forbidden static snapshot entry: {entry_path}")
        raw_candidate = root / candidate
        current = root
        for part in candidate.parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspaceViolation(
                    f"static snapshot entry cannot include symlink: {entry_path}"
                )
        resolved = raw_candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise WorkspaceViolation(
                f"static snapshot entry escapes workspace: {entry_path}"
            ) from exc
        if not resolved.exists() or not resolved.is_file():
            raise WorkspaceFileNotFound(f"workspace file not found: {entry_path}")
        if resolved.is_symlink():
            raise WorkspaceViolation(f"static snapshot entry cannot be a symlink: {entry_path}")
        if resolved.suffix.lower() not in {".html", ".htm"}:
            raise WorkspaceViolation(f"static snapshot entry must be an HTML file: {entry_path}")
        return resolved

    def _is_excluded(self, relative: Path) -> bool:
        return any(
            part in STATIC_SNAPSHOT_EXCLUDED_PARTS or part.startswith(".env.")
            for part in relative.parts
        )
