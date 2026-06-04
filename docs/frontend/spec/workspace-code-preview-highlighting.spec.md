# Workspace Code Preview Highlighting Spec

> Owner: F
> Scope: `frontend/**`
> Status: Draft
> Last updated: 2026-06-04

## 1. 目标

优化 Workspace 右侧文件预览中的代码阅读体验，让 `app.js`、`styles.css`、`index.html`、`README.md` 等文本文件从“普通等宽文本框”升级为更接近代码编辑器的预览界面。

本 spec 聚焦截图中红框区域：`ArtifactPreview` 的非编辑状态代码预览。

目标不是引入完整 IDE，而是在不显著增加复杂度的前提下做到：

- 代码有语法高亮，深浅主题都清晰可读。
- 预览区域层级更轻、更像代码窗口。
- 支持行号、语言标签、复制、自动换行切换等基础阅读能力。
- 编辑模式仍保留轻量 textarea，不阻塞保存能力。
- 大文件和高亮失败时有稳定降级。

## 2. 当前状态

相关文件：

- `frontend/src/components/artifact/ArtifactPreview.tsx`
- `frontend/src/components/blocks/SyntaxHighlightedCode.tsx`
- `frontend/src/components/blocks/CodeBlock.tsx`
- `frontend/src/components/blocks/WorkflowBlock.tsx`
- `frontend/src/components/blocks/ToolCallBlock.tsx`

当前实现：

- 聊天消息中的 `CodeBlock`、`WorkflowBlock`、`ToolCallBlock` 已复用 `SyntaxHighlightedCode`。
- `SyntaxHighlightedCode` 已基于 Shiki，内置 `github-dark` / `github-light`。
- Workspace 的 `ArtifactPreview` 在非编辑状态下仍使用：

```tsx
<pre className="...">{draft}</pre>
```

- 编辑模式使用 textarea，能保存 workspace 文本文件。
- 全屏预览复用同一份 `ArtifactContent`。

当前问题：

- 代码无语法高亮，视觉上和普通日志/纯文本没有差异。
- 右侧 Workspace 面板宽度有限，大段 JS/CSS 阅读压力大。
- 缺少行号，用户难以定位讨论中的具体片段。
- 文件头展示了 mime type，但预览正文没有语言语义。
- 预览和编辑模式视觉差异不够明确。
- 浅色模式下代码区域偏“白纸”，缺少代码容器质感。

## 3. 非目标

本阶段不做：

- Monaco / CodeMirror 等完整编辑器引入。
- 多光标、搜索替换、格式化、跳转定义。
- diff review、inline comment、版本历史。
- 后端 API 或 OpenAPI 契约改动。
- 直接读取 `.agenthub/artifacts.json`。

这些能力可作为后续 Workspace IDE 化阶段单独设计。

## 4. 用户体验方案

### 4.1 预览模式

文本代码文件默认展示为代码预览卡：

- 顶部仍使用现有 `ArtifactHeader`：文件名、mime type、大小、修改、全屏。
- 代码正文使用“代码面板”视觉：
  - subtle 背景色。
  - 左侧行号列。
  - 语法高亮正文。
  - 横向滚动默认开启。
  - 可选“自动换行”切换。

建议 UI：

```text
┌────────────────────────────────────┐
│ app.js        text/javascript 12KB  │
├────────────────────────────────────┤
│  1 │ const app = ...               │
│  2 │ function resizeStars() {      │
│  3 │   ...                         │
└────────────────────────────────────┘
```

### 4.2 编辑模式

点击“修改”后进入编辑模式：

- 保留 textarea，优先保证稳定保存。
- textarea 视觉与代码预览对齐：
  - 同样的 font、line-height、背景。
  - 不强制语法高亮。
  - 可选后续增强为 overlay highlighting，但不作为本阶段目标。

原因：

- textarea 简单、可靠、移动端兼容更好。
- 语法高亮编辑器会带来选区、IME、软键盘、滚动同步等额外风险。

### 4.3 全屏模式

全屏预览应明显提升代码阅读能力：

- 使用更大的可视高度：`flex-1 min-h-0`。
- 代码区域填满剩余空间。
- 行号列保持对齐。
- 自动换行状态与普通预览共享。
- Escape 保持关闭全屏。

### 4.4 文件类型展示策略

按 `mime_type` 和 `name/path` 推断语言：

| 文件 | 语言 |
|------|------|
| `.js`, `.mjs`, `.cjs` | `javascript` |
| `.ts` | `typescript` |
| `.tsx` | `tsx` |
| `.css` | `css` |
| `.html`, `.htm` | `html` |
| `.json` | `json` |
| `.md`, `.markdown` | `markdown` |
| `.yaml`, `.yml` | `yaml` |
| `.sh`, `.bash` | `bash` |
| unknown text | `markdown` 或 `text` fallback |

