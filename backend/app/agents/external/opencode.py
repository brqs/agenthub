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
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

DEFAULT_COMMAND = "opencode"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_TOOL_OUTPUT_MAX_CHARS = 4000
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

        if not command:
            yield self._error("external_runtime_error", "OpenCode command is empty")
            return

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_path),
                env=self._subprocess_env(),
            )
        except Exception as exc:
            yield self._error("external_runtime_error", self._safe_message(exc))
            return

        try:
            await self._write_stdin(process, messages, system_prompt, tool_specs)
        except Exception as exc:
            await self._terminate_process(process)
            yield self._error("external_runtime_error", self._safe_message(exc))
            return

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

                if event_type == "error":
                    if text_block_open:
                        yield StreamChunk(event_type="block_end", block_index=next_block_index)
                    await self._terminate_process(process)
                    yield self._error(
                        self._string_field(event, "error_code") or "external_runtime_error",
                        self._string_field(event, "error") or "OpenCode runtime error",
                    )
                    return

                if event_type not in {"text_delta", "tool_call", "tool_result"}:
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
                    event_type == "text_delta"
                    and not text_block_open
                    and isinstance(event.get("text"), str)
                    and event.get("text")
                ):
                    text_block_open = True
                elif event_type in {"tool_call", "tool_result"} and text_block_open:
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
        if event_type == "text_delta":
            text = event.get("text")
            if not isinstance(text, str) or not text:
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

        if event_type == "tool_call":
            yield StreamChunk(
                event_type="tool_call",
                call_id=self._string_field(event, "call_id"),
                tool_name=self._string_field(event, "tool_name"),
                tool_arguments=self._dict_field(event, "arguments"),
            )
            return

        if event_type == "tool_result":
            output = self._string_field(event, "output") or ""
            truncated_output = self._truncate(output, output_max_chars)
            yield StreamChunk(
                event_type="tool_result",
                call_id=self._string_field(event, "call_id"),
                tool_status=self._tool_status(event.get("status")),
                tool_output=truncated_output,
                tool_output_truncated=len(output) > len(truncated_output),
            )
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
    def _subprocess_env() -> dict[str, str]:
        return {key: value for key, value in os.environ.items() if key in ENV_ALLOWLIST}

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

    @staticmethod
    def _tool_status(value: object) -> Literal["ok", "error"]:
        return "error" if value == "error" else "ok"

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
