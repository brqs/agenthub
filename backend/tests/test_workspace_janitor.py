from __future__ import annotations

import os
import time

from app.services.workspace_janitor import WorkspaceResourceJanitor


def test_janitor_keeps_recent_untracked_directory(tmp_path) -> None:
    janitor = WorkspaceResourceJanitor()
    pending = tmp_path / "pending-preview"
    pending.mkdir()
    (pending / "index.html").write_text("ok", encoding="utf-8")

    janitor._remove_orphan_directories(tmp_path, set())  # noqa: SLF001

    assert pending.exists()


def test_janitor_removes_old_untracked_directory(tmp_path) -> None:
    janitor = WorkspaceResourceJanitor()
    orphan = tmp_path / "old-preview"
    orphan.mkdir()
    (orphan / "index.html").write_text("ok", encoding="utf-8")
    old_time = time.time() - 700
    os.utime(orphan / "index.html", (old_time, old_time))
    os.utime(orphan, (old_time, old_time))

    janitor._remove_orphan_directories(tmp_path, set())  # noqa: SLF001

    assert not orphan.exists()
