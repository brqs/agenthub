"""Artifact path tracking for Orchestrator task attempts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.agents.orchestrator.types import SubTask, TaskAttempt, TaskState

SENSITIVE_ARTIFACT_PARTS = {".env", "secrets", ".ssh", ".agenthub"}
ARTIFACT_PATH_KEYS = {
    "path",
    "file_path",
    "filepath",
    "filename",
    "file",
    "target_path",
    "output_path",
}
ARTIFACT_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.\-/\\])"
    r"([A-Za-z0-9_.\-/\\]+"
    r"\.(?:html|css|js|jsx|ts|tsx|py|md|json|txt|yml|yaml|toml|xml|svg|png|jpg|jpeg|gif|webp))"
)


def finalize_artifact_candidates(attempt: TaskAttempt, task: SubTask) -> None:
    candidates: list[str] = []
    if task.expected_output:
        candidates.extend(extract_artifact_paths_from_text(task.expected_output))
    candidates.extend(attempt.artifact_paths)
    if not candidates:
        candidates.extend(extract_artifact_paths_from_text(task.instruction))
    attempt.artifact_paths = _dedupe_strings(candidates)


def check_attempt_artifacts(
    attempt: TaskAttempt,
    workspace_path: Path | None,
) -> None:
    if workspace_path is None or not attempt.artifact_paths:
        attempt.state = TaskState.SUCCEEDED
        return
    resolved_paths: list[str] = []
    missing: list[str] = []
    for path in attempt.artifact_paths:
        resolved = _resolve_artifact_path(workspace_path, path)
        if resolved is None:
            missing.append(path)
            continue
        resolved_paths.append(resolved)
    attempt.artifact_paths = _dedupe_strings(resolved_paths)
    attempt.missing_artifact_paths = missing
    if missing:
        attempt.state = TaskState.ARTIFACT_MISSING
        attempt.error = f"missing artifact: {', '.join(missing)}"
        return
    attempt.state = TaskState.SUCCEEDED


def extract_artifact_paths_from_mapping(value: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    for key, item in value.items():
        normalized_key = str(key).lower()
        if normalized_key in ARTIFACT_PATH_KEYS and isinstance(item, str):
            candidate = _normalize_artifact_path(item)
            if candidate is not None:
                paths.append(candidate)
        elif isinstance(item, Mapping):
            paths.extend(extract_artifact_paths_from_mapping(item))
        elif isinstance(item, list):
            for child in item:
                if isinstance(child, Mapping):
                    paths.extend(extract_artifact_paths_from_mapping(child))
                elif isinstance(child, str):
                    paths.extend(extract_artifact_paths_from_text(child))
    return _dedupe_strings(paths)


def extract_artifact_paths_from_text(text: str) -> list[str]:
    return _dedupe_strings(
        path
        for match in ARTIFACT_PATH_PATTERN.finditer(text)
        if (path := _normalize_artifact_path(match.group(1))) is not None
    )


def _resolve_artifact_path(workspace_path: Path, artifact_path: str) -> str | None:
    exact = workspace_path / artifact_path
    if exact.is_file():
        return artifact_path
    if "/" in artifact_path:
        return None

    matches: list[str] = []
    workspace_root = workspace_path.resolve()
    for candidate in workspace_path.rglob(artifact_path):
        if not candidate.is_file():
            continue
        try:
            relative = candidate.resolve().relative_to(workspace_root)
        except ValueError:
            continue
        if any(part in SENSITIVE_ARTIFACT_PARTS for part in relative.parts):
            continue
        matches.append(relative.as_posix())
    if len(matches) == 1:
        return matches[0]
    return None


def _normalize_artifact_path(raw_path: str) -> str | None:
    cleaned = raw_path.strip().strip("`'\"").rstrip(".,;:)]}")
    if not cleaned:
        return None
    cleaned = cleaned.replace("\\", "/")
    candidate = Path(cleaned)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    parts = [part for part in cleaned.split("/") if part]
    if not parts or any(part in SENSITIVE_ARTIFACT_PARTS for part in parts):
        return None
    if any(part.startswith(".") and part not in {".well-known"} for part in parts):
        return None
    return "/".join(parts)


def _dedupe_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
