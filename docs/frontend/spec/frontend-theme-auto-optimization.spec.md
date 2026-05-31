# Frontend Theme Auto Optimization Spec

> Owner: F
> Scope: `frontend/**`
> Status: Draft

## 1. 目标

让 AgentHub 前端的深色模式、浅色模式和系统自动模式都达到可演示质量。

本次优化的目标不是单纯“能切换”，而是：

- 默认可跟随系统主题。
- 用户可以手动选择深色、浅色或系统。
- 深浅主题在聊天、Workspace、Agent 管理、归档、登录页等核心页面都清晰可读。
- 减少依赖 `html:not(.dark) .bg-slate-*` 这类全局反向映射，逐步迁移到明确的设计 token。

## 2. 当前状态

当前实现：

- `frontend/src/stores/uiStore.ts` 中 `ThemeMode = "dark" | "light"`。
- 默认主题为 `dark`。
- `applyTheme(theme)` 通过切换 `html.dark` 和 `color-scheme` 生效。
- `ModuleRail` 底部按钮支持深浅切换。
- `globals.css` 中大量使用 `html:not(.dark)` 把深色 Tailwind class 映射为浅色。
- 部分组件已显式写了 `dark:` / light class，例如 `CodeBlock`、`DiffBlock`、`ToolCallBlock`、`ConversationItem`。

主要问题：

1. 没有 `system` 自动模式。
2. 首屏主题可能在 rehydrate 前短暂错色。
3. 浅色主题依赖全局 class override，容易出现局部黑底黑字、白底白字。
4. 新组件容易继续写死 `bg-slate-950` / `text-white`，导致浅色回归。
5. Settings 里只展示运行状态，没有主题模式说明。

## 3. 目标体验

### 3.1 主题模式

支持三种用户选择：

```ts
type ThemePreference = "system" | "dark" | "light";
type ResolvedTheme = "dark" | "light";
```

语义：

- `system`：跟随 `window.matchMedia("(prefers-color-scheme: dark)")`。
- `dark`：强制深色。
- `light`：强制浅色。

默认：

- 新用户默认 `system`。
- 如果无法访问 `matchMedia`，默认 `dark`，保证当前演示视觉不退化。

### 3.2 用户入口

ModuleRail 主题按钮：

- 单击可在 `system -> dark -> light -> system` 间循环。
- tooltip / aria-label 显示当前模式，例如 `主题：跟随系统`。
- 图标建议：
  - `system`：Monitor / Laptop
  - `dark`：Moon
  - `light`：Sun

SettingsDialog：

- 展示：
  - `主题偏好`: System / Dark / Light
  - `当前生效`: Dark / Light
  - `系统主题`: Dark / Light / Unknown

### 3.3 自动响应

当用户选择 `system` 时：

- 系统主题变化后页面自动切换。
- 用户选择 `dark` 或 `light` 后不再跟随系统变化。

## 4. 技术方案

### 4.1 UI Store

文件：

- `frontend/src/stores/uiStore.ts`
- `frontend/src/stores/uiStore.test.ts`

建议状态：

```ts
export type ThemePreference = "system" | "dark" | "light";
export type ResolvedTheme = "dark" | "light";

interface UiState {
  themePreference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setThemePreference: (preference: ThemePreference) => void;
  cycleThemePreference: () => void;
}
```

保留兼容字段：

- 旧 localStorage 中可能存在 `theme: "dark" | "light"`。
- rehydrate 时迁移为 `themePreference`。
- 短期可保留 `theme` getter/alias，避免一次性大改组件。

### 4.2 applyTheme

建议拆分：

```ts
function resolveTheme(preference: ThemePreference): ResolvedTheme;
function applyResolvedTheme(theme: ResolvedTheme): void;
function subscribeSystemTheme(onChange: () => void): () => void;
```

DOM 规则：

```ts
document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
document.documentElement.dataset.theme = resolvedTheme;
document.documentElement.dataset.themePreference = preference;
document.documentElement.style.colorScheme = resolvedTheme;
```

原因：

- `class="dark"` 继续兼容 Tailwind `dark:`。
- `data-theme` 方便后续 token 和测试定位。
- `color-scheme` 影响表单控件和浏览器滚动条。

### 4.3 首屏防闪

在 React 挂载前尽早应用主题。

可选方案：

1. 在 `frontend/index.html` 注入极短 inline script。
2. 或在 `main.tsx` import store 前执行 `initializeTheme()`。

推荐 index inline script，避免 React bundle 加载前闪烁。

伪代码：

