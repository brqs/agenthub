"""Refresh-token backed user session management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_refresh_token
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import UserSessionOut
from app.services.audit_service import record_audit_event
from app.services.event_service import event_service


class SessionService:
    async def create_session(
        self,
        db: AsyncSession,
        *,
        user: User,
        device_name: str | None,
        platform: str,
        request: Request | None,
    ) -> tuple[str, str, int, UserSession]:
        refresh_token = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            device_name=(device_name or _default_device_name(platform)).strip()[:160],
            platform=platform,
            user_agent=_request_header(request, "user-agent"),
            ip_address=_client_ip(request),
            expires_at=expires_at,
        )
        db.add(session)
        await db.flush()
        access_token, access_expires_in = create_access_token(user.id, session.id)
        await record_audit_event(
            db,
            user_id=user.id,
            action="auth.session_created",
            resource_type="user_session",
            resource_id=str(session.id),
            metadata={"platform": platform},
            ip_address=session.ip_address,
            user_agent=session.user_agent,
        )
        await event_service.record(
            db,
            user_id=user.id,
            event_type="auth.session_created",
            resource_type="user_session",
            resource_id=session.id,
            payload={"platform": platform},
        )
        return access_token, refresh_token, access_expires_in, session

    async def refresh(
        self,
        db: AsyncSession,
        *,
        refresh_token: str,
        request: Request | None,
    ) -> tuple[User, str, str, int, UserSession]:
        session = await self._active_session_by_refresh(db, refresh_token)
        user = await db.get(User, session.user_id)
        if user is None:
            raise _auth_error("USER_NOT_FOUND", "User not found")
        new_refresh = create_refresh_token()
        session.refresh_token_hash = hash_refresh_token(new_refresh)
        session.last_active_at = datetime.now(UTC)
        session.user_agent = _request_header(request, "user-agent") or session.user_agent
        session.ip_address = _client_ip(request) or session.ip_address
        access_token, access_expires_in = create_access_token(user.id, session.id)
        await record_audit_event(
            db,
            user_id=user.id,
            action="auth.session_refreshed",
            resource_type="user_session",
            resource_id=str(session.id),
            ip_address=session.ip_address,
            user_agent=session.user_agent,
        )
        await event_service.record(
            db,
            user_id=user.id,
            event_type="auth.session_refreshed",
            resource_type="user_session",
            resource_id=session.id,
        )
        return user, access_token, new_refresh, access_expires_in, session

    async def logout(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID | None,
        refresh_token: str | None,
    ) -> None:
        session: UserSession | None = None
        if refresh_token:
            session = await self._session_by_refresh(db, refresh_token)
        elif session_id is not None:
            session = await db.get(UserSession, session_id)
        if session is not None and session.user_id == user_id and session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            session.revoked_reason = "logout"
            await record_audit_event(
                db,
                user_id=user_id,
                action="auth.session_revoked",
                resource_type="user_session",
                resource_id=str(session.id),
                metadata={"reason": "logout"},
            )
            await event_service.record(
                db,
                user_id=user_id,
                event_type="auth.session_revoked",
                resource_type="user_session",
                resource_id=session.id,
                payload={"reason": "logout"},
            )

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        current_session_id: UUID | None,
    ) -> list[UserSessionOut]:
        rows = (
            await db.execute(
                select(UserSession)
                .where(UserSession.user_id == user_id)
                .order_by(desc(UserSession.last_active_at))
            )
        ).scalars().all()
        return [
            UserSessionOut.model_validate(row).model_copy(
                update={
                    "is_current": current_session_id is not None and row.id == current_session_id
                }
            )
            for row in rows
        ]

    async def rename_session(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
        device_name: str,
    ) -> UserSession:
        session = await self._owned_session(db, user_id=user_id, session_id=session_id)
        session.device_name = device_name.strip()[:160]
        await db.flush()
        return session

    async def revoke_session(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
        reason: str = "remote_logout",
    ) -> None:
        session = await self._owned_session(db, user_id=user_id, session_id=session_id)
        if session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            session.revoked_reason = reason
            await record_audit_event(
                db,
                user_id=user_id,
                action="auth.session_revoked",
                resource_type="user_session",
                resource_id=str(session.id),
                metadata={"reason": reason},
            )
            await event_service.record(
                db,
                user_id=user_id,
                event_type="auth.session_revoked",
                resource_type="user_session",
                resource_id=session.id,
                payload={"reason": reason},
            )

    async def revoke_other_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        current_session_id: UUID | None,
    ) -> int:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
        )
        if current_session_id is not None:
            stmt = stmt.where(UserSession.id != current_session_id)
        result = await db.execute(
            stmt.values(revoked_at=datetime.now(UTC), revoked_reason="remote_logout_all")
        )
        await record_audit_event(
            db,
            user_id=user_id,
            action="auth.other_sessions_revoked",
            resource_type="user_session",
            metadata={"count": int(result.rowcount or 0)},
        )
        await event_service.record(
            db,
            user_id=user_id,
            event_type="auth.other_sessions_revoked",
            resource_type="user_session",
            resource_id=str(user_id),
            payload={"count": int(result.rowcount or 0)},
        )
        return int(result.rowcount or 0)

    async def _owned_session(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> UserSession:
        session = await db.get(UserSession, session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}},
            )
        return session

    async def _active_session_by_refresh(
        self,
        db: AsyncSession,
        refresh_token: str,
    ) -> UserSession:
        session = await self._session_by_refresh(db, refresh_token)
        now = datetime.now(UTC)
        if session.revoked_at is not None:
            raise _auth_error("SESSION_REVOKED", "Session has been revoked")
        if session.expires_at <= now:
            raise _auth_error("SESSION_EXPIRED", "Session has expired")
        return session

    async def _session_by_refresh(
        self,
        db: AsyncSession,
        refresh_token: str,
    ) -> UserSession:
        token_hash = hash_refresh_token(refresh_token)
        session = (
            await db.execute(
                select(UserSession).where(UserSession.refresh_token_hash == token_hash)
            )
        ).scalar_one_or_none()
        if session is None:
            raise _auth_error("INVALID_REFRESH_TOKEN", "Invalid refresh token")
        return session


def _auth_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": code, "message": message}},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _request_header(request: Request | None, name: str) -> str | None:
    if request is None:
        return None
    value = request.headers.get(name)
    return value[:512] if value else None


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host[:64]


def _default_device_name(platform: str) -> str:
    return {
        "desktop": "Windows Desktop",
        "ios": "iOS",
        "android": "Android",
    }.get(platform, "Web Browser")


session_service = SessionService()
