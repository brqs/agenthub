"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All app settings, loaded from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── Server ───
    environment: str = Field(default="development")
    host: str = Field(default="0.0.0.0")  # noqa: S104 - needed for Docker binding.
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # ─── Database ───
    database_url: str = Field(
        default="postgresql+asyncpg://agenthub:agenthub_dev_pw@localhost:5432/agenthub"
    )

    # ─── Redis ───
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ─── Auth ───
    jwt_secret: str = Field(default="change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_days: int = Field(default=7)

    # ─── AI Providers ───
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    anthropic_base_url: str = Field(default="")
    openai_base_url: str = Field(default="")

    # ─── CORS ───
    cors_origins: str = Field(default="http://localhost:5173")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Singleton settings accessor."""
    return Settings()


settings = get_settings()
