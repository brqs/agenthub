"""Deterministic Evaluation / Reflection helpers for Orchestrator attempts."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import re
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from app.agents.orchestrator.types import SubTask, TaskAttempt

DEFAULT_EVALUATION_READ_MAX_BYTES = 65_536
MAX_EVALUATION_READ_LIMIT = 1_048_576
SENSITIVE_PATH_PARTS = {".agenthub", ".env", ".ssh", "secrets"}
DOCUMENT_SUFFIXES = {".md", ".txt"}
STATIC_CODE_SUFFIXES = {".py", ".json", ".toml"}
STRUCTURED_SUFFIXES = {".json", ".yaml", ".yml"}
TEST_INTENT_RE = re.compile(r"(?i)(test|tests|pytest|测试|验收|校验)")
WORKFLOW_INTENT_RE = re.compile(r"(?i)(workflow|工作流|流程编排|dag)")
PPT_INTENT_RE = re.compile(r"(?i)(ppt|slides?|deck|presentation|幻灯片|演示文稿)")
TEST_RUNNER_OUTPUT_MAX_CHARS = 4_000
UNFINISHED_MARKERS = (
    "todo",
    "tbd",
    "placeholder",
    "lorem ipsum",
    "待补充",
    "待完善",
    "未完成",
    "占位",
)


@dataclass(frozen=True, slots=True)
class EvaluationIssue:
    code: str
    message: str
    evidence: str | None = None
    repair_hint: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluator: str
    status: str
    passed: bool
    severity: str = "info"
    issues: list[EvaluationIssue] = field(default_factory=list)
    checked_artifacts: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReflectionResult:
    failure_category: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    repair_instruction: str = ""


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    results: list[EvaluationResult]
    reflection: ReflectionResult | None = None

    @property
    def failed(self) -> bool:
        return any(not result.passed and result.status == "failed" for result in self.results)


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
        suffix = target.suffix.lower()
        if suffix not in DOCUMENT_SUFFIXES | STATIC_CODE_SUFFIXES | STRUCTURED_SUFFIXES:
            continue
        text = _read_text_limited(target, read_max_bytes)
        if text is None:
            continue
        artifact_texts[artifact_path] = text
        if suffix in DOCUMENT_SUFFIXES:
            results.append(_evaluate_document(artifact_path, text))
        elif suffix in STATIC_CODE_SUFFIXES:
            results.append(_evaluate_static_code(artifact_path, suffix, text))
        if _looks_like_workflow_artifact(task, artifact_path):
            results.append(_evaluate_workflow_artifact(artifact_path, suffix, text))
        if _looks_like_ppt_artifact(task, artifact_path):
            results.append(_evaluate_ppt_artifact(artifact_path, suffix, text))

    for artifact_path, target in artifact_files.items():
        if _looks_like_ppt_artifact(task, artifact_path) and target.suffix.lower() == ".pptx":
            results.append(
                EvaluationResult(
                    evaluator="ppt_validation",
                    status="skipped",
                    passed=True,
                    checked_artifacts=[artifact_path],
                    issues=[
                        EvaluationIssue(
                            code="pptx_binary_not_parsed",
                            message=".pptx binary validation is not part of the MVP evaluator.",
                            evidence=artifact_path,
                        )
                    ],
                )
            )

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


def _artifact_exists_result(attempt: TaskAttempt) -> EvaluationResult:
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


def _evaluate_document(path: str, text: str) -> EvaluationResult:
    stripped = text.strip()
    issues: list[EvaluationIssue] = []
    if not stripped:
        issues.append(
            EvaluationIssue(
                code="empty_document",
                message=f"{path} is empty.",
                evidence=path,
                repair_hint="Write substantive content that satisfies the task.",
            )
        )
    elif _looks_placeholder_only(stripped):
        issues.append(
            EvaluationIssue(
                code="placeholder_document",
                message=f"{path} is mostly placeholder or unfinished text.",
                evidence=path,
                repair_hint="Replace placeholders with complete, task-specific content.",
            )
        )
    if issues:
        return EvaluationResult(
            evaluator="document_quality",
            status="failed",
            passed=False,
            severity="major",
            issues=issues,
            checked_artifacts=[path],
        )
    return EvaluationResult(
        evaluator="document_quality",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )


def _evaluate_static_code(path: str, suffix: str, text: str) -> EvaluationResult:
    try:
        if suffix == ".py":
            ast.parse(text, filename=path)
        elif suffix == ".json":
            json.loads(text)
        elif suffix == ".toml":
            tomllib.loads(text)
    except (SyntaxError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return EvaluationResult(
            evaluator="code_static_quality",
            status="failed",
            passed=False,
            severity="major",
            issues=[
                EvaluationIssue(
                    code="parse_error",
                    message=f"{path} failed static parse: {exc}",
                    evidence=path,
                    repair_hint=f"Fix the syntax in {path}.",
                )
            ],
            checked_artifacts=[path],
        )
    return EvaluationResult(
        evaluator="code_static_quality",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )


def _evaluate_workflow_artifact(path: str, suffix: str, text: str) -> EvaluationResult:
    payload = _load_structured_payload(path, suffix, text, "workflow_validation")
    if isinstance(payload, EvaluationResult):
        return payload
    issues: list[EvaluationIssue] = []
    if not isinstance(payload, Mapping):
        issues.append(
            EvaluationIssue(
                code="workflow_not_object",
                message=f"{path} must be an object with version, name, nodes, and edges.",
                evidence=path,
                repair_hint="Use a JSON/YAML object containing version, name, nodes, and edges.",
            )
        )
        return _failed("workflow_validation", [path], issues)

    for key in ("version", "name", "nodes", "edges"):
        if key not in payload:
            issues.append(
                EvaluationIssue(
                    code=f"workflow_missing_{key}",
                    message=f"{path} is missing required workflow field '{key}'.",
                    evidence=path,
                    repair_hint=f"Add the '{key}' field to the workflow artifact.",
                )
            )
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    node_ids: set[str] = set()
    if not isinstance(nodes, list) or not nodes:
        issues.append(
            EvaluationIssue(
                code="workflow_nodes_invalid",
                message=f"{path} must define a non-empty nodes list.",
                evidence=path,
                repair_hint="Add nodes with string id and type fields.",
            )
        )
    else:
        for index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                issues.append(
                    EvaluationIssue(
                        code="workflow_node_not_object",
                        message=f"{path} node {index} must be an object.",
                        evidence=f"nodes[{index}]",
                        repair_hint="Represent each workflow node as an object.",
                    )
                )
                continue
            node_id = node.get("id")
            node_type = node.get("type")
            if not isinstance(node_id, str) or not node_id.strip():
                issues.append(
                    EvaluationIssue(
                        code="workflow_node_missing_id",
                        message=f"{path} node {index} is missing a string id.",
                        evidence=f"nodes[{index}]",
                        repair_hint="Give every node a unique string id.",
                    )
                )
                continue
            if node_id in node_ids:
                issues.append(
                    EvaluationIssue(
                        code="workflow_duplicate_node_id",
                        message=f"{path} contains duplicate node id '{node_id}'.",
                        evidence=node_id,
                        repair_hint="Make workflow node ids unique.",
                    )
                )
            node_ids.add(node_id)
            if not isinstance(node_type, str) or not node_type.strip():
                issues.append(
                    EvaluationIssue(
                        code="workflow_node_missing_type",
                        message=f"{path} node '{node_id}' is missing a string type.",
                        evidence=node_id,
                        repair_hint="Give every node a string type.",
                    )
                )
    if not isinstance(edges, list):
        issues.append(
            EvaluationIssue(
                code="workflow_edges_invalid",
                message=f"{path} must define an edges list.",
                evidence=path,
                repair_hint="Add an edges list, using [] when there are no edges.",
            )
        )
    else:
        for index, edge in enumerate(edges):
            if not isinstance(edge, Mapping):
                issues.append(
                    EvaluationIssue(
                        code="workflow_edge_not_object",
                        message=f"{path} edge {index} must be an object.",
                        evidence=f"edges[{index}]",
                        repair_hint="Represent each workflow edge as an object.",
                    )
                )
                continue
            source = edge.get("source")
            target = edge.get("target")
            if not isinstance(source, str) or source not in node_ids:
                issues.append(
                    EvaluationIssue(
                        code="workflow_dangling_edge_source",
                        message=f"{path} edge {index} references missing source node.",
                        evidence=str(source),
                        repair_hint="Point every edge source at an existing node id.",
                    )
                )
            if not isinstance(target, str) or target not in node_ids:
                issues.append(
                    EvaluationIssue(
                        code="workflow_dangling_edge_target",
                        message=f"{path} edge {index} references missing target node.",
                        evidence=str(target),
                        repair_hint="Point every edge target at an existing node id.",
                    )
                )
    if issues:
        return _failed("workflow_validation", [path], issues)
    return EvaluationResult(
        evaluator="workflow_validation",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )


def _evaluate_ppt_artifact(path: str, suffix: str, text: str) -> EvaluationResult:
    if suffix == ".json":
        payload = _load_structured_payload(path, suffix, text, "ppt_validation")
        if isinstance(payload, EvaluationResult):
            return payload
        return _evaluate_ppt_outline_payload(path, payload)
    issues: list[EvaluationIssue] = []
    stripped = text.strip()
    if not stripped:
        issues.append(
            EvaluationIssue(
                code="ppt_empty",
                message=f"{path} is empty.",
                evidence=path,
                repair_hint="Add a presentation title and slide content.",
            )
        )
    elif _looks_placeholder_only(stripped):
        issues.append(
            EvaluationIssue(
                code="ppt_placeholder",
                message=f"{path} is mostly placeholder or unfinished text.",
                evidence=path,
                repair_hint="Replace placeholder slide text with complete content.",
            )
        )
    slide_markers = [
        line
        for line in stripped.splitlines()
        if line.lstrip().startswith("#") or line.strip() == "---"
    ]
    if not slide_markers:
        issues.append(
            EvaluationIssue(
                code="ppt_no_slide_structure",
                message=f"{path} does not expose clear slide structure.",
                evidence=path,
                repair_hint="Use headings or --- separators to mark slides.",
            )
        )
    if issues:
        return _failed("ppt_validation", [path], issues)
    return EvaluationResult(
        evaluator="ppt_validation",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )


def _evaluate_ppt_outline_payload(path: str, payload: Any) -> EvaluationResult:
    issues: list[EvaluationIssue] = []
    if not isinstance(payload, Mapping):
        issues.append(
            EvaluationIssue(
                code="ppt_outline_not_object",
                message=f"{path} must be an object with title and slides.",
                evidence=path,
                repair_hint="Use a JSON object containing title and slides.",
            )
        )
        return _failed("ppt_validation", [path], issues)
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        issues.append(
            EvaluationIssue(
                code="ppt_missing_title",
                message=f"{path} is missing a presentation title.",
                evidence=path,
                repair_hint="Add a non-empty title.",
            )
        )
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        issues.append(
            EvaluationIssue(
                code="ppt_no_slides",
                message=f"{path} must contain a non-empty slides list.",
                evidence=path,
                repair_hint="Add at least one slide with substantive content.",
            )
        )
    else:
        for index, slide in enumerate(slides):
            if not isinstance(slide, Mapping):
                issues.append(
                    EvaluationIssue(
                        code="ppt_slide_not_object",
                        message=f"{path} slide {index} must be an object.",
                        evidence=f"slides[{index}]",
                        repair_hint="Represent each slide as an object.",
                    )
                )
                continue
            slide_title = slide.get("title")
            content = slide.get("content", slide.get("body", slide.get("bullets")))
            has_title = isinstance(slide_title, str) and bool(slide_title.strip())
            has_content = _has_substantive_slide_content(content)
            if not has_title or not has_content:
                issues.append(
                    EvaluationIssue(
                        code="ppt_slide_incomplete",
                        message=f"{path} slide {index} needs a title and content.",
                        evidence=f"slides[{index}]",
                        repair_hint="Give every slide a title and substantive content.",
                    )
                )
    if issues:
        return _failed("ppt_validation", [path], issues)
    return EvaluationResult(
        evaluator="ppt_validation",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )


async def _test_report_quality_result(
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


async def _requirements_coverage_result(
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
        passed = bool(raw.get("passed", not issues))
        return EvaluationResult(
            evaluator="requirements_coverage",
            status="passed" if passed else "failed",
            passed=passed,
            severity=str(raw.get("severity") or ("info" if passed else "major")),
            issues=issues,
            checked_artifacts=[
                str(item)
                for item in raw_checked_artifacts
                if isinstance(item, str)
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


def _reflection_for_failures(
    task: SubTask,
    results: list[EvaluationResult],
) -> ReflectionResult | None:
    failed_lines = failed_evaluation_lines(results)
    if not failed_lines:
        return None
    evidence = failed_lines[:8]
    repair_instruction = (
        "Revise the workspace artifacts for this task so the failed evaluation checks pass. "
        f"Task: {task.title}. "
        f"Expected output: {task.expected_output or 'not specified'}. "
        f"Evaluation issues: {'; '.join(evidence)}"
    )
    return ReflectionResult(
        failure_category="evaluation_failed",
        summary="One or more required artifact evaluation checks failed.",
        evidence=evidence,
        repair_instruction=repair_instruction,
    )


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


def _failed(
    evaluator: str,
    checked_artifacts: list[str],
    issues: list[EvaluationIssue],
) -> EvaluationResult:
    return EvaluationResult(
        evaluator=evaluator,
        status="failed",
        passed=False,
        severity="major",
        issues=issues,
        checked_artifacts=checked_artifacts,
    )


def _load_structured_payload(
    path: str,
    suffix: str,
    text: str,
    evaluator: str,
) -> Any:
    try:
        if suffix == ".json":
            return json.loads(text)
        if suffix in {".yaml", ".yml"}:
            yaml = import_module("yaml")
            return yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        return _failed(
            evaluator,
            [path],
            [
                EvaluationIssue(
                    code="structured_parse_error",
                    message=f"{path} failed structured parse: {exc}",
                    evidence=path,
                    repair_hint=f"Fix the syntax in {path}.",
                )
            ],
        )
    return _failed(
        evaluator,
        [path],
        [
            EvaluationIssue(
                code="unsupported_structured_type",
                message=f"{path} is not a supported structured artifact.",
                evidence=path,
            )
        ],
    )


def _looks_like_workflow_artifact(task: SubTask, path: str) -> bool:
    lowered = path.lower()
    if not lowered.endswith((".json", ".yaml", ".yml")):
        return False
    if any(token in lowered for token in ("workflow", "dag", "flow")):
        return True
    return bool(WORKFLOW_INTENT_RE.search(f"{task.title}\n{task.instruction}"))


def _looks_like_ppt_artifact(task: SubTask, path: str) -> bool:
    lowered = path.lower()
    if not lowered.endswith((".json", ".md", ".txt", ".pptx")):
        return False
    if any(token in lowered for token in ("ppt", "slides", "slide", "deck", "presentation")):
        return True
    return bool(PPT_INTENT_RE.search(f"{task.title}\n{task.instruction}"))


def _has_substantive_slide_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip()) and not _looks_placeholder_only(content)
    if isinstance(content, list):
        text = "\n".join(item for item in content if isinstance(item, str))
        return bool(text.strip()) and not _looks_placeholder_only(text)
    return False


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


def _read_max_bytes(config: Mapping[str, Any]) -> int:
    value = config.get(
        "orchestrator_evaluation_read_max_bytes",
        DEFAULT_EVALUATION_READ_MAX_BYTES,
    )
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_EVALUATION_READ_MAX_BYTES
    return max(1, min(value, MAX_EVALUATION_READ_LIMIT))


def _safe_artifact_file(workspace_path: Path, artifact_path: str) -> Path | None:
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


def _read_text_limited(path: Path, max_bytes: int) -> str | None:
    if path.stat().st_size > max_bytes:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _looks_placeholder_only(text: str) -> bool:
    lowered = text.lower()
    marker_count = sum(lowered.count(marker) for marker in UNFINISHED_MARKERS)
    if marker_count == 0:
        return False
    meaningful = re.sub(
        r"(?i)todo|tbd|placeholder|lorem ipsum|待补充|待完善|未完成|占位|[#*\-\s:：]",
        "",
        text,
    )
    return len(meaningful.strip()) < 20 or (marker_count >= 2 and len(text) < 240)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "...[truncated]"
