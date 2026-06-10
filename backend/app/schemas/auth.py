"""Auth schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_BCRYPT_PASSWORD_BYTES = 72


def _validate_bcrypt_password_bytes(password: str) -> str:
    if len(password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password must be 72 bytes or fewer")
    return password


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    avatar_url: str | None = None
    created_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8)
    device_name: str | None = Field(default=None, max_length=160)
    platform: Literal["web", "desktop", "ios", "android"] = "web"

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, password: str) -> str:
        return _validate_bcrypt_password_bytes(password)


class LoginRequest(BaseModel):
    username: str
    password: str
    device_name: str | None = Field(default=None, max_length=160)
    platform: Literal["web", "desktop", "ios", "android"] = "web"

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, password: str) -> str:
        return _validate_bcrypt_password_bytes(password)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    session: UserSessionOut | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=512)


class UpdateSessionRequest(BaseModel):
    device_name: str | None = Field(default=None, min_length=1, max_length=160)


class UserSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_name: str
    platform: str
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    is_current: bool = False


class UserSessionList(BaseModel):
    items: list[UserSessionOut]
    total: int


AuthResponse.model_rebuild()
