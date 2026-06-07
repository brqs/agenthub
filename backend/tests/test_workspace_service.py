"""WorkspaceService sandbox tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.models.conversation import Conversation
from app.models.user import User
from app.models.workspace import Workspace
from app.services.workspace_service import (
    WorkspaceFileTooLarge,
    WorkspaceService,
    WorkspaceViolation,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
def workspace_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 128)


async def _create_conversation() -> UUID:
    async with SessionFactory() as db:
        user = User(username=f"workspace_{uuid4().hex[:16]}", password_hash="hash")
        db.add(user)
        await db.flush()
        conversation = Conversation(
            user_id=user.id,
            title="Workspace test",
            mode="single",
            agent_ids=["test-agent"],
        )
        db.add(conversation)
        await db.commit()
        return conversation.id


async def test_get_or_create_workspace_creates_db_row_and_directory() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        await db.commit()

    root = Path(workspace.root_path)
    assert root.exists()
    assert (root / "README.md").exists()
    assert (root / ".agenthub" / "manifest.json").exists()

    async with SessionFactory() as db:
        stored = (
            await db.execute(
                select(Workspace).where(Workspace.conversation_id == conversation_id)
            )
        ).scalar_one()
    assert stored.root_path == str(root)


async def test_get_or_create_workspace_is_idempotent() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        first = await WorkspaceService().get_or_create(db, conversation_id)
        first_id = first.id
        second = await WorkspaceService().get_or_create(db, conversation_id)
        await db.commit()
        count = (
            await db.execute(
                select(func.count(Workspace.id)).where(
                    Workspace.conversation_id == conversation_id
                )
            )
        ).scalar_one()

    assert second.id == first_id
    assert count == 1


async def test_get_or_create_repairs_workspace_root_from_old_base(tmp_path: Path) -> None:
    conversation_id = await _create_conversation()
    stale_root = tmp_path / "pytest-of-root" / "old-workspaces" / str(conversation_id)
    expected_root = Path(settings.workspace_base_dir) / str(conversation_id)
    async with SessionFactory() as db:
        db.add(Workspace(conversation_id=conversation_id, root_path=str(stale_root)))
        await db.commit()

    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        await db.commit()

    assert Path(workspace.root_path) == expected_root
    assert expected_root.exists()
    assert (expected_root / "README.md").exists()
    async with SessionFactory() as db:
        stored = (
            await db.execute(
                select(Workspace).where(Workspace.conversation_id == conversation_id)
            )
        ).scalar_one()
    assert stored.root_path == str(expected_root)


async def test_get_or_create_workspace_is_concurrency_safe() -> None:
    conversation_id = await _create_conversation()

    async def create_once() -> UUID:
        async with SessionFactory() as db:
            workspace = await WorkspaceService().get_or_create(db, conversation_id)
            await db.commit()
            return workspace.id

    ids = await asyncio.gather(*(create_once() for _ in range(8)))

    async with SessionFactory() as db:
        count = (
            await db.execute(
                select(func.count(Workspace.id)).where(
                    Workspace.conversation_id == conversation_id
                )
            )
        ).scalar_one()

    assert len(set(ids)) == 1
    assert count == 1


async def test_write_and_read_file_inside_workspace() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        service = WorkspaceService()
        service.write_file(workspace, "src/App.tsx", b"export default function App() {}")
        content, mime_type = service.read_file(workspace, "src/App.tsx")

    assert content == b"export default function App() {}"
    assert mime_type == "text/tsx"


async def test_write_file_creates_parent_directories() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        WorkspaceService().write_file(workspace, "nested/a/b/demo.txt", b"hello")

    assert (Path(workspace.root_path) / "nested" / "a" / "b" / "demo.txt").exists()


async def test_list_tree_skips_file_that_disappears_during_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = await _create_conversation()
    service = WorkspaceService()
    async with SessionFactory() as db:
        workspace = await service.get_or_create(db, conversation_id)
        service.write_file(workspace, "stable.txt", b"stable")
        service.write_file(workspace, "transient.txt", b"transient")

    original_is_file = Path.is_file

    def flaky_is_file(path: Path) -> bool:
        if path.name == "transient.txt":
            raise FileNotFoundError("transient disappeared")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", flaky_is_file)

    tree = service.list_tree(workspace)
    names = {child["name"] for child in tree["children"]}

    assert "stable.txt" in names
    assert "transient.txt" not in names


async def test_list_tree_tolerates_directory_changing_during_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = await _create_conversation()
    service = WorkspaceService()
    async with SessionFactory() as db:
        workspace = await service.get_or_create(db, conversation_id)
        service.write_file(workspace, "stable.txt", b"stable")
    (Path(workspace.root_path) / "changing").mkdir()

    original_iterdir = Path.iterdir

    def flaky_iterdir(path: Path):
        if path.name == "changing":
            raise NotADirectoryError("changed while scanning")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", flaky_iterdir)

    tree = service.list_tree(workspace)
    names = {child["name"] for child in tree["children"]}

    assert "stable.txt" in names
    assert "changing" in names


async def test_rejects_path_traversal() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        with pytest.raises(WorkspaceViolation):
            WorkspaceService().write_file(workspace, "../escape.txt", b"escape")


async def test_rejects_absolute_path() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        with pytest.raises(WorkspaceViolation):
            WorkspaceService().write_file(workspace, "/etc/passwd", b"escape")


async def test_rejects_agenthub_metadata_access() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        service = WorkspaceService()
        with pytest.raises(WorkspaceViolation):
            service.write_file(workspace, ".agenthub/manifest.json", b"{}")
        with pytest.raises(WorkspaceViolation):
            service.read_file(workspace, ".agenthub/manifest.json")


@pytest.mark.parametrize(
    "rel_path",
    [".env", ".git/config", ".ssh/id_rsa", "secrets/key.txt"],
)
async def test_rejects_sensitive_paths(rel_path: str) -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        with pytest.raises(WorkspaceViolation):
            WorkspaceService().write_file(workspace, rel_path, b"secret")


async def test_rejects_symlink_escape(tmp_path: Path) -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link_path = Path(workspace.root_path) / "link"
    link_path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceViolation):
        WorkspaceService().read_file(workspace, "link/secret.txt")
    with pytest.raises(WorkspaceViolation):
        WorkspaceService().write_file(workspace, "link/new.txt", b"nope")


async def test_read_file_rejects_large_file() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        WorkspaceService().write_file(workspace, "large.txt", b"x" * 129)
        with pytest.raises(WorkspaceFileTooLarge):
            WorkspaceService().read_file(workspace, "large.txt")


async def test_delete_workspace_removes_db_row_and_directory() -> None:
    conversation_id = await _create_conversation()
    async with SessionFactory() as db:
        workspace = await WorkspaceService().get_or_create(db, conversation_id)
        root = Path(workspace.root_path)
        await WorkspaceService().delete(db, conversation_id)
        await db.commit()

    assert not root.exists()
    async with SessionFactory() as db:
        stored = (
            await db.execute(
                select(Workspace).where(Workspace.conversation_id == conversation_id)
            )
        ).scalar_one_or_none()
    assert stored is None
