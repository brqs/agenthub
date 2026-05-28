"""Runtime budget helpers for external agent runtimes."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from app.agents.types import StreamChunk

DEFAULT_MAX_RUNTIME_SECONDS = 600.0
DEFAULT_IDLE_TIMEOUT_SECONDS = 180.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
CODEX_IDLE_TIMEOUT_SECONDS = 240.0

T = TypeVar("T")


@dataclass(frozen=True)
class RuntimeBudgetConfig:
    max_runtime_seconds: float = DEFAULT_MAX_RUNTIME_SECONDS
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS


class RuntimeTimeoutError(TimeoutError):
    """Raised when an external runtime exceeds its configured budget."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.stdout = stdout
        self.stderr = stderr


class RuntimeBudget:
    """Tracks hard and idle runtime deadlines and emits heartbeat chunks."""

    def __init__(self, config: RuntimeBudgetConfig) -> None:
        self.config = config
        self._loop = asyncio.get_running_loop()
        self.started_at = self._loop.time()
        self.last_activity_at = self.started_at
        self.last_heartbeat_at = self.started_at

    def record_activity(self) -> None:
        now = self._loop.time()
        self.last_activity_at = now

    def elapsed_seconds(self) -> float:
        return self._loop.time() - self.started_at

    def idle_seconds(self) -> float:
        return self._loop.time() - self.last_activity_at

    def next_wait_seconds(self) -> float:
        now = self._loop.time()
        remaining_hard = self.config.max_runtime_seconds - (now - self.started_at)
        remaining_idle = self.config.idle_timeout_seconds - (now - self.last_activity_at)
        remaining_heartbeat = self.config.heartbeat_interval_seconds - (
            now - self.last_heartbeat_at
        )
        return max(0.0, min(remaining_hard, remaining_idle, remaining_heartbeat))

    def check_timeout(self) -> None:
        if self.elapsed_seconds() >= self.config.max_runtime_seconds:
            raise RuntimeTimeoutError(
                "runtime_hard_timeout",
                "External runtime exceeded max_runtime_seconds",
            )
        if self.idle_seconds() >= self.config.idle_timeout_seconds:
            raise RuntimeTimeoutError(
                "runtime_idle_timeout",
                "External runtime exceeded idle_timeout_seconds",
            )

    def heartbeat(self, *, agent_id: str, provider: str) -> StreamChunk:
        self.last_heartbeat_at = self._loop.time()
        return StreamChunk(
            event_type="heartbeat",
            agent_id=agent_id,
            metadata={
                "provider": provider,
                "elapsed_seconds": round(self.elapsed_seconds(), 3),
                "idle_seconds": round(self.idle_seconds(), 3),
                "max_runtime_seconds": self.config.max_runtime_seconds,
                "idle_timeout_seconds": self.config.idle_timeout_seconds,
            },
        )


def runtime_budget_config(
    config: dict[str, Any],
    *,
    default_idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
    default_max_runtime_seconds: float = DEFAULT_MAX_RUNTIME_SECONDS,
    default_heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> RuntimeBudgetConfig:
    max_runtime = _float_config(
        config.get("max_runtime_seconds", config.get("timeout_seconds")),
        default_max_runtime_seconds,
    )
    idle_timeout = _float_config(
        config.get("idle_timeout_seconds"),
        default_idle_timeout_seconds,
    )
    heartbeat_interval = _float_config(
        config.get("heartbeat_interval_seconds"),
        default_heartbeat_interval_seconds,
    )
    if idle_timeout > max_runtime:
        idle_timeout = max_runtime
    return RuntimeBudgetConfig(
        max_runtime_seconds=max_runtime,
        idle_timeout_seconds=idle_timeout,
        heartbeat_interval_seconds=heartbeat_interval,
    )


async def iter_with_runtime_budget(
    source: AsyncIterator[T],
    budget: RuntimeBudget,
    *,
    agent_id: str,
    provider: str,
) -> AsyncIterator[T | StreamChunk]:
    """Iterate over an async source while emitting heartbeats during waits."""
    iterator = source.__aiter__()
    next_task: asyncio.Task[T] | None = asyncio.create_task(_next_item(iterator))
    try:
        while next_task is not None:
            done, _ = await asyncio.wait(
                {next_task},
                timeout=budget.next_wait_seconds(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if next_task in done:
                try:
                    item = next_task.result()
                except StopAsyncIteration:
                    return
                budget.record_activity()
                budget.check_timeout()
                yield item
                next_task = asyncio.create_task(_next_item(iterator))
                continue

            budget.check_timeout()
            yield cast(T | StreamChunk, budget.heartbeat(agent_id=agent_id, provider=provider))
    except BaseException:
        if next_task is not None and not next_task.done():
            next_task.cancel()
            with contextlib.suppress(BaseException):
                await next_task
        raise


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


async def _next_item(iterator: AsyncIterator[T]) -> T:
    return await anext(iterator)
