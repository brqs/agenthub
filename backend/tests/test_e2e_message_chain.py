"""End-to-end message chain tests.

Covers: user send → agent stream → DB persist → SSE delivery.
Uses FakeAdapter + monkeypatched get_adapter, no real LLM calls.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.agents.types import StreamChunk
from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.main import app
from app.models.agent import Agent
from app.models.message import Message

pytestmark = pytest.mark.asyncio(loop_scope="module")

PREFIX = "e2echain"


# ── Fixtures ──


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with SessionFactory() as db:
        await db.execute(
            text(
                "DELETE FROM messages WHERE conversation_id IN "
                "(SELECT id FROM conversations WHERE title LIKE :p)"
            ),
            {"p": f"%{PREFIX}%"},
        )
        await db.execute(
            text("DELETE FROM conversations WHERE title LIKE :p"),
            {"p": f"%{PREFIX}%"},
        )
        await db.execute(text(f"DELETE FROM agents WHERE id LIKE '{PREFIX}-%'"))
        await db.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def workspace_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "workspaces"))
    monkeypatch.setattr(settings, "workspace_max_read_bytes", 1024 * 1024)


# ── Helpers ──


async def _register(
    client: AsyncClient,
) -> tuple[dict[str, Any], dict[str, str]]:
    username = f"{PREFIX}_{uuid4().hex[:16]}"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "P@ssw0rd!"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def _insert_agent() -> str:
    agent_id = f"{PREFIX}-{uuid4().hex[:8]}"
    async with SessionFactory() as db:
        db.add(
            Agent(
                id=agent_id,
                name=f"Test Agent {agent_id}",
                provider="mock",
                avatar_url="/avatars/test.png",
                capabilities=["testing"],
                config={},
                is_builtin=True,
            )
        )
        await db.commit()
    return agent_id


async def _create_conversation(
    client: AsyncClient, headers: dict[str, str], agent_ids: list[str]
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={
            "title": f"Test {uuid4().hex[:8]}",
            "mode": "single" if len(agent_ids) == 1 else "group",
            "agent_ids": agent_ids,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conv_id: str,
    *,
    text: str = "hello",
    target_agent_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if target_agent_id is not None:
        payload["target_agent_id"] = target_agent_id
    resp = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers,
        json=payload,
    )
    return resp.json()


async def _stream_sse(
    client: AsyncClient, headers: dict[str, str], msg_id: str
) -> tuple[int, list[dict[str, str]]]:
    """Return (status_code, list_of_parsed_sse_events)."""
    events: list[dict[str, str]] = []
    async with client.stream(
        "GET", f"/api/v1/messages/{msg_id}/stream", headers=headers
    ) as resp:
        status = resp.status_code
        raw = (await resp.aread()).decode()
    # Normalize line endings: SSE uses \r\n or \n
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    for block in raw.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = ""
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if event_type:
            events.append({"event": event_type, "data": data})
    return status, events


async def _stored_message(msg_id: str) -> Message:
    async with SessionFactory() as db:
        msg = await db.get(Message, UUID(msg_id))
    assert msg is not None
    return msg


# ── Fake Adapters ──


class TextOnlyAdapter:
    """Yields a single text block."""

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id="test")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="Hello from agent")
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="test", total_blocks=1)


class MultiBlockAdapter:
    """Yields text + code blocks."""

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id="test")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="Here is code:")
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(
            event_type="block_start",
            block_index=1,
            block_type="code",
            metadata={"language": "python"},
        )
        yield StreamChunk(event_type="delta", block_index=1, code_delta="print('hi')")
        yield StreamChunk(event_type="block_end", block_index=1)
        yield StreamChunk(event_type="done", agent_id="test", total_blocks=2)


class ToolCallAdapter:
    """Yields tool_call + tool_result + text."""

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id="test")
        yield StreamChunk(
            event_type="tool_call",
            call_id="call-001",
            tool_name="read_file",
            tool_arguments={"path": "hello.txt"},
        )
        yield StreamChunk(
            event_type="tool_result",
            call_id="call-001",
            tool_status="ok",
            tool_output="file contents here",
        )
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta", block_index=0, text_delta="I read the file."
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="test", total_blocks=1)


class ErrorAfterTextAdapter:
    """Yields partial text then an error."""

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id="test")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta="Partial...")
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(
            event_type="error",
            agent_id="test",
            error_code="upstream_error",
            error="LLM exploded",
        )


class ExplodingAdapter:
    """Raises an exception during stream."""

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(event_type="start", agent_id="test")
        raise RuntimeError("adapter boom")


class FileWritingAdapter:
    """Writes a file to workspace_path during stream."""

    async def stream(
        self,
        messages: list[Any],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if workspace_path:
            out = workspace_path / "output.txt"
            out.write_text("agent created this file")
        yield StreamChunk(event_type="start", agent_id="test")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(
            event_type="delta", block_index=0, text_delta="File written."
        )
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id="test", total_blocks=1)


def _mock_get_adapter(adapter: Any):
    async def _get(agent_id: str, db: Any) -> Any:
        return adapter

    return _get


# ── Tests ──


class TestFullChainTextResponse:
    async def test_full_message_chain_text_response(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """User send → agent text block → SSE complete → DB done."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        monkeypatch.setattr(
            "app.api.v1.stream.get_adapter", _mock_get_adapter(TextOnlyAdapter())
        )

        send_resp = await _send_message(client, headers, conv["id"])
        assert send_resp["agent_message"]["status"] == "pending"
        msg_id = send_resp["agent_message"]["id"]

        status, events = await _stream_sse(client, headers, msg_id)
        assert status == 200

        event_types = [e["event"] for e in events]
        assert event_types[0] == "start"
        assert event_types[-1] == "done"

        stored = await _stored_message(msg_id)
        assert stored.status == "done"
        blocks = stored.content
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert "Hello from agent" in blocks[0]["text"]


