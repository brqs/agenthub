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
    model_account_encryption_key: str = Field(default="")
    allow_user_stdio_mcp_health_checks: bool = Field(default=False)

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

    # User uploads
    upload_storage_dir: str = Field(default="data/uploads")
    upload_max_file_bytes: int = Field(default=100_000_000)
    upload_preview_max_bytes: int = Field(default=1_048_576)

    # Workspace preview service
    preview_enabled: bool = Field(default=True)
    preview_port_start: int = Field(default=8082)
    preview_port_end: int = Field(default=8182)
    preview_public_base_url: str = Field(default="http://111.229.151.159")
    preview_allowed_frame_ancestors: str = Field(default="http://154.44.25.94:1573")
    preview_idle_ttl_seconds: int = Field(default=1800)
    preview_start_timeout_seconds: int = Field(default=15)
    preview_snapshot_dir: str = Field(
        default="/tmp/agenthub_preview_snapshots"  # noqa: S108 - generated previews.
    )

    # Workspace deployment / source export service
    deployment_enabled: bool = Field(default=True)
    deployment_export_dir: str = Field(
        default="/tmp/agenthub_workspace_exports"  # noqa: S108 - generated exports.
    )
    deployment_max_export_bytes: int = Field(default=25_000_000)
    deployment_max_file_count: int = Field(default=1000)
    deployment_max_single_file_bytes: int = Field(default=5_000_000)
    deployment_export_ttl_seconds: int = Field(default=86_400)
    deployment_janitor_interval_seconds: int = Field(default=300)
    deployment_public_base_url: str = Field(default="http://111.229.151.159:8000")
    deployment_static_root: str = Field(
        default="/tmp/agenthub_static_releases"  # noqa: S108 - generated releases.
    )
    deployment_release_token_bytes: int = Field(default=24)
    deployment_container_enabled: bool = Field(default=True)
    deployment_container_runtime: str = Field(default="podman")
    deployment_container_trusted_host_mode: bool = Field(default=False)
    deployment_container_public_base_url: str = Field(default="http://111.229.151.159")
    deployment_container_healthcheck_base_url: str = Field(default="")
    deployment_container_build_root: str = Field(
        default="/tmp/agenthub_container_deployments"  # noqa: S108 - generated deployments.
    )
    deployment_container_port_start: int = Field(default=8081)
    deployment_container_port_end: int = Field(default=8085)
    deployment_container_max_cpu: float = Field(default=1)
    deployment_container_max_memory_mb: int = Field(default=512)
    deployment_container_max_runtime_seconds: int = Field(default=3600)
    deployment_container_build_timeout_seconds: int = Field(default=180)
    deployment_container_run_timeout_seconds: int = Field(default=60)
    deployment_container_health_timeout_seconds: int = Field(default=30)
    deployment_container_health_retry_interval_seconds: float = Field(default=1)
    deployment_container_health_max_attempts: int = Field(default=30)
    deployment_container_health_backoff_multiplier: float = Field(default=1.5)
    deployment_container_log_tail_bytes: int = Field(default=20_000)

    # Shared static snapshot limits
    static_snapshot_max_file_count: int = Field(default=1000)
    static_snapshot_max_single_file_bytes: int = Field(default=5_000_000)
    static_snapshot_max_total_bytes: int = Field(default=25_000_000)

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
    orchestrator_subagent_text_visible_default: bool = Field(default=False)

    # External runtime isolation
    external_runtime_state_dir: str = Field(
        default="/tmp/agenthub_external_runtime"  # noqa: S108 - per-message runtime state.
    )
    agent_stream_stale_seconds: int = Field(default=900)
    agent_stream_idle_timeout_seconds: int = Field(default=60)
    agent_stream_hard_timeout_seconds: int = Field(default=900)

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
