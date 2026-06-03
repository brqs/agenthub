# Orchestrated Message Rendering Spec

> Owner: F
> Related: [B1 ContentBlock Attribution](../../b1/spec/message-content-block-attribution.spec.md), [B2 Orchestrator Attribution](../../b2/spec/orchestrator/message-attribution.spec.md)

## 1. 目标

Orchestrator 群聊消息需要按真实输出 Agent 分段展示。用户看到的聊天流应表达：

- Orchestrator 负责计划、调度和总结。
- Claude Code / Codex / OpenCode 等子 Agent 负责各自输出。
- Tool call、错误、文件产物归属到实际执行 Agent。

当前问题是后端把多个子 Agent 的输出合并到一条 `agent_id="orchestrator"` 的 Message 中。前端只能按 message 级 `agent_id` 渲染头像和作者，因此子 Agent 内容会全部显示为 Orchestrator。

## 2. 输入契约

B1/B2 完成后，Message 的每个 ContentBlock 可带可选 `agent_id`：

```ts
type ContentBlock = {
  type: string;
  agent_id?: string | null;
  // block-specific fields...
};
```

语义：

- `message.agent_id`：顶层负责 Agent。Orchestrator 编排消息仍为 `orchestrator`。
- `block.agent_id`：该 block 的实际来源 Agent。
- `block.agent_id` 为空时，前端继承 `message.agent_id`，兼容旧消息。

示例：

```json
{
  "agent_id": "orchestrator",
  "content": [
    { "type": "text", "agent_id": "orchestrator", "text": "Planned 2 sub-task(s)..." },
    { "type": "agent_switch", "from_agent": "orchestrator", "to_agent": "claude-code" },
    { "type": "text", "agent_id": "claude-code", "text": "设计视角..." },
    { "type": "tool_call", "agent_id": "claude-code", "tool_name": "write_file" },
    { "type": "text", "agent_id": "opencode-helper", "text": "实现视角..." },
    { "type": "text", "agent_id": "orchestrator", "text": "Execution summary..." }
  ]
}
```

## 3. 展示规则

### 3.1 普通消息

非 Orchestrator 消息保持现有 `MessageBubble` 展示：

- 用户消息右侧气泡。
- Agent 消息左侧头像 + 作者名 + content blocks。

### 3.2 Orchestrator 消息

当 `message.agent_id === "orchestrator"` 且存在至少一个 `block.agent_id !== "orchestrator"` 时，启用 grouped rendering。

分组规则：

1. 遍历 `message.content`。
2. 对每个 block 计算归属：`owner = block.agent_id ?? message.agent_id ?? "agent"`。
3. 连续相同 owner 的正文 block 合并为一个视觉段落。
4. `agent_switch` 作为轻量调度分隔，可显示在两个段落之间，但不改变正文归属。
5. `tool_call` 跟随自己的 `agent_id` 所属段落。
6. 没有 `agent_id` 的历史 block 归属 Orchestrator。

目标视觉结构：

```text
Orchestrator
Planned 2 sub-task(s)...

Claude Code
设计视角...
[write_file tool call]

OpenCode Helper
实现视角...

Orchestrator
Execution summary...
```

### 3.3 错误展示

子 Agent 失败 block 应归属实际失败 Agent：

```json
{ "type": "text", "agent_id": "opencode-helper", "text": "failed: ..." }
```

前端展示为 `OpenCode Helper` 的错误段，而不是 Orchestrator 大段正文。

### 3.4 兼容旧消息

旧消息没有 `block.agent_id` 时：

- 不做文本正则拆分作为主路径。
- 继续按 `message.agent_id` 渲染。
- 不因为缺字段报错。

## 4. 前端修改清单

### 4.1 类型

文件：

- `frontend/src/lib/types.ts`
- `frontend/src/lib/mockData.ts`

改动：

- 为所有 ContentBlock 类型增加可选 `agent_id?: string | null`。
- 如果 OpenAPI 重新生成类型后已有字段，移除手写重复定义。
- Demo 扩展块 `task_card` / `agent_switch` 可暂不加 `agent_id`，但 renderer 必须兼容。

### 4.2 流式状态

文件：

- `frontend/src/lib/types.ts`
- `frontend/src/stores/chatStore.ts`

改动：

- `StreamEvent.block_start` 增加 `agent_id?: string`。
- `StreamEvent.delta` 可选 `agent_id?: string`，但前端以 `block_start.agent_id` 为准。
- `StreamEvent.tool_call` / `tool_result` 增加 `agent_id?: string`。
- `chatStore.applyStreamEvent` 创建 block 时保存 `agent_id`。
- `tool_result` 只更新匹配 `call_id` 的 block，保留原 block `agent_id`。

### 4.3 渲染组件

建议新增：

- `frontend/src/components/chat/OrchestratedMessageBubble.tsx`
- `frontend/src/components/chat/messageGrouping.ts`

`messageGrouping.ts` 负责纯函数：

```ts
interface MessageBlockGroup {
  agentId: string | null;
  blocks: DemoContentBlock[];
}

export function groupMessageBlocks(
  messageAgentId: string | null | undefined,
  blocks: DemoContentBlock[],
): MessageBlockGroup[];
```

`MessageBubble.tsx` 中：

- 若是用户消息，保持原逻辑。
- 若是 Orchestrator 且 `groupMessageBlocks()` 返回多个 owner，使用 `OrchestratedMessageBubble`。
- 否则保持原逻辑。

### 4.4 Agent 名称和头像

分组段落中根据 `agentId` 查找 `agents`：

- 找到则显示 `AgentAvatar` + `agent.name`。
- 找不到则显示 `agentId`。
- `agentId === "orchestrator"` 使用 Orchestrator 的 Agent 数据。

### 4.5 不做事项

- 不用正则解析正文里的 `@claude-code` 作为长期方案。
- 不把 `agent_switch` 当正文归属来源。
- 不在前端猜测 tool_call 属于哪个 Agent；必须依赖 block/event `agent_id`。

## 5. 测试计划

新增/更新测试：

- `frontend/src/components/chat/messageGrouping.test.ts`
- `frontend/src/components/chat/MessageBubble.test.tsx`
- `frontend/src/stores/chatStore.test.ts`

覆盖：

1. 连续相同 `agent_id` block 合并。
2. Orchestrator plan / summary 仍显示为 Orchestrator。
3. 子 Agent text block 显示对应 Agent 名称和头像。
4. ToolCallBlock 跟随 `agent_id` 分组。
5. 旧消息没有 block `agent_id` 时保持旧渲染。
6. 流式 `block_start(agent_id)` 后 delta 聚合到带归属的 block。
7. 子 Agent error text 不显示为 Orchestrator 作者。

## 6. 验收标准

- 截图中的 Orchestrator 大消息不再把所有子 Agent 内容显示为 Orchestrator。
- 刷新页面后分组仍正确，因为归属信息已持久化。
- SSE 流式过程中分组逐步稳定显示，不等 done 才切分。
- 旧历史消息仍可正常展示。
- `pnpm tsc --noEmit`、`pnpm lint`、`pnpm test -- --run`、`pnpm build` 通过。
