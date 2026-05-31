# Orchestrator Message Attribution Spec

> Owner: B2
> Related: [B1 ContentBlock Attribution](../../b1/spec/message-content-block-attribution.spec.md), [F Orchestrated Rendering](../../frontend/spec/orchestrated-message-rendering.spec.md)

## 1. 目标

Orchestrator 合并多个子 Agent stream 时，必须保留每个输出 chunk 的真实来源 Agent，使前端能把同一条 Orchestrator message 按子 Agent 分段显示。

B2 负责：

- 为 Orchestrator 自己的 plan / summary chunk 标记 `agent_id="orchestrator"`。
- 为子 Agent block/tool chunk 标记实际 `agent_id`。
- 移除或降级纯文本 `@<agent_id>` header，不再把它作为归属语义。

B2 不负责：

- OpenAPI/Pydantic 持久化字段。
- 前端 UI 分组。

## 2. 当前问题

当前 Orchestrator 子任务执行会：

1. 发出 `agent_switch(from_agent="orchestrator", to_agent=task.agent_id)`。
2. 输出一个普通 text block：`@<agent_id>\n\n`。
3. 转发子 Agent 的 block/delta/tool events。
4. 最终输出 Execution summary。

由于转发后的子 Agent block 没有稳定 `agent_id`，B1 持久化后只剩一条 `message.agent_id="orchestrator"` 的消息。前端无法知道哪些 block 属于 Claude Code、OpenCode 或 fallback Agent。

## 3. StreamChunk Attribution 规则

`StreamChunk.agent_id` 在 Orchestrator 合流场景中扩展为“当前 chunk 的实际输出 Agent”。

| Chunk 来源 | event_type | agent_id |
|---|---|---|
| Orchestrator plan | `block_start/delta/block_end` | `orchestrator` |
| Orchestrator summary | `block_start/delta/block_end` | `orchestrator` |
| 子 Agent 文本/代码/diff | `block_start/delta/block_end` | 实际 attempt agent id |
| 子 Agent tool | `tool_call/tool_result` | 实际 attempt agent id |
| 子 Agent heartbeat | `heartbeat` | 实际 attempt agent id，可选 |
| `agent_switch` | `agent_switch` | 可为空，继续使用 `from_agent/to_agent` |
| fatal error | `error` | 产生错误的 Agent，可选 |

普通单 Agent adapter 可继续只在 `start/done` 设置 `agent_id`。但 Orchestrator 合流时必须给可持久化内容 chunk 标记 `agent_id`。

## 4. 后端文件修改

### 4.1 StreamChunk 类型说明

文件：

- `backend/app/agents/types.py`
- `docs/b2/spec/agent-runtime-adapter.spec.md`

代码字段已存在：

```python
agent_id: str | None = None
```

需要更新注释 / spec，明确：

- `agent_id` 不只用于 `start/done`。
- `block_start/delta/block_end/tool_call/tool_result` 可携带 `agent_id` 表示实际输出者。

### 4.2 Orchestrator text block helper

文件：

- `backend/app/agents/orchestrator/execution.py`

当前 helper：

```python
def _text_block(block_index: int, text: str) -> tuple[StreamChunk, ...]:
    ...
```

建议改为：

```python
def _text_block(
    block_index: int,
    text: str,
    *,
    agent_id: str = "orchestrator",
) -> tuple[StreamChunk, StreamChunk, StreamChunk]:
    return (
        StreamChunk(
            event_type="block_start",
            block_index=block_index,
            block_type="text",
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="delta",
            block_index=block_index,
            text_delta=text,
            agent_id=agent_id,
        ),
        StreamChunk(
            event_type="block_end",
            block_index=block_index,
            agent_id=agent_id,
        ),
    )
```

`_text_block_with_next()` 同步透传 `agent_id`。

### 4.3 子 Agent stream remap

文件：

- `backend/app/agents/orchestrator/streams.py`

在 `remapped_sub_stream()` 中，对以下事件附加实际 `agent_id`：

- `block_start`
- `delta`
- `block_end`
- `tool_call`
- `tool_result`
- `heartbeat` 可选

