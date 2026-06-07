# Frontend Demo Polish Spec

## 目标

打磨桌面 Demo 的关键体验状态，让演示过程更稳定、更清晰，减少空白、卡顿和错误状态带来的不确定性。

## 输入 / 输出

输入：

- 会话列表为空、搜索无结果、消息列表为空、消息加载中。
- 消息发送中、Agent 流式回复中、SSE error 事件。

输出：

- 会话搜索无结果时展示空状态。
- 新会话无消息时展示引导空态。
- 消息加载中展示轻量 loading。
- Agent 回复处于 `pending` 或 `streaming` 且内容块为空时，气泡内展示轻量状态文案，不能显示空白气泡。
- 发送中禁用输入和发送按钮。
- 错误消息展示错误样式和重试按钮。

## 边界 / 错误处理

- 当前阶段不改真实 API。
- 重试只针对当前 Mock message id 重新订阅流。
- 错误 UI 不应影响已有消息展示。

## 性能要求

- 消息更新后自动滚动到底部。
- Loading / empty / error 状态保持固定尺寸，避免演示时大面积跳动。

## 依赖

- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/conversation/ConversationSidebar.tsx`
- `frontend/src/stores/chatStore.ts`

## 验收标准

- 新建会话后中间区域展示空态。
- 发送中输入框和发送按钮进入 disabled 状态。
- 错误消息有重试入口。
- 会话搜索无结果时有明确空态。
- `tsc`、`eslint`、`vite build` 通过。
