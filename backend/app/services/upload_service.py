"""File upload storage and attachment helpers."""

from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation
from app.models.upload import MessageAttachment, Upload
from app.schemas.upload import (
    AttachmentPreview,
    ClientPlatform,
    UploadOut,
    UploadPurpose,
    UploadSafetyStatus,
    UploadStatus,
)

TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".tar.gz"}
DOCUMENT_EXTENSIONS = {".doc", ".docx", ".pdf", ".ppt", ".pptx", ".xls", ".xlsx"}


class UploadService:
    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir or settings.upload_storage_dir)

    async def create_upload(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        purpose: UploadPurpose,
        file: UploadFile,
        client_platform: ClientPlatform = "web",
    ) -> Upload:
        filename = _safe_filename(file.filename or "upload.bin")
        upload = Upload(
            owner_user_id=user_id,
            conversation_id=conversation_id,
            purpose=purpose,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            detected_content_type=None,
            size_bytes=0,
            sha256="",
            storage_key="",
            status="processing",
            client_platform=client_platform,
            safety_status="passed",
            preview={},
        )
        db.add(upload)
        await db.flush()

        target_dir = self.storage_dir / str(user_id) / str(upload.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename

        digest = hashlib.sha256()
        total = 0
        try:
            with target_path.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.upload_max_file_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail={
                                "error": {
                                    "code": "UPLOAD_TOO_LARGE",
                                    "message": "Uploaded file exceeds the configured size limit",
                                }
                            },
                        )
                    digest.update(chunk)
                    out.write(chunk)
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise
        finally:
            await file.close()

        detected_type = _detect_content_type(filename, upload.content_type)
        upload.size_bytes = total
        upload.sha256 = digest.hexdigest()
        upload.detected_content_type = detected_type
        upload.storage_key = str(target_path)
        upload.status = "ready"
        upload.preview = self._build_preview(upload, target_path).model_dump(exclude_none=True)
        await db.flush()
        return upload

    async def create_upload_from_path(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        purpose: UploadPurpose,
        filename: str,
        content_type: str,
        source_path: Path,
        expected_sha256: str | None,
        client_platform: ClientPlatform = "web",
    ) -> Upload:
        safe_name = _safe_filename(filename)
        target_upload = Upload(
            owner_user_id=user_id,
            conversation_id=conversation_id,
            purpose=purpose,
            filename=safe_name,
            content_type=content_type or "application/octet-stream",
            detected_content_type=None,
            size_bytes=0,
            sha256="",
            storage_key="",
            status="processing",
            client_platform=client_platform,
            safety_status="passed",
            preview={},
        )
        db.add(target_upload)
        await db.flush()
        target_dir = self.storage_dir / str(user_id) / str(target_upload.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        digest = hashlib.sha256()
        total = 0
        with source_path.open("rb") as incoming, target_path.open("wb") as out:
            while chunk := incoming.read(1024 * 1024):
                total += len(chunk)
                if total > settings.upload_max_file_bytes:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "error": {
                                "code": "UPLOAD_TOO_LARGE",
                                "message": "Uploaded file exceeds the configured size limit",
                            }
                        },
                    )
                digest.update(chunk)
                out.write(chunk)
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "UPLOAD_DIGEST_MISMATCH",
                        "message": "Upload checksum did not match",
                    }
                },
            )
        detected_type = _detect_content_type(safe_name, content_type)
        target_upload.size_bytes = total
        target_upload.sha256 = actual_sha256
        target_upload.detected_content_type = detected_type
        target_upload.storage_key = str(target_path)
        target_upload.status = "ready"
        target_upload.preview = self._build_preview(target_upload, target_path).model_dump(
            exclude_none=True
        )
        await db.flush()
        return target_upload

    async def get_owned_upload(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        upload_id: UUID,
    ) -> Upload:
        upload = await db.get(Upload, upload_id)
        if upload is None or upload.owner_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "UPLOAD_NOT_FOUND", "message": "Upload not found"}},
            )
        return upload

    async def validate_ready_uploads(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        conversation_id: UUID,
        upload_ids: list[UUID],
    ) -> list[Upload]:
        if not upload_ids:
            return []
        unique_ids = list(dict.fromkeys(upload_ids))
        stmt = select(Upload).where(Upload.id.in_(unique_ids))
        uploads_by_id = {upload.id: upload for upload in (await db.execute(stmt)).scalars()}
        uploads: list[Upload] = []
        for upload_id in unique_ids:
            upload = uploads_by_id.get(upload_id)
            if upload is None or upload.owner_user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": {
                            "code": "UPLOAD_NOT_FOUND",
                            "message": "One or more uploads were not found",
                        }
                    },
                )
            if upload.conversation_id not in (None, conversation_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": {
                            "code": "UPLOAD_CONVERSATION_MISMATCH",
                            "message": "Upload does not belong to this conversation",
                        }
                    },
                )
            if upload.status != "ready":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "UPLOAD_NOT_READY",
                            "message": "Upload is not ready to attach",
                        }
                    },
                )
            if upload.safety_status == "blocked":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": {
                            "code": "UPLOAD_BLOCKED",
                            "message": "Upload was blocked by safety checks",
                        }
                    },
                )
            uploads.append(upload)
        return uploads

    async def assert_conversation_owner(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        conversation_id: UUID,
    ) -> None:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "CONVERSATION_NOT_FOUND",
                        "message": "Conversation not found",
                    }
                },
            )

    def download_path(self, upload: Upload) -> Path:
        if upload.status == "deleted":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={"error": {"code": "UPLOAD_DELETED", "message": "Upload was deleted"}},
            )
        path = Path(upload.storage_key)
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "UPLOAD_FILE_MISSING", "message": "File not found"}},
            )
        return path

    async def delete_upload(self, db: AsyncSession, upload: Upload) -> None:
        upload.status = "deleted"
        path = Path(upload.storage_key)
        shutil.rmtree(path.parent, ignore_errors=True)
        await db.flush()

    async def link_message_attachments(
        self,
        db: AsyncSession,
        *,
        message_id: UUID,
        uploads: list[Upload],
    ) -> None:
        for upload in uploads:
            db.add(
                MessageAttachment(
                    message_id=message_id,
                    upload_id=upload.id,
                    role="user_supplied",
                    disposition=upload.purpose,
                )
            )
        await db.flush()

    def attachment_blocks(self, uploads: list[Upload]) -> list[dict[str, Any]]:
        return [
            {
                "type": "attachment",
                "upload_id": str(upload.id),
                "filename": upload.filename,
                "content_type": upload.detected_content_type or upload.content_type,
                "size_bytes": upload.size_bytes,
                "purpose": upload.purpose,
                "safety_status": upload.safety_status,
                "preview": upload.preview or None,
            }
            for upload in uploads
        ]

    def to_out(self, upload: Upload) -> UploadOut:
        return UploadOut(
            id=upload.id,
            filename=upload.filename,
            content_type=upload.content_type,
            detected_content_type=upload.detected_content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            purpose=cast(UploadPurpose, upload.purpose),
            status=cast(UploadStatus, upload.status),
            client_platform=cast(ClientPlatform, upload.client_platform),
            safety_status=cast(UploadSafetyStatus, upload.safety_status),
            preview=AttachmentPreview.model_validate(upload.preview)
            if upload.preview
            else None,
            error_code=upload.error_code,
            error_message=upload.error_message,
            created_at=upload.created_at,
        )

    def _build_preview(self, upload: Upload, path: Path) -> AttachmentPreview:
        content_type = upload.detected_content_type or upload.content_type
        suffix = _compound_suffix(path.name)
        if content_type.startswith("image/"):
            return AttachmentPreview(
                kind="image",
                url=f"/api/v1/uploads/{upload.id}/download",
                thumbnail_url=f"/api/v1/uploads/{upload.id}/download",
            )
        if suffix in ARCHIVE_EXTENSIONS:
            return AttachmentPreview(kind="archive", entries_preview=_archive_entries(path))
        if content_type.startswith("text/") or suffix in TEXT_EXTENSIONS:
            preview = _read_text_preview(path)
            return AttachmentPreview(
                kind="code" if suffix in TEXT_EXTENSIONS - {".txt", ".md"} else "text",
                text_preview=preview["text"],
                truncated=preview["truncated"],
            )
        if suffix in DOCUMENT_EXTENSIONS:
            return AttachmentPreview(kind="document")
        return AttachmentPreview(kind="unknown")


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    return name[:180] or "upload.bin"


def _compound_suffix(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(lower).suffix


def _detect_content_type(filename: str, fallback: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback or "application/octet-stream"


def _read_text_preview(path: Path) -> dict[str, Any]:
    max_bytes = settings.upload_preview_max_bytes
    raw = path.read_bytes()[: max_bytes + 1]
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    return {
        "text": raw.decode("utf-8", errors="replace"),
        "truncated": truncated,
    }


def _archive_entries(path: Path) -> list[str]:
    if path.suffix.lower() != ".zip":
        return []
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()[:20]
    except zipfile.BadZipFile:
        return []


upload_service = UploadService()
