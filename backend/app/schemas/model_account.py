"""Schemas for user model accounts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ModelProvider = Literal["deepseek", "openai", "anthropic", "openai_compatible"]
ModelProtocol = Literal["openai_compatible", "anthropic"]
ModelAccountStatus = Literal["unverified", "ready", "unavailable"]


class ModelProviderOut(BaseModel):
    provider: ModelProvider
    company_name: str
    protocol: ModelProtocol
    default_model: str
    models: list[str] = Field(default_factory=list)
    requires_base_url: bool = False
    default_base_url: str | None = None


class ModelProviderListOut(BaseModel):
    items: list[ModelProviderOut] = Field(default_factory=list)


class ModelAccountOut(BaseModel):
    id: UUID
    display_name: str
    provider: ModelProvider
    protocol: ModelProtocol
    model: str
    base_url: str | None = None
    api_key_preview: str
    status: ModelAccountStatus
    last_verified_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelAccountListOut(BaseModel):
    items: list[ModelAccountOut] = Field(default_factory=list)


class CreateModelAccountRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider: ModelProvider
    api_key: str = Field(min_length=1, max_length=4096)
    model: str = Field(min_length=1, max_length=160)
    base_url: str | None = Field(default=None, max_length=512)

    @field_validator("display_name", "api_key", "model", "base_url")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class UpdateModelAccountRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    model: str | None = Field(default=None, min_length=1, max_length=160)
    base_url: str | None = Field(default=None, max_length=512)

    @field_validator("display_name", "api_key", "model", "base_url")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class ModelAccountVerifyOut(BaseModel):
    status: ModelAccountStatus
    error: str | None = None
    verified_at: datetime | None = None
