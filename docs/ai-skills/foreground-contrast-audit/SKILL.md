---
name: foreground-contrast-audit
description: Use when changing AgentHub frontend foreground colors, text tokens, theme classes, light/dark readability, contrast, hover/selected/disabled states, or when the user asks to check every module/component for text visibility in both dark and light mode.
---

# Foreground Contrast Audit Skill

> 类型：AI 协作 Skill / 前端可读性修复闭环
> 适用范围：AgentHub 前端前景色、文本颜色、状态色、明暗主题、组件级对比度验收
> 最后更新：2026-06-08

---

## 1. 何时使用

当任务涉及“文字看不清”“前景色”“对比度”“浅色模式/深色模式”“hover 后不可读”“组件颜色统一”“逐个模块逐个组件检查”时，必须使用本 Skill。

典型触发语句：

- “优化前端字体颜色 / 前景色”
- “浅色模式有字看不清”
- “深色模式和浅色模式都检查一遍”
- “逐个模块逐个组件校验颜色”
- “修一下 hover / selected / disabled 的对比度”
- “做 WCAG / contrast audit”
- “颜色改完后帮我验收”

---

## 2. 核心目标

不是只改一个 class，而是进入闭环：

```text
发现前景色/对比度风险
-> 确认真实背景和状态
-> 按模块列出受影响组件
-> 最小修复 token 或组件 class
-> 补充/更新 contrast 单测
-> 深色模式浏览器验收
-> 浅色模式浏览器验收
-> 移动窄屏验收
-> 记录修复和剩余风险
```

如果发现一个组件有问题，必须顺手检查同类组件是否复用同一错误模式，例如 `text-white` 落在浅色卡片、`text-slate-600` 落在深色浮层、透明深色背景覆盖浅色页面。

---

## 3. 判定标准

### 3.1 对比度阈值

采用 WCAG AA 作为最低线：

| 文本类型 | 最低 contrast ratio |
|---|---:|
| 正文、标题、输入文字、主按钮文字 | 4.5:1 |
| 大号文字、粗体短标签、badge | 3:1 |
| 图标按钮、边框表达状态 | 3:1 |
| placeholder、disabled | 可以低于 4.5:1，但必须能辨认且不能接近背景 |

状态色必须同时有文本语义，不能只靠颜色判断。

### 3.2 必须禁止

- 黑底黑字。
- 白底白字。
- 低透明度文字叠在复杂背景上。
- `text-white` 出现在浅色卡片、浅色弹窗、浅色输入框。
- `text-slate-600` / `text-slate-700` 出现在深色浮层。
- hover / selected / active / disabled 后文字突然不可读。
- 只修 light mode 导致 dark mode 演示质量下降。

### 3.3 真实背景优先

不要只看 Tailwind class 名称判断颜色。必须考虑：

- `html.dark` / `html:not(.dark)` 全局 override。
- `data-theme` / `data-theme-preference`。
- 父级透明背景、backdrop、overlay、message bubble、selected row。
- Shiki、Markdown、KaTeX、iframe 内外背景。
- 移动端 safe-area、bottom nav、sheet、软键盘区域。

---

## 4. 前置阅读

