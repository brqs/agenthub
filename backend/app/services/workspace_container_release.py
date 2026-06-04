"""Platform-managed container deployment worker."""

from __future__ import annotations

import asyncio
import re
import shutil
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.services.workspace_service import WorkspaceFileTooLarge, WorkspaceViolation

CONTAINER_EXCLUDED_PARTS = {
    ".agenthub",
    ".env",
    ".git",
    ".ssh",
    ".venv",
    "__pycache__",
    "node_modules",
    "secrets",
}
EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
MANAGED_LABEL = "agenthub.managed=true"
DEPLOYMENT_LABEL = "agenthub.deployment_id"
CommandRunner = Callable[[list[str], int], Awaitable[tuple[int, str, str]]]
StateEventSink = Callable[[str, dict[str, Any]], Awaitable[None]]
CancellationChecker = Callable[[], Awaitable[bool]]


class ContainerPolicyError(RuntimeError):
    """Raised when a requested container release violates platform policy."""


class ContainerDeploymentError(RuntimeError):
    """Raised when the container worker cannot publish a deployment."""


class ContainerDeploymentCancelledError(ContainerDeploymentError):
    """Raised when a queued/publishing container deployment is stopped."""


@dataclass(frozen=True)
class ContainerReleasePolicy:
    """Restricted container release policy."""

    runtime: str = "docker"
    trusted_host_mode: bool = False
    cpu_limit: float = 1
    memory_mb: int = 512
    runtime_seconds: int = 3600
    privileged: bool = False
    host_network: bool = False
    host_mounts: tuple[str, ...] = ()
    docker_socket: bool = False


@dataclass(frozen=True)
class ContainerDeploymentResult:
    """Result returned after a container is built, run, and checked."""

    url: str
    healthcheck_url: str
    runtime_id: str
    image_id: str
    container_id: str
    host_port: int
    container_port: int
    runtime_kind: str
    runtime_status: str
    logs_tail: str
    snapshot_path: Path


class ContainerPolicyValidator:
    """Reject unsafe container execution requests before worker dispatch."""

    def validate(self, policy: ContainerReleasePolicy) -> None:
        if policy.runtime not in {"docker", "podman"}:
            raise ContainerPolicyError("container runtime must be docker or podman")
        if policy.runtime == "docker" and not policy.trusted_host_mode:
            raise ContainerPolicyError("docker runtime requires trusted host mode")
        if policy.privileged:
            raise ContainerPolicyError("privileged containers are not allowed")
        if policy.host_network:
            raise ContainerPolicyError("host network is not allowed")
        if policy.host_mounts:
            raise ContainerPolicyError("host path mounts are not allowed")
        if policy.docker_socket:
            raise ContainerPolicyError("docker socket access is not allowed")
        if policy.cpu_limit <= 0 or policy.cpu_limit > settings.deployment_container_max_cpu:
            raise ContainerPolicyError("container CPU limit exceeds platform policy")
        if policy.memory_mb <= 0 or policy.memory_mb > settings.deployment_container_max_memory_mb:
            raise ContainerPolicyError("container memory limit exceeds platform policy")
        if (
            policy.runtime_seconds <= 0
            or policy.runtime_seconds > settings.deployment_container_max_runtime_seconds
        ):
            raise ContainerPolicyError("container runtime limit exceeds platform policy")


def current_container_policy() -> ContainerReleasePolicy:
    """Build the effective container policy from current settings."""
    return ContainerReleasePolicy(
        runtime=settings.deployment_container_runtime,
        trusted_host_mode=settings.deployment_container_trusted_host_mode,
        cpu_limit=settings.deployment_container_max_cpu,
        memory_mb=settings.deployment_container_max_memory_mb,
        runtime_seconds=settings.deployment_container_max_runtime_seconds,
    )


