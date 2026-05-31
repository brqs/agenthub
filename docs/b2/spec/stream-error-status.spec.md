# Stream Error Status Spec

> 状态：Implemented historical boundary
> 最后更新：2026-05-31

> 维护说明：本文档记录 B2-06 时 B1 SSE 层消费 B2 `StreamChunk(error)` 的协同规则。当前代码已将 stream 入口拆薄，相关逻辑分散在 `backend/app/api/v1/stream.py`、`stream_accumulator.py`、`stream_orchestrator_context.py` 和 `stream_preview.py`；本文保留为错误状态持久化规则，不作为 stream 模块结构索引。

## 目标

明确 B1 SSE 层消费 B2 `StreamChunk` 时的错误状态持久化规则，避免上游 Agent 已经失败但消息仍被标记为 `done`，或失败前已生成的内容被意外丢弃。

本 Spec 服务于 B2-06，属于 B1/B2 协同边界：

- B2 负责定义 Adapter error chunk 的语义。
- B1 `backend/app/api/v1/stream.py` 负责把流式事件转换为 SSE，并持久化 `Message.status` 与 `Message.content`。

## 输入 / 输出

输入：

- `BaseAgentAdapter.stream()` 产生的 `AsyncIterator[StreamChunk]`
- `StreamChunk.event_type`
- 客户端连接状态 `request.is_disconnected()`
- pending agent message

输出：

- SSE event stream
- `messages.status`: `streaming` / `done` / `error`
- `messages.content`: 已累积的 ContentBlock 列表

## 状态规则

### 正常完成

当 Adapter 流正常结束，且未出现 `error` chunk，且客户端未断开：

- SSE 继续转发所有 chunk。
- `message.status = "done"`。
- `message.content` 保存累积出的 blocks。

### Adapter 主动返回 error chunk

当 Adapter yield `StreamChunk(event_type="error")`：

- SSE 必须把该 error chunk 转发给客户端。
- `_event_generator` 必须立即停止继续消费 Adapter。
- `message.status = "error"`。
- `message.content` 必须保存 error 之前已经累积出的 blocks。
- 已打开但未收到 `block_end` 的当前 block，应在持久化前被收尾保存。

### Adapter 抛异常

当 Adapter 在 streaming 过程中抛出非 `AgentNotFoundError` 异常：

- SSE 必须返回 `event: error`，`error_code="internal_error"`。
- `message.status = "error"`。
- `message.content` 必须保存异常前已经累积出的 blocks。
- 不允许异常逃逸成 HTTP 500 中断 SSE 响应。

### Agent 不存在

当 `get_adapter()` 抛 `AgentNotFoundError`：

- SSE 返回 `event: error`，`error_code="agent_not_found"`。
- `message.status = "error"`。
- 如果此前没有任何 chunk，`message.content` 保持空列表。

### Message 缺少 agent_id

当 agent message 没有 `agent_id`：

- SSE 返回 `event: error`，`error_code="missing_agent"`。
- `message.status = "error"`。
- `message.content` 保持空列表。

### 客户端断开

当 `request.is_disconnected()` 返回 true：

- 停止继续消费 Adapter。
- `message.status = "error"`。
- `message.content` 保存断开前已经累积出的 blocks。

## 边界

- 本任务不修改 `BaseAgentAdapter.stream()` 签名。
- 本任务不修改 `StreamChunk` schema。
- 本任务不修改 OpenAPI。
- 本任务不改变 Adapter 内部错误映射规则。
- 本任务只处理 SSE 层的消费、停止和持久化策略。

## 验收标准

- Adapter error chunk 不会被误标记为 `done`。
- Adapter 抛异常时，SSE 返回 `internal_error`，消息状态为 `error`。
- error 前已完成或正在进行的 block 会被持久化。
- 正常流仍标记为 `done`，既有成功路径不回归。
- 缺失 agent / agent 不存在仍返回 error event。
- 相关行为有自动化测试覆盖。