开工前至少阅读：

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,260p' docs/frontend/spec/frontend-theme-auto-optimization.spec.md
sed -n '1,220p' frontend/src/lib/themeContrast.ts
sed -n '1,220p' frontend/src/stores/uiStore.ts
```

如果修改代码高亮、Markdown 或 workspace 预览，再读：

```bash
sed -n '1,220p' docs/frontend/spec/workspace-code-preview-highlighting.spec.md
sed -n '1,220p' frontend/src/components/blocks/SyntaxHighlightedCode.tsx
```

---

## 5. 审查范围

每次前景色/对比度任务都要按模块扫一遍。不要只看当前截图中的组件。

### 5.1 页面模块

| 路由 | 必查区域 |
|---|---|
| `/login` | 标题、副标题、输入框、placeholder、错误文案、主按钮、切换登录/注册 |
| `/chat` | 空态、会话列表、聊天头部、消息流、输入区、右侧栏、设置/用户菜单 |
| `/chat/:conversationId` | 用户气泡、Agent 气泡、所有 ContentBlock、streaming/error/retry 状态 |
| `/agents` | Agent 卡片、详情、创建/编辑弹窗、knowledge/skill 上传与删除 |
| `/archive` | 归档列表、空态、操作按钮、hover/selected |
| `/markdown-test` | Markdown、GFM table、inline code、code fence、KaTeX |

### 5.2 组件模块

| 模块 | 组件 |
|---|---|
| Layout | `AppLayout`, `ModuleRail`, `SettingsDialog`, `UserMenu`, `OfflineBanner` |
| Conversation | `ConversationSidebar`, `ConversationItem`, `NewConversationDialog` |
| Chat | `ChatHeader`, `MessageList`, `MessageBubble`, `MessageInput`, `AgentMentionPicker`, `StreamingStatusBar` |
| Blocks | `TextBlock`, `CodeBlock`, `DiffBlock`, `ToolCallBlock`, `ProcessBlock`, `TaskCardBlock`, `DeploymentStatusBlock`, `FileBlock`, `AttachmentBlock`, `ClarificationCard`, `TurnControlBlock`, `WorkflowBlock`, `UnknownBlock`, `WebPreviewBlock` |
| Workspace | `WorkspaceFileTree`, `ArtifactPreview`, `WorkspaceCodePreview`, `DeploymentHistory` |
| Agents | `AgentCard`, `AgentDetailPanel`, `AgentCreateDialog`, `AgentEditDialog`, `RightAgentPanel` |
| Mobile | `MobileBottomNav`, `MobileSheet`, chat narrow layout, input safe-area |

### 5.3 状态矩阵

每个可交互组件至少检查：

- default
- hover
- active / selected
- focus-visible
- disabled
- loading / streaming
- success
- warning
- error
- empty

---

## 6. 标准工作流

### Step 1 - 建立风险清单

用 `rg` 找高风险 class 和硬编码颜色：

```bash
cd frontend
rg -n "text-white|text-slate-[56789]00|text-gray-[56789]00|bg-slate-9|bg-black|opacity-[0-9]+|#[0-9a-fA-F]{3,8}|rgba?\\(" src
```

同时列出本轮涉及的组件：

```bash
git diff --name-only -- src
find src/components src/pages -maxdepth 2 -type f \( -name '*.tsx' -o -name '*.ts' \) | sort
```

### Step 2 - 优先改 token 或局部显式 light/dark class

修复优先级：

1. 优先使用已有语义 token、局部 `text-slate-* dark:text-slate-*`、`bg-* dark:bg-*`。
2. 同一类组件重复问题，抽成局部 helper 或统一 class 常量。
3. 只有当全局 token 确实缺失时，才改 `frontend/src/styles/globals.css` 或新增 token。
4. 不要用更低 opacity “调柔”正文文字。
5. 不要为了浅色模式改掉深色模式已稳定的品牌层级。

### Step 3 - 更新 contrast 单测

如果新增或调整核心 token，必须同步维护：

```text
frontend/src/lib/themeContrast.ts
frontend/src/lib/themeContrast.test.ts
```

至少覆盖：

- app surface 上的 primary / secondary / muted text。
- panel/card 上的正文和次级文字。
- input text / placeholder。
- brand button。
- success / warning / error status。
- code preview header / line number / inline code。

浅色和深色都要覆盖；如果当前文件只有 light cases，应新增 `DARK_THEME_CONTRAST_CASES`。

运行：

```bash
cd frontend
pnpm test -- --run src/lib/themeContrast.test.ts
```

### Step 4 - 浏览器逐模块验收

必须分别验收 `light` 和 `dark`。

建议顺序：

```text
Light -> 登录页 -> Chat -> 右侧 Workspace -> Blocks -> Agents -> Archive -> Mobile narrow
Dark  -> 登录页 -> Chat -> 右侧 Workspace -> Blocks -> Agents -> Archive -> Mobile narrow
```

浏览器验收重点：

- 页面级无横向溢出。
- 所有文字能在实际背景上看清。
- selected/hover 不反转出低对比。
- 输入框、placeholder、按钮、错误文案可读。
- Markdown 表格、inline code、链接、blockquote 可读。
- CodeBlock / ToolCallBlock / WorkspaceCodePreview 高亮与容器背景匹配。
- 弹窗、sheet、menu、toast 不出现浅底浅字或深底深字。
- 移动端底部导航和输入区不被 safe-area/键盘区域污染。

### Step 5 - 修复后回归

最小回归命令：

```bash
cd frontend
pnpm test -- --run src/lib/themeContrast.test.ts
pnpm tsc --noEmit
pnpm build
```

如果改动涉及具体组件测试，额外跑对应测试，例如：

```bash
pnpm test -- --run src/components/chat/MessageBubble.test.tsx
pnpm test -- --run src/components/artifact/WorkspaceCodePreview.test.tsx
pnpm test -- --run src/components/blocks/ToolCallBlock.test.tsx
```

---

## 7. 浏览器验收矩阵

每次报告至少覆盖以下组合：

| Theme | Viewport | 路由 |
|---|---|---|
| light | 1440x900 | `/chat/:conversationId` |
| light | 390x844 | `/chat/:conversationId` |
| light | 1440x900 | `/agents` |
| light | 1440x900 | `/archive` |
| dark | 1440x900 | `/chat/:conversationId` |
| dark | 390x844 | `/chat/:conversationId` |
| dark | 1440x900 | `/agents` |
| dark | 1440x900 | `/archive` |

如果没有真实会话数据，使用 mock/demo route 或创建本地会话，但报告必须说明数据来源。

验收时建议在控制台确认：

```js
document.documentElement.dataset.theme
document.documentElement.classList.contains('dark')
```

---

## 8. 失败分类

| 类型 | 表现 | 处理方式 |
|---|---|---|
| Token mismatch | 全局浅色 override 导致局部反色 | 用局部显式 light/dark class 或补 token |
| Hardcoded foreground | `text-white` / hex 固定 | 改为 theme-aware class |
| Transparent surface | 背景透出导致字发灰 | 提升 surface 不透明度或改文字色 |
| State regression | hover/selected 后不可读 | 补对应 state class |
| Syntax theme mismatch | 代码高亮颜色和容器冲突 | 按 resolved theme 切换 Shiki theme |
| Mobile safe-area | 底部/顶部文字贴边或叠层 | 补 safe-area padding 和背景 |
| Disabled too faint | 禁用态几乎不可见 | 保留低强调但可辨认 |

---

## 9. 报告模板

最终回复或 PR 描述中使用：

```markdown
## Foreground / Contrast Audit

### Scope
- Modules:
- Components:
- Themes: light / dark
- Viewports:

### Changes
- 

### Automated Checks
- `pnpm test -- --run src/lib/themeContrast.test.ts`: pass/fail
- `pnpm tsc --noEmit`: pass/fail
- `pnpm build`: pass/fail

### Browser Checks
| Theme | Viewport | Route | Result | Notes |
|---|---|---|---|---|
| light | 1440x900 | /chat/... | pass | |
| light | 390x844 | /chat/... | pass | |
| dark | 1440x900 | /chat/... | pass | |
| dark | 390x844 | /chat/... | pass | |

### Residual Risk
- 
```

---

## 10. 完成标准

- 深色模式和浅色模式都通过核心页面核对。
- 每个受影响模块和同类组件都被检查，不只修截图里的一处。
- 核心 token contrast 单测通过。
- 没有新增硬编码不可迁移颜色。
- 没有引入页面级横向溢出。
- 前端类型检查和构建通过。
- 修复记录写入最终回复、PR 描述或 `docs/frontend/changelog.md`。

