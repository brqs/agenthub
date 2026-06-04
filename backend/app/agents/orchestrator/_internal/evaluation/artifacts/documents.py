"""Document and static-code evaluators."""

from __future__ import annotations

import ast
import json
import re
import tomllib

from app.agents.orchestrator._internal.evaluation.artifacts.common import (
    _failed,
    _looks_placeholder_only,
)
from app.agents.orchestrator._internal.evaluation.types import EvaluationIssue, EvaluationResult


def evaluate_document(path: str, text: str, *, strict: bool = False) -> EvaluationResult:
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
    elif strict:
        lines = [line.strip() for line in stripped.splitlines()]
        has_title = any(
            line.startswith("#") and len(line.lstrip("#").strip()) >= 3
            for line in lines
        )
        meaningful_lines = [
            line
            for line in lines
            if len(line) >= 8 and not line.startswith("#") and line not in {"---", "***"}
        ]
        placeholder_lines = _placeholder_lines(lines)
        empty_headings = [
            index
            for index, line in enumerate(lines)
            if line.startswith("#") and not _heading_has_content(lines, index)
        ]
        if path.lower().endswith(".md") and not has_title:
            issues.append(
                EvaluationIssue(
                    code="document_missing_title",
                    message=f"{path} is missing a clear markdown title.",
                    evidence=path,
                    repair_hint="Add a top-level or section title that describes the document.",
                )
            )
        if not meaningful_lines or (not has_title and len(stripped) < 40):
            issues.append(
                EvaluationIssue(
                    code="document_too_short",
                    message=f"{path} is too short to satisfy a report/document task.",
                    evidence=path,
                    repair_hint="Add substantive paragraphs with task-specific detail.",
                )
            )
        if empty_headings:
            issues.append(
                EvaluationIssue(
                    code="document_empty_section",
                    message=f"{path} has headings without section content.",
                    evidence=path,
                    repair_hint=(
                        "Fill each section with substantive content or remove empty sections."
                    ),
                )
            )
        if placeholder_lines:
            issues.append(
                EvaluationIssue(
                    code="document_unfinished_marker",
                    message=f"{path} still contains unfinished placeholder lines.",
                    evidence="; ".join(placeholder_lines[:3]),
                    repair_hint="Remove TODO/placeholder lines from the final document.",
                )
            )
    if issues:
        return _failed(
            "document_quality",
            [path],
            issues,
        )
    return EvaluationResult(
        evaluator="document_quality",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )

def evaluate_static_code(path: str, suffix: str, text: str) -> EvaluationResult:
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

def _heading_has_content(lines: list[str], heading_index: int) -> bool:
    heading_level = _markdown_heading_level(lines[heading_index])
    if heading_level is None:
        return True
    saw_child_heading = False
    for line in lines[heading_index + 1 :]:
        next_heading_level = _markdown_heading_level(line)
        if next_heading_level is not None:
            if next_heading_level <= heading_level:
                return saw_child_heading
            saw_child_heading = True
            continue
        if saw_child_heading:
            continue
        if len(line.strip()) >= 8:
            return True
    return saw_child_heading

def _markdown_heading_level(line: str) -> int | None:
    if not line.startswith("#"):
        return None
    marker = line.split(maxsplit=1)[0]
    if set(marker) != {"#"}:
        return None
    return len(marker)

def _placeholder_lines(lines: list[str]) -> list[str]:
    placeholder_re = re.compile(
        r"(?i)^\s*(?:[-*]\s*)?(?:\[[ x]?\]\s*)?"
        r"(todo|tbd|placeholder|待补充|待完善|未完成|占位)\b"
    )
    matches: list[str] = []
    in_fence = False
    for line in lines:
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence and placeholder_re.search(line):
            matches.append(line)
    return matches
