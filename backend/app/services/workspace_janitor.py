"""Periodic cleanup for workspace preview and deployment resources."""

from __future__ import annotations

import asyncio
import shutil
import time
from contextlib import suppress
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.workspace import WorkspaceDeployment, WorkspacePreviewSession
from app.services.workspace_deployment import WorkspaceDeploymentService
from app.services.workspace_preview import WorkspacePreviewService


class WorkspaceResourceJanitor:
    """Remove idle sessions, expired archives, and orphan generated files."""

    async def cleanup_once(self) -> None:
        async with SessionFactory() as db:
            await WorkspacePreviewService().cleanup_stale(db)
            await WorkspaceDeploymentService().cleanup_expired(db)
            await db.commit()
            preview_paths = set(
                (
                    await db.execute(
                        select(WorkspacePreviewSession.snapshot_path).where(
                            WorkspacePreviewSession.snapshot_path.is_not(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
            release_paths = set(
                (
                    await db.execute(
                        select(WorkspaceDeployment.snapshot_path).where(
                            WorkspaceDeployment.snapshot_path.is_not(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
            export_paths = {
                str(
                    WorkspaceDeploymentService().export_path(
                        deployment.conversation_id,
                        deployment.id,
                    )
                )
                for deployment in (
                    await db.execute(
                        select(WorkspaceDeployment).where(
                            WorkspaceDeployment.kind == "source_zip",
                            WorkspaceDeployment.status == "published",
                        )
                    )
                )
                .scalars()
                .all()
            }
        self._remove_orphan_directories(Path(settings.preview_snapshot_dir), preview_paths)
        self._remove_orphan_directories(Path(settings.deployment_static_root), release_paths)
        self._remove_orphan_exports(Path(settings.deployment_export_dir), export_paths)

    async def run_forever(self) -> None:
        """Run cleanup until cancelled by application shutdown."""
        while True:
            with suppress(Exception):
                await self.cleanup_once()
            await asyncio.sleep(settings.deployment_janitor_interval_seconds)

    def _remove_orphan_directories(self, root: Path, tracked: set[str | None]) -> None:
        expected = {str(Path(item).resolve()) for item in tracked if item}
        if not root.exists():
            return
        for child in root.iterdir():
            if str(child.resolve()) in expected:
                continue
            if self._is_recent_generated_path(child):
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    def _remove_orphan_exports(self, root: Path, tracked: set[str]) -> None:
        expected = {str(Path(item).resolve()) for item in tracked}
        if not root.exists():
            return
        for path in root.rglob("*.zip"):
            if str(path.resolve()) not in expected and not self._is_recent_generated_path(path):
                path.unlink(missing_ok=True)
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir():
                with suppress(OSError):
                    path.rmdir()

    def _is_recent_generated_path(self, path: Path) -> bool:
        """Avoid deleting resources created by an uncommitted long-running request."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return True
        grace_seconds = max(settings.deployment_janitor_interval_seconds * 2, 600)
        return time.time() - mtime < grace_seconds
