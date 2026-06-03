# Message ContentBlock Attribution Spec

> Owner: B1
> Related: [F Orchestrated Rendering](../../frontend/spec/orchestrated-message-rendering.spec.md), [B2 Orchestrator Attribution](../../b2/spec/orchestrator/message-attribution.spec.md)

## 1. 目标

支持 `messages.content` 中每个 ContentBlock 保存实际来源 Agent，使 Orchestrator 编排消息可以在前端按子 Agent 分段展示。

B1 负责：

- OpenAPI 契约更新。
- Pydantic message schema 更新。
- SSE stream accumulator 持久化 `agent_id`。
- 保持旧消息兼容。

B1 不负责：

- 判断子 Agent 归属来源。
- 修改 Orchestrator 调度逻辑。
- 前端分组 UI。

## 2. 当前问题

当前一条 Orchestrator 消息形态：

```json
{
  "role": "agent",
  "agent_id": "orchestrator",
  "content": [
    { "type": "text", "text": "Planned..." },
    { "type": "text", "text": "@claude-code\n\n设计视角..." },
    { "type": "text", "text": "@opencode-helper\n\n实现视角..." }
  ]
}
```

问题：

- 子 Agent 归属只藏在文本里。
- 前端刷新后无法可靠切分。
- tool_call / error / code block 无法可靠归属。

## 3. 契约变更

所有 ContentBlock 增加可选字段：

```yaml
agent_id:
  type: string
  nullable: true
  description: Actual agent that produced this content block. Defaults to parent message.agent_id when omitted.
```

涉及 schema：

- `TextBlock`
- `CodeBlock`
- `DiffBlock`
- `WebPreviewBlock`
- `FileBlock`
- `ToolCallBlock`

语义：

- `Message.agent_id` 表示顶层响应 Agent。
- `ContentBlock.agent_id` 表示该 block 的真实输出 Agent。
- 为空时调用方应继承 `Message.agent_id`。

## 4. 后端文件修改

### 4.1 OpenAPI

文件：

- `shared/openapi.yaml`

修改：

- 上述所有 ContentBlock schema 增加 optional `agent_id`。
- 不需要新增 endpoint。
- 不需要修改 `Message` 顶层结构。

完成后 F 需要运行：

```bash
cd frontend
pnpm gen:types
```

### 4.2 Pydantic Schema

文件：

- `backend/app/schemas/message.py`

修改示例：

```python
class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    agent_id: str | None = None
    text: str
```

所有 block schema 同步增加 `agent_id`。

### 4.3 StreamContentAccumulator

文件：

- `backend/app/api/v1/stream_accumulator.py`

规则：

1. `block_start` 时创建 `self.current`，保存 `chunk.agent_id`。
2. 如果 `chunk.agent_id` 为空，尝试读取 `chunk.metadata["agent_id"]`。
3. `tool_call` 时创建 block，保存 `chunk.agent_id`。
4. `tool_result` 只更新已有 tool_call block，不覆盖 `agent_id`。
5. `_finalize_current()` 处理 diff 时保留 `agent_id`。

伪代码：

```python
def _chunk_agent_id(chunk: StreamChunk) -> str | None:
    if chunk.agent_id:
        return chunk.agent_id
    value = (chunk.metadata or {}).get("agent_id")
    return value if isinstance(value, str) and value else None
```

`block_start`：

```python
self.current = {"type": chunk.block_type or "text"}
agent_id = _chunk_agent_id(chunk)
if agent_id:
    self.current["agent_id"] = agent_id
```

`tool_call`：

```python
block = {
    "type": "tool_call",
    "call_id": chunk.call_id,
    "tool_name": chunk.tool_name,
    "arguments": ...,
    "status": "pending",
}
if chunk.agent_id:
    block["agent_id"] = chunk.agent_id
```

`diff` finalize 必须保留：

```python
agent_id = self.current.get("agent_id")
self.current = {...}
if agent_id:
    self.current["agent_id"] = agent_id
```

## 5. 数据库影响

不需要 migration。

原因：

- `messages.content` 是 JSONB。
- 新字段是 optional。
- 旧数据没有 `agent_id` 仍可被 Pydantic 解析。

## 6. 测试计划

新增/更新：

- `backend/tests/test_stream_tool_calls.py`
- 或新增 `backend/tests/test_stream_accumulator.py`

