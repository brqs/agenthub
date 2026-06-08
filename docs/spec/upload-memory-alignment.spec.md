# AgentHub Upload 与 Memory 对齐契约

> Status: Draft handoff spec  
> Last updated: 2026-06-08  
> Owners: B1 Upload + B2 Memory/Orchestrator + F Composer/Attachment UI  
> Scope: 让文件上传功能与现有消息记忆、会话压缩记忆、Orchestrator 结构化记忆、workspace 文档上下文稳定对齐。

## 0. 为什么需要这份契约

文件上传功能可以由独立 Agent/团队实现，但它不能只完成“文件能上传、能下载、能展示”。对 AgentHub 来说，上传文件最终要成为 Agent 可理解、可引用、可压缩、可追踪的上下文。

如果上传模块和记忆模块不约定边界，就会出现这种断层：

- 用户上传了图片或压缩包，聊天里能看到附件，但 Agent 不知道里面是什么。
- 当前轮能看到附件预览，但对话压缩后长期记忆里只剩“有个文件”，丢失关键要求。
- Orchestrator 调度子 Agent 时没有附件摘要，子 Agent 只能猜。
- workspace 导入后，记忆里不知道哪些文件来自用户上传，后续 review/repair 容易误判。

本 spec 的核心目标是定义一个中间契约：**AttachmentContext**。上传模块负责产出它，记忆模块负责消费它。

## 1. 当前系统已有基础

当前代码中已经存在以下基础能力：

- `uploads` 表：保存上传文件元数据、owner、conversation、purpose、size、sha256、storage key、preview。
- `message_attachments` 表：保存 message 与 upload 的绑定关系。
- `AttachmentBlock`：消息内容块中已有 `type="attachment"`。
- `POST /api/v1/uploads`、`GET /api/v1/uploads/{id}`、`GET /api/v1/uploads/{id}/download`、`DELETE /api/v1/uploads/{id}`。
- `SendMessageRequest` / `QueueMessageRequest` 已有 `attachment_ids`。
- 前端 `MessageInput` 已有选择、拖拽、粘贴图片、上传队列、附件 chip 的雏形。

但当前记忆链路还没有完整消费附件内容：

- `blocks_to_text()` 暂时没有稳定处理 `attachment` block。
- 会话压缩摘要不会自动保留附件的可读内容。
- Orchestrator 结构化 memory 主要记录 run/task/attempt/event，不会自动提取上传文件语义。
- workspace docs 只有在显式写入时才会成为项目记忆。

因此上传模块实现时必须主动产出记忆可用的摘要结构，而不是只落文件元数据。

## 2. 设计原则

1. **附件不是装饰，是上下文输入。**  
   每个被发送的附件都必须能被转成 Agent 可读的最小事实。

2. **UI 展示块和记忆上下文分离。**  
   `AttachmentBlock` 面向用户展示；`AttachmentContext` 面向模型、压缩器和 Orchestrator。不要把大段 extracted text 直接塞进聊天 UI block。

3. **上传不等于 workspace side effect。**  
   用户上传压缩包时，默认只是 message attachment。只有用户明确导入 workspace，才解压/复制进 workspace。

4. **记忆只消费安全、可诊断的内容。**  
   被 safety block、解析失败或未完成处理的附件，只能作为元数据进入上下文，不得伪装成已读内容。

5. **大文件必须分层摘要。**  
   附件上下文应优先提供 summary、manifest、preview、chunk refs，而不是把全文塞入消息历史。

6. **当前会话优先。**  
   附件默认只属于当前 conversation；除非用户显式加入 Agent knowledge 或项目文档，否则不进入跨会话长期记忆。

## 3. 上传模块必须交付的契约

### 3.1 Upload 元数据

每个上传文件必须至少持久化：

