# AgentHub 前端开发计划

> 本文档用于指导 AgentHub 前端开发。
> 方向：AgentHub 自有品牌视觉 + Discord 式信息架构 + 桌面 Demo 优先。
> 文档版本：v0.1
> 最后更新：2026-05-25

---

## 执行状态速览（2026-05-25）

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 前端基建整理 | ✅ |
| 1 | Discord 式主框架 | ✅ |
| 2 | Mock 聊天体验 | ✅ |
| 3 | 真实 API 接入 | ✅（Auth / 会话 / 消息 / Agent CRUD 已接，见 [changelog](changelog.md) 第一/二/三刀） |
| 4 | SSE 流式接入 | 🟡 客户端就绪，等后端 register 修复后联调 |
| 5 | 富媒体消息块 | ✅ |
| 6 | Agent 管理页 | ✅ |
| 7 | Demo 打磨 | 🟡 基础态完成；二轮打磨见 [demo-polish-v2-plan.md](demo-polish-v2-plan.md) 未开始 |

🟢 全部 ✅／🟡 进行中／🔴 未开始

---

## 1. 开发目标

第一阶段目标是完成一个可演示的桌面版 AgentHub 前端：

- UI 与交互可以先使用 Mock 数据。
- 架构必须能平滑替换为真实后端 API。
- 信息架构参考 Discord：模块栏、会话列表、主聊天区、右侧 Agent 信息栏。
- 视觉不照搬 Discord，保留 AgentHub 的专业、多 Agent 协作产品感。
- 明暗主题都预留，第一阶段优先精修深色主题。
- 暂不优先移动端，先保证桌面 Demo 稳定可用。

---

## 2. 产品与设计约束

### 2.1 信息架构

桌面端采用四栏结构：

```text
┌────────┬────────────────────┬──────────────────────────────┬──────────────────┐
│ 模块栏 │ 会话 / 频道列表      │ 聊天主区                       │ Agent / 上下文栏   │
│ 60px   │ 280px              │ flex-1                       │ 300px            │
└────────┴────────────────────┴──────────────────────────────┴──────────────────┘
```

### 2.2 核心页面

- `/login`：登录 / 注册页
- `/chat`：聊天主页
- `/chat/:conversationId`：具体会话
- `/agents`：Agent 管理页

### 2.3 视觉方向

- 主体体验参考 Discord 的信息密度与导航效率。
- 品牌视觉参考 `docs/product-design.md` 中的 AgentHub 设计规范。
- 深色主题优先，浅色主题保留变量和基础可用性。
- 使用 Tailwind CSS + shadcn/ui + lucide-react。
- 图标按钮优先使用 Lucide 图标。

### 2.4 开发边界

前端 Owner 为 F，主要改动范围：

```text
frontend/**
```

涉及以下文件时需要同步团队：

```text
shared/openapi.yaml
backend/app/schemas/**
docs/**
```

---

## 3. 技术选型

遵循项目既有技术栈：

| 能力 | 方案 |
|------|------|
| 框架 | React 18 + Vite + TypeScript |
| 样式 | Tailwind CSS + shadcn/ui |
| 图标 | lucide-react |
| 路由 | React Router v6 |
| 服务端数据 | TanStack Query |
| UI 状态 | Zustand |
| SSE | `@microsoft/fetch-event-source` |
| Markdown | react-markdown |
| 代码高亮 | shiki |
| Diff | react-diff-viewer-continued |
| 测试 | vitest + Testing Library |

---

## 4. 推荐目录结构

```text
frontend/src/
├── lib/
│   ├── api.ts
│   ├── sse.ts
│   ├── types.ts
│   ├── mockData.ts
│   └── utils.ts
├── stores/
│   ├── authStore.ts
│   ├── uiStore.ts
│   └── chatStore.ts
├── hooks/
│   ├── useAuth.ts
│   ├── useAgents.ts
│   ├── useConversations.ts
│   ├── useMessages.ts
│   ├── useSendMessage.ts
│   └── useStream.ts
├── pages/
│   ├── LoginPage.tsx
│   ├── ChatPage.tsx
│   └── AgentsPage.tsx
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx
│   │   ├── ModuleRail.tsx
│   │   └── RightPanel.tsx
│   ├── conversation/
│   │   ├── ConversationSidebar.tsx
│   │   ├── ConversationItem.tsx
│   │   └── NewConversationDialog.tsx
│   ├── chat/
│   │   ├── ChatHeader.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── MessageInput.tsx
│   │   └── AgentMentionPicker.tsx
│   ├── blocks/
│   │   ├── ContentRenderer.tsx
│   │   ├── TextBlock.tsx
│   │   ├── CodeBlock.tsx
│   │   ├── DiffBlock.tsx
│   │   ├── WebPreviewBlock.tsx
│   │   ├── FileBlock.tsx
│   │   └── TaskCardBlock.tsx
│   ├── agents/
│   │   ├── AgentCard.tsx
│   │   ├── AgentAvatar.tsx
│   │   ├── AgentStatusList.tsx
│   │   └── RightAgentPanel.tsx
│   └── ui/
└── styles/
    └── globals.css
```

