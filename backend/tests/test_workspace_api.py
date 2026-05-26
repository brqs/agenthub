"""Workspace Artifact API regression tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.workspace import Workspace
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


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


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
    ]

    assert [response.status_code for response in responses] == [404, 404, 404]


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
