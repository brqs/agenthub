"""OpenCode CLI external agent adapter."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from app.agents.base import BaseAgentAdapter
from app.agents.external.cli_runtime import cli_env, resolve_command
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEFAULT_COMMAND = "opencode"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_TOOL_OUTPUT_MAX_CHARS = 4000
TEXT_EVENT_TYPES = {"text", "text_delta", "reasoning"}
TOOL_CALL_EVENT_TYPES = {"tool_call"}
TOOL_RESULT_EVENT_TYPES = {"tool_result"}
TOOL_USE_EVENT_TYPES = {"tool_use"}
TOOL_EVENT_TYPES = TOOL_CALL_EVENT_TYPES | TOOL_RESULT_EVENT_TYPES | TOOL_USE_EVENT_TYPES
ENV_ALLOWLIST = {
    "PATH",
    "LANG",
    "LC_ALL",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
}


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

        if workspace_path is None:
            yield self._error("workspace_violation", "OpenCode requires a workspace_path")
            return

        merged = self.merged_config(config)
        command = self._argv(merged.get("command", DEFAULT_COMMAND))
        args = self._argv(merged.get("args", []))
        timeout_seconds = self._float_config(
            merged.get("timeout_seconds"),
            DEFAULT_TIMEOUT_SECONDS,
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
                self._format_prompt(messages, system_prompt),
            ]
            write_stdin_payload = False

        if not command:
            yield self._error("external_runtime_error", "OpenCode command is empty")
            return

        try:
            process = await asyncio.create_subprocess_exec(
                *resolve_command(command),
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_path),
                env=cli_env(),
            )
        except Exception as exc:
            yield self._error("external_runtime_error", self._safe_message(exc))
            return

        if write_stdin_payload:
            try:
                await self._write_stdin(process, messages, system_prompt, tool_specs)
            except Exception as exc:
                await self._terminate_process(process)
                yield self._error("external_runtime_error", self._safe_message(exc))
                return
        elif process.stdin is not None:
            process.stdin.close()
            await process.stdin.wait_closed()

        text_block_open = False
        next_block_index = 0
        saw_terminal_event = False
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        try:
            stdout = process.stdout
            if stdout is None:
                yield self._error("external_runtime_error", "OpenCode stdout pipe was not created")
                await self._terminate_process(process)
                return

            while True:
                line = await asyncio.wait_for(
                    stdout.readline(),
                    timeout=self._remaining_seconds(deadline),
                )
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
                    yield StreamChunk(
                        event_type="delta",
                        block_index=next_block_index,
                        text_delta=line.decode(errors="replace"),
                    )
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
                    return_code = await self._wait_process(process, deadline)
                    if return_code != 0:
                        stderr = await self._read_stderr(process)
                        yield self._exit_error(return_code, stderr)
                        return
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
                        self._string_field(event, "error") or "OpenCode runtime error",
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

            return_code = await self._wait_process(process, deadline)
        except TimeoutError:
            if text_block_open:
                yield StreamChunk(event_type="block_end", block_index=next_block_index)
            await self._terminate_process(process)
            yield self._error("timeout", "OpenCode runtime timed out")
            return

        if text_block_open:
            yield StreamChunk(event_type="block_end", block_index=next_block_index)
            next_block_index += 1

        if return_code != 0 and not saw_terminal_event:
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

        if event_type in TOOL_CALL_EVENT_TYPES | TOOL_USE_EVENT_TYPES:
            yield self._tool_call_chunk(event)
            if event_type in TOOL_USE_EVENT_TYPES:
                yield self._tool_result_chunk(event, output_max_chars)
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
        tool_specs: list[ToolSpec] | None,
    ) -> None:
        if process.stdin is None:
            return
        payload = {
            "messages": [message.model_dump() for message in messages],
            "system_prompt": self.effective_system_prompt(system_prompt),
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
    ) -> str:
        lines: list[str] = []
        effective_system = self.effective_system_prompt(system_prompt)
        if effective_system:
            lines.append(f"System: {effective_system}")
        for message in messages:
            if message.role == "system":
                lines.append(f"System: {message.content}")
            elif message.content:
                lines.append(f"{message.role.title()}: {message.content}")
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
    ) -> StreamChunk:
        output = self._tool_output(event) or ""
        truncated_output = self._truncate(output, output_max_chars)
        return StreamChunk(
            event_type="tool_result",
            call_id=self._string_field_deep(
                event,
                ("call_id", "callID", "tool_call_id", "tool_use_id", "id"),
            ),
            tool_status=self._tool_status(event),
            tool_output=truncated_output,
            tool_output_truncated=len(output) > len(truncated_output),
        )

    @staticmethod
    def _argv(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return shlex.split(value, posix=os.name != "nt")
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

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
    def _remaining_seconds(deadline: float) -> float:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    @staticmethod
    async def _wait_process(
        process: asyncio.subprocess.Process,
        deadline: float,
    ) -> int:
        return await asyncio.wait_for(
            process.wait(),
            timeout=OpenCodeAdapter._remaining_seconds(deadline),
        )

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            process.kill()
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
        if status == "error":
            return "error"
        return "error" if self._field_deep(event, ("error", "is_error")) is True else "ok"

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
        if max_chars <= 0:
            return ""
        return value[:max_chars]

    def _error(self, error_code: str, error: str) -> StreamChunk:
        return StreamChunk(
            event_type="error",
            agent_id=self.agent_id,
            error_code=error_code,
            error=error,
            metadata={"provider": self.provider},
        )

    def _exit_error(self, return_code: int, stderr: str) -> StreamChunk:
        return self._error(
            "external_runtime_error",
            f"OpenCode exited with code {return_code}: {stderr}",
        )

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        return str(exc)[:500] or exc.__class__.__name__
