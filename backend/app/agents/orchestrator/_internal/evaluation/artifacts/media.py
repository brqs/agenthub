"""Presentation, image, archive, and manual-review evaluators."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.agents.orchestrator._internal.evaluation.artifacts.common import (
    _failed,
    _load_structured_payload,
    _looks_placeholder_only,
)
from app.agents.orchestrator._internal.evaluation.types import EvaluationIssue, EvaluationResult
from app.services.artifacts.metadata import (
    read_pptx_slide_text,
    validate_archive_artifact,
    validate_image_artifact,
)


def evaluate_ppt_artifact(path: str, suffix: str, text: str) -> EvaluationResult:
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

def evaluate_pptx_artifact(path: str, target: Path) -> EvaluationResult:
    try:
        slides = read_pptx_slide_text(target)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return _failed(
            "ppt_validation",
            [path],
            [
                EvaluationIssue(
                    code="pptx_parse_error",
                    message=f"{path} is not a readable .pptx OpenXML presentation.",
                    evidence=path,
                    repair_hint="Regenerate a valid .pptx file or provide a PPT outline.",
                )
            ],
        )
    issues: list[EvaluationIssue] = []
    if not slides:
        issues.append(
            EvaluationIssue(
                code="pptx_no_slides",
                message=f"{path} does not contain readable slides.",
                evidence=path,
                repair_hint="Add at least one slide with title or body text.",
            )
        )
    for index, text in enumerate(slides):
        if not text.strip() or _looks_placeholder_only(text):
            issues.append(
                EvaluationIssue(
                    code="pptx_slide_incomplete",
                    message=f"{path} slide {index + 1} lacks substantive text.",
                    evidence=f"slide {index + 1}",
                    repair_hint="Give every slide a title or meaningful body text.",
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

def evaluate_image_artifact(path: str, target: Path) -> EvaluationResult:
    ok, metadata, error = validate_image_artifact(target)
    if not ok:
        return _failed(
            "image_validation",
            [path],
            [
                EvaluationIssue(
                    code=error or "image_invalid",
                    message=f"{path} is not a valid image artifact.",
                    evidence=json.dumps(metadata, ensure_ascii=False),
                    repair_hint="Regenerate a valid PNG, JPEG, GIF, WebP, or SVG image.",
                )
            ],
        )
    return EvaluationResult(
        evaluator="image_validation",
        status="passed",
        passed=True,
        checked_artifacts=[path],
        issues=[
            EvaluationIssue(
                code="image_metadata",
                message="Image metadata parsed.",
                evidence=json.dumps(metadata, ensure_ascii=False),
            )
        ],
    )

def evaluate_archive_artifact(path: str, target: Path) -> EvaluationResult:
    ok, metadata, error = validate_archive_artifact(target)
    if not ok:
        return _failed(
            "archive_validation",
            [path],
            [
                EvaluationIssue(
                    code=error or "archive_invalid",
                    message=f"{path} is not a valid safe archive.",
                    evidence=json.dumps(metadata, ensure_ascii=False),
                    repair_hint=(
                        "Regenerate the archive without unsafe paths and within platform limits."
                    ),
                )
            ],
        )
    return EvaluationResult(
        evaluator="archive_validation",
        status="passed",
        passed=True,
        checked_artifacts=[path],
        issues=[
            EvaluationIssue(
                code="archive_metadata",
                message="Archive metadata parsed.",
                evidence=json.dumps(metadata, ensure_ascii=False),
            )
        ],
    )

def manual_review_result(path: str, artifact_kind: str) -> EvaluationResult:
    return EvaluationResult(
        evaluator="manual_review_required",
        status="skipped",
        passed=True,
        severity="info",
        checked_artifacts=[path],
        issues=[
            EvaluationIssue(
                code="manual_review_required",
                message=f"{path} requires human review for {artifact_kind} quality.",
                evidence=path,
                repair_hint="Ask a reviewer to confirm the artifact content and visual quality.",
            )
        ],
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

def _has_substantive_slide_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip()) and not _looks_placeholder_only(content)
    if isinstance(content, list):
        text = "\n".join(item for item in content if isinstance(item, str))
        return bool(text.strip()) and not _looks_placeholder_only(text)
    return False
