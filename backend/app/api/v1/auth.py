"""Auth routes — Owner: B1."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.deps import DbSession, get_current_session_id, get_current_user
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    UpdateSessionRequest,
    UserOut,
    UserSessionList,
    UserSessionOut,
)
from app.services.session_service import session_service

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: RegisterRequest, db: DbSession, request: Request) -> AuthResponse:
    existing = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "USERNAME_TAKEN",
                    "message": "Username already exists",
                }
            },
        )

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    await db.flush()  # populate user.id

    token, refresh_token, expires_in, session = await session_service.create_session(
        db,
        user=user,
        device_name=payload.device_name,
        platform=payload.platform,
        request=request,
    )
    return AuthResponse(
        access_token=token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        session=UserSessionOut.model_validate(session).model_copy(update={"is_current": True}),
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: DbSession, request: Request) -> AuthResponse:
    user = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"}
            },
        )

    token, refresh_token, expires_in, session = await session_service.create_session(
        db,
        user=user,
        device_name=payload.device_name,
        platform=payload.platform,
        request=request,
    )
    return AuthResponse(
        access_token=token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        session=UserSessionOut.model_validate(session).model_copy(update={"is_current": True}),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(payload: RefreshTokenRequest, db: DbSession, request: Request) -> AuthResponse:
    user, token, refresh_token, expires_in, session = await session_service.refresh(
        db,
        refresh_token=payload.refresh_token,
        request=request,
    )
    return AuthResponse(
        access_token=token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        session=UserSessionOut.model_validate(session).model_copy(update={"is_current": True}),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    session_id: Annotated[str | None, Depends(get_current_session_id)],
) -> Response:
    await session_service.logout(
        db,
        user_id=user.id,
        session_id=UUID(session_id) if session_id else None,
        refresh_token=payload.refresh_token,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/sessions", response_model=UserSessionList)
async def list_sessions(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    session_id: Annotated[str | None, Depends(get_current_session_id)],
) -> UserSessionList:
    current = UUID(session_id) if session_id else None
    items = await session_service.list_sessions(db, user_id=user.id, current_session_id=current)
    return UserSessionList(items=items, total=len(items))


@router.patch("/sessions/{session_id}", response_model=UserSessionOut)
async def update_session(
    session_id: UUID,
    payload: UpdateSessionRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    current_session_id: Annotated[str | None, Depends(get_current_session_id)],
) -> UserSessionOut:
    if payload.device_name is None:
        session = await session_service._owned_session(db, user_id=user.id, session_id=session_id)
    else:
        session = await session_service.rename_session(
            db,
            user_id=user.id,
            session_id=session_id,
            device_name=payload.device_name,
        )
    return UserSessionOut.model_validate(session).model_copy(
        update={"is_current": current_session_id == str(session.id)}
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await session_service.revoke_session(db, user_id=user.id, session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_other_sessions(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    session_id: Annotated[str | None, Depends(get_current_session_id)],
) -> Response:
    await session_service.revoke_other_sessions(
        db,
        user_id=user.id,
        current_session_id=UUID(session_id) if session_id else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