```html
<script>
  (() => {
    try {
      const raw = localStorage.getItem("agenthub-ui");
      const stored = raw ? JSON.parse(raw)?.state : null;
      const preference = stored?.themePreference || stored?.theme || "system";
      const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
      const resolved = preference === "system" ? (systemDark ? "dark" : "light") : preference;
      document.documentElement.classList.toggle("dark", resolved === "dark");
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themePreference = preference;
      document.documentElement.style.colorScheme = resolved;
    } catch {
      document.documentElement.classList.add("dark");
      document.documentElement.style.colorScheme = "dark";
    }
  })();
</script>
```

## 5. Design Token 方案

### 5.1 问题

当前大量组件直接写：

- `bg-slate-950`
- `bg-slate-900`
- `border-slate-800`
- `text-white`
- `text-slate-500`

然后在 `globals.css` 里用 `html:not(.dark)` 强行映射。这个方式短期有效，但长期很容易误伤：

- 某些组件需要保持深色，例如 brand button。
- 某些第三方输出，例如 Shiki / KaTeX，不适合被全局后代规则覆盖。
- class override 难以静态发现遗漏。

### 5.2 Token 分层

建议定义语义 token class，逐步替换组件硬编码：

| Token class | 深色 | 浅色 | 用途 |
|---|---|---|---|
| `surface-app` | slate-950 | slate-100 | App 主背景 |
| `surface-panel` | slate-900 | white | 侧栏、右栏、弹窗 |
| `surface-panel-muted` | slate-950/70 | slate-100/80 | 次级卡片 |
| `surface-elevated` | slate-900/80 | white/95 | 浮层、菜单 |
| `border-subtle` | slate-800 | slate-300 | 普通边框 |
| `border-strong` | slate-700 | slate-400 | 强边框 |
| `text-primary` | white/slate-100 | slate-950 | 主文字 |
| `text-secondary` | slate-300 | slate-700 | 次文字 |
| `text-muted` | slate-500 | slate-500 | 弱提示 |
| `interactive-muted` | hover slate-800 | hover slate-100 | 普通 hover |
| `message-agent` | slate-900/75 | white | Agent 气泡 |
| `message-user` | brand | brand | 用户气泡 |

实现位置：

- `frontend/src/styles/globals.css`

示例：

```css
@layer components {
  .surface-app {
    @apply bg-slate-100 text-slate-950 dark:bg-slate-950 dark:text-slate-100;
  }

  .surface-panel {
    @apply bg-white text-slate-950 dark:bg-slate-900 dark:text-slate-100;
  }

  .border-subtle {
    @apply border-slate-300 dark:border-slate-800;
  }
}
```

### 5.3 迁移策略

分阶段迁移，避免大爆炸式改动：

1. 新增 token class，不删除现有 `html:not(.dark)` fallback。
2. 优先迁移布局骨架：
   - `AppLayout`
   - `ModuleRail`
   - `ConversationSidebar`
   - `ChatPage`
   - `RightAgentPanel`
3. 迁移消息流：
   - `MessageBubble`
   - `MessageInput`
   - `StreamingStatusBar`
4. 迁移 Workspace：
   - `WorkspaceFileTree`
   - `ArtifactPreview`
5. 最后缩减 `globals.css` 中的全局 class override。

## 6. 浅色模式可读性审计

本优化必须显式解决“浅色模式下文字看不清”的问题。浅色主题不能只靠肉眼感觉通过，需要有清单、判定标准和回归入口。

### 6.1 判定标准

所有核心文本在浅色模式下必须满足：

- 正文 / 标题 / 按钮文字：对比度目标不低于 WCAG AA 4.5:1。
- 大号文字 / 标签 / badge：对比度目标不低于 3:1。
- 禁用态 / placeholder 可以低于正文，但必须能辨认，不得接近背景色。
- 品牌色按钮必须保持白字可读。
- 错误、成功、警告状态必须在浅色背景下同时具备颜色和文本语义，不能只靠颜色判断。

不允许出现：

- 黑底黑字。
- 白底白字。
- 深色透明背景叠在浅色页面上导致正文发灰。
- `text-white` 落在浅色卡片上。
- `text-slate-600` 落在深色浮层上。
- hover / active 后文字突然不可读。

### 6.2 必查文本类型

浅色模式必须逐项检查：

