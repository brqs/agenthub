"""B1/B2 workspace sandbox contract tests for BuiltinAgent tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.builtin.tools.exceptions import ToolExecutionError, WorkspaceViolation
from app.agents.builtin.tools.workspace_tools import read_file, write_file
from app.core.config import settings


async def test_builtin_workspace_tools_read_and_write_inside_workspace(
    tmp_path: Path,
) -> None:
    result = await write_file(tmp_path, "src/App.tsx", "export default 1")
    content = await read_file(tmp_path, "src/App.tsx")

    assert result == "wrote src/App.tsx (16 bytes)"
    assert content == "export default 1"


@pytest.mark.parametrize(
    "rel_path",
    [
        "../escape.txt",
        "/etc/passwd",
        "C:/Users/secret.txt",
        ".agenthub/manifest.json",
        ".env",
        ".git/config",
        ".ssh/id_rsa",
        "secrets/key.txt",
    ],
)
async def test_builtin_workspace_tools_reject_forbidden_write_paths(
    tmp_path: Path,
    rel_path: str,
) -> None:
    with pytest.raises(WorkspaceViolation):
        await write_file(tmp_path, rel_path, "secret")


@pytest.mark.parametrize(
    "rel_path",
    [
        ".agenthub/manifest.json",
        ".env",
        ".git/config",
        ".ssh/id_rsa",
        "secrets/key.txt",
    ],
)
async def test_builtin_workspace_tools_reject_forbidden_read_paths(
    tmp_path: Path,
    rel_path: str,
) -> None:
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("secret", encoding="utf-8")

    with pytest.raises(WorkspaceViolation):
        await read_file(tmp_path, rel_path)


async def test_builtin_workspace_tools_reject_parent_symlink_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link_path = tmp_path / "link"
    try:
        link_path.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(WorkspaceViolation):
        await read_file(tmp_path, "link/secret.txt")
    with pytest.raises(WorkspaceViolation):
        await write_file(tmp_path, "link/new.txt", "nope")


async def test_builtin_workspace_tools_reject_large_read_and_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 128)

    with pytest.raises(ToolExecutionError):
        await write_file(tmp_path, "large.txt", "x" * 129)

    large_path = tmp_path / "large-existing.txt"
    large_path.write_text("x" * 129, encoding="utf-8")
    with pytest.raises(ToolExecutionError):
        await read_file(tmp_path, "large-existing.txt")