class ContainerDeployWorker:
    """Build and run one workspace Dockerfile with platform-controlled flags."""

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._command_runner = command_runner or _run_command
        self._http_client_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=5, trust_env=False)
        )
        self._policy_validator = ContainerPolicyValidator()

    async def publish(
        self,
        workspace_root: Path,
        deployment_id: UUID,
        *,
        container_port: int | None,
        health_path: str,
        event_sink: StateEventSink | None = None,
        cancellation_checker: CancellationChecker | None = None,
    ) -> ContainerDeploymentResult:
        policy = current_container_policy()
        self._policy_validator.validate(policy)
        root = workspace_root.expanduser().resolve()
        dockerfile = root / "Dockerfile"
        if not dockerfile.is_file() or dockerfile.is_symlink():
            raise ContainerDeploymentError("Dockerfile is required for container deployment")
        await _raise_if_cancelled(cancellation_checker)
        resolved_port = container_port or _infer_exposed_port(
            dockerfile.read_text(encoding="utf-8")
        )
        if resolved_port is None:
            raise ContainerDeploymentError(
                "container_port is required unless Dockerfile has exactly one EXPOSE port"
            )
        if resolved_port <= 0 or resolved_port > 65535:
            raise ContainerDeploymentError("container_port must be between 1 and 65535")
        normalized_health_path = _normalize_health_path(health_path)
        build_context = self._build_context(root, deployment_id)
        await _emit_event(
            event_sink,
            "snapshot_created",
            {"step": "snapshot", "message": "Container build context created."},
        )
        image_tag = f"agenthub-deployment-{deployment_id}"
        host_port = _allocate_host_port()
        await _emit_event(
            event_sink,
            "port_allocated",
            {"step": "port", "host_port": host_port, "container_port": resolved_port},
        )
        runtime = settings.deployment_container_runtime
        logs: list[str] = [f"Building image {image_tag} from workspace snapshot."]
        await _raise_if_cancelled(cancellation_checker)
        await _emit_event(
            event_sink,
            "build_started",
            {"step": "build", "runtime": runtime, "image_id": image_tag},
        )
        build_rc, build_out, build_err = await self._command_runner(
            [
                runtime,
                "build",
                "--label",
                MANAGED_LABEL,
                "--label",
                f"{DEPLOYMENT_LABEL}={deployment_id}",
                "-t",
                image_tag,
                str(build_context),
            ],
            settings.deployment_container_health_timeout_seconds,
        )
        logs.append(_trim_logs(build_out, build_err))
        if build_rc != 0:
            await self.remove(container_id=None, image_id=image_tag, snapshot_path=build_context)
            await _emit_event(
                event_sink,
                "build_failed",
                {"step": "build", "exit_code": build_rc},
            )
            raise ContainerDeploymentError(_trim_message("container image build failed", logs))
        await _emit_event(
            event_sink,
            "build_completed",
            {"step": "build", "exit_code": build_rc},
        )
        try:
            await _raise_if_cancelled(cancellation_checker)
        except ContainerDeploymentCancelledError:
            await self.remove(container_id=None, image_id=image_tag, snapshot_path=build_context)
            raise
        run_command = [
            runtime,
            "run",
            "--detach",
            "--label",
            MANAGED_LABEL,
            "--label",
            f"{DEPLOYMENT_LABEL}={deployment_id}",
            "--cpus",
            str(settings.deployment_container_max_cpu),
            "--memory",
            f"{settings.deployment_container_max_memory_mb}m",
            "--pids-limit",
            "256",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108 - container tmpfs mount.
            "--tmpfs",
            "/var/cache/nginx:rw,noexec,nosuid,size=64m",
            "--tmpfs",
            "/var/run:rw,noexec,nosuid,size=16m",
            "--security-opt",
            "no-new-privileges",
            "--network",
            "bridge",
            "-p",
            f"{host_port}:{resolved_port}",
            image_tag,
        ]
        await _emit_event(
            event_sink,
            "run_started",
            {"step": "run", "host_port": host_port, "container_port": resolved_port},
        )
        run_rc, run_out, run_err = await self._command_runner(
            run_command,
            settings.deployment_container_health_timeout_seconds,
        )
        logs.append(_trim_logs(run_out, run_err))
        if run_rc != 0:
            await self.remove(container_id=None, image_id=image_tag, snapshot_path=build_context)
            await _emit_event(event_sink, "run_failed", {"step": "run", "exit_code": run_rc})
            raise ContainerDeploymentError(_trim_message("container run failed", logs))
        container_id = run_out.strip().splitlines()[-1] if run_out.strip() else image_tag
        await _emit_event(
            event_sink,
            "run_completed",
            {"step": "run", "container_id": container_id, "exit_code": run_rc},
        )
        base_url = settings.deployment_container_public_base_url.rstrip("/")
        url = f"{base_url}:{host_port}"
        healthcheck_url = f"{url}{normalized_health_path}"
        local_healthcheck_url = f"http://127.0.0.1:{host_port}{normalized_health_path}"
        try:
            await _raise_if_cancelled(cancellation_checker)
            await self._check_health(local_healthcheck_url, event_sink=event_sink)
        except ContainerDeploymentError as exc:
            logs_rc, logs_out, logs_err = await self._command_runner(
                [runtime, "logs", "--tail", "80", container_id],
                settings.deployment_container_health_timeout_seconds,
            )
            logs.append(_trim_logs(logs_out, logs_err) if logs_rc == 0 else "Unable to read logs.")
            await self.remove(
                container_id=container_id,
                image_id=image_tag,
                snapshot_path=build_context,
            )
            await _emit_event(
                event_sink,
                "health_failed",
                {"step": "health", "healthcheck_url": healthcheck_url},
            )
            raise ContainerDeploymentError(
                _trim_message("container health check failed", logs)
            ) from exc
        await _emit_event(
            event_sink,
            "health_passed",
            {"step": "health", "healthcheck_url": healthcheck_url},
        )
        return ContainerDeploymentResult(
            url=url,
            healthcheck_url=healthcheck_url,
            runtime_id=container_id,
            image_id=image_tag,
            container_id=container_id,
            host_port=host_port,
            container_port=resolved_port,
            runtime_kind=runtime,
            runtime_status="running",
            logs_tail=_trim_text("\n".join(logs), settings.deployment_container_log_tail_bytes),
            snapshot_path=build_context,
        )

    async def remove(
        self,
        *,
        container_id: str | None,
        image_id: str | None,
        snapshot_path: Path | str | None,
    ) -> None:
        runtime = settings.deployment_container_runtime
        if container_id:
            await self._command_runner(
                [runtime, "rm", "-f", container_id],
                settings.deployment_container_health_timeout_seconds,
            )
        if image_id:
            await self._command_runner(
                [runtime, "rmi", "-f", image_id],
                settings.deployment_container_health_timeout_seconds,
            )
        if snapshot_path:
            self._remove_snapshot(Path(snapshot_path))

    async def cleanup_orphans(
        self,
        *,
        tracked_deployment_ids: set[str],
        tracked_container_ids: set[str],
        tracked_image_ids: set[str],
    ) -> None:
        """Best-effort cleanup for managed runtime resources no longer tracked by DB."""
        runtime = settings.deployment_container_runtime
        timeout = settings.deployment_container_health_timeout_seconds
        try:
            container_rc, container_out, _ = await self._command_runner(
                [
                    runtime,
                    "ps",
                    "-a",
                    "--filter",
                    f"label={MANAGED_LABEL}",
                    "--format",
                    f'{{{{.ID}}}}\t{{{{.Label "{DEPLOYMENT_LABEL}"}}}}',
                ],
                timeout,
            )
            if container_rc == 0:
                for resource_id, deployment_id in _managed_resource_rows(container_out):
                    if (
                        deployment_id not in tracked_deployment_ids
                        and resource_id not in tracked_container_ids
                    ):
                        await self._command_runner(
                            [runtime, "rm", "-f", resource_id],
                            timeout,
                        )
            image_rc, image_out, _ = await self._command_runner(
                [
                    runtime,
                    "images",
                    "--filter",
                    f"label={MANAGED_LABEL}",
                    "--format",
                    f'{{{{.ID}}}}\t{{{{.Label "{DEPLOYMENT_LABEL}"}}}}',
                ],
                timeout,
            )
            if image_rc == 0:
                for resource_id, deployment_id in _managed_resource_rows(image_out):
                    if (
                        deployment_id not in tracked_deployment_ids
                        and resource_id not in tracked_image_ids
                    ):
                        await self._command_runner(
                            [runtime, "rmi", "-f", resource_id],
                            timeout,
                        )
        except Exception:
            return

    def _build_context(self, workspace_root: Path, deployment_id: UUID) -> Path:
        target = Path(settings.deployment_container_build_root).expanduser() / str(deployment_id)
        staging = target.parent / f".{target.name}.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        total_bytes = 0
        file_count = 0
        try:
            for path in sorted(workspace_root.rglob("*")):
                relative = path.relative_to(workspace_root)
                if _is_excluded(relative):
                    continue
                if path.is_symlink():
                    raise WorkspaceViolation(
                        f"container snapshot cannot include symlink: {relative.as_posix()}"
                    )
                if not path.is_file():
                    continue
                stat = path.stat()
                if stat.st_size > settings.deployment_max_single_file_bytes:
                    raise WorkspaceFileTooLarge(
                        f"container snapshot file is too large: {relative.as_posix()}"
                    )
                file_count += 1
                if file_count > settings.deployment_max_file_count:
                    raise WorkspaceFileTooLarge("container snapshot contains too many files")
                total_bytes += stat.st_size
                if total_bytes > settings.deployment_max_export_bytes:
                    raise WorkspaceFileTooLarge("container snapshot is too large")
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(path.read_bytes())
            if not (staging / "Dockerfile").is_file():
                raise ContainerDeploymentError("Dockerfile is required for container deployment")
            shutil.rmtree(target, ignore_errors=True)
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return target

    def _remove_snapshot(self, snapshot_path: Path) -> None:
        root = Path(settings.deployment_container_build_root).expanduser().resolve()
        resolved = snapshot_path.expanduser().resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise WorkspaceViolation(
                f"container snapshot path escapes managed root: {snapshot_path}"
            ) from exc
        if resolved != root:
            shutil.rmtree(resolved, ignore_errors=True)

    async def _check_health(
        self,
        url: str,
        *,
        event_sink: StateEventSink | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.deployment_container_health_timeout_seconds
        attempts = max(settings.deployment_container_health_max_attempts, 1)
        interval = max(settings.deployment_container_health_retry_interval_seconds, 0)
        multiplier = max(settings.deployment_container_health_backoff_multiplier, 1)
        started = loop.time()
        async with self._http_client_factory() as client:
            for attempt in range(1, attempts + 1):
                elapsed = loop.time() - started
                try:
                    response = await client.get(url)
                    await _emit_event(
                        event_sink,
                        "health_attempt",
                        {
                            "step": "health",
                            "attempt": attempt,
                            "http_status": response.status_code,
                            "elapsed_seconds": round(elapsed, 3),
                        },
                    )
                    if 200 <= response.status_code < 400:
                        return
                except httpx.HTTPError as exc:
                    await _emit_event(
                        event_sink,
                        "health_attempt",
                        {
                            "step": "health",
                            "attempt": attempt,
                            "error_category": exc.__class__.__name__,
                            "elapsed_seconds": round(elapsed, 3),
                        },
                    )
                if loop.time() >= deadline or attempt >= attempts:
                    raise ContainerDeploymentError(f"container health check timed out: {url}")
                sleep_for = min(interval, max(deadline - loop.time(), 0))
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                interval *= multiplier
        raise ContainerDeploymentError(f"container health check timed out: {url}")


async def _run_command(command: list[str], timeout_seconds: int) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return 124, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    return process.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def _allocate_host_port() -> int:
    for port in range(
        settings.deployment_container_port_start,
        settings.deployment_container_port_end + 1,
    ):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))  # noqa: S104 - checks public host port.
            except OSError:
                continue
            return port
    raise ContainerDeploymentError("container deployment port pool is exhausted")


