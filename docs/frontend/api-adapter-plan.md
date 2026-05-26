# AgentHub 前端 API Adapter 层准备计划

> 本文档用于指导前端在后端仍同步开发时，提前整理真实 API 接入前的 Adapter 层。
> 目标是在不破坏当前 Mock Demo 的前提下，为真实 REST API、SSE、Artifact 预览和 Agent CRUD 接入建立清晰边界。

---

## 执行状态速览（2026-05-25）

| Step | 内容 | 状态 |
|---|---|---|
| 1 | 新增 `lib/env.ts` 集中读环境变量 | ✅ |
| 2 | 拆出 Mock SSE | 🟡 `sse.ts` 改用 `env.useMockSse` 分支，但 `mockSse.ts` 还没拆成独立文件 |
| 3 | 新增 Adapter 类型与空实现 | ✅ `auth / conversations / agents / messages` 全部完成 |
| 4 | 逐步迁移 hooks | ✅ `useAgents / useConversations / useMessages / useCreateConversation / useCreateAgent / useSendMessage` 全部走双模式 |
| 5 | 真实 API 联调 | 🔴 阻塞：后端 `/auth/register` 500，无法登录跑全链路冒烟 |

🟢 全部 ✅／🟡 进行中／🔴 未开始或阻塞

---

## 1. 背景

当前前端已经完成桌面 Mock Demo：

- 四栏聊天主界面
- Mock 会话 / 消息 / Agent 数据
- Mock API hooks
- Mock SSE 流式事件
- 多 Agent `agent_switch`
- 富媒体消息块
- Agent 管理页
- 第一批前端测试

后端仍在同步开发，因此下一步前端不应直接大规模替换 Mock，而应先准备 Adapter 层：

```text
Page / Component
  -> hooks
    -> adapter
      -> mock data 或 real api
```

这样后端接口稳定后，只需要替换 Adapter 内部实现，不需要重写页面组件。

---

## 2. 目标

### 2.1 本阶段目标

- 明确 Mock / API 双模式切换策略。
- 规划 `api.ts` 的 endpoint 方法，而不是在 hooks 中散落裸路径。
- 规划每个 hook 的 Adapter 边界。
- 列出真实 API 接入需要后端确认的字段和事件。
- 明确哪些前端 Demo 扩展字段需要进入 OpenAPI 契约。
- 保持当前 Mock Demo 可运行。

### 2.2 非目标

本阶段暂不做：

- 不直接修改 `shared/openapi.yaml`。
- 不移除 Mock 数据。
- 不强依赖真实后端。
- 不改后端代码。
- 不引入 MSW，除非后续测试需要。

---

## 3. 现状盘点

### 3.1 已有 API 基础

文件：

```text
frontend/src/lib/api.ts
```

当前能力：

- Axios instance
- `VITE_API_BASE_URL`
- JWT 自动注入 `Authorization: Bearer <token>`
- 401 自动 logout 并跳转 `/login`
- `extractApiError`

需要补充：

- endpoint 方法封装
- request / response 类型映射
- Mock / real API adapter 统一返回形态

### 3.2 已有 SSE 基础

文件：

```text
frontend/src/lib/sse.ts
frontend/src/hooks/useStream.ts
```

当前能力：

- `@microsoft/fetch-event-source`
- `Authorization` Header
- `VITE_USE_MOCK_API !== 'false'` 时使用 Mock SSE
- 支持 `start`、`block_start`、`delta`、`block_end`、`done`、`error`、`agent_switch`

需要补充：

- 将 Mock SSE 事件生成逻辑从 `lib/sse.ts` 中拆出。
- 明确真实 SSE URL 与事件 payload。
- 对 `heartbeat` 做显式 no-op。
- 对重连 / abort / fatal error 建立统一策略。

### 3.3 已有 Hook

当前 hooks：

```text
frontend/src/hooks/useConversations.ts
frontend/src/hooks/useMessages.ts
frontend/src/hooks/useAgents.ts
frontend/src/hooks/useCreateConversation.ts
frontend/src/hooks/useSendMessage.ts
frontend/src/hooks/useStream.ts
```

当前问题：

- hooks 直接读 Zustand mock store。
- hooks 尚未接 TanStack Query。
- Mock 创建和真实 mutation 的边界还不够清楚。
- `useAgents` 已经从 `agentStore` 读取，未来要切到 query + mutation。

---

