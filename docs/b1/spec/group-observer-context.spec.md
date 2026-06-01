# Group Observer Context Spec

> Owner: B1
> Related: B2 Orchestrator / Agent Runtime, F Group Chat Rendering

## 1. Goal

Group conversations can contain messages from multiple agents. The current agent must be able to read those messages as a participant observing the group history, without confusing another agent's output with its own prior work.

This spec defines the B1 context contract for group chat memory and observer identity.

## 2. Problem

Before this change, group context already prefixed agent messages with labels such as:

```text
[Agent: claude-code] I created the file.
[Agent: opencode-helper] I reviewed the code.
```

That solved basic attribution, but it did not explicitly tell the currently invoked agent:

- who it is in this stream
- that it is reading a group conversation as an observer
- that labeled messages from other agents are not its own statements
- how to refer to another agent's work

This could cause a model to say "I created that file" when the file was actually produced by another agent.

## 3. B1 Contract

### 3.1 ContextBuilder Input

`build_context()` now accepts an optional keyword-only argument:

```python
current_agent_id: str | None = None
```

The SSE stream endpoint passes the target `message.agent_id` into `build_context()`.

### 3.2 Group System Message

For group conversations, B1 prepends a system message that identifies the current agent and explains the observer semantics.

When `current_agent_id` is available, the message includes:

- `You are Agent: <current_agent_id>`
- all agents in the conversation
- other agents in the conversation
- the meaning of `[Agent: <agent_id>]`
- the rule that other-agent messages are not the current agent's own statements, actions, files, or conclusions
- the instruction to name another agent explicitly when referring to that agent's work

When `current_agent_id` is unavailable, B1 falls back to a generic group notice and still treats labeled messages as observations from their named agents.

### 3.3 Message Labels

B1 continues to label agent messages in group context:

```text
[Agent: <agent_id>] <message text>
```

This applies to:

- recent raw messages
- pinned messages
- compressed memory source text

User messages are not given an agent label.

### 3.4 Single Conversation Behavior

Single conversations do not receive the group observer system prompt, even when `current_agent_id` is provided.

## 4. API and Storage Impact

No public API changes.

No database migration.

No message schema change.

This is a model-input context change only. Existing front-end requests and B2 adapter contracts remain compatible.

## 5. B2 Impact

B2 adapters do not need to change for this spec.

B2 can rely on B1 to pass group history with observer semantics before calling:

```python
adapter.stream(messages, ...)
```

If B2 Orchestrator forwards group history to child agents, it should preserve the same meaning:

- group history is context to read
- child agents may use other agents' outputs
- child agents must not claim another agent's work as their own

If a route intentionally disables history, such as a direct tool or identity task with `include_history=False`, this observer context may be omitted by design.

## 6. F Impact

No front-end API changes are required.

F should continue rendering group messages and content block attribution normally. This spec affects what the model receives before it replies, not what the browser must send.

The expected user-visible effect is:

- an agent can answer questions about what another agent said
- an agent is less likely to impersonate another agent
- an agent should phrase references as "claude-code said..." or "opencode-helper created..."

## 7. Example

Conversation agents:

```text
claude-code, codex-helper, orchestrator
```

Current stream target:

```text
codex-helper
```

The first context message is equivalent to:

```text
You are Agent: codex-helper. You are observing a group conversation.
Agents in this conversation: claude-code, codex-helper, orchestrator.
Other agents: claude-code, orchestrator.
Messages prefixed with [Agent: <agent_id>] were produced by that agent.
Those other-agent messages are not your own statements, actions, files, or conclusions.
You may read, quote, analyze, continue, or disagree with them, but do not claim them as your own.
When referring to another agent's work, name that agent explicitly.
```

Then history continues as:

```text
user: Please remember: AgentHub uses FastAPI.
assistant: [Agent: claude-code] I designed the backend API.
assistant: [Agent: codex-helper] I reviewed the sandbox code.
```

## 8. Validation

Covered by backend tests:

- group context includes current observer identity
- group context labels other agent messages
- single conversations do not receive the group observer prompt
- SSE stream passes the current target agent id into `build_context()`
- multi-agent turn-taking keeps current-agent and other-agent semantics distinct
- old pinned group agent messages keep `[Agent: <agent_id>]` labels
- compressed group memory keeps agent labels and follows the observer system prompt
- Orchestrator stream handoff keeps the observer prompt before Orchestrator structured memory
- `include_history=False` sub-agent routes remain free of original conversation history
- full backend regression remains compatible

Recommended checks:

```bash
docker compose exec -T backend pytest tests/test_context_builder.py tests/test_stream_tool_calls.py -q
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

Debug note:

To inspect the first context message received by an adapter in group chat, patch
`app.api.v1.stream.get_adapter` in a stream test with a fake adapter that records
the `messages` argument passed to `stream()`. In a group Orchestrator stream,
`messages[0]` must be the observer system prompt; any Orchestrator structured
memory must appear later, before the latest active user request.

## 9. Follow-up Coverage

### P1: Orchestrator / Sub-agent Observer Semantics

Goal: when Orchestrator passes group history to sub-agents, each sub-agent still understands the difference between observed group history and the current task it must execute.

B1-facing coverage:

- Keep `build_context(..., current_agent_id=...)` as the single B1 entry point for group observer context.
- Verified Orchestrator streams receive the observer system message before any Orchestrator-specific memory injection.
- Added regression coverage for group Orchestrator handoff where another agent's prior message remains labeled as that agent's work.
- Kept `include_history=False` routes history-free by design, especially for direct identity or routing tasks.

Coordination:

- B2 owns Orchestrator task routing and child-agent prompt construction.
- B1 owns context assembly and stream handoff.
- F has no required API change for P1.

### P2: Debuggability, Documentation, And Full Regression

Goal: make observer semantics easy to validate during AI collaboration, review, and demo.

B1-facing coverage:

- Added the debug note above for inspecting adapter input in group stream tests.
- Expanded regression coverage for multi-agent turn-taking, agent-to-agent references, pinned group facts, and compressed group memory.
- Kept this spec aligned with `message-content-block-attribution.spec.md`: observer context explains model input while ContentBlock attribution explains persisted output ownership.
- No new collaboration log entry is required for this follow-up because it does not change owner boundaries or reusable workflow rules.

Coordination:

- B2 should document any Orchestrator child-agent prompt changes in the related Orchestrator specs.
- F should document rendering behavior in `docs/frontend/spec/orchestrated-message-rendering.spec.md` when block-level attribution is consumed.
