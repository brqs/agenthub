# AgentHub 前端更新记录

> 本文档用于记录前端开发过程中的重要更新。
> 适用范围：`frontend/**`、前端相关 API 对接、前端 Mock、UI/交互、SSE 消费、富媒体渲染。
> 维护人：F（前端），涉及契约或跨模块变更时需同步 B1 / B2。

---

## 记录格式

```markdown
## YYYY-MM-DD — <更新标题>

### 改动范围
- <涉及页面 / 组件 / hook / store / lib>

### 更新内容
- <本次做了什么>

### API / 契约影响
- <是否涉及 shared/openapi.yaml、types.ts、后端接口>

### 验证方式
- <pnpm dev / pnpm test / pnpm tsc --noEmit / 手动验证路径>

### 后续事项
- <待补充、风险、需要其他成员配合的点>
```

---

## 2026-05-25 — 创建前端开发计划与更新记录

### 改动范围
- `docs/frontend-development-plan.md`
- `docs/frontend-changelog.md`

### 更新内容
- 新增前端开发计划，明确 AgentHub 前端采用自有品牌视觉 + Discord 式信息架构。
- 明确第一阶段桌面 Demo 优先，UI 与 Mock 数据并行推进，后续平滑接入真实 API 与 SSE。
- 新增本文档，用于持续记录前端开发更新。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及 `frontend/src/lib/types.ts` 重新生成。

### 验证方式
- 文档结构检查完成。

### 后续事项
- 前端实际开发开始后，每个重要 PR 或阶段性功能完成后追加记录。

---

## 2026-05-25 — 实现 Discord 式桌面 Mock 聊天界面

### 改动范围
- `frontend/src/components/layout/AppLayout.tsx`
- `frontend/src/components/layout/ModuleRail.tsx`
- `frontend/src/components/conversation/ConversationSidebar.tsx`
- `frontend/src/components/conversation/ConversationItem.tsx`
- `frontend/src/components/chat/ChatHeader.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/agents/AgentAvatar.tsx`
- `frontend/src/components/agents/RightAgentPanel.tsx`
- `frontend/src/components/blocks/*`
- `frontend/src/lib/mockData.ts`
- `frontend/src/stores/chatStore.ts`
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/vite.config.ts`

### 更新内容
- 完成第一版桌面四栏布局：模块栏、会话栏、聊天主区、右侧 Agent / 上下文栏。
- 新增本地 Mock Agent、会话、消息、任务卡片数据。
- 新增 Mock 聊天状态管理，支持发送消息后模拟 Agent 逐字回复。
- 新增登录页“进入前端 Demo”入口，方便无后端时直接查看前端效果。
- 新增 Agent 管理页 Mock 卡片视图。
- 新增基础富媒体渲染组件：Text、Code、TaskCard，并为 Diff / WebPreview / File 做降级展示。
- 修复 `vite.config.ts` 的 Vitest 配置类型导入。
- 修复 `useStream` 中 `Partial<ContentBlock>` 对联合类型不兼容的问题。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。
- 当前聊天数据为 Mock，真实 API 接入将从 Hook 层替换。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/vite build`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`

### 后续事项
- 接入真实 `useConversations`、`useMessages`、`useAgents` hooks。
- 将 Mock 流式回复替换为 `@microsoft/fetch-event-source` 的真实 SSE。
- 为 `TaskCardBlock` 补正式 OpenAPI / ContentBlock 契约前，需要先与 B1 / B2 同步。

---

## 2026-05-25 — 用 Mock 实现 API Hooks 与 SSE 接入形态

### 改动范围
- `frontend/src/hooks/useConversations.ts`
- `frontend/src/hooks/useMessages.ts`
- `frontend/src/hooks/useAgents.ts`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/hooks/useStream.ts`
- `frontend/src/lib/sse.ts`
- `frontend/src/stores/chatStore.ts`
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/pages/AgentsPage.tsx`

### 更新内容
- 在后端 API 尚未完成的情况下，新增前端 API hooks 的 Mock 实现。
- `ChatPage` 改为通过 `useConversations`、`useMessages`、`useSendMessage` 和 `useStream` 组织数据流。
- `useSendMessage` 模拟真实发送消息流程，返回 pending agent message id。
- `lib/sse.ts` 新增 Mock SSE 分支，使用真实 SSE 事件形态模拟 `start`、`block_start`、`delta`、`block_end`、`done`。
- `useStream` 支持向外透出事件回调，页面可将流式事件同步写入消息状态。
- `chatStore` 新增 `createPendingExchange` 和 `applyStreamEvent`，为后续真实 API / SSE 替换保留稳定边界。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。
- 约定 `VITE_USE_MOCK_API !== 'false'` 时使用 Mock SSE；后续接真实后端时可通过环境变量关闭。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`

### 后续事项
- 后端完成后，将 hooks 内部数据源从 Mock store 替换为 TanStack Query + `api.ts`。
- `lib/sse.ts` 已保留真实 `fetchEventSource` 分支，后端 SSE 可用后将 `VITE_USE_MOCK_API=false` 进行联调。

---

## 2026-05-25 — 补齐 Mock 新建会话与 Agent Mention 体验

### 改动范围
- `frontend/src/components/conversation/NewConversationDialog.tsx`
- `frontend/src/components/conversation/ConversationSidebar.tsx`
- `frontend/src/components/chat/AgentMentionPicker.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/hooks/useCreateConversation.ts`
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/stores/chatStore.ts`

### 更新内容
- 新增 Mock 新建会话弹窗，支持单聊 / 群聊模式。
- 支持在新建会话时选择一个或多个 Agent，群聊默认补入 Orchestrator。
- 会话栏的新建按钮已接入弹窗，创建后自动跳转到新会话。
- 新增 `useCreateConversation`，模拟真实创建会话 mutation 的调用形态。
- 群聊输入框支持输入 `@` 触发 Agent Mention Picker。
- 选择 Agent 后会插入 `@agent-id`，Mock 发送逻辑会优先把回复路由给被提及的 Agent。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。
- 目前新建会话和 mention 仍为前端 Mock 行为，后续可替换为 `POST /api/v1/conversations` 和消息发送中的 `target_agent_id`。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`

### 后续事项
- 将 `AgentMentionPicker` 从本地 Mock Agent 数据改为通过 props / hook 注入，减少组件对 Mock 数据的直接依赖。
- 接入真实后端时，需要把 `@agent-id` 解析结果转换为 `target_agent_id`。
