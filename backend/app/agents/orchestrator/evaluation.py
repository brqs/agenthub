"""Deterministic Evaluation / Reflection helpers for Orchestrator attempts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agents.orchestrator._internal.evaluation.artifacts import (
    artifact_exists_result as _artifact_exists_result,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    artifact_suffix as _artifact_suffix,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_archive_artifact as _evaluate_archive_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_document as _evaluate_document,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_image_artifact as _evaluate_image_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_ppt_artifact as _evaluate_ppt_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_pptx_artifact as _evaluate_pptx_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_static_code as _evaluate_static_code,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    evaluate_workflow_artifact as _evaluate_workflow_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    looks_like_document_artifact as _looks_like_document_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    looks_like_ppt_artifact as _looks_like_ppt_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    looks_like_workflow_artifact as _looks_like_workflow_artifact,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    manual_review_result as _manual_review_result,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    read_max_bytes as _read_max_bytes,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    read_text_limited as _read_text_limited,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    requirements_coverage_result as _requirements_coverage_result,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    safe_artifact_file as _safe_artifact_file,
)
from app.agents.orchestrator._internal.evaluation.artifacts import (
    test_report_quality_result as _test_report_quality_result,
)
from app.agents.orchestrator._internal.evaluation.types import (
    EvaluationIssue as EvaluationIssue,
)
from app.agents.orchestrator._internal.evaluation.types import (
    EvaluationOutcome,
    EvaluationResult,
    ReflectionResult,
)
from app.agents.orchestrator.types import SubTask, TaskAttempt
from app.services.artifacts.metadata import (
    classify_artifact,
)

DOCUMENT_SUFFIXES = {".md", ".txt"}
STATIC_CODE_SUFFIXES = {".py", ".json", ".toml"}
STRUCTURED_SUFFIXES = {".json", ".yaml", ".yml"}
MANUAL_REVIEW_SUFFIXES = {".pdf", ".docx", ".ppt"}

__all__ = [
    "EvaluationIssue",
    "EvaluationOutcome",
    "EvaluationResult",
    "ReflectionResult",
    "evaluate_attempt",
    "evaluation_results_payload",
    "failed_evaluation_lines",
    "reflection_payload",
]


async def evaluate_attempt(
    config: Mapping[str, Any],
    task: SubTask,
    attempt: TaskAttempt,
    workspace_path: Path | None,
) -> EvaluationOutcome:
    """Run the MVP non-browser evaluators for a successful artifact attempt."""

    if config.get("orchestrator_evaluation_enabled", True) is False:
        return EvaluationOutcome(results=[])

    results: list[EvaluationResult] = [_artifact_exists_result(attempt)]
    if workspace_path is None or not attempt.artifact_paths:
        return EvaluationOutcome(results=results)

    read_max_bytes = _read_max_bytes(config)
    artifact_texts: dict[str, str] = {}
    artifact_files: dict[str, Path] = {}
    for artifact_path in attempt.artifact_paths:
        target = _safe_artifact_file(workspace_path, artifact_path)
        if target is None:
            continue
        artifact_files[artifact_path] = target
        suffix = _artifact_suffix(artifact_path)
        if suffix not in DOCUMENT_SUFFIXES | STATIC_CODE_SUFFIXES | STRUCTURED_SUFFIXES:
            continue
        text = _read_text_limited(target, read_max_bytes)
        if text is None:
            continue
        artifact_texts[artifact_path] = text
        if suffix in DOCUMENT_SUFFIXES:
            results.append(
                _evaluate_document(
                    artifact_path,
                    text,
                    strict=_looks_like_document_artifact(task, artifact_path),
                )
            )
        elif suffix in STATIC_CODE_SUFFIXES:
            results.append(_evaluate_static_code(artifact_path, suffix, text))
        if _looks_like_workflow_artifact(task, artifact_path):
            results.append(_evaluate_workflow_artifact(artifact_path, suffix, text))
        if _looks_like_ppt_artifact(task, artifact_path):
            results.append(_evaluate_ppt_artifact(artifact_path, suffix, text))

    for artifact_path, target in artifact_files.items():
        kind = classify_artifact(artifact_path)
        suffix = _artifact_suffix(artifact_path)
        if _looks_like_ppt_artifact(task, artifact_path) and suffix == ".pptx":
            results.append(_evaluate_pptx_artifact(artifact_path, target))
        if kind == "image":
            results.append(_evaluate_image_artifact(artifact_path, target))
        elif kind == "archive":
            results.append(_evaluate_archive_artifact(artifact_path, target))
        elif suffix in MANUAL_REVIEW_SUFFIXES:
            results.append(_manual_review_result(artifact_path, kind))

    test_result = await _test_report_quality_result(
        config,
        task,
        workspace_path,
        artifact_files,
    )
    if test_result is not None:
        results.append(test_result)

    judge_result = await _requirements_coverage_result(config, task, attempt, artifact_texts)
    if judge_result is not None:
        results.append(judge_result)

    reflection = _reflection_for_failures(task, results)
    return EvaluationOutcome(results=results, reflection=reflection)


def evaluation_results_payload(results: list[Any]) -> list[dict[str, Any]]:
    return [_evaluation_result_payload(result) for result in results]


def reflection_payload(reflection: Any | None) -> dict[str, Any] | None:
    if reflection is None:
        return None
    if isinstance(reflection, ReflectionResult):
        return asdict(reflection)
    if isinstance(reflection, Mapping):
        return dict(reflection)
    return None


def failed_evaluation_lines(results: list[Any]) -> list[str]:
    lines: list[str] = []
    for result in results:
        payload = _evaluation_result_payload(result)
        if payload.get("status") != "failed":
            continue
        evaluator = str(payload.get("evaluator") or "evaluation")
        issues = payload.get("issues")
        if not isinstance(issues, list) or not issues:
            lines.append(f"{evaluator}: failed")
            continue
        for issue in issues:
            if not isinstance(issue, Mapping):
                continue
            code = str(issue.get("code") or "issue")
            message = str(issue.get("message") or "failed")
            repair_hint = issue.get("repair_hint")
            if isinstance(repair_hint, str) and repair_hint:
                message = f"{message} - {repair_hint}"
            lines.append(f"{evaluator}/{code}: {message}")
    return lines


def _reflection_for_failures(
    task: SubTask,
    results: list[EvaluationResult],
) -> ReflectionResult | None:
    failed_lines = failed_evaluation_lines(results)
    if not failed_lines:
        return None
    evidence = failed_lines[:8]
    artifact_targets = _failed_artifact_targets(results)
    artifact_clause = (
        f"Artifact target(s): {', '.join(artifact_targets)}. "
        if artifact_targets
        else ""
    )
    expected_reference = task.expected_output or "not specified"
    repair_instruction = (
        "This is a repair attempt after deterministic evaluation failed. "
        "Revise the workspace artifacts for this task so the failed evaluation checks pass. "
        "Do not repeat the previous failing artifact content. "
        "Ignore any earlier instruction that intentionally asked for an empty artifact, "
        "TODO-only content, placeholder-only content, or blank sections; those instructions "
        "were only for triggering evaluation failure. "
        "If the original user/task prompt contains repair or fallback requirements, follow "
        "those repair requirements now. "
        f"Task: {task.title}. "
        f"{artifact_clause}"
        "Original expected output is only a path/format reference, not permission to keep "
        f"failing placeholders: {expected_reference}. "
        f"Evaluation issues: {'; '.join(evidence)}. "
        "Return complete task-specific content with no TODO or placeholder-only sections."
    )
    return ReflectionResult(
        failure_category="evaluation_failed",
        summary="One or more required artifact evaluation checks failed.",
        evidence=evidence,
        repair_instruction=repair_instruction,
    )


def _failed_artifact_targets(results: list[EvaluationResult]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for result in results:
        if result.status != "failed":
            continue
        for artifact_path in result.checked_artifacts:
            item = artifact_path.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            targets.append(item)
    return targets[:8]


def _evaluation_result_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, EvaluationResult):
        return asdict(result)
    if isinstance(result, Mapping):
        return dict(result)
    return {
        "name": "evaluation",
        "status": "unknown",
        "passed": False,
        "severity": "major",
        "issues": [],
        "checked_artifacts": [],
    }
