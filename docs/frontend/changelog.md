# AgentHub 前端更新记录

> 本文档用于记录前端开发过程中的重要更新。
> 适用范围：`frontend/**`、前端相关 API 对接、前端 Mock、UI/交互、SSE 消费、富媒体渲染。
> 维护人：F（前端），涉及契约或跨模块变更时需同步 B1 / B2。

---

## 当前状态总览（2026-05-25）

### 端点接入面（含真后端冒烟结果）

| 端点 | 前端接入 | 真后端冒烟 |
|---|---|---|
| `POST /auth/register` | ✅ `LoginPage` | ✅ 201 |
| `POST /auth/login` | ✅ `LoginPage` | ✅ 200 + JWT |
| `GET /auth/me` | ✅ `AuthGuard` | ✅ 200 |
| `GET /conversations` | ✅ `useConversations` | ✅ `{items,total,page,page_size}` |
| `POST /conversations` | ✅ `useCreateConversation` | ✅ 返回 ConversationOut |
| `PATCH/DELETE /conversations/{id}` | 🔴 未接 | — |
| `GET /conversations/{id}/messages` | ✅ `useMessages` | ✅ |
| `POST /conversations/{id}/messages` | ✅ `useSendMessage` | ✅ 返回 `{user_message, agent_message}` |
| `POST /messages/{id}/regenerate` | 🔴 未接 | — |
| `PATCH/DELETE /messages/{id}` | 🔴 未接 | — |
| `GET /messages/{id}/stream` (SSE) | ✅ `subscribeMessageStream` | 🟡 通道工作，handshake/event 格式正确；上游 Anthropic Connection error，未到 delta |
| `GET /agents` | ✅ `useAgents` | ✅ 5 个 builtin seed |
| `POST /agents` | ✅ `useCreateAgent` | 🟡 `provider:claude` ✅；`provider:custom` 后端要求 `upstream_provider` 但 OpenAPI 没有该字段，必失败 |
| `PATCH/DELETE /agents/{id}` | 🟡 adapter 已实现，UI 未做 | — |

### 验证状态

`tsc -b` ✅ · `eslint --max-warnings 0` ✅ · `npx vitest --run` 19/19 ✅ · `vite build` ✅
`vite --port 5179` 86ms 起来 ✅ · `/api` 代理转发 → 后端 401 ✅（无 token 时）

### 已知阻塞 / 后端问题

- 🟡 **B2 Anthropic 上游报 `Connection error.`**（SSE 端到端没拿到 delta，agent_message 直接落到 `status=error`）。前端 SSE 消费、error 渲染、retry 重置都已就位，等 B2 处理 API Key / 网络后即可端到端跑通。
- 🟡 **`POST /agents` provider=custom** 后端要求 `upstream_provider` 字段但未在 OpenAPI 声明，Pydantic 会剥掉额外字段。前端 `AgentCreateDialog` 默认值已临时改为 `provider:claude` 避开。需要 B1/B2 把 `upstream_provider` 加进 `CreateAgentRequest` schema，或后端取消该校验。
- ⚠️ **`POST /messages` 后没回填 `last_message_preview`**（仍为 `null`）。前端 `chatStore.appendRemoteExchange` 自己算了本地 preview，所以 UI 不受影响，但服务器侧的列表预览暂时一直是空。
- ⚠️ **OpenAPI 多字段未标 `required`**（`agent_ids` / `capabilities` / `config` / `status` / `is_pinned` / `is_archived` / `avatar_url`），前端在 `lib/types.ts` 用 `Override` 临时收窄。

### 默认行为

- `VITE_USE_MOCK_API` 默认 `true` → Mock Demo 不依赖后端，比赛演示路径不变。
- 设 `VITE_USE_MOCK_API=false` → 全部 hooks 走真实后端；SSE 跟随 `VITE_USE_MOCK_SSE`（默认跟随 `VITE_USE_MOCK_API`）。
- Vite dev `/api` 代理默认指向 `http://111.229.151.159:8000`，可由 `VITE_DEV_PROXY_TARGET` 覆盖。

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

---

## 2026-05-25 — 增强 Markdown 与网页产物预览

### 改动范围
- `frontend/src/components/blocks/FileBlock.tsx`
- `frontend/src/components/blocks/WebPreviewBlock.tsx`
- `frontend/src/components/blocks/ContentRenderer.tsx`
- `frontend/src/lib/mockData.ts`