## 5. 技术方案

### 5.1 复用高亮核心

优先复用：

- `frontend/src/components/blocks/SyntaxHighlightedCode.tsx`

建议增强 `SyntaxHighlightedCode` 支持 Workspace 场景需要的能力：

```ts
interface SyntaxHighlightedCodeProps {
  code: string;
  language: string;
  className?: string;
  fallbackClassName?: string;
  showLineNumbers?: boolean;
  wrapLines?: boolean;
  maxHeightClassName?: string;
}
```

兼容要求：

- 现有 `CodeBlock`、`WorkflowBlock`、`ToolCallBlock` 不需要重写。
- 新 props 都有默认值，避免影响聊天消息。

### 5.2 新增 WorkspaceCodePreview 组件

建议新增：

- `frontend/src/components/artifact/WorkspaceCodePreview.tsx`
- `frontend/src/components/artifact/WorkspaceCodePreview.test.tsx`

职责：

- 接收 `artifact.name`、`artifact.mime_type`、`draft`。
- 推断 language。
- 渲染代码面板、行号、自动换行开关。
- 使用 `SyntaxHighlightedCode` 输出高亮 HTML。
- 高亮失败时展示纯文本 fallback。

建议接口：

```ts
interface WorkspaceCodePreviewProps {
  filename: string;
  mimeType: string;
  code: string;
  isFullscreen?: boolean;
}
```

### 5.3 ArtifactPreview 接入

修改点：

- `frontend/src/components/artifact/ArtifactPreview.tsx`

当前：

```tsx
if (typeof artifact.content === "string" && isTextMime(artifact.mime_type)) {
  return <pre>{draft}</pre>;
}
```

目标：

```tsx
if (typeof artifact.content === "string" && isTextMime(artifact.mime_type)) {
  return (
    <WorkspaceCodePreview
      filename={artifact.name}
      mimeType={artifact.mime_type}
      code={draft}
      isFullscreen={isFullscreen}
    />
  );
}
```

注意：

- `ArtifactContent` 当前不知道 `isFullscreen`，需要从 `ArtifactPreview` 传入。
- 编辑模式 textarea 仍留在 `ArtifactContent` 内。

### 5.4 语言推断工具

建议新增纯函数：

- `frontend/src/components/artifact/workspaceCodeLanguage.ts`
- `frontend/src/components/artifact/workspaceCodeLanguage.test.ts`

接口：

```ts
export function inferWorkspaceCodeLanguage(filename: string, mimeType: string): string;
```

映射优先级：

1. 文件扩展名。
2. MIME type。
3. fallback：`markdown`。

示例：

```ts
inferWorkspaceCodeLanguage("app.js", "text/javascript") === "javascript";
inferWorkspaceCodeLanguage("styles.css", "text/css") === "css";
inferWorkspaceCodeLanguage("index.html", "text/html") === "html";
inferWorkspaceCodeLanguage("README.md", "text/markdown") === "markdown";
```

## 6. 视觉规范

### 6.1 容器

普通预览：

- `max-h-[36rem]`
- `overflow-auto`
- `border-t border-slate-200 dark:border-slate-800`
- light: `bg-slate-50`
- dark: `bg-slate-950`

全屏预览：

- `h-full`
- `min-h-0`
- `overflow-auto`
- 代码正文尽量填满可用空间。

### 6.2 字体

统一使用：

- `font-mono`
- `text-xs`
- `leading-5`

可选优化：

- 行号使用 `tabular-nums`。
- 代码正文设置 `font-feature-settings: "liga" 0;`，避免符号连字影响复制认知。

### 6.3 行号

行号列：

- 宽度：`w-10` 或按行数自适应 `min-w-10`。
- 对齐：右对齐。
- 颜色：`text-slate-400 dark:text-slate-600`。
- 背景略深/浅于正文。
- `select-none`，复制代码时不复制行号。

### 6.4 自动换行

默认：

- 不换行，保留横向滚动，更符合代码预览。

切换后：

- 使用 `whitespace-pre-wrap break-words`。
- 行号仍按原始行数显示，不做视觉软换行行号重排。

按钮位置：

- 放在 ArtifactHeader 的次级按钮区域，或 WorkspaceCodePreview 顶部右侧。
- 文案：`换行` / `不换行`。

## 7. 主题策略

Shiki 主题：

- dark: `github-dark`
- light: `github-light`

依赖当前：

- `useUiStore((state) => state.theme)`

后续如果主题系统迁移为 `resolvedTheme`，`SyntaxHighlightedCode` 应切换到 resolved theme，避免 system 模式下取错。

高亮完成前 fallback：

- light: `text-slate-900 bg-slate-50`
- dark: `text-slate-300 bg-slate-950`

高亮完成后：