## 4. 推荐目录结构

建议新增 Adapter 层目录：

```text
frontend/src/lib/
├── api.ts
├── apiClient.ts              # 可选：底层 axios/fetch 封装
├── apiAdapters/
│   ├── conversations.ts
│   ├── messages.ts
│   ├── agents.ts
│   ├── auth.ts
│   └── artifacts.ts
├── mockAdapters/
│   ├── conversations.ts
│   ├── messages.ts
│   ├── agents.ts
│   ├── auth.ts
│   └── artifacts.ts
├── sse.ts
├── mockSse.ts
└── env.ts
```

更轻量的第一步也可以先使用：

```text
frontend/src/lib/adapters/
├── conversations.ts
├── messages.ts
├── agents.ts
├── auth.ts
├── artifacts.ts
└── index.ts
```

每个 adapter 文件内部根据环境变量选择 Mock 或真实 API。

---

## 5. 环境变量策略

建议统一封装：

```text
frontend/src/lib/env.ts
```

建议变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `''` | 后端 API base URL |
| `VITE_USE_MOCK_API` | `'true'` | 是否使用 Mock REST API |
| `VITE_USE_MOCK_SSE` | 默认跟随 `VITE_USE_MOCK_API` | 是否使用 Mock SSE |
| `VITE_ENABLE_DEMO_DATA` | `'true'` | 是否显示 Demo seed 数据 |

建议实现：

```ts
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || '',
  useMockApi: import.meta.env.VITE_USE_MOCK_API !== 'false',
  useMockSse:
    import.meta.env.VITE_USE_MOCK_SSE === undefined
      ? import.meta.env.VITE_USE_MOCK_API !== 'false'
      : import.meta.env.VITE_USE_MOCK_SSE !== 'false',
  enableDemoData: import.meta.env.VITE_ENABLE_DEMO_DATA !== 'false',
};
```

这样可以支持：

```bash
# 纯 Mock Demo
VITE_USE_MOCK_API=true npm run dev

# REST 接真实 API，但 SSE 仍使用 Mock
VITE_USE_MOCK_API=false VITE_USE_MOCK_SSE=true npm run dev

# REST + SSE 全部接真实后端
VITE_USE_MOCK_API=false VITE_USE_MOCK_SSE=false npm run dev
```

---

## 6. Adapter 接口设计

### 6.1 Auth Adapter

建议文件：

```text
frontend/src/lib/adapters/auth.ts
```

建议接口：

```ts
export interface LoginInput {
  username: string;
  password: string;
}

export interface RegisterInput {
  username: string;
  password: string;
}

export interface AuthAdapter {
  login(input: LoginInput): Promise<AuthResponse>;
  register(input: RegisterInput): Promise<AuthResponse>;
  getCurrentUser(): Promise<User>;
}
```

真实 API 预期：

```text
POST /api/v1/auth/login
POST /api/v1/auth/register
GET  /api/v1/auth/me
```

前端当前状态：

- `LoginPage` 直接调用 `api.post(...)`。
- 后续应改为 `authAdapter.login/register`。

---

### 6.2 Conversations Adapter

建议文件：

```text
frontend/src/lib/adapters/conversations.ts
```

建议接口：

```ts
export interface CreateConversationInput {
  title: string;
  mode: 'single' | 'group';
  agentIds: string[];
}

export interface ConversationsAdapter {
  listConversations(): Promise<Conversation[]>;
  getConversation(conversationId: string): Promise<Conversation>;
  createConversation(input: CreateConversationInput): Promise<Conversation>;
  archiveConversation(conversationId: string): Promise<void>;
  pinConversation(conversationId: string, pinned: boolean): Promise<Conversation>;
}
```

真实 API 预期：

```text
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversation_id}
POST   /api/v1/conversations
PATCH  /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
```

前端当前状态：

- `useConversations` 从 `chatStore.conversations` 读取。
- `useCreateConversation` 调用 `chatStore.createConversation`。

迁移策略：

- Mock 模式继续读 `chatStore`。
- API 模式使用 TanStack Query：

```text
useConversations
  -> queryKey: ['conversations']
  -> conversationsAdapter.listConversations()

useCreateConversation
  -> mutation
  -> conversationsAdapter.createConversation(input)
  -> invalidate ['conversations']
```

---

### 6.3 Messages Adapter

建议文件：

```text
frontend/src/lib/adapters/messages.ts
```