### 更新内容
- `FileBlock` 从单纯外链升级为“预览 + 外链”双操作。
- Markdown 文件支持点击后在弹层内渲染 Markdown 内容。
- `WebPreviewBlock` 支持点击打开内置网页预览弹层。
- Mock WebPreview 增加预览标题与正文，用于模拟构建产物页面。
- Mock Markdown 文件增加可预览内容，覆盖 Demo 演示路径。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- `preview_text`、`preview_title`、`preview_body` 为前端 Mock 扩展字段，真实契约落地前需要与 B1 / B2 同步。

### 验证方式
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`
- 浏览器手动验证：进入 `/chat/conv-demo-flow`，分别点击 Markdown 文件预览和网页预览，确认弹层内容正常展示。

### 后续事项
- 真实后端支持产物文件后，可将预览内容替换为文件读取 API 或 artifact preview API。

---

## 2026-05-25 — 补齐第一批前端测试

### 改动范围
- `frontend/src/stores/chatStore.test.ts`
- `frontend/src/stores/agentStore.test.ts`
- `frontend/src/components/blocks/ContentRenderer.test.tsx`
- `frontend/src/components/blocks/FileBlock.test.tsx`
- `frontend/src/components/blocks/WebPreviewBlock.test.tsx`
- `frontend/src/components/chat/MessageInput.test.tsx`
- `frontend/src/components/chat/MessageInput.tsx`

### 更新内容
- 新增 `chatStore` 测试，覆盖会话创建、消息发送、SSE 事件应用、Agent 路由和重试重置。
- 新增 `agentStore` 测试，覆盖 Mock Agent 创建、重名 id 处理和选中态更新。
- 新增 `ContentRenderer` 测试，覆盖核心 block 分发和 unknown fallback。
- 新增 `MessageInput` 测试，覆盖发送、空文本、Enter / Shift+Enter、发送中禁用和 Agent mention。
- 新增 `FileBlock` 与 `WebPreviewBlock` 测试，覆盖内联预览弹层和安全外链。
- 为 `MessageInput` 的图标按钮补充 `aria-label` / `title`，提升测试稳定性和可访问性。

### API / 契约影响
- 暂不涉及 `shared/openapi.yaml`。
- 暂不涉及重新生成 `frontend/src/lib/types.ts`。

### 验证方式
- `npm test -- --run`
- `./node_modules/.bin/tsc -b`
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
- `./node_modules/.bin/vite build`

### 后续事项
- 继续补 `CodeBlock`、`AgentCreateDialog`、`AgentsPage`、`ChatPage` 页面级测试。
- 真实 API 接入后补 API hooks 与 fetch mock / MSW 相关测试。

---

## 2026-05-25 — 接入远端后端：第一刀 Auth + 列表

### 改动范围
- `frontend/package.json`（`gen:types` 改为从远端 `/openapi.json` 生成）
- `frontend/vite.config.ts`（`/api` 代理默认指向远端 demo 后端，可由 `VITE_DEV_PROXY_TARGET` 覆盖）
- `frontend/.env.example`
- `frontend/src/lib/env.ts`（新增；集中读取 API base / Mock 开关）
- `frontend/src/lib/types.gen.ts`（新增；由 `pnpm gen:types` 从线上 OpenAPI 生成）
- `frontend/src/lib/types.ts`（改为基于生成类型的友好别名，并对 backend 默认值字段做收窄）
- `frontend/src/lib/adapters/index.ts`、`auth.ts`、`conversations.ts`、`agents.ts`（新增 Adapter 层）
- `frontend/src/hooks/useConversations.ts`（按 `env.useMockApi` 在 Mock store 与 TanStack Query 之间切换）
- `frontend/src/hooks/useAgents.ts`（同上）

### 更新内容
- 后端地址：`http://111.229.151.159:8000`。`/health` 200，`/openapi.json` 可用。
- 类型源切到线上后端 OpenAPI；保留 `types.ts` 作为友好别名层，单点向 components.schemas 引用。
- 新增 `lib/env.ts`：`apiBaseUrl` / `useMockApi` / `useMockSse`，组件不再直接读 `import.meta.env`。
- 新增 `lib/adapters/`：`auth.login/register/getCurrentUser`、`conversations.listConversations/createConversation`、`agents.listAgents`，统一 axios 调用形态。
- `useConversations` / `useAgents` 在 `VITE_USE_MOCK_API=false` 时通过 TanStack Query 真实拉远端列表；默认仍为 Mock，保证比赛 Demo 不依赖后端。
- Vite 开发服务器 `/api` 代理默认指向远端，避免本地 CORS 问题。