覆盖：

1. text block 持久化 `agent_id`。
2. code block 持久化 `agent_id`。
3. diff block finalize 后不丢 `agent_id`。
4. tool_call block 持久化 `agent_id`。
5. tool_result 更新状态时保留 `agent_id`。
6. 没有 `agent_id` 的旧 chunk 行为不变。
7. `MessageOut` 能序列化带 `agent_id` 的 content。

## 7. 验收标准

- `GET /conversations/{id}/messages` 返回的 content block 中保留 `agent_id`。
- SSE done 后刷新页面，前端仍可按 Agent 分组。
- 旧消息没有 `agent_id` 不报错。
- 不改变 `Message.agent_id` 语义。
- 后端测试、ruff、mypy 通过。

## 8. 边界说明

这项后端工作 **属于 B1 + B2 交界**。

- B2 负责生成正确 `StreamChunk.agent_id`。
- B1 负责 schema / OpenAPI / accumulator 持久化。

如果 B2 未提供 chunk attribution，B1 不应通过解析文本 `@agent` 猜测归属。

## 9. B1 实施方案

本任务按 P0-P3 拆分，目标是先让后端可保存 attribution，再让 API 契约和测试完整闭环。

### P0: Schema / OpenAPI 契约落地

修改范围：

- `backend/app/schemas/message.py`
- `shared/openapi.yaml`

实施要求：

- 为 `TextBlock`、`CodeBlock`、`DiffBlock`、`WebPreviewBlock`、`FileBlock`、`ToolCallBlock` 增加 optional `agent_id`。
- OpenAPI 字段保持 optional，不加入 `required`。
- 不改变 `Message.agent_id` 顶层语义。
- 不新增 endpoint，不新增 migration。

验收点：

- 旧消息 content block 不带 `agent_id` 仍可通过 `MessageOut` 序列化。
- 新消息 content block 带 `agent_id` 时 API 响应保留该字段。

### P1: StreamContentAccumulator 持久化

修改范围：

- `backend/app/api/v1/stream_accumulator.py`

实施要求：

- 新增 `_chunk_agent_id(chunk)` helper，优先读 `chunk.agent_id`，为空时读 `chunk.metadata["agent_id"]`。
- `block_start` 创建 text / code / diff / web_preview 当前 block 时写入 `agent_id`。
- `tool_call` 创建 `ToolCallBlock` 时写入 `agent_id`。
- `tool_result` 只更新已有 tool block 的状态、输出和错误码，不覆盖 `agent_id`。
- `_finalize_current()` 将 diff raw block 转成 final diff block 时必须保留 `agent_id`。

禁止事项：

- 不解析正文里的 `@claude-code`、`@opencode-helper` 等文本来猜测归属。
- 不在 B1 中判断子 Agent 来源；没有结构化 `agent_id` 就保持为空。

### P2: 后端测试闭环

推荐测试文件：

- `backend/tests/test_stream_content_blocks.py`
- `backend/tests/test_stream_tool_calls.py`

必须覆盖：

1. text block 持久化 `agent_id`。
2. code block 持久化 `agent_id`。
3. diff block finalize 后保留 `agent_id`。
4. tool_call block 持久化 `agent_id`。
5. tool_result 更新状态时保留原 tool block `agent_id`。
6. `metadata["agent_id"]` fallback 生效。
7. 没有 `agent_id` 的旧 chunk 行为不变。
8. `MessageOut` 能序列化带 `agent_id` 的 content block。

验证命令：

```bash
docker compose exec -T backend pytest tests/test_stream_tool_calls.py tests/test_stream_content_blocks.py -q
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

### P3: 协作交付与前端提醒

交付要求：

- PR 描述标注这是 B1/B2/F 交界契约变更。
- 明确说明：B1 只保存 attribution，B2 负责生产真实 `StreamChunk.agent_id`，F 负责消费 `block.agent_id ?? message.agent_id`。
- 提醒 F 在合并后运行：

```bash
cd frontend
pnpm gen:types
pnpm test
pnpm build
```

AI 协作证据：

- 使用 [../../ai-skills/b1-contract-change/SKILL.md](../../ai-skills/b1-contract-change/SKILL.md) 作为执行流程。
- 若实现中调整了 owner 边界或测试策略，需要追加 `docs/ai-collaboration-log.md`。
