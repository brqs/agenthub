"""Workspace Artifact API regression tests."""

from __future__ import annotations

import socket
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.workspace import Workspace
from app.services.workspace_container_release import ContainerDeploymentResult
from app.services.workspace_deployment import WorkspaceDeploymentService
from app.services.workspace_service import WorkspaceService

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'workspace-api-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest.fixture(autouse=True)
def workspace_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 128)
    preview_port = _free_port()
    monkeypatch.setattr(settings, "preview_enabled", True)
    monkeypatch.setattr(settings, "preview_port_start", preview_port)
    monkeypatch.setattr(settings, "preview_port_end", preview_port)
    monkeypatch.setattr(settings, "preview_public_base_url", "http://127.0.0.1")
    monkeypatch.setattr(settings, "preview_start_timeout_seconds", 5)
    monkeypatch.setattr(settings, "preview_snapshot_dir", str(tmp_path / "preview-snapshots"))
    monkeypatch.setattr(settings, "deployment_static_root", str(tmp_path / "static-releases"))
    monkeypatch.setattr(settings, "deployment_export_dir", str(tmp_path / "exports"))
    monkeypatch.setattr(settings, "browser_verify_enabled", True)
    monkeypatch.setattr(settings, "browser_verify_timeout_seconds", 10)
    monkeypatch.setattr(
        settings,
        "browser_verify_screenshot_dir",
        str(tmp_path / "screenshots"),
    )


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"workspace_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"workspace-api-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name="Workspace API Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                config={},
                is_builtin=True,
            )
        )
        await db.commit()
    return agent_id


