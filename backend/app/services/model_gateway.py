"""Provider-agnostic model calls used by internal backend services."""

from __future__ import annotations

from typing import Any

import anthropic
import openai

from app.core.config import settings


class ModelGatewayUnavailableError(RuntimeError):
    """Raised when an internal model call cannot be completed."""


SUPPORTED_COMPRESSION_MODELS = {
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    "openai_compatible": ["custom"],
    "anthropic": ["claude-sonnet-4-6", "claude-haiku-4-5"],
}


def normalize_compression_provider(provider: str) -> str:
    """Normalize administrator-facing provider names to internal provider keys."""
    normalized = provider.strip().lower().replace("-", "_")
    if normalized == "claude":
        return "anthropic"
    return normalized


def effective_compression_provider() -> str:
    return normalize_compression_provider(settings.context_compression_provider)


def effective_compression_model() -> str:
    return settings.context_compression_model


def default_compression_base_url(provider: str) -> str:
    if provider == "deepseek":
        return "https://api.deepseek.com"
    return ""


def effective_compression_base_url(provider: str) -> str:
    if settings.context_compression_base_url:
        return settings.context_compression_base_url
    return default_compression_base_url(provider)


def effective_compression_api_key(provider: str) -> str:
    _ = provider
    return settings.context_compression_api_key


def has_configured_compression_api_key() -> bool:
    return bool(effective_compression_api_key(effective_compression_provider()))


class CompressionModelGateway:
    """Model gateway for non-streaming context compression calls."""

    def _provider(self) -> str:
        return effective_compression_provider()

    def _model(self) -> str:
        return effective_compression_model()

    def _api_key(self) -> str:
        return effective_compression_api_key(self._provider())

    def _base_url(self) -> str:
        provider = self._provider()
        return effective_compression_base_url(provider) or default_compression_base_url(provider)

    async def complete(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        provider = self._provider()
        if provider not in SUPPORTED_COMPRESSION_MODELS:
            raise ModelGatewayUnavailableError("unsupported compression provider")
        api_key = self._api_key()
        if not api_key:
            raise ModelGatewayUnavailableError("missing compression API key")
        if provider in {"deepseek", "openai", "openai_compatible"}:
            return await self._complete_openai_compatible(
                provider=provider,
                api_key=api_key,
                base_url=self._base_url(),
                model=self._model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
            )
        return await self._complete_anthropic(
            api_key=api_key,
            base_url=self._base_url(),
            model=self._model(),
            system=system,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )

    async def test_connection(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> str:
        """Send a tiny request to verify that a model config works."""
        normalized_provider = normalize_compression_provider(provider or self._provider())
        effective_key = api_key or effective_compression_api_key(normalized_provider)
        effective_model = model or self._model()
        effective_base_url = (
            base_url
            if base_url is not None
            else effective_compression_base_url(normalized_provider)
            or default_compression_base_url(normalized_provider)
        )
        if not effective_key:
            raise ModelGatewayUnavailableError("missing compression API key")
        if normalized_provider in {"deepseek", "openai", "openai_compatible"}:
            return await self._complete_openai_compatible(
                provider=normalized_provider,
                api_key=effective_key,
                base_url=effective_base_url,
                model=effective_model,
                messages=[
                    {"role": "system", "content": "Reply with exactly: ok"},
                    {"role": "user", "content": "health check"},
                ],
                max_tokens=8,
            )
        return await self._complete_anthropic(
            api_key=effective_key,
            base_url=effective_base_url,
            model=effective_model,
            system="Reply with exactly: ok",
            user_prompt="health check",
            max_tokens=8,
        )

    async def _complete_openai_compatible(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> str:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if provider == "openai_compatible" and not base_url:
            raise ModelGatewayUnavailableError("openai_compatible requires base_url")

        client = openai.AsyncOpenAI(**kwargs)
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
                stream=False,
            )
        except openai.OpenAIError as exc:
            raise ModelGatewayUnavailableError(str(exc)) from exc

        content = response.choices[0].message.content if response.choices else ""
        if not content:
            raise ModelGatewayUnavailableError("empty compression response")
        return content

    async def _complete_anthropic(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        system: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = anthropic.AsyncAnthropic(**kwargs)
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise ModelGatewayUnavailableError(str(exc)) from exc

        content_parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        ]
        content = "\n".join(content_parts)
        if not content:
            raise ModelGatewayUnavailableError("empty compression response")
        return content