async def _emit_event(
    event_sink: StateEventSink | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    if event_sink is not None:
        await event_sink(event_type, payload)


async def _raise_if_cancelled(
    cancellation_checker: CancellationChecker | None,
) -> None:
    if cancellation_checker is not None and await cancellation_checker():
        raise ContainerDeploymentCancelledError("container deployment stop requested")


def _infer_exposed_port(dockerfile_text: str) -> int | None:
    ports: set[int] = set()
    for match in EXPOSE_RE.finditer(dockerfile_text):
        for token in match.group(1).split():
            raw_port = token.split("/", 1)[0]
            if raw_port.isdigit():
                ports.add(int(raw_port))
    return next(iter(ports)) if len(ports) == 1 else None


def _normalize_health_path(health_path: str | None) -> str:
    raw = (health_path or "/").strip()
    if not raw:
        return "/"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    if "\\" in raw or ".." in Path(raw).parts:
        raise ContainerDeploymentError("health_path must be an absolute URL path")
    return raw


def _is_excluded(relative: Path) -> bool:
    return any(
        part in CONTAINER_EXCLUDED_PARTS or part.startswith(".env.")
        for part in relative.parts
    )


def _trim_logs(stdout: str, stderr: str) -> str:
    text = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part)
    return _trim_text(text, settings.deployment_container_log_tail_bytes)


def _trim_message(prefix: str, logs: list[str]) -> str:
    return _trim_text(f"{prefix}: {' | '.join(log for log in logs if log)}", 1000)


def _trim_text(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    return encoded[-max_bytes:].decode("utf-8", errors="replace")


def _managed_resource_rows(output: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        resource_id, separator, deployment_id = line.strip().partition("\t")
        if resource_id and separator and deployment_id:
            rows.append((resource_id, deployment_id))
    return rows
