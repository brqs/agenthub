# AgentHub 前端 Demo 二轮打磨计划

> 本文档用于指导 AgentHub 前端 Demo 的第二轮体验打磨。
> 当前阶段不以真实后端联调为目标，因为后端仍在并行开发，部分功能暂时无法稳定测试。
> 本阶段重点是：重构前端界面、增强桌面 Demo 产品感、补齐主要交互入口、提升比赛演示稳定性。

---

## 执行状态速览（2026-05-25）

**整体进度：🟡 二轮 Demo 体验打磨主体已完成，剩余真实投屏微调。**

| 批次 | 内容 | 状态 |
|---|---|---|
| 第一批 | 聊天主界面重构 / 右侧栏协作状态 / Demo Prompt | 🟡 |
| 第二批 | Pin 消息 / Archive 入口 / 会话操作菜单 | 🟡 |
| 第三批 | 用户菜单 / Settings 面板 / 主题切换基础态 | 🟡 |
| 第四批 | 视觉一致性 / 动效细节 / Demo Seed 优化 | ✅ |
| 第五批 | 桌面布局收口 / 富媒体抗溢出 / 右栏状态密度 | ✅ |

🟢 全部 ✅／🟡 进行中／🔴 未开始

---

## 1. 阶段判断

目前前端已经完成：

- Discord 式桌面四栏布局
- Mock 会话 / 消息 / Agent 数据
- Mock API hooks 与 Mock SSE
- 多 Agent 协作演示流
- 富媒体消息块渲染
- Markdown / Diff / WebPreview / File 基础预览
- Agent 管理页
- Loading / Empty / Error / Retry 状态
- 第一批前端测试
- 真实 API Adapter 层准备

但当前仍不适合把二轮精力放到后端联调：

- 后端功能仍在并行开发，部分端点和真实流式结果还不稳定。
- 后端是否能跑通不应阻塞前端比赛 Demo。
- 当前最有价值的工作是把前端界面做得更完整、更像产品，而不是等待真实接口。
- Mock / Adapter 边界已经具备，后续真实 API 接入可以独立推进。

因此本阶段采用：

```text
前端界面重构优先
Mock Demo 体验优先
真实后端联调延后
```

---

## 2. 目标

### 2.1 产品目标

- 让评审在 3 分钟内看懂 AgentHub 的核心价值。
- 强化“多 Agent 群聊协作”与普通聊天工具的差异。
- 让聊天流里的任务拆解、Agent 接力、产物预览更醒目。
- 补齐模块栏、右侧栏、用户区等主要入口，减少“点了没反应”的感觉。
- 让整体界面从“可跑 Demo”提升为“可展示产品原型”。

### 2.2 技术目标

- 继续默认使用 Mock 数据和 Mock SSE。
- 不依赖真实后端，不把后端可用性纳入本阶段验收。
- 不改 `shared/openapi.yaml`，不改后端代码。
- 不破坏已完成的 Adapter 层与 Hook 双模式结构。
- 控制重构范围，以 `frontend/**` 为主。
- 每批完成后保持测试、类型检查、lint、build 通过。

### 2.3 非目标

本阶段暂不做：

- 真实 API 全链路联调
- 真实 SSE delta 端到端验收
- 移动端完整适配
- Tauri / Electron 客户端打包
- 新增复杂权限系统
- 大规模替换状态管理或 UI 框架

---

## 3. 当前界面问题

### 3.1 主演示路径还不够聚焦

现在聊天界面已经能跑通，但评审第一次看到时，需要从较多信息中自己理解：

- 当前 Orchestrator 在做什么
- 哪个 Agent 正在接力
- 任务拆解是否完成
- 聊天里的产物有哪些
- 为什么这是“多 Agent 协作”而不只是普通 AI 聊天

二轮打磨要把这些信息显式呈现出来。

### 3.2 模块入口还不完整

当前 Chat / Agents 主路径可用，但 Archive、Settings、用户菜单等边缘入口还不够完整。比赛演示时，如果评审点到这些入口，应该看到合理反馈。

### 3.3 右侧栏价值还可以更强

右侧栏目前承担 Agent 列表、上下文、Pin 信息，但还没有真正成为“协作状态面板”。二轮要把它升级为 Demo 的解释器：

- 当前协作模式
- Orchestrator 状态
- 活跃 Agent
- 任务进度
- Pin / 产物摘要

### 3.4 Mock 演示内容需要更像真实项目

Demo Seed 已经有基础内容，但还可以进一步固化为比赛演示脚本：用户提出复杂任务，Orchestrator 拆解，多个 Agent 接力，最后输出代码、Diff、网页预览和文件。

---

## 4. 打磨范围

本轮建议覆盖：