| 文本类型 | 典型组件 | 风险 |
|---|---|---|
| 页面标题 | ChatHeader, AgentsPage, ArchivePage | `text-white` 未转换 |
| 弱提示 | 空态、subtitle、时间戳 | 过浅导致看不清 |
| 输入内容 | MessageInput, LoginPage input | 输入框背景和文字冲突 |
| placeholder | 搜索框、消息输入框 | `placeholder:text-slate-600` 映射不足 |
| 按钮文字 | 发送、保存、编辑、关闭 | hover/disabled 状态冲突 |
| badge | provider, mode, status | 浅底低对比 |
| 错误文案 | SSE error, API error, ToolCall error | 红色在浅底过淡 |
| Markdown | TextBlock h/p/li/table/code/link | 局部元素仍用深色 token |
| 代码高亮 | CodeBlock, ToolCallBlock arguments | Shiki theme 与容器不匹配 |
| Workspace 文本 | 文件树、ArtifactPreview、全屏弹层 | 右栏沿用深色容器 |

### 6.3 自动审计建议

建议新增轻量 contrast audit 工具，不阻塞首轮实现，但应作为回归目标。

可选实现：

- 新建 `frontend/src/lib/themeContrast.ts`，维护关键 token 对。
- 新增 `frontend/src/lib/themeContrast.test.ts`，计算相对亮度和 contrast ratio。

测试 token：

```ts
const LIGHT_CONTRAST_CASES = [
  ["text-primary", "#020617", "#ffffff", 4.5],
  ["text-secondary", "#334155", "#ffffff", 4.5],
  ["text-muted", "#475569", "#ffffff", 4.5],
  ["error-text", "#b91c1c", "#fef2f2", 4.5],
  ["success-text", "#047857", "#ecfdf5", 4.5],
  ["brand-button", "#ffffff", "#635bff", 4.5],
];
```

注意：

- 自动审计覆盖 token，不替代浏览器视觉检查。
- 对渐变、透明、阴影、iframe、Shiki HTML 仍需手动或截图核对。

### 6.4 浏览器核对流程

每次主题改动后，至少执行以下浅色模式冒烟：

1. 切到 `Light`。
2. 打开 `/chat`，检查会话列表、消息区、右侧 Workspace。
3. 选中一条 Orchestrator/Agent 消息，检查作者名、时间、正文、ToolCallBlock。
4. 打开 Workspace 全屏预览，检查 header、保存按钮、textarea、文件替换入口。
5. 打开 `/agents`，检查 Agent 卡片、详情面板、创建/编辑弹窗。
6. 打开 `/archive`，检查空态、归档列表和操作按钮。
7. 打开 `/login`，检查输入框、错误提示和按钮。

每个页面记录：

- 是否有不可读文字。
- 哪个 class 或 token 导致不可读。
- 修复方式是 token 修改还是组件局部 `dark:` / light class 修改。

### 6.5 浅色缺陷修复优先级

| 优先级 | 类型 | 处理要求 |
|---|---|---|
| P0 | 正文、输入框、主要按钮不可读 | 必须立即修 |
| P1 | 次级说明、badge、hover/active 不清晰 | 当前迭代修 |
| P2 | 阴影层级、边框太淡、装饰图标不明显 | 可排后续 polish |

## 7. 组件验收范围

必须检查以下页面/组件：

### 7.1 页面

- `/login`
- `/chat`
- `/chat/:conversationId`
- `/agents`
- `/archive`
- `/markdown-test`

### 7.2 聊天核心

- 用户消息气泡
- Agent 消息气泡
- Orchestrator 多 Agent 分组消息
- StreamingStatusBar
- MessageInput
- AgentMentionPicker
- Pin / retry / error 状态

### 7.3 富媒体块

- TextBlock Markdown + KaTeX
- CodeBlock + Shiki `github-light` / `github-dark`
- DiffBlock
- ToolCallBlock
- WebPreviewBlock fullscreen
- FileBlock preview

### 7.4 Workspace

- 文件树选中态
- 文本预览
- HTML iframe 预览
- 全屏预览弹层
- 修改模式 textarea / 文件替换
- 保存中 / 已保存 / 错误态

### 7.5 Agent 管理

- AgentCard
- AgentDetailPanel
- AgentCreateDialog
- AgentEditDialog
- provider badge / builtin badge

## 8. 具体修改清单

### 8.1 Store

文件：

- `frontend/src/stores/uiStore.ts`
- `frontend/src/stores/uiStore.test.ts`

改动：

- 增加 `ThemePreference = "system" | "dark" | "light"`。
- 增加 `resolvedTheme`。
- 增加系统主题监听。
- 支持旧 localStorage `theme` 迁移。
- 测试覆盖：
  - manual dark
  - manual light
  - system dark
  - system light
  - system change event
  - localStorage migration

### 8.2 Layout

文件：