class TestFullChainMultiBlock:
    async def test_full_message_chain_multi_block(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Agent returns text + code → DB has 2 blocks."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        monkeypatch.setattr(
            "app.api.v1.stream.get_adapter", _mock_get_adapter(MultiBlockAdapter())
        )

        send_resp = await _send_message(client, headers, conv["id"])
        msg_id = send_resp["agent_message"]["id"]

        _, events = await _stream_sse(client, headers, msg_id)
        event_types = [e["event"] for e in events]
        assert event_types[-1] == "done"

        stored = await _stored_message(msg_id)
        assert stored.status == "done"
        blocks = stored.content
        assert len(blocks) == 2
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "code"
        assert blocks[1]["language"] == "python"


class TestFullChainToolCalls:
    async def test_full_message_chain_with_tool_calls(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Agent emits tool_call + tool_result → DB has ToolCallBlock with paired call_id."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        monkeypatch.setattr(
            "app.api.v1.stream.get_adapter", _mock_get_adapter(ToolCallAdapter())
        )

        send_resp = await _send_message(client, headers, conv["id"])
        msg_id = send_resp["agent_message"]["id"]

        _, events = await _stream_sse(client, headers, msg_id)
        event_types = [e["event"] for e in events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert event_types[-1] == "done"

        stored = await _stored_message(msg_id)
        assert stored.status == "done"
        blocks = stored.content
        tool_blocks = [b for b in blocks if b["type"] == "tool_call"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["call_id"] == "call-001"
        assert tool_blocks[0]["tool_name"] == "read_file"
        assert tool_blocks[0]["status"] == "ok"


class TestFullChainAgentError:
    async def test_full_message_chain_agent_error(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Agent yields error chunk → DB status "error", prior content preserved."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        monkeypatch.setattr(
            "app.api.v1.stream.get_adapter", _mock_get_adapter(ErrorAfterTextAdapter())
        )

        send_resp = await _send_message(client, headers, conv["id"])
        msg_id = send_resp["agent_message"]["id"]

        _, events = await _stream_sse(client, headers, msg_id)
        event_types = [e["event"] for e in events]
        assert event_types[-1] == "error"

        stored = await _stored_message(msg_id)
        assert stored.status == "error"
        # Prior text block content should be preserved
        blocks = stored.content
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert "Partial..." in blocks[0]["text"]


class TestFullChainAdapterException:
    async def test_full_message_chain_adapter_exception(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Adapter raises exception → DB status "error", SSE returns internal_error."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        monkeypatch.setattr(
            "app.api.v1.stream.get_adapter", _mock_get_adapter(ExplodingAdapter())
        )

        send_resp = await _send_message(client, headers, conv["id"])
        msg_id = send_resp["agent_message"]["id"]

        _, events = await _stream_sse(client, headers, msg_id)
        event_types = [e["event"] for e in events]
        assert event_types[-1] == "error"

        error_event = [e for e in events if e["event"] == "error"][0]
        error_data = json.loads(error_event["data"])
        assert error_data["error_code"] == "internal_error"

        stored = await _stored_message(msg_id)
        assert stored.status == "error"


class TestConversationBusy:
    async def test_conversation_busy_rejects_concurrent_message(
        self,
        client: AsyncClient,
    ) -> None:
        """Sending a message while agent is pending returns 409 CONVERSATION_BUSY."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        # First message creates a pending agent message
        first = await _send_message(client, headers, conv["id"])
        assert first["agent_message"]["status"] == "pending"

        # Second message should be rejected
        payload = {"content": [{"type": "text", "text": "second"}]}
        resp = await client.post(
            f"/api/v1/conversations/{conv['id']}/messages",
            headers=headers,
            json=payload,
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["detail"]["error"]["code"] == "CONVERSATION_BUSY"


class TestFullChainAgentWritesFile:
    async def test_full_message_chain_agent_writes_file(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Agent writes file to workspace → file accessible via workspace API."""
        _, headers = await _register(client)
        agent_id = await _insert_agent()
        conv = await _create_conversation(client, headers, [agent_id])

        monkeypatch.setattr(
            "app.api.v1.stream.get_adapter", _mock_get_adapter(FileWritingAdapter())
        )

        send_resp = await _send_message(client, headers, conv["id"])
        msg_id = send_resp["agent_message"]["id"]

        _, events = await _stream_sse(client, headers, msg_id)
        event_types = [e["event"] for e in events]
        assert event_types[-1] == "done"

        stored = await _stored_message(msg_id)
        assert stored.status == "done"

        # Verify file exists in workspace via API
        tree_resp = await client.get(
            f"/api/v1/workspaces/{conv['id']}/tree", headers=headers
        )
        assert tree_resp.status_code == 200
        tree = tree_resp.json()
        # tree structure: {root, tree: {name, type, children: [...]}}
        root_node = tree["tree"]
        filenames = [c["name"] for c in root_node.get("children", [])]
        assert "output.txt" in filenames

        # Read file content
        file_resp = await client.get(
            f"/api/v1/workspaces/{conv['id']}/files/output.txt", headers=headers
        )
        assert file_resp.status_code == 200
        assert "agent created this file" in file_resp.text
