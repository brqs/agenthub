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
    deepseek_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    anthropic_base_url: str = Field(default="")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    openai_base_url: str = Field(default="")

    # ─── Context Compression ───
    context_compression_mode: str = Field(default="hybrid")
    context_compression_provider: str = Field(default="deepseek")
    context_compression_model: str = Field(default="deepseek-v4-flash")
    context_compression_api_key: str = Field(default="")
    context_compression_base_url: str = Field(default="")
    context_summary_max_tokens: int = Field(default=1200)
    context_recent_raw_keep: int = Field(default=12)

    # Workspaces
    workspace_base_dir: str = Field(default="/workspaces")
    workspace_max_read_bytes: int = Field(default=1_048_576)

    # Workspace preview service
    preview_enabled: bool = Field(default=True)
    preview_port_start: int = Field(default=8082)
    preview_port_end: int = Field(default=8182)
    preview_public_base_url: str = Field(default="http://111.229.151.159")
    preview_idle_ttl_seconds: int = Field(default=1800)
    preview_start_timeout_seconds: int = Field(default=15)

    # Workspace deployment / source export service
    deployment_enabled: bool = Field(default=True)
    deployment_export_dir: str = Field(
        default="/tmp/agenthub_workspace_exports"  # noqa: S108 - generated exports.
    )
    deployment_max_export_bytes: int = Field(default=25_000_000)

    # Browser-level workspace preview verification
    browser_verify_enabled: bool = Field(default=True)
    browser_verify_timeout_seconds: int = Field(default=30)
    browser_verify_screenshot_dir: str = Field(
        default="/tmp/agenthub_browser_verify"  # noqa: S108 - browser reports are temp artifacts.
    )
    orchestrator_quality_max_repair_rounds: int = Field(default=2)
    orchestrator_quality_repair_agent_order: str = Field(
        default="codex-helper,claude-code,opencode-helper"
    )

    # Orchestrator default behavior. Built-in agent DB config may still override
    # these per deployment or per custom agent.
    orchestrator_llm_planning_default: bool = Field(default=True)
    orchestrator_parallel_enabled_default: bool = Field(default=True)
    orchestrator_parallel_max_concurrency_default: int = Field(default=3)

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
