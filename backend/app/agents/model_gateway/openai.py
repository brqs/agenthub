"""OpenAI-compatible raw model backend for ModelGateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import openai

from app.agents.artifact_parser import StreamingArtifactParser
from app.agents.model_gateway.resilience import (
    ProviderErrorClasses,
    ProviderErrorCode,
    ResilienceConfig,
    classify_exception,
    error_chunk,
    exception_classes,
    is_retryable_error,
    parse_resilience_config,
    safe_error_message,
    sleep_before_retry,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.core.config import settings

DEFAULT_TOOL_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}


class OpenAIBackend:
    """OpenAI-compatible backend used by BuiltinAgent through ModelGateway."""

    provider = "openai"
    default_model = "mimo-v2.5-pro"
    api_key_setting = "openai_api_key"
    base_url_setting = "openai_base_url"
    display_name = "OpenAI"

    def __init__(
        self,
        agent_id: str = "model-gateway-openai",
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.default_config = default_config or {}

    def _settings(self) -> Any:
        return settings

    def _openai_module(self) -> Any:
        return openai

    def _api_key(self) -> str:
        runtime_key = self.default_config.get("_runtime_api_key")
        if isinstance(runtime_key, str) and runtime_key:
            return runtime_key
        return str(getattr(self._settings(), self.api_key_setting))

    def _base_url(self) -> str:
        runtime_base_url = self.default_config.get("_runtime_base_url")
        if isinstance(runtime_base_url, str) and runtime_base_url:
            return runtime_base_url
        return str(getattr(self._settings(), self.base_url_setting))

    def _create_client(self) -> Any:
        """Build an async OpenAI-compatible client from settings."""
        kwargs: dict[str, Any] = {"api_key": self._api_key()}
        if self._base_url():
            kwargs["base_url"] = self._base_url()
        return self._openai_module().AsyncOpenAI(**kwargs)

    def _provider_error_classes(self) -> ProviderErrorClasses:
        openai_module = self._openai_module()
        return ProviderErrorClasses(
            rate_limit=exception_classes(getattr(openai_module, "RateLimitError", None)),
            timeout=exception_classes(getattr(openai_module, "APITimeoutError", None)),
            connection=exception_classes(getattr(openai_module, "APIConnectionError", None)),
            api=exception_classes(getattr(openai_module, "APIError", None)),
        )

    def _error_chunk(
        self,
        *,
        error_code: ProviderErrorCode,
        error: str,
        attempts: int,
        retryable: bool,
    ) -> StreamChunk:
        return error_chunk(
            agent_id=self.agent_id,
            provider=self.provider,
            error_code=error_code,
            error=error,
            attempts=attempts,
            retryable=retryable,
        )

    def merged_config(self, override: dict[str, Any] | None) -> dict[str, Any]:
        return {**self.default_config, **(override or {})}

    def effective_system_prompt(self, override: str | None) -> str | None:
        return override if override is not None else self.system_prompt

    def _openai_tools(self, tools: list[ToolSpec] | None) -> list[dict[str, Any]]:
        if not tools:
            return []
        openai_tools: list[dict[str, Any]] = []
        for tool in tools:
            function: dict[str, Any] = {
                "name": tool.name,
                "parameters": tool.parameters or DEFAULT_TOOL_PARAMETERS,
            }
            if tool.description:
                function["description"] = tool.description
            openai_tools.append({"type": "function", "function": function})
        return openai_tools

    async def _open_stream_with_retries(
        self,
        client: Any,
        stream_kwargs: dict[str, Any],
        resilience: ResilienceConfig,
    ) -> tuple[Any | None, StreamChunk | None, int]:
        error_classes = self._provider_error_classes()
        max_attempts = resilience.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                stream = await asyncio.wait_for(
                    client.chat.completions.create(**stream_kwargs),
                    timeout=resilience.request_timeout_seconds,
                )
                return stream, None, attempt
            except Exception as exc:
                error_code = classify_exception(exc, error_classes)
                retryable = is_retryable_error(error_code, resilience)
                if retryable and attempt <= resilience.max_retries:
                    await sleep_before_retry(resilience, attempt)
                    continue
                return (
                    None,
                    self._error_chunk(
                        error_code=error_code,
                        error=safe_error_message(exc),
                        attempts=attempt,
                        retryable=retryable,
                    ),
                    attempt,
                )

        return None, None, max_attempts

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)
        resilience = parse_resilience_config(merged)
        model = merged.get("model") or self.default_model
        temperature = merged.get("temperature")
        if temperature is None:
            temperature = 0.7
        max_tokens = merged.get("max_tokens")
        if max_tokens is None:
            max_tokens = 4096

        effective_system = self.effective_system_prompt(system_prompt) or ""

        openai_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                if effective_system:
                    effective_system += "\n" + msg.content
                else:
                    effective_system = msg.content
            elif msg.content:
                openai_messages.append({"role": msg.role, "content": msg.content})

        if effective_system:
            openai_messages.insert(0, {"role": "system", "content": effective_system})

        yield StreamChunk(event_type="start", agent_id=self.agent_id)

        runtime_account_error = merged.get("_runtime_model_account_error")
        if isinstance(runtime_account_error, str) and runtime_account_error.strip():
            yield self._error_chunk(
                error_code="missing_api_key",
                error=f"Model account is unavailable: {runtime_account_error.strip()}",
                attempts=0,
                retryable=False,
            )
            return

        if not self._api_key():
            yield self._error_chunk(
                error_code="missing_api_key",
                error=f"{self.display_name} API key is not configured",
                attempts=0,
                retryable=False,
            )
            return

        try:
            client = self._create_client()
        except Exception as exc:
            error_code = classify_exception(exc, self._provider_error_classes())
            yield self._error_chunk(
                error_code=error_code,
                error=safe_error_message(exc),
                attempts=0,
                retryable=False,
            )
            return

        parser = StreamingArtifactParser()

        stream_kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        openai_tools = self._openai_tools(tools)
        if openai_tools:
            stream_kwargs["tools"] = openai_tools
            tool_choice = _openai_tool_choice(merged.get("tool_choice"))
            if tool_choice is not None:
                stream_kwargs["tool_choice"] = tool_choice

        stream, setup_error, attempts = await self._open_stream_with_retries(
            client,
            stream_kwargs,
            resilience,
        )
        if setup_error is not None:
            yield setup_error
            return
        if stream is None:
            yield self._error_chunk(
                error_code="upstream_error",
                error=f"{self.display_name} stream was not opened",
                attempts=attempts,
                retryable=False,
            )
            return

        try:
            tool_buffers: dict[int, dict[str, Any]] = {}
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta_obj = chunk.choices[0].delta
                delta = _string_attr(delta_obj, "content")
                if delta:
                    for parser_chunk in parser.feed(delta):
                        yield parser_chunk
                for tool_call in _tool_calls(delta_obj):
                    _accumulate_tool_call(tool_buffers, tool_call)

            for parser_chunk in parser.flush():
                yield parser_chunk
            for tool_call in _completed_tool_calls(tool_buffers, self.agent_id):
                yield tool_call

            total_blocks = parser.block_index + 1 if parser.block_index >= 0 else 0
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=total_blocks,
            )
        except Exception as exc:
            for parser_chunk in parser.flush():
                yield parser_chunk

            error_code = classify_exception(exc, self._provider_error_classes())
            yield self._error_chunk(
                error_code=error_code,
                error=safe_error_message(exc),
                attempts=attempts,
                retryable=False,
            )


def _openai_tool_choice(value: object) -> object | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    raw_type = value.get("type")
    if raw_type == "auto":
        return "auto"
    if raw_type == "tool" and isinstance(value.get("name"), str):
        return {"type": "function", "function": {"name": value["name"]}}
    if raw_type == "function":
        return value
    return None


def _string_attr(value: Any, name: str) -> str | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, str) else None


def _int_attr(value: Any, name: str) -> int | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, int) else None


def _tool_calls(delta_obj: Any) -> list[Any]:
    calls = getattr(delta_obj, "tool_calls", None)
    return list(calls) if isinstance(calls, list) else []


def _accumulate_tool_call(tool_buffers: dict[int, dict[str, Any]], tool_call: Any) -> None:
    index = _int_attr(tool_call, "index")
    if index is None:
        index = len(tool_buffers)
    buffer = tool_buffers.setdefault(
        index,
        {"id": f"tool-{index}", "name": "unknown_tool", "arguments": []},
    )
    call_id = _string_attr(tool_call, "id")
    if call_id:
        buffer["id"] = call_id
    function = getattr(tool_call, "function", None)
    name = _string_attr(function, "name")
    if name:
        buffer["name"] = name
    arguments = _string_attr(function, "arguments")
    if arguments:
        cast(list[str], buffer["arguments"]).append(arguments)


def _completed_tool_calls(
    tool_buffers: dict[int, dict[str, Any]],
    agent_id: str,
) -> list[StreamChunk]:
    chunks: list[StreamChunk] = []
    for index in sorted(tool_buffers):
        tool = tool_buffers[index]
        chunks.append(
            StreamChunk(
                event_type="tool_call",
                agent_id=agent_id,
                call_id=cast(str, tool["id"]),
                tool_name=cast(str, tool["name"]),
                tool_arguments=_tool_arguments(cast(list[str], tool["arguments"])),
            )
        )
    return chunks


def _tool_arguments(json_parts: list[str]) -> dict[str, Any]:
    raw_json = "".join(json_parts).strip()
    if not raw_json:
        return {}
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError:
        return {"_raw_input": raw_json}
    if isinstance(decoded, dict):
        return decoded
    return {"_value": decoded}
