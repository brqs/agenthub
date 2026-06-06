"""Platform-managed static preview sessions for workspace artifacts."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import ProxyHandler, build_opener
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workspace import WorkspacePreviewSession
from app.services.workspace.static_snapshot import WorkspaceStaticSnapshotService
from app.services.workspace_service import WorkspaceService, WorkspaceViolation


class WorkspacePreviewDisabledError(RuntimeError):
    """Raised when platform preview is disabled by configuration."""


class WorkspacePreviewStartError(RuntimeError):
    """Raised when the platform preview service cannot be started."""


class WorkspacePreviewService:
    """Start, reuse, query, and stop static HTTP previews for workspaces."""

    mode = "static"

    def __init__(
        self,
        workspace_service: WorkspaceService | None = None,
        snapshot_service: WorkspaceStaticSnapshotService | None = None,
    ) -> None:
        self._workspace_service = workspace_service or WorkspaceService()
        self._snapshot_service = snapshot_service or WorkspaceStaticSnapshotService()

    async def get(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> WorkspacePreviewSession | None:
        session = await self._session_for_conversation(db, conversation_id)
        if session is None:
            return None
        await self._refresh_session_status(session)
        session.last_accessed_at = datetime.now(UTC)
        await db.flush()
        return session

    async def start(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        entry_path: str,
        requested_port: int | None = None,
    ) -> WorkspacePreviewSession:
        if not settings.preview_enabled:
            raise WorkspacePreviewDisabledError("workspace preview is disabled")
        if requested_port is not None and not (
            settings.preview_port_start <= requested_port <= settings.preview_port_end
        ):
            raise WorkspacePreviewStartError(
                "requested preview port "
                f"{requested_port} is outside configured range "
                f"{settings.preview_port_start}-{settings.preview_port_end}"
            )

        workspace = await self._workspace_service.get_or_create(db, conversation_id)
        snapshot_path = self.snapshot_path(conversation_id)
        snapshot = self._snapshot_service.build(
            Path(workspace.root_path),
            snapshot_path,
            entry_path=entry_path,
        )
        normalized_entry_path = snapshot.entry_path

        session = await self._session_for_conversation(db, conversation_id)
        if session is not None:
            await self._refresh_session_status(session)
            if (
                session.entry_path == normalized_entry_path
                and session.artifact_digest == snapshot.artifact_digest
                and session.status == "running"
                and self._pid_alive(session.pid)
                and (requested_port is None or session.port == requested_port)
            ):
                session.last_accessed_at = datetime.now(UTC)
                await db.flush()
                return session
            await self._stop_process(session)
        else:
            session = WorkspacePreviewSession(
                conversation_id=conversation_id,
                workspace_id=workspace.id,
                entry_path=normalized_entry_path,
                port=0,
                url="",
                status="starting",
            )
            db.add(session)

        port = await self._allocate_port(
            db,
            conversation_id=conversation_id,
            preferred=requested_port or session.port or None,
            allow_fallback=requested_port is None,
        )
        session.workspace_id = workspace.id
        session.entry_path = normalized_entry_path
        session.snapshot_path = str(snapshot.root)
        session.artifact_digest = snapshot.artifact_digest
        session.port = port
        session.pid = None
        session.url = self._public_url(port, normalized_entry_path)
        session.status = "starting"
        session.error = None
        self._touch(session)
        await db.flush()

        process = self._start_process(snapshot.root, normalized_entry_path, port)
        session.pid = process.pid
        try:
            self._wait_until_healthy(port, normalized_entry_path)
        except Exception as exc:
            await self._stop_process(session)
            self._remove_snapshot(session)
            session.status = "error"
            session.error = str(exc)
            self._touch(session)
            await db.flush()
            raise WorkspacePreviewStartError(str(exc)) from exc

        session.status = "running"
        session.error = None
        self._touch(session)
        await db.flush()
        return session

    async def stop(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> WorkspacePreviewSession | None:
        session = await self._session_for_conversation(db, conversation_id)
        if session is None:
            return None
        await self._stop_process(session)
        self._remove_snapshot(session)
        session.status = "stopped"
        session.error = None
        self._touch(session)
        await db.flush()
        return session

    async def _session_for_conversation(
        self,
        db: AsyncSession,
        conversation_id: UUID,
    ) -> WorkspacePreviewSession | None:
        stmt = select(WorkspacePreviewSession).where(
            WorkspacePreviewSession.conversation_id == conversation_id
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _allocate_port(
        self,
        db: AsyncSession,
        *,
        conversation_id: UUID,
        preferred: int | None = None,
        allow_fallback: bool = True,
    ) -> int:
        if preferred is not None:
            await self._release_managed_port(
                db,
                preferred,
                exclude_conversation_id=conversation_id,
            )
        used_ports = set(
            (
                await db.execute(
                    select(WorkspacePreviewSession.port).where(
                        WorkspacePreviewSession.status.in_(("starting", "running"))
                    )
                )
            )
            .scalars()
            .all()
        )
        candidates: list[int] = []
        if preferred is not None:
            candidates.append(preferred)
        if allow_fallback:
            candidates.extend(range(settings.preview_port_start, settings.preview_port_end + 1))
        seen: set[int] = set()
        for port in candidates:
            if port in seen:
                continue
            seen.add(port)
            if port in used_ports and port != preferred:
                continue
            if self._port_available(port):
                return port
        if preferred is not None and not allow_fallback:
            raise WorkspacePreviewStartError(
                f"requested preview port {preferred} is not available"
            )
        raise WorkspacePreviewStartError("no preview port is available")

    async def _release_managed_port(
        self,
        db: AsyncSession,
        port: int,
        *,
        exclude_conversation_id: UUID,
    ) -> None:
        stmt = select(WorkspacePreviewSession).where(
            WorkspacePreviewSession.port == port,
            WorkspacePreviewSession.status.in_(("starting", "running")),
        )
        sessions = list((await db.execute(stmt)).scalars().all())
        released = False
        for session in sessions:
            if session.conversation_id == exclude_conversation_id:
                continue
            await self._refresh_session_status(session)
            if session.status not in {"starting", "running"}:
                continue
            await self._stop_process(session)
            try:
                self._remove_snapshot(session)
                session.error = "preview replaced by a newer explicit port request"
            except (OSError, WorkspaceViolation) as exc:
                session.snapshot_path = None
                session.artifact_digest = None
                session.error = f"preview replacement cleanup failed: {exc}"
            session.status = "stopped"
            self._touch(session)
            released = True
        if released:
            await db.flush()

    def _start_process(self, root: Path, entry_path: str, port: int) -> subprocess.Popen[bytes]:
        argv = [
            sys.executable,
            "-m",
            "app.services.workspace.static_server",
            "--root",
            str(root),
            "--entry",
            entry_path,
            "--port",
            str(port),
            "--frame-ancestors",
            settings.preview_allowed_frame_ancestors,
        ]
        if os.name == "nt":
            return subprocess.Popen(  # noqa: S603 - static argv, workspace path is validated.
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        return subprocess.Popen(  # noqa: S603 - static argv, workspace path is validated.
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    async def _refresh_session_status(self, session: WorkspacePreviewSession) -> None:
        if session.status in {"starting", "running"} and not self._pid_alive(session.pid):
            session.status = "error"
            session.error = "preview process is not running"
            self._touch(session)

    async def _stop_process(self, session: WorkspacePreviewSession) -> None:
        pid = session.pid
        session.pid = None
        if not self._pid_alive(pid):
            return
        assert pid is not None
        try:
            self._kill_preview_process(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            if os.name == "nt":
                raise
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self._pid_alive(pid):
                return
            time.sleep(0.05)
        try:
            self._kill_preview_process(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except ProcessLookupError:
            return
        except PermissionError:
            if os.name == "nt":
                raise
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))

    def _kill_preview_process(self, pid: int, sig: signal.Signals) -> None:
        if os.name == "nt":
            self._kill_windows_process_tree(pid)
            return
        killpg = getattr(os, "killpg", None)
        if killpg is not None:
            killpg(pid, sig)
            return
        os.kill(pid, sig)

    def _kill_windows_process_tree(self, pid: int) -> None:
        taskkill = shutil.which("taskkill")
        if taskkill is None:
            raise FileNotFoundError("taskkill.exe was not found")
        completed = subprocess.run(  # noqa: S603, S607 - taskkill is the Windows process-tree primitive.
            [taskkill, "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode == 0:
            return
        if completed.returncode == 128:
            raise ProcessLookupError(pid)
        if not self._pid_alive(pid):
            raise ProcessLookupError(pid)
        raise PermissionError(f"taskkill failed with exit code {completed.returncode}")

    def _wait_until_healthy(self, port: int, entry_path: str) -> None:
        url = f"http://127.0.0.1:{port}/{self._quote_path(entry_path)}"
        opener = build_opener(ProxyHandler({}))
        timeout_seconds = settings.preview_start_timeout_seconds
        if os.name == "nt":
            timeout_seconds = max(timeout_seconds, 15)
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with opener.open(url, timeout=1) as response:
                    if response.status == 200:
                        return
                    last_error = WorkspacePreviewStartError(
                        f"preview health check returned {response.status}"
                    )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(0.1)
        raise WorkspacePreviewStartError(f"preview health check failed: {last_error}")

    def _port_available(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))  # noqa: S104 - mirrors preview bind address.
            except OSError:
                return False
        return True

    def _public_url(self, port: int, entry_path: str) -> str:
        base = settings.preview_public_base_url.rstrip("/") or f"http://127.0.0.1:{port}"
        parsed = urlparse(base)
        if parsed.scheme and parsed.netloc and parsed.port is None:
            netloc = f"{parsed.hostname}:{port}" if parsed.hostname else parsed.netloc
            if parsed.username or parsed.password:
                auth = parsed.username or ""
                if parsed.password:
                    auth = f"{auth}:{parsed.password}"
                netloc = f"{auth}@{netloc}"
            base = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
        return f"{base.rstrip('/')}/{self._quote_path(entry_path)}"

    def _quote_path(self, path: str) -> str:
        return "/".join(quote(part) for part in path.split("/"))

    def _pid_alive(self, pid: int | None) -> bool:
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _touch(self, session: WorkspacePreviewSession) -> None:
        now = datetime.now(UTC)
        session.updated_at = now
        session.last_accessed_at = now

    def snapshot_path(self, conversation_id: UUID) -> Path:
        """Return the isolated preview snapshot path for a conversation."""
        return Path(settings.preview_snapshot_dir).expanduser() / str(conversation_id)

    def _remove_snapshot(self, session: WorkspacePreviewSession) -> None:
        target = (
            Path(session.snapshot_path)
            if session.snapshot_path
            else self.snapshot_path(session.conversation_id)
        )
        self._snapshot_service.remove(
            target,
            allowed_root=Path(settings.preview_snapshot_dir),
        )
        session.snapshot_path = None
        session.artifact_digest = None

    async def cleanup_stale(self, db: AsyncSession) -> int:
        """Stop legacy or idle preview sessions and remove their snapshots."""
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.preview_idle_ttl_seconds)
        stmt = select(WorkspacePreviewSession).where(
            WorkspacePreviewSession.status.in_(("starting", "running"))
        )
        sessions = list((await db.execute(stmt)).scalars().all())
        cleaned = 0
        for session in sessions:
            if session.snapshot_path is None or session.last_accessed_at < cutoff:
                await self._stop_process(session)
                try:
                    self._remove_snapshot(session)
                    session.error = None
                except (OSError, WorkspaceViolation) as exc:
                    session.snapshot_path = None
                    session.artifact_digest = None
                    session.error = f"preview cleanup failed: {exc}"
                session.status = "stopped"
                self._touch(session)
                cleaned += 1
        if cleaned:
            await db.flush()
        return cleaned
