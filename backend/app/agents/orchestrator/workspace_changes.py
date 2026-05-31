"""Workspace snapshot and conflict helpers for Orchestrator runs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.agents.orchestrator.types import OrchestratorRunContext

IGNORED_DIRS = {".agenthub", ".git", ".venv", "__pycache__", "node_modules"}
IGNORED_FILE_PREFIXES = (".agenthub_",)

WorkspaceSnapshot = dict[str, dict[str, Any]]


def snapshot_workspace(workspace_path: Path | None) -> WorkspaceSnapshot:
    """Return a small content-aware snapshot of workspace files."""

    if workspace_path is None:
        return {}
    root = workspace_path.resolve()
    if not root.exists() or not root.is_dir():
        return {}

    snapshot: WorkspaceSnapshot = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if _ignored(relative):
            continue
        try:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        snapshot[relative.as_posix()] = {
            "path": relative.as_posix(),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
        }
    return snapshot


def diff_workspace_snapshots(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
) -> dict[str, list[str]]:
    created = sorted(path for path in after if path not in before)
    deleted = sorted(path for path in before if path not in after)
    modified = sorted(
        path
        for path in after.keys() & before.keys()
        if after[path].get("sha256") != before[path].get("sha256")
    )
    return {"created": created, "modified": modified, "deleted": deleted}


def changed_paths(file_changes: dict[str, list[str]]) -> set[str]:
    return {
        path
        for key in ("created", "modified", "deleted")
        for path in file_changes.get(key, [])
    }


def refresh_workspace_conflicts(
    run_context: OrchestratorRunContext,
) -> list[dict[str, Any]]:
    """Recompute conflicts across all recorded task results."""

    for result in run_context.results.values():
        result.workspace_conflicts.clear()
        for attempt in result.attempts:
            attempt.conflict_paths.clear()

    writers_by_path: dict[str, list[dict[str, str]]] = {}
    for task_id in run_context.result_order:
        recorded_result = run_context.results.get(task_id)
        if recorded_result is None:
            continue
        for attempt in recorded_result.attempts:
            for path in sorted(changed_paths(attempt.file_changes)):
                writers_by_path.setdefault(path, []).append(
                    {
                        "task_id": task_id,
                        "title": recorded_result.title,
                        "agent_id": attempt.agent_id,
                    }
                )

    conflicts: list[dict[str, Any]] = []
    for path, writers in sorted(writers_by_path.items()):
        task_ids = {writer["task_id"] for writer in writers}
        if len(task_ids) < 2:
            continue
        conflict = {"path": path, "writers": writers}
        conflicts.append(conflict)
        for writer in writers:
            recorded_result = run_context.results.get(writer["task_id"])
            if recorded_result is None:
                continue
            recorded_result.workspace_conflicts.append(conflict)
            for attempt in recorded_result.attempts:
                if path in changed_paths(attempt.file_changes):
                    attempt.conflict_paths.append(path)

    for result in run_context.results.values():
        result.workspace_conflicts = _dedupe_conflicts(result.workspace_conflicts)
        for attempt in result.attempts:
            attempt.conflict_paths = sorted(set(attempt.conflict_paths))
    return conflicts


def _ignored(relative: Path) -> bool:
    if any(part in IGNORED_DIRS for part in relative.parts):
        return True
    return relative.name.startswith(IGNORED_FILE_PREFIXES)


def _dedupe_conflicts(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for conflict in conflicts:
        path = str(conflict.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        output.append(conflict)
    return output
