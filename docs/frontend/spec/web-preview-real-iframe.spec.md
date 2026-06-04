# Web Preview Real Iframe Spec

> Owner: F
> Scope: `frontend/**`
> Status: Implemented
> Last updated: 2026-06-04

## 1. 背景

当前聊天消息中的 `web_preview` block 会展示平台返回的 preview URL，例如：

```text
http://111.229.151.159:8082/index.html
```

但点击“预览网页”后，弹窗并没有加载该 URL 指向的真实 workspace 文件，而是前端在 `WebPreviewBlock` 内部绘制了一套固定的模拟页面：

- 标题：`Workspace preview: index.html`
- 文案：`AgentHub platform-managed static preview.`
- 卡片：`Chat Shell / Agent Flow / Rich Blocks`

这会造成用户误判：看起来像打开了预览，实际看到的不是 agent 生成的 `index.html` 内容。

## 2. 根因

相关文件：

- `frontend/src/components/blocks/WebPreviewBlock.tsx`
- `frontend/src/components/blocks/ContentRenderer.tsx`
- `frontend/src/components/blocks/WebPreviewBlock.test.tsx`

当前 `WebPreviewBlock` 的 modal 内容使用静态 JSX 模拟浏览器窗口，只把 `url` 展示在地址栏文字里，没有使用：

```tsx
<iframe src={url} />
```

因此即使后端 `web_preview.url` 正确，前端也不会真实加载 workspace preview service 输出的 HTML。

## 3. 目标

把 `web_preview` 弹窗从“模拟预览”改成“真实 URL 预览”：

- 点击预览后，在弹窗中通过 iframe 加载 `block.url`。
- 地址栏显示真实 URL。
- iframe 加载成功时，用户看到真实 workspace 文件内容。
- iframe 加载失败时，展示明确失败态和“新窗口打开”入口。
- 保留外链打开按钮，便于绕过 iframe 限制。
- 不修改 OpenAPI，不新增后端接口作为第一步。

## 4. 非目标

本阶段不做：

- 不在前端重写 preview server。
- 不直接读取 workspace 文件再自己拼 iframe HTML。
- 不把 `previewTitle / previewBody` 当真实预览内容。
- 不修改 `.agenthub/manifest.json` 或直接读取隐藏文件。
- 不要求前端启动或停止 preview service。
- 不实现浏览器级质量验收；验收仍由后端 `verify_web_preview` 负责。

## 5. 用户体验方案

### 5.1 卡片态

消息流中的卡片仍保持轻量：

```text
┌────────────────────────────────────┐
│ 111.229.151.159                    │
│ Workspace preview: index.html       │
│ AgentHub platform-managed static... │
│ http://111.229.151.159:8082/...     │
└────────────────────────────────────┘
```

保留两个操作：

- 预览网页：打开 modal。
- 打开外链：新窗口打开 URL。

### 5.2 Modal 真实预览

弹窗结构调整为：

```text
┌──────────────────────────────────────────────┐
│ Workspace preview: index.html        关闭    │
│ http://111.229.151.159:8082/index.html       │
├──────────────────────────────────────────────┤
│ ● ● ●  http://111.229.151.159:8082/index... │
├──────────────────────────────────────────────┤
│ iframe: 真实加载 url                         │
│                                              │
└──────────────────────────────────────────────┘
```

要求：

- iframe 区域填满 modal 主体。
- modal 默认宽度比当前更适合网页预览：
  - desktop：`max-w-[min(1280px,calc(100vw-2rem))]`
  - 高度：`min(86vh, 100dvh)`
- iframe 背景为白色，避免网页透明背景在深色 modal 上变脏。
- 预览页面内部滚动交给 iframe。
- 弹窗外层不再出现大面积假内容。

### 5.3 加载态

打开 modal 后：

- 先显示“正在加载真实预览…”。
- iframe `onLoad` 触发后隐藏加载态。
- 加载态最多不影响 iframe 渲染；即使 `onLoad` 不稳定，iframe 仍应挂载。

### 5.4 失败态

iframe 常见失败原因：

- preview URL 不可访问。
- HTTP preview 被 HTTPS 前端页面阻止 mixed content。
- preview service 返回 `X-Frame-Options` 或 CSP `frame-ancestors` 禁止嵌入。
- 跨域页面自身 JS/CSS 资源失败。

前端不能完全判断所有失败类型，但需要提供可理解的降级：

- 显示提示：

```text
如果预览区域为空白，可能是浏览器阻止了嵌入预览。
请点击“新窗口打开”查看真实页面。
```

- 保留 `打开外链` 按钮。
- 如果 iframe `onError` 触发，展示错误态文案。

## 6. 技术方案

### 6.1 修改 WebPreviewBlock

文件：

- `frontend/src/components/blocks/WebPreviewBlock.tsx`

建议新增状态：

```ts
const [previewOpen, setPreviewOpen] = useState(false);
const [iframeLoaded, setIframeLoaded] = useState(false);
const [iframeErrored, setIframeErrored] = useState(false);
```

打开弹窗时重置：

```ts
function openPreview() {
  setIframeLoaded(false);
  setIframeErrored(false);
  setPreviewOpen(true);
}
```

替换当前假内容区域为：

```tsx
<iframe
  title={title ?? 'Workspace preview'}
  src={url}
  className="h-full w-full border-0 bg-white"
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
  referrerPolicy="no-referrer"
  onLoad={() => setIframeLoaded(true)}
  onError={() => setIframeErrored(true)}
/>
```

说明：

