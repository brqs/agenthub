"""Platform-managed workspace artifact manifest service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

logger = logging.getLogger(__name__)

MANIFEST_VERSION = 1
MANIFEST_DIR = ".agenthub"
MANIFEST_FILENAME = "artifacts.json"
SENSITIVE_ARTIFACT_PARTS = {".agenthub", ".env", ".git", ".ssh", "secrets"}

ArtifactEvaluationStatus = Literal[
    "passed",
    "failed",
    "manual_review_required",
    "unknown",
]


class ArtifactManifestError(RuntimeError):
    """Raised when an artifact manifest operation violates platform policy."""


class ArtifactManifestService:
    """Read and update the internal `.agenthub/artifacts.json` manifest."""

    def list_entries(self, workspace_root: Path) -> list[dict[str, Any]]:
        manifest = self._read_manifest(workspace_root)
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]

    def upsert_entry(
        self,
        workspace_root: Path,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        path = self._validate_artifact_path(str(entry.get("path") or ""))
        now = datetime.now(UTC).isoformat()
        manifest = self._read_manifest(workspace_root)
        entries = [
            item for item in manifest.get("entries", []) if isinstance(item, dict)
        ]
        existing = next(
            (item for item in entries if item.get("path") == path),
            None,
        )
        created_at = str((existing or {}).get("created_at") or now)
        normalized = self._normalize_entry(
            {
                **(existing or {}),
                **entry,
                "path": path,
                "created_at": created_at,
                "updated_at": now,
            }
        )
        if existing is None:
            entries.append(normalized)
        else:
            entries[entries.index(existing)] = normalized
        self._write_manifest(workspace_root, {"version": MANIFEST_VERSION, "entries": entries})
        return normalized

    def update_evaluation(
        self,
        workspace_root: Path,
        *,
        path: str,
        evaluation_status: ArtifactEvaluationStatus,
        evaluation_results: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        manifest = self._read_manifest(workspace_root)
        entries = [
            item for item in manifest.get("entries", []) if isinstance(item, dict)
        ]
        for index, entry in enumerate(entries):
            if entry.get("path") != path:
                continue
            updated = self._normalize_entry(
                {
                    **entry,
                    "evaluation_status": evaluation_status,
                    "evaluation_results": evaluation_results,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            entries[index] = updated
            self._write_manifest(
                workspace_root,
                {"version": MANIFEST_VERSION, "entries": entries},
            )
            return updated
        return None

    def _read_manifest(self, workspace_root: Path) -> dict[str, Any]:
        path = self._manifest_path(workspace_root)
        if not path.exists():
            manifest = {"version": MANIFEST_VERSION, "entries": []}
            self._write_manifest(workspace_root, manifest)
            return manifest
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("artifact_manifest_recovered_bad_json", exc_info=exc)
            manifest = {"version": MANIFEST_VERSION, "entries": []}
            self._write_manifest(workspace_root, manifest)
            return manifest
        if not isinstance(raw, dict) or raw.get("version") != MANIFEST_VERSION:
            manifest = {"version": MANIFEST_VERSION, "entries": []}
            self._write_manifest(workspace_root, manifest)
            return manifest
        entries = raw.get("entries")
        if not isinstance(entries, list):
            raw["entries"] = []
        return raw

    def _write_manifest(self, workspace_root: Path, manifest: dict[str, Any]) -> None:
        path = self._manifest_path(workspace_root)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(path)

    def _manifest_path(self, workspace_root: Path) -> Path:
        root = workspace_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        metadata_dir = root / MANIFEST_DIR
        if metadata_dir.exists() and metadata_dir.is_symlink():
            raise ArtifactManifestError("artifact manifest metadata dir is a symlink")
        metadata_dir.mkdir(exist_ok=True)
        path = (metadata_dir / MANIFEST_FILENAME).resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ArtifactManifestError("artifact manifest escapes workspace") from exc
        return path

    def _validate_artifact_path(self, raw_path: str) -> str:
        if not raw_path or not raw_path.strip():
            raise ArtifactManifestError("artifact path is empty")
        normalized = raw_path.replace("\\", "/").strip()
        raw = Path(normalized)
        if raw.is_absolute() or PureWindowsPath(raw_path).is_absolute():
            raise ArtifactManifestError(
                f"absolute artifact path is not allowed: {raw_path}"
            )
        if PureWindowsPath(raw_path).drive:
            raise ArtifactManifestError(f"drive artifact path is not allowed: {raw_path}")
        parts = [part for part in normalized.split("/") if part and part != "."]
        if not parts or ".." in parts:
            raise ArtifactManifestError(
                f"artifact path traversal is not allowed: {raw_path}"
            )
        if any(part in SENSITIVE_ARTIFACT_PARTS for part in parts):
            raise ArtifactManifestError(
                f"sensitive artifact path is not allowed: {raw_path}"
            )
        if any(part.startswith(".") and part not in {".well-known"} for part in parts):
            raise ArtifactManifestError(f"hidden artifact path is not allowed: {raw_path}")
        return "/".join(parts)

    def _normalize_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        metadata = entry.get("metadata")
        evaluation_results = entry.get("evaluation_results")
        return {
            "path": str(entry.get("path") or ""),
            "artifact_kind": str(entry.get("artifact_kind") or "other"),
            "filename": str(entry.get("filename") or Path(str(entry.get("path") or "")).name),
            "size": int(entry.get("size") or 0),
            "mime_type": str(entry.get("mime_type") or "application/octet-stream"),
            "url": str(entry.get("url") or ""),
            "agent_id": _optional_str(entry.get("agent_id")),
            "task_id": _optional_str(entry.get("task_id")),
            "run_id": _optional_str(entry.get("run_id")),
            "preview_text": _optional_str(entry.get("preview_text")),
            "preview_truncated": _optional_bool(entry.get("preview_truncated")),
            "metadata": metadata if isinstance(metadata, dict) else {},
            "evaluation_status": _evaluation_status(entry.get("evaluation_status")),
            "evaluation_results": (
                [item for item in evaluation_results if isinstance(item, dict)]
                if isinstance(evaluation_results, list)
                else []
            ),
            "created_at": str(entry.get("created_at") or datetime.now(UTC).isoformat()),
            "updated_at": str(entry.get("updated_at") or datetime.now(UTC).isoformat()),
        }


def evaluation_status_for_artifact(
    artifact_path: str,
    results: list[dict[str, Any]],
) -> ArtifactEvaluationStatus:
    related: list[dict[str, Any]] = []
    for result in results:
        checked = result.get("checked_artifacts")
        if isinstance(checked, list) and artifact_path in checked:
            related.append(result)
    if not related:
        return "unknown"
    if any(result.get("status") == "failed" or result.get("passed") is False for result in related):
        return "failed"
    if any(result.get("evaluator") == "manual_review_required" for result in related):
        return "manual_review_required"
    if any(result.get("status") == "passed" and result.get("passed") is True for result in related):
        return "passed"
    return "unknown"


def evaluation_results_for_artifact(
    artifact_path: str,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        result
        for result in results
        if isinstance(result.get("checked_artifacts"), list)
        and artifact_path in result["checked_artifacts"]
    ]


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _evaluation_status(value: Any) -> ArtifactEvaluationStatus:
    if value == "passed":
        return "passed"
    if value == "failed":
        return "failed"
    if value == "manual_review_required":
        return "manual_review_required"
    return "unknown"