```text
1. 聊天主界面信息层级重构
2. 右侧栏协作状态增强
3. Demo Prompt 与标准演示会话
4. Pin 消息 Mock 交互
5. Archive Mock 入口
6. 用户菜单与 Settings 面板
7. 主题切换基础态
8. Agent 切换与任务卡动效
9. 视觉一致性与布局细节
```

所有功能默认基于 Mock 数据实现；如果已有真实 Adapter 能顺手复用，可以保持接口形态一致，但不把真实后端结果作为验收条件。

---

## 5. 详细任务

## 5.1 聊天主界面信息层级重构

目标：让 `/chat` 第一屏更像成熟协作产品，而不是单纯消息列表。

建议调整：

- `ChatHeader` 展示更明确的会话类型：单聊 / 群聊 / Orchestrated。
- 群聊会话顶部增加轻量协作摘要。
- 输入区附近加入 Demo Prompt 快捷入口。
- 消息流中强化任务卡、Agent 接力、产物块的视觉层级。
- 长代码块、Diff、WebPreview 不能撑破聊天区。

验收：

- 进入 Demo 会话后，不需要解释太多，用户能看出这是多 Agent 协作流。
- 1280x720 下聊天主区仍可用。
- 消息列表、输入框、右侧栏之间没有视觉拥挤或重叠。

---

## 5.2 右侧栏协作状态增强

当前右侧栏已有：

- 当前会话 Agent 列表
- Agent 能力标签
- Pin 消息入口
- Mock 模式说明

建议增强为“协作状态面板”。

### 5.2.1 Orchestrator 状态卡

群聊时展示：

- 当前协调者：Orchestrator
- 当前阶段：Planning / Routing / Generating / Reviewing / Done
- 当前接力 Agent
- 最近一次 Agent switch

建议 UI：

```text
Orchestrator
状态：正在协调
阶段：Generating
接力：OpenCode Helper -> Codex Helper
```

数据来源：

- 从当前消息里的 `task_card`、`agent_switch` block 推导。
- Mock 阶段不新增后端字段。

验收：

- 群聊右侧栏能明确看到 Orchestrator 正在做什么。
- 单聊会话展示“单 Agent 模式”，不强行出现 Orchestrator。

### 5.2.2 当前任务进度摘要

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

- Mock SSE 完成后进度可以显示为全部完成。
- 没有任务卡时展示简洁空态。

### 5.2.3 Agent 活跃状态

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
- 状态样式克制，不抢消息正文注意力。

---

## 5.3 Demo Prompt 与标准演示会话

### 5.3.1 标准演示会话

新增或强化一个固定会话：

```text
AgentHub 比赛演示
```

内容包含：

1. 用户提出复杂任务。
2. Orchestrator 拆解任务。
3. OpenCode Helper 给 UI 实现补充建议。
4. Codex Helper 输出代码。
5. Reviewer Agent 给出检查建议。
6. 附带 Markdown、Diff、WebPreview、File 产物。

验收：

- 不需要现场输入也能演示完整链路。
- 内容足够贴近 AgentHub 自身开发，不像空泛样例。

### 5.3.2 一键 Demo Prompt

在输入框附近或空态中提供建议 Prompt：

```text
@orchestrator 帮我完成一个带任务拆解、代码产物、Diff 和网页预览的前端开发演示
```

行为：

- 点击后填入输入框。
- 用户仍需手动发送，避免误触。

验收：

- 演示时不用手打长 prompt。
- Prompt 文案与 Mock SSE 返回内容一致。

---

## 5.4 Pin 消息 Mock 交互

当前：

- 消息数据里有 `is_pinned`。
- 右侧栏展示 Pin 消息。
- 但用户无法从消息气泡操作 Pin。

建议新增：

### 5.4.1 消息 Pin 按钮

在消息 hover 或消息头部展示 Pin 图标按钮。

行为：

- 点击后切换 `message.is_pinned`。
- 右侧 Pin 消息列表同步更新。
- 第一版不强制 Toast。

Store：

```ts
toggleMessagePin(messageId: string): void;
```

验收：

- 用户可以 Pin / Unpin 一条消息。
- 右侧栏立即同步。

### 5.4.2 Pin 列表定位

点击右侧 Pin 消息：

- 第一版可只高亮对应消息 1 秒。
- 不要求复杂滚动定位。

Store：

```ts
highlightedMessageId: string | null;
setHighlightedMessageId(messageId: string | null): void;
```

验收：

- 点击 Pin 消息后，聊天流中对应消息有短暂高亮。

---

## 5.5 Archive Mock 入口

当前：

- `Conversation` 有 `is_archived` 字段。
- 模块栏有 Archive 图标。
- 归档入口还不是完整体验。

建议新增：

### 5.5.1 归档视图

优先采用轻量方案：

```text
ModuleRail Archive -> /archive
```

`ArchivePage` 展示：

