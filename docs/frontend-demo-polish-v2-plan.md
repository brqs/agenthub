# AgentHub 前端 Demo 二轮打磨计划

> 本文档用于指导 AgentHub 前端 Demo 的第二轮体验打磨。
> 当前真实后端仍在同步开发，因此本阶段继续以 Mock Demo 为主，目标是提升比赛演示的稳定性、完整度和产品感。

---

## 1. 背景

前端当前已经完成：

- Discord 式桌面四栏布局
- Mock 会话 / 消息 / Agent 数据
- Mock API hooks
- Mock SSE 流式回复
- 多 Agent 协作流
- 富媒体消息块
- Markdown / 网页产物内联预览
- Agent 管理页
- Loading / Empty / Error / Retry 状态
- 第一批前端测试

第一轮 Demo 已经“能跑通”。第二轮打磨的重点是让它“更像真实产品”：

- 演示路径更顺。
- 状态反馈更清楚。
- 边缘入口不显得空。
- 右侧栏更有协作感。
- 动效和视觉层级更稳定。

---

## 2. 目标

### 2.1 产品目标

- 让评审在 3 分钟内看懂 AgentHub 的核心价值。
- 强化“多 Agent 群聊协作”与普通聊天工具的差异。
- 强化“产物在聊天流内可查看”的产品感。
- 降低演示时因为空态、未实现按钮、视觉跳动造成的疑惑。

### 2.2 技术目标

- 不依赖真实后端。
- 不破坏当前 Mock API / Mock SSE 架构。
- 不引入复杂状态机。
- 保持现有测试通过。
- 新增打磨项尽量落在前端 Owner 范围：`frontend/**`。

---

## 3. 打磨范围

本轮建议覆盖：

```text
1. 右侧栏协作状态增强
2. Pin 消息 Mock 交互
3. 会话归档 Mock 交互
4. 设置 / 用户菜单 Mock
5. 主题切换基础可用
6. Agent 切换与流式状态动效
7. 演示脚本与 Demo Seed 优化
8. 视觉一致性与布局细节
```

不建议本轮做：

- 真实 API 接入
- 真实 SSE 联调
- 移动端完整适配
- 大规模重构
- 新增复杂权限模型

---

## 4. 详细任务

## 4.1 右侧栏协作状态增强

当前右侧栏已有：

- 当前会话 Agent 列表
- Agent 能力标签
- Pin 消息入口
- Mock 模式说明

建议增强：

### 4.1.1 Orchestrator 状态卡

群聊时展示：

- 当前协调者：Orchestrator
- 当前阶段：Planning / Routing / Generating / Reviewing / Done
- 当前接力 Agent
- 最近一次 `agent_switch`

建议 UI：

```text
Orchestrator
状态：正在协调
当前阶段：Generating
接力：Web Designer -> Codex Helper
```

数据来源：

- 可从当前消息中的 `task_card`、`agent_switch` block 推导。
- Mock 阶段不需要新增后端字段。

验收：

- 群聊会话右侧栏能明确看到 Orchestrator 正在做什么。
- 单聊会话不展示 Orchestrator 状态卡，或展示“单 Agent 模式”。

### 4.1.2 当前任务进度摘要

从最新 `task_card` 中提取：

- 总任务数
- 已完成数
- running 任务

建议 UI：

```text
任务进度 2 / 3
当前：输出可落地的前端实现片段
```

验收：

- 群聊 Mock SSE 完成后进度能显示为全部完成。

### 4.1.3 Agent 活跃状态

在右侧 Agent 列表上显示：

- Active
- Idle
- Done

Mock 推导：

- 最后一个 `agent_switch.to_agent` 为 Active。
- task_card done 的 Agent 为 Done。
- 其他为 Idle。

验收：

- 当前正在输出或最近接力的 Agent 有明确视觉标识。

---

## 4.2 Pin 消息 Mock 交互

当前：

- 消息数据里有 `is_pinned`。
- 右侧栏展示 Pin 消息。
- 但用户无法从消息气泡操作 Pin。

建议新增：

### 4.2.1 消息 Pin 按钮

在 Agent 消息 hover 或消息头部展示 Pin 图标按钮。

行为：

- 点击后切换 `message.is_pinned`。
- 右侧 Pin 消息列表同步更新。
- Toast 可选，第一版可以不用。

Store 需要：

```ts
toggleMessagePin(messageId: string): void
```

验收：

- 用户可以 Pin / Unpin 一条消息。
- 右侧栏立即同步。

### 4.2.2 Pin 列表定位

点击右侧 Pin 消息：

- 第一版可以只高亮对应消息 1 秒。
- 不要求复杂滚动定位。

可选 store：

```ts
highlightedMessageId: string | null
setHighlightedMessageId(messageId: string | null): void
```

验收：

- 点击 Pin 消息后，聊天流中对应消息有短暂高亮。

---

## 4.3 会话归档 Mock 交互

当前：

- `Conversation` 有 `is_archived` 字段。
- 模块栏有 Archive 图标，但暂不可用。

建议新增：

