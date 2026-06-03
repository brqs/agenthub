# Artifact Parser v2 Spec

## 目标

B2-07 的目标是在不新增 ContentBlock 类型、不修改 OpenAPI、不修改 `StreamChunk` 字段的前提下，增强 `StreamingArtifactParser` 对富媒体产物的识别能力：

- 继续稳定输出 `text` 和 `code` block。
- 将 fenced diff/patch 内容识别为既有 `diff` block。
- 将独立 URL 行识别为既有 `web_preview` block。
- 让 B1 SSE 持久化层能保存 `diff` / `web_preview` block，而不是丢失或降级成空内容。

## 输入 / 输出

输入：

- LLM 流式文本 delta。
- Markdown fenced code block，例如 ```` ```python ````、```` ```diff ````。
- 独立 URL 行，例如 `https://github.com/brqs/agenthub/pull/17`。

输出：

- `StreamChunk(event_type="block_start", block_type="text" | "code" | "diff" | "web_preview" | "file")`
- `StreamChunk(event_type="delta", text_delta=... | code_delta=...)`
- `StreamChunk(event_type="block_end")`
- SSE 持久化后的 `Message.content` 中包含合法 ContentBlock：
  - `TextBlock`
  - `CodeBlock`
  - `DiffBlock`
  - `WebPreviewBlock`
  - `FileBlock`

## 行为规则

### 代码块

- 非 diff 语言继续输出 `code` block。
- language tag 仍只取第一段 token。
- 未闭合 code fence 在 `flush()` 时仍应收尾为合法 block。

### Diff 块

当 fenced code language 为以下值时，parser 应将其识别为 `diff`：

- `diff`
- `patch`
- `udiff`

Diff block 应满足：

- `block_type="diff"`。
- `metadata.filename` 尽量从 diff header 中提取。
- 如果无法提取 filename，使用稳定 fallback，例如 `changes.diff`。
- `delta` 可以继续使用 `text_delta` 承载 raw unified diff 内容。
- 持久化层负责将 raw diff 转换为 `DiffBlock(filename, before, after)`。

Diff 解析规则：

- 忽略 `diff --git`、`index`、`@@` 等结构行。
- `--- a/file` / `+++ b/file` 只用于 filename 推断，不进入 before/after 正文。
- 以 `-` 开头且不是 `---` 的行进入 `before`。
- 以 `+` 开头且不是 `+++` 的行进入 `after`。
- 以空格开头的 context 行同时进入 `before` 和 `after`。
- 解析失败时不抛异常，应降级为一个可读 diff block。

### Web Preview 块

当文本中的某一行只包含一个 `http://` 或 `https://` URL 时，parser 应将其识别为 `web_preview` block。

Web preview block 应满足：

- `block_type="web_preview"`。
- `metadata.url` 为标准化后的 URL。
- 不发起网络请求，不抓取网页标题，不做 OpenGraph 解析。
- `title`、`description`、`thumbnail_url` 可以为空。
- 行内 URL 不应被拆成 `web_preview`，继续作为普通 text。
- 非 http/https scheme 不识别，例如 `file://`、`javascript:`。

## 边界 / 错误处理

- 不修改 `BaseAgentAdapter.stream()` 签名。
- 不修改 `StreamChunk` schema。
- 不修改 `backend/app/schemas/message.py`。
- 不修改 `shared/openapi.yaml`。
- 不修改前端。
- 不引入第三方依赖。
- Parser 不做任何网络 I/O。
- 对 malformed diff、奇怪 URL、跨 chunk 的 code fence 和 URL 行必须保持稳定，不允许抛异常中断 adapter stream。

## 持久化要求

`backend/app/api/v1/stream.py` 的 `_ContentAccumulator` 当前至少支持 `text` / `code`。B2-07 需要最小扩展：

- `diff` block：累计 raw diff text，`block_end` 时转换为 `{"type": "diff", "filename": ..., "before": ..., "after": ...}`。
- `web_preview` block：根据 metadata 持久化为 `{"type": "web_preview", "url": ..., "title": ..., "description": ..., "thumbnail_url": ...}`，空值字段可以省略或保留为 `None`，但必须符合 Pydantic schema。

## 验收标准

- 既有 `test_artifact_parser.py` 全部通过。
- 新增 parser 测试覆盖：
  - diff fence 输出 `diff` block。
  - patch/udiff fence 输出 `diff` block。
  - 普通 code fence 仍输出 `code` block。
  - 独立 URL 行输出 `web_preview` block。
  - 行内 URL 保持 text。
  - URL 或 diff fence 跨 chunk 时仍稳定。
- 新增 SSE/accumulator 测试覆盖：
  - diff block 最终持久化为合法 `DiffBlock`。
  - web_preview block 最终持久化为合法 `WebPreviewBlock`。
- `ruff` 通过。
- 相关 pytest 通过。
