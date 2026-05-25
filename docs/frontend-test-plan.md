# AgentHub 前端测试补齐计划

> 本文档用于指导 AgentHub 前端测试建设。
> 当前后端仍在同步开发，因此测试重点先覆盖 Mock Demo、前端状态流和富媒体渲染，避免后续接真实 API 时破坏已有演示能力。

---

## 1. 目标

前端测试的第一阶段目标不是追求 100% 覆盖，而是保护当前 Demo 的核心路径：

- 聊天消息流不会被 SSE 事件改坏。
- 富媒体消息块能稳定渲染。
- 新建会话、发送消息、Agent mention、重试等关键交互可用。
- Agent 管理页的 Mock 创建流程可用。
- 后续真实 API / SSE 接入时，有测试能及时发现前端行为回归。

---

## 2. 当前测试基础

项目已具备基础测试配置：

- 测试框架：`vitest`
- DOM 环境：`jsdom`
- 组件测试：`@testing-library/react`
- 断言扩展：`@testing-library/jest-dom`
- 配置位置：`frontend/vite.config.ts`
- Setup 文件：`frontend/src/test-setup.ts`

当前配置：

```ts
test: {
  environment: 'jsdom',
  setupFiles: ['./src/test-setup.ts'],
  globals: true,
}
```

建议测试命令：

```bash
cd frontend
npm test
```

单次运行：

```bash
cd frontend
npm test -- --run
```

---

## 3. 测试分层

### 3.1 Store 测试

目标：验证 Zustand 状态变更，不依赖页面渲染。

优先覆盖：

- `chatStore`
- `agentStore`

建议文件：

```text
frontend/src/stores/chatStore.test.ts
frontend/src/stores/agentStore.test.ts
```

### 3.2 Hook 测试

目标：验证业务 Hook 的输入输出，尤其是 Mock API / SSE 的接入形态。

优先覆盖：

- `useSendMessage`
- `useCreateConversation`
- `useStream`

建议文件：

```text
frontend/src/hooks/useSendMessage.test.tsx
frontend/src/hooks/useCreateConversation.test.tsx
frontend/src/hooks/useStream.test.tsx
```

### 3.3 组件测试

目标：验证用户可见 UI 和交互。

优先覆盖：

- `MessageInput`
- `ContentRenderer`
- `FileBlock`
- `WebPreviewBlock`
- `CodeBlock`
- `AgentCreateDialog`
- `ConversationItem`

建议文件：

```text
frontend/src/components/chat/MessageInput.test.tsx
frontend/src/components/blocks/ContentRenderer.test.tsx
frontend/src/components/blocks/FileBlock.test.tsx
frontend/src/components/blocks/WebPreviewBlock.test.tsx
frontend/src/components/blocks/CodeBlock.test.tsx
frontend/src/components/agents/AgentCreateDialog.test.tsx
frontend/src/components/conversation/ConversationItem.test.tsx
```

### 3.4 页面级测试

目标：轻量覆盖 Demo 主路径，不做复杂端到端。

优先覆盖：

- `ChatPage`
- `AgentsPage`

建议文件：

```text
frontend/src/pages/ChatPage.test.tsx
frontend/src/pages/AgentsPage.test.tsx
```

---

## 4. 第一批测试优先级

建议第一批只做高收益测试，避免一次铺太大。

| 优先级 | 测试文件 | 覆盖内容 |
|---|---|---|
| P0 | `chatStore.test.ts` | 消息追加、SSE 事件、重试、Agent 路由 |
| P0 | `agentStore.test.ts` | 创建 Agent、重名 id、选中态 |
| P0 | `ContentRenderer.test.tsx` | block type 分发与 unknown fallback |
| P0 | `MessageInput.test.tsx` | 发送、禁用、Enter / Shift+Enter、mention |
| P1 | `FileBlock.test.tsx` | Markdown 预览弹层与外链入口 |
| P1 | `WebPreviewBlock.test.tsx` | 网页预览弹层与关闭 |
| P1 | `CodeBlock.test.tsx` | 复制按钮与语言标签 |
| P2 | `AgentCreateDialog.test.tsx` | 创建表单与取消 |
| P2 | `AgentsPage.test.tsx` | 分组、搜索、创建后详情 |
| P2 | `ChatPage.test.tsx` | Demo 页面主结构与空态 |

第一批建议实际落地顺序：

```text
1. chatStore.test.ts
2. agentStore.test.ts
3. ContentRenderer.test.tsx
4. MessageInput.test.tsx
5. FileBlock.test.tsx
6. WebPreviewBlock.test.tsx
```

---

## 5. 详细测试点

### 5.1 `chatStore`

文件：

```text
frontend/src/stores/chatStore.test.ts
```

测试点：

