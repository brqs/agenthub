# Frontend Chat Demo Spec

## 目标

完成桌面 Demo 中的 Mock 多 Agent 协作闭环，让群聊会话可以展示 Orchestrator 任务拆解、Agent 切换、任务状态推进和流式回复。

## 输入 / 输出

输入：

- 用户在聊天输入框发送普通文本。
- 群聊中用户可使用 `@agent-id` 指定目标 Agent。
- Mock SSE 根据待回复消息的目标 Agent 生成事件序列。

输出：

- 用户消息立即追加到当前会话。
- Agent 回复进入 streaming 状态。
- Orchestrator 场景展示任务卡、Agent 切换分隔和最终回复。
- 单 Agent 场景保持普通流式文本回复。

## 边界 / 错误处理

- 当前阶段不修改 `shared/openapi.yaml`。
- `task_card` 与 `agent_switch` 仅作为前端 Demo 扩展块存在。
- 未知 SSE 事件应被忽略，不能导致 UI 崩溃。
- SSE error 事件需要把消息状态更新为 error，并在消息内容中展示错误信息。

## 性能要求

- Mock 流式更新不应造成整页明显卡顿。
- 消息流更新时自动滚动到底部。
- UI 元素不应因任务状态变化产生明显布局跳动。

## 依赖

- `frontend/src/lib/sse.ts`
- `frontend/src/stores/chatStore.ts`
- `frontend/src/components/blocks/TaskCardBlock.tsx`
- `frontend/src/components/blocks/ContentRenderer.tsx`
- `frontend/src/components/chat/MessageList.tsx`

## 验收标准

- 群聊默认发送给 Orchestrator 时能看到任务卡和 Agent 切换。
- `agent_switch` 能以清晰的分隔 UI 出现在消息内容中。
- TaskCard 任务状态能从 pending / running 推进到 done。
- 普通单聊仍可正常展示流式文本。
- `tsc`、`eslint`、`vite build` 通过。
