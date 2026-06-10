"""Artifact recognition and safe file access for evaluation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.agents.orchestrator._internal.evaluation.types import EvaluationIssue, EvaluationResult
from app.agents.orchestrator.types import SubTask, TaskAttempt

DEFAULT_EVALUATION_READ_MAX_BYTES = 262_144
MAX_EVALUATION_READ_LIMIT = 1_048_576
SENSITIVE_PATH_PARTS = {".agenthub", ".env", ".ssh", "secrets"}
WORKFLOW_INTENT_RE = re.compile(r"(?i)(workflow|工作流|流程编排|dag)")
PPT_INTENT_RE = re.compile(r"(?i)(ppt|slides?|deck|presentation|幻灯片|演示文稿)")
DOCUMENT_INTENT_RE = re.compile(r"(?i)(report|document|brief|readme|文档|报告|说明)")


def artifact_exists_result(attempt: TaskAttempt) -> EvaluationResult:
    if attempt.missing_artifact_paths:
        return EvaluationResult(
            evaluator="artifact_exists",
            status="failed",
            passed=False,
            severity="major",
            issues=[
                EvaluationIssue(
                    code="missing_artifact",
                    message=f"Missing artifact: {path}",
                    evidence=path,
                    repair_hint=f"Create or update {path}.",
                )
                for path in attempt.missing_artifact_paths
            ],
            checked_artifacts=attempt.artifact_paths,
        )
    return EvaluationResult(
        evaluator="artifact_exists",
        status="passed",
        passed=True,
        checked_artifacts=attempt.artifact_paths,
    )

def looks_like_workflow_artifact(task: SubTask, path: str) -> bool:
    lowered = path.lower()
    if not lowered.endswith((".json", ".yaml", ".yml")):
        return False
    if any(token in lowered for token in ("workflow", "dag", "flow")):
        return True
    return bool(WORKFLOW_INTENT_RE.search(f"{task.title}\n{task.instruction}"))

def looks_like_ppt_artifact(task: SubTask, path: str) -> bool:
    lowered = path.lower()
    if not lowered.endswith((".json", ".md", ".txt", ".ppt", ".pptx")):
        return False
    if any(
        token in lowered for token in ("ppt", "slides", "slide", "deck", "presentation")
    ):
        return True
    return bool(PPT_INTENT_RE.search(f"{task.title}\n{task.instruction}"))

def looks_like_document_artifact(task: SubTask, path: str) -> bool:
    lowered = path.lower()
    if any(token in lowered for token in ("report", "document", "readme", "brief")):
        return True
    return bool(DOCUMENT_INTENT_RE.search(f"{task.title}\n{task.instruction}"))

def read_max_bytes(config: Mapping[str, Any]) -> int:
    value = config.get(
        "orchestrator_evaluation_read_max_bytes",
        DEFAULT_EVALUATION_READ_MAX_BYTES,
    )
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_EVALUATION_READ_MAX_BYTES
    return max(1, min(value, MAX_EVALUATION_READ_LIMIT))

def artifact_suffix(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(lowered).suffix

def safe_artifact_file(workspace_path: Path, artifact_path: str) -> Path | None:
    if not artifact_path or artifact_path.startswith("/"):
        return None
    parts = tuple(part for part in artifact_path.replace("\\", "/").split("/") if part)
    if not parts or ".." in parts or any(part in SENSITIVE_PATH_PARTS for part in parts):
        return None
    root = workspace_path.resolve()
    target = (root / Path(*parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None

def read_text_limited(path: Path, max_bytes: int) -> str | None:
    if path.stat().st_size > max_bytes:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
