"""Tests for OrchestratorAdapter injection-based dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.orchestrator import OrchestratorAdapter
from app.agents.registry import get_adapter
from app.agents.types import ChatMessage, StreamChunk, ToolSpec
from app.models.agent import Agent


async def _collect(
    adapter: OrchestratorAdapter,
    config: dict[str, Any] | None = None,
    messages: list[ChatMessage] | None = None,
    workspace_path: Path | None = None,
) -> list[StreamChunk]:
    return [
        chunk
        async for chunk in adapter.stream(
            messages=messages or [ChatMessage(role="user", content="Build a todo app")],
            config=config,
            workspace_path=workspace_path,
        )
    ]


def _assert_blocks_balanced(chunks: list[StreamChunk]) -> None:
    stack: list[int] = []
    for chunk in chunks:
        if chunk.event_type == "block_start" and chunk.block_index is not None:
            stack.append(chunk.block_index)
        elif chunk.event_type == "block_end" and chunk.block_index is not None:
            assert stack, f"Unexpected block_end for block_index={chunk.block_index}"
            assert (
                stack.pop() == chunk.block_index
            ), f"Mismatched block_end for block_index={chunk.block_index}"
    assert not stack, f"Unclosed blocks: {stack}"


class FakeSubAdapter(BaseAgentAdapter):
    provider = "fake"

    def __init__(
        self,
        agent_id: str,
        chunks: list[StreamChunk],
        system_prompt: str | None = "fake prompt",
    ) -> None:
        super().__init__(agent_id=agent_id, system_prompt=system_prompt)
        self._chunks = chunks
        self.received_messages: list[ChatMessage] = []
        self.received_system_prompt: str | None = None
        self.received_config: dict[str, Any] | None = None

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        self.received_config = config
        for chunk in self._chunks:
            yield chunk


class FakePartialThenExceptionAdapter(BaseAgentAdapter):
    """Yields some chunks then raises an exception mid-stream."""

    provider = "fake"

    def __init__(self, agent_id: str, chunks: list[StreamChunk], exc: Exception) -> None:
        super().__init__(agent_id=agent_id)
        self._chunks = chunks
        self._exc = exc

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        for chunk in self._chunks:
            yield chunk
        raise self._exc


class FakeWorkspaceWriterAdapter(FakeSubAdapter):
    def __init__(
        self,
        agent_id: str,
        chunks: list[StreamChunk],
        write_path: str,
        content: str = "ok",
    ) -> None:
        super().__init__(agent_id, chunks)
        self.write_path = write_path
        self.content = content

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if workspace_path is not None:
            target = workspace_path / self.write_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.content, encoding="utf-8")
        async for chunk in super().stream(
            messages,
            system_prompt=system_prompt,
            config=config,
            workspace_path=workspace_path,
            tool_specs=tool_specs,
        ):
            yield chunk


class FakeWorkspaceVerifierAdapter(FakeSubAdapter):
    def __init__(self, agent_id: str, verify_path: str) -> None:
        super().__init__(agent_id, [])
        self.verify_path = verify_path
        self.verified_content = ""

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received_messages = messages
        self.received_system_prompt = system_prompt
        self.received_config = config
        target = workspace_path / self.verify_path if workspace_path else None
        self.verified_content = target.read_text(encoding="utf-8") if target else ""
        checks = {
            "title": "Orchestrator Flow Smoke Test" in self.verified_content,
            "input": "<input" in self.verified_content,
            "button": "<button" in self.verified_content,
            "display": "textContent" in self.verified_content,
        }
        result = (
            f"Checked {self.verify_path}: "
            f"title={checks['title']}, input={checks['input']}, "
            f"button={checks['button']}, display={checks['display']}"
        )
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        yield StreamChunk(
            event_type="tool_call",
            call_id="verify-1",
            tool_name="read_file",
            tool_arguments={"path": self.verify_path},
        )
        yield StreamChunk(
            event_type="tool_result",
            call_id="verify-1",
            tool_status="ok" if all(checks.values()) else "error",
            tool_output=result,
        )
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0, text_delta=result)
        yield StreamChunk(event_type="block_end", block_index=0)
        yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=1)


class FakePlannerGateway:
    def __init__(self, chunks: list[StreamChunk]) -> None:
        self._chunks = chunks
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "config": config,
                "tools": tools,
            }
        )
        for chunk in self._chunks:
            yield chunk


class FakeAnswerGateway(FakePlannerGateway):
    pass


class SequencedGateway:
    def __init__(self, chunk_sequences: list[list[StreamChunk]]) -> None:
        self._chunk_sequences = chunk_sequences
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "config": config,
                "tools": tools,
            }
        )
        index = len(self.calls) - 1
        chunks = self._chunk_sequences[index] if index < len(self._chunk_sequences) else []
        for chunk in chunks:
            yield chunk


def _react_decision_chunks(payload: str) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="react"),
        StreamChunk(event_type="delta", text_delta=payload),
        StreamChunk(event_type="done", agent_id="react"),
    ]


def _task(
    task_id: str,
    agent_id: str,
    title: str,
    instruction: str,
    priority: int = 0,
    depends_on: list[str] | None = None,
    expected_output: str | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    task = {
        "task_id": task_id,
        "agent_id": agent_id,
        "title": title,
        "instruction": instruction,
        "depends_on": depends_on or [],
        "priority": priority,
        "include_history": include_history,
    }
    if expected_output is not None:
        task["expected_output"] = expected_output
    return task


def _text_chunks(text: str, block_index: int = 0) -> list[StreamChunk]:
    return [
        StreamChunk(event_type="start", agent_id="sub-agent"),
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
        ),
        StreamChunk(event_type="delta", block_index=block_index, text_delta=text),
        StreamChunk(event_type="block_end", block_index=block_index),
        StreamChunk(event_type="done", agent_id="sub-agent", total_blocks=1),
    ]


async def test_orchestrator_emits_planning_agent_switch_subagent_and_summary() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("backend done"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("frontend done"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-b", "agent-b", "Frontend UI", "Build UI", priority=2),
                _task("task-a", "agent-a", "Backend API", "Build API", priority=1),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[0].event_type == "start"
    assert chunks[-1].event_type == "done"
    assert [chunk.event_type for chunk in chunks].count("start") == 1
    assert [chunk.event_type for chunk in chunks].count("done") == 1
    assert any(
        chunk.event_type == "delta" and "Planned 2 sub-task(s)" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert [
        (chunk.from_agent, chunk.to_agent, chunk.task)
        for chunk in chunks
        if chunk.event_type == "agent_switch"
    ] == [
        ("orchestrator", "agent-a", "Backend API"),
        ("orchestrator", "agent-b", "Frontend UI"),
    ]
    assert any(chunk.text_delta == "backend done" for chunk in chunks)
    assert any(chunk.text_delta == "frontend done" for chunk in chunks)
    assert any("Execution summary" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_remaps_block_indices_without_collisions() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a", block_index=0))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b", block_index=0))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    block_starts = [
        chunk.block_index for chunk in chunks if chunk.event_type == "block_start"
    ]
    assert block_starts == list(range(len(block_starts)))

    started = set(block_starts)
    for chunk in chunks:
        if chunk.event_type in {"delta", "block_end"} and chunk.block_index is not None:
            assert chunk.block_index in started

    a_delta = next(chunk for chunk in chunks if chunk.text_delta == "from a")
    b_delta = next(chunk for chunk in chunks if chunk.text_delta == "from b")
    assert a_delta.block_index != b_delta.block_index
    _assert_blocks_balanced(chunks)


async def test_orchestrator_preserves_subagent_metadata_and_delta_fields() -> None:
    sub_chunks = [
        StreamChunk(event_type="start", agent_id="agent-a"),
        StreamChunk(
            event_type="block_start",
            block_index=3,
            block_type="code",
            metadata={"language": "python", "filename": "app.py"},
        ),
        StreamChunk(event_type="delta", block_index=3, code_delta="print('ok')\n"),
        StreamChunk(event_type="block_end", block_index=3),
        StreamChunk(event_type="block_start", block_index=7, block_type="text"),
        StreamChunk(event_type="delta", block_index=7, text_delta="notes"),
        StreamChunk(event_type="block_end", block_index=7),
        StreamChunk(event_type="done", agent_id="agent-a", total_blocks=2),
    ]
    adapter_a = FakeSubAdapter("agent-a", sub_chunks)
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Code", "Write code")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    code_start = next(chunk for chunk in chunks if chunk.block_type == "code")
    code_delta = next(chunk for chunk in chunks if chunk.code_delta is not None)
    text_delta = next(chunk for chunk in chunks if chunk.text_delta == "notes")

    assert code_start.metadata == {"language": "python", "filename": "app.py"}
    assert code_delta.code_delta == "print('ok')\n"
    assert code_delta.block_index == code_start.block_index
    assert text_delta.block_index != code_start.block_index


async def test_orchestrator_does_not_require_database() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("factory result"))
    factory_calls: list[str] = []

    async def adapter_factory(agent_id: str) -> BaseAgentAdapter:
        factory_calls.append(agent_id)
        return adapter_a

    messages = [ChatMessage(role="user", content="Initial request")]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Injected task")],
            "adapter_factory": adapter_factory,
        },
    )

    assert chunks[-1].event_type == "done"
    assert factory_calls == ["agent-a"]
    assert adapter_a.received_messages == [
        ChatMessage(role="user", content="Initial request"),
        ChatMessage(role="user", content="Injected task"),
    ]
    assert adapter_a.received_system_prompt is None
    assert adapter_a.received_config is None


async def test_orchestrator_derives_tasks_from_managed_agents() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("analysis done"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("implementation done"))
    messages = [ChatMessage(role="user", content="Build a calendar app")]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "managed_agent_ids": ["orchestrator", "agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert adapter_a.received_messages[-1].content.startswith("Analyze the user's request")
    assert "Build a calendar app" in adapter_b.received_messages[-1].content


async def test_orchestrator_derives_direct_tasks_for_named_agents() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("claude response"))
    opencode = FakeSubAdapter("opencode-helper", _text_chunks("opencode response"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex response"))
    planner = FakePlannerGateway([])
    messages = [
        ChatMessage(
            role="user",
            content=(
                '@orchestrator send claude code, opencode, and codex the same message '
                '"hello, what model are you?" and return their outputs'
            ),
        )
    ]
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=messages,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": [
                "claude-code",
                "codex-helper",
                "opencode-helper",
            ],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
                "opencode-helper": opencode,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "opencode-helper", "codex-helper"]
    assert planner.calls == []
    assert all(
        chunk.event_type != "delta" or "Analyze request" not in (chunk.text_delta or "")
        for chunk in chunks
    )

    assert len(claude.received_messages) == 1
    assert len(opencode.received_messages) == 2
    assert len(codex.received_messages) == 2

    for adapter in (claude, opencode, codex):
        instruction = adapter.received_messages[-1].content
        assert "Message:\nhello, what model are you?" in instruction
        assert "@orchestrator" not in instruction
        assert "Do not contact, invoke, or simulate other agents" in instruction


async def test_orchestrator_answers_meta_question_without_planner() -> None:
    planner = FakePlannerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="planner used")]
    )
    answer = FakeAnswerGateway(_text_chunks("我是 AgentHub Orchestrator。"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 你是什么模型")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "managed_agent_ids": ["claude-code", "codex-helper"],
        },
    )

    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert answer.calls == []
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert any(
        chunk.event_type == "delta" and "AgentHub Orchestrator" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_answers_group_agents_from_conversation_context() -> None:
    planner = FakePlannerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="planner used")]
    )
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 当前群聊有哪些 agent")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                    "is_builtin": True,
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "is_builtin": True,
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli", "files"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["claude-code", "codex-helper", "opencode-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert answer.calls == []
    assert "当前群聊包含 4 个 agent" in text
    assert "Orchestrator" in text
    assert "Claude Code" in text
    assert "Codex Helper" in text
    assert "OpenCode Helper" in text
    assert "Planner" not in text
    assert "Specialist Agents" not in text


async def test_orchestrator_answers_group_models_from_platform_facts() -> None:
    planner = FakePlannerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="planner used")]
    )
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 当前群聊有哪些模型")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                    "model_backend": "claude",
                    "answer_model_backend": "deepseek",
                    "planner_model_backend": "claude",
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                    "is_builtin": True,
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "is_builtin": True,
                    "runtime": "cli",
                    "qa_model_backend": "deepseek",
                    "qa_model": "deepseek-chat",
                },
            ],
            "managed_agent_ids": ["claude-code", "codex-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert answer.calls == []
    assert "可见的模型/运行时配置" in text
    assert "answer_model_backend: deepseek" in text
    assert "planner_model_backend: claude" in text
    assert "provider: claude_code" in text
    assert "执行模型: 未在 AgentHub 配置中暴露" in text
    assert "runtime: cli" in text
    assert "qa_model_backend: deepseek" in text
    assert "GPT-4" not in text
    assert "Gemini" not in text
    assert "Llama" not in text
    assert "Mistral" not in text


async def test_orchestrator_answers_combined_group_agents_and_self_model() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="@orchestrator 当前群聊有哪些agent，你又是什么模型",
            )
        ],
        config={
            "answer_gateway": answer,
            "model_backend": "claude",
            "answer_model_backend": "deepseek",
            "planner_model_backend": "claude",
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                    "model_backend": "claude",
                },
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["claude-code"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "当前群聊包含 2 个 agent" in text
    assert "Claude Code" in text
    assert "我是 AgentHub Orchestrator" in text
    assert "direct answer backend: deepseek" in text
    assert "可见的模型/运行时配置" not in text


async def test_orchestrator_answers_combined_group_agents_and_self_model_variants() -> None:
    cases = [
        "@orchestrator 当前群聊有哪些 agent？你又是什么模型？",
        "@orchestrator 群里有哪些成员，你用什么后端",
        "@orchestrator 当前群聊有什么 agent？你用的是什么模型？",
        "@orchestrator 群聊里有谁？你也是什么模型？",
        "@orchestrator 当前群聊有哪些agent，以及 orchestrator 用什么模型",
        "@orchestrator what agents are in this group and what model are you?",
        "@orchestrator who is in this group, and which backend are you using?",
    ]

    for content in cases:
        answer = FakeAnswerGateway(
            [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
        )
        orchestrator = OrchestratorAdapter(agent_id="orchestrator")

        chunks = await _collect(
            orchestrator,
            messages=[ChatMessage(role="user", content=content)],
            config={
                "answer_gateway": answer,
                "model_backend": "claude",
                "answer_model_backend": "deepseek",
                "planner_model_backend": "claude",
                "conversation_agents": [
                    {
                        "id": "orchestrator",
                        "name": "Orchestrator",
                        "provider": "builtin",
                        "capabilities": ["task_decomposition", "coordination"],
                        "is_builtin": True,
                        "model_backend": "claude",
                    },
                    {
                        "id": "claude-code",
                        "name": "Claude Code",
                        "provider": "claude_code",
                        "capabilities": ["coding", "files", "analysis"],
                        "is_builtin": True,
                    },
                    {
                        "id": "codex-helper",
                        "name": "Codex Helper",
                        "provider": "codex",
                        "capabilities": ["coding", "sandbox"],
                        "is_builtin": True,
                    },
                ],
                "managed_agent_ids": ["claude-code", "codex-helper"],
            },
        )

        text = "".join(chunk.text_delta or "" for chunk in chunks)
        assert chunks[-1].event_type == "done", content
        assert answer.calls == [], content
        assert "当前群聊包含 3 个 agent" in text, content
        assert "Claude Code" in text, content
        assert "Codex Helper" in text, content
        assert "我是 AgentHub Orchestrator" in text, content
        assert "direct answer backend: deepseek" in text, content
        assert "planner backend: claude" in text, content
        assert "可见的模型/运行时配置" not in text, content


async def test_orchestrator_answers_model_followup_from_recent_context() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(role="user", content="@orchestrator 当前群聊有哪些模型"),
            ChatMessage(role="assistant", content="当前群聊可见模型如下"),
            ChatMessage(role="user", content="还有哪些模型"),
        ],
        config={
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["coordination"],
                    "is_builtin": True,
                    "model_backend": "claude",
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli", "files"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["opencode-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "OpenCode Helper" in text
    assert "未在 AgentHub 配置中暴露" in text


async def test_orchestrator_answers_self_model_without_llm() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 你是什么模型")],
        config={
            "answer_gateway": answer,
            "model_backend": "claude",
            "answer_model_backend": "deepseek",
            "planner_model_backend": "claude",
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "我是 AgentHub Orchestrator" in text
    assert "direct answer backend: deepseek" in text
    assert "planner backend: claude" in text


async def test_orchestrator_answers_group_capabilities_from_platform_facts() -> None:
    answer = FakeAnswerGateway(
        [StreamChunk(event_type="error", error_code="unexpected", error="answer used")]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 这些 agent 能做什么")],
        config={
            "answer_gateway": answer,
            "conversation_agents": [
                {
                    "id": "orchestrator",
                    "name": "Orchestrator",
                    "provider": "builtin",
                    "capabilities": ["task_decomposition", "coordination"],
                    "is_builtin": True,
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                    "is_builtin": True,
                },
            ],
            "managed_agent_ids": ["codex-helper"],
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert answer.calls == []
    assert "能力配置如下" in text
    assert "task_decomposition, coordination" in text
    assert "coding, sandbox" in text


async def test_platform_fact_classifier_invalid_json_falls_back_to_direct_answer() -> None:
    classifier = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="classifier"),
            StreamChunk(event_type="delta", text_delta="not json"),
            StreamChunk(event_type="done", agent_id="classifier"),
        ]
    )
    answer = FakeAnswerGateway(
        [
            StreamChunk(event_type="start", agent_id="answer"),
            StreamChunk(event_type="delta", text_delta="direct answer"),
            StreamChunk(event_type="done", agent_id="answer"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 介绍一下")],
        config={
            "platform_fact_classifier_enabled": True,
            "platform_fact_classifier_gateway": classifier,
            "answer_gateway": answer,
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(classifier.calls) == 1
    assert len(answer.calls) == 1
    assert any(chunk.text_delta == "direct answer" for chunk in chunks)


async def test_platform_fact_classifier_low_confidence_falls_back_to_direct_answer() -> None:
    classifier = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="classifier"),
            StreamChunk(
                event_type="delta",
                text_delta=(
                    '{"intent":"platform_fact","fact_type":"group_models",'
                    '"confidence":0.2}'
                ),
            ),
            StreamChunk(event_type="done", agent_id="classifier"),
        ]
    )
    answer = FakeAnswerGateway(
        [
            StreamChunk(event_type="start", agent_id="answer"),
            StreamChunk(event_type="delta", text_delta="direct answer"),
            StreamChunk(event_type="done", agent_id="answer"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="@orchestrator 介绍一下")],
        config={
            "platform_fact_classifier_enabled": True,
            "platform_fact_classifier_gateway": classifier,
            "answer_gateway": answer,
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(classifier.calls) == 1
    assert len(answer.calls) == 1
    assert any(chunk.text_delta == "direct answer" for chunk in chunks)


async def test_platform_fact_classifier_error_does_not_block_task_planning() -> None:
    classifier = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="classifier_error",
                error="boom",
            )
        ]
    )
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a todo app")],
        config={
            "platform_fact_classifier_enabled": True,
            "platform_fact_classifier_gateway": classifier,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(classifier.calls) == 1
    assert any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert any(chunk.text_delta == "done" for chunk in chunks)


async def test_orchestrator_planner_cannot_select_agent_outside_available_agents() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="delta",
                text_delta=(
                    '{"tasks":[{"task_id":"task-a","agent_id":"web-designer",'
                    '"title":"Design","instruction":"Build UI"}]}'
                ),
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a landing page")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["codex-helper"],
            "available_agents": [
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding"],
                    "is_builtin": True,
                }
            ],
        },
    )

    assert len(planner.calls) == 1
    assert "- codex-helper" in planner.calls[0]["messages"][0].content
    assert "web-designer" not in planner.calls[0]["messages"][0].content
    assert chunks[-1].event_type == "error"
    assert "unknown agent_id 'web-designer'" in (chunks[-1].error or "")
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)


async def test_orchestrator_direct_routing_only_matches_current_managed_agents() -> None:
    claude = FakeSubAdapter("claude-code", _text_chunks("claude response"))
    codex = FakeSubAdapter("codex-helper", _text_chunks("codex response"))
    planner = FakePlannerGateway([])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    '@orchestrator ask claude code, codex, and web-designer '
                    '"hello" and return their outputs'
                ),
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "codex-helper"],
            "sub_adapters": {
                "claude-code": claude,
                "codex-helper": codex,
            },
        },
    )

    assert chunks[-1].event_type == "done"
    assert planner.calls == []
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["claude-code", "codex-helper"]
    assert not any(chunk.to_agent == "web-designer" for chunk in chunks)


async def test_orchestrator_plans_tasks_with_llm_tool_call() -> None:
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "task-b",
                            "agent-b",
                            "Second",
                            "Reply from agent-b.",
                            priority=2,
                        ),
                        _task(
                            "task-a",
                            "agent-a",
                            "First",
                            "Reply from agent-a.",
                            priority=1,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Ask both agents who they are")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert adapter_a.received_messages[-1].content == "Reply from agent-a."
    assert adapter_b.received_messages[-1].content == "Reply from agent-b."
    assert planner.calls[0]["tools"][0].name == "submit_task_plan"
    assert planner.calls[0]["config"]["tool_choice"] == {"type": "auto"}
    assert "Ask both agents who they are" in planner.calls[0]["messages"][0].content
    assert "Port preview/deploy requests must not become" in (
        planner.calls[0]["messages"][0].content
    )
    assert "Do not create tasks that start, deploy, preview" in (
        planner.calls[0]["system_prompt"] or ""
    )


async def test_orchestrator_smoke_flows_create_then_verify_html(
    tmp_path: Path,
) -> None:
    html_path = "orchestrator-flow-smoke.html"
    html_content = """<!doctype html>
