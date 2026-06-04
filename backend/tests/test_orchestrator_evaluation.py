"""Focused tests for deterministic Orchestrator artifact evaluators."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.agents.orchestrator.evaluation import evaluate_attempt
from app.agents.orchestrator.types import SubTask, TaskAttempt
from app.services.artifacts.manifest import evaluation_status_for_artifact
from app.services.artifacts.metadata import build_artifact_metadata

pytestmark = pytest.mark.asyncio


def _task(title: str, instruction: str, expected_output: str) -> SubTask:
    return SubTask(
        task_id="task-a",
        agent_id="agent-a",
        title=title,
        instruction=instruction,
        expected_output=expected_output,
    )


async def _evaluate(tmp_path: Path, artifact_path: str, task: SubTask):
    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=[artifact_path],
    )
    return await evaluate_attempt({}, task, attempt, tmp_path)


def _write_minimal_pptx(path: Path, slide_text: str = "Title\nBody") -> None:
    slide_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{slide_text}</a:t>"
        "</a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("ppt/slides/slide1.xml", slide_xml)


def _write_png(path: Path) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00"
    )


async def test_document_quality_rejects_unstructured_short_markdown(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("Short.", encoding="utf-8")

    outcome = await _evaluate(
        tmp_path,
        "report.md",
        _task("Write report", "Write report.md", "report.md"),
    )

    failed = [result for result in outcome.results if result.evaluator == "document_quality"]
    assert failed[0].status == "failed"
    assert {issue.code for issue in failed[0].issues} >= {
        "document_missing_title",
        "document_too_short",
    }


async def test_document_quality_accepts_structured_markdown(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text(
        "# Report\n\nThis section explains the background and concrete validation result.\n",
        encoding="utf-8",
    )

    outcome = await _evaluate(
        tmp_path,
        "report.md",
        _task("Write report", "Write report.md", "report.md"),
    )

    result = next(item for item in outcome.results if item.evaluator == "document_quality")
    assert result.status == "passed"


async def test_document_quality_accepts_title_with_populated_sections(
    tmp_path: Path,
) -> None:
    (tmp_path / "report.md").write_text(
        "\n".join(
            [
                "# Repair Report",
                "",
                "## Summary",
                "",
                "This section explains the failure and the repair approach in detail.",
                "",
                "## Validation Evidence",
                "",
                "This section records concrete evidence that the repaired artifact passes.",
            ]
        ),
        encoding="utf-8",
    )

    outcome = await _evaluate(
        tmp_path,
        "report.md",
        _task("Write repair report", "Write repair-report.md", "report.md"),
    )

    result = next(item for item in outcome.results if item.evaluator == "document_quality")
    assert result.status == "passed"


async def test_document_quality_rejects_titled_todo_placeholder(
    tmp_path: Path,
) -> None:
    (tmp_path / "report.md").write_text(
        "# Repair Report\n\nTODO: Evaluation/repair workflow not yet initiated.\n",
        encoding="utf-8",
    )

    outcome = await _evaluate(
        tmp_path,
        "report.md",
        _task("Write repair report", "Write repair-report.md", "report.md"),
    )

    result = next(item for item in outcome.results if item.evaluator == "document_quality")
    assert result.status == "failed"
    assert {issue.code for issue in result.issues} >= {"document_unfinished_marker"}


async def test_document_quality_allows_placeholder_evidence_in_code_fence(
    tmp_path: Path,
) -> None:
    (tmp_path / "report.md").write_text(
        "\n".join(
            [
                "# Repair Report",
                "",
                "## Summary",
                "",
                "This report explains the completed repair and current validation status.",
                "",
                "## Validation Evidence",
                "",
                "The old placeholder content is shown only as historical evidence:",
                "",
                "```",
                "TODO: replace this placeholder",
                "```",
                "",
                "The current document has substantive content outside the fenced example.",
            ]
        ),
        encoding="utf-8",
    )

    outcome = await _evaluate(
        tmp_path,
        "report.md",
        _task("Write repair report", "Write repair-report.md", "report.md"),
    )

    result = next(item for item in outcome.results if item.evaluator == "document_quality")
    assert result.status == "passed"


async def test_pptx_validation_accepts_openxml_slides(tmp_path: Path) -> None:
    _write_minimal_pptx(tmp_path / "deck.pptx")

    outcome = await _evaluate(
        tmp_path,
        "deck.pptx",
        _task("Create PPT", "Create deck.pptx", "deck.pptx"),
    )

    result = next(item for item in outcome.results if item.evaluator == "ppt_validation")
    assert result.status == "passed"


async def test_pptx_validation_rejects_corrupt_binary(tmp_path: Path) -> None:
    (tmp_path / "deck.pptx").write_bytes(b"not a zip")

    outcome = await _evaluate(
        tmp_path,
        "deck.pptx",
        _task("Create PPT", "Create deck.pptx", "deck.pptx"),
    )

    result = next(item for item in outcome.results if item.evaluator == "ppt_validation")
    assert result.status == "failed"
    assert result.issues[0].code == "pptx_parse_error"


async def test_image_and_archive_validators_report_metadata(tmp_path: Path) -> None:
    _write_png(tmp_path / "logo.png")
    with zipfile.ZipFile(tmp_path / "export.zip", "w") as archive:
        archive.writestr("README.md", "# Export")

    image = await _evaluate(
        tmp_path,
        "logo.png",
        _task("Create image", "Create logo.png", "logo.png"),
    )
    archive = await _evaluate(
        tmp_path,
        "export.zip",
        _task("Create archive", "Create export.zip", "export.zip"),
    )

    assert next(item for item in image.results if item.evaluator == "image_validation").status == (
        "passed"
    )
    assert next(
        item for item in archive.results if item.evaluator == "archive_validation"
    ).status == "passed"


async def test_archive_validator_rejects_path_traversal(tmp_path: Path) -> None:
    with tarfile.open(tmp_path / "bad.tar.gz", "w:gz") as archive:
        data = b"bad"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))

    outcome = await _evaluate(
        tmp_path,
        "bad.tar.gz",
        _task("Create archive", "Create bad.tar.gz", "bad.tar.gz"),
    )

    result = next(item for item in outcome.results if item.evaluator == "archive_validation")
    assert result.status == "failed"
    assert result.issues[0].code == "archive_path_traversal"


async def test_manual_review_required_for_unsupported_binary_document(
    tmp_path: Path,
) -> None:
    (tmp_path / "brief.docx").write_bytes(b"fake-docx")

    outcome = await _evaluate(
        tmp_path,
        "brief.docx",
        _task("Create document", "Create brief.docx", "brief.docx"),
    )

    result = next(item for item in outcome.results if item.evaluator == "manual_review_required")
    assert result.status == "skipped"
    assert result.passed is True


async def test_requirements_coverage_judge_can_return_skipped(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text(
        "# Report\n\nThis section contains enough detail for deterministic checks.",
        encoding="utf-8",
    )

    async def judge(**_: object) -> dict[str, object]:
        return {
            "status": "skipped",
            "issues": [
                {
                    "code": "judge_not_configured",
                    "message": "No production judge configured.",
                }
            ],
            "checked_artifacts": ["report.md"],
        }

    attempt = TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        artifact_paths=["report.md"],
    )
    outcome = await evaluate_attempt(
        {"orchestrator_evaluation_judge": judge},
        _task("Write report", "Write report.md", "report.md"),
        attempt,
        tmp_path,
    )

    result = next(item for item in outcome.results if item.evaluator == "requirements_coverage")
    assert result.status == "skipped"
    assert result.passed is True
    assert result.checked_artifacts == ["report.md"]


async def test_artifact_metadata_for_text_image_and_archive(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("# Report\n\nBody", encoding="utf-8")
    _write_png(tmp_path / "logo.png")
    with zipfile.ZipFile(tmp_path / "export.zip", "w") as archive:
        archive.writestr("README.md", "# Export")

    document = build_artifact_metadata(tmp_path / "report.md", "report.md")
    image = build_artifact_metadata(tmp_path / "logo.png", "logo.png")
    archive_meta = build_artifact_metadata(tmp_path / "export.zip", "export.zip")

    assert document.artifact_kind == "document"
    assert document.preview_text == "# Report\n\nBody"
    assert image.artifact_kind == "image"
    assert image.metadata["width"] == 1
    assert archive_meta.artifact_kind == "archive"
    assert archive_meta.metadata["file_count"] == 1


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (
            [
                {
                    "evaluator": "document_quality",
                    "status": "passed",
                    "passed": True,
                    "checked_artifacts": ["report.md"],
                }
            ],
            "passed",
        ),
        (
            [
                {
                    "evaluator": "document_quality",
                    "status": "failed",
                    "passed": False,
                    "checked_artifacts": ["report.md"],
                }
            ],
            "failed",
        ),
        (
            [
                {
                    "evaluator": "manual_review_required",
                    "status": "skipped",
                    "passed": True,
                    "checked_artifacts": ["report.md"],
                }
            ],
            "manual_review_required",
        ),
        (
            [
                {
                    "evaluator": "requirements_coverage",
                    "status": "skipped",
                    "passed": True,
                    "checked_artifacts": ["report.md"],
                }
            ],
            "unknown",
        ),
    ],
)
async def test_manifest_evaluation_status_mapping(
    results: list[dict[str, object]],
    expected: str,
) -> None:
    assert evaluation_status_for_artifact("report.md", results) == expected