```ts
type Upload = {
  id: string;
  owner_user_id: string;
  conversation_id?: string | null;
  purpose:
    | "message_attachment"
    | "workspace_file"
    | "workspace_import"
    | "agent_knowledge"
    | "agent_icon"
    | "skill_package"
    | "mcp_config";
  filename: string;
  content_type: string;
  detected_content_type?: string | null;
  size_bytes: number;
  sha256: string;
  storage_key: string;
  status: "processing" | "ready" | "failed" | "deleted";
  safety_status: "pending" | "passed" | "blocked" | "manual_review_required";
  preview?: AttachmentPreview | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};
```

上传模块不得依赖文件名扩展名作为唯一事实。`content_type`、mime sniff、sha256 都要参与判断。

### 3.2 AttachmentBlock 展示契约

发送消息时，后端应把 `attachment_ids` 转成轻量 `AttachmentBlock`：

```ts
type AttachmentBlock = {
  type: "attachment";
  upload_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  purpose: string;
  safety_status: string;
  preview?: AttachmentPreview | null;
  context_status?: "pending" | "ready" | "failed" | "blocked";
  context_summary?: string | null;
};
```

说明：

- `preview` 给前端展示用。
- `context_summary` 只能是短摘要，建议不超过 500 字符。
- 全文、OCR、压缩包完整 manifest 不应直接塞进 `AttachmentBlock`。
- `context_status` 用来告诉记忆模块这份附件是否已有可消费上下文。

### 3.3 AttachmentContext 记忆契约

上传模块需要为每个 ready 附件尽量产出标准化上下文：

```ts
type AttachmentContext = {
  upload_id: string;
  conversation_id?: string | null;
  filename: string;
  content_type: string;
  detected_content_type?: string | null;
  size_bytes: number;
  sha256: string;
  purpose: string;
  safety_status: "passed" | "blocked" | "manual_review_required" | "pending";
  context_status: "ready" | "partial" | "failed" | "blocked" | "unsupported";
  kind: "image" | "archive" | "document" | "text" | "code" | "spreadsheet" | "audio" | "video" | "unknown";
  summary: string;
  text_preview?: string | null;
  extracted_text_ref?: string | null;
  extracted_text_token_estimate?: number | null;
  image_caption?: string | null;
  ocr_text?: string | null;
  archive_entries_preview?: string[];
  archive_total_entries?: number | null;
  imported_workspace_paths?: string[];
  structured_facts?: string[];
  parser_version: string;
  created_at: string;
  updated_at: string;
};
```

推荐持久化方式：

- MVP 可以存到 `uploads.preview.context` 或 `uploads.preview.memory_context`。
- 更稳的后续版本建议新增 `upload_contexts` 表，避免 UI preview 和 memory context 混在一起。

建议表结构：

```text
upload_contexts
  upload_id primary key references uploads(id)
  conversation_id nullable
  kind
  context_status
  summary text
  text_preview text nullable
  extracted_text_storage_key nullable
  extracted_text_token_estimate integer nullable
  structured_facts jsonb
  metadata jsonb
  parser_version
  created_at
  updated_at
```

### 3.4 各文件类型的最小上下文要求

#### 文本 / Markdown / JSON / CSV / 代码

上传模块应产出：

- `summary`
- `text_preview`
- `extracted_text_ref`，如果全文超过 preview 限制
- `structured_facts`，例如标题、字段名、主要函数名、显式需求

示例：

```text
[Attachment: requirements.md]
kind=document
summary=用户上传了一份需求说明，主要要求实现移动端登录页、短信验证码、暗色主题。
preview=...
```

#### 图片

上传模块应产出：

- 基础元数据：尺寸、格式、大小
- `image_caption`，如果有多模态/OCR 服务
- `ocr_text`，如果图片包含文字
- 如果暂时没有图片理解能力，也必须产出清晰 summary：`Image attachment uploaded; no caption available yet.`

图片不能只用文件名进入记忆，否则 Agent 很难基于 UI 草图或截图工作。

