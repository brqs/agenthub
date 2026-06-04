"""Shared evaluation result types for orchestrator evaluators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


EvaluationPayload = dict[str, Any]
