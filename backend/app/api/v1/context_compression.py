"""Context compression configuration routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.conversation import (
    ContextCompressionConfigOut,
    ContextCompressionTestOut,
    ContextCompressionTestRequest,
    UpdateContextCompressionConfigRequest,
)
from app.services.model_gateway import (
    SUPPORTED_COMPRESSION_MODELS,
    CompressionModelGateway,
    ModelGatewayUnavailableError,
    default_compression_base_url,
    effective_compression_api_key,
    effective_compression_base_url,
    effective_compression_model,
    effective_compression_provider,
    normalize_compression_provider,
)

router = APIRouter()


def _api_key_source() -> str:
    if settings.context_compression_api_key:
        return "context_compression_api_key"
    return "missing"


def _mask_api_key(api_key: str) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"


def _compression_config_out() -> ContextCompressionConfigOut:
    provider = effective_compression_provider()
    api_key = effective_compression_api_key(provider)
    base_url = effective_compression_base_url(provider) or default_compression_base_url(provider)
    return ContextCompressionConfigOut(
        mode=settings.context_compression_mode,
        provider=provider,
        model=effective_compression_model(),
        summary_max_tokens=settings.context_summary_max_tokens,
        recent_raw_keep=settings.context_recent_raw_keep,
        api_key_configured=bool(api_key),
        api_key_source=_api_key_source(),
        api_key_preview=_mask_api_key(api_key),
        base_url=base_url,
        supported_models=SUPPORTED_COMPRESSION_MODELS.get(provider, []),
    )


def _require_development() -> None:
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Not found"}},
        )


@router.get("/config", response_model=ContextCompressionConfigOut)
async def get_context_compression_config(
    user: Annotated[User, Depends(get_current_user)],
) -> ContextCompressionConfigOut:
    """Return the active context compression config without exposing API keys."""
    _ = user
    return _compression_config_out()


@router.patch("/config", response_model=ContextCompressionConfigOut)
async def update_context_compression_config(
    payload: UpdateContextCompressionConfigRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ContextCompressionConfigOut:
    """Temporarily update compression model settings for local development."""
    _ = user
    _require_development()
    provider = normalize_compression_provider(
        payload.provider or effective_compression_provider()
    )
    model = payload.model or effective_compression_model()
    supported_models = SUPPORTED_COMPRESSION_MODELS.get(provider)
    if supported_models is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "UNSUPPORTED_COMPRESSION_PROVIDER",
                    "message": "Unsupported context compression provider",
                    "details": {"supported_providers": list(SUPPORTED_COMPRESSION_MODELS)},
                }
            },
        )
    if provider != "openai_compatible" and model not in supported_models:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "UNSUPPORTED_COMPRESSION_MODEL",
                    "message": "Unsupported context summarizer model",
                    "details": {"supported_models": supported_models},
                }
            },
        )
    if provider == "openai_compatible" and not (
        payload.base_url or effective_compression_base_url(provider)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "MISSING_COMPRESSION_BASE_URL",
                    "message": "openai_compatible provider requires base_url",
                }
            },
        )

    if payload.mode is not None:
        settings.context_compression_mode = payload.mode
    if payload.provider is not None:
        settings.context_compression_provider = provider
    if payload.model is not None:
        settings.context_compression_model = payload.model
    if payload.api_key is not None:
        settings.context_compression_api_key = payload.api_key
    if payload.base_url is not None:
        settings.context_compression_base_url = payload.base_url
    if payload.summary_max_tokens is not None:
        settings.context_summary_max_tokens = payload.summary_max_tokens
    if payload.recent_raw_keep is not None:
        settings.context_recent_raw_keep = payload.recent_raw_keep

    return _compression_config_out()


@router.post("/config/test", response_model=ContextCompressionTestOut)
async def test_context_compression_config(
    payload: ContextCompressionTestRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ContextCompressionTestOut:
    """Verify a compression provider/model/key/base_url combination."""
    _ = user
    _require_development()
    provider = normalize_compression_provider(
        payload.provider or effective_compression_provider()
    )
    model = payload.model or effective_compression_model()
    try:
        await CompressionModelGateway().test_connection(
            provider=provider,
            model=model,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
    except ModelGatewayUnavailableError as exc:
        return ContextCompressionTestOut(
            ok=False,
            provider=provider,
            model=model,
            error_code="compression_connection_failed",
            message=str(exc),
        )
    return ContextCompressionTestOut(ok=True, provider=provider, model=model)