建议接口：

```ts
export interface SendMessageInput {
  conversationId: string;
  text: string;
  targetAgentId?: string | null;
}

export interface SendMessageResult {
  userMessage: Message;
  agentMessage: Message;
}

export interface MessagesAdapter {
  listMessages(conversationId: string): Promise<Message[]>;
  sendMessage(input: SendMessageInput): Promise<SendMessageResult>;
  retryMessage(messageId: string): Promise<Message>;
  pinMessage(messageId: string, pinned: boolean): Promise<Message>;
}
```

真实 API 预期：

```text
GET   /api/v1/conversations/{conversation_id}/messages
POST  /api/v1/conversations/{conversation_id}/messages
POST  /api/v1/messages/{message_id}/retry
PATCH /api/v1/messages/{message_id}
```

前端当前状态：

- `useMessages` 从 `chatStore.messagesByConversation` 读取。
- `useSendMessage` 调用 `chatStore.createPendingExchange`。
- target Agent 目前由前端从 `@agent-id` 解析。

需要后端确认：

- 发送消息时是否传 `target_agent_id`。
- 后端是否同时返回 `user_message` 与 `agent_message`。
- `agent_message.id` 是否用于订阅 SSE。
- retry 是复用旧 message id 还是返回新 message。

---

### 6.4 Agents Adapter

建议文件：

```text
frontend/src/lib/adapters/agents.ts
```

建议接口：

```ts
export interface CreateAgentInput {
  name: string;
  provider: 'claude_code' | 'codex' | 'opencode' | 'builtin';
  config: {
    model_backend?: 'claude' | 'deepseek' | 'openai';
    max_iterations?: number;
    mcp_servers?: Record<string, unknown>[];
    command?: string | string[];
    args?: string[];
    timeout_seconds?: number;
    [key: string]: unknown;
  };
  capabilities: string[];
  systemPrompt: string;
}

export interface AgentsAdapter {
  listAgents(): Promise<Agent[]>;
  getAgent(agentId: string): Promise<Agent>;
  createAgent(input: CreateAgentInput): Promise<Agent>;
  updateAgent(agentId: string, input: Partial<CreateAgentInput>): Promise<Agent>;
  deleteAgent(agentId: string): Promise<void>;
}
```

真实 API 预期：

```text
GET    /api/v1/agents
GET    /api/v1/agents/{agent_id}
POST   /api/v1/agents
PATCH  /api/v1/agents/{agent_id}
DELETE /api/v1/agents/{agent_id}
```

前端当前状态：

- `useAgents` 从 `agentStore.agents` 读取。
- `AgentsPage` 创建 Agent 时调用 `agentStore.createAgent`。

迁移策略：

- Mock 模式保留 `agentStore`。
- API 模式使用 TanStack Query + mutation。
- 创建成功后 invalidate `['agents']`。

---

### 6.5 Artifacts Adapter

当前前端已经有产物预览：

- Markdown 文件预览：`preview_text`
- 网页构建预览：`preview_title` / `preview_body`

这些字段当前只是 Mock 扩展。真实接入时建议单独设计 artifact API。

建议文件：

```text
frontend/src/lib/adapters/artifacts.ts
```

建议接口：

```ts
export interface ArtifactPreview {
  id: string;
  type: 'markdown' | 'html' | 'image' | 'file';
  title: string;
  content?: string;
  url?: string;
  mimeType?: string;
}

export interface ArtifactsAdapter {
  getArtifactPreview(artifactId: string): Promise<ArtifactPreview>;
  getFileText(fileId: string): Promise<string>;
}
```

真实 API 预期：

```text
GET /api/v1/artifacts/{artifact_id}/preview
GET /api/v1/files/{file_id}/text
```

需要后端确认：

- `FileBlock` 是否只存 URL，还是存 `file_id`。
- `WebPreviewBlock` 是否存 `artifact_id`。
- 构建网页预览是 iframe URL、HTML 字符串，还是截图。
- Markdown 文件内容是否允许前端直接读取。

---

## 7. SSE Adapter 设计

当前文件：

```text
frontend/src/lib/sse.ts
```

建议拆分：

```text
frontend/src/lib/sse.ts       # 对外 subscribeMessageStream
frontend/src/lib/mockSse.ts   # Mock 事件生成
```

对外接口保持不变：

```ts
export function subscribeMessageStream(
  messageId: string,
  sub: StreamSubscriber,
): AbortController
```