### 4.3.1 会话归档视图

在模块栏点击 Archive：

- 不新增真实路由也可以。
- 可以在 ChatPage 里切换 sidebar filter。
- 或新增 `/archive` 页面，展示已归档会话。

建议更简单方案：

```text
ModuleRail Archive -> /chat?view=archive
```

如果不想处理 query：

```text
新增 /archive 页面，只展示 Mock archived conversations
```

验收：

- Archive 按钮不再像“死按钮”。
- 至少有一个空态：暂无归档会话。

### 4.3.2 会话归档操作

在会话列表 item 或 ChatHeader 的更多菜单中提供：

- Archive
- Unarchive

Store：

```ts
toggleConversationArchive(conversationId: string): void
```

验收：

- 归档后会话从最近列表消失。
- 归档页可看到归档会话。

---

## 4.4 设置 / 用户菜单 Mock

当前：

- 模块栏底部 Settings 图标用于退出登录。
- 主题按钮还没有实际行为。
- 用户菜单没有明确入口。

建议调整：

### 4.4.1 用户菜单

将底部按钮拆分：

- User avatar / menu
- Theme toggle
- Settings

用户菜单内容：

- 当前用户：frontend-demo
- Mock 模式：开启
- 退出登录

验收：

- 退出登录不藏在 Settings 图标里。
- 演示时能解释“当前是 Mock Demo 模式”。

### 4.4.2 Settings 面板

点击 Settings 打开右侧或居中弹层：

- API 模式：Mock / Real 只读显示
- SSE 模式：Mock / Real 只读显示
- Base URL
- 构建版本占位

验收：

- Settings 不再是空按钮。
- 能在演示中说明后续真实 API 可切换。

---

## 4.5 主题切换基础可用

当前计划里提到明暗主题都预留，但第一阶段精修深色主题。

建议本轮做“基础可用”：

- Theme toggle 支持 dark / light。
- 默认 dark。
- light 不做精修，但不能看不清。
- 主题写入 localStorage。

建议 store：

```text
frontend/src/stores/uiStore.ts
```

字段：

```ts
theme: 'dark' | 'light'
rightPanelOpen: boolean
setTheme(theme): void
toggleTheme(): void
```

验收：

- 点击主题按钮可以切换。
- 刷新后主题保持。
- 深色主题视觉不受影响。

注意：

- Tailwind 需要确认 `darkMode` 配置。
- 如果当前样式大量写死 `bg-slate-950`，light 只能做到基础可用，不追求精修。

---

## 4.6 Agent 切换与流式状态动效

当前：

- 流式光标已有。
- `agent_switch` 有分隔 UI。
- TaskCard 状态能流转。

建议增强：

### 4.6.1 Agent Switch 动效

给 `agent_switch` block 增加：

- fade-in
- 轻微 slide-up
- Active Agent 高亮

验收：

- 群聊流式回复时 Agent 接力更清楚。

### 4.6.2 TaskCard 状态动效

状态变化：

- pending -> running：轻微 pulse
- running -> done：check icon 过渡

验收：

- 任务卡状态变化更容易被注意到。

### 4.6.3 Streaming Status Bar

在 ChatHeader 或 MessageInput 上方显示：

```text
Codex Helper 正在输出代码...
```

数据来源：

- 当前 streaming message 的 `agent_id`
- 最新 block type

验收：

- 流式输出时用户能明确知道哪个 Agent 在工作。

---

## 4.7 演示脚本与 Demo Seed 优化

当前 Demo seed 已经包含：

- Discord 风格前端壳
- React Todo 组件
- 产品文案
- 答辩 Demo 流程

建议补充：

### 4.7.1 标准演示会话

新增或强化一个固定会话：

```text
AgentHub 比赛演示
```

内容包含：

1. 用户提出复杂任务。
2. Orchestrator 拆解任务。
3. Web Designer 给 UI 建议。
4. Codex Helper 输出代码。
5. Reviewer Agent 给出检查。
6. 附带 Markdown 文档和网页构建预览。

验收：

- 不需要现场输入也能演示完整链路。

### 4.7.2 一键 Demo Prompt

在输入框附近或新建会话空态中提供建议 Prompt：

```text
@orchestrator 帮我做一个带任务拆解、代码产物和网页预览的演示
```

点击后填入输入框，用户再发送。

验收：

- 演示时不用手打长 prompt。

---

## 4.8 视觉一致性与布局细节

建议检查：

- 所有按钮都有 `title` / `aria-label`。
- 所有弹层关闭按钮位置一致。
- 卡片圆角保持 `rounded-md`，不扩大成过度圆角。
- 右侧栏宽度稳定。
- 消息流长代码块不撑破布局。
- 弹层在 1280x720 下可用。
- 空态文案简洁，不解释过多功能。

验收：

- 1280x720、1440x900、宽屏下无明显错位。
- 所有交互按钮可点击且不是“死入口”。

---

## 5. 推荐实施顺序

### 第一批：最影响演示的入口

