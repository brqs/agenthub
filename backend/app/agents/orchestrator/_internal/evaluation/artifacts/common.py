"""Shared evaluator result and parsing helpers."""

from __future__ import annotations

import json
import re
from importlib import import_module
from typing import Any

from app.agents.orchestrator._internal.evaluation.types import EvaluationIssue, EvaluationResult

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
