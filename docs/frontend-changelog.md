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