async def _create_conversation(
    client: AsyncClient,
    headers: dict[str, str],
) -> dict[str, Any]:
    agent_id = await _insert_agent()
    response = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": "Workspace API test",
            "mode": "single",
            "agent_ids": [agent_id],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_workspace_tree_requires_auth(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/workspaces/{uuid4()}/tree")

    assert response.status_code == 401


async def test_workspace_tree_creates_workspace_for_owned_conversation(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/tree",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root"].endswith(conversation["id"])
    assert body["tree"]["type"] == "directory"
    assert any(child["name"] == "README.md" for child in body["tree"]["children"])

    async with SessionFactory() as db:
        workspace = (
            await db.execute(
                select(Workspace).where(
                    Workspace.conversation_id == UUID(conversation["id"])
                )
            )
        ).scalar_one_or_none()
    assert workspace is not None


async def test_workspace_routes_hide_other_users_conversation(
    client: AsyncClient,
) -> None:
    _, owner_headers = await _register(client)
    _, other_headers = await _register(client)
    conversation = await _create_conversation(client, owner_headers)

    responses = [
        await client.get(
            f"/api/v1/workspaces/{conversation['id']}/tree",
            headers=other_headers,
        ),
        await client.get(
            f"/api/v1/workspaces/{conversation['id']}/files/README.md",
            headers=other_headers,
        ),
        await client.put(
            f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
            headers=other_headers,
            content=b"nope",
        ),
        await client.post(
            f"/api/v1/workspaces/{conversation['id']}/preview",
            headers=other_headers,
            json={"entry_path": "index.html"},
        ),
        await client.get(
            f"/api/v1/workspaces/{conversation['id']}/deployments",
            headers=other_headers,
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404]


async def test_write_then_read_workspace_file(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    write_response = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
        headers=headers,
        content=b"export default function App() {}",
    )
    read_response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/src/App.tsx",
        headers=headers,
    )

    assert write_response.status_code == 204, write_response.text
    assert read_response.status_code == 200, read_response.text
    assert read_response.content == b"export default function App() {}"
    assert read_response.headers["content-type"].startswith("text/tsx")
    assert read_response.headers["x-content-type-options"] == "nosniff"


async def test_write_workspace_file_creates_parent_directories(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/nested/a/b/demo.txt",
        headers=headers,
        content=b"hello",
    )

    assert response.status_code == 204, response.text
    assert (
        Path(settings.workspace_base_dir)
        / conversation["id"]
        / "nested"
        / "a"
        / "b"
        / "demo.txt"
    ).exists()


async def test_read_workspace_file_not_found(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/missing.txt",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "workspace_file_not_found"


@pytest.mark.parametrize(
    "rel_path",
    [
        "..%2Fescape.txt",
        ".env",
        ".git/config",
        ".ssh/id_rsa",
        "secrets/key.txt",
    ],
)
async def test_workspace_file_routes_reject_forbidden_paths(
    client: AsyncClient,
    rel_path: str,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/{rel_path}",
        headers=headers,
        content=b"secret",
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "workspace_violation"


async def test_read_workspace_file_rejects_large_file(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, UUID(conversation["id"]))
        WorkspaceService().write_file(workspace, "large.txt", b"x" * 129)
        await db.commit()

    response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/large.txt",
        headers=headers,
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error"]["code"] == "workspace_file_too_large"


async def test_write_workspace_file_rejects_large_body(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/large.txt",
        headers=headers,
        content=b"x" * 129,
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error"]["code"] == "workspace_file_too_large"


async def test_workspace_preview_static_html_lifecycle(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<!doctype html><html><body><h1>Preview OK</h1></body></html>",
    )

    start_response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "index.html", "requested_port": settings.preview_port_start},
    )
    assert start_response.status_code == 201, start_response.text
    started = start_response.json()
    try:
        assert started["status"] == "running"
        assert started["entry_path"] == "index.html"
        assert started["port"] == settings.preview_port_start
        assert started["url"].endswith(f":{started['port']}/index.html")
        local_response = httpx.get(
            f"http://127.0.0.1:{started['port']}/index.html",
            timeout=5,
            trust_env=False,
        )
        assert local_response.status_code == 200
        assert "Preview OK" in local_response.text

        repeat_response = await client.post(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
            json={"entry_path": "index.html"},
        )
        assert repeat_response.status_code == 201, repeat_response.text
        repeated = repeat_response.json()
        assert repeated["id"] == started["id"]
        assert repeated["port"] == started["port"]

        get_response = await client.get(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
        )
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["status"] == "running"
    finally:
        stop_response = await client.delete(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
        )
        assert stop_response.status_code == 200, stop_response.text
        assert stop_response.json()["status"] == "stopped"


async def test_workspace_static_site_deployment_lifecycle(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<!doctype html><html><body><h1>Deploy OK</h1></body></html>",
    )

    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={
            "kind": "static_site",
            "entry_path": "index.html",
            "requested_port": settings.preview_port_start,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    try:
        assert body["kind"] == "static_site"
        assert body["status"] == "published"
        assert body["entry_path"] == "index.html"
        assert "/releases/" in body["url"]
        assert body["artifact_digest"]
        assert body["file_count"] == 1
        public = await client.get(urlparse(body["url"]).path)
        assert public.status_code == 200
        assert "Deploy OK" in public.text

        get_response = await client.get(
            f"/api/v1/workspaces/{conversation_id}/deployments/{body['id']}",
            headers=headers,
        )
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "published"
    finally:
        await client.delete(
            f"/api/v1/workspaces/{conversation_id}/deployments/{body['id']}",
            headers=headers,
        )


async def test_workspace_static_site_deployment_does_not_fallback_port(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<!doctype html><html><body>Port busy</body></html>",
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", settings.preview_port_start))
        sock.listen()
        response = await client.post(
            f"/api/v1/workspaces/{conversation_id}/deployments",
            headers=headers,
            json={
                "kind": "static_site",
                "entry_path": "index.html",
                "requested_port": settings.preview_port_start,
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "published"
    assert "/releases/" in response.json()["url"]
    await client.delete(
        f"/api/v1/workspaces/{conversation_id}/deployments/{response.json()['id']}",
        headers=headers,
    )


async def test_workspace_preview_serves_only_guarded_static_snapshot(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html><head><link rel='stylesheet' href='assets/styles.css'></head></html>",
    )
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/assets/styles.css",
        headers=headers,
        content=b"body{color:#123}",
    )

    started = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "index.html"},
    )
    assert started.status_code == 201, started.text
    port = started.json()["port"]
    try:
        index = httpx.get(f"http://127.0.0.1:{port}/", timeout=5, trust_env=False)
        css = httpx.get(
            f"http://127.0.0.1:{port}/assets/styles.css",
            timeout=5,
            trust_env=False,
        )
        metadata = httpx.get(
            f"http://127.0.0.1:{port}/.agenthub/manifest.json",
            timeout=5,
            trust_env=False,
        )
        directory = httpx.get(f"http://127.0.0.1:{port}/assets/", timeout=5, trust_env=False)
        assert index.status_code == 200
        assert index.headers["x-content-type-options"] == "nosniff"
        assert "content-security-policy" in index.headers
        assert css.status_code == 200
        assert metadata.status_code == 404
        assert directory.status_code == 404
    finally:
        await client.delete(f"/api/v1/workspaces/{conversation_id}/preview", headers=headers)


async def test_workspace_preview_rebuilds_snapshot_after_workspace_change(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html><body>preview-v1</body></html>",
    )
    started = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "index.html"},
    )
    assert started.status_code == 201, started.text
    url = started.json()["url"]
    try:
        assert "preview-v1" in httpx.get(url, timeout=5, trust_env=False).text
        await client.put(
            f"/api/v1/workspaces/{conversation_id}/files/index.html",
            headers=headers,
            content=b"<html><body>preview-v2</body></html>",
        )
        restarted = await client.post(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
            json={"entry_path": "index.html"},
        )
        assert restarted.status_code == 201, restarted.text
        updated = httpx.get(restarted.json()["url"], timeout=5, trust_env=False)
        assert updated.status_code == 200
        assert "preview-v2" in updated.text
        assert "preview-v1" not in updated.text
    finally:
        await client.delete(f"/api/v1/workspaces/{conversation_id}/preview", headers=headers)


async def test_workspace_static_release_is_immutable_and_stop_invalidates_url(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html><body>release-v1</body></html>",
    )
    deployment = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "static_site", "entry_path": "index.html"},
    )
    assert deployment.status_code == 201, deployment.text
    body = deployment.json()
    release_path = urlparse(body["url"]).path
    assert "release-v1" in (await client.get(release_path)).text

    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html><body>release-v2</body></html>",
    )
    unchanged = await client.get(release_path)
    assert unchanged.status_code == 200
    assert "release-v1" in unchanged.text
    assert "release-v2" not in unchanged.text

    stopped = await client.delete(
        f"/api/v1/workspaces/{conversation_id}/deployments/{body['id']}",
        headers=headers,
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["url"] is None
    assert (await client.get(release_path)).status_code == 404


async def test_delete_conversation_cleans_workspace_preview_and_deployment_resources(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html><body>cleanup</body></html>",
    )
    preview = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "index.html"},
    )
    assert preview.status_code == 201, preview.text
    static_release = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "static_site", "entry_path": "index.html"},
    )
    source_zip = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "source_zip"},
    )
    assert static_release.status_code == 201, static_release.text
    assert source_zip.status_code == 201, source_zip.text
    release_path = urlparse(static_release.json()["url"]).path
    release_dir = Path(settings.deployment_static_root) / static_release.json()["id"]
    preview_dir = Path(settings.preview_snapshot_dir) / conversation_id
    export_dir = Path(settings.deployment_export_dir) / conversation_id
    workspace_dir = Path(settings.workspace_base_dir) / conversation_id
    assert release_dir.is_dir()
    assert preview_dir.is_dir()
    assert export_dir.is_dir()
    assert workspace_dir.is_dir()

    deleted = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)

    assert deleted.status_code == 204, deleted.text
    assert not release_dir.exists()
    assert not preview_dir.exists()
    assert not export_dir.exists()
    assert not workspace_dir.exists()
    assert (await client.get(release_path)).status_code == 404