- `frontend/src/components/layout/AppLayout.tsx`
- `frontend/src/components/layout/ModuleRail.tsx`
- `frontend/src/components/layout/SettingsDialog.tsx`
- `frontend/src/components/layout/UserMenu.tsx`

改动：

- ModuleRail 展示三态主题图标。
- SettingsDialog 展示主题偏好和当前生效主题。
- Layout 使用 token class 替换硬编码背景。

### 8.3 CSS Token

文件：

- `frontend/src/styles/globals.css`

改动：

- 新增 semantic token class。
- 保留现有 `html:not(.dark)` fallback。
- 新增 theme-specific scrollbar token。
- 禁止新增 `.agent-markdown *` 级别后代覆盖，避免再次破坏 KaTeX。

### 8.4 Components

优先迁移：

- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/conversation/ConversationSidebar.tsx`
- `frontend/src/components/agents/RightAgentPanel.tsx`
- `frontend/src/components/artifact/ArtifactPreview.tsx`

原则：

- 新代码优先使用 token class。
- 组件特有状态仍可用显式 `dark:`。
- brand 色、status 色不要通过全局反向映射处理。

## 9. 测试计划

### 9.1 Unit / Component

必须新增或更新：

- `frontend/src/stores/uiStore.test.ts`
- `frontend/src/components/layout/ModuleRail.test.tsx`（如当前没有，可新增）
- `frontend/src/components/layout/SettingsDialog.test.tsx`
- `frontend/src/components/artifact/ArtifactPreview.test.tsx`
- `frontend/src/components/chat/MessageBubble.test.tsx`

重点断言：

- `document.documentElement.classList.contains("dark")` 正确。
- `data-theme` / `data-theme-preference` 正确。
- 切换主题按钮 aria-label 正确。
- Settings 中显示偏好和生效主题。
- 全屏弹层在 light/dark 下基础 class 不缺失。

### 9.2 Contrast / Readability

必须新增或执行：

- token contrast unit test，覆盖浅色核心文字 token。
- 浏览器浅色模式可读性 checklist。
- 修复记录写入 PR 描述或前端 changelog。

浅色模式 PR 必检项：

- [ ] 主要页面没有黑底黑字 / 白底白字。
- [ ] 输入框、placeholder、按钮、错误提示可读。
- [ ] Workspace 全屏预览可读。
- [ ] ToolCallBlock / CodeBlock / DiffBlock 可读。
- [ ] hover、selected、disabled 状态可读。

### 9.3 Visual Smoke

建议使用浏览器手动/自动冒烟：

1. 登录页 light/dark。
2. Chat 页面 light/dark/system。
3. Workspace 全屏预览 light/dark。
4. Agents 页面 light/dark。
5. Archive 页面 light/dark。

每个页面检查：

- 无黑底黑字 / 白底白字。
- 边框层级可见。
- hover/active 状态可见。
- 输入框 placeholder 可读。
- 弹窗遮罩不突兀。

### 9.4 Build

必须通过：

```bash
cd frontend
pnpm tsc --noEmit
pnpm lint
pnpm test -- --run
pnpm build
```

## 10. 验收标准

- 新用户默认跟随系统主题。
- 用户可以切换 System / Dark / Light，刷新后保留偏好。
- System 模式下，操作系统主题变化会自动更新页面。
- 深色主题保持当前演示质量。
- 浅色主题核心页面无明显可读性问题，且通过浅色可读性 checklist。
- 浅色核心文字 token 通过 contrast unit test。
- 不再新增依赖 `html:not(.dark) .bg-slate-*` 的全局补丁作为主要方案。
- CodeBlock 在浅色使用 `github-light`，深色使用 `github-dark`。
- KaTeX 不出现下标错位或布局被 CSS 覆盖。
- 全部前端测试和构建通过。

## 11. 不做事项

- 不引入完整设计系统库。
- 不重写 Tailwind 配置为 CSS variables 作为第一步。
- 不要求所有历史组件一次性迁移到 token class。
- 不做用户自定义颜色主题。
- 不做高对比度无障碍主题，但 token 设计要为后续保留空间。

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 全局 light override 误伤新 token | token class 优先显式 light/dark；逐步删除旧 override |
| rehydrate 前闪烁 | index inline script 提前设置 html class |
| matchMedia 在测试环境缺失 | store 中做 fallback，测试 mock matchMedia |
| KaTeX 被 CSS 覆盖 | 禁止 `.agent-markdown *` 全局规则 |
| Shiki 主题切换异步闪烁 | 维持当前 fallback pre 样式，highlight 完成后替换 |
| 浅色模式文字不可读但测试未发现 | token contrast test + 浏览器 checklist 双保险 |
