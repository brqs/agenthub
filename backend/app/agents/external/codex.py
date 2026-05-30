"""Codex external runtime adapter backed by Codex CLI, with SDK opt-in."""

from __future__ import annotations

import importlib
import inspect
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from app.agents.base import BaseAgentAdapter
from app.agents.external.cli_runtime import CliCompleted, stream_cli_text
from app.agents.external.direct_chat import maybe_stream_direct_chat
from app.agents.external.runtime_budget import (
    CODEX_IDLE_TIMEOUT_SECONDS,
    RuntimeBudgetConfig,
    RuntimeTimeoutError,
    runtime_budget_config,
)
from app.agents.external.runtime_prelude import (
    external_runtime_prelude,
    text_result_chunks,
)
from app.agents.external.runtime_utils import (
    classify_external_exception,
    external_error_chunk,
    safe_exception_message,
    safe_runtime_output,
    truncate,
)
from app.agents.external.sdk_stream import stream_sdk_events
from app.agents.external.workspace_prompt import (
    format_runtime_messages,
    workspace_guard_prompt,
)
from app.agents.runtime_guard import (
    redact_runtime_secrets,
    sanitize_preview_deploy_text,
)
from app.agents.types import ChatMessage, StreamChunk, ToolSpec

SDK_MODULE_NAME = "agents"
DEFAULT_MODEL = "gpt-4.1"
DEFAULT_TOOL_OUTPUT_MAX_CHARS = 4000
DEFAULT_RUNTIME_ERROR_MAX_CHARS = 4000
DEFAULT_RUNTIME = "cli"
DEFAULT_CLI_SANDBOX_MODE = "danger-full-access"
SUPPORTED_RUNTIMES = {"cli", "sdk"}
SUPPORTED_CLI_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}
TEXT_EVENT_NAMES = {
    "text_delta",
    "text",
    "output_text_delta",
    "response.output_text.delta",
}
TOOL_CALL_EVENT_NAMES = {
    "tool_call",
    "tool_use",
    "function_call",
    "function_tool_call",
    "response.output_item.added",
}
TOOL_RESULT_EVENT_NAMES = {
    "tool_result",
    "tool_call_output",
    "function_call_output",
    "tool_output_item",
}
SKIP_EVENT_NAMES = {
    "start",
    "done",
    "raw_response_event",
    "run_item_stream_event",
    "agent_updated_stream_event",
}

logger = logging.getLogger(__name__)