### API / 契约影响
- 不修改 `shared/openapi.yaml`；以远端实时 OpenAPI 为类型源。
- `pnpm gen:types` 现在从 `http://111.229.151.159:8000/openapi.json` 拉取。
- **后端 schema 待补 `required` 的字段**（已在 `types.ts` 用 `Override` 临时收窄，需通知 B1 修复 OpenAPI）：
  - `ConversationOut.{agent_ids, is_pinned, is_archived}`
  - `MessageOut.{content, status, is_pinned}`
  - `AgentOut.{capabilities, config, is_builtin, avatar_url}`
  - 这些字段后端模型有默认值，但 OpenAPI 没声明为 required，导致前端处处 undefined 检查。

### 验证方式
- `./node_modules/.bin/tsc -b` ✅
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0` ✅
- `npx vitest --run` ✅ 19/19
- 真实后端冒烟：
  - `GET /health` → 200 `{"status":"ok"}` ✅
  - `GET /api/v1/conversations` / `GET /api/v1/agents`（无 token） → 401 ✅（鉴权链路工作）
  - `POST /api/v1/auth/login`（错误账号） → 401 JSON ✅
  - `POST /api/v1/auth/register`（合法 payload） → **500 Internal Server Error** ❌（后端 bug，**阻塞前端实测带 token 的列表请求**）

### 后续事项 / 阻塞
- **🔴 阻塞 B1**：`POST /api/v1/auth/register` 对合法 payload 返回 500（非 422）。需要 B1 检查 [backend/app/api/v1/auth.py](backend/app/api/v1/auth.py) register 路由的 commit/flush 逻辑或返回 Pydantic 校验，并把 server 日志贴出来定位。422 校验路径工作正常，所以问题在路由本身。
- 待 register 修复后：前端把 `VITE_USE_MOCK_API=false` 启动一次，确认登录、`/auth/me`、`/conversations`、`/agents` 通跑。
- 通知 B1 把上面列出的 `required` 字段补到 OpenAPI，前端去掉 `types.ts` 里的 `Override` 收窄。
- 下一刀：`useMessages`（消息列表 + 游标分页）+ `useSendMessage`（POST messages 返回 `{user_message, agent_message}`）+ SSE 联调。

---

## 2026-05-25 — 接入远端后端：第二刀 消息列表 + 发送消息 + SSE 切换

### 改动范围
- `frontend/src/lib/adapters/messages.ts`（新增；listMessages / sendMessage / regenerateMessage）
- `frontend/src/lib/adapters/index.ts`（导出 messagesAdapter）
- `frontend/src/lib/sse.ts`（Mock 分支改读 `env.useMockSse`，去除内联 env 读取）
- `frontend/src/stores/chatStore.ts`（新增 `addConversation` / `hydrateConversations` / `hydrateMessages` / `appendRemoteExchange`）
- `frontend/src/hooks/useConversations.ts`（API 模式 useQuery → 写入 chatStore）
- `frontend/src/hooks/useMessages.ts`（按 conversationId useQuery → hydrate chatStore；ASC 排序）
- `frontend/src/hooks/useCreateConversation.ts`（API 模式 useMutation → POST /conversations → addConversation）
- `frontend/src/hooks/useSendMessage.ts`（API 模式 POST /messages → appendRemoteExchange → 返回 agentMessageId 给 useStream）

### 更新内容
- **数据源策略**：`chatStore` 仍是渲染唯一真相。API 模式下 query/mutation 把远端结果 hydrate 进 chatStore，下游 streaming/applyStreamEvent 完全不变。Mock 模式行为完全保留。
- **消息列表**：`useMessages` 在 API 模式按 `conversationId` 触发 useQuery，调 `GET /api/v1/conversations/{id}/messages?limit=50&direction=before`，按 `created_at` ASC 排好序后写入 chatStore。`staleTime: 30s` 防止流式过程中被刷新覆盖。
- **发送消息**：`useSendMessage` 在 API 模式解析 `@agent-id`（群聊）→ POST `/messages` body `{content:[{type:'text',text}], target_agent_id?}` → 把 `{user_message, agent_message}` 整体 append 到 chatStore → 返回 `agent_message.id` 用于 SSE 订阅。
- **新建会话**：`useCreateConversation` 在 API 模式调 POST `/conversations`，成功后 prepend 到 chatStore 并设为选中。
- **SSE**：`subscribeMessageStream` 改为读 `env.useMockSse`；保留 `messageId.startsWith('msg-')` 启发式，让 Mock 内部生成的消息 ID 始终走 Mock SSE（真后端返回 UUID 不会触发）。`fetchEventSource` 已经在用 `Authorization: Bearer <token>`，无需改动。

### API / 契约影响
- 不修改 `shared/openapi.yaml`。
- 已使用的真实端点：
  - `GET  /api/v1/conversations`（list）
  - `POST /api/v1/conversations`（create）
  - `GET  /api/v1/conversations/{conv_id}/messages`（list，游标分页）
  - `POST /api/v1/conversations/{conv_id}/messages`（send，返回 `{user_message, agent_message}`）
  - `GET  /api/v1/agents`（list）
  - `GET  /api/v1/messages/{msg_id}/stream`（SSE）
- 暂未接入：`PATCH/DELETE /conversations`、`PATCH/DELETE /messages`、`POST /messages/{id}/regenerate`、`PATCH/DELETE /agents`、`POST /agents`、`GET /auth/me`（保留给后续 slice）。

### 验证方式
- `./node_modules/.bin/tsc -b` ✅
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0` ✅
- `npx vitest --run` ✅ 19/19
- `./node_modules/.bin/vite build` ✅
- 真实后端冒烟仍被 register 500 阻塞，所有认证后的端点未跑通；代码路径在 Mock 模式下行为不变（已通过测试覆盖）。

