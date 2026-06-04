"""Controlled test runner and requirements judge evaluators."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.agents.orchestrator._internal.evaluation.artifacts.common import _failed
from app.agents.orchestrator._internal.evaluation.types import EvaluationIssue, EvaluationResult
from app.agents.orchestrator.types import SubTask, TaskAttempt

TEST_INTENT_RE = re.compile(r"(?i)(test|tests|pytest|测试|验收|校验)")
TEST_RUNNER_OUTPUT_MAX_CHARS = 4_000


async def test_report_quality_result(
    config: Mapping[str, Any],
    task: SubTask,
    workspace_path: Path,
    artifact_files: Mapping[str, Path],
) -> EvaluationResult | None:
    if not _wants_test_runner(task):
        return None
    if config.get("orchestrator_test_runner_enabled") is not True:
        return EvaluationResult(
            evaluator="test_report_quality",
            status="skipped",
            passed=True,
            checked_artifacts=list(artifact_files),
        )
    allowed_aliases = _test_command_allowlist(config)
    if "python_compile_artifacts" not in allowed_aliases:
        return EvaluationResult(
            evaluator="test_report_quality",
            status="skipped",
            passed=True,
            issues=[
                EvaluationIssue(
                    code="test_alias_not_allowed",
                    message="No supported test runner alias is allowlisted.",
                    repair_hint="Allowlist python_compile_artifacts for Python artifacts.",
                )
            ],
            checked_artifacts=list(artifact_files),
        )
    python_artifacts = [
        artifact_path
        for artifact_path, path in artifact_files.items()
        if path.suffix.lower() == ".py"
    ]
    if not python_artifacts:
        return EvaluationResult(
            evaluator="test_report_quality",
            status="skipped",
            passed=True,
            checked_artifacts=list(artifact_files),
        )
    return await _run_python_compile_test(workspace_path, python_artifacts)

async def requirements_coverage_result(
    config: Mapping[str, Any],
    task: SubTask,
    attempt: TaskAttempt,
    artifact_texts: dict[str, str],
) -> EvaluationResult | None:
    judge = config.get("orchestrator_evaluation_judge")
    if judge is None:
        return EvaluationResult(
            evaluator="requirements_coverage",
            status="skipped",
            passed=True,
            checked_artifacts=list(artifact_texts),
        )
    raw_result = judge(task=task, attempt=attempt, artifact_texts=artifact_texts)
    if inspect.isawaitable(raw_result):
        raw_result = await raw_result
    return _coerce_judge_result(raw_result, list(artifact_texts))

async def _run_python_compile_test(
    workspace_path: Path,
    artifact_paths: list[str],
) -> EvaluationResult:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "py_compile",
        *artifact_paths,
        cwd=workspace_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except TimeoutError:
        process.kill()
        await process.wait()
        return _failed(
            "test_report_quality",
            artifact_paths,
            [
                EvaluationIssue(
                    code="test_runner_timeout",
                    message="python_compile_artifacts timed out.",
                    repair_hint="Simplify or fix the Python artifacts so compilation finishes.",
                )
            ],
        )
    output = _truncate(
        "\n".join(
            item.decode("utf-8", errors="replace")
            for item in (stdout, stderr)
            if item
        ),
        TEST_RUNNER_OUTPUT_MAX_CHARS,
    )
    if process.returncode != 0:
        return _failed(
            "test_report_quality",
            artifact_paths,
            [
                EvaluationIssue(
                    code="test_runner_failed",
                    message="python_compile_artifacts failed.",
                    evidence=output,
                    repair_hint="Fix the Python artifacts until py_compile exits successfully.",
                )
            ],
        )
    return EvaluationResult(
        evaluator="test_report_quality",
        status="passed",
        passed=True,
        checked_artifacts=artifact_paths,
        issues=[
            EvaluationIssue(
                code="test_runner_passed",
                message="python_compile_artifacts passed.",
                evidence=output or "py_compile exited successfully",
            )
        ],
    )

def _coerce_judge_result(raw: Any, checked_artifacts: list[str]) -> EvaluationResult:
    if isinstance(raw, EvaluationResult):
        return raw
    if isinstance(raw, Mapping):
        raw_checked_artifacts = raw.get("checked_artifacts", checked_artifacts)
        if not isinstance(raw_checked_artifacts, list):
            raw_checked_artifacts = checked_artifacts
        issues = [
            EvaluationIssue(
                code=str(issue.get("code") or "requirements_issue"),
                message=str(issue.get("message") or "Requirements coverage issue."),
                evidence=(
                    str(issue.get("evidence")) if issue.get("evidence") is not None else None
                ),
                repair_hint=(
                    str(issue.get("repair_hint"))
                    if issue.get("repair_hint") is not None
                    else None
                ),
            )
            for issue in raw.get("issues", [])
            if isinstance(issue, Mapping)
        ]
        raw_status = str(raw.get("status") or "")
        if raw_status == "skipped":
            return EvaluationResult(
                evaluator="requirements_coverage",
                status="skipped",
                passed=True,
                severity=str(raw.get("severity") or "info"),
                issues=issues,
                checked_artifacts=[
                    str(item)
                    for item in raw_checked_artifacts
                    if isinstance(item, str)
                ],
            )
        passed = bool(raw.get("passed", not issues))
        return EvaluationResult(
            evaluator="requirements_coverage",
            status="passed" if passed else "failed",
            passed=passed,
            severity=str(raw.get("severity") or ("info" if passed else "major")),
            issues=issues,
            checked_artifacts=[
                str(item) for item in raw_checked_artifacts if isinstance(item, str)
            ],
        )
    passed = bool(raw)
    return EvaluationResult(
        evaluator="requirements_coverage",
        status="passed" if passed else "failed",
        passed=passed,
        severity="info" if passed else "major",
        issues=[]
        if passed
        else [
            EvaluationIssue(
                code="requirements_not_covered",
                message="The artifact does not cover the requested requirements.",
                repair_hint="Revise the artifact to cover the user request and task instruction.",
            )
        ],
        checked_artifacts=checked_artifacts,
    )

def _wants_test_runner(task: SubTask) -> bool:
    return bool(
        TEST_INTENT_RE.search(
            "\n".join(
                item
                for item in (task.title, task.instruction, task.expected_output or "")
                if item
            )
        )
    )

def _test_command_allowlist(config: Mapping[str, Any]) -> set[str]:
    value = config.get("orchestrator_test_command_allowlist")
    if not isinstance(value, list):
        return set()
    return {
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip() == "python_compile_artifacts"
    }

def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "...[truncated]"
