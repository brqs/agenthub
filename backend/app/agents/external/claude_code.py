"""Claude Code external runtime adapter."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import AsyncIterator, Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, cast

from app.agents.base import BaseAgentAdapter
from app.agents.external.cli_runtime import run_cli_text
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

SDK_MODULE_NAME = "claude_agent_sdk"
DEFAULT_CLI_TIMEOUT_SECONDS = 120.0
TEXT_EVENT_NAMES = {"text", "text_block", "text_delta", "content_block_delta"}
TOOL_CALL_EVENT_NAMES = {"tool_call", "tool_use", "tool_start", "tooluseblock"}
TOOL_RESULT_EVENT_NAMES = {"tool_result", "tool_finish", "tool_end", "toolresultblock"}
SKIP_EVENT_NAMES = {"start", "done", "result", "system", "assistantmessage"}


class ClaudeCodeAdapter(BaseAgentAdapter):
    """Adapter for the Claude Code agent runtime SDK."""

    provider = "claude_code"

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id=self.agent_id)

        if workspace_path is None:
            yield self._error_chunk("workspace_violation", "workspace_path is required")
            return

        timeout_seconds = self._float_config(
            self.merged_config(config).get("timeout_seconds"),
            DEFAULT_CLI_TIMEOUT_SECONDS,
        )

        try:
            sdk = self._load_sdk()
            prompt = self._format_prompt(messages, system_prompt)
            stream = await self._open_sdk_stream(sdk, prompt, workspace_path, config)
        except ModuleNotFoundError as exc:
            if exc.name == SDK_MODULE_NAME:
                async for chunk in self._stream_cli(
                    messages,
                    system_prompt,
                    config,
                    workspace_path,
                ):
                    yield chunk
                return
            yield self._error_chunk(self._classify_exception(exc), self._safe_error_message(exc))
            return
        except Exception as exc:  # noqa: BLE001
            yield self._error_chunk(self._classify_exception(exc), self._safe_error_message(exc))
            return

        block_open = False
        block_index = 0
        total_blocks = 0
        try:
            async with asyncio.timeout(timeout_seconds):
                async for sdk_event in stream:
                    for chunk in self._map_sdk_event(sdk_event):
                        if chunk.event_type == "delta":
                            if not block_open:
                                yield StreamChunk(
                                    event_type="block_start",
                                    block_index=block_index,
                                    block_type="text",
                                )
                                block_open = True
                            chunk.block_index = block_index
                            yield chunk
                            continue

                        if block_open:
                            yield StreamChunk(event_type="block_end", block_index=block_index)
                            total_blocks += 1
                            block_index += 1
                            block_open = False
                        yield chunk
        except TimeoutError:
            if block_open:
                yield StreamChunk(event_type="block_end", block_index=block_index)
            yield self._error_chunk("timeout", "Claude Code runtime timed out")
            return
        except Exception as exc:  # noqa: BLE001
            if block_open:
                yield StreamChunk(event_type="block_end", block_index=block_index)
            yield self._error_chunk(self._classify_exception(exc), self._safe_error_message(exc))
            return

        if block_open:
            yield StreamChunk(event_type="block_end", block_index=block_index)
            total_blocks += 1

        yield StreamChunk(
            event_type="done",
            agent_id=self.agent_id,
            total_blocks=total_blocks,
        )

    def _load_sdk(self) -> Any:
        return importlib.import_module(SDK_MODULE_NAME)

    async def _stream_cli(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
        config: dict[str, Any] | None,
        workspace_path: Path,
    ) -> AsyncIterator[StreamChunk]:
        merged = self.merged_config(config)
        timeout_seconds = self._float_config(
            merged.get("timeout_seconds"),
            DEFAULT_CLI_TIMEOUT_SECONDS,
        )
        prompt = self._format_prompt(messages, system_prompt)
        command = [
            "claude",
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "acceptEdits",
            "--no-session-persistence",
            prompt,
        ]
        try:
            result = await run_cli_text(
                command,
                cwd=workspace_path,
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError:
            yield self._error_chunk("timeout", "Claude Code CLI timed out")
            return
        except Exception as exc:  # noqa: BLE001
            yield self._error_chunk("external_runtime_error", self._safe_error_message(exc))
            return

        if result.return_code != 0:
            output = self._safe_runtime_output(result.stderr or result.stdout)
            yield self._error_chunk(
                "external_runtime_error",
                f"Claude Code CLI exited with code {result.return_code}: {output}",
            )
            return

        text = result.stdout.strip()
        total_blocks = 0
        if text:
            yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
            yield StreamChunk(event_type="delta", block_index=0, text_delta=text)
            yield StreamChunk(event_type="block_end", block_index=0)
            total_blocks = 1
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=total_blocks)

    async def _open_sdk_stream(
        self,
        sdk: Any,
        prompt: str,
        workspace_path: Path,
        config: dict[str, Any] | None,
    ) -> AsyncIterator[Any]:
        options = self._build_options(sdk, workspace_path, config)
        stream = sdk.query(prompt=prompt, options=options)
        if inspect.isawaitable(stream):
            stream = await stream
        return cast(AsyncIterator[Any], stream)

    def _build_options(
        self,
        sdk: Any,
        workspace_path: Path,
        config: dict[str, Any] | None,
    ) -> Any:
        merged = self.merged_config(config)
        option_kwargs = self._sdk_options(merged)
        option_kwargs["cwd"] = workspace_path

        option_cls = getattr(sdk, "ClaudeAgentOptions", None) or getattr(
            sdk,
            "ClaudeCodeOptions",
            None,
        )
        if option_cls is None:
            return option_kwargs
        return option_cls(**option_kwargs)

    def _sdk_options(self, config: dict[str, Any]) -> dict[str, Any]:
        options = config.get("sdk_options", {})
        if not isinstance(options, dict):
            return {}
        return dict(options)

    def _format_prompt(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
    ) -> str:
        effective_system = self.effective_system_prompt(system_prompt)
        lines: list[str] = []
        if effective_system:
            lines.append(f"System: {effective_system}")
        for message in messages:
            if message.role == "system":
                lines.append(f"System: {message.content}")
            elif message.content:
                lines.append(f"{message.role.title()}: {message.content}")
        return "\n\n".join(lines)

    def _map_sdk_event(self, event: Any) -> list[StreamChunk]:
        event_name = self._event_name(event)
        if self._is_tool_call(event_name):
            return [self._tool_call_chunk(event)]
        if self._is_tool_result(event_name):
            return [self._tool_result_chunk(event)]

        content_blocks = self._content_blocks(event)
        if content_blocks:
            chunks: list[StreamChunk] = []
            for block in content_blocks:
                chunks.extend(self._map_sdk_event(block))
            return chunks

        if event_name in SKIP_EVENT_NAMES:
            return []

        text = self._text_delta(event, event_name)
        if text is None:
            return []
        return [StreamChunk(event_type="delta", text_delta=text)]

    def _content_blocks(self, event: Any) -> list[Any]:
        content = self._field(event, ("content", "blocks"))
        if isinstance(content, str) or not isinstance(content, Iterable):
            return []
        return list(content)

    def _event_name(self, event: Any) -> str:
        value = self._field(event, ("type", "event_type", "kind"))
        if isinstance(value, str):
            return str(value).lower()
        return type(event).__name__.lower()

    def _is_tool_call(self, event_name: str) -> bool:
        return event_name in TOOL_CALL_EVENT_NAMES or event_name.endswith("tooluseblock")

    def _is_tool_result(self, event_name: str) -> bool:
        return event_name in TOOL_RESULT_EVENT_NAMES or event_name.endswith("toolresultblock")

    def _text_delta(self, event: Any, event_name: str) -> str | None:
        if event_name not in TEXT_EVENT_NAMES and not event_name.endswith("textblock"):
            return None
        value = self._field(event, ("text_delta", "delta", "text"))
        return value if isinstance(value, str) and value else None

    def _tool_call_chunk(self, event: Any) -> StreamChunk:
        return StreamChunk(
            event_type="tool_call",
            call_id=self._string_field(event, ("call_id", "id", "tool_use_id")),
            tool_name=self._string_field(event, ("tool_name", "name")),
            tool_arguments=self._mapping_field(event, ("tool_arguments", "arguments", "input")),
        )

    def _tool_result_chunk(self, event: Any) -> StreamChunk:
        return StreamChunk(
            event_type="tool_result",
            call_id=self._string_field(event, ("call_id", "tool_use_id", "id")),
            tool_status=self._tool_status(event),
            tool_output=self._tool_output(event),
            tool_output_truncated=False,
        )

    def _tool_status(self, event: Any) -> Literal["ok", "error"]:
        status = self._field(event, ("tool_status", "status"))
        if status == "error":
            return "error"
        is_error = self._field(event, ("is_error", "error"))
        return "error" if is_error is True else "ok"

    def _tool_output(self, event: Any) -> str | None:
        value = self._field(event, ("tool_output", "output", "result", "content"))
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, Iterable) and not isinstance(value, Mapping):
            return "".join(str(item) for item in value)
        return str(value)

    def _field(self, event: Any, names: tuple[str, ...]) -> Any:
        if isinstance(event, Mapping):
            for name in names:
                if name in event:
                    return event[name]
            return None
        for name in names:
            value = getattr(event, name, None)
            if value is not None:
                return value
        return None

    def _string_field(self, event: Any, names: tuple[str, ...]) -> str | None:
        value = self._field(event, names)
        return value if isinstance(value, str) else None

    def _mapping_field(self, event: Any, names: tuple[str, ...]) -> dict[str, Any]:
        value = self._field(event, names)
        if not isinstance(value, Mapping):
            return {}
        return dict(value)

    def _error_chunk(self, error_code: str, error: str) -> StreamChunk:
        return StreamChunk(
            event_type="error",
            agent_id=self.agent_id,
            error_code=error_code,
            error=error,
            metadata={"provider": self.provider},
        )

    def _classify_exception(self, exc: BaseException) -> str:
        lowered = f"{exc.__class__.__name__}: {exc}".lower()
        if "api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
            return "missing_api_key"
        return "external_runtime_error"

    def _safe_error_message(self, exc: BaseException) -> str:
        return str(exc) or exc.__class__.__name__

    @staticmethod
    def _float_config(value: object, default: float) -> float:
        if value is None:
            return default
        if not isinstance(value, str | int | float):
            return default
        try:
            parsed = float(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _safe_runtime_output(output: str) -> str:
        return output.strip()[:500] or "no output"
