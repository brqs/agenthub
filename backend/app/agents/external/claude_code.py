"""Claude Code external runtime adapter."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import os
import shutil
import subprocess
import tempfile
import time
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
    leading_block_count,
    offset_stream_chunk_indices,
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
DEFAULT_RUNTIME = "sdk"
SUPPORTED_RUNTIMES = {"cli", "sdk"}
DEFAULT_SHARED_AUTH_DIR = "/root/.agenthub/claude-auth"
CLAUDE_AUTH_DIR_ENV = "AGENTHUB_CLAUDE_AUTH_DIR"
CLAUDE_MISSING_CREDENTIALS_ERROR = (
    "Claude Code runtime is not authenticated. Provide backend .env credentials "
    "or complete Claude Code login in the claude-state volume."
)
AUTH_ENV_PREFIXES = ("ANTHROPIC_", "CLAUDE_")
AUTH_ERROR_MARKERS = (
    "api key",
    "api_key",
    "auth",
    "credential",
    "login",
    "not logged in",
    "please run /login",
    "returned an error result: success",
    "unauthorized",
)
RUNTIME_PROBE_TTL_SECONDS = 120.0
RUNTIME_PROBE_TIMEOUT_SECONDS = 60.0
RUNTIME_PROBE_PROMPT = "只回复 OK"
TEXT_EVENT_NAMES = {"text", "text_block", "text_delta", "content_block_delta"}
TOOL_CALL_EVENT_NAMES = {"tool_call", "tool_use", "tool_start", "tooluseblock"}
TOOL_RESULT_EVENT_NAMES = {"tool_result", "tool_finish", "tool_end", "toolresultblock"}
SKIP_EVENT_NAMES = {"start", "done", "result", "system", "assistantmessage"}
_RUNTIME_PROBE_CACHE: dict[
    tuple[Any, ...],
    tuple[float, tuple[str, str | None]],
] = {}


class SharedClaudeAuthError(RuntimeError):
    """Raised when shared Claude auth exists but cannot be safely copied."""


def claude_code_runtime_status(config: dict[str, Any] | None = None) -> tuple[str, str | None]:
    runtime = str((config or {}).get("runtime") or DEFAULT_RUNTIME).strip().lower()
    if runtime not in SUPPORTED_RUNTIMES:
        return "invalid", "Claude Code runtime must be one of: cli, sdk"
    if not (_has_provider_credentials() or _has_shared_auth()):
        return "unavailable", CLAUDE_MISSING_CREDENTIALS_ERROR

    key = _runtime_probe_cache_key(config)
    now = time.monotonic()
    cached = _RUNTIME_PROBE_CACHE.get(key)
    if cached is not None and now - cached[0] < RUNTIME_PROBE_TTL_SECONDS:
        return cached[1]

    status = _probe_claude_runtime(config)
    _RUNTIME_PROBE_CACHE[key] = (now, status)
    return status


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
        messages = prelude.messages or messages
        for chunk in prelude.leading_chunks:
            yield chunk
        block_offset = leading_block_count(prelude.leading_chunks)
        assert workspace_path is not None

        budget_config = runtime_budget_config(
            merged,
            default_idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
        )
        runtime = str(merged.get("runtime") or DEFAULT_RUNTIME).strip().lower()
        if runtime not in SUPPORTED_RUNTIMES:
            yield self._error_chunk(
                "external_runtime_error",
                "Claude Code runtime must be one of: cli, sdk",
            )
            return
        if runtime == "cli":
            async for chunk in self._stream_cli(
                messages,
                system_prompt,
                merged,
                workspace_path,
            ):
                yield offset_stream_chunk_indices(chunk, block_offset)
            return

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
                    yield offset_stream_chunk_indices(chunk, block_offset)
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
            yield offset_stream_chunk_indices(chunk, block_offset)

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
        runtime_env = isolated_runtime_env(
            config,
            workspace_path=workspace_path,
            agent_id=self.agent_id,
        )
        result = None
        try:
            self._copy_shared_auth(runtime_env)
            async for event in stream_cli_text(
                command,
                cwd=workspace_path,
                budget_config=budget_config,
                agent_id=self.agent_id,
                provider=self.provider,
                env=runtime_env,
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
        self._copy_shared_auth(option_kwargs["env"])

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
        if self._safe_error_message(exc) == CLAUDE_MISSING_CREDENTIALS_ERROR:
            return "missing_api_key"
        return classify_external_exception(exc)

    def _safe_error_message(self, exc: BaseException) -> str:
        return self._normalize_runtime_error(str(exc) or exc.__class__.__name__)

    @staticmethod
    def _safe_runtime_output(output: str) -> str:
        return ClaudeCodeAdapter._normalize_runtime_error(
            safe_runtime_output(output, max_chars=500)
        )

    @staticmethod
    def _copy_shared_auth(env: dict[str, str]) -> None:
        source_dir = _shared_auth_dir()
        if not _path_exists(source_dir):
            return
        home = env.get("HOME")
        if not home:
            return
        destination_home = Path(home)
        try:
            _copy_if_present(source_dir / ".claude.json", destination_home / ".claude.json")
            _copy_if_present(source_dir / ".claude", destination_home / ".claude")
        except OSError as exc:
            raise SharedClaudeAuthError(CLAUDE_MISSING_CREDENTIALS_ERROR) from exc

    @staticmethod
    def _normalize_runtime_error(output: str) -> str:
        safe_output = safe_runtime_output(output, max_chars=500)
        if _looks_like_auth_error(safe_output):
            return CLAUDE_MISSING_CREDENTIALS_ERROR
        return safe_output


def _has_provider_credentials() -> bool:
    return any(
        value
        for key, value in os.environ.items()
        if key.startswith(AUTH_ENV_PREFIXES) and key.endswith(("API_KEY", "AUTH_TOKEN", "TOKEN"))
    )


def _has_shared_auth() -> bool:
    source_dir = _shared_auth_dir()
    return _is_readable_file(source_dir / ".claude.json") or _is_readable_dir(
        source_dir / ".claude"
    )


def _probe_claude_runtime(config: dict[str, Any] | None) -> tuple[str, str | None]:
    merged_config = dict(config or {})
    command = [
        *argv(merged_config.get("command", "claude"), default=("claude",), drop_empty=True),
        "-p",
        RUNTIME_PROBE_PROMPT,
        "--output-format",
        "text",
        "--permission-mode",
        "acceptEdits",
        "--no-session-persistence",
    ]
    with tempfile.TemporaryDirectory(prefix="agenthub-claude-probe-") as temp_dir:
        workspace_path = Path(temp_dir)
        probe_config = {
            **merged_config,
            "runtime_context": {
                "conversation_id": "claude-runtime-probe",
                "agent_message_id": "claude-runtime-probe",
                "agent_id": "claude-code",
            },
        }
        try:
            runtime_env = isolated_runtime_env(
                probe_config,
                workspace_path=workspace_path,
                agent_id="claude-code",
            )
            ClaudeCodeAdapter._copy_shared_auth(runtime_env)
        except Exception as exc:  # noqa: BLE001
            return "unavailable", ClaudeCodeAdapter._normalize_runtime_error(str(exc))
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                cwd=workspace_path,
                env=runtime_env,
                capture_output=True,
                text=True,
                timeout=RUNTIME_PROBE_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            return (
                "unavailable",
                "Claude Code CLI command 'claude' was not found in backend container PATH.",
            )
        except subprocess.TimeoutExpired as exc:
            output = _completed_output(exc.stdout, exc.stderr)
            suffix = f": {output}" if output else ""
            return "unavailable", f"Claude Code runtime probe timed out{suffix}"
        except Exception as exc:  # noqa: BLE001
            return "unavailable", ClaudeCodeAdapter._normalize_runtime_error(str(exc))

    output = _completed_output(completed.stdout, completed.stderr)
    normalized = ClaudeCodeAdapter._normalize_runtime_error(output)
    if completed.returncode == 0 and not _looks_like_auth_error(output):
        return "ready", None
    if _looks_like_auth_error(output):
        return "unavailable", CLAUDE_MISSING_CREDENTIALS_ERROR
    return "unavailable", f"Claude Code runtime probe failed: {normalized}"


def _runtime_probe_cache_key(config: dict[str, Any] | None) -> tuple[Any, ...]:
    command = tuple(
        argv((config or {}).get("command", "claude"), default=("claude",), drop_empty=True)
    )
    return (
        command,
        _auth_env_fingerprint(),
        _shared_auth_fingerprint(),
    )


def _auth_env_fingerprint() -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(
            (key, len(value))
            for key, value in os.environ.items()
            if key.startswith(AUTH_ENV_PREFIXES)
            and key.endswith(("API_KEY", "AUTH_TOKEN", "TOKEN"))
            and value
        )
    )


def _shared_auth_fingerprint() -> tuple[Any, ...]:
    source_dir = _shared_auth_dir()
    claude_json = source_dir / ".claude.json"
    claude_dir = source_dir / ".claude"
    json_stat = _path_signature(claude_json)
    if not _path_exists(claude_dir):
        return (str(source_dir), json_stat, None)
    if not _is_readable_dir(claude_dir):
        return (str(source_dir), json_stat, "unreadable")
    file_count = 0
    total_size = 0
    newest_mtime_ns = 0
    try:
        paths = list(claude_dir.rglob("*"))
    except OSError:
        return (str(source_dir), json_stat, "unreadable")
    for path in paths:
        if not path.is_file():
            continue
        with contextlib.suppress(OSError):
            stat = path.stat()
            file_count += 1
            total_size += stat.st_size
            newest_mtime_ns = max(newest_mtime_ns, stat.st_mtime_ns)
    return (str(source_dir), json_stat, (file_count, total_size, newest_mtime_ns))


def _path_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _is_readable_file(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.R_OK)
    except OSError:
        return False


def _is_readable_dir(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.R_OK | os.X_OK)
    except OSError:
        return False


def _completed_output(stdout: object, stderr: object) -> str:
    parts: list[str] = []
    for value in (stderr, stdout):
        if value is None:
            continue
        if isinstance(value, bytes):
            parts.append(value.decode(errors="replace"))
        else:
            parts.append(str(value))
    return "\n".join(part for part in parts if part).strip()


def _clear_runtime_probe_cache() -> None:
    _RUNTIME_PROBE_CACHE.clear()


def _shared_auth_dir() -> Path:
    return Path(os.environ.get(CLAUDE_AUTH_DIR_ENV, DEFAULT_SHARED_AUTH_DIR)).expanduser()


def _copy_if_present(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _looks_like_auth_error(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in AUTH_ERROR_MARKERS)