---

## 5. 分阶段开发计划

### ✅ 阶段 0：前端基建整理

目标：让前端项目具备稳定开发基础。

任务：

- 确认依赖完整：React Router、Tailwind、shadcn/ui、lucide-react、Zustand、TanStack Query、fetch-event-source。
- 整理主题变量：深色主题精修，浅色主题保留基础 token。
- 建立布局尺寸变量：模块栏、会话栏、聊天区、右侧栏。
- 确认 `src/lib/types.ts` 来自 OpenAPI，不手写重复类型。
- 建立 Mock 数据：Agent、会话、消息、任务卡片、流式回复。

验收标准：

- `pnpm dev` 能启动。
- 无后端时也能看到完整桌面 UI。
- 深色主题视觉方向稳定。

### ✅ 阶段 1：Discord 式主框架

目标：完成 AgentHub 主界面骨架。

任务：

- 实现 `AppLayout`。
- 实现左侧 `ModuleRail`。
- 实现 `ConversationSidebar`。
- 实现主聊天区 `ChatPage`。
- 实现右侧 `RightAgentPanel`。
- 完成 Chat / Agents 模块切换。

模块栏应包含：

- Chat
- Agents
- Archive
- Settings
- User menu

会话栏应包含：

- 搜索框
- 新建会话按钮
- 置顶会话
- 最近会话
- 单聊 / 群聊标识
- 当前选中态

右侧栏应包含：

- 当前会话 Agent 列表
- Agent 能力标签
- 当前上下文状态
- Pin 消息入口
- 群聊时的 Orchestrator 状态

验收标准：

- 点击 Mock 会话能刷新聊天区与右侧栏。
- 桌面四栏布局稳定，无明显溢出和错位。
- UI 信息架构像 Discord，但品牌视觉属于 AgentHub。

### ✅ 阶段 2：Mock 聊天体验

目标：先做出可演示的产品体验。

任务：

- 实现 `MessageList`。
- 实现 `MessageBubble`。
- 实现 `MessageInput`。
- 实现 `AgentMentionPicker`。
- 发送消息后本地追加用户消息。
- 使用 Mock Stream 模拟 Agent 逐字回复。
- 群聊中支持 `@Orchestrator` 的视觉表达。
- 支持 `agent_switch` 的 Mock 展示。

验收标准：

- 可以演示“选择会话 → 输入消息 → Agent 流式回复”。
- 群聊中不同 Agent 身份清晰。
- 右侧栏跟随当前会话更新。

### ✅ 阶段 3：真实 API 接入

目标：逐步将 Mock 数据替换为后端 API。

任务：

- 完善 `src/lib/api.ts`，统一请求封装。
- Token 自动注入请求 Header。
- 错误响应统一处理。
- 接入登录 / 注册 / 当前用户。
- 接入会话列表。
- 接入消息列表。
- 接入 Agent 列表。
- 接入新建会话与发送消息。

Hook 规划：

```text
hooks/useAuth.ts
hooks/useConversations.ts
hooks/useMessages.ts
hooks/useAgents.ts
hooks/useSendMessage.ts
```

TanStack Query 使用规划：

| 数据 | 类型 |
|------|------|
| 当前用户 | query |
| 会话列表 | query |
| 消息列表 | query |
| Agent 列表 | query |
| 登录 / 注册 | mutation |
| 新建会话 | mutation |
| 发送消息 | mutation |
| Pin / 删除 / 重生成 | mutation |

验收标准：

- 登录后能拿到真实 token。
- 会话列表来自真实 API。
- Agent 列表来自真实 API。
- 发送消息后得到 `user_message` 和 `agent_message`。

### 🟡 阶段 4：SSE 流式接入（客户端就绪，等后端可登录后联调）

目标：跑通 AgentHub 的核心体验。

任务：

- 实现 `src/lib/sse.ts`。
- 实现 `hooks/useStream.ts`。
- 使用 `@microsoft/fetch-event-source`。
- JWT 通过 Authorization Header 传入。
- 处理后端定义的 SSE 事件。

事件处理：

| Event | 前端行为 |
|------|----------|
| `start` | 标记消息进入 streaming |
| `block_start` | 创建新的 ContentBlock |
| `delta` | 增量更新指定 block |
| `block_end` | 标记当前 block 完成 |
| `done` | 标记消息完成并关闭流 |
| `error` | 展示错误卡片 |
| `agent_switch` | 展示 Agent 切换分隔 |
| `heartbeat` | 保持连接，无需 UI 更新 |

验收标准：

- 发送消息后自动订阅 `agent_message.id`。
- 文本可以逐字出现。
- 代码块可以流式出现。
- 错误时 UI 不崩溃，并能显示重试入口。

### ✅ 阶段 5：富媒体消息块

目标：完成 Demo 中最有产品感的内容展示。

组件优先级：

1. `TextBlock`
2. `CodeBlock`
3. `TaskCardBlock`
4. `DiffBlock`
5. `WebPreviewBlock`
6. `FileBlock`

`ContentRenderer` 必须使用 block type 分发：

