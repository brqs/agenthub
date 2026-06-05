"""OpenCode CLI external agent adapter."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from app.agents.base import BaseAgentAdapter
from app.agents.external.cli_runtime import (
    kill_process_tree,
    process_kwargs,
    resolve_command,
)
from app.agents.external.direct_chat import maybe_stream_direct_chat
from app.agents.external.runtime_budget import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    RuntimeBudget,
    RuntimeTimeoutError,
    runtime_budget_config,
)
from app.agents.external.runtime_isolation import isolated_runtime_env
from app.agents.external.runtime_prelude import external_runtime_prelude
from app.agents.external.runtime_utils import (
    argv,
    external_error_chunk,
    safe_exception_message,
    safe_runtime_output,
    truncate,
)
from app.agents.external.workspace_prompt import (
    format_runtime_messages,
    workspace_guard_prompt,
)
from app.agents.runtime_guard import sanitize_preview_deploy_text
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEFAULT_COMMAND = "opencode"
DEFAULT_TOOL_OUTPUT_MAX_CHARS = 4000
DEFAULT_SHARED_AUTH_DIR = "/root/.local/share/opencode"
OPENCODE_AUTH_DIR_ENV = "AGENTHUB_OPENCODE_AUTH_DIR"
OPENCODE_CLI_MISSING_ERROR = (
    "OpenCode CLI command 'opencode' was not found in backend container PATH. "
    "Install OpenCode in the backend Docker image or update opencode-helper "
    "config.command to an executable command."
)
OPENCODE_MISSING_CREDENTIALS_ERROR = (
    "OpenCode CLI is installed but no usable model credentials are configured. "
    "Set provider keys in backend .env or run `docker compose exec backend "
    "opencode auth login` and keep the opencode-state volume."
)
AUTH_ERROR_MARKERS = (
    "api key",
    "api_key",
    "auth",
    "credential",
    "login",
    "no provider",
    "not configured",
    "unauthorized",
)
TEXT_EVENT_TYPES = {"text", "text_delta", "reasoning"}
TOOL_CALL_EVENT_TYPES = {"tool_call"}
TOOL_RESULT_EVENT_TYPES = {"tool_result"}
TOOL_USE_EVENT_TYPES = {"tool_use"}
TOOL_EVENT_TYPES = TOOL_CALL_EVENT_TYPES | TOOL_RESULT_EVENT_TYPES | TOOL_USE_EVENT_TYPES
TOOL_USE_OK_STATUSES = {"completed", "done", "success", "ok"}
TOOL_USE_ERROR_STATUSES = {"error", "failed"}
TOOL_USE_NON_TERMINAL_STATUSES = {"running", "pending", "started"}
def opencode_runtime_status(config: dict[str, Any] | None = None) -> tuple[str, str | None]:
    command = argv((config or {}).get("command", DEFAULT_COMMAND))
    if not command:
        return "invalid", "OpenCode command is empty"
    if _command_available(command):
        return "ready", None
    return "unavailable", OPENCODE_CLI_MISSING_ERROR


def _command_available(command: list[str]) -> bool:
    resolved = resolve_command(command)
    executable = resolved[0]
    if executable != command[0]:
        return True
    if _looks_like_path(executable):
        return Path(executable).exists()
    return shutil.which(executable, path=os.environ.get("PATH")) is not None


def _looks_like_path(value: str) -> bool:
    return "/" in value or "\\" in value or value.startswith(".")


class OpenCodeAdapter(BaseAgentAdapter):
    """Adapter for OpenCode CLI JSONL runtime events."""

    provider = "opencode"

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
            workspace_error="OpenCode requires a workspace_path",
            error_chunk=self._error,
            direct_chat=maybe_stream_direct_chat,
        )
        if prelude.handled and prelude.stream is not None:
            async for chunk in prelude.stream:
                yield chunk
            return
        merged = prelude.merged_config
        assert workspace_path is not None

        command = argv(merged.get("command", DEFAULT_COMMAND))
        args = argv(merged.get("args", []))
        budget_config = runtime_budget_config(
            merged,
            default_idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
        )
        jsonl = bool(merged.get("jsonl", True))
        output_max_chars = int(
            merged.get("tool_output_max_chars", DEFAULT_TOOL_OUTPUT_MAX_CHARS)
        )
        write_stdin_payload = True
        if not args:
            args = [
                "run",
                "--format",
                "json",
                "--dir",
                str(workspace_path),
                self._format_prompt(messages, system_prompt, workspace_path),
            ]
            write_stdin_payload = False

        if not command:
            yield self._error("external_runtime_error", "OpenCode command is empty")
            return

        runtime_env = self._runtime_env(merged, workspace_path)
        try:
            process = await asyncio.create_subprocess_exec(
                *resolve_command(command),
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_path),
                env=runtime_env,
                **process_kwargs(),
            )
        except FileNotFoundError:
            yield self._error("external_runtime_error", OPENCODE_CLI_MISSING_ERROR)
            return
        except Exception as exc:
            yield self._error("external_runtime_error", self._safe_message(exc))
            return

        if write_stdin_payload:
            try:
                await self._write_stdin(
                    process,
                    messages,
                    system_prompt,
                    workspace_path,
                    tool_specs,
                )
            except Exception as exc:
                await self._terminate_process(process)
                yield self._error("external_runtime_error", self._safe_message(exc))
                return
        elif process.stdin is not None:
            process.stdin.close()
            await process.stdin.wait_closed()

        text_block_open = False
        next_block_index = 0
        saw_meaningful_event = False
        budget = RuntimeBudget(budget_config)

        try:
            stdout = process.stdout
            if stdout is None:
                yield self._error("external_runtime_error", "OpenCode stdout pipe was not created")
                await self._terminate_process(process)
                return

            while True:
                line_task = asyncio.create_task(stdout.readline())
                try:
                    while True:
                        done, _ = await asyncio.wait(
                            {line_task},
                            timeout=budget.next_wait_seconds(),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if line_task in done:
                            line = line_task.result()
                            if line:
                                budget.record_activity()
                                budget.check_timeout()
                            break
                        budget.check_timeout()
                        yield budget.heartbeat(agent_id=self.agent_id, provider=self.provider)
                finally:
                    if not line_task.done():
                        line_task.cancel()
                if not line:
                    break

                if not jsonl:
                    if not text_block_open:
                        yield StreamChunk(
                            event_type="block_start",
                            block_index=next_block_index,
                            block_type="text",
                        )
                        text_block_open = True
                        saw_meaningful_event = True
                    yield StreamChunk(
                        event_type="delta",
                        block_index=next_block_index,
                        text_delta=sanitize_preview_deploy_text(
                            line.decode(errors="replace")
                        ),
                    )
                    saw_meaningful_event = True
                    continue

                try:
                    event = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    if text_block_open:
                        yield StreamChunk(event_type="block_end", block_index=next_block_index)
                    await self._terminate_process(process)
                    yield self._error(
                        "external_runtime_error",
                        f"OpenCode emitted invalid JSONL: {exc.msg}",
                    )
                    return

                if not isinstance(event, dict):
                    if text_block_open:
                        yield StreamChunk(event_type="block_end", block_index=next_block_index)
                    await self._terminate_process(process)
                    yield self._error(
                        "external_runtime_error",
                        "OpenCode JSONL event must be an object",
                    )
                    return

                event_type = event.get("type")
                if event_type == "done":
                    if text_block_open:
                        yield StreamChunk(event_type="block_end", block_index=next_block_index)
                        text_block_open = False
                        next_block_index += 1
                    await self._wait_process(process, budget)
                    yield StreamChunk(
                        event_type="done",
                        agent_id=self.agent_id,
                        total_blocks=next_block_index,
                    )
                    return

                if event_type in {"step_start", "step_finish"}:
                    continue

                if event_type == "error":
                    if text_block_open:
                        yield StreamChunk(event_type="block_end", block_index=next_block_index)
                    await self._terminate_process(process)
                    yield self._error(
                        self._string_field(event, "error_code") or "external_runtime_error",
                        self._normalize_runtime_error(
                            self._string_field(event, "error") or "OpenCode runtime error"
                        ),
                    )
                    return

                if event_type not in TEXT_EVENT_TYPES | TOOL_EVENT_TYPES:
                    if text_block_open:
                        yield StreamChunk(event_type="block_end", block_index=next_block_index)
                    await self._terminate_process(process)
                    yield self._error(
                        "external_runtime_error",
                        f"OpenCode emitted unsupported event type: {event_type!r}",
                    )
                    return

                async for chunk in self._map_event(
                    event,
                    text_block_open=text_block_open,
                    block_index=next_block_index,
                    output_max_chars=output_max_chars,
                ):
                    if chunk.event_type in {
                        "block_start",
                        "delta",
                        "tool_call",
                        "tool_result",
                    }:
                        saw_meaningful_event = True
                    yield chunk

                if (
                    event_type in TEXT_EVENT_TYPES
                    and not text_block_open
                    and self._event_text(event)
                ):
                    text_block_open = True
                elif event_type in TOOL_EVENT_TYPES and text_block_open:
                    text_block_open = False
                    next_block_index += 1

            return_code = await self._wait_process(process, budget)
        except RuntimeTimeoutError as exc:
            if text_block_open:
                yield StreamChunk(event_type="block_end", block_index=next_block_index)
            await self._terminate_process(process)
            yield self._error(exc.error_code, str(exc))
            return
        finally:
            if process.returncode is None:
                await self._terminate_process(process)

        if text_block_open:
            yield StreamChunk(event_type="block_end", block_index=next_block_index)
            next_block_index += 1

        if return_code != 0 and not saw_meaningful_event:
            stderr = await self._read_stderr(process)
            yield self._exit_error(return_code, stderr)
            return

        yield StreamChunk(
            event_type="done",
            agent_id=self.agent_id,
            total_blocks=next_block_index,
        )

    async def _map_event(
        self,
        event: object,
        *,
        text_block_open: bool,
        block_index: int,
        output_max_chars: int,
    ) -> AsyncIterator[StreamChunk]:
        if not isinstance(event, dict):
            return

        event_type = event.get("type")
        if event_type in TEXT_EVENT_TYPES:
            text = self._event_text(event)
            if not text:
                return
            text = sanitize_preview_deploy_text(text)
            if not text:
                return
            if not text_block_open:
                yield StreamChunk(
                    event_type="block_start",
                    block_index=block_index,
                    block_type="text",
                )
            yield StreamChunk(
                event_type="delta",
                block_index=block_index,
                text_delta=text,
            )
            return

        if text_block_open:
            yield StreamChunk(event_type="block_end", block_index=block_index)

        if event_type in TOOL_CALL_EVENT_TYPES:
            yield self._tool_call_chunk(event)
            return

        if event_type in TOOL_USE_EVENT_TYPES:
            yield self._tool_call_chunk(event)
            result_status = self._tool_use_result_status(event)
            if result_status is not None:
                yield self._tool_result_chunk(
                    event,
                    output_max_chars,
                    tool_status=result_status,
                )
            return

        if event_type in TOOL_RESULT_EVENT_TYPES:
            yield self._tool_result_chunk(event, output_max_chars)
            return

        return

    async def _write_stdin(
        self,
        process: asyncio.subprocess.Process,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
        tool_specs: list[ToolSpec] | None,
    ) -> None:
        if process.stdin is None:
            return
        payload = {
            "messages": [message.model_dump() for message in messages],
            "system_prompt": self._effective_system_prompt(system_prompt, workspace_path),
            "tool_specs": [tool.model_dump() for tool in tool_specs or []],
        }
        process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await process.stdin.drain()
        process.stdin.close()
        await process.stdin.wait_closed()

    def _format_prompt(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
    ) -> str:
        lines: list[str] = [
            f"System: {self._effective_system_prompt(system_prompt, workspace_path)}"
        ]
        conversation = format_runtime_messages(messages)
        if conversation:
            lines.append(conversation)
        return "\n\n".join(lines)

    def _effective_system_prompt(
        self,
        system_prompt: str | None,
        workspace_path: Path,
    ) -> str:
        lines = [workspace_guard_prompt(workspace_path)]
        effective_system = self.effective_system_prompt(system_prompt)
        if effective_system:
            lines.append(effective_system)
        return "\n\n".join(lines)

    @staticmethod
    def _event_text(event: dict[Any, Any]) -> str | None:
        text = event.get("text")
        if isinstance(text, str):
            return text
        part = event.get("part")
        if not isinstance(part, dict) or part.get("type") not in {"text", "reasoning"}:
            return None
        part_text = part.get("text")
        return part_text if isinstance(part_text, str) else None

    def _tool_call_chunk(self, event: dict[Any, Any]) -> StreamChunk:
        return StreamChunk(
            event_type="tool_call",
            call_id=self._string_field_deep(
                event,
                ("call_id", "callID", "id", "tool_call_id", "tool_use_id"),
            ),
            tool_name=self._string_field_deep(event, ("tool_name", "tool", "name")),
            tool_arguments=self._dict_field_deep(
                event,
                ("arguments", "tool_arguments", "input", "args"),
                include_state=True,
            ),
        )

    def _tool_result_chunk(
        self,
        event: dict[Any, Any],
        output_max_chars: int,
        *,
        tool_status: Literal["ok", "error"] | None = None,
    ) -> StreamChunk:
        output = self._tool_output(event) or ""
        truncated_output = self._truncate(output, output_max_chars)
        return StreamChunk(
            event_type="tool_result",
            call_id=self._string_field_deep(
                event,
                ("call_id", "callID", "tool_call_id", "tool_use_id", "id"),
            ),
            tool_status=tool_status or self._tool_status(event),
            tool_output=truncated_output,
            tool_output_truncated=len(output) > len(truncated_output),
        )

    async def _wait_process(
        self,
        process: asyncio.subprocess.Process,
        budget: RuntimeBudget,
    ) -> int:
        wait_task = asyncio.create_task(process.wait())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {wait_task},
                    timeout=budget.next_wait_seconds(),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if wait_task in done:
                    return wait_task.result()
                budget.check_timeout()
        finally:
            if not wait_task.done():
                wait_task.cancel()

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            kill_process_tree(process)
        try:
            await process.wait()
        except Exception:
            return

    @staticmethod
    async def _read_stderr(process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            return ""
        stderr = await process.stderr.read()
        return stderr.decode(errors="replace")[:500]

    @staticmethod
    def _string_field(event: dict[Any, Any], key: str) -> str | None:
        value = event.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _dict_field(event: dict[Any, Any], key: str) -> dict[str, Any]:
        value = event.get(key)
        return value if isinstance(value, dict) else {}

    def _string_field_deep(
        self,
        event: dict[Any, Any],
        keys: tuple[str, ...],
    ) -> str | None:
        for candidate in self._field_candidates(event):
            for key in keys:
                value = candidate.get(key)
                if value is None:
                    continue
                return value if isinstance(value, str) else str(value)
        return None

    def _dict_field_deep(
        self,
        event: dict[Any, Any],
        keys: tuple[str, ...],
        *,
        include_state: bool = False,
    ) -> dict[str, Any]:
        for candidate in self._field_candidates(event, include_state=include_state):
            for key in keys:
                value = candidate.get(key)
                if isinstance(value, dict):
                    return value
        return {}

    def _field_deep(self, event: dict[Any, Any], keys: tuple[str, ...]) -> Any:
        for candidate in self._field_candidates(event, include_state=True):
            for key in keys:
                value = candidate.get(key)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _field_candidates(
        event: dict[Any, Any],
        *,
        include_state: bool = False,
    ) -> list[dict[Any, Any]]:
        candidates = [event]
        for first_level in ("part", "item", "data"):
            value = event.get(first_level)
            if isinstance(value, dict):
                candidates.append(value)
                state = value.get("state")
                if include_state and isinstance(state, dict):
                    candidates.append(state)
        state = event.get("state")
        if include_state and isinstance(state, dict):
            candidates.append(state)
        return candidates

    def _tool_status(self, event: dict[Any, Any]) -> Literal["ok", "error"]:
        status = self._field_deep(event, ("tool_status", "status"))
        if isinstance(status, str) and status.lower() in TOOL_USE_ERROR_STATUSES:
            return "error"
        return "error" if self._field_deep(event, ("error", "is_error")) is True else "ok"

    def _tool_use_result_status(self, event: dict[Any, Any]) -> Literal["ok", "error"] | None:
        status = self._field_deep(event, ("tool_status", "status"))
        if not isinstance(status, str):
            return None
        normalized = status.lower()
        if normalized in TOOL_USE_OK_STATUSES:
            return "ok"
        if normalized in TOOL_USE_ERROR_STATUSES:
            return "error"
        if normalized in TOOL_USE_NON_TERMINAL_STATUSES:
            return None
        return None

    def _tool_output(self, event: dict[Any, Any]) -> str | None:
        value = self._field_deep(event, ("tool_output", "output", "result", "content", "error"))
        if value is None:
            metadata = self._dict_field_deep(event, ("metadata",))
            value = metadata.get("output") or metadata.get("error")
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _truncate(value: str, max_chars: int) -> str:
        return truncate(value, max_chars)

    def _error(self, error_code: str, error: str) -> StreamChunk:
        return external_error_chunk(
            agent_id=self.agent_id,
            provider=self.provider,
            error_code=error_code,
            error=error,
        )

    def _exit_error(self, return_code: int, stderr: str) -> StreamChunk:
        return self._error(
            "external_runtime_error",
            f"OpenCode exited with code {return_code}: "
            f"{self._normalize_runtime_error(stderr)}",
        )

    def _runtime_env(self, config: dict[str, Any], workspace_path: Path) -> dict[str, str]:
        env = isolated_runtime_env(
            config,
            workspace_path=workspace_path,
            agent_id=self.agent_id,
        )
        self._copy_shared_auth(env)
        return env

    @staticmethod
    def _copy_shared_auth(env: dict[str, str]) -> None:
        source_dir = Path(
            os.environ.get(OPENCODE_AUTH_DIR_ENV)
            or os.environ.get("OPENCODE_AUTH_DIR", "")
            or DEFAULT_SHARED_AUTH_DIR
        ).expanduser()
        source = source_dir / "auth.json"
        if not source.exists():
            return
        xdg_data_home = env.get("XDG_DATA_HOME")
        home = env.get("HOME")
        if xdg_data_home:
            destination_dir = Path(xdg_data_home) / "opencode"
        elif home:
            destination_dir = Path(home) / ".local" / "share" / "opencode"
        else:
            return
        destination = destination_dir / "auth.json"
        if source.resolve() == destination.resolve():
            return
        destination_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    @staticmethod
    def _normalize_runtime_error(output: str) -> str:
        safe_output = safe_runtime_output(output, max_chars=500)
        if _looks_like_auth_error(safe_output):
            return OPENCODE_MISSING_CREDENTIALS_ERROR
        return safe_output

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        return safe_exception_message(exc)


def _looks_like_auth_error(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in AUTH_ERROR_MARKERS)