async def test_workspace_source_zip_deployment_excludes_sensitive_paths(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html>source</html>",
    )
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, UUID(conversation_id))
        root = Path(workspace.root_path)
        (root / ".env").write_text("SECRET=1", encoding="utf-8")
        (root / ".env.local").write_text("LOCAL_SECRET=1", encoding="utf-8")
        (root / "node_modules").mkdir(exist_ok=True)
        (root / "node_modules" / "skip.js").write_text("skip", encoding="utf-8")
        await db.commit()

    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "source_zip"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "source_zip"
    assert body["status"] == "published"
    assert body["download_url"]
    assert body["artifact_digest"]
    assert body["file_count"] >= 1
    assert body["expires_at"]

    download = await client.get(body["download_url"], headers=headers)
    assert download.status_code == 200, download.text
    zip_path = Path(settings.deployment_export_dir) / conversation_id / f"{body['id']}.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "index.html" in names
    assert ".env" not in names
    assert ".env.local" not in names
    assert "node_modules/skip.js" not in names


async def test_workspace_source_zip_expired_download_is_removed(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deployment_export_ttl_seconds", -1)
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<html>expired</html>",
    )
    deployment = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "source_zip"},
    )
    assert deployment.status_code == 201, deployment.text
    body = deployment.json()
    export_path = Path(settings.deployment_export_dir) / conversation_id / f"{body['id']}.zip"
    assert export_path.is_file()

    download = await client.get(body["download_url"], headers=headers)

    assert download.status_code == 404
    assert not export_path.exists()