建议新增 helper：

```python
def attach_agent_id(chunk: StreamChunk, agent_id: str) -> StreamChunk:
    if chunk.agent_id == agent_id:
        return chunk
    return chunk.model_copy(update={"agent_id": agent_id})
```

使用点：

```python
if chunk.event_type in {"tool_call", "tool_result"}:
    accumulate_tool_event(attempt, chunk)
    remapped = remap_tool_call_id(chunk, call_id_prefix)
    yield attach_agent_id(remapped, agent_id), next_block_index, False
    continue
```

block remap 后：

```python
remapped, next_block_index = remap_block_index(...)
remapped = attach_agent_id(remapped, agent_id)
yield remapped, next_block_index, False
```

### 4.4 移除文本 header

文件：

- `backend/app/agents/orchestrator/execution.py`

当前：

```python
yield _agent_switch(task, agent_id), next_block_index
for chunk in _text_block_with_next(next_block_index, _agent_header_text(task, agent_id)):
    yield chunk
next_block_index += 1
```

推荐改为：

```python
yield _agent_switch(task, agent_id), next_block_index
```

不再输出 `@claude-code\n\n` 这种普通正文 header。

如果担心前端尚未支持分组，可以加 feature flag：

```python
emit_agent_text_headers = bool(config.get("orchestrator_emit_agent_text_headers", False))
```

默认应为 `False`。

### 4.5 失败文本归属

当前失败文本：

```python
@opencode-helper failed: ...
```

建议改为：

```text
failed: This session is provisioning...
```

并用 `agent_id=<failed_agent_id>` 标记该 text block。

这样前端显示为：

```text
OpenCode Helper
failed: ...
```

而不是：

```text
Orchestrator
@opencode-helper failed: ...
```

## 5. Per-task fallback 规则

若任务从原 agent fallback 到另一个 agent：

- `agent_switch.to_agent` 使用实际 attempt agent。
- fallback attempt 的所有输出 chunk 使用 fallback agent id。
- summary 仍由 Orchestrator 输出，`agent_id="orchestrator"`。
- tool_call `call_id` 继续使用当前 `<task_id>.attempt-N.<call_id>` 规则，避免冲突。

## 6. Memory / Summary 影响

`TaskAttempt.agent_id` 已存在，应继续作为结构化 memory 的真实 attempt agent。

本次不要求修改 Orchestrator memory 表结构。

注意：

- 去掉文本 header 后，summary / memory 不应依赖 `@agent` 文本解析。
- `attempt.text_preview` 继续从子 Agent delta 累积。

## 7. 测试计划

新增/更新后端 B2 测试：

- `backend/tests/test_orchestrator.py`
- `backend/tests/test_stream_tool_calls.py`
- 需要时新增 `backend/tests/test_orchestrator_attribution.py`

覆盖：

1. Orchestrator planning block 带 `agent_id="orchestrator"`。
2. 子 Agent text block 带实际 `agent_id`。
3. 子 Agent tool_call/tool_result 带实际 `agent_id` 且 call_id 仍被 remap。
4. 子 Agent error 转普通失败 text block，block agent_id 是失败 Agent。
5. fallback attempt 输出使用 fallback agent_id。
6. 不再输出普通 `@<agent_id>` header，或 feature flag off 时不输出。
7. final summary block agent_id 是 `orchestrator`。

## 8. 验收标准

- SSE live event 中，子 Agent block/tool chunk 带实际 `agent_id`。
- B1 accumulator 落库后 content block 保留该 `agent_id`。
- 前端刷新后可按 Agent 分段展示。
- Orchestrator 消息不再通过纯文本 `@agent` header 表达归属。
- 现有 Orchestrator 任务执行、fallback、summary 行为不回归。

## 9. 边界说明

这项工作不是纯 B1，也不是纯前端。正确职责是：

- B2 生产 attribution。
- B1 持久化 attribution。
- F 消费 attribution。

B2 不应要求前端用正文正则解析 `@agent`；那会在 code block、tool_call、失败重试和 fallback 场景中继续失真。
