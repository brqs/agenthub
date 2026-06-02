"""Tests for Orchestrator platform-owned tools."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base, SessionFactory, engine
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.user import User
from app.services.orchestrator_platform_tools import OrchestratorPlatformToolExecutor
from app.services.workspace_service import WorkspaceService

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


async def _conversation() -> Conversation:
    async with SessionFactory() as db:
        user = User(
            username=f"platform_tool_{uuid4().hex[:16]}",
            password_hash="hash",
        )
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="Platform tools",
            mode="group",
            agent_ids=["orchestrator"],
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation


async def test_create_custom_agent_tool_creates_agent_and_adds_to_group() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {
                "name": "Copy Agent",
                "provider": "builtin",
                "system_prompt": "You write concise product copy.",
                "capabilities": ["writing", "copy"],
                "config": {"model_backend": "claude", "mcp_servers": []},
                "add_to_conversation": True,
            },
        )
        await db.commit()

        assert result.status == "ok"
        payload = json.loads(result.output)
        agent_id = payload["agent"]["id"]
        agent = await db.get(Agent, agent_id)
        updated_conversation = await db.get(Conversation, conversation.id)

        assert agent is not None
        assert agent.user_id == conversation.user_id
        assert agent.provider == "builtin"
        assert agent.system_prompt == "You write concise product copy."
        assert updated_conversation is not None
        assert agent_id in updated_conversation.agent_ids


async def test_create_custom_agent_tool_requires_key_fields() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {"name": "Incomplete Agent", "provider": "builtin"},
        )

        assert result.status == "error"
        assert result.error_code == "missing_required_agent_fields"
        assert result.needs_user_input is True
        assert json.loads(result.output)["missing_fields"] == ["system_prompt"]


async def test_create_custom_agent_tool_rejects_invalid_provider() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {
                "name": "Legacy Agent",
                "provider": "custom",
                "system_prompt": "nope",
            },
        )

        assert result.status == "error"
        assert result.error_code == "invalid_provider"


async def test_create_custom_agent_tool_rejects_invalid_config() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_custom_agent",
            {
                "name": "Bad Agent",
                "provider": "builtin",
                "system_prompt": "bad config",
                "config": {"model_backend": "local"},
            },
        )

        assert result.status == "error"
        assert result.error_code == "INVALID_MODEL_BACKEND"


async def test_create_custom_agent_tool_does_not_create_on_error() -> None:
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        await executor(
            "create_custom_agent",
            {"name": "No Prompt", "provider": "builtin"},
        )
        count = (
            await db.execute(
                select(Agent).where(
                    Agent.user_id == conversation.user_id,
                    Agent.name == "No Prompt",
                )
            )
        ).scalars().all()

        assert count == []


async def test_create_deployment_tool_publishes_static_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    conversation = await _conversation()
    preview_port = _free_port()
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "preview_port_start", preview_port)
    monkeypatch.setattr(settings, "preview_port_end", preview_port)
    monkeypatch.setattr(settings, "preview_public_base_url", "http://127.0.0.1")
    monkeypatch.setattr(settings, "deployment_static_root", str(tmp_path / "static-releases"))
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation.id)
        WorkspaceService().write_file(
            workspace,
            "index.html",
            b"<!doctype html><html><body>Tool deploy</body></html>",
        )
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor(
            "create_deployment",
            {
                "kind": "static_site",
                "entry_path": "index.html",
                "requested_port": preview_port,
            },
        )

        assert result.status == "ok", result.output
        payload = json.loads(result.output)
        assert payload["kind"] == "static_site"
        assert payload["status"] == "published"
        assert payload["status_card"]["type"] == "deployment_status"
        assert "/releases/" in payload["url"]
        assert payload["url"].endswith("/index.html")
        assert "Ignored requested_port" in payload["logs_preview"]


async def test_package_workspace_source_tool_excludes_sensitive_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    conversation = await _conversation()
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "deployment_export_dir", str(tmp_path / "exports"))
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation.id)
        root = Path(workspace.root_path)
        WorkspaceService().write_file(workspace, "index.html", b"<html></html>")
        (root / ".env").write_text("SECRET=1", encoding="utf-8")
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor("package_workspace_source", {"format": "zip"})

        assert result.status == "ok", result.output
        payload = json.loads(result.output)
        assert payload["kind"] == "source_zip"
        assert payload["download_url"].endswith("/download")
        export_path = Path(settings.deployment_export_dir) / str(conversation.id) / (
            payload["deployment_id"] + ".zip"
        )
        with zipfile.ZipFile(export_path) as archive:
            names = set(archive.namelist())
        assert "index.html" in names
        assert ".env" not in names


async def test_create_deployment_tool_returns_container_not_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "deployment_container_enabled", False)
    conversation = await _conversation()
    async with SessionFactory() as db:
        executor = OrchestratorPlatformToolExecutor(
            db=db,
            conversation_id=conversation.id,
        )

        result = await executor("create_deployment", {"kind": "container"})

        assert result.status == "ok"
        payload = json.loads(result.output)
        assert payload["kind"] == "container"
        assert payload["status"] == "not_supported"
        assert payload["status_card"]["status"] == "not_supported"


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
