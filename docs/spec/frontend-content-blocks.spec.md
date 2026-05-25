# Frontend Content Blocks Spec

## 目标

打磨 AgentHub 聊天流中的富媒体消息块，让代码、Diff、网页预览和文件内容具备可演示的产品质感。

## 输入 / 输出

输入：

- `text`、`code`、`diff`、`web_preview`、`file` 类型的 ContentBlock。
- 前端 Demo 扩展块：`task_card`、`agent_switch`。
- 未知 block 类型。

输出：

- `CodeBlock` 展示语言标签、复制按钮和高亮代码。
- `DiffBlock` 使用 unified 风格展示新增、删除和上下文行。
- `WebPreviewBlock` 展示标题、描述、URL 和外链入口。
- `FileBlock` 展示文件类型、文件名、大小和打开入口。
- 未知 block 使用降级 UI，不能让消息流崩溃。

## 边界 / 错误处理

- 本阶段不修改 `shared/openapi.yaml`。
- 高亮失败时退回纯文本代码展示。
- Clipboard 不可用或复制失败时不能影响消息渲染。
- 文件和网页链接必须使用安全的外链属性。

## 性能要求

- 代码高亮异步执行，不能阻塞初始消息渲染。
- Diff 行渲染适合 Demo 规模，不处理超大文件虚拟滚动。
- 固定头部、按钮和行号尺寸，避免流式内容导致布局明显跳动。

## 依赖

- `frontend/src/components/blocks/CodeBlock.tsx`
- `frontend/src/components/blocks/DiffBlock.tsx`
- `frontend/src/components/blocks/WebPreviewBlock.tsx`
- `frontend/src/components/blocks/FileBlock.tsx`
- `frontend/src/components/blocks/UnknownBlock.tsx`
- `frontend/src/components/blocks/ContentRenderer.tsx`

## 验收标准

- Demo 消息中可以看到 code、diff、web_preview、file 的正式样式。
- CodeBlock 复制按钮可点击，复制成功有状态反馈。
- DiffBlock 能区分新增、删除和上下文行。
- WebPreviewBlock 与 FileBlock 在深色主题下可读。
- 未知 block 有降级展示。
- `tsc`、`eslint`、`vite build` 通过。
