"""Resumable upload session service."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.session import UploadSession
from app.schemas.upload import (
    CompleteUploadSessionRequest,
    CreateUploadSessionRequest,
    UploadOut,
    UploadSessionOut,
)
from app.services.event_service import event_service
from app.services.upload_service import upload_service


class ResumableUploadService:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.upload_storage_dir) / "_sessions"

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        payload: CreateUploadSessionRequest,
    ) -> UploadSession:
        if payload.total_size_bytes > settings.upload_max_file_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": {"code": "UPLOAD_TOO_LARGE", "message": "Upload too large"}},
            )
        session = UploadSession(
            owner_user_id=user_id,
            conversation_id=payload.conversation_id,
            purpose=payload.purpose,
            filename=payload.filename,
            content_type=payload.content_type,
            total_size_bytes=payload.total_size_bytes,
            expected_sha256=payload.expected_sha256,
            client_platform=payload.client_platform,
            part_size_bytes=payload.part_size_bytes,
            received_parts=[],
            status="open",
            storage_key="",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        db.add(session)
        await db.flush()
        session_dir = self._session_dir(user_id, session.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        session.storage_key = str(session_dir)
        await db.flush()
        await event_service.record(
            db,
            user_id=user_id,
            event_type="upload_session.created",
            resource_type="upload_session",
            resource_id=session.id,
            conversation_id=session.conversation_id,
            payload={"client_platform": session.client_platform},
        )
        return session

    async def get_owned(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> UploadSession:
        session = await db.get(UploadSession, session_id)
        if session is None or session.owner_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "UPLOAD_SESSION_NOT_FOUND", "message": "Not found"}},
            )
        if session.status == "open" and session.expires_at <= datetime.now(UTC):
            session.status = "expired"
            session.error_code = "UPLOAD_SESSION_EXPIRED"
            session.error_message = "Upload session expired"
            await db.flush()
        return session

    async def put_part(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
        part_number: int,
        data: bytes,
    ) -> UploadSession:
        if part_number < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": {"code": "INVALID_PART_NUMBER", "message": "Invalid part number"}},
            )
        session = await self.get_owned(db, user_id=user_id, session_id=session_id)
        self._assert_open(session)
        if len(data) > session.part_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": {"code": "UPLOAD_PART_TOO_LARGE", "message": "Part too large"}},
            )
        part_path = Path(session.storage_key) / f"{part_number:08d}.part"
        part_path.write_bytes(data)
        parts = sorted({*session.received_parts, part_number})
        session.received_parts = parts
        await db.flush()
        await event_service.record(
            db,
            user_id=user_id,
            event_type="upload_session.part_received",
            resource_type="upload_session",
            resource_id=session.id,
            conversation_id=session.conversation_id,
            payload={"part_number": part_number, "received_parts": parts},
        )
        return session

    async def complete(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
        payload: CompleteUploadSessionRequest,
    ) -> tuple[UploadSession, UploadOut]:
        session = await self.get_owned(db, user_id=user_id, session_id=session_id)
        self._assert_open(session)
        assembled = Path(session.storage_key) / "assembled.upload"
        total = 0
        with assembled.open("wb") as out:
            for part_number in session.received_parts:
                part_path = Path(session.storage_key) / f"{part_number:08d}.part"
                if not part_path.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "UPLOAD_PART_MISSING",
                                "message": f"Upload part {part_number} is missing",
                            }
                        },
                    )
                data = part_path.read_bytes()
                total += len(data)
                out.write(data)
        if total != session.total_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "UPLOAD_SIZE_MISMATCH",
                        "message": "Upload size did not match declared size",
                    }
                },
            )
        digest = payload.sha256 or session.expected_sha256
        upload = await upload_service.create_upload_from_path(
            db,
            user_id=user_id,
            conversation_id=session.conversation_id,
            purpose=session.purpose,  # type: ignore[arg-type]
            filename=session.filename,
            content_type=session.content_type,
            source_path=assembled,
            expected_sha256=digest,
            client_platform=session.client_platform,  # type: ignore[arg-type]
        )
        session.status = "completed"
        session.upload_id = upload.id
        await db.flush()
        shutil.rmtree(Path(session.storage_key), ignore_errors=True)
        await event_service.record(
            db,
            user_id=user_id,
            event_type="upload.ready",
            resource_type="upload",
            resource_id=upload.id,
            conversation_id=session.conversation_id,
            payload={
                "upload_session_id": str(session.id),
                "client_platform": session.client_platform,
            },
        )
        return session, upload_service.to_out(upload)

    async def cancel(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> UploadSession:
        session = await self.get_owned(db, user_id=user_id, session_id=session_id)
        if session.status == "open":
            session.status = "cancelled"
            shutil.rmtree(Path(session.storage_key), ignore_errors=True)
            await db.flush()
            await event_service.record(
                db,
                user_id=user_id,
                event_type="upload_session.cancelled",
                resource_type="upload_session",
                resource_id=session.id,
                conversation_id=session.conversation_id,
            )
        return session

    def to_out(self, session: UploadSession) -> UploadSessionOut:
        return UploadSessionOut(
            id=session.id,
            filename=session.filename,
            content_type=session.content_type,
            total_size_bytes=session.total_size_bytes,
            expected_sha256=session.expected_sha256,
            client_platform=session.client_platform,  # type: ignore[arg-type]
            part_size_bytes=session.part_size_bytes,
            received_parts=session.received_parts,
            status=session.status,  # type: ignore[arg-type]
            upload_id=session.upload_id,
            error_code=session.error_code,
            error_message=session.error_message,
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_at=session.expires_at,
        )

    def _assert_open(self, session: UploadSession) -> None:
        if session.status != "open":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "UPLOAD_SESSION_NOT_OPEN",
                        "message": "Upload session is not open",
                    }
                },
            )

    def _session_dir(self, user_id: UUID, session_id: UUID) -> Path:
        return self.base_dir / str(user_id) / str(session_id)


resumable_upload_service = ResumableUploadService()
