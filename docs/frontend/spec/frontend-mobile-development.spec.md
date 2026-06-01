# Frontend Mobile Development Spec

> Owner: F
> Scope: `frontend/**`
> Status: Proposed
> Date: 2026-06-01

## 1. 背景与文档核对结论

本方案基于项目全量文档、归档文档、`shared/openapi.yaml` 和当前前端代码核对后形成。

文档优先级：

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/product-design.md`
4. `docs/tech-architecture.md`
5. `docs/frontend/**`
6. `shared/openapi.yaml`
7. `docs/archive/**`

归档文档不是当前实现入口，但原始课题文档仍提供产品边界：

- Web 端：完整 IM、代码编辑、全功能。
- 桌面端：本地文件访问、系统通知、Agent 进程管理。
- 移动端：轻量 IM，重点支持查看对话、审批确认、产物预览。

现行产品设计进一步明确：

- Web 移动端采用抽屉式侧边栏和单栏切换。
- PWA 在 Web 移动端基础上增加添加到主屏幕和基础 UI 离线缓存。
- React SPA 保持一份代码；PWA、Tauri、Capacitor 都是增量包装层。

因此，本轮移动端开发不是把桌面三栏布局压缩到手机宽度，而是建立移动端导航状态机和轻量工作流。

## 2. 目标

让 AgentHub 在手机和平板浏览器中具备可交付的移动 Web 体验，并为 PWA 和 Capacitor 包装保留稳定入口。

P0 目标：

- 手机竖屏下完成登录、会话切换、查看消息、发送消息、`@Agent`、查看流式回复。
- 手机端能够打开 Workspace、预览文件、查看部署状态和发布历史。
- 富媒体块不撑破视口，代码、Diff、日志可横向滚动。
- 所有主要操作不依赖 hover、右键或鼠标拖拽。
- 支持深色、浅色和跟随系统主题。

P1 目标：

- 增加 PWA manifest、图标和基础 service worker。
- 支持添加到主屏幕。
- 离线时展示应用壳和明确的只读提示，不伪造聊天、SSE 或 Workspace 数据。

P2 目标：

- 使用 Capacitor 包装同一份 `dist/`，输出 iOS / Android 壳。
- 增加原生安全区、键盘、返回键、外链打开策略。

## 3. 非目标

本轮不做：

- 不重写后端 API。
- 不修改 `shared/openapi.yaml`。
- 不在移动端开放本地 Agent runtime、宿主机 shell 或 Docker 管理。
- 不承诺离线发送消息、离线 SSE、离线 Workspace 编辑。
- 不在 P0 实现复杂手势导航、拖拽排序或原生推送。
- 不把 Monaco 等桌面级编辑器强塞入手机；手机先提供轻量文本编辑。

## 4. 当前实现缺口

### 4.1 全局布局

当前：

- `AppLayout` 使用 `h-screen w-screen`。
- `ModuleRail` 固定宽度 `w-16`，始终占据左侧。
- `ConversationSidebar` 固定宽度 `w-72`。
- `RightAgentPanel` 仅在 `xl` 显示。

问题：

- 手机端有效聊天宽度被模块栏继续侵占。
- 会话列表没有 drawer 语义。
- Workspace 在手机端不可访问。
- iOS Safari 地址栏变化时，`100vh` 可能导致输入框抖动或被遮挡。

### 4.2 聊天交互

当前：

- `ChatHeader` 操作较多，窄屏容易拥挤。
- `ConversationItem` 的 Pin / Archive 快捷按钮主要通过 hover 展示。
- `MessageBubble` 的 Agent 菜单通过右键触发。
- `MessageInput` 未处理软键盘和安全区。

问题：

- 触屏设备没有可靠 hover。
- 手机端需要长按或明确的更多菜单。
- 输入框需要保留底部安全区并避免键盘遮挡。

### 4.3 Workspace 与产物

当前：

- Workspace 文件树和发布历史只存在于桌面右栏。
- 文件、网页和 Artifact 全屏预览沿用桌面 modal。
- Diff 行使用较大的固定最小宽度，适合桌面横向滚动，但需要移动端提示。

问题：

- 手机端无法进入 Workspace。
- 全屏预览没有针对安全区和小屏操作栏优化。
- 文本编辑区需要区分手机轻量编辑和平板增强编辑。

### 4.4 Agent 管理

当前：

- `AgentsPage` 采用列表 + 桌面右侧详情栏。
- `AgentDetailPanel` 只在 `xl` 展示。
- 创建 / 编辑弹窗没有小屏底部 sheet 形态。

问题：

- 手机用户点 Agent 卡片后看不到详情。
- 长表单在软键盘场景下需要可滚动内容区和固定操作栏。

## 5. 产品范围

### 5.1 移动端核心旅程

P0 必须覆盖：

1. 登录真实账号。
2. 打开会话列表 drawer。
3. 搜索并切换会话。
4. 阅读单聊或群聊消息。
5. 发送消息，使用 `@Agent` 选择器。
6. 查看 SSE 流式状态和错误重试。
7. 打开 Workspace sheet。
8. 浏览文件树、预览文件、轻量编辑文本文件。
9. 查看 deployment 状态卡、复制 URL、打开部署地址、下载源码包。
10. 查看 Agent 列表和 Agent 详情。

### 5.2 手机端降级策略

| 能力 | 手机端策略 |
|---|---|
| 会话列表 | 左侧 drawer |
| 模块导航 | 底部导航栏 |
| Workspace / Context | 全屏 sheet，默认 Workspace |
| Workspace 文件树 | 文件列表 + 面包屑，避免深层树在窄屏挤压 |
| 文本文件编辑 | 轻量 textarea，保留保存能力 |
| HTML / 图片 / PDF 预览 | 全屏预览 |
| CodeBlock | 横向滚动 + 复制 |
| DiffBlock | 横向滚动 + 明确滚动提示 |
| ToolCallBlock | 默认折叠 |
| DeploymentStatusBlock | 操作按钮换行，保留复制、打开、下载、停止 |
| Agent 详情 | 全屏 sheet |
| Agent 创建 / 编辑 | 全屏 sheet，固定底部提交栏 |
| Pin / Archive | 更多菜单或长按菜单，不依赖 hover |

## 6. 响应式策略

沿用 Tailwind 断点：

```text
< 640px       手机竖屏
640 - 767px   大屏手机 / 手机横屏
768 - 1023px  平板
1024 - 1279px 笔记本
>= 1280px     桌面
```

布局模式：

| 模式 | 宽度 | 布局 |
|---|---:|---|
| `mobile` | `< 768px` | 单栏主内容 + 底部导航 + drawer / sheet |
| `tablet` | `768 - 1279px` | 模块栏 + 单栏内容；会话 drawer；Workspace sheet |
| `desktop` | `>= 1280px` | 现有模块栏 + 会话栏 + 聊天 + Workspace 右栏 |

实现原则：

- CSS 负责视觉布局。
- Zustand 负责用户主动打开 / 关闭 drawer 和 sheet。
- 不把 `window.innerWidth` 存进全局 store。
- 需要 JS 判断媒体查询时，新增 `useMediaQuery()` hook。
- 使用 `100dvh`，保留 `100vh` fallback。

## 7. 信息架构

### 7.1 手机聊天页

```text
┌──────────────────────────┐
│ ☰  会话标题        工作台 │
├──────────────────────────┤
│                          │
│ 消息流                   │
│                          │
├──────────────────────────┤
│ @ 提示 / Mention Picker  │
│ [附件] 输入消息...   [发] │
├──────────────────────────┤
│ 聊天   Agent   归档   设置│
└──────────────────────────┘
```

### 7.2 会话 drawer

```text
┌──────────────────────┐
│ AgentHub        关闭 │
│ 搜索会话             │
│ + 新建会话           │
│ 置顶                 │
│ 最近                 │
│ 会话列表             │
└──────────────────────┘
```

### 7.3 Workspace sheet

```text
┌──────────────────────────┐
│ 工作台              关闭 │
│ Context | Workspace      │
├──────────────────────────┤
│ 文件列表 / 面包屑         │
│ 文件预览 / 编辑           │
│ 发布历史                 │
└──────────────────────────┘
```

## 8. 状态设计

扩展 `frontend/src/stores/uiStore.ts`：

```ts
type MobileSheet = 'none' | 'conversation-list' | 'workspace' | 'agent-detail';

interface UiState {
  mobileSheet: MobileSheet;
  mobileNavVisible: boolean;
  openMobileSheet: (sheet: Exclude<MobileSheet, 'none'>) => void;
  closeMobileSheet: () => void;
}
```

规则：

- 切换会话后自动关闭 conversation drawer。
- 点击遮罩、关闭按钮或 `Escape` 关闭 sheet。
- 桌面断点恢复时关闭 mobile sheet，避免隐藏状态残留。
- 只持久化主题和桌面面板宽度，不持久化临时 mobile sheet。
- sheet 打开时锁定 body 滚动。

## 9. 组件改造方案

### 9.1 新增组件

建议新增：

```text
frontend/src/components/mobile/
├── MobileBottomNav.tsx
├── MobileSheet.tsx
├── MobileConversationDrawer.tsx
├── MobileWorkspaceSheet.tsx
├── MobileAgentDetailSheet.tsx
├── MobileMoreMenu.tsx
└── useMediaQuery.ts
```

### 9.2 Layout

修改：

- `frontend/src/components/layout/AppLayout.tsx`
- `frontend/src/components/layout/ModuleRail.tsx`
- `frontend/src/components/layout/UserMenu.tsx`
- `frontend/src/components/layout/SettingsDialog.tsx`
- `frontend/src/styles/globals.css`

要求：

- `< 768px` 隐藏 `ModuleRail`，显示 `MobileBottomNav`。
- UserMenu 在手机端改为底部 sheet。
- Settings 在手机端改为全屏或接近全屏 sheet。
- 根布局使用 `min-h-[100dvh] h-[100dvh]`。
- 增加 `env(safe-area-inset-top)` 和 `env(safe-area-inset-bottom)`。

### 9.3 Chat

修改：

- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/components/chat/ChatHeader.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/chat/AgentMentionPicker.tsx`

要求：

- 手机顶栏显示 drawer 按钮、截断标题和 Workspace 按钮。
- 次要操作收进 `MobileMoreMenu`。
- 消息区 padding 缩小到 `px-3`。
- 用户气泡手机最大宽度调整为约 `88%`。
- Agent 头像可缩小到 32px。
- Mention Picker 放在输入框上方，限制高度并允许滚动。
- 输入区增加安全区 padding。
- 软键盘弹出时保持输入区可见。

### 9.4 Conversation

修改：

- `frontend/src/components/conversation/ConversationSidebar.tsx`
- `frontend/src/components/conversation/ConversationItem.tsx`
- `frontend/src/components/conversation/NewConversationDialog.tsx`

要求：

- 复用同一个 `ConversationSidebar` 内容，不维护第二份会话逻辑。
- 桌面渲染为固定侧栏，手机渲染在 drawer 容器内。
- ConversationItem 在触屏模式始终显示更多按钮。
- Pin / Archive 放入操作菜单；保留桌面 hover 快捷按钮。
- 新建会话弹窗手机端全屏滚动，底部操作栏固定。

### 9.5 Workspace 与 Artifact

修改：

- `frontend/src/components/agents/RightAgentPanel.tsx`
- `frontend/src/components/artifact/WorkspaceFileTree.tsx`
- `frontend/src/components/artifact/ArtifactPreview.tsx`
- `frontend/src/components/artifact/DeploymentHistory.tsx`
- `frontend/src/components/blocks/DeploymentStatusBlock.tsx`
- `frontend/src/components/blocks/CodeBlock.tsx`
- `frontend/src/components/blocks/DiffBlock.tsx`
- `frontend/src/components/blocks/WebPreviewBlock.tsx`
- `frontend/src/components/blocks/FileBlock.tsx`
- `frontend/src/components/blocks/ToolCallBlock.tsx`

要求：

- 把右栏内部内容抽为可复用 `WorkspacePanelContent` / `ContextPanelContent`。
- 桌面继续渲染 `RightAgentPanel`。
- 手机由 `MobileWorkspaceSheet` 复用同一内容。
- Artifact 全屏预览使用 `100dvh`，手机取消外层大间距。
- 文件树手机端优先列表导航；平板可以保留树。
- Diff 和代码保留横向滚动，不做强制换行。
- ToolCall 默认折叠，Deployment 操作按钮允许换行。

### 9.6 Agent 管理

修改：

- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/components/agents/AgentDetailPanel.tsx`
- `frontend/src/components/agents/AgentCreateDialog.tsx`
- `frontend/src/components/agents/AgentEditDialog.tsx`

要求：

- 手机 Agent 列表单列。
- 点击 Agent 卡片打开详情 sheet。
- AgentDetailPanel 内容抽为 `AgentDetailContent`，桌面侧栏和手机 sheet 复用。
- 创建 / 编辑表单使用可滚动内容区，提交按钮固定到底部。
- 删除确认在移动端使用明确确认 dialog，不依赖浏览器默认样式作为最终产品形态。

## 10. PWA 方案

P1 新增：

```text
frontend/public/
├── manifest.webmanifest
├── icons/icon-192.png
├── icons/icon-512.png
└── icons/maskable-512.png
frontend/src/components/mobile/OfflineBanner.tsx
```

建议引入：

```bash
pnpm add -D vite-plugin-pwa
```

缓存规则：

- 预缓存静态应用壳：HTML、CSS、JS、字体、图标。
- 不缓存认证响应。
- 不缓存 SSE。
- Workspace tree、消息、deployment 状态默认走 network-first。
- 离线时不允许发送消息，输入区显示“当前离线，恢复网络后可继续发送”。
- 已渲染在内存中的消息可继续查看。

`index.html` 增加：

```html
<meta name="theme-color" content="#020617" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
```

## 11. Capacitor 方案

P2 执行，不能阻塞 P0/P1。

建议命令：

```bash
pnpm add @capacitor/core @capacitor/cli
pnpm exec cap init AgentHub com.agenthub.app
pnpm exec cap add ios
pnpm exec cap add android
```

边界：

- 继续使用同一套 Web API 和 SSE。
- API base URL 不能依赖 Vite dev proxy；移动壳必须配置真实 HTTPS API 地址。
- 外部部署 URL 使用系统浏览器打开。
- 下载 zip 需要针对 iOS / Android 文件系统能力单独验证。
- Android 返回键先关闭 sheet，再返回上一页。
- iOS 安全区和软键盘行为纳入 E2E。

## 12. API 与后端影响

### 12.1 P0 移动 Web

不需要后端修改。

理由：

- 认证、会话、消息、SSE、Agent、Workspace、Preview、Deployment API 已经存在。
- 移动端只是改变布局和交互入口。

### 12.2 P1 PWA

默认不需要后端修改。

可选增强：

- 后端增加健康检查和更明确的离线错误码。
- 静态托管配置 manifest 和 service worker 的缓存头。

### 12.3 P2 Capacitor

可能需要部署层调整：

- API 必须提供 HTTPS。
- CORS 允许 Capacitor origin。
- 下载与公开预览 URL 需要在移动网络下可访问。

这些属于部署 / B1 协作项，不在 F 单独实现范围。

## 13. 测试方案

### 13.1 组件测试

新增：

- `MobileBottomNav.test.tsx`
- `MobileSheet.test.tsx`
- `MobileConversationDrawer.test.tsx`
- `MobileWorkspaceSheet.test.tsx`
- `MobileAgentDetailSheet.test.tsx`
- `useMediaQuery.test.ts`

补充：

- `ChatHeader.test.tsx`
- `MessageInput.test.tsx`
- `ConversationItem.test.tsx`
- `RightAgentPanel.test.tsx`
- `ArtifactPreview.test.tsx`
- `DeploymentStatusBlock.test.tsx`
- `AgentsPage.test.tsx`

### 13.2 视口矩阵

浏览器验收至少覆盖：

| 设备 | 视口 |
|---|---|
| iPhone SE | `375 x 667` |
| iPhone 14 | `390 x 844` |
| Android 常见尺寸 | `412 x 915` |
| iPad Mini | `768 x 1024` |
| Laptop | `1366 x 768` |
| Desktop | `1440 x 900` |

每个视口核对：

- 页面无横向整体溢出。
- 输入框不被软键盘和底部导航遮挡。
- drawer / sheet 可打开、关闭和返回。
- Code / Diff 仅在块内部横向滚动。
- 深色、浅色、系统主题均可读。
- 部署 URL 可复制和打开。

### 13.3 自动验证

```bash
cd frontend
pnpm tsc --noEmit
pnpm lint
pnpm test -- --run
pnpm build
```

P1 增加：

```bash
pnpm exec vite preview
# Chrome DevTools Lighthouse: PWA / Accessibility / Best Practices
```

## 14. 分阶段实施

### Phase 0：基础设施

- 新增 `useMediaQuery`。
- 扩展 `uiStore` 的 mobile sheet 状态。
- 根布局切换为 `100dvh` 和安全区工具类。
- 建立移动组件目录和测试骨架。

### Phase 1：聊天主链路

- 底部导航。
- 会话 drawer。
- 手机聊天 Header。
- MessageList / MessageBubble / MessageInput 小屏适配。
- Mention Picker 与错误重试。

验收：手机竖屏可完成登录、切会话、发消息、看 SSE。

### Phase 2：Workspace 与富媒体

- Workspace 全屏 sheet。
- 文件树移动导航。
- Artifact 全屏预览和轻量文本编辑。
- Code / Diff / ToolCall / Deployment 卡片抗溢出。
- 发布历史移动展示。

验收：手机可查看产物、复制部署 URL、下载源码包、停止发布。

### Phase 3：Agent 与归档

- Agent 列表单列。
- Agent 详情 sheet。
- 创建 / 编辑表单 sheet。
- 归档页 padding、列表和空状态适配。
- UserMenu / Settings sheet。

### Phase 4：PWA

- manifest、图标、service worker。
- 离线 banner 和发送禁用态。
- 安装提示与 Lighthouse 核对。

### Phase 5：Capacitor

- iOS / Android 壳。
- HTTPS、CORS、外链、下载、返回键、安全区验证。

## 15. PR 拆分建议

| PR | 分支 | 内容 |
|---|---|---|
| PR-1 | `feat/F-mobile-layout-foundation` | `useMediaQuery`、`uiStore`、`MobileSheet`、底部导航 |
| PR-2 | `feat/F-mobile-chat-flow` | 会话 drawer、聊天 Header、消息、输入框、Mention |
| PR-3 | `feat/F-mobile-workspace-preview` | Workspace sheet、Artifact、Deployment、富媒体 |
| PR-4 | `feat/F-mobile-agent-management` | Agent 详情、创建编辑、归档、Settings |
| PR-5 | `feat/F-pwa-shell` | manifest、service worker、离线 UI |
| PR-6 | `feat/F-capacitor-shell` | Capacitor iOS / Android 包装 |

## 16. 验收标准

P0 完成定义：

- 手机宽度下不显示桌面固定模块栏、固定会话栏和固定 Workspace 右栏。
- 底部导航、会话 drawer 和 Workspace sheet 可用。
- 登录、聊天、SSE、错误重试、Workspace 预览、文本编辑、部署操作可用。
- 触屏操作不依赖 hover、右键和拖拽。
- Code / Diff / 日志不会撑破页面。
- 深色、浅色、系统主题在手机和平板可读。
- `pnpm tsc --noEmit`、`pnpm lint`、`pnpm test -- --run`、`pnpm build` 全部通过。

P1 完成定义：

- 可添加到主屏幕。
- 离线打开应用壳时有明确提示。
- 离线不发送消息，不伪造成功状态。

P2 完成定义：

- iOS / Android 包装能连接真实 HTTPS API。
- SSE、外链、下载、安全区和返回键通过真机或模拟器验收。

## 17. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 桌面和移动维护两套 UI 导致分叉 | 抽取内容组件，drawer / sheet 只做容器 |
| iOS Safari `100vh` 抖动 | 使用 `100dvh` + fallback |
| 软键盘遮挡输入区 | 固定底部区域 + safe-area + 真机验证 |
| hover 操作在手机不可用 | 明确更多菜单、长按只作为增强 |
| Workspace 树在手机过密 | 改为列表 + 面包屑 |
| PWA 缓存旧 bundle | service worker 版本化和更新提示 |
| SSE 离线重连误导用户 | 显示连接状态，不伪造恢复成功 |
| Capacitor 下载行为差异 | P2 单独验收文件系统和外链策略 |