async def test_workspace_source_zip_rejects_single_file_over_limit(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deployment_max_single_file_bytes", 64)
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/large.txt",
        headers=headers,
        content=b"x" * 65,
    )

    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "source_zip"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "workspace_deployment_failed"


async def test_workspace_container_deployment_returns_not_supported(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deployment_container_enabled", False)
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.post(
        f"/api/v1/workspaces/{conversation['id']}/deployments",
        headers=headers,
        json={"kind": "container"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "container"
    assert body["status"] == "not_supported"
    assert "disabled" in body["error"].lower()


async def test_workspace_container_deployment_fails_without_dockerfile(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)

    response = await client.post(
        f"/api/v1/workspaces/{conversation['id']}/deployments",
        headers=headers,
        json={"kind": "container", "container_port": 8000, "health_path": "/health"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "container"
    assert body["status"] == "failed"
    assert "Dockerfile" in body["error"]


async def test_workspace_container_deployment_uses_worker_and_stops(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.api.v1 import workspaces as workspace_api

    class FakeContainerWorker:
        def __init__(self) -> None:
            self.removed: list[tuple[str | None, str | None]] = []

        async def publish(
            self,
            workspace_root: Path,
            deployment_id: UUID,
            *,
            container_port: int | None,
            health_path: str,
        ) -> ContainerDeploymentResult:
            assert (workspace_root / "Dockerfile").is_file()
            assert container_port == 8000
            assert health_path == "/health"
            return ContainerDeploymentResult(
                url="http://127.0.0.1:8200",
                healthcheck_url="http://127.0.0.1:8200/health",
                runtime_id="container-123",
                image_id="image-123",
                container_id="container-123",
                host_port=8200,
                container_port=8000,
                runtime_kind="docker",
                runtime_status="running",
                logs_tail="healthy",
                snapshot_path=tmp_path / "container-snapshot",
            )

        async def remove(
            self,
            *,
            container_id: str | None,
            image_id: str | None,
            snapshot_path: Path | str | None,
        ) -> None:
            _ = snapshot_path
            self.removed.append((container_id, image_id))

    fake_worker = FakeContainerWorker()
    monkeypatch.setattr(settings, "deployment_container_runtime", "docker")
    monkeypatch.setattr(
        workspace_api,
        "deployment_service",
        WorkspaceDeploymentService(container_worker=fake_worker),  # type: ignore[arg-type]
    )
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/Dockerfile",
        headers=headers,
        content=b"FROM python:3.12-slim\nEXPOSE 8000\n",
    )

    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "container", "container_port": 8000, "health_path": "/health"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "published"
    assert body["url"] == "http://127.0.0.1:8200"
    assert body["healthcheck_url"] == "http://127.0.0.1:8200/health"
    assert body["host_port"] == 8200
    assert body["container_port"] == 8000
    assert body["runtime_status"] == "running"

    stopped = await client.delete(
        f"/api/v1/workspaces/{conversation_id}/deployments/{body['id']}",
        headers=headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "stopped"
    assert fake_worker.removed == [("container-123", "image-123")]


async def test_workspace_deployment_rejects_invalid_entries(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/app.js",
        headers=headers,
        content=b"console.log('nope')",
    )

    missing = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "static_site", "entry_path": "missing.html"},
    )
    non_html = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "static_site", "entry_path": "app.js"},
    )
    traversal = await client.post(
        f"/api/v1/workspaces/{conversation_id}/deployments",
        headers=headers,
        json={"kind": "static_site", "entry_path": "../index.html"},
    )

    assert missing.status_code == 404
    assert non_html.status_code == 403
    assert traversal.status_code == 403


async def test_workspace_preview_rejects_missing_and_forbidden_entries(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]

    missing_response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "missing.html"},
    )
    forbidden_response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "../escape.html"},
    )
    non_html_response = await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/app.txt",
        headers=headers,
        content=b"not html",
    )
    assert non_html_response.status_code == 204
    invalid_type_response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "app.txt"},
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["detail"]["error"]["code"] == "workspace_file_not_found"
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["detail"]["error"]["code"] == "workspace_violation"
    assert invalid_type_response.status_code == 403
    assert invalid_type_response.json()["detail"]["error"]["code"] == "workspace_violation"