#### PDF / Word / PPT / Excel

上传模块应产出：

- `summary`
- 前几页/前几个 sheet 的 `text_preview`
- 页数、sheet 名、slide 数等结构信息
- 解析失败时的 `context_status="failed"` 和明确错误码

#### 压缩包

上传模块默认只做安全 inspection，不自动导入 workspace。

应产出：

- `archive_entries_preview`
- `archive_total_entries`
- 总解压大小估计，如果能获得
- 是否存在可疑路径：`../`、绝对路径、Windows drive letter
- 是否包含常见项目入口：`package.json`、`pyproject.toml`、`index.html`、`README.md`

只有用户明确选择“导入 workspace”，才执行解压/复制。

#### 二进制未知文件

应产出：

- 文件名、类型、大小、sha256
- `context_status="unsupported"`
- 用户可见提示：可以下载/导入，但当前不能解析内容

## 4. 上传模块与消息发送的对齐流程

### 4.1 普通附件流程

```text
1. 用户选择文件
2. POST /api/v1/uploads
3. 后端保存 upload metadata
4. 后端生成 preview 和 AttachmentContext
5. 前端显示 upload chip
6. 用户发送消息，带 attachment_ids
7. send_message 校验 upload ready/safety
8. 用户消息 content = text blocks + attachment blocks
9. message_attachments 建立关系
10. Agent context builder / memory compressor 可通过 upload_id 读取 AttachmentContext
```

### 4.2 大文件异步解析流程

如果解析较慢：

```text
upload.status = ready
attachment.context_status = pending
background parser job starts
user can still send message
Agent receives metadata-only context first
parser finishes and writes AttachmentContext
future turns/compression can use full context
```

注意：

- 不要因为 OCR/PDF 解析慢阻塞发送消息。
- 但如果用户明确说“请读取这个 PDF”，而上下文还没 ready，Agent 应该说明正在解析或只能基于当前可用摘要回答。

### 4.3 workspace import 流程

```text
1. 用户上传 zip
2. 系统展示 archive preview
3. 用户明确选择导入 workspace
4. 后端安全解压到 conversation workspace
5. 写 imported_workspace_paths 到 AttachmentContext
6. workspace tree invalidate
7. Orchestrator 后续可以把这些 path 作为 workspace 文件事实使用
```

导入 workspace 是 side effect，必须显式确认。

## 5. 记忆模块需要进行的修改

### 5.1 在 blocks_to_text 中处理 attachment

当前 `blocks_to_text()` 应新增 `attachment` 分支。

目标输出不是“文件已上传”这种空事实，而是使用 AttachmentContext 形成可压缩文本：

```text
[Attachment: ui-reference.png]
upload_id=...
kind=image
summary=移动端个人中心截图，包含头像、订单入口、会员卡模块
ocr=我的订单、优惠券、设置
```

如果 AttachmentContext 不可用，则降级为：

```text
[Attachment: ui-reference.png]
kind=image
content_type=image/png
size=842 KB
context_status=pending
summary=Attachment uploaded; content summary is not available yet.
```

### 5.2 新增 AttachmentContextAdapter

建议新增后端服务：

```python
class AttachmentContextAdapter:
    async def context_for_upload(upload_id: UUID) -> AttachmentContext | None:
        ...

    async def context_for_message(message: Message) -> list[AttachmentContext]:
        ...

    def to_memory_text(context: AttachmentContext, budget: int) -> str:
        ...
```

职责：

- 读取 upload + upload_context。
- 生成模型可读文本。
- 控制 token/字符预算。
- 对 blocked/failed/pending 做安全降级。
- 不负责上传、下载、OCR、解压。

### 5.3 会话压缩记忆消费附件

`ContextCompressor` 在压缩消息时应能使用附件上下文。

建议实现方式：

