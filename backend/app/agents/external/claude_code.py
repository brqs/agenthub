"""Claude Code external runtime adapter."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import AsyncIterator, Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, cast

from app.agents.base import BaseAgentAdapter
from app.agents.external.cli_runtime import CliCompleted, stream_cli_text
from app.agents.external.direct_chat import maybe_stream_direct_chat
from app.agents.external.runtime_budget import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    RuntimeTimeoutError,
    runtime_budget_config,
)
from app.agents.external.runtime_isolation import (
    isolated_runtime_env,
    isolated_session_id,
)
from app.agents.external.runtime_prelude import (
    external_runtime_prelude,
    text_result_chunks,
)
from app.agents.external.runtime_utils import (
    argv,
    classify_external_exception,
    external_error_chunk,
    safe_runtime_output,
)
from app.agents.external.sdk_stream import stream_sdk_events
from app.agents.external.workspace_prompt import (
    format_runtime_messages,
    workspace_guard_prompt,
)
from app.agents.runtime_guard import (
    sanitize_preview_deploy_text,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

SDK_MODULE_NAME = "claude_agent_sdk"
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

        prelude = await external_runtime_prelude(
            adapter=self,
            provider=self.provider,
            messages=messages,
            system_prompt=system_prompt,
            config=config,
            workspace_path=workspace_path,
            workspace_error="workspace_path is required",
            error_chunk=self._error_chunk,
            direct_chat=maybe_stream_direct_chat,
        )
        if prelude.handled and prelude.stream is not None:
            async for chunk in prelude.stream:
                yield chunk
            return
        merged = prelude.merged_config
        assert workspace_path is not None

        budget_config = runtime_budget_config(
            merged,
            default_idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
        )

        try:
            sdk = self._load_sdk()
            prompt = self._format_prompt(messages, system_prompt, workspace_path)
            stream = await self._open_sdk_stream(sdk, prompt, workspace_path, merged)
        except ModuleNotFoundError as exc:
            if exc.name == SDK_MODULE_NAME:
                async for chunk in self._stream_cli(
                    messages,
                    system_prompt,
                    merged,
                    workspace_path,
                ):
                    yield chunk
                return
            yield self._error_chunk(self._classify_exception(exc), self._safe_error_message(exc))
            return
        except Exception as exc:  # noqa: BLE001
            yield self._error_chunk(self._classify_exception(exc), self._safe_error_message(exc))
            return

        async def exception_stream(
            exc: BaseException,
            saw_runtime_chunk: bool,
        ) -> AsyncIterator[StreamChunk]:
            _ = saw_runtime_chunk
            yield self._error_chunk(
                self._classify_exception(exc),
                self._safe_error_message(exc),
            )

        async for chunk in stream_sdk_events(
            stream,
            budget_config=budget_config,
            agent_id=self.agent_id,
            provider=self.provider,
            map_event=self._map_sdk_event,
            timeout_error_chunk=lambda exc: self._error_chunk(exc.error_code, str(exc)),
            exception_stream=exception_stream,
        ):
            yield chunk

    def _load_sdk(self) -> Any:
        return importlib.import_module(SDK_MODULE_NAME)

    async def _stream_cli(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
        config: dict[str, Any],
        workspace_path: Path,
    ) -> AsyncIterator[StreamChunk]:
        budget_config = runtime_budget_config(
            config,
            default_idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
        )
        prompt = self._format_prompt(messages, system_prompt, workspace_path)
        command = [
            *argv(config.get("command", "claude"), default=("claude",), drop_empty=True),
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "acceptEdits",
            "--no-session-persistence",
            prompt,
        ]
        result = None
        try:
            async for event in stream_cli_text(
                command,
                cwd=workspace_path,
                budget_config=budget_config,
                agent_id=self.agent_id,
                provider=self.provider,
                env=isolated_runtime_env(
                    config,
                    workspace_path=workspace_path,
                    agent_id=self.agent_id,
                ),
            ):
                if isinstance(event, StreamChunk):
                    yield event
                elif isinstance(event, CliCompleted):
                    result = event.result
        except RuntimeTimeoutError as exc:
            output = self._safe_runtime_output(exc.stderr or exc.stdout)
            yield self._error_chunk(exc.error_code, f"Claude Code CLI timed out: {output}")
            return
        except Exception as exc:  # noqa: BLE001
            yield self._error_chunk("external_runtime_error", self._safe_error_message(exc))
            return

        if result is None:
            yield self._error_chunk(
                "external_runtime_error",
                "Claude Code CLI ended without result",
            )
            return

        if result.return_code != 0:
            output = self._safe_runtime_output(result.stderr or result.stdout)
            yield self._error_chunk(
                "external_runtime_error",
                f"Claude Code CLI exited with code {result.return_code}: {output}",
            )
            return

        text = sanitize_preview_deploy_text(result.stdout.strip())
        total_blocks = 0
        if text:
            for chunk in text_result_chunks(text, self.agent_id):
                if chunk.event_type == "done":
                    continue
                yield chunk
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
        option_kwargs["continue_conversation"] = False
        option_kwargs["resume"] = None
        option_kwargs["session_id"] = isolated_session_id(merged, self.agent_id)
        option_kwargs["env"] = isolated_runtime_env(
            merged,
            workspace_path=workspace_path,
            agent_id=self.agent_id,
        )

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
            options = {}
        sdk_options = dict(options)
        sdk_options.setdefault("permission_mode", "acceptEdits")
        return sdk_options

    def _format_prompt(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
    ) -> str:
        effective_system = self.effective_system_prompt(system_prompt)
        lines: list[str] = [f"System: {workspace_guard_prompt(workspace_path)}"]
        if effective_system:
            lines.append(f"System: {effective_system}")
        conversation = format_runtime_messages(messages)
        if conversation:
            lines.append(conversation)
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
        return external_error_chunk(
            agent_id=self.agent_id,
            provider=self.provider,
            error_code=error_code,
            error=error,
        )

    def _classify_exception(self, exc: BaseException) -> str:
        return classify_external_exception(exc)

    def _safe_error_message(self, exc: BaseException) -> str:
        return str(exc) or exc.__class__.__name__

    @staticmethod
    def _safe_runtime_output(output: str) -> str:
        return safe_runtime_output(output, max_chars=500)