async def test_html_workspace_file_adds_preview_security_headers(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/index.html",
        headers=headers,
        content=b"<h1>Hello</h1>",
    )

    response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/files/index.html",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_workspace_preview_requested_port_unavailable_fails(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"<!doctype html><html><body><h1>Port Busy</h1></body></html>",
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("0.0.0.0", settings.preview_port_start))
        sock.listen(1)
        response = await client.post(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
            json={
                "entry_path": "index.html",
                "requested_port": settings.preview_port_start,
            },
        )

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["error"]["code"] == "workspace_preview_start_failed"


async def test_workspace_preview_verify_browser_checks(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 4096)
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/index.html",
        headers=headers,
        content=b"""<!doctype html>
<html>
<head><title>Verify OK</title><link rel="stylesheet" href="styles.css"></head>
<body>
  <main>
    <h1>Preview OK</h1>
    <button id="toggle">Toggle</button>
    <p id="status">Ready</p>
  </main>
  <script src="app.js"></script>
</body>
</html>
""",
    )
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/styles.css",
        headers=headers,
        content=b"body{font-family:sans-serif;margin:0}main{padding:24px}button{padding:8px}",
    )
    await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/app.js",
        headers=headers,
        content=(
            b"document.querySelector('#toggle').onclick=()=>{"
            b"document.querySelector('#status').textContent='Clicked'};"
        ),
    )
    start_response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/preview",
        headers=headers,
        json={"entry_path": "index.html"},
    )
    assert start_response.status_code == 201, start_response.text
    try:
        verify_response = await client.post(
            f"/api/v1/workspaces/{conversation_id}/preview/verify",
            headers=headers,
            json={"required_text": ["Preview OK"], "max_clicks": 1},
        )
        assert verify_response.status_code == 200, verify_response.text
        body = verify_response.json()
        assert body["passed"] is True
        assert body["checks"]["no_console_errors"] is True
        assert body["checks"]["no_page_errors"] is True
        assert body["screenshots"]["desktop"].endswith("desktop.png")
        assert Path(body["screenshots"]["desktop"]).exists()
        assert Path(body["screenshots"]["mobile"]).exists()
    finally:
        await client.delete(
            f"/api/v1/workspaces/{conversation_id}/preview",
            headers=headers,
        )


async def test_workspace_tree_max_depth_limits_children(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    await client.put(
        f"/api/v1/workspaces/{conversation['id']}/files/nested/a/b/demo.txt",
        headers=headers,
        content=b"hello",
    )

    response = await client.get(
        f"/api/v1/workspaces/{conversation['id']}/tree?max_depth=1",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    nested = next(
        child for child in response.json()["tree"]["children"] if child["name"] == "nested"
    )
    assert nested["type"] == "directory"
    assert nested["children"] == []


async def test_openapi_includes_workspace_routes(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/workspaces/{conversation_id}/tree" in paths
    assert "/api/v1/workspaces/{conversation_id}/files/{path}" in paths
    assert "/api/v1/workspaces/{conversation_id}/preview/verify" in paths
    assert "/releases/{release_token}" in paths
    assert "/releases/{release_token}/{path}" in paths