- 已归档会话列表
- 空态
- 点击会话可回到 `/chat/:conversationId`

验收：

- Archive 按钮不再像“死按钮”。
- 没有归档会话时有简洁空态。

### 5.5.2 会话归档操作

在会话列表 item 或 `ChatHeader` 的更多菜单中提供：

- Archive
- Unarchive

Store：

```ts
toggleConversationArchive(conversationId: string): void;
```

验收：

- 归档后会话从最近列表消失。
- 归档页可看到归档会话。
- 取消归档后会话回到聊天列表。

---

## 5.6 用户菜单与 Settings 面板

当前：

- 模块栏底部入口还不够清楚。
- Settings 与退出登录的语义容易混淆。

建议调整：

### 5.6.1 用户菜单

将底部区域拆成：

- User avatar / menu
- Theme toggle
- Settings

用户菜单内容：

- 当前用户：frontend-demo
- 当前模式：Mock Demo
- 退出登录

验收：

- 退出登录不藏在 Settings 图标里。
- 演示时能说明当前是前端 Mock Demo。

### 5.6.2 Settings 面板

点击 Settings 打开弹层：

- API 模式：Mock / Real 只读显示
- SSE 模式：Mock / Real 只读显示
- Base URL
- Demo 数据开关状态
- 构建版本占位

验收：

- Settings 不再是空按钮。
- 面板只展示状态，不提供不可用的真实配置编辑。

---

## 5.7 主题切换基础态

当前计划里提到明暗主题都预留，第一阶段精修深色主题。

本轮只做基础可用：

- Theme toggle 支持 dark / light。
- 默认 dark。
- light 不精修，但不能看不清。
- 主题写入 localStorage。

建议 store：

```text
frontend/src/stores/uiStore.ts
```

字段：

```ts
theme: 'dark' | 'light';
setTheme(theme: 'dark' | 'light'): void;
toggleTheme(): void;
```

验收：

- 点击主题按钮可以切换。
- 刷新后主题保持。
- 深色主题视觉不受影响。

注意：

- 如果当前样式大量写死 `bg-slate-950`，light 只能做到基础可用。
- 不要为了 light theme 大范围重写所有组件。

---

## 5.8 Agent 切换与任务卡动效

当前：

- 流式光标已有。
- `agent_switch` 有分隔 UI。
- TaskCard 状态能流转。

建议增强：

### 5.8.1 Agent Switch 动效

给 `agent_switch` block 增加：

- fade-in
- 轻微 slide-up
- Active Agent 高亮

验收：

- 群聊流式回复时 Agent 接力更清楚。

### 5.8.2 TaskCard 状态动效

状态变化：

- pending -> running：轻微 pulse
- running -> done：check icon 过渡

验收：

- 任务卡状态变化更容易被注意到。
- 动效克制，不影响阅读。

### 5.8.3 Streaming Status Bar

在 ChatHeader 下方或 MessageInput 上方显示：

```text
Codex Helper 正在输出代码...
```

数据来源：

- 当前 streaming message 的 `agent_id`
- 最新 block type

验收：

- 流式输出时用户能明确知道哪个 Agent 在工作。

---

## 5.9 视觉一致性与布局细节

建议检查：

- 所有 icon button 有 `title` 或 `aria-label`。
- 所有弹层关闭按钮位置一致。
- 卡片圆角保持 `rounded-md`，避免过度圆角。
- 不使用过多说明性文案占据界面。
- 右侧栏宽度稳定。
- 消息流长代码块不撑破布局。
- 弹层在 1280x720 下可用。
- 空态文案简洁，不解释过多功能。

验收：

- 1280x720、1440x900、宽屏下无明显错位。
- 所有主要交互按钮可点击且有反馈。
- Demo 首屏视觉重点明确。

---

## 6. 推荐实施顺序

### 第一批：主界面重构与演示聚焦

```text
1. 重构 ChatHeader / MessageList / MessageInput 的信息层级
2. 右侧栏以 Agent 列表为主，不再保留独立 OrchestratorStatusCard
3. 新增 DemoPromptBar
4. 强化标准演示会话 seed
```

原因：

- 直接影响比赛演示第一印象。
- 不依赖后端。
- 能最明显强化多 Agent 协作感。

### 第二批：补齐高频交互

```text
5. chatStore 增加 Pin / Highlight
6. MessageBubble 增加 Pin 按钮
7. 右侧 Pin 列表支持点击高亮
8. ArchivePage + 会话归档操作
```

原因：

- 让右侧栏和模块栏变成可用功能。
- 避免明显“死入口”。

### 第三批：补齐产品外壳

```text
9. UserMenu
10. SettingsDialog
11. uiStore
12. Theme toggle 基础态
```

原因：

- 让 Demo 更像完整产品。
- 这些能力独立于真实后端。