真实 SSE 预期 URL：

```text
GET /api/v1/messages/{message_id}/stream
```

Header：

```text
Accept: text/event-stream
Authorization: Bearer <token>
```

事件契约：

| Event | Payload | 前端行为 |
|---|---|---|
| `start` | `{ message_id?, agent_id? }` | 消息进入 streaming |
| `block_start` | `{ block_index, block_type, metadata? }` | 创建 block |
| `delta` | `{ block_index, text_delta?, code_delta? }` | 增量追加 |
| `block_end` | `{ block_index }` | 当前 block 完成 |
| `done` | `{ message_id?, total_blocks? }` | 消息完成 |
| `error` | `{ error_code?, error? }` | 展示错误和重试 |
| `agent_switch` | `{ from_agent, to_agent, task? }` | 展示 Agent 切换 |
| `heartbeat` | `{}` | no-op |

需要后端确认：

- `block_index` 是否稳定递增。
- `metadata.language` 是否用于 code block。
- `agent_switch` 是否是独立 SSE event。
- 错误后 SSE 是否关闭。
- retry 后是否使用同一个 stream endpoint。

---

## 8. Hook 迁移策略

### 8.1 当前 Hook 返回形态

当前 hooks 多数返回：

```ts
{
  data,
  isLoading,
  error,
}
```

建议保留这个形态，方便页面不变。

### 8.2 TanStack Query 接入策略

真实 API 模式下：

```text
useConversations -> useQuery
useMessages      -> useQuery
useAgents        -> useQuery
useCreateConversation -> useMutation
useSendMessage   -> useMutation
```

Mock 模式下：

```text
useConversations -> Zustand selector + useMemo
useMessages      -> Zustand selector + useMemo
useAgents        -> Zustand selector + useMemo
useCreateConversation -> local async wrapper
useSendMessage   -> local async wrapper
```

### 8.3 推荐实现方式

先在 Adapter 层隐藏 Mock/API 分支：

```ts
const conversationsAdapter = env.useMockApi
  ? mockConversationsAdapter
  : apiConversationsAdapter;
```

hooks 只依赖 adapter：

```ts
export function useConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: conversationsAdapter.listConversations,
  });
}
```

但注意：

- 如果 Mock adapter 内部直接读 Zustand，`useQuery` 不会自动响应 Zustand 变化。
- 第一阶段可以保留当前 Mock hooks。
- 等真实 API 接入时再切 query。

因此推荐分两步：

1. 先补 Adapter 方法和类型，不动 hooks 行为。
2. 接真实 API 时，将 hooks 切到 TanStack Query。

---

## 9. 类型策略

项目规则要求：

- API 相关类型从 `frontend/src/lib/types.ts` 导入。
- `types.ts` 最终由 `shared/openapi.yaml` 生成。
- 不在前端手写重复 API 类型。

当前现实：

- `frontend/src/lib/types.ts` 仍是 placeholder。
- Demo 扩展类型在 `frontend/src/lib/mockData.ts` 中存在。

后续策略：

1. 后端 OpenAPI 稳定后运行：

```bash
cd frontend
pnpm gen:types
```

如果没有 pnpm：

```bash
cd frontend
npx openapi-typescript ../shared/openapi.yaml -o src/lib/types.ts
```

2. 前端将 adapter input/output 对齐生成类型。
3. Demo 扩展字段要么进入 OpenAPI，要么留在 Mock-only 类型中。

---

## 10. 需要纳入契约的前端扩展

当前前端已有一些 Demo-only 扩展：

| 能力 | 当前字段 / 类型 | 建议 |
|---|---|---|
| 任务卡 | `task_card` | 纳入 `ContentBlock` |
| Agent 切换 | `agent_switch` | 纳入 SSE event，是否纳入 ContentBlock 需讨论 |
| Markdown 文件预览 | `preview_text` | 改为 artifact/file preview API |
| 网页预览标题 | `preview_title` | 改为 artifact preview response |
| 网页预览正文 | `preview_body` | 改为 artifact preview response |
| 指定 Agent 发送 | `target_agent_id` | 纳入 send message request |

建议新增文档：

```text
docs/spec/frontend-api-alignment.spec.md
```

用于和 B1 / B2 对齐：

- ContentBlock schema
- SSE event schema
- message send request / response
- artifact preview API
- agent CRUD API

---

## 11. 推荐实施步骤

