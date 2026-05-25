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

---

## 2026-05-25 — 完成 Mock 多 Agent 协作演示闭环

### 改动范围
- `docs/spec/frontend-chat-demo.spec.md`
- `frontend/src/lib/sse.ts`
- `frontend/src/lib/mockData.ts`
- `frontend/src/stores/chatStore.ts`
- `frontend/src/components/blocks/ContentRenderer.tsx`

### 更新内容
- 新增前端聊天 Demo Spec，明确 Mock 多 Agent 协作流的目标、边界和验收标准。
- Mock SSE 新增 Orchestrator 场景事件序列，包含任务卡、文本回复、Agent 切换和代码块输出。
- 新增前端 Demo 专用 `agent_switch` 内容块，用于在消息流中展示 Agent 接力分隔。
- `TaskCardBlock` 支持跟随 `agent_switch` 事件推进任务状态，流式完成后自动收尾 running 任务。
- 普通单聊仍保留基础 Mock 流式文本回复。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。
- `task_card` 与 `agent_switch` 当前为前端 Demo 扩展块，真实契约落地前需要与 B1 / B2 同步。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`
- 浏览器手动验证：进入群聊后发送 `@orchestrator 做一次群聊多 Agent 协作演示`，确认任务卡、Agent 切换分隔和代码块正常出现。

### 后续事项
- 继续打磨 `CodeBlock`、`DiffBlock`、`WebPreviewBlock`、`FileBlock`。
- 接入真实后端时，需要把 `agent_switch` 与 `task_card` 正式纳入 ContentBlock / SSE 契约。

---

## 2026-05-25 — 打磨富媒体消息块展示

### 改动范围
- `docs/spec/frontend-content-blocks.spec.md`
- `frontend/src/components/blocks/CodeBlock.tsx`
- `frontend/src/components/blocks/ContentRenderer.tsx`
- `frontend/src/components/blocks/DiffBlock.tsx`
- `frontend/src/components/blocks/WebPreviewBlock.tsx`
- `frontend/src/components/blocks/FileBlock.tsx`
- `frontend/src/components/blocks/UnknownBlock.tsx`
- `frontend/src/lib/mockData.ts`

### 更新内容
- 新增富媒体消息块 Spec，明确 code、diff、web preview、file 与未知 block 的验收标准。
- `CodeBlock` 新增 Shiki 异步代码高亮，保留纯文本回退，并优化复制按钮状态。
- 新增 `DiffBlock`，使用 unified 风格展示新增、删除和上下文行。
- 新增 `WebPreviewBlock`，展示站点、标题、描述、URL 和外链入口。
- 新增 `FileBlock`，展示文件类型图标、文件名、大小和打开入口。
- 新增 `UnknownBlock`，用于未知消息块的安全降级展示。
- `conv-demo-flow` 补充 diff、web_preview 和 file Mock 示例，方便 Demo 直接检查。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。
- 本次仅消费已有 `ContentBlock` placeholder 类型，并继续保留前端 Demo 扩展块。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`

### 后续事项
- 可继续为 `ContentRenderer`、`CodeBlock` 复制行为和 `DiffBlock` 行渲染补组件测试。
- 真实契约稳定后，用 `pnpm gen:types` 替换当前 placeholder 类型。

---

## 2026-05-25 — 完成 Agent 管理页与 Demo 打磨

### 改动范围
- `docs/spec/frontend-agent-management.spec.md`
- `docs/spec/frontend-demo-polish.spec.md`
- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/components/agents/AgentCard.tsx`
- `frontend/src/components/agents/AgentCreateDialog.tsx`
- `frontend/src/components/agents/AgentDetailPanel.tsx`
- `frontend/src/stores/agentStore.ts`
- `frontend/src/hooks/useAgents.ts`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/conversation/ConversationSidebar.tsx`
- `frontend/src/stores/chatStore.ts`

### 更新内容
- 新增 Agent 管理页 Spec 与 Demo 打磨 Spec。
- Agent 管理页新增“我的 Agent / 内置 Agent”分组、搜索、统计卡和右侧详情栏。
- 新增 Mock 创建 Agent 表单，创建后写入 `agentStore` 并自动进入详情态。
- `useAgents` 改为从 `agentStore` 读取，为后续真实 API 替换保留 Hook 边界。
- 消息列表新增 loading 状态和新会话空态。
- 消息错误状态新增重试按钮，重试会重置当前消息并重新订阅 Mock SSE。
- 消息输入在发送中进入 disabled 状态，避免重复提交。
- 会话搜索无结果时展示空状态。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。
- Agent 创建仍为前端 Mock 行为，后续可替换为真实 Agent CRUD API。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`
- 浏览器手动验证：进入 Agent 管理页，创建 `Frontend Reviewer`，确认“我的 Agent”、右侧详情与聊天入口正常。

### 后续事项
- 可继续补 AgentsPage、AgentCreateDialog、MessageList 的组件测试。
- 后端 Agent API 稳定后，将 `agentStore` 创建行为替换为 mutation + query invalidation。
