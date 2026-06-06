# Orchestrator Message Attribution Spec

> Owner: B2
> Related: [B1 ContentBlock Attribution](../../../b1/spec/message-content-block-attribution.spec.md), [F Orchestrated Rendering](../../../frontend/spec/orchestrated-message-rendering.spec.md)
> Last updated: 2026-06-05

## 1. 目标

Orchestrator 合并多个子 Agent stream 时，必须保留每个输出 chunk 的真实来源 Agent。

当前契约分两层：

1. **兼容层**：同一条 Orchestrator message 内的 block/tool chunk 继续带 `agent_id`，旧前端可按 block 分段展示。
2. **真实群聊层**：group conversation 中，子 Agent 输出会创建独立 `messages` 行，并通过 SSE `message_start` / `message_done` / `message_error` 以及带 `message_id` 的 block/tool events 归属到该子消息。

B2 负责：

- 为 Orchestrator 自己的 plan / summary chunk 标记 `agent_id="orchestrator"`。
- 为子 Agent block/tool chunk 标记实际 `agent_id`。
- 在真实群聊后端模式下，为子 Agent 输出创建独立 message 并持久化其 content / status。
- 移除或降级纯文本 `@<agent_id>` header，不再把它作为归属语义。

B2 不负责：

- 前端 UI 如何展示新增 message lifecycle 事件。
- 折叠/展开 process 或高级执行详情。

## 2. 当前问题

当前 Orchestrator 子任务执行会：

1. 发出 `agent_switch(from_agent="orchestrator", to_agent=task.agent_id)`。
2. 输出一个普通 text block：`@<agent_id>\n\n`。
3. 转发子 Agent 的 block/delta/tool events。
4. 最终输出 Execution summary。

历史问题分两阶段：

- 第一阶段：转发后的子 Agent block 没有稳定 `agent_id`，B1 持久化后无法知道哪些 block 属于 Claude Code、OpenCode 或 fallback Agent。
- 第二阶段：即使 block 有 `agent_id`，DB 仍只有一条 `message.agent_id="orchestrator"` 的回复，聊天窗口看起来仍像 Orchestrator 汇总所有人发言。

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

## 4. 真实群聊消息行规则

启用条件：

- conversation `mode="group"`。
- target agent 为 `orchestrator`。
- `orchestrator_group_messages_enabled` 未显式设为 `false`。

SSE lifecycle：

| event | 语义 |
|---|---|
| `message_start` | 创建并开始一个子 Agent message，payload 包含 `message_id`、`conversation_id`、`agent_id`、`reply_to_id`、`created_at`、`status="streaming"` |
| `block_start/delta/block_end` | 若携带子 `message_id`，该 block 属于对应子 message；否则属于父 Orchestrator message |
| `tool_call/tool_result` | 若携带子 `message_id`，该 tool block 属于对应子 message |
| `message_done` | 子 message 完成并持久化为 `status="done"` |
| `message_error` | 子 message 失败并持久化为 `status="error"` |
| `done` | 整个 Orchestrator 父 stream 完成，语义不变 |

持久化：

- 子 message 复用现有 `messages` 表，不新增 migration。
- `reply_to_id` 指向原 user message。
- 子 message `agent_id` 为实际负责 Agent。
- 每个子 message 使用独立 `StreamContentAccumulator`；block index 是该子 message 的局部 index。
- 父 Orchestrator message 继续承载 task card、process、orchestration 证据与最终用户可见总结。

关闭 `orchestrator_group_messages_enabled=false` 时，Orchestrator 回到旧模式：所有子 Agent block 仍在父 Orchestrator message 中以 `agent_id` 标记。

## 5. 后端文件修改

### 5.1 StreamChunk 类型说明

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

### 5.2 Orchestrator text block helper

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

### 5.3 子 Agent stream remap

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

### 5.4 移除文本 header

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

### 5.5 失败文本归属

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

## 6. Per-task fallback 规则

若任务从原 agent fallback 到另一个 agent：

- `agent_switch.to_agent` 使用实际 attempt agent。
- fallback attempt 的所有输出 chunk 使用 fallback agent id。
- summary 仍由 Orchestrator 输出，`agent_id="orchestrator"`。
- tool_call `call_id` 继续使用当前 `<task_id>.attempt-N.<call_id>` 规则，避免冲突。

## 7. Memory / Summary 影响

`TaskAttempt.agent_id` 已存在，应继续作为结构化 memory 的真实 attempt agent。

本次不要求修改 Orchestrator memory 表结构。

注意：

- 去掉文本 header 后，summary / memory 不应依赖 `@agent` 文本解析。
- `attempt.text_preview` 继续从子 Agent delta 累积。

## 8. 测试计划

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
8. group + Orchestrator + enabled 配置下，子 Agent stream 会创建独立 persisted child message。
9. `orchestrator_group_messages_enabled=false` 时回到旧父消息合流模式。

## 9. 验收标准

