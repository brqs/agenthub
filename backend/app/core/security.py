"""JWT and password hashing utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: UUID) -> tuple[str, int]:
    """Create a JWT and return (token, expires_in_seconds)."""
    expire_delta = timedelta(days=settings.jwt_expire_days)
    expire = datetime.now(UTC) + expire_delta
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expire_delta.total_seconds())


def decode_access_token(token: str) -> UUID:
    """Decode a JWT and return the user_id. Raises JWTError if invalid."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise JWTError("Invalid token: missing sub")
    return UUID(sub)