```text
1. 右侧栏 Orchestrator 状态卡
2. Pin 消息 Mock 交互
3. 一键 Demo Prompt
```

原因：

- 直接强化多 Agent 协作感。
- 演示中最容易被看到。
- 不依赖后端。

### 第二批：补齐导航死角

```text
4. Archive Mock 页面 / 空态
5. 用户菜单
6. Settings Mock 面板
```

原因：

- 避免评审点到按钮后没有反应。
- 让产品完整度更高。

### 第三批：视觉和主题

```text
7. Agent switch 动效
8. TaskCard 状态动效
9. 主题切换基础可用
```

原因：

- 增强质感。
- 但优先级低于主演示路径。

---

## 6. 建议新增 / 修改文件

可能新增：

```text
frontend/src/stores/uiStore.ts
frontend/src/components/layout/UserMenu.tsx
frontend/src/components/layout/SettingsDialog.tsx
frontend/src/pages/ArchivePage.tsx
frontend/src/components/chat/DemoPromptBar.tsx
frontend/src/components/chat/StreamingStatusBar.tsx
frontend/src/components/agents/OrchestratorStatusCard.tsx
```

可能修改：

```text
frontend/src/App.tsx
frontend/src/components/layout/ModuleRail.tsx
frontend/src/components/agents/RightAgentPanel.tsx
frontend/src/components/chat/MessageBubble.tsx
frontend/src/components/chat/MessageInput.tsx
frontend/src/components/blocks/TaskCardBlock.tsx
frontend/src/components/blocks/ContentRenderer.tsx
frontend/src/stores/chatStore.ts
frontend/src/lib/mockData.ts
```

---

## 7. Store 规划

### 7.1 `chatStore` 可新增

```ts
toggleMessagePin(messageId: string): void;
toggleConversationArchive(conversationId: string): void;
highlightedMessageId: string | null;
setHighlightedMessageId(messageId: string | null): void;
```

### 7.2 `uiStore` 可新增

```ts
theme: 'dark' | 'light';
settingsOpen: boolean;
userMenuOpen: boolean;
rightPanelOpen: boolean;
toggleTheme(): void;
setSettingsOpen(open: boolean): void;
setUserMenuOpen(open: boolean): void;
setRightPanelOpen(open: boolean): void;
```

---

## 8. 测试计划

二轮打磨需要补对应测试：

```text
frontend/src/stores/uiStore.test.ts
frontend/src/components/agents/OrchestratorStatusCard.test.tsx
frontend/src/components/chat/DemoPromptBar.test.tsx
frontend/src/components/layout/UserMenu.test.tsx
frontend/src/components/layout/SettingsDialog.test.tsx
frontend/src/pages/ArchivePage.test.tsx
```

重点测试：

- Pin / Unpin 后右侧栏数据变化。
- Archive 后会话进入归档视图。
- Demo Prompt 点击后填入输入框。
- UserMenu 点击退出登录。
- SettingsDialog 显示 Mock/API 状态。
- OrchestratorStatusCard 能从消息 blocks 推导状态。

---

## 9. 验证命令

每批完成后执行：

```bash
cd frontend
npm test -- --run
./node_modules/.bin/tsc -b
./node_modules/.bin/eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
./node_modules/.bin/vite build
```

浏览器手动验证：

```text
1. 进入 /chat/conv-demo-flow
2. 查看右侧 Orchestrator 状态
3. 发送群聊 Mock prompt
4. Pin 一条消息
5. 打开 Pin 列表并点击
6. 进入 Archive 页面
7. 打开用户菜单和 Settings
8. 切换主题
```

---

## 10. 验收标准

本轮完成后应满足：

- 主要模块栏按钮都有可见反馈。
- 右侧栏能表达当前多 Agent 协作状态。
- 用户能 Pin / Unpin 消息。
- 用户能查看归档入口或归档页面。
- 用户能打开用户菜单和设置面板。
- 主题切换基础可用。
- Demo Prompt 能降低演示输入成本。
- 流式与 Agent 切换更清晰。
- 现有测试全部通过。
- Mock Demo 不依赖后端仍可完整演示。

---

## 11. 风险与注意事项

### 11.1 不要把 Mock 入口做成真实承诺

Settings 面板、Archive 页面、Pin 功能都应保持 Mock 语义清晰，避免评审误以为后端已完成。

### 11.2 避免过度动画

动画只服务于状态理解。不要引入大面积动效，以免比赛演示时显得不稳。

### 11.3 不要扩大跨端范围

本轮仍以桌面 Demo 为主。移动端和客户端打包可以另开文档。

### 11.4 保持测试同步

每新增一个可点击入口，至少补一个组件测试或 store 测试，避免 Mock 行为后续回归。

---

## 12. 推荐下一步

建议先做第一批：

```text
1. RightAgentPanel 增加 OrchestratorStatusCard
2. chatStore 增加 toggleMessagePin
3. MessageBubble 增加 Pin 按钮
4. 新增 DemoPromptBar
5. 补对应测试
```

这批完成后，Demo 的“多 Agent 协作感”和“可演示稳定性”会提升最明显。