- `allow-scripts`：agent 生成的前端 demo 需要运行 JS。
- `allow-same-origin`：保留页面自身资源访问和 local behavior。
- `allow-forms`：允许 demo 中的表单交互。
- `allow-popups` / `allow-downloads`：支持 demo 中的外链和下载场景。
- 不加 `allow-top-navigation`，避免预览页面跳转宿主应用。

### 6.2 URL 安全

`web_preview.url` 来自后端平台 preview service，但前端仍应做最小校验。

允许：

- `http://`
- `https://`

不允许 iframe 加载：

- `javascript:`
- `data:`
- `blob:`（本阶段不需要）
- 空字符串或非法 URL

非法 URL 展示降级卡片：

```text
预览 URL 不合法，无法嵌入展示。
```

外链按钮也应避免打开非法 URL。

建议新增 helper：

```ts
function isPreviewUrlAllowed(url: string): boolean
```

### 6.3 保留 previewTitle / previewBody 的用途

`previewTitle` / `previewBody` 只能作为卡片摘要或 iframe 失败态的补充说明，不能作为真实预览主体。

推荐：

- 卡片标题仍使用 `title ?? previewTitle ?? url`。
- 卡片描述仍使用 `description ?? previewBody`。
- modal 主体只使用 iframe。

### 6.4 测试

更新：

- `frontend/src/components/blocks/WebPreviewBlock.test.tsx`

新增/调整测试：

1. 打开 modal 后渲染 iframe：

```ts
expect(screen.getByTitle('Demo Website')).toHaveAttribute('src', 'https://example.com/demo');
```

2. 不再渲染假内容：

```ts
expect(screen.queryByText('Chat Shell')).not.toBeInTheDocument();
expect(screen.queryByText('Agent Flow')).not.toBeInTheDocument();
expect(screen.queryByText('Rich Blocks')).not.toBeInTheDocument();
```

3. iframe sandbox 存在：

```ts
expect(iframe).toHaveAttribute('sandbox', expect.stringContaining('allow-scripts'));
```

4. 非法 URL 降级：

```ts
render(<WebPreviewBlock url="javascript:alert(1)" title="Bad" />);
fireEvent.click(screen.getByTitle('预览网页'));
expect(screen.getByText(/预览 URL 不合法/)).toBeInTheDocument();
```

5. 外链属性保留：

```ts
target="_blank"
rel="noreferrer"
```

## 7. 是否需要后端修改

### 7.1 第一阶段：不需要后端修改

只要 `web_preview.url` 已经能在浏览器地址栏直接打开，前端改 iframe 后就能真实预览。

当前截图中的 URL：

```text
http://111.229.151.159:8082/index.html
```

如果当前前端页面也是 HTTP，本阶段前端修复后应能直接 iframe 加载。

### 7.2 可能需要 B1 后端配合的情况

如果前端部署为 HTTPS，而 preview URL 是 HTTP，浏览器会阻止 mixed content。此时需要 B1/平台层提供一种 HTTPS 或同源预览入口。

建议后端方案二选一：

1. 给 preview service 配 HTTPS 域名：

```text
https://preview.agenthub.example.com/{conversation_id}/index.html
```

2. 通过主 API 域名提供同源反向代理：

```text
https://agenthub.example.com/api/v1/workspaces/{conversation_id}/preview/proxy/index.html
```

要求：

- 代理必须只允许当前用户访问自己的 conversation workspace。
- 代理必须做 path traversal 防护。
- HTML/CSS/JS/image 等静态资源路径需要能正确解析。

### 7.3 可能需要 B2 后端配合的情况

B2 只负责生成和传递 `web_preview` block，不负责前端 iframe。

如果发现 `web_preview.url` 不是平台 preview service 生成，而是 Agent 文本里编造的 URL，需要 B2/Orchestrator 保持当前约束：

- `web_preview.url` 必须来自平台 `start_workspace_preview`。
- Agent 自己输出的普通 URL 不能伪装成平台 preview。

## 8. 验收标准

### 8.1 本地组件验收

- `WebPreviewBlock` 打开后有 iframe。
- iframe `src` 等于 block.url。
- modal 中不再出现 `Chat Shell / Agent Flow / Rich Blocks` 假卡片。
- 非法 URL 不会进入 iframe。
- `pnpm vitest run src/components/blocks/WebPreviewBlock.test.tsx` 通过。
- `pnpm tsc --noEmit` 通过。
- `pnpm lint` 通过。

### 8.2 真实 API 验收

使用已有会话或新会话生成 `web_preview` block：

1. 聊天流中出现 preview 卡片。
2. 点击预览。
3. modal 中 iframe 显示真实 `index.html` 内容。
4. 页面中的按钮、主题切换、基础 JS 交互可点击。
5. 点击“打开外链”能在新窗口打开同一真实 URL。
6. 如果 iframe 空白，外链仍可打开，并记录是否为 mixed content / CSP / X-Frame-Options。

### 8.3 回归范围

需要确认不影响：

- `text` Markdown 渲染。
- `file` preview。
- Workspace 右侧 `ArtifactPreview`。
- Deployment status card。
- 移动端 sheet 打开工作台。

## 9. 后续增强

可选增强，不纳入本阶段：

- modal 顶部增加刷新 iframe 按钮。
- 增加 viewport 切换：desktop / tablet / mobile。
- 增加 iframe 截图或 verify report 链接。
- 当 preview API 状态为 stopped/error 时，前端自动提示重新启动 preview。
- 将 preview URL 与 Workspace 当前选中文件关联，支持“预览当前 HTML 文件”。