1. 在压缩前批量读取消息里的 upload ids。
2. 构造 `attachment_context_by_upload_id`。
3. `message_to_text()` / `blocks_to_text()` 支持传入 resolver。
4. 摘要里保留附件相关关键事实，而不是只保留文件名。

压缩摘要中应保留：

- 用户上传了什么材料。
- 材料中的关键需求/约束。
- 附件是否导入 workspace。
- 导入后的 workspace path。
- 解析失败/无法读取的事实。

### 5.4 Orchestrator 上下文消费附件

Orchestrator planning 前的 history 构建应包含附件摘要。

规则：

- 当前用户消息附件必须进入 planner 上下文。
- 最近几轮附件可按预算进入上下文。
- 被导入 workspace 的附件应优先以 workspace path 形式表达。
- blocked 附件不得传给模型，只能显示“附件被安全策略阻止”。

Planner prompt 应明确：

```text
Use attachment summaries as user-provided context.
Do not claim to have read full attachment content unless the attachment context says it was extracted.
If an archive is uploaded but not imported, ask before modifying workspace from it.
```

### 5.5 Orchestrator 结构化 memory 记录附件事实

当某个 run 使用了附件，应在 `orchestrator_run_events` 里记录轻量事件：

```json
{
  "event_type": "attachment_context_used",
  "payload": {
    "upload_id": "...",
    "filename": "mockup.png",
    "kind": "image",
    "context_status": "ready",
    "summary": "..."
  }
}
```

当附件被导入 workspace，应记录：

```json
{
  "event_type": "workspace_imported_from_upload",
  "payload": {
    "upload_id": "...",
    "filename": "assets.zip",
    "imported_paths": ["assets/logo.png", "src/App.tsx"]
  }
}
```

这样用户之后问“我刚刚上传的那个包用了吗？”时，Orchestrator 可以基于结构化事实回答。

### 5.6 Workspace docs 记忆

附件内容不要自动写入 `CONTEXT.md`。

只有以下情况才写入 workspace 文档：

- 用户明确说“把这个记到项目文档/需求文档里”。
- `/grill-with-docs` 流程确认后写入。
- `/setup-matt-pocock-skills` 或自定义 Agent builder 明确把附件作为知识资料导入。

这能避免临时截图、错误文件、隐私文件被误写进项目长期文档。

## 6. 前端需要配合的点

前端上传 UI 应保证：

- 附件 chip 明确显示 `uploading / ready / failed / blocked / context pending`。
- 上传完成但解析未完成时，不要阻塞普通发送。
- 如果用户请求“分析这个附件”，而 `context_status=pending`，可以提示“附件仍在解析，Agent 可能先基于文件名和预览回答”。
- 图片展示缩略图，压缩包展示文件数量/部分目录，文本展示短 preview。
- 删除未发送附件时，应调用 delete 或至少从本地 pending list 移除。
- 已发送消息中的附件 block 可下载，但不能被误认为 workspace 文件。

移动端/原生壳注意：

- iOS/Android 大文件不要 base64 全量塞进 JS 内存。
- 原生 URI 应先复制到可读 cache，再流式 multipart 上传。
- Web/PWA 仍使用标准 file input、paste、drag-drop。

## 7. 安全边界

上传模块必须保证：

- 文件路径不信任原始 filename。
- 压缩包导入必须防 zip-slip。
- `.env`、密钥、token 等内容至少要进入 safety warning 或 secret scan backlog。
- blocked 文件不能进入模型上下文。
- download API 必须 owner 校验。
- workspace import 必须 conversation owner 校验。

记忆模块必须保证：

- 不把 blocked 附件内容写入 `conversation_memories`。
- 不把大文件全文塞入 summary prompt。
- 不声称读取了未解析附件。
- 不把附件内容提升为跨会话用户偏好，除非用户明确要求。

## 8. 测试要求

### 8.1 上传模块测试