### ✅ Step 1：新增 env 封装

文件：

```text
frontend/src/lib/env.ts
```

目标：

- 统一 `VITE_USE_MOCK_API`
- 统一 `VITE_USE_MOCK_SSE`
- 统一 `VITE_API_BASE_URL`

验收：

- 当前 Mock Demo 行为不变。

### 🟡 Step 2：拆出 Mock SSE（已切 `env.useMockSse`；`mockSse.ts` 文件未拆）

文件：

```text
frontend/src/lib/mockSse.ts
frontend/src/lib/sse.ts
```

目标：

- `sse.ts` 只负责选择 Mock 或真实 SSE。
- `mockSse.ts` 负责 Demo 事件生成。

验收：

- 现有流式回复测试通过。
- Demo 群聊协作流不变。

### ✅ Step 3：新增 Adapter 类型与空实现

文件：

```text
frontend/src/lib/adapters/conversations.ts
frontend/src/lib/adapters/messages.ts
frontend/src/lib/adapters/agents.ts
frontend/src/lib/adapters/auth.ts
frontend/src/lib/adapters/artifacts.ts
```

目标：

- 先定义接口。
- Mock 实现调用现有 store。
- API 实现调用 `api.ts`，但可暂时不接入 hooks。

验收：

- 类型检查通过。
- hooks 行为不变。

### ✅ Step 4：逐步迁移 hooks

顺序：

```text
useAgents
useConversations
useMessages
useCreateConversation
useSendMessage
useAuth
```

验收：

- Mock 模式下所有页面行为不变。
- API 模式下可以按接口逐个联调。

### 🔴 Step 5：真实 API 联调（阻塞：后端 register 500）

前置条件：

- 后端 OpenAPI 更新。
- 前端重新生成 `types.ts`。
- 后端支持 auth / conversations / messages / agents。

验收：

- 登录拿到真实 token。
- 会话列表来自真实 API。
- Agent 列表来自真实 API。
- 发送消息返回 user message + agent message。
- SSE 能订阅 agent message stream。

---

## 12. 测试要求

Adapter 层准备阶段应补测试：

```text
frontend/src/lib/env.test.ts
frontend/src/lib/mockSse.test.ts
frontend/src/lib/adapters/*.test.ts
```

重点：

- env 默认值正确。
- `VITE_USE_MOCK_API=false` 时切换真实 API 分支。
- Mock adapter 返回结构与 hooks 预期一致。
- Mock SSE 事件序列稳定。

真实 API 接入后应补：

```text
frontend/src/lib/api.test.ts
frontend/src/hooks/useConversations.test.tsx
frontend/src/hooks/useMessages.test.tsx
frontend/src/hooks/useAgents.test.tsx
```

建议后续使用 MSW 或 fetch/axios mock，不依赖真实后端跑单元测试。

---

## 13. 风险与注意事项

### 13.1 不要破坏 Mock Demo

当前比赛演示依赖 Mock Demo。Adapter 准备阶段必须保证：

```bash
cd frontend
npm test -- --run
./node_modules/.bin/tsc -b
./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
./node_modules/.bin/vite build
```

全部通过。

### 13.2 不要提前硬编码后端未确认字段

如果后端未确认：

- endpoint path
- request body
- response shape
- SSE event payload

前端只能在文档中标记为“待确认”，不要直接写死真实实现。

### 13.3 不要让组件感知 Mock / API

组件只关心 props 和 hooks 返回值。

错误示例：

```tsx
if (import.meta.env.VITE_USE_MOCK_API) {
  ...
}
```

正确做法：

```text
Component -> Hook -> Adapter -> Mock/API
```

### 13.4 Demo 扩展要和契约隔离

`task_card`、`agent_switch`、artifact preview 字段暂时可以保留在 Demo 类型中，但真实接入前必须和后端同步。

---

## 14. 推荐下一步

建议下一步按这个顺序做：

1. 新增 `frontend/src/lib/env.ts`。
2. 将 `lib/sse.ts` 中的 Mock SSE 拆到 `lib/mockSse.ts`。
3. 新增 `docs/spec/frontend-api-alignment.spec.md`，列出需要后端确认的契约。
4. 新增 Adapter 接口文件，但暂时不迁移页面。
5. 为 `env` 和 `mockSse` 补测试。

这样能在不等待后端的情况下继续推进，同时保持当前 Demo 稳定。
