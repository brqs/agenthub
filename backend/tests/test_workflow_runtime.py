"""Workflow runtime / dry-run API tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.services.workspace_workflow_runtime import WorkspaceWorkflowRuntimeService

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(text("DELETE FROM agents WHERE id LIKE 'workflow-runtime-agent-%'"))
        await db.commit()
    await engine.dispose()


@pytest.fixture(autouse=True)
def workspace_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 65536)


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_workflow_dry_run_passes_and_exposes_history_health(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await _write_file(
        client,
        headers,
        conversation_id,
        "flow.yaml",
        """
version: "1"
name: Runtime Flow
nodes:
  - id: start
    type: trigger
  - id: set_context
    type: task
    config:
      action: set_context
      values:
        release:
          status: ready
  - id: check
    type: assert
    config:
      equals:
        release.status: ready
  - id: done
    type: end
edges:
  - source: start
    target: set_context
  - source: set_context
    target: check
  - source: check
    target: done
""",
    )

    created = await client.post(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs",
        headers=headers,
        json={"path": "flow.yaml", "inputs": {"request_id": "r-1"}},
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "passed"
    assert body["validation_status"] == "passed"
    assert body["runtime_status"] == "ready"
    assert body["dry_run_status"] == "passed"
    assert body["health_status"] == "passed"
    assert [item["node_id"] for item in body["node_results"]] == [
        "start",
        "set_context",
        "check",
        "done",
    ]
    assert body["context"]["release"]["status"] == "ready"

    listed = await client.get(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs?path=flow.yaml",
        headers=headers,
    )
    detail = await client.get(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs/{body['id']}",
        headers=headers,
    )
    health = await client.get(
        f"/api/v1/workspaces/{conversation_id}/workflow-health?path=flow.yaml",
        headers=headers,
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["id"] == body["id"]
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == body["id"]
    assert health.status_code == 200, health.text
    assert health.json()["latest_run"]["id"] == body["id"]
    assert health.json()["dry_run_status"] == "passed"


async def test_workflow_dry_run_failure_skips_downstream(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await _write_file(
        client,
        headers,
        conversation_id,
        "fail.yaml",
        """
version: "1"
name: Failing Flow
nodes:
  - id: start
    type: trigger
  - id: set_context
    type: task
    config:
      action: set_context
      values:
        result: nope
  - id: check
    type: assert
    config:
      equals:
        result: ok
  - id: done
    type: end
edges:
  - source: start
    target: set_context
  - source: set_context
    target: check
  - source: check
    target: done
""",
    )

    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs",
        headers=headers,
        json={"path": "fail.yaml"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["runtime_status"] == "invalid"
    assert body["dry_run_status"] == "failed"
    statuses = {item["node_id"]: item["status"] for item in body["node_results"]}
    assert statuses["check"] == "failed"
    assert statuses["done"] == "skipped"


async def test_workflow_runtime_rejects_unsupported_and_cycle(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await _write_file(
        client,
        headers,
        conversation_id,
        "unsupported.yaml",
        """
version: "1"
name: Unsupported Flow
nodes:
  - id: start
    type: trigger
  - id: call_api
    type: task
    config:
      action: http_request
edges:
  - source: start
    target: call_api
""",
    )
    await _write_file(
        client,
        headers,
        conversation_id,
        "cycle.yaml",
        """
version: "1"
name: Cycle Flow
nodes:
  - id: a
    type: trigger
  - id: b
    type: end
edges:
  - source: a
    target: b
  - source: b
    target: a
""",
    )

    unsupported = await client.post(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs",
        headers=headers,
        json={"path": "unsupported.yaml"},
    )
    cycle = await client.post(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs",
        headers=headers,
        json={"path": "cycle.yaml"},
    )

    assert unsupported.status_code == 201, unsupported.text
    assert unsupported.json()["validation_status"] == "passed"
    assert unsupported.json()["runtime_status"] == "invalid"
    assert "unsupported workflow task action" in unsupported.json()["error"]
    assert cycle.status_code == 201, cycle.text
    assert cycle.json()["validation_status"] == "passed"
    assert cycle.json()["runtime_status"] == "invalid"
    assert "cycle" in cycle.json()["error"]


async def test_workflow_action_nodes_are_preview_ready_but_dry_run_not_supported(
    client: AsyncClient,
) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await _write_file(
        client,
        headers,
        conversation_id,
        "p1-workflow.yaml",
        """
version: "1"
name: P1 Workflow E2E
nodes:
  - id: start
    type: trigger
  - id: review
    type: action
  - id: publish
    type: action
edges:
  - source: start
    target: review
  - source: review
    target: publish
""",
    )

    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs",
        headers=headers,
        json={"path": "p1-workflow.yaml"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "passed"
    assert body["validation_status"] == "passed"
    assert body["runtime_status"] == "ready"
    assert body["dry_run_status"] == "not_supported"
    assert body["health_status"] == "passed"
    assert {item["status"] for item in body["node_results"]} == {"skipped"}


async def test_workflow_block_enrichment_uses_latest_run(client: AsyncClient) -> None:
    _, headers = await _register(client)
    conversation = await _create_conversation(client, headers)
    conversation_id = conversation["id"]
    await _write_file(
        client,
        headers,
        conversation_id,
        "flow.yaml",
        """
version: "1"
name: Runtime Flow
nodes:
  - id: start
    type: trigger
edges: []
""",
    )
    response = await client.post(
        f"/api/v1/workspaces/{conversation_id}/workflow-runs",
        headers=headers,
        json={"path": "flow.yaml"},
    )
    assert response.status_code == 201, response.text
    run = response.json()

    async with SessionFactory() as db:
        blocks = await WorkspaceWorkflowRuntimeService().enrich_workflow_blocks(
            db,
            UUID(conversation_id),
            [
                {
                    "type": "workflow",
                    "path": "flow.yaml",
                    "validation_status": "passed",
                    "runtime_status": "ready",
                    "dry_run_status": "not_supported",
                    "health_status": "unknown",
                }
            ],
        )

    assert blocks[0]["last_run_id"] == run["id"]
    assert blocks[0]["dry_run_status"] == "passed"
    assert blocks[0]["health_status"] == "passed"


async def _register(client: AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"wfrt_{uuid4().hex[:16]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"workflow-runtime-agent-{uuid4().hex}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name="Workflow Runtime Agent",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["workflow"],
                system_prompt=None,
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
            "title": "Workflow Runtime",
            "mode": "single",
            "agent_ids": [agent_id],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _write_file(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    path: str,
    content: str,
) -> None:
    response = await client.put(
        f"/api/v1/workspaces/{conversation_id}/files/{path}",
        headers=headers,
        content=content.encode(),
    )
    assert response.status_code == 204, response.text
