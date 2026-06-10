"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token, decode_access_token_payload

if TYPE_CHECKING:
    from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    """Resolve current user from JWT.

    Returns app.models.user.User. Import deferred to avoid circular import.
    """
    from app.models.user import User  # local import

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Missing token"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = decode_access_token(credentials.credentials)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": str(e)}},
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found"}},
        )
    return user


async def get_current_session_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str | None:
    if not credentials:
        return None
    try:
        payload = decode_access_token_payload(credentials.credentials)
    except JWTError:
        return None
    sid = payload.get("sid")
    return sid if isinstance(sid, str) else None