- `createConversation`
  - 创建单聊会话。
  - 创建群聊会话。
  - 创建后会话出现在列表头部。
  - 创建后消息列表初始化为空。
  - `selectedConversationId` 更新为新会话。

- `createPendingExchange`
  - 追加用户消息。
  - 追加 pending agent message。
  - 返回 `agentMessageId`。
  - 单聊默认路由到会话第一个 Agent。
  - 群聊未 mention 时默认路由到 `orchestrator`。
  - 群聊包含 `@agent-id` 时路由到指定 Agent。

- `applyStreamEvent`
  - `start` 将消息状态置为 `streaming`。
  - `block_start:text` 创建 text block。
  - `block_start:code` 创建 code block。
  - `delta.text_delta` 追加文本。
  - `delta.code_delta` 追加代码。
  - `agent_switch` 追加 agent switch block。
  - `done` 将状态置为 `done`。
  - `error` 将状态置为 `error` 并追加错误文本。

- `resetMessageForRetry`
  - 将指定消息状态重置为 `streaming`。
  - 清空内容并恢复为一个空 text block。

注意：

- Zustand store 是全局状态，测试之间必须重置。
- 可以通过 `useChatStore.setState(...)` 初始化固定状态。

---

### 5.2 `agentStore`

文件：

```text
frontend/src/stores/agentStore.test.ts
```

测试点：

- `createAgent`
  - 根据表单输入创建自建 Agent。
  - `is_builtin` 为 `false`。
  - 能力标签保存正确。
  - `system_prompt` 为空时保存为 `null`。
  - 创建后插入列表头部。
  - 创建后 `selectedAgentId` 更新为新 Agent。

- 重名处理
  - 同名 Agent 创建时自动生成不同 id。
  - 不能覆盖已有 Agent。

- `setSelectedAgentId`
  - 能正确更新选中 Agent。
  - 能设置为 `null`。

---

### 5.3 `ContentRenderer`

文件：

```text
frontend/src/components/blocks/ContentRenderer.test.tsx
```

测试点：

- `text` block 渲染 Markdown 文本。
- `code` block 渲染代码语言标签。
- `diff` block 渲染文件名和新增/删除统计。
- `web_preview` block 渲染标题和 URL。
- `file` block 渲染文件名、大小和预览按钮。
- `task_card` block 渲染任务标题。
- `agent_switch` block 渲染 Agent 切换分隔。
- 未知 block 渲染 `UnknownBlock`。

建议：

- 这里不需要深测每个子组件的内部行为，只验证分发正确。
- 子组件细节放到各自测试文件中。

---

### 5.4 `MessageInput`

文件：

```text
frontend/src/components/chat/MessageInput.test.tsx
```

测试点：

- 输入普通文本后点击发送，调用 `onSend(text)`。
- 空白文本不能发送。
- 按 Enter 发送。
- 按 Shift+Enter 不发送，用于保留换行行为。
- `isSending=true` 时 textarea 和发送按钮 disabled。
- 群聊输入 `@` 时显示 Agent mention picker。
- 选择 Agent 后插入 `@agent-id`。

需要准备：

- 单聊 `DemoConversation` mock。
- 群聊 `DemoConversation` mock。

---

### 5.5 `FileBlock`

文件：

```text
frontend/src/components/blocks/FileBlock.test.tsx
```

测试点：

- 渲染文件名、mime type、文件大小。
- 有 `previewText` 时显示“预览文件”按钮。
- 点击“预览文件”打开弹层。
- Markdown 内容在弹层中渲染。
- 点击“关闭预览”关闭弹层。
- 外链入口存在，且带有 `target="_blank"` 和 `rel="noreferrer"`。
- 没有 `previewText` 时不显示预览按钮。

---

### 5.6 `WebPreviewBlock`

文件：

```text
frontend/src/components/blocks/WebPreviewBlock.test.tsx
```

测试点：

- 渲染标题、描述、URL。
- 渲染 hostname。
- 点击“预览网页”打开弹层。
- 弹层展示模拟浏览器地址栏。
- 弹层展示 `previewTitle` 和 `previewBody`。
- 点击关闭按钮关闭弹层。
- 外链入口存在，且带有安全属性。

---

### 5.7 `CodeBlock`

文件：

```text
frontend/src/components/blocks/CodeBlock.test.tsx
```

测试点：

- 渲染语言标签。
- 渲染复制按钮。
- 点击复制调用 `navigator.clipboard.writeText`。
- 复制成功后显示“已复制”。
- Shiki 高亮失败时仍显示原始代码。

Mock 策略：

- 在测试中 mock `navigator.clipboard.writeText`。
- 如 Shiki 异步高亮导致测试慢，可 mock `shiki/core` 和语言包。

---

### 5.8 `AgentCreateDialog`

文件：