### 第四批：视觉与动效收口

```text
13. Agent switch 动效
14. TaskCard 状态动效
15. StreamingStatusBar
16. 响应式与可访问性检查
```

原因：

- 提升质感。
- 放在最后可以避免早期视觉细节反复返工。

---

## 7. 建议新增 / 修改文件

可能新增：

```text
frontend/src/stores/uiStore.ts
frontend/src/components/layout/UserMenu.tsx
frontend/src/components/layout/SettingsDialog.tsx
frontend/src/pages/ArchivePage.tsx
frontend/src/components/chat/DemoPromptBar.tsx
frontend/src/components/chat/StreamingStatusBar.tsx
```

可能修改：

```text
frontend/src/App.tsx
frontend/src/components/layout/ModuleRail.tsx
frontend/src/components/agents/RightAgentPanel.tsx
frontend/src/components/chat/ChatHeader.tsx
frontend/src/components/chat/MessageBubble.tsx
frontend/src/components/chat/MessageInput.tsx
frontend/src/components/chat/MessageList.tsx
frontend/src/components/blocks/TaskCardBlock.tsx
frontend/src/components/blocks/ContentRenderer.tsx
frontend/src/stores/chatStore.ts
frontend/src/lib/mockData.ts
```

---

## 8. Store 规划

### 8.1 `chatStore` 可新增

```ts
toggleMessagePin(messageId: string): void;
toggleConversationArchive(conversationId: string): void;
highlightedMessageId: string | null;
setHighlightedMessageId(messageId: string | null): void;
```

### 8.2 `uiStore` 可新增

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

## 9. 测试计划

二轮打磨需要补对应测试：

```text
frontend/src/stores/uiStore.test.ts
frontend/src/components/chat/DemoPromptBar.test.tsx
frontend/src/components/layout/UserMenu.test.tsx
frontend/src/components/layout/SettingsDialog.test.tsx
frontend/src/pages/ArchivePage.test.tsx
```

重点测试：

- 右侧 Agent 列表能从 Mock 消息 blocks 推导 Active / Done / Idle 状态。
- Demo Prompt 点击后填入输入框。
- Pin / Unpin 后右侧栏数据变化。
- Archive 后会话进入归档视图。
- UserMenu 点击退出登录。
- SettingsDialog 显示 Mock/API 状态。
- Theme toggle 能更新 DOM class 和 localStorage。

本阶段测试不要求真实后端可用。

---

## 10. 验证命令

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
3. 点击 Demo Prompt 并发送
4. 观察 Mock 多 Agent 流式回复
5. Pin 一条消息
6. 点击右侧 Pin 列表并高亮对应消息
7. 归档一个会话并进入 /archive
8. 打开用户菜单和 Settings
9. 切换主题
10. 检查 1280x720 下布局是否稳定
```

---

## 11. 验收标准

本轮完成后应满足：

- 主聊天界面信息层级更清楚。
- 右侧栏能表达当前多 Agent 协作状态。
- 标准 Demo 会话可以独立完成比赛演示。
- Demo Prompt 能降低现场输入成本。
- 用户能 Pin / Unpin 消息。
- 用户能进入 Archive 视图并看到合理空态或会话列表。
- 用户能打开用户菜单和设置面板。
- 主题切换基础可用。
- Agent 切换与任务卡状态变化更清晰。
- 现有测试全部通过。
- Mock Demo 不依赖后端仍可完整演示。

---

## 12. 风险与注意事项

### 12.1 不要把本阶段变成后端联调

真实 API / SSE 已经有 Adapter 边界，但当前阶段不要因为后端状态不稳定而阻塞前端界面重构。

### 12.2 不要扩大 Mock 与真实契约差异

可以继续使用 `task_card`、`agent_switch` 作为 Demo 扩展块，但需要集中在 `mockData.ts` / `ContentRenderer` / `chatStore` 这条链路内，不要散落到真实 API 类型里。

### 12.3 避免过度动画

动画只服务于状态理解。不要引入大面积动效，以免比赛演示时显得不稳。

### 12.4 不要扩大跨端范围

本轮仍以桌面 Demo 为主。移动端和客户端打包另开阶段处理。

### 12.5 保持测试同步

每新增一个可点击入口，至少补一个组件测试或 store 测试，避免 Mock 行为后续回归。

---

## 13. 推荐下一步

建议先做第一批：

```text
1. 调整 ChatHeader / MessageInput / MessageList 的 Demo 信息层级
2. RightAgentPanel 保留 Agent 列表作为主要协作状态面板
3. 新增 DemoPromptBar
4. 更新 mockData 的标准演示会话
5. 补 RightAgentPanel 与 DemoPromptBar 测试
```

完成这批后，Demo 的“多 Agent 协作感”和“现场演示稳定性”会提升最明显。