- 上传文本文件后生成 ready upload、sha256、preview、AttachmentContext。
- 上传图片后生成 image preview；无 OCR 时也有 metadata-only context。
- 上传 zip 后只生成 archive preview，不自动导入 workspace。
- zip-slip archive 被拒绝或标记 blocked。
- 超大文件返回稳定错误码。
- 不属于当前 conversation 的 upload id 不能附加到消息。
- blocked upload 不能附加到消息。

### 8.2 记忆模块测试

- `blocks_to_text()` 能把 attachment block 转成含 summary 的文本。
- context pending 时输出 metadata fallback。
- blocked attachment 不输出敏感内容。
- conversation compression 后仍保留附件关键事实。
- Orchestrator planner history 包含当前用户消息附件摘要。
- 用户追问“刚刚上传的文件是什么”时能基于同 conversation 记录回答。
- workspace import 事件进入 Orchestrator structured memory。

### 8.3 集成 smoke

1. 上传一张 UI 截图，发送“按这张图做一个页面”。  
   期望：Agent 上下文包含 image caption/OCR 或 metadata fallback。

2. 上传 `requirements.md`，发送“根据这个需求做”。  
   期望：planner 能看到需求摘要，压缩后摘要仍保留关键要求。

3. 上传 zip，未导入 workspace，发送“帮我改里面的项目”。  
   期望：Orchestrator 先要求确认导入，不直接修改 workspace。

4. 上传 zip 并导入 workspace。  
   期望：workspace 出现文件，memory 记录 upload 与 imported paths 的关系。

5. 任务完成后问“你用了我刚才上传的哪个文件？”  
   期望：Orchestrator 基于 `attachment_context_used` 或 message attachment 事实回答。

## 9. 分阶段实现建议

### Phase 1: 上传即附件

- 完成 upload API、MessageInput、AttachmentBlock、message attachment link。
- `blocks_to_text()` 至少输出附件 metadata fallback。
- 文本类文件写入短 `context_summary`。

### Phase 2: 附件上下文解析

- 新增 `AttachmentContextAdapter`。
- 文本/Markdown/JSON/CSV/code 解析进入 memory。
- 图片 metadata + OCR/caption fallback。
- 压缩包 inspection。

### Phase 3: Orchestrator 深度消费

- planner/direct-answer/history status query 注入附件上下文。
- run events 记录 `attachment_context_used`。
- workspace import 记录 structured memory。

### Phase 4: 知识库与自定义 Agent

- 用户可以把附件提升为 Agent knowledge。
- 自定义 Agent builder 可引用上传文件作为知识材料、skill package 或 MCP config。
- 增加权限、版本、回滚和可见来源。

## 10. 上传模块给记忆模块的交付清单

上传负责人完成后，请在 PR 里确认：

- [ ] `AttachmentBlock` 字段稳定，OpenAPI/types 已更新。
- [ ] `attachment_ids` 能绑定到 user message。
- [ ] 每个 upload 有 owner/conversation/purpose/safety/status。
- [ ] ready upload 有 preview。
- [ ] 文本类 upload 有 `context_summary` 或 AttachmentContext。
- [ ] 解析失败有稳定 `error_code` / `context_status`。
- [ ] blocked upload 不会进入 message 或 memory。
- [ ] 压缩包不会自动导入 workspace。
- [ ] workspace import 能记录 imported paths。
- [ ] 测试覆盖 upload -> message -> memory text fallback。

## 11. 记忆模块后续 PR 清单

记忆负责人后续应完成：

- [ ] 新增 `AttachmentContextAdapter`。
- [ ] `blocks_to_text()` 支持 `attachment`。
- [ ] `ContextCompressor` 批量解析附件上下文。
- [ ] Orchestrator planning history 注入附件上下文。
- [ ] Orchestrator run events 记录附件使用和 workspace import。
- [ ] 压缩摘要保留附件关键事实。
- [ ] blocked/pending/failed 附件有安全降级。
- [ ] 相关 tests 和 smoke 补齐。