### 后续事项 / 阻塞
- **🔴 仍阻塞**：register 500 → 无法登录 → 无法实测 `/conversations` `/messages` `/stream`。建议 B1 同步给临时账号或修复 register。
- 第三刀候选：`POST /agents`（自建 Agent）、`PATCH /conversations`（置顶/归档/改名）、`POST /messages/{id}/regenerate`（重生成）、`GET /auth/me` 接入 AuthGuard。
- 现在 Mock 与 API 通过 chatStore 共用一套渲染路径，hydrate 时机不当可能覆盖流式中状态。`useMessages` 的 30s `staleTime` + 不主动 invalidate 是 workaround；待 SSE 联调跑通后，需要细化"流式完成事件 → 主动 invalidate `['messages', convId]`"的策略。

---

## 2026-05-25 — 真后端全链路冒烟（register 修复后）

### 触发
后端 B1 修复 `POST /auth/register` 500 之后，前端 `VITE_USE_MOCK_API=false` 全链路冒烟。

### 范围
- 真实后端 `http://111.229.151.159:8000` 上的 9 个端点
- 前端 dev server 在 API 模式下启动验证
- 重生成 `src/lib/types.gen.ts`（无 schema 变化）

### 通过的端点
| 端点 | 结果 |
|---|---|
| `POST /auth/register` | 201 + JWT |
| `GET  /auth/me` | 200 |
| `GET  /agents` | 5 个 seed（orchestrator / claude-code / codex-helper / writer / web-designer） |
| `GET  /conversations` | 空 items 数组 + 分页字段 |
| `POST /conversations` | 返回完整 ConversationOut |
| `POST /conversations/{id}/messages` | 返回 `{user_message:done, agent_message:pending}` |
| `GET  /conversations/{id}/messages` | 返回两条消息（user done + agent error） |
| `GET  /messages/{id}/stream` SSE | handshake 成功，event 格式与前端类型兼容 |

### 发现的问题
1. **B2 Anthropic 上游 `Connection error.`** — SSE 通道工作，但 agent 调用 Anthropic 时连接失败，消息直接走到 `status=error`。需要 B2 检查 API Key / 出网 / 代理。前端已能正确渲染该错误状态并支持 retry。
2. **`POST /agents` provider=custom 必失败** — 后端要求 `upstream_provider`，但该字段不在 OpenAPI 的 `CreateAgentRequest` 中，且 Pydantic 会剥掉额外字段。已把 `AgentCreateDialog` 默认 provider 改为 `claude`、默认 model 改为 `claude-sonnet-4-6` 避开。`provider:claude` / `provider:openai` 可正常创建。
3. **`last_message_preview` 不会被后端自动填** — 发消息后 `GET /conversations` 该字段仍是 `null`。前端 `chatStore.appendRemoteExchange` 用本地文本兜底，UI 不受影响。

### 改动
- `frontend/.env.local`（本地）：`VITE_USE_MOCK_API=false` / `VITE_USE_MOCK_SSE=false`
- `frontend/src/components/agents/AgentCreateDialog.tsx`：默认 provider `custom → claude`，默认 model `agenthub-demo-v1 → claude-sonnet-4-6`，加注释说明真后端约束
- `frontend/src/lib/types.gen.ts`：重新拉取（无 schema 变化）