```text
frontend/src/components/agents/AgentCreateDialog.test.tsx
```

测试点：

- `open=false` 时不渲染。
- `open=true` 时显示表单。
- 修改名称、Provider、模型、能力标签、System Prompt。
- 点击创建调用 `onCreate`。
- 点击取消调用 `onClose`。
- 点击关闭按钮调用 `onClose`。

---

### 5.9 `AgentsPage`

文件：

```text
frontend/src/pages/AgentsPage.test.tsx
```

测试点：

- 显示“我的 Agent”和“内置 Agent”分组。
- 显示内置 Agent 卡片。
- 搜索无结果显示空状态。
- 点击创建 Agent，提交后出现在“我的 Agent”。
- 点击 Agent 后右侧详情更新。

注意：

- 页面测试需要重置 `agentStore`。
- 如果路由上下文缺失，需要用 `MemoryRouter` 包裹。

---

### 5.10 `ChatPage`

文件：

```text
frontend/src/pages/ChatPage.test.tsx
```

测试点：

- 默认渲染会话栏、消息区、右侧栏。
- 点击新建会话按钮打开弹窗。
- 创建新会话后显示空态。
- 发送消息后出现用户消息。
- 错误消息显示重试按钮。

注意：

- 页面测试可以先只做轻量验证。
- Mock SSE 的完整流式行为优先放到 store / hook 测试里。

---

## 6. 测试工具与 Mock 策略

### 6.1 推荐测试工具

使用 Testing Library：

```ts
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
```

当前项目尚未安装 `@testing-library/user-event`，建议补充：

```bash
cd frontend
npm install -D @testing-library/user-event
```

如果暂时不安装，也可以用 `fireEvent`，但用户行为测试会不如 `userEvent` 真实。

### 6.2 全局 Mock

建议扩展 `frontend/src/test-setup.ts`：

```ts
import '@testing-library/jest-dom';
import { vi } from 'vitest';

Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn(),
  },
});

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock;
```

如后续组件使用 `IntersectionObserver`，也在这里 mock。

### 6.3 Store 重置

Store 测试建议在每个 `beforeEach` 中重置：

```ts
beforeEach(() => {
  useChatStore.setState({
    conversations: mockConversations,
    messagesByConversation: mockMessages,
    selectedConversationId: mockConversations[0]?.id ?? '',
    search: '',
  });
});
```

如果后续 store 变复杂，可以抽出专门的 test helper。

---

## 7. 测试目录建议

优先采用“测试靠近源码”的结构：

```text
frontend/src/
├── stores/
│   ├── chatStore.ts
│   └── chatStore.test.ts
├── components/
│   ├── chat/
│   │   ├── MessageInput.tsx
│   │   └── MessageInput.test.tsx
│   └── blocks/
│       ├── FileBlock.tsx
│       └── FileBlock.test.tsx
└── pages/
    ├── AgentsPage.tsx
    └── AgentsPage.test.tsx
```

原因：

- 修改组件时容易同步维护测试。
- PR review 时能直接看到对应行为。
- 适合三人并行开发，减少跨目录查找成本。

---

## 8. 验收标准

第一批测试补齐完成后，应满足：

- `npm test -- --run` 通过。
- `npm run build` 通过。
- P0 测试全部落地。
- P1 至少完成 `FileBlock` 和 `WebPreviewBlock`。
- 测试不依赖真实后端。
- 测试不写死大量 DOM class，优先通过文本、role、label 查询。

---

## 9. 建议迭代顺序

### 第一轮：保护核心状态流

```text
chatStore.test.ts
agentStore.test.ts
```

### 第二轮：保护关键输入与渲染

```text
MessageInput.test.tsx
ContentRenderer.test.tsx
```

### 第三轮：保护富媒体预览

```text
FileBlock.test.tsx
WebPreviewBlock.test.tsx
CodeBlock.test.tsx
```

### 第四轮：保护页面级 Demo

```text
AgentsPage.test.tsx
ChatPage.test.tsx
```

---

## 10. 与真实 API 接入的关系

当前测试先覆盖 Mock 行为，但需要为真实 API 接入保留空间：

- 页面组件测试不应关心数据来自 Mock 还是 API。
- Hook 测试可以在后续拆成 Mock 模式和 API 模式两组。
- Store 测试保留，继续覆盖 UI 临时状态和流式增量状态。
- 当 `frontend/src/lib/types.ts` 由 OpenAPI 重新生成后，需要检查测试数据是否仍符合新类型。

真实 API 接入后建议新增：

```text
frontend/src/lib/api.test.ts
frontend/src/hooks/useConversations.api.test.tsx
frontend/src/hooks/useMessages.api.test.tsx
frontend/src/hooks/useAgents.api.test.tsx
```

可以用 MSW 或轻量 fetch mock 模拟后端响应。