- SSE live event 中，子 Agent block/tool chunk 带实际 `agent_id`。
- B1 accumulator 落库后 content block 保留该 `agent_id`。
- 启用真实群聊后，SSE 中出现 `message_start` / `message_done` 或 `message_error`，且子 Agent block/tool event 带子 `message_id`。
- 子 Agent 输出持久化到独立 `messages` 行，`message.agent_id` 为实际 Agent，`reply_to_id` 指向原 user message。
- 前端后续消费 lifecycle 后可按真实 Agent 消息行展示；旧 block attribution 仍作为兼容层保留。
- Orchestrator 消息不再通过纯文本 `@agent` header 表达归属。
- 现有 Orchestrator 任务执行、fallback、summary 行为不回归。

## 10. 边界说明

这项工作不是纯 B1，也不是纯前端。正确职责是：

- B2 生产 attribution。
- B2/API stream runner 持久化真实子消息。
- F 消费 `message_start` / `message_done` / `message_error` 与带 `message_id` 的 block/tool events。

B2 不应要求前端用正文正则解析 `@agent`；那会在 code block、tool_call、失败重试和 fallback 场景中继续失真。

## 11. 2026-06-05 实现与验证证据

实现状态：

- `StreamChunk` 已支持 `message_start`、`message_done`、`message_error`，并允许 block/tool events 携带子 `message_id`。
- group conversation + Orchestrator + `orchestrator_group_messages_enabled=true` 时，API stream runner 会创建独立 child `messages` 行，并用独立 accumulator 持久化子 Agent content。
- 父 Orchestrator message 继续承载 task card、process、orchestration 证据与最终 summary；子 Agent 的 text/code/file/tool output 不再写入父 accumulator。
- 子 Agent lifecycle 的 terminal 状态可以是 `done` 或 `error`；业务失败应落到对应 Agent 的 error child message，而不是让父 Orchestrator 吞掉 stderr。

Repair loop 结论：

- 修复 parallel producer 跑在 outer stream persistence 前面导致 child message 停留 `streaming` 的问题：group messages 启用时，parallel event queue 使用 ack backpressure。
- 修复同一 `AsyncSession` 被 memory writer、group writer、adapter factory 并发使用的问题：`stream_orchestrator_context` 注入共享 `orchestrator_db_lock`，相关路径复用同一把锁。

本地门禁：

```text
cd backend
AGENTHUB_ALLOW_DEV_DB_TESTS=1 uv run python -m pytest tests/test_stream_content_blocks.py tests/test_conversation_api.py tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_response_presentation.py tests/test_orchestrator_tool_calling.py -q
# 122 passed

uv run python -m ruff check app/agents app/api/v1 app/schemas tests
# passed

uv run python -m mypy app/agents app/api/v1 app/schemas
# Success: no issues found in 126 source files

git diff --check
# passed
```

公网 smoke：

```text
report: /tmp/agenthub_group_messages_report.json
sse: /tmp/agenthub_group_messages_sse.jsonl
base_url: http://111.229.151.159:8000
conversation_id: 0948e3a6-1fc4-40a2-8cf7-3e348b2047ae
parent_message_id: fc81e594-5f4c-4eca-b593-570d629e6f71
run_id: 34f5ef15-e649-4827-84e4-0808037f8cfe
message_start: 2
message_done: 1
message_error: 1
child_statuses:
  web-designer: done
  writer: error
checks:
  child_agents_are_not_orchestrator: true
  child_content_present: true
  no_child_left_streaming: true
  all_child_messages_terminal: true
  final_text_no_forbidden_terms: true
  sse_no_core_trace: true
  temporary_config_restored: true
passed: true
```

部署记录：

```text
backend_pid: 1189179 -> 1203019
alembic_current: 7e8f9012abcd (head)
local_health: {"status":"ok"}
public_health: {"status":"ok"}
```

## 12. 2026-06-06 通用场景回归扩展

新增 live E2E scenarios 用于验证 message attribution 不依赖前端质量演示模板：

- `group_process_document_strategy`
- `group_process_data_analysis`
- `group_process_workflow_delivery`
- `group_process_failure_readable`
- `group_process_frontend_preview`

这些 case 的共同验收点：

- SSE 出现 child `message_start` / terminal lifecycle。
- persisted messages 中子 Agent 为独立 `messages` 行，`agent_id` 不是 Orchestrator。
- 子 message 有自己的 `process` block，并能接收 `process_delta`。
- 父 Orchestrator message 不内嵌子 Agent 的 text/code/file/tool 输出。
- 可见文本不包含 `ReAct step`、`Observation:`、`Action:`、`Tools:`、`call_`、
  raw stderr 或 stack trace。

本轮本地脚本/规划/stream 门禁通过，但 live `passed=true` 暂未达成：

- Codex CLI 当前额度限制到 `2026-06-11 17:54`，不能作为必须成功的外部 runtime gate。
- 公网 `111.229.151.159:8000` 请求未命中本机已重启 PID `1650213` 的 uvicorn access log；
  后续公网验收前需先确认服务落点。