### 验证方式
- 八个 REST 端点全部经过 `curl` 真实调用 ✅
- SSE handshake `curl -N` 30s 超时内拿到 `start` + `error` 事件 ✅
- `./node_modules/.bin/tsc -b` ✅
- `npx vitest --run` 19/19 ✅
- `./node_modules/.bin/vite --port 5179` 86ms 起来；`GET /` 200；`GET /api/v1/agents`（无 token） → 401 经代理透传 ✅

### 后续事项 / 后端 follow-up
- 🟡 B2：修 Anthropic 上游连接，然后用 `claude-code` agent 重发 hello 验证 delta 流。
- 🟡 B1：把 `upstream_provider` 加进 `CreateAgentRequest` 或干脆让 backend 接受 `provider:custom` + 默认上游。
- 🟡 B1：让 `POST /messages` 之后给会话回填 `last_message_preview`。
- 🟡 B1：补 OpenAPI 中的 `required` 字段列表（前端已用 `Override` 临时收窄）。

---

## 2026-05-25 — 接入远端后端：第三刀 Agent CRUD + auth/me

### 改动范围
- `frontend/src/lib/adapters/agents.ts`（新增 `createAgent` / `updateAgent` / `deleteAgent`）
- `frontend/src/stores/agentStore.ts`（新增 `addAgent` / `hydrateAgents`，给 `authStore` 加 `setUser`）
- `frontend/src/stores/authStore.ts`（新增 `setUser`）
- `frontend/src/hooks/useAgents.ts`（API 模式 useQuery → hydrate agentStore）
- `frontend/src/hooks/useCreateAgent.ts`（新增；Mock/API 分支）
- `frontend/src/pages/AgentsPage.tsx`（接 `useCreateAgent` 替代直接调 `agentStore.createAgent`）
- `frontend/src/components/layout/AuthGuard.tsx`（API 模式 mount 时 `GET /auth/me` 校验 token + 刷新用户）

### 更新内容
- **Agent CRUD adapter**：完整覆盖 `POST/PATCH/DELETE /api/v1/agents/...`。本刀只接 create 到 UI，update/delete 等到有界面再接。
- **`useCreateAgent` hook**：Mock 走 `agentStore.createAgent`（保留 slugify 逻辑）；API 走 `POST /agents` body `{name, provider, avatar_url:"", capabilities, system_prompt, config:{model,temperature}}`，成功后 `agentStore.addAgent` + `invalidate ['agents']`。
- **`useAgents` 写回 agentStore**：和 conversations/messages 一致，API 模式 query 结果 hydrate 进 agentStore，UI 唯一从 store 读。
- **AuthGuard 增强**：API 模式下 `useQuery(['auth','me'])` 跑一次 `GET /auth/me`；token 失效自动落到 axios 401 拦截器走 logout + redirect；token 有效则刷新 `authStore.user`。Mock 模式跳过该查询（不会用 mock-demo-token 戳真后端）。

### API / 契约影响
- 不修改 `shared/openapi.yaml`。
- 新接入端点：`POST /api/v1/agents`、`GET /api/v1/auth/me`。
- Adapter 内已实现但暂未接 UI：`PATCH /api/v1/agents/{id}`、`DELETE /api/v1/agents/{id}`。
- 类型小坑：生成出的 `CreateAgentRequest.avatar_url` 是必填（OpenAPI 给了默认值但 openapi-typescript v7 视作 required），前端 hook 显式传 `avatar_url: ''`。本质上和后端默认一致，但属于"OpenAPI default 字段"的常见摩擦点，可以让 B1 把这些字段放进 `required` 或显式标注 nullable。

### 验证方式
- `./node_modules/.bin/tsc -b` ✅
- `./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0` ✅
- `npx vitest --run` ✅ 19/19
- `./node_modules/.bin/vite build` ✅
- 真实后端冒烟仍被 register 500 阻塞；Mock 模式 `创建 Agent` 行为已通过 `AgentsPage` 验证未回归。

### 后续事项 / 阻塞
- **🔴 register 500 仍是唯一阻塞**。建议 B1 用 docker compose logs / uvicorn stdout 抓栈，最可能的几个点：`AsyncSession` 没 commit / `expire_on_commit=True` 导致 `UserOut.model_validate` 时 detached、或 `created_at` default 在 async 上下文里没填好。
- 接下来可做（不依赖后端）：
  - 给会话条目加 Pin/Archive/Rename/Delete 菜单 + 调 `PATCH/DELETE /conversations/{id}`
  - Agent 详情面板加编辑/删除按钮 + 调 `PATCH/DELETE /agents/{id}`
  - 错误消息重试按钮 → `POST /messages/{id}/regenerate`
- 接下来必须等后端：完整 E2E 跑通 Auth → 列表 → 发消息 → SSE 流。