class CodexAdapter(BaseAgentAdapter):
    """Adapter for Codex CLI, with OpenAI Agents SDK as an opt-in runtime."""

    provider = "codex"

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
            workspace_error="Codex requires a workspace_path",
            error_chunk=self._error,
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
            default_idle_timeout_seconds=CODEX_IDLE_TIMEOUT_SECONDS,
        )
        output_max_chars = int(
            merged.get("tool_output_max_chars", DEFAULT_TOOL_OUTPUT_MAX_CHARS)
        )
        runtime = self._string_choice(
            merged.get("runtime"),
            DEFAULT_RUNTIME,
            SUPPORTED_RUNTIMES,
        )
        if runtime is None:
            yield self._error(
                "external_runtime_error",
                "Codex runtime must be one of: cli, sdk",
            )
            return

        if runtime == "cli":
            async for chunk in self._stream_cli(
                messages,
                system_prompt,
                merged,
                workspace_path,
                budget_config,
            ):
                yield chunk
            return

        try:
            sdk = self._load_sdk()
            sdk_stream = await self._open_sdk_stream(
                sdk,
                messages,
                system_prompt,
                workspace_path,
                merged,
            )
        except Exception as exc:  # noqa: BLE001
            if self._should_fallback_to_cli(exc):
                async for chunk in self._stream_cli(
                    messages,
                    system_prompt,
                    merged,
                    workspace_path,
                    budget_config,
                ):
                    yield chunk
                return
            yield self._error(self._classify_exception(exc), self._safe_message(exc))
            return

        async def exception_stream(
            exc: BaseException,
            saw_runtime_chunk: bool,
        ) -> AsyncIterator[StreamChunk]:
            if not saw_runtime_chunk and self._should_fallback_to_cli(exc):
                async for fallback_chunk in self._stream_cli(
                    messages,
                    system_prompt,
                    merged,
                    workspace_path,
                    budget_config,
                ):
                    yield fallback_chunk
                return
            yield self._error(self._classify_exception(exc), self._safe_message(exc))

        async for chunk in stream_sdk_events(
            sdk_stream,
            budget_config=budget_config,
            agent_id=self.agent_id,
            provider=self.provider,
            map_event=lambda event: self._map_sdk_event(event, output_max_chars),
            timeout_error_chunk=lambda exc: self._error(exc.error_code, str(exc)),
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
        budget_config: RuntimeBudgetConfig,
    ) -> AsyncIterator[StreamChunk]:
        output_path = workspace_path / f".agenthub_codex_{uuid4().hex}.txt"
        command = [
            "codex",
            "--ask-for-approval",
            "never",
            "exec",
            "--cd",
            str(workspace_path),
            "--skip-git-repo-check",
            "--sandbox",
            self._cli_sandbox_mode(config),
            "--ephemeral",
            "--color",
            "never",
            "-o",
            str(output_path),
            self._format_cli_prompt(messages, system_prompt, workspace_path),
        ]
        model = config.get("model")
        if isinstance(model, str) and model:
            command[1:1] = ["-m", model]

        result = None
        try:
            async for event in stream_cli_text(
                command,
                cwd=workspace_path,
                budget_config=budget_config,
                agent_id=self.agent_id,
                provider=self.provider,
                activity_paths=[output_path],
            ):
                if isinstance(event, StreamChunk):
                    yield event
                elif isinstance(event, CliCompleted):
                    result = event.result
        except RuntimeTimeoutError as exc:
            text = self._read_cli_output(output_path)
            if text:
                for chunk in self._text_result_chunks(text):
                    yield chunk
                return
            logger.warning(
                "Codex CLI timed out without output in workspace %s\nstdout:\n%s\nstderr:\n%s",
                workspace_path,
                redact_runtime_secrets(exc.stdout or ""),
                redact_runtime_secrets(exc.stderr or ""),
            )
            output = self._safe_runtime_output(exc.stderr or exc.stdout)
            yield self._error(exc.error_code, f"Codex CLI timed out: {output}")
            return
        except Exception as exc:  # noqa: BLE001
            output_path.unlink(missing_ok=True)
            logger.exception(
                "Codex CLI failed before producing a process result in workspace %s",
                workspace_path,
            )
            yield self._error("external_runtime_error", self._safe_message(exc))
            return

        if result is None:
            output_path.unlink(missing_ok=True)
            yield self._error("external_runtime_error", "Codex CLI ended without result")
            return

        text = self._read_cli_output(output_path)

        if result.return_code != 0:
            self._log_cli_failure(result, text, workspace_path)
            output = self._runtime_failure_output(result, text)
            yield self._error(
                "external_runtime_error",
                f"Codex CLI exited with code {result.return_code}: {output}",
            )
            return

        if not text:
            text = result.stdout.strip()

        if text:
            for chunk in self._text_result_chunks(text):
                yield chunk
            return
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=0)

    def _should_fallback_to_cli(self, exc: BaseException) -> bool:
        if isinstance(exc, ModuleNotFoundError) and exc.name == SDK_MODULE_NAME:
            return True
        lowered = f"{exc.__class__.__name__}: {exc}".lower()
        if (
            "missing credentials" in lowered
            or "openai_api_key" in lowered
            or "openai_admin_key" in lowered
        ):
            return True
        return (
            isinstance(exc, RuntimeError)
            and str(exc) == "OpenAI Agents SDK sandbox runtime is unavailable"
        )

    async def _open_sdk_stream(
        self,
        sdk: Any,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
        config: dict[str, Any],
    ) -> AsyncIterator[Any]:
        result = await self._start_run(sdk, messages, system_prompt, workspace_path, config)
        stream_events = getattr(result, "stream_events", None)
        if callable(stream_events):
            events = stream_events()
        else:
            events = result
        if inspect.isawaitable(events):
            events = await events
        return cast(AsyncIterator[Any], events)

    async def _start_run(
        self,
        sdk: Any,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
        config: dict[str, Any],
    ) -> Any:
        runner = self._sdk_attr(sdk, "Runner", "agents")
        agent_cls = self._sdk_attr(sdk, "SandboxAgent", "agents.sandbox")
        prompt = self._format_input(messages)
        run_config = self._build_run_config(sdk, workspace_path, config)

        if runner is not None and agent_cls is not None:
            agent = self._build_agent(
                agent_cls,
                messages,
                system_prompt,
                workspace_path,
                config,
            )
            run_streamed = runner.run_streamed
            kwargs = self._supported_kwargs(
                run_streamed,
                {
                    "input": prompt,
                    "run_config": run_config,
                },
            )
            result = run_streamed(agent, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        run_streamed = getattr(sdk, "run_streamed", None)
        if callable(run_streamed):
            kwargs = self._supported_kwargs(
                run_streamed,
                {
                    "input": prompt,
                    "messages": [message.model_dump() for message in messages],
                    "system_prompt": self._effective_instructions(
                        messages,
                        system_prompt,
                        workspace_path,
                    ),
                    "model": str(config.get("model") or DEFAULT_MODEL),
                    "run_config": run_config,
                },
            )
            result = run_streamed(**kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        raise RuntimeError("OpenAI Agents SDK does not expose a streaming runner")

    def _build_agent(
        self,
        agent_cls: Callable[..., Any],
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
        config: dict[str, Any],
    ) -> Any:
        kwargs = self._supported_kwargs(
            agent_cls,
            {
                "name": self.agent_id,
                "instructions": self._effective_instructions(
                    messages,
                    system_prompt,
                    workspace_path,
                ),
                "model": str(config.get("model") or DEFAULT_MODEL),
            },
        )
        return agent_cls(**kwargs)

    def _build_run_config(
        self,
        sdk: Any,
        workspace_path: Path,
        config: dict[str, Any],
    ) -> Any:
        manifest_cls = self._sdk_attr(sdk, "Manifest", "agents.sandbox")
        sandbox_run_config_cls = self._sdk_attr(
            sdk,
            "SandboxRunConfig",
            "agents.sandbox",
            "agents.run_config",
        )
        run_config_cls = self._sdk_attr(sdk, "RunConfig", "agents.run", "agents.run_config")
        client_cls = self._sdk_attr(
            sdk,
            "UnixLocalSandboxClient",
            "agents.sandbox.sandboxes.unix_local",
        )
        options_cls = self._sdk_attr(
            sdk,
            "UnixLocalSandboxClientOptions",
            "agents.sandbox.sandboxes.unix_local",
        )
        required_sdk_types = (
            manifest_cls,
            sandbox_run_config_cls,
            run_config_cls,
            client_cls,
            options_cls,
        )
        if any(sdk_type is None for sdk_type in required_sdk_types):
            raise RuntimeError("OpenAI Agents SDK sandbox runtime is unavailable")

        manifest = manifest_cls(root=str(workspace_path))
        sandbox_config = sandbox_run_config_cls(
            client=client_cls(),
            options=self._sandbox_options(options_cls, config),
            manifest=manifest,
        )
        return run_config_cls(
            model=str(config.get("model") or DEFAULT_MODEL),
            sandbox=sandbox_config,
            workflow_name="AgentHub Codex runtime",
        )

    def _sdk_attr(self, sdk: Any, name: str, *module_names: str) -> Any:
        value = getattr(sdk, name, None)
        if value is not None:
            return value
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue
            value = getattr(module, name, None)
            if value is not None:
                return value
        return None

    def _map_sdk_event(
        self,
        event: Any,
        output_max_chars: int,
    ) -> list[StreamChunk]:
        nested = self._nested_event(event)
        if nested is not None:
            chunks = self._map_sdk_event(nested, output_max_chars)
            if chunks:
                return chunks

        event_name = self._event_name(event)
        if self._is_tool_call(event_name, event):
            return [self._tool_call_chunk(event)]
        if self._is_tool_result(event_name, event):
            return [self._tool_result_chunk(event, output_max_chars)]
        if event_name in SKIP_EVENT_NAMES:
            return []

        text = self._text_delta(event, event_name)
        if text is None:
            return []
        return [StreamChunk(event_type="delta", text_delta=text)]

    def _nested_event(self, event: Any) -> Any | None:
        for name in ("data", "item"):
            nested = self._field(event, (name,))
            if nested is not None and nested is not event:
                return nested
        return None

    def _event_name(self, event: Any) -> str:
        value = self._field(event, ("type", "event_type", "kind"))
        if isinstance(value, str):
            return value.lower()
        return type(event).__name__.lower()

    def _is_tool_call(self, event_name: str, event: Any) -> bool:
        item_type = self._string_field(event, ("item_type", "type"))
        return event_name in TOOL_CALL_EVENT_NAMES or item_type == "tool_call_item"

    def _is_tool_result(self, event_name: str, event: Any) -> bool:
        item_type = self._string_field(event, ("item_type", "type"))
        return event_name in TOOL_RESULT_EVENT_NAMES or item_type == "tool_call_output_item"

    def _text_delta(self, event: Any, event_name: str) -> str | None:
        if event_name not in TEXT_EVENT_NAMES and not event_name.endswith("text.delta"):
            return None
        value = self._field(event, ("text_delta", "delta", "text"))
        return value if isinstance(value, str) and value else None

    def _tool_call_chunk(self, event: Any) -> StreamChunk:
        return StreamChunk(
            event_type="tool_call",
            call_id=self._string_field_deep(event, ("call_id", "id", "tool_call_id")),
            tool_name=self._string_field_deep(event, ("tool_name", "name")),
            tool_arguments=self._arguments_field(event),
        )

    def _tool_result_chunk(self, event: Any, output_max_chars: int) -> StreamChunk:
        output = self._tool_output(event)
        truncated_output = self._truncate(output, output_max_chars) if output is not None else None
        return StreamChunk(
            event_type="tool_result",
            call_id=self._string_field_deep(event, ("call_id", "tool_call_id", "id")),
            tool_status=self._tool_status(event),
            tool_output=truncated_output,
            tool_output_truncated=(
                None
                if output is None or truncated_output is None
                else len(output) > len(truncated_output)
            ),
        )

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
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    def _string_field_deep(self, event: Any, names: tuple[str, ...]) -> str | None:
        for candidate in self._field_candidates(event):
            value = self._string_field(candidate, names)
            if value is not None:
                return value
        return None

    def _field_deep(self, event: Any, names: tuple[str, ...]) -> Any:
        for candidate in self._field_candidates(event):
            value = self._field(candidate, names)
            if value is not None:
                return value
        return None

    def _field_candidates(self, event: Any) -> list[Any]:
        candidates = [event]
        for name in ("raw_item", "item", "data"):
            nested = self._field(event, (name,))
            if nested is not None and nested is not event:
                candidates.append(nested)
        return candidates

    def _arguments_field(self, event: Any) -> dict[str, Any]:
        value = self._field_deep(event, ("tool_arguments", "arguments", "input"))
        if isinstance(value, Mapping):
            return dict(value)
        if not isinstance(value, str) or not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        if isinstance(parsed, Mapping):
            return dict(parsed)
        return {"value": parsed}

    def _tool_status(self, event: Any) -> Literal["ok", "error"]:
        status = self._field_deep(event, ("tool_status", "status"))
        if status == "error":
            return "error"
        is_error = self._field_deep(event, ("is_error", "error"))
        return "error" if is_error is True else "ok"

    def _tool_output(self, event: Any) -> str | None:
        value = self._field_deep(event, ("tool_output", "output", "result", "content"))
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, Iterable) and not isinstance(value, Mapping):
            return "".join(str(item) for item in value)
        return json.dumps(value, ensure_ascii=False) if isinstance(value, Mapping) else str(value)

    def _runtime_options(self, config: dict[str, Any]) -> dict[str, Any]:
        options = config.get("runtime_options", {})
        return dict(options) if isinstance(options, Mapping) else {}

    def _sandbox_options(self, options_cls: Callable[..., Any], config: dict[str, Any]) -> Any:
        runtime_options = self._runtime_options(config)
        exposed_ports = runtime_options.get("exposed_ports", ())
        if not isinstance(exposed_ports, tuple):
            if isinstance(exposed_ports, list):
                exposed_ports = tuple(int(port) for port in exposed_ports)
            else:
                exposed_ports = ()
        return options_cls(exposed_ports=exposed_ports)

    def _effective_instructions(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
    ) -> str:
        lines: list[str] = [workspace_guard_prompt(workspace_path)]
        effective_system = self.effective_system_prompt(system_prompt)
        if effective_system:
            lines.append(effective_system)
        lines.extend(message.content for message in messages if message.role == "system")
        return "\n\n".join(lines)

    def _format_input(self, messages: list[ChatMessage]) -> str:
        return format_runtime_messages(messages, include_system=False)

    def _format_cli_prompt(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None,
        workspace_path: Path,
    ) -> str:
        instructions = self._effective_instructions(
            messages,
            system_prompt,
            workspace_path,
        )
        user_input = self._format_input(messages)
        if instructions and user_input:
            return f"System: {instructions}\n\n{user_input}"
        return instructions or user_input

    def _supported_kwargs(
        self,
        callable_obj: Callable[..., Any],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            signature = inspect.signature(callable_obj)
        except (TypeError, ValueError):
            return kwargs
        parameters = signature.parameters.values()
        if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
            return kwargs
        names = set(signature.parameters)
        return {key: value for key, value in kwargs.items() if key in names}

    @staticmethod
    def _string_choice(
        value: object,
        default: str,
        allowed: set[str],
    ) -> str | None:
        if value is None:
            return default
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        return normalized if normalized in allowed else None

    def _cli_sandbox_mode(self, config: dict[str, Any]) -> str:
        mode = self._string_choice(
            config.get("sandbox_mode"),
            DEFAULT_CLI_SANDBOX_MODE,
            SUPPORTED_CLI_SANDBOX_MODES,
        )
        return mode or DEFAULT_CLI_SANDBOX_MODE

    @staticmethod
    def _read_cli_output(output_path: Path) -> str:
        try:
            return output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        finally:
            output_path.unlink(missing_ok=True)

    def _text_result_chunks(self, text: str) -> list[StreamChunk]:
        return text_result_chunks(sanitize_preview_deploy_text(text), self.agent_id)

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

    def _classify_exception(self, exc: BaseException) -> str:
        return classify_external_exception(exc)

    @staticmethod
    def _safe_message(exc: BaseException) -> str:
        return safe_exception_message(exc)

    def _runtime_failure_output(self, result: Any, output_file_text: str) -> str:
        sections: list[str] = []
        if result.stderr and result.stderr.strip():
            sections.append(f"stderr:\n{result.stderr.strip()}")
        if result.stdout and result.stdout.strip():
            sections.append(f"stdout:\n{result.stdout.strip()}")
        if output_file_text and output_file_text.strip():
            sections.append(f"output_file:\n{output_file_text.strip()}")
        return self._safe_runtime_output("\n\n".join(sections))

    @staticmethod
    def _safe_runtime_output(output: str) -> str:
        return safe_runtime_output(
            output,
            max_chars=DEFAULT_RUNTIME_ERROR_MAX_CHARS,
        )

    def _log_cli_failure(
        self,
        result: Any,
        output_file_text: str,
        workspace_path: Path,
    ) -> None:
        logger.error(
            "Codex CLI exited with code %s in workspace %s\n"
            "stdout:\n%s\n"
            "stderr:\n%s\n"
            "output_last_message:\n%s",
            result.return_code,
            workspace_path,
            redact_runtime_secrets(result.stdout or ""),
            redact_runtime_secrets(result.stderr or ""),
            redact_runtime_secrets(output_file_text or ""),
        )
