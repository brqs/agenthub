"""Immutable public static releases for workspace web artifacts."""

from __future__ import annotations

from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import quote
from uuid import UUID

from app.core.config import settings
from app.services.workspace_static_snapshot import StaticSnapshot, WorkspaceStaticSnapshotService


class WorkspaceStaticReleaseService:
    """Create and remove immutable static release snapshots."""

    def __init__(self, snapshot_service: WorkspaceStaticSnapshotService | None = None) -> None:
        self._snapshot_service = snapshot_service or WorkspaceStaticSnapshotService()

    def publish(
        self,
        workspace_root: Path,
        deployment_id: UUID,
        *,
        entry_path: str,
    ) -> tuple[StaticSnapshot, str, str]:
        """Publish a snapshot and return its metadata, token, and URL."""
        target = self.snapshot_path(deployment_id)
        snapshot = self._snapshot_service.build(workspace_root, target, entry_path=entry_path)
        release_token = token_urlsafe(settings.deployment_release_token_bytes)
        return snapshot, release_token, self.public_url(release_token, snapshot.entry_path)

    def remove(self, snapshot_path: str | None, deployment_id: UUID) -> None:
        """Remove a release snapshot."""
        target = Path(snapshot_path) if snapshot_path else self.snapshot_path(deployment_id)
        self._snapshot_service.remove(
            target,
            allowed_root=Path(settings.deployment_static_root),
        )

    def snapshot_path(self, deployment_id: UUID) -> Path:
        return Path(settings.deployment_static_root).expanduser() / str(deployment_id)

    def public_url(self, release_token: str, entry_path: str | None = None) -> str:
        base = f"{settings.deployment_public_base_url.rstrip('/')}/releases/{release_token}"
        quoted_entry = "/".join(quote(part) for part in entry_path.split("/")) if entry_path else ""
        return f"{base}/{quoted_entry}" if quoted_entry else base
