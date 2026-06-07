"""Upload service unit tests that do not require a database."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.upload import Upload
from app.services.upload_service import UploadService, _safe_filename


def test_safe_filename_strips_path_and_unsafe_characters() -> None:
    assert _safe_filename("../../secret?.txt") == "secret_.txt"
    assert _safe_filename("") == "upload.bin"


def test_build_preview_reads_text_preview(tmp_path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# hello\nAgentHub upload", encoding="utf-8")
    upload = _upload(filename="notes.md", content_type="text/markdown")

    preview = UploadService(tmp_path)._build_preview(upload, path)

    assert preview.kind == "text"
    assert preview.text_preview == "# hello\nAgentHub upload"
    assert preview.truncated is False


def test_build_preview_lists_zip_entries(tmp_path) -> None:
    import zipfile

    path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("README.md", "hello")
        archive.writestr("src/app.ts", "console.log('hi')")
    upload = _upload(filename="bundle.zip", content_type="application/zip")

    preview = UploadService(tmp_path)._build_preview(upload, path)

    assert preview.kind == "archive"
    assert preview.entries_preview == ["README.md", "src/app.ts"]


def test_download_path_rejects_deleted_upload(tmp_path) -> None:
    path = tmp_path / "deleted.txt"
    path.write_text("deleted", encoding="utf-8")
    upload = _upload(filename="deleted.txt", content_type="text/plain")
    upload.storage_key = str(path)
    upload.status = "deleted"

    with pytest.raises(HTTPException) as exc:
        UploadService(tmp_path).download_path(upload)

    assert exc.value.status_code == 410


def _upload(*, filename: str, content_type: str) -> Upload:
    return Upload(
        id=uuid4(),
        owner_user_id=uuid4(),
        conversation_id=uuid4(),
        purpose="message_attachment",
        filename=filename,
        content_type=content_type,
        detected_content_type=content_type,
        size_bytes=0,
        sha256="hash",
        storage_key="",
        status="ready",
        safety_status="passed",
        preview={},
    )
