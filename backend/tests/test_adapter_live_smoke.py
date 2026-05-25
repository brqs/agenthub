"""Optional live provider smoke tests — skipped by default."""

from __future__ import annotations

import os
from collections.abc import Callable
from importlib import import_module
from typing import Any, Protocol, cast

import pytest

from app.agents.adapters.claude import ClaudeAdapter
from app.agents.adapters.deepseek import DeepSeekAdapter
from app.agents.adapters.openai import OpenAIAdapter
from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk

pytestmark = pytest.mark.slow


# ─── Helpers (duplicated minimally to avoid cross-test import fragility) ───


class _ContentAccumulatorProtocol(Protocol):
    def feed(self, chunk: StreamChunk) -> None: ...

    def to_list(self) -> object: ...


def _new_content_accumulator() -> _ContentAccumulatorProtocol:
    stream_module = import_module("app.api.v1.stream")
    accumulator_name = "_ContentAccumulator"
    factory = cast(
        Callable[[], _ContentAccumulatorProtocol],
        getattr(stream_module, accumulator_name),
    )
    return factory()


def _skip_if_no_live() -> None:
    if os.environ.get("AGENTHUB_RUN_LIVE_PROVIDER_TESTS") != "1":
        pytest.skip("AGENTHUB_RUN_LIVE_PROVIDER_TESTS is not set")


def _skip_if_no_key(key: str) -> None:
    if not os.environ.get(key):
        pytest.skip(f"{key} not set")


async def _collect(
    adapter: BaseAgentAdapter,
    messages: list[ChatMessage],
    config: dict[str, Any] | None = None,
) -> list[StreamChunk]:
    return [chunk async for chunk in adapter.stream(messages, config=config)]


def _assert_stream_contract(chunks: list[StreamChunk]) -> None:
    assert len(chunks) >= 1
    assert chunks[0].event_type == "start"

    last = chunks[-1]
    assert last.event_type in ("done", "error")

    open_blocks: set[int] = set()
    block_count = 0
    has_error = any(c.event_type == "error" for c in chunks)

    for chunk in chunks:
        sse = chunk.to_sse()
        assert "event" in sse
        assert "data" in sse

        if chunk.event_type == "block_start":
            assert chunk.block_index is not None
            assert len(open_blocks) == 0, (
                f"block_start while blocks still open: {open_blocks}"
            )
            open_blocks.add(chunk.block_index)
            block_count += 1
        elif chunk.event_type == "block_end":
            assert chunk.block_index is not None
            assert chunk.block_index in open_blocks
            open_blocks.remove(chunk.block_index)
        elif chunk.event_type == "delta":
            assert chunk.block_index is not None
            assert chunk.block_index in open_blocks

    assert len(open_blocks) == 0, f"Unclosed blocks: {open_blocks}"

    if last.event_type == "done":
        assert not has_error, "error chunk appeared before done"
        assert last.total_blocks == block_count


def _accumulate_content(chunks: list[StreamChunk]) -> list[dict[str, Any]]:
    acc = _new_content_accumulator()
    for chunk in chunks:
        acc.feed(chunk)
    return cast(list[dict[str, Any]], acc.to_list())


# ─── Live tests ───


class TestClaudeLiveSmoke:
    async def test_claude_live_smoke(self) -> None:
        _skip_if_no_live()
        _skip_if_no_key("ANTHROPIC_API_KEY")

        adapter = ClaudeAdapter(agent_id="live-claude")
        chunks = await _collect(
            adapter,
            messages=[
                ChatMessage(role="user", content="Reply with exactly one short sentence.")
            ],
            config={"max_tokens": 64},
        )
        _assert_stream_contract(chunks)
        blocks = _accumulate_content(chunks)
        assert any(b.get("type") == "text" and b.get("text") for b in blocks)
        assert len(blocks) == chunks[-1].total_blocks


class TestOpenAILiveSmoke:
    async def test_openai_live_smoke(self) -> None:
        _skip_if_no_live()
        _skip_if_no_key("OPENAI_API_KEY")

        adapter = OpenAIAdapter(agent_id="live-openai")
        chunks = await _collect(
            adapter,
            messages=[
                ChatMessage(role="user", content="Reply with exactly one short sentence.")
            ],
            config={"max_tokens": 64},
        )
        _assert_stream_contract(chunks)
        blocks = _accumulate_content(chunks)
        assert any(b.get("type") == "text" and b.get("text") for b in blocks)
        assert len(blocks) == chunks[-1].total_blocks


class TestDeepSeekLiveSmoke:
    async def test_deepseek_live_smoke(self) -> None:
        _skip_if_no_live()
        _skip_if_no_key("DEEPSEEK_API_KEY")

        adapter = DeepSeekAdapter(agent_id="live-deepseek")
        chunks = await _collect(
            adapter,
            messages=[
                ChatMessage(role="user", content="Reply with exactly one short sentence.")
            ],
            config={"max_tokens": 64},
        )
        _assert_stream_contract(chunks)
        blocks = _accumulate_content(chunks)
        assert any(b.get("type") == "text" and b.get("text") for b in blocks)
        assert len(blocks) == chunks[-1].total_blocks