```tsx
const BLOCK_COMPONENTS = {
  text: TextBlock,
  code: CodeBlock,
  diff: DiffBlock,
  web_preview: WebPreviewBlock,
  file: FileBlock,
} as const;
```

验收标准：

- Markdown 文本可读。
- CodeBlock 有语言标签、复制按钮、代码高亮。
- TaskCardBlock 能展示 Orchestrator 任务状态。
- DiffBlock 至少能用 unified 视图展示。
- 未知 block 类型有降级 UI。

### ✅ 阶段 6：Agent 管理页

目标：做出内置 Agent 与自建 Agent 的管理入口。

任务：

- 实现 `AgentsPage`。
- 实现内置 Agent 列表。
- 实现我的 Agent 列表。
- 实现 Agent 能力标签。
- 实现创建 Agent 表单入口。
- 第一版允许创建流程先使用 Mock，后续接真实 API。

验收标准：

- 可以从模块栏切到 Agent 页面。
- Agent 卡片视觉统一。
- 创建表单字段结构完整。

### 🟡 阶段 7：Demo 打磨（基础态已做；二轮打磨见 [demo-polish-v2-plan.md](demo-polish-v2-plan.md)）

目标：保证比赛演示稳定、顺滑、有产品感。

任务：

- 深色主题精修。
- Loading skeleton。
- 空状态。
- 错误状态。
- 流式光标。
- Agent 切换动画。
- 新消息自动滚动。
- 会话选中态与 hover 态。
- 右侧栏信息密度优化。

验收 Demo 路径：

1. 登录。
2. 进入聊天页。
3. 新建单聊会话。
4. 发送“写一个 React Todo 组件”。
5. 看到流式回复和代码块。
6. 切到群聊。
7. `@Orchestrator` 发送复杂任务。
8. 看到任务拆解、Agent 切换、产物输出。

---

## 6. Mock 与真实 API 并行策略

前端第一阶段可以先用 Mock 数据推进 UI，但必须保留真实 API 的切换路径。

建议：

- Mock 数据集中放在 `src/lib/mockData.ts`。
- 页面组件不直接依赖 Mock 数据。
- 通过 Hook 层切换 Mock / API 数据源。
- Hook 返回结构尽量与 OpenAPI 类型一致。

示例：

```text
Page / Component
  → hooks/useConversations
    → mockData 或 api client
```

这样后端接口稳定后，只需要替换 Hook 内部数据来源。

---

## 7. 状态管理规划

| 状态 | 工具 | 说明 |
|------|------|------|
| 当前用户 / token | Zustand + localStorage | 需要持久化 |
| 当前选中会话 | Zustand | UI 状态 |
| 侧边栏展开 / 右侧栏开关 | Zustand | UI 状态 |
| 会话列表 | TanStack Query | 服务端状态 |
| 消息列表 | TanStack Query | 服务端状态 |
| Agent 列表 | TanStack Query | 服务端状态 |
| 流式消息临时内容 | Hook 局部状态或 chatStore | 高频更新 |

原则：

- 服务端数据优先放 TanStack Query。
- 纯 UI 状态放 Zustand。
- 流式增量更新要避免整页重渲染。

---

## 8. API 与契约要求

前端必须遵守：

- API 类型从 `frontend/src/lib/types.ts` 导入。
- `src/lib/types.ts` 由 `shared/openapi.yaml` 生成。
- API 变更必须先改 `shared/openapi.yaml`。
- 不在组件中散落裸 API 路径。
- 不使用 `any` 逃避类型检查。

生成类型命令：

```bash
cd frontend
pnpm gen:types
```

---

## 9. 测试与验证

第一阶段建议覆盖：

- `useStream` 的事件处理逻辑。
- `ContentRenderer` 的 block 分发逻辑。
- `MessageInput` 的发送行为。
- `ConversationItem` 的选中态。
- `CodeBlock` 的复制行为。

验证命令：

```bash
cd frontend
pnpm tsc --noEmit
pnpm lint
pnpm test
```

---

## 10. PR 拆分建议

建议拆成小 PR，降低冲突和 review 成本：

1. `feat/F-layout-shell`：四栏布局与主题变量。
2. `feat/F-mock-chat`：Mock 会话、消息、输入与流式回复。
3. `feat/F-agent-panel`：右侧 Agent 信息栏。
4. `feat/F-api-hooks`：API client 与基础 query hooks。
5. `feat/F-sse-stream`：真实 SSE 接入。
6. `feat/F-content-blocks`：富媒体消息块。
7. `feat/F-agents-page`：Agent 管理页。
8. `polish/F-demo-ui`：Demo 打磨。

---

## 11. 第一阶段完成定义

第一阶段前端完成后，应满足：

- 桌面端 UI 可完整演示。
- Mock 模式下无需后端即可展示主要体验。
- 真实 API 模式下能完成登录、拉会话、拉 Agent、发消息。
- SSE 模式下能展示流式回复。
- CodeBlock 与 TaskCardBlock 可用于 Demo。
- 深色主题质量达到演示标准。
- 代码结构能支撑后续移动端、PWA、Tauri 包装。

