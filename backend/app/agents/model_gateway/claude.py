"""Claude raw model backend for ModelGateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import anthropic

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

DEFAULT_TOOL_INPUT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


class ClaudeBackend:
    """Anthropic Claude backend used by BuiltinAgent through ModelGateway."""

    provider = "claude"

    def __init__(
        self,
        agent_id: str = "model-gateway-claude",
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.default_config = default_config or {}

    def _settings(self) -> Any:
        return settings

    def _anthropic_module(self) -> Any:
        return anthropic

    def _create_client(self) -> Any:
        """Build an async Anthropic client from settings."""
        current_settings = self._settings()
        runtime_key = self.default_config.get("_runtime_api_key")
        api_key = (
            runtime_key
            if isinstance(runtime_key, str) and runtime_key
            else current_settings.anthropic_api_key
        )
        kwargs: dict[str, Any] = {"api_key": api_key}
        runtime_base_url = self.default_config.get("_runtime_base_url")
        base_url = (
            runtime_base_url
            if isinstance(runtime_base_url, str) and runtime_base_url
            else current_settings.anthropic_base_url
        )
        if base_url:
            kwargs["base_url"] = base_url
        return self._anthropic_module().AsyncAnthropic(**kwargs)

    def _provider_error_classes(self) -> ProviderErrorClasses:
        anthropic_module = self._anthropic_module()
        return ProviderErrorClasses(
            rate_limit=exception_classes(getattr(anthropic_module, "RateLimitError", None)),
            timeout=exception_classes(getattr(anthropic_module, "APITimeoutError", None)),
            connection=exception_classes(getattr(anthropic_module, "APIConnectionError", None)),
            api=exception_classes(getattr(anthropic_module, "APIError", None)),
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

    def _anthropic_tools(self, tools: list[ToolSpec] | None) -> list[dict[str, Any]]:
        if not tools:
            return []
        anthropic_tools: list[dict[str, Any]] = []
        for tool in tools:
            entry: dict[str, Any] = {
                "name": tool.name,
                "input_schema": tool.parameters or DEFAULT_TOOL_INPUT_SCHEMA,
            }
            if tool.description:
                entry["description"] = tool.description
            anthropic_tools.append(entry)
        return anthropic_tools

    async def _open_stream_with_retries(
        self,
        client: Any,
        stream_kwargs: dict[str, Any],
        resilience: ResilienceConfig,
    ) -> tuple[Any | None, Any | None, StreamChunk | None, int]:
        error_classes = self._provider_error_classes()
        max_attempts = resilience.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                stream_manager = client.messages.stream(**stream_kwargs)
                stream = await asyncio.wait_for(
                    stream_manager.__aenter__(),
                    timeout=resilience.request_timeout_seconds,
                )
                return stream_manager, stream, None, attempt
            except Exception as exc:
                error_code = classify_exception(exc, error_classes)
                retryable = is_retryable_error(error_code, resilience)
                if retryable and attempt <= resilience.max_retries:
                    await sleep_before_retry(resilience, attempt)
                    continue
                return (
                    None,
                    None,
                    self._error_chunk(
                        error_code=error_code,
                        error=safe_error_message(exc),
                        attempts=attempt,
                        retryable=retryable,
                    ),
                    attempt,
                )

        return None, None, None, max_attempts

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
        model = merged.get("model") or "claude-sonnet-4-6"
        temperature = merged.get("temperature")
        if temperature is None:
            temperature = 0.7
        max_tokens = merged.get("max_tokens")
        if max_tokens is None:
            max_tokens = 4096

        effective_system = self.effective_system_prompt(system_prompt) or ""

        anthropic_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                if effective_system:
                    effective_system += "\n" + msg.content
                else:
                    effective_system = msg.content
            elif msg.content:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

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

        runtime_key = self.default_config.get("_runtime_api_key")
        configured_key = (
            runtime_key
            if isinstance(runtime_key, str) and runtime_key
            else self._settings().anthropic_api_key
        )
        if not configured_key:
            yield self._error_chunk(
                error_code="missing_api_key",
                error="Anthropic API key is not configured",
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
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
        }
        if effective_system:
            stream_kwargs["system"] = effective_system
        anthropic_tools = self._anthropic_tools(tools)
        if anthropic_tools:
            stream_kwargs["tools"] = anthropic_tools
            tool_choice = merged.get("tool_choice")
            if isinstance(tool_choice, dict):
                stream_kwargs["tool_choice"] = tool_choice

        stream_manager, stream, setup_error, attempts = await self._open_stream_with_retries(
            client,
            stream_kwargs,
            resilience,
        )
        if setup_error is not None:
            yield setup_error
            return
        if stream_manager is None or stream is None:
            yield self._error_chunk(
                error_code="upstream_error",
                error="Anthropic stream was not opened",
                attempts=attempts,
                retryable=False,
            )
            return

        stream_closed = False

        async def close_stream_once(exc: BaseException | None = None) -> None:
            nonlocal stream_closed
            if stream_closed:
                return

            stream_closed = True
            if exc is None:
                await stream_manager.__aexit__(None, None, None)
                return

            await stream_manager.__aexit__(
                type(exc),
                exc,
                exc.__traceback__,
            )

        stream_error: BaseException | None = None
        try:
            try:
                if anthropic_tools and hasattr(stream, "__aiter__"):
                    async for chunk in self._stream_tool_events(stream, parser):
                        yield chunk
                else:
                    async for text in stream.text_stream:
                        for chunk in parser.feed(text):
                            yield chunk
            except Exception as exc:
                stream_error = exc
                for chunk in parser.flush():
                    yield chunk

                error_code = classify_exception(exc, self._provider_error_classes())
                yield self._error_chunk(
                    error_code=error_code,
                    error=safe_error_message(exc),
                    attempts=attempts,
                    retryable=False,
                )
                return

            for chunk in parser.flush():
                yield chunk

            try:
                await close_stream_once()
            except Exception as exc:
                error_code = classify_exception(exc, self._provider_error_classes())
                yield self._error_chunk(
                    error_code=error_code,
                    error=safe_error_message(exc),
                    attempts=attempts,
                    retryable=False,
                )
                return

            total_blocks = parser.block_index + 1 if parser.block_index >= 0 else 0
            yield StreamChunk(
                event_type="done",
                agent_id=self.agent_id,
                total_blocks=total_blocks,
            )
        finally:
            if not stream_closed:
                try:
                    await close_stream_once(stream_error)
                except Exception as cleanup_exc:
                    _ = cleanup_exc

    async def _stream_tool_events(
        self,
        stream: Any,
        parser: StreamingArtifactParser,
    ) -> AsyncIterator[StreamChunk]:
        tool_buffers: dict[int, dict[str, Any]] = {}
        async for event in stream:
            event_type = _string_attr(event, "type")
            index = _int_attr(event, "index")
            if event_type == "content_block_start":
                content_block = getattr(event, "content_block", None)
                block_type = _string_attr(content_block, "type")
                if block_type == "text":
                    text = _string_attr(content_block, "text")
                    if text:
                        for chunk in parser.feed(text):
                            yield chunk
                elif block_type == "tool_use" and index is not None:
                    tool_buffers[index] = {
                        "id": _string_attr(content_block, "id") or f"tool-{index}",
                        "name": _string_attr(content_block, "name") or "unknown_tool",
                        "input": _dict_attr(content_block, "input"),
                        "json_parts": [],
                    }
            elif event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                delta_type = _string_attr(delta, "type")
                if delta_type == "text_delta":
                    text = _string_attr(delta, "text")
                    if text:
                        for chunk in parser.feed(text):
                            yield chunk
                elif delta_type == "input_json_delta" and index in tool_buffers:
                    partial_json = _string_attr(delta, "partial_json")
                    if partial_json:
                        cast(list[str], tool_buffers[index]["json_parts"]).append(
                            partial_json
                        )
            elif event_type == "content_block_stop" and index in tool_buffers:
                tool = tool_buffers.pop(index)
                for chunk in parser.flush():
                    yield chunk
                yield StreamChunk(
                    event_type="tool_call",
                    agent_id=self.agent_id,
                    call_id=cast(str, tool["id"]),
                    tool_name=cast(str, tool["name"]),
                    tool_arguments=_tool_arguments(
                        cast(dict[str, Any] | None, tool["input"]),
                        cast(list[str], tool["json_parts"]),
                    ),
                )


def _string_attr(value: Any, name: str) -> str | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, str) else None


def _int_attr(value: Any, name: str) -> int | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, int) else None


def _dict_attr(value: Any, name: str) -> dict[str, Any] | None:
    attr = getattr(value, name, None)
    return dict(attr) if isinstance(attr, dict) else None


def _tool_arguments(
    initial_input: dict[str, Any] | None,
    json_parts: list[str],
) -> dict[str, Any]:
    raw_json = "".join(json_parts).strip()
    if raw_json:
        try:
            decoded = json.loads(raw_json)
        except json.JSONDecodeError:
            return {"_raw_input": raw_json}
        if isinstance(decoded, dict):
            return decoded
        return {"_value": decoded}
    return initial_input or {}
