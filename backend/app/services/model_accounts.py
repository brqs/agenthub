"""Model provider/account helpers for custom Agents."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_gateway import ModelGateway
from app.agents.types import ChatMessage
from app.core.config import settings
from app.models.agent import Agent
from app.models.model_account import UserModelAccount
from app.schemas.model_account import ModelProviderOut


@dataclass(frozen=True)
class ProviderDefinition:
    provider: str
    company_name: str
    protocol: str
    default_model: str
    models: tuple[str, ...]
    requires_base_url: bool = False
    default_base_url: str | None = None


PROVIDERS: dict[str, ProviderDefinition] = {
    "deepseek": ProviderDefinition(
        provider="deepseek",
        company_name="DeepSeek",
        protocol="openai_compatible",
        default_model="deepseek-v4-flash",
        models=(
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
        ),
        default_base_url="https://api.deepseek.com",
    ),
    "openai": ProviderDefinition(
        provider="openai",
        company_name="OpenAI",
        protocol="openai_compatible",
        default_model="gpt-5.4-mini",
        models=(
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-5.2",
            "gpt-5.2-pro",
            "gpt-5.1",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "o3-pro",
            "o3",
            "o4-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
        ),
    ),
    "anthropic": ProviderDefinition(
        provider="anthropic",
        company_name="Anthropic Claude",
        protocol="anthropic",
        default_model="claude-sonnet-4-6",
        models=(
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-haiku-4-5-20251001",
        ),
    ),
    "openai_compatible": ProviderDefinition(
        provider="openai_compatible",
        company_name="OpenAI 兼容接口",
        protocol="openai_compatible",
        default_model="custom",
        models=("custom",),
        requires_base_url=True,
    ),
}


def provider_list() -> list[ModelProviderOut]:
    return [
        ModelProviderOut(
            provider=definition.provider,  # type: ignore[arg-type]
            company_name=definition.company_name,
            protocol=definition.protocol,  # type: ignore[arg-type]
            default_model=definition.default_model,
            models=list(definition.models),
            requires_base_url=definition.requires_base_url,
            default_base_url=definition.default_base_url,
        )
        for definition in PROVIDERS.values()
    ]


def provider_definition(provider: str) -> ProviderDefinition:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported model provider: {provider}") from exc


def backend_for_provider(provider: str) -> str:
    if provider == "anthropic":
        return "claude"
    if provider == "deepseek":
        return "deepseek"
    return "openai"


def model_profile_for_default() -> dict[str, Any]:
    return {
        "source": "agenthub_default",
        "provider": "deepseek",
        "model": PROVIDERS["deepseek"].default_model,
    }


def _fernet() -> Fernet:
    raw_key = settings.model_account_encryption_key.strip()
    if raw_key:
        return Fernet(raw_key.encode("utf-8"))
    digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_api_key: str) -> str:
    return _fernet().decrypt(encrypted_api_key.encode("utf-8")).decode("utf-8")


def api_key_preview(api_key: str) -> str:
    trimmed = api_key.strip()
    if len(trimmed) <= 8:
        return "***" + trimmed[-4:]
    return f"{trimmed[:3]}***{trimmed[-4:]}"


def validate_provider_payload(provider: str, base_url: str | None) -> ProviderDefinition:
    definition = provider_definition(provider)
    if definition.requires_base_url and not (base_url or "").strip():
        raise ValueError("base_url is required for OpenAI-compatible model providers")
    return definition


async def create_model_account(
    db: AsyncSession,
    *,
    user_id: UUID,
    display_name: str,
    provider: str,
    api_key: str,
    model: str,
    base_url: str | None,
) -> UserModelAccount:
    definition = validate_provider_payload(provider, base_url)
    account = UserModelAccount(
        user_id=user_id,
        display_name=display_name,
        provider=definition.provider,
        protocol=definition.protocol,
        model=model,
        base_url=(base_url or definition.default_base_url or None),
        encrypted_api_key=encrypt_api_key(api_key),
        api_key_preview=api_key_preview(api_key),
        status="unverified",
    )
    db.add(account)
    await db.flush()
    return account


async def list_model_accounts(db: AsyncSession, *, user_id: UUID) -> list[UserModelAccount]:
    result = await db.execute(
        select(UserModelAccount)
        .where(UserModelAccount.user_id == user_id)
        .order_by(UserModelAccount.created_at.desc(), UserModelAccount.id.desc())
    )
    return list(result.scalars().all())


async def get_user_model_account(
    db: AsyncSession,
    *,
    user_id: UUID,
    account_id: UUID,
) -> UserModelAccount | None:
    account = await db.get(UserModelAccount, account_id)
    if account is None or account.user_id != user_id:
        return None
    return account


async def update_model_account(
    db: AsyncSession,
    account: UserModelAccount,
    *,
    display_name: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> UserModelAccount:
    if display_name is not None:
        account.display_name = display_name
    if model is not None:
        account.model = model
    if base_url is not None:
        validate_provider_payload(account.provider, base_url)
        account.base_url = base_url or None
    if api_key is not None:
        account.encrypted_api_key = encrypt_api_key(api_key)
        account.api_key_preview = api_key_preview(api_key)
        account.status = "unverified"
        account.last_error = None
        account.last_verified_at = None
    await db.flush()
    return account


async def account_is_used_by_agent(db: AsyncSession, *, user_id: UUID, account_id: UUID) -> bool:
    account_id_text = str(account_id)
    result = await db.execute(
        select(Agent.id).where(
            Agent.user_id == user_id,
            Agent.config["model_profile"]["account_id"].astext == account_id_text,
        )
    )
    return result.first() is not None


def runtime_config_for_account(account: UserModelAccount) -> dict[str, Any]:
    config: dict[str, Any] = {
        "model": account.model,
        "_runtime_api_key": decrypt_api_key(account.encrypted_api_key),
    }
    if account.base_url:
        config["_runtime_base_url"] = account.base_url
    return config


def unavailable_runtime_config(profile: dict[str, Any], reason: str) -> dict[str, Any]:
    provider = str(profile.get("provider") or "deepseek")
    if provider not in PROVIDERS:
        provider = "deepseek"
    model = profile.get("model")
    if not isinstance(model, str) or not model.strip():
        model = PROVIDERS[provider].default_model
    return {
        "model_backend": backend_for_provider(provider),
        "model": model,
        "_runtime_api_key": "",
        "_runtime_model_account_error": reason,
    }


async def resolve_agent_model_config(db: AsyncSession, agent: Agent) -> dict[str, Any]:
    config = dict(agent.config or {})
    if agent.provider != "builtin" or agent.user_id is None:
        return config
    profile = config.get("model_profile")
    if not isinstance(profile, dict) or profile.get("source") != "user_account":
        config.setdefault("model_profile", model_profile_for_default())
        return config
    raw_account_id = profile.get("account_id")
    try:
        account_id = UUID(str(raw_account_id))
    except (TypeError, ValueError):
        config.update(unavailable_runtime_config(profile, "Model account reference is invalid."))
        return config
    account = await get_user_model_account(db, user_id=agent.user_id, account_id=account_id)
    if account is None:
        config.update(unavailable_runtime_config(profile, "Model account was not found."))
        return config
    if account.status == "unavailable":
        reason = account.last_error or "Model account is unavailable."
        config.update(unavailable_runtime_config(profile, reason))
        return config
    config["model_backend"] = backend_for_provider(account.provider)
    config.update(runtime_config_for_account(account))
    return config


async def verify_model_account(account: UserModelAccount) -> tuple[str, str | None]:
    config = runtime_config_for_account(account)
    backend = backend_for_provider(account.provider)
    gateway = ModelGateway(
        backend,
        config,
        agent_id=f"model-account-{account.id}",
        system_prompt="Only answer with OK.",
    )
    text_seen = False
    async for chunk in gateway.stream(
        [ChatMessage(role="user", content="Reply with OK.")],
        config={"max_tokens": 16, "temperature": 0},
    ):
        if chunk.event_type == "error":
            return "unavailable", (chunk.error or "Model account verification failed.")[:500]
        if chunk.event_type in {"delta", "block_start", "block_end"}:
            text_seen = True
        if chunk.event_type == "done":
            return "ready", None
    return ("ready", None) if text_seen else ("unavailable", "Model account did not respond.")


async def persist_verification_result(
    db: AsyncSession,
    account: UserModelAccount,
    *,
    status: str,
    error: str | None,
) -> UserModelAccount:
    account.status = status
    account.last_error = error
    account.last_verified_at = datetime.now(UTC)
    await db.flush()
    return account
