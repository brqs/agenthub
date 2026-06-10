"""Upload routes — Owner: B1."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.core.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.upload import (
    ClientPlatform,
    CompleteUploadSessionRequest,
    CompleteUploadSessionResponse,
    CreateUploadSessionRequest,
    UploadOut,
    UploadPurpose,
    UploadSessionOut,
)
from app.services.event_service import event_service
from app.services.resumable_upload_service import resumable_upload_service
from app.services.upload_service import upload_service

router = APIRouter()


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def create_upload(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    purpose: Annotated[UploadPurpose, Form()] = "message_attachment",
    conversation_id: Annotated[UUID | None, Form()] = None,
    client_platform: Annotated[ClientPlatform, Form()] = "web",
) -> UploadOut:
    if conversation_id is not None:
        await upload_service.assert_conversation_owner(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )
    upload = await upload_service.create_upload(
        db,
        user_id=user.id,
        conversation_id=conversation_id,
        purpose=purpose,
        file=file,
        client_platform=client_platform,
    )
    await event_service.record(
        db,
        user_id=user.id,
        event_type="upload.ready",
        resource_type="upload",
        resource_id=upload.id,
        conversation_id=upload.conversation_id,
        payload={"client_platform": upload.client_platform},
    )
    await db.commit()
    await db.refresh(upload)
    return upload_service.to_out(upload)


@router.post("/sessions", response_model=UploadSessionOut, status_code=status.HTTP_201_CREATED)
async def create_upload_session(
    payload: CreateUploadSessionRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> UploadSessionOut:
    if payload.conversation_id is not None:
        await upload_service.assert_conversation_owner(
            db,
            user_id=user.id,
            conversation_id=payload.conversation_id,
        )
    session = await resumable_upload_service.create(db, user_id=user.id, payload=payload)
    await db.commit()
    await db.refresh(session)
    return resumable_upload_service.to_out(session)


@router.get("/sessions/{session_id}", response_model=UploadSessionOut)
async def get_upload_session(
    session_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> UploadSessionOut:
    session = await resumable_upload_service.get_owned(
        db,
        user_id=user.id,
        session_id=session_id,
    )
    return resumable_upload_service.to_out(session)


@router.put("/sessions/{session_id}/parts/{part_number}", response_model=UploadSessionOut)
async def put_upload_session_part(
    session_id: UUID,
    part_number: int,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    body: Annotated[bytes, Body(media_type="application/octet-stream")],
) -> UploadSessionOut:
    session = await resumable_upload_service.put_part(
        db,
        user_id=user.id,
        session_id=session_id,
        part_number=part_number,
        data=body,
    )
    await db.commit()
    await db.refresh(session)
    return resumable_upload_service.to_out(session)


@router.post("/sessions/{session_id}/complete")
async def complete_upload_session(
    session_id: UUID,
    payload: CompleteUploadSessionRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> CompleteUploadSessionResponse:
    session, upload = await resumable_upload_service.complete(
        db,
        user_id=user.id,
        session_id=session_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(session)
    return CompleteUploadSessionResponse(
        session=resumable_upload_service.to_out(session),
        upload=upload,
    )


@router.delete("/sessions/{session_id}", response_model=UploadSessionOut)
async def cancel_upload_session(
    session_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> UploadSessionOut:
    session = await resumable_upload_service.cancel(db, user_id=user.id, session_id=session_id)
    await db.commit()
    await db.refresh(session)
    return resumable_upload_service.to_out(session)


@router.get("/{upload_id}", response_model=UploadOut)
async def get_upload(
    upload_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> UploadOut:
    upload = await upload_service.get_owned_upload(db, user_id=user.id, upload_id=upload_id)
    return upload_service.to_out(upload)


@router.get("/{upload_id}/download")
async def download_upload(
    upload_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    upload = await upload_service.get_owned_upload(db, user_id=user.id, upload_id=upload_id)
    path = upload_service.download_path(upload)
    return FileResponse(
        path,
        filename=upload.filename,
        media_type=upload.detected_content_type or upload.content_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_upload(
    upload_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    upload = await upload_service.get_owned_upload(db, user_id=user.id, upload_id=upload_id)
    await upload_service.delete_upload(db, upload)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
