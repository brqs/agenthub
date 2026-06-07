"""Upload routes — Owner: B1."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.core.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.upload import UploadOut, UploadPurpose
from app.services.upload_service import upload_service

router = APIRouter()


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def create_upload(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    purpose: Annotated[UploadPurpose, Form()] = "message_attachment",
    conversation_id: Annotated[UUID | None, Form()] = None,
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
    )
    await db.commit()
    await db.refresh(upload)
    return upload_service.to_out(upload)


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
