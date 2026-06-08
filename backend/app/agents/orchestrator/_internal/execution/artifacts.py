"""Artifact file block and manifest side effects for task attempts."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

from app.agents.orchestrator._internal.memory import (
    record_event as _memory_record_event,
)
from app.agents.orchestrator._internal.presentation_markers import (
    artifact_evidence_presentation,
)
from app.agents.orchestrator.evaluation import (
    evaluation_results_payload as _evaluation_results_payload,
)
from app.agents.orchestrator.types import (
    OrchestratorRunContext,
    SubTask,
    TaskAttempt,
)
from app.agents.types import StreamChunk
from app.services.artifacts.manifest import (
    ArtifactManifestService,
    evaluation_results_for_artifact,
    evaluation_status_for_artifact,
)
from app.services.artifacts.metadata import build_artifact_metadata

logger = logging.getLogger(__name__)
artifact_manifest_service = ArtifactManifestService()


async def artifact_file_blocks(
    config: Mapping[str, Any],
    workspace_path: Path | None,
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    next_block_index: int,
    agent_id: str,
) -> tuple[list[StreamChunk], int]:
    if workspace_path is None or not attempt.artifact_paths:
        return [], next_block_index
    conversation_id = config.get("conversation_id")
    blocks: list[StreamChunk] = []
    for artifact_path in attempt.artifact_paths:
        target = safe_workspace_file(workspace_path, artifact_path)
        if target is None:
            continue
        metadata = build_artifact_metadata(target, artifact_path)
        if metadata.artifact_kind not in {"document", "ppt", "image", "archive", "workflow"}:
            continue
        evaluation_payloads = _evaluation_results_payload(attempt.evaluation_results)
        artifact_evaluation_results = evaluation_results_for_artifact(
            metadata.path,
            evaluation_payloads,
        )
        evaluation_status = evaluation_status_for_artifact(
            metadata.path,
            evaluation_payloads,
        )
        payload: dict[str, Any] = {
            "path": metadata.path,
            "filename": metadata.filename,
            "url": workspace_file_url(conversation_id, metadata.path),
            "size": metadata.size,
            "mime_type": metadata.mime_type,
            "artifact_kind": metadata.artifact_kind,
            "metadata": metadata.metadata,
            "presentation": artifact_evidence_presentation(),
        }
        if metadata.preview_text is not None:
            payload["preview_text"] = metadata.preview_text
            payload["preview_truncated"] = metadata.preview_truncated
        await upsert_artifact_manifest_entry(
            config,
            workspace_path,
            task,
            attempt,
            run_context,
            agent_id,
            payload,
            evaluation_status=evaluation_status,
            evaluation_results=artifact_evaluation_results,
        )
        if metadata.artifact_kind == "workflow":
            workflow_chunks = workflow_artifact_chunks(
                target,
                metadata.path,
                next_block_index,
                agent_id,
            )
            if workflow_chunks:
                blocks.extend(workflow_chunks)
                next_block_index += 1
            continue
        blocks.extend(
            [
                StreamChunk(
                    event_type="block_start",
                    block_index=next_block_index,
                    block_type="file",
                    metadata=payload,
                    agent_id=agent_id,
                ),
                StreamChunk(
                    event_type="block_end",
                    block_index=next_block_index,
                    agent_id=agent_id,
                ),
            ]
        )
        next_block_index += 1
    return blocks, next_block_index


def workflow_artifact_chunks(
    target: Path,
    artifact_path: str,
    block_index: int,
    agent_id: str,
) -> list[StreamChunk]:
    try:
        raw_definition = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    workflow_format = "json" if target.suffix.lower() == ".json" else "yaml"
    return [
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="workflow",
            metadata={
                "path": artifact_path,
                "format": workflow_format,
                "validation_status": "unknown",
                "runtime_status": "not_supported",
                "dry_run_status": "not_supported",
                "presentation": artifact_evidence_presentation(),
            },
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="delta",
            block_index=block_index,
            text_delta=raw_definition,
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="block_end",
            block_index=block_index,
            agent_id=agent_id,
        ),
    ]


async def upsert_artifact_manifest_entry(
    config: Mapping[str, Any],
    workspace_path: Path,
    task: SubTask,
    attempt: TaskAttempt,
    run_context: OrchestratorRunContext,
    agent_id: str,
    payload: dict[str, Any],
    *,
    evaluation_status: str,
    evaluation_results: list[dict[str, Any]],
) -> None:
    service_raw = config.get("orchestrator_artifact_manifest_service")
    service = (
        service_raw
        if isinstance(service_raw, ArtifactManifestService)
        else artifact_manifest_service
    )
    entry = {
        **payload,
        "agent_id": agent_id,
        "task_id": task.task_id,
        "run_id": str(run_context.memory_run_id) if run_context.memory_run_id else None,
        "preview_text": payload.get("preview_text"),
        "preview_truncated": payload.get("preview_truncated"),
        "evaluation_status": evaluation_status,
        "evaluation_results": evaluation_results,
    }
    try:
        lock = config.get("orchestrator_artifact_manifest_lock")
        if lock is None:
            service.upsert_entry(workspace_path, entry)
        else:
            async with cast(Any, lock):
                service.upsert_entry(workspace_path, entry)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "artifact_manifest_update_failed path=%s task_id=%s agent_id=%s",
            payload.get("path"),
            task.task_id,
            agent_id,
            exc_info=True,
        )
        await _memory_record_event(
            config,
            run_context,
            event_type="artifact_manifest_update_failed",
            task_id=task.task_id,
            agent_id=agent_id,
            payload={
                "attempt_index": attempt.attempt_index,
                "path": str(payload.get("path") or ""),
                "error": str(exc),
            },
        )


def safe_workspace_file(workspace_path: Path, artifact_path: str) -> Path | None:
    parts = tuple(part for part in artifact_path.replace("\\", "/").split("/") if part)
    if not parts or ".." in parts:
        return None
    root = workspace_path.resolve()
    target = (root / Path(*parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None


def workspace_file_url(conversation_id: Any, path: str) -> str:
    if not isinstance(conversation_id, UUID):
        return ""
    return f"/api/v1/workspaces/{conversation_id}/files/{quote(path, safe='/')}"