- 保持 Shiki 的 token 颜色。
- 覆盖 Shiki 默认背景为透明，避免和容器背景冲突。

## 8. 性能与降级

### 8.1 大文件策略

阈值建议：

- `<= 200 KB`：启用 Shiki 高亮。
- `> 200 KB`：默认纯文本预览，显示提示：
  - `文件较大，已使用纯文本模式以保证性能。`
- 后续可加入“仍然高亮”手动按钮。

原因：

- Workspace 文件可能由 Agent 生成，大小不可控。
- Shiki 对大文件高亮可能带来明显阻塞和内存压力。

### 8.2 高亮失败

失败时：

- 不显示错误 toast。
- fallback 到纯文本 `<pre>`。
- 可在 console/debug 环境记录，但生产不需要打断用户。

### 8.3 异步闪烁

要求：

- 首帧先展示纯文本 fallback。
- 高亮完成后替换为 tokenized HTML。
- 容器尺寸、字体、行高保持一致，减少跳动。

## 9. 可访问性

- 代码区域使用 `role="region"`，`aria-label="{filename} code preview"`。
- 自动换行按钮有明确 `aria-pressed`。
- 行号列 `aria-hidden="true"`。
- 全屏模式 Escape 可关闭。
- 代码正文保持可选择、可复制。
- 颜色对比在 light/dark 下满足可读性，不依赖单一颜色表达状态。

## 10. 测试计划

新增测试：

- `workspaceCodeLanguage.test.ts`
  - 覆盖 js/css/html/md/json/yaml/bash fallback。
- `WorkspaceCodePreview.test.tsx`
  - 渲染文件名语言对应的高亮容器。
  - 纯文本 fallback 可读。
  - 自动换行按钮切换 class / aria-pressed。
  - 大文件走纯文本模式并显示提示。
- `ArtifactPreview.test.tsx`
  - 文本文件非编辑态渲染 `WorkspaceCodePreview`。
  - 点击“修改”仍进入 textarea。
  - 全屏模式下代码预览仍可见。

回归测试：

- `CodeBlock.test.tsx`
- `ToolCallBlock.test.tsx`
- `WorkflowBlock.test.tsx`

验证命令：

```bash
cd frontend
pnpm vitest run src/components/artifact/WorkspaceCodePreview.test.tsx src/components/artifact/workspaceCodeLanguage.test.ts src/components/artifact/ArtifactPreview.test.tsx
pnpm tsc --noEmit
pnpm lint
```

## 11. 验收标准

- Workspace 中打开 `app.js` 时显示 JavaScript 高亮。
- 打开 `styles.css` 时显示 CSS 高亮。
- 打开 `index.html` 时显示 HTML 高亮。
- 打开 `README.md` 时显示 Markdown 高亮或良好的 Markdown/text fallback。
- 代码预览有行号，行号不参与文本复制。
- 预览模式与编辑模式视觉区分明确。
- 点击“修改”后仍能编辑并保存文本文件。
- 全屏模式下代码区域占满主空间，滚动自然。
- 深色和浅色主题下都无文字看不清问题。
- 大文件不明显卡顿，能降级为纯文本。
- `tsc`、`eslint`、相关 vitest 通过。

## 12. 实施顺序

建议分三步：

1. **Model / Utility**
   - 新增 `inferWorkspaceCodeLanguage`。
   - 补语言推断测试。

2. **Preview Component**
   - 增强 `SyntaxHighlightedCode` 可选行号 / wrap。
   - 新增 `WorkspaceCodePreview`。
   - 补组件测试。

3. **ArtifactPreview Integration**
   - `ArtifactContent` 接入 `WorkspaceCodePreview`。
   - 保持 textarea 编辑逻辑不变。
   - 跑回归测试并手动检查 Workspace 右侧预览。

## 13. 风险与取舍

| 风险 | 影响 | 缓解 |
|------|------|------|
| Shiki 高亮大文件卡顿 | Workspace 面板响应慢 | 大文件阈值降级 |
| 行号与自动换行不同步 | 视觉定位不精确 | 软换行时仍按原始行显示行号，文案可接受 |
| 编辑模式无高亮 | 与预览视觉不一致 | 本阶段优先保存稳定性，后续再评估 CodeMirror |
| 主题 store 后续重构 | 高亮主题取值可能变 | 封装 `resolvedTheme` getter 或 adapter |
| 测试环境 Shiki 慢 | 单测耗时上升 | mock `SyntaxHighlightedCode` 或 mock Shiki |

## 14. 后续增强

- 搜索当前文件。
- 一键复制全文。
- 行号点击复制 `path:line` 引用。
- mini map / 代码折叠。
- CodeMirror 只读模式替代 Shiki HTML。
- 编辑模式升级为 CodeMirror，并保留移动端 textarea fallback。
