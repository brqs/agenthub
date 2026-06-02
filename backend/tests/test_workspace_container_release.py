"""Container release policy safety tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.workspace_container_release import (
    ContainerDeploymentError,
    ContainerDeployWorker,
    ContainerPolicyError,
    ContainerPolicyValidator,
    ContainerReleasePolicy,
)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"privileged": True}, "privileged"),
        ({"host_network": True}, "host network"),
        ({"host_mounts": ("/",)}, "host path mounts"),
        ({"docker_socket": True}, "docker socket"),
        ({"runtime": "docker", "trusted_host_mode": False}, "trusted host mode"),
        ({"runtime": "unknown"}, "docker or podman"),
    ],
)
def test_container_policy_rejects_unsafe_configuration(
    changes: dict[str, object],
    message: str,
) -> None:
    policy = replace(ContainerReleasePolicy(trusted_host_mode=True), **cast(Any, changes))

    with pytest.raises(ContainerPolicyError, match=message):
        ContainerPolicyValidator().validate(policy)


def test_container_policy_accepts_rootless_or_trusted_boundary() -> None:
    validator = ContainerPolicyValidator()

    validator.validate(ContainerReleasePolicy(runtime="podman", trusted_host_mode=False))
    validator.validate(ContainerReleasePolicy(runtime="docker", trusted_host_mode=True))


async def test_container_worker_adds_tmpfs_for_common_read_only_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    async def fake_runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        _ = timeout
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            return 0, "container-123\n", ""
        return 0, "ok\n", ""

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> object:
            _ = url

            class Response:
                status_code = 200

            return Response()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Dockerfile").write_text("FROM nginx:alpine\nEXPOSE 80\n", encoding="utf-8")
    (workspace / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    monkeypatch.setattr(settings, "deployment_container_trusted_host_mode", True)
    worker = ContainerDeployWorker(
        command_runner=fake_runner,
        http_client_factory=cast(Any, FakeClient),
    )

    result = await worker.publish(
        workspace,
        uuid4(),
        container_port=None,
        health_path="/",
    )

    run_command = next(command for command in commands if command[:2] == ["docker", "run"])
    build_command = next(command for command in commands if command[:2] == ["docker", "build"])
    assert result.container_port == 80
    assert "agenthub.managed=true" in build_command
    assert "agenthub.managed=true" in run_command
    assert "--read-only" in run_command
    assert "/tmp:rw,noexec,nosuid,size=64m" in run_command
    assert "/var/cache/nginx:rw,noexec,nosuid,size=64m" in run_command
    assert "/var/run:rw,noexec,nosuid,size=16m" in run_command


async def test_container_worker_cleans_build_context_on_build_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    async def fake_runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        _ = timeout
        commands.append(command)
        if command[:2] == ["docker", "build"]:
            return 1, "", "build failed"
        return 0, "removed\n", ""

    workspace = tmp_path / "workspace"
    build_root = tmp_path / "builds"
    workspace.mkdir()
    (workspace / "Dockerfile").write_text("FROM nginx:alpine\nEXPOSE 80\n", encoding="utf-8")
    deployment_id = uuid4()
    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    monkeypatch.setattr(settings, "deployment_container_trusted_host_mode", True)
    monkeypatch.setattr(settings, "deployment_container_build_root", str(build_root))
    worker = ContainerDeployWorker(command_runner=fake_runner)

    with pytest.raises(ContainerDeploymentError, match="container image build failed"):
        await worker.publish(
            workspace,
            deployment_id,
            container_port=None,
            health_path="/",
        )

    assert not (build_root / str(deployment_id)).exists()
    assert ["docker", "rmi", "-f", f"agenthub-deployment-{deployment_id}"] in commands


async def test_container_worker_cleans_resources_on_run_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    async def fake_runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        _ = timeout
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            return 1, "", "run failed"
        return 0, "ok\n", ""

    workspace = tmp_path / "workspace"
    build_root = tmp_path / "builds"
    workspace.mkdir()
    (workspace / "Dockerfile").write_text("FROM nginx:alpine\nEXPOSE 80\n", encoding="utf-8")
    deployment_id = uuid4()
    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    monkeypatch.setattr(settings, "deployment_container_trusted_host_mode", True)
    monkeypatch.setattr(settings, "deployment_container_build_root", str(build_root))
    worker = ContainerDeployWorker(command_runner=fake_runner)

    with pytest.raises(ContainerDeploymentError, match="container run failed"):
        await worker.publish(
            workspace,
            deployment_id,
            container_port=None,
            health_path="/",
        )

    assert not (build_root / str(deployment_id)).exists()
    assert ["docker", "rmi", "-f", f"agenthub-deployment-{deployment_id}"] in commands


async def test_container_worker_cleans_resources_on_health_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    async def fake_runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        _ = timeout
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            return 0, "container-123\n", ""
        if command[:2] == ["docker", "logs"]:
            return 0, "app failed\n", ""
        return 0, "ok\n", ""

    class FailingClient:
        async def __aenter__(self) -> FailingClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> object:
            _ = url

            class Response:
                status_code = 500

            return Response()

    workspace = tmp_path / "workspace"
    build_root = tmp_path / "builds"
    workspace.mkdir()
    (workspace / "Dockerfile").write_text("FROM nginx:alpine\nEXPOSE 80\n", encoding="utf-8")
    deployment_id = uuid4()
    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    monkeypatch.setattr(settings, "deployment_container_trusted_host_mode", True)
    monkeypatch.setattr(settings, "deployment_container_build_root", str(build_root))
    monkeypatch.setattr(settings, "deployment_container_health_timeout_seconds", 0)
    worker = ContainerDeployWorker(
        command_runner=fake_runner,
        http_client_factory=cast(Any, FailingClient),
    )

    with pytest.raises(ContainerDeploymentError, match="container health check failed"):
        await worker.publish(
            workspace,
            deployment_id,
            container_port=None,
            health_path="/",
        )

    assert not (build_root / str(deployment_id)).exists()
    assert ["docker", "rm", "-f", "container-123"] in commands
    assert ["docker", "rmi", "-f", f"agenthub-deployment-{deployment_id}"] in commands


async def test_container_worker_cleanup_orphans_removes_untracked_labelled_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    async def fake_runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        _ = timeout
        commands.append(command)
        if command[:2] == ["docker", "ps"]:
            return 0, "container-live\ttracked\ncontainer-old\torphan\n", ""
        if command[:2] == ["docker", "images"]:
            return 0, "image-live\ttracked\nimage-old\torphan\n", ""
        return 0, "ok\n", ""

    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    worker = ContainerDeployWorker(command_runner=fake_runner)

    await worker.cleanup_orphans(
        tracked_deployment_ids={"tracked"},
        tracked_container_ids={"container-live"},
        tracked_image_ids={"image-live"},
    )

    assert ["docker", "rm", "-f", "container-old"] in commands
    assert ["docker", "rmi", "-f", "image-old"] in commands
    assert ["docker", "rm", "-f", "container-live"] not in commands
    assert ["docker", "rmi", "-f", "image-live"] not in commands