<html>
<head><title>Orchestrator Flow Smoke Test</title></head>
<body>
  <h1>Orchestrator Flow Smoke Test</h1>
  <input id="smoke-input" />
  <button id="smoke-button">Show</button>
  <p id="smoke-output"></p>
  <script>
    document.getElementById("smoke-button").addEventListener("click", () => {
      document.getElementById("smoke-output").textContent =
        document.getElementById("smoke-input").value;
    });
  </script>
</body>
</html>
"""
    creator = FakeWorkspaceWriterAdapter(
        "codex-helper",
        [
            StreamChunk(event_type="start", agent_id="codex-helper"),
            StreamChunk(
                event_type="tool_call",
                call_id="write-1",
                tool_name="write_file",
                tool_arguments={"path": html_path, "content": html_content},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="write-1",
                tool_status="ok",
                tool_output=f"wrote {html_path}",
            ),
            *_text_chunks(f"Created {html_path}")[1:],
        ],
        write_path=html_path,
        content=html_content,
    )
    verifier = FakeWorkspaceVerifierAdapter("opencode-helper", html_path)
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "create-html",
                            "codex-helper",
                            "Create smoke HTML",
                            f"Create {html_path} with title, input, button, and display logic.",
                            priority=1,
                            expected_output=html_path,
                        ),
                        _task(
                            "verify-html",
                            "opencode-helper",
                            "Verify smoke HTML",
                            (
                                f"Verify {html_path} contains the title, input, button, "
                                "and click display behavior. Do not regenerate the file."
                            ),
                            priority=2,
                            depends_on=["create-html"],
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "@orchestrator 请编排当前群聊里的 agent 协作完成一个极简 HTML "
                    f"文件 `{html_path}`。第一个子任务只负责创建 HTML 文件，"
                    "第二个子任务必须基于第一个子任务的结果进行检查。"
                ),
            )
        ],
        workspace_path=tmp_path,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["claude-code", "codex-helper", "opencode-helper"],
            "available_agents": [
                {
                    "id": "claude-code",
                    "name": "Claude Code",
                    "provider": "claude_code",
                    "capabilities": ["coding", "files", "analysis"],
                },
                {
                    "id": "codex-helper",
                    "name": "Codex Helper",
                    "provider": "codex",
                    "capabilities": ["coding", "sandbox"],
                },
                {
                    "id": "opencode-helper",
                    "name": "OpenCode Helper",
                    "provider": "opencode",
                    "capabilities": ["coding", "cli", "files"],
                },
            ],
            "sub_adapters": {
                "codex-helper": creator,
                "opencode-helper": verifier,
            },
        },
    )

    persisted_html = (tmp_path / html_path).read_text(encoding="utf-8")
    planning_text = "".join(chunk.text_delta or "" for chunk in chunks)
    planner_prompt = planner.calls[0]["messages"][0].content
    verifier_system_messages = [
        message for message in verifier.received_messages if message.role == "system"
    ]
    summary = planning_text.split("Execution summary", 1)[1]

    assert chunks[-1].event_type == "done"
    assert "Planned 2 sub-task(s) via LLM planner/config" in planning_text
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["codex-helper", "opencode-helper"]
    assert "web-designer" not in planner_prompt
    assert "Previous sub-agent results" in verifier_system_messages[0].content
    assert "create-html @codex-helper succeeded" in verifier_system_messages[0].content
    assert html_path in verifier_system_messages[0].content
    assert "Created orchestrator-flow-smoke.html" in verifier_system_messages[0].content
    assert "- succeeded: @codex-helper - Create smoke HTML" in summary
    assert "- succeeded: @opencode-helper - Verify smoke HTML" in summary
    assert f"artifacts: {html_path}" in summary
    assert "Checked orchestrator-flow-smoke.html" in planning_text
    assert "title=True" in planning_text
    assert "input=True" in planning_text
    assert "button=True" in planning_text
    assert "display=True" in planning_text
    assert "Orchestrator Flow Smoke Test" in persisted_html
    assert "<input" in persisted_html
    assert "<button" in persisted_html
    assert "textContent" in persisted_html
    assert verifier.verified_content == persisted_html


async def test_orchestrator_react_disabled_preserves_static_flow() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish"}],"summary":"unused"}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": False,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "Static", "Run static task")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    assert react_gateway.calls == []
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "agent-a"
    ]
    assert not any("ReAct step" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_react_adds_fix_task_after_failure_and_finishes() -> None:
    verify = FakeSubAdapter(
        "opencode-helper",
        [
            StreamChunk(
                event_type="error",
                error_code="verification_failed",
                error="missing click behavior",
            )
        ],
    )
    fix = FakeSubAdapter("codex-helper", _text_chunks("Fixed click behavior"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"add_task","task":{'
                '"task_id":"fix-html","agent_id":"codex-helper",'
                '"title":"Fix HTML behavior",'
                '"instruction":"Fix the missing click behavior.",'
                '"priority":2}}],'
                '"summary":"thought: add repair task"}'
            ),
            _react_decision_chunks(
                '{"actions":[{"type":"finish","reason":"Fixed and verified"}],"summary":"done"}'
            ),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Fix and verify an HTML file")],
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [
                _task(
                    "verify-html",
                    "opencode-helper",
                    "Verify HTML",
                    "Verify the click behavior.",
                )
            ],
            "managed_agent_ids": ["codex-helper", "opencode-helper"],
            "sub_adapters": {
                "opencode-helper": verify,
                "codex-helper": fix,
            },
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert len(react_gateway.calls) == 2
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["opencode-helper", "codex-helper"]
    assert "ReAct step 1" in text
    assert "Action: add_task fix-html -> @codex-helper" in text
    assert "ReAct step 2" in text
    assert "Action: finish: Fixed and verified" in text
    assert "- failed: @opencode-helper - Verify HTML" in text
    assert "- succeeded: @codex-helper - Fix HTML behavior" in text
    assert "thought" not in text
    assert "chain_of_thought" not in text


async def test_orchestrator_react_rejects_add_task_outside_allowed_agents() -> None:
    verify = FakeSubAdapter(
        "opencode-helper",
        [
            StreamChunk(
                event_type="error",
                error_code="verification_failed",
                error="needs design",
            )
        ],
    )
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"add_task","task":{'
                '"task_id":"design","agent_id":"web-designer",'
                '"title":"Design","instruction":"Design UI","priority":2}}],'
                '"summary":"add designer"}'
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [_task("verify", "opencode-helper", "Verify", "Verify output")],
            "managed_agent_ids": ["opencode-helper"],
            "sub_adapters": {"opencode-helper": verify},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "unknown agent_id 'web-designer'" in text
    assert not any(chunk.to_agent == "web-designer" for chunk in chunks)


async def test_orchestrator_react_cannot_update_succeeded_task() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"update_task","task_id":"task-a",'
                '"patch":{"instruction":"mutated"}}],"summary":"bad update"}'
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "Done", "Original")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "cannot update completed task 'task-a'" in text
    assert adapter.received_messages[-1].content == "Original"


async def test_orchestrator_react_skip_task_prevents_execution() -> None:
    first = FakeSubAdapter("agent-a", _text_chunks("first done"))
    skipped = FakeSubAdapter("agent-b", _text_chunks("should not run"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"skip_task","task_id":"task-b",'
                '"reason":"not needed"},{"type":"finish","reason":"done"}],'
                '"summary":"skip second"}'
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [
                _task("task-a", "agent-a", "First", "Run first", priority=1),
                _task("task-b", "agent-b", "Second", "Run second", priority=2),
            ],
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": first, "agent-b": skipped},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a"]
    assert skipped.received_messages == []
    assert "- skipped: @agent-b - Second" in text


async def test_orchestrator_react_max_iterations_stops_without_replanner() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish"}],"summary":"unused"}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "max_iterations": 1,
            "tasks": [_task("task-a", "agent-a", "One", "Run one")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert react_gateway.calls == []
    assert "max_iterations reached (1)" in text


async def test_orchestrator_react_added_task_receives_previous_results() -> None:
    first = FakeSubAdapter("agent-a", _text_chunks("Analysis result"))
    second = FakeSubAdapter("agent-b", _text_chunks("Follow-up result"))
    react_gateway = SequencedGateway(
        [
            _react_decision_chunks(
                '{"actions":[{"type":"add_task","task":{'
                '"task_id":"follow-up","agent_id":"agent-b",'
                '"title":"Follow up","instruction":"Use prior result.",'
                '"depends_on":["task-a"],"priority":2}}],'
                '"summary":"add follow-up"}'
            ),
            _react_decision_chunks('{"actions":[{"type":"finish","reason":"done"}]}'),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "Analyze", "Analyze request", priority=1)],
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": first, "agent-b": second},
        },
    )

    system_messages = [
        message for message in second.received_messages if message.role == "system"
    ]
    assert chunks[-1].event_type == "done"
    assert len(system_messages) == 1
    assert "Previous sub-agent results" in system_messages[0].content
    assert "task-a @agent-a succeeded" in system_messages[0].content
    assert "Analysis result" in system_messages[0].content


async def test_orchestrator_react_trace_can_be_hidden() -> None:
    adapter = FakeSubAdapter("agent-a", _text_chunks("done"))
    react_gateway = SequencedGateway(
        [_react_decision_chunks('{"actions":[{"type":"finish","reason":"done"}]}')]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "react_enabled": True,
            "react_trace_visible": False,
            "react_gateway": react_gateway,
            "tasks": [_task("task-a", "agent-a", "One", "Run one")],
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter},
        },
    )

    text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert len(react_gateway.calls) == 1
    assert "ReAct step" not in text
    assert "- succeeded: @agent-a - One" in text


async def test_orchestrator_filters_planner_port_service_tasks() -> None:
    web_designer = FakeSubAdapter("web-designer", _text_chunks("created snake.html"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(
                event_type="tool_call",
                call_id="plan-1",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task(
                            "task-create",
                            "web-designer",
                            "Create snake.html",
                            "Create a complete snake.html game file.",
                        ),
                        _task(
                            "task-preview",
                            "claude-code",
                            "Start 8082 preview service",
                            "Set up the port preview service and verify the game.",
                            priority=2,
                        ),
                    ]
                },
            ),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[
            ChatMessage(
                role="user",
                content="Create snake.html and preview it on port 8082.",
            )
        ],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["web-designer", "claude-code"],
            "sub_adapters": {"web-designer": web_designer},
        },
    )

    planning_text = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "via LLM planner/config" in planning_text
    assert "Start 8082 preview service" not in planning_text
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["web-designer"]


async def test_orchestrator_plans_tasks_from_llm_json_text() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="start", agent_id="planner"),
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta=(
                    '```json\n{"tasks":[{"task_id":"task-a","agent_id":"agent-a",'
                    '"title":"Answer","instruction":"Answer directly.",'
                    '"priority":0}]}\n```'
                ),
            ),
            StreamChunk(event_type="block_end", block_index=0),
            StreamChunk(event_type="done", agent_id="planner"),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"] == [
        "agent-a"
    ]
    assert adapter_a.received_messages[-1].content == "Answer directly."


async def test_orchestrator_rejects_planner_unknown_agent() -> None:
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="tool_call",
                tool_name="submit_task_plan",
                tool_arguments={
                    "tasks": [
                        _task("task-a", "unknown-agent", "Bad", "Do work"),
                    ]
                },
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": FakeSubAdapter("agent-a", _text_chunks("unused"))},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "invalid_task_plan"
    assert "unknown agent_id" in (chunks[1].error or "")


async def test_orchestrator_planner_error_does_not_use_template_by_default() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="planner timeout",
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_task_plan"
    assert "timeout: planner timeout" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_empty_output_is_visible_error() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway([])
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_task_plan"
    assert "empty_planner_output" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_invalid_json_is_visible_error() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="not a task plan",
            ),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "invalid_task_plan"
    assert "invalid_json" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_invalid_json_can_fallback_to_direct_answer() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("unused"))
    planner = FakePlannerGateway(
        [
            StreamChunk(event_type="block_start", block_index=0, block_type="text"),
            StreamChunk(
                event_type="delta",
                block_index=0,
                text_delta="not a task plan",
            ),
            StreamChunk(event_type="block_end", block_index=0),
        ]
    )
    answer = FakeAnswerGateway(_text_chunks("Direct answer fallback."))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "answer_gateway": answer,
            "direct_answer_on_planner_failure": True,
            "managed_agent_ids": ["agent-a"],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert chunks[-1].event_type == "done"
    assert len(planner.calls) == 1
    assert len(answer.calls) == 1
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert any(chunk.text_delta == "Direct answer fallback." for chunk in chunks)
    assert adapter_a.received_messages == []


async def test_orchestrator_planner_template_fallback_requires_flag() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    planner = FakePlannerGateway(
        [
            StreamChunk(
                event_type="error",
                error_code="timeout",
                error="planner timeout",
            )
        ]
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[ChatMessage(role="user", content="Build a launch plan")],
        config={
            "planner_gateway": planner,
            "planner_fallback_to_template": True,
            "managed_agent_ids": ["agent-a", "agent-b"],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert any(
        "via legacy template" in (chunk.text_delta or "") for chunk in chunks
    )
    assert adapter_a.received_messages[-1].content.startswith("Analyze the user's request")


async def test_orchestrator_forwards_tool_events_with_remapped_call_ids() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "hello.html"},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="ok",
                tool_output="wrote hello.html",
            ),
            StreamChunk(event_type="done", agent_id="agent-a"),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Write HTML", "Write hello.html")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    tool_result = next(chunk for chunk in chunks if chunk.event_type == "tool_result")
    assert tool_call.call_id == "task-a.c-1"
    assert tool_result.call_id == "task-a.c-1"
    assert tool_call.tool_name == "write_file"
    assert tool_result.tool_status == "ok"


async def test_orchestrator_injects_dependency_result_context() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Created snake.html"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Reviewed result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Create", "Create snake.html"),
                _task(
                    "task-b",
                    "agent-b",
                    "Review",
                    "Review the prior artifact",
                    depends_on=["task-a"],
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    system_messages = [
        message for message in adapter_b.received_messages if message.role == "system"
    ]
    assert len(system_messages) == 1
    assert "Previous sub-agent results" in system_messages[0].content
    assert "task-a @agent-a succeeded" in system_messages[0].content
    assert "Created snake.html" in system_messages[0].content


async def test_orchestrator_include_history_false_still_injects_dependency_context() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Analysis complete"))
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Second result"))
    user_message = ChatMessage(role="user", content="Original user request")
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        messages=[user_message],
        config={
            "tasks": [
                _task("task-a", "agent-a", "Analyze", "Analyze request"),
                _task(
                    "task-b",
                    "agent-b",
                    "Direct",
                    "Use dependency only",
                    depends_on=["task-a"],
                    include_history=False,
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert chunks[-1].event_type == "done"
    assert user_message not in adapter_b.received_messages
    assert adapter_b.received_messages[0].role == "system"
    assert "Analysis complete" in adapter_b.received_messages[0].content
    assert adapter_b.received_messages[-1].content == "Use dependency only"


async def test_orchestrator_marks_missing_expected_artifact(tmp_path: Path) -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Created snake.html"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create HTML",
                    "Create snake.html",
                    expected_output="snake.html",
                )
            ],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- artifact_missing: @agent-a - Create HTML" in summary
    assert "missing: snake.html" in summary


async def test_orchestrator_artifact_missing_triggers_per_task_fallback(
    tmp_path: Path,
) -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("Created snake.html"))
    adapter_b = FakeWorkspaceWriterAdapter(
        "agent-b",
        [
            StreamChunk(event_type="start", agent_id="agent-b"),
            StreamChunk(
                event_type="tool_call",
                call_id="c-1",
                tool_name="write_file",
                tool_arguments={"path": "snake.html"},
            ),
            StreamChunk(
                event_type="tool_result",
                call_id="c-1",
                tool_status="ok",
                tool_output="wrote snake.html",
            ),
            *_text_chunks("Fallback created snake.html")[1:],
        ],
        write_path="snake.html",
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        workspace_path=tmp_path,
        config={
            "tasks": [
                _task(
                    "task-a",
                    "agent-a",
                    "Create HTML",
                    "Create snake.html",
                    expected_output="snake.html",
                )
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    tool_call = next(chunk for chunk in chunks if chunk.event_type == "tool_call")
    assert (tmp_path / "snake.html").exists()
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert tool_call.call_id == "task-a.attempt-2.c-1"
    assert "- succeeded: @agent-b - Create HTML" in summary
    assert "attempt 1 @agent-a: artifact_missing" in summary
    assert "artifacts: snake.html" in summary


async def test_orchestrator_subagent_error_triggers_per_task_fallback() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="runtime_idle_timeout",
                error="idle timeout",
            ),
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("Recovered result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Work", "Do work")],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert [
        chunk.to_agent for chunk in chunks if chunk.event_type == "agent_switch"
    ] == ["agent-a", "agent-b"]
    assert "Previous attempt failure" in adapter_b.received_messages[-2].content
    assert "idle timeout" in adapter_b.received_messages[-2].content
    assert "- succeeded: @agent-b - Work" in summary
    assert "attempt 1 @agent-a: failed - idle timeout" in summary


async def test_orchestrator_all_fallback_attempts_fail_still_done() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [StreamChunk(event_type="error", error_code="boom", error="first failed")],
    )
    adapter_b = FakeSubAdapter(
        "agent-b",
        [StreamChunk(event_type="error", error_code="boom", error="second failed")],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Work", "Do work")],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
            "task_fallback_agent_ids": ["agent-b"],
            "max_task_attempts": 2,
        },
    )

    summary = "".join(chunk.text_delta or "" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert "- failed: @agent-b - Work" in summary
    assert "attempt 1 @agent-a: failed - first failed" in summary
    assert "attempt 2 @agent-b: failed - second failed" in summary


async def test_registry_returns_orchestrator_adapter_for_builtin_orchestrator() -> None:
    class FakeDb:
        async def get(self, model: object, key: str) -> Agent | None:
            assert model is Agent
            if key != "orchestrator":
                return None
            return Agent(
                id="orchestrator",
                user_id=None,
                name="Orchestrator",
                provider="builtin",
                avatar_url="/avatars/orchestrator.png",
                capabilities=["task_decomposition", "coordination"],
                system_prompt="Coordinate sub agents.",
                config={"model_backend": "claude"},
                is_builtin=True,
            )

    adapter = await get_adapter("orchestrator", FakeDb())  # type: ignore[arg-type]

    assert isinstance(adapter, OrchestratorAdapter)
    assert callable(adapter.default_config["adapter_factory"])
    assert adapter.default_config["managed_agent_ids"]


async def test_orchestrator_requires_task_plan_or_emits_clear_error() -> None:
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    missing_tasks = await _collect(orchestrator, config={"sub_adapters": {}})
    assert [chunk.event_type for chunk in missing_tasks] == ["start", "error"]
    assert missing_tasks[1].error_code == "missing_task_plan"

    missing_adapters = await _collect(
        orchestrator,
        config={"tasks": [_task("task-a", "agent-a", "Backend API", "Build API")]},
    )
    assert [chunk.event_type for chunk in missing_adapters] == ["start", "error"]
    assert missing_adapters[1].error_code == "missing_sub_adapters"


async def test_orchestrator_intercepts_subagent_error_chunk() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Build API")],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and "@agent-a failed: too many requests" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any("- failed: @agent-a - Backend API" in (chunk.text_delta or "") for chunk in chunks)


async def test_orchestrator_continues_after_subagent_stream_exception() -> None:
    adapter_a = FakePartialThenExceptionAdapter(
        "agent-a",
        [
            StreamChunk(
                event_type="block_start", block_index=0, block_type="text"
            ),
            StreamChunk(
                event_type="delta", block_index=0, text_delta="partial from a"
            ),
        ],
        RuntimeError("upstream connection lost"),
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(chunk.text_delta == "partial from a" for chunk in chunks)
    assert any(
        chunk.event_type == "delta"
        and "@agent-a failed: upstream connection lost" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- succeeded: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )
    _assert_blocks_balanced(chunks)


async def test_orchestrator_continues_after_subagent_error_chunk() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and "@agent-a failed: too many requests" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- succeeded: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_skips_tasks_with_failed_dependencies() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task(
                    "task-b",
                    "agent-b",
                    "Frontend UI",
                    "Build UI",
                    depends_on=["task-a"],
                ),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert not any(
        chunk.event_type == "agent_switch" and chunk.to_agent == "agent-b"
        for chunk in chunks
    )
    assert not any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- skipped: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_all_tasks_fail_still_done() -> None:
    adapter_a = FakeSubAdapter(
        "agent-a",
        [
            StreamChunk(event_type="start", agent_id="agent-a"),
            StreamChunk(
                event_type="error",
                agent_id="agent-a",
                error_code="rate_limit",
                error="too many requests",
            ),
        ],
    )
    adapter_b = FakeSubAdapter(
        "agent-b",
        [
            StreamChunk(event_type="start", agent_id="agent-b"),
            StreamChunk(
                event_type="error",
                agent_id="agent-b",
                error_code="timeout",
                error="connection timeout",
            ),
        ],
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "sub_adapters": {"agent-a": adapter_a, "agent-b": adapter_b},
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- failed: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_adapter_factory_exception_is_task_failure() -> None:
    adapter_b = FakeSubAdapter("agent-b", _text_chunks("from b"))

    def adapter_factory(agent_id: str) -> BaseAgentAdapter:
        if agent_id == "agent-a":
            raise RuntimeError("factory broken")
        return adapter_b

    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-b", "agent-b", "Frontend UI", "Build UI"),
            ],
            "adapter_factory": adapter_factory,
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and "@agent-a failed: factory broken" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(chunk.text_delta == "from b" for chunk in chunks)
    assert any(
        "- failed: @agent-a - Backend API" in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        "- succeeded: @agent-b - Frontend UI" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_fallback_adapter_handles_invalid_task_plan() -> None:
    fallback = FakeSubAdapter("fallback", _text_chunks("fallback result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": "invalid task plan",
            "fallback_agent_id": "claude-code",
            "fallback_adapter": fallback,
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(
        chunk.event_type == "delta"
        and "Task plan unavailable; falling back to @claude-code." in (chunk.text_delta or "")
        for chunk in chunks
    )
    assert any(
        chunk.event_type == "agent_switch"
        and chunk.to_agent == "claude-code"
        and chunk.task == "fallback"
        for chunk in chunks
    )
    assert any(chunk.text_delta == "fallback result" for chunk in chunks)
    assert any(
        "- fallback: single agent mode" in (chunk.text_delta or "")
        for chunk in chunks
    )


async def test_orchestrator_does_not_fallback_when_adapter_source_missing() -> None:
    fallback = FakeSubAdapter("fallback", _text_chunks("fallback result"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [_task("task-a", "agent-a", "Backend API", "Build API")],
            "fallback_agent_id": "claude-code",
            "fallback_adapter": fallback,
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "missing_sub_adapters"
    assert not any(chunk.event_type == "agent_switch" for chunk in chunks)
    assert fallback.received_messages == []


async def test_orchestrator_rejects_duplicate_task_ids() -> None:
    adapter_a = FakeSubAdapter("agent-a", _text_chunks("from a"))
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": [
                _task("task-a", "agent-a", "Backend API", "Build API"),
                _task("task-a", "agent-a", "Review API", "Review API"),
            ],
            "sub_adapters": {"agent-a": adapter_a},
        },
    )

    assert [chunk.event_type for chunk in chunks] == ["start", "error"]
    assert chunks[1].error_code == "invalid_task_plan"
    assert "duplicate task_id" in (chunks[1].error or "")
    assert adapter_a.received_messages == []


async def test_orchestrator_fallback_closes_open_block_on_exception() -> None:
    fallback = FakePartialThenExceptionAdapter(
        "fallback",
        [
            StreamChunk(
                event_type="block_start", block_index=0, block_type="text"
            ),
            StreamChunk(
                event_type="delta", block_index=0, text_delta="partial fallback"
            ),
        ],
        RuntimeError("fallback crashed"),
    )
    orchestrator = OrchestratorAdapter(agent_id="orchestrator")

    chunks = await _collect(
        orchestrator,
        config={
            "tasks": "invalid task plan",
            "fallback_agent_id": "claude-code",
            "fallback_adapter": fallback,
        },
    )

    assert not any(chunk.event_type == "error" for chunk in chunks)
    assert chunks[-1].event_type == "done"
    assert any(chunk.text_delta == "partial fallback" for chunk in chunks)
    assert any(
        chunk.event_type == "delta"
        and "@claude-code failed: fallback crashed" in (chunk.text_delta or "")
        for chunk in chunks
    )
    _assert_blocks_balanced(chunks)
