# File Upload Backend Spec

> Status: Draft for next implementation phase
> Owner: B1 for platform API/storage/workspace import, B2 for runtime materialization contract
> Last updated: 2026-06-07
> Source roadmap: `docs/spec/next-major-modules.spec.md` Module B

## 1. 目标

让 AgentHub 支持用户主动上传图片、压缩包、文档、代码文件等，并把它们作为：

- 对话附件，随用户消息进入上下文；
- Workspace 输入文件，显式复制或解包到当前 conversation workspace；
- Agent knowledge / skill package / MCP config 的后续扩展来源。

上传失败、解析失败或导入失败不能拖垮聊天流，也不能污染 workspace。任何 workspace 变更必须来自用户显式操作。

## 2. 非目标

- 不在上传阶段执行任何脚本、安装依赖、运行构建命令。
- 不自动解包压缩包到 workspace。
- 不直接读取 `.agenthub/`、`.git/`、`.env*`、`.ssh/`、`secrets/` 等敏感路径。
- 不在 Adapter 内直接访问数据库或对象存储；B2 只能消费 B1 提供的结构化 metadata/materialized files。
- MVP 不做全文向量索引，可以先提供文本截断摘要和 metadata。

## 3. 归属模型

上传文件必须有明确归属和用途。

```text
Upload
  id: UUID
  owner_user_id: UUID
  conversation_id?: UUID
  purpose: UploadPurpose
  filename: str
  content_type: str
  detected_content_type: str
  size_bytes: int
  sha256: str
  storage_key: str
  status: UploadStatus
  safety_status: UploadSafetyStatus
  preview: jsonb
  error_code?: str
  error_message?: str
  created_at: datetime
  updated_at: datetime
  expires_at?: datetime

MessageAttachment
  id: UUID
  message_id: UUID
  upload_id: UUID
  role: AttachmentRole
  disposition: AttachmentDisposition
  created_at: datetime

WorkspaceImport
  id: UUID
  upload_id: UUID
  conversation_id: UUID
  mode: WorkspaceImportMode
  target_path: str
  imported_paths: jsonb
  status: WorkspaceImportStatus
  error_code?: str
  error_message?: str
  created_at: datetime
```

Enums:

```text
UploadPurpose =
  message_attachment
  workspace_import
  agent_knowledge
  agent_icon
  skill_package
  mcp_config

UploadStatus =
  uploading
  processing
  ready
  failed
  deleted

UploadSafetyStatus =
  pending
  passed
  blocked
  manual_review_required

AttachmentRole =
  user_supplied
  agent_reference

AttachmentDisposition =
  message_context
  workspace_candidate
  imported_workspace_file

WorkspaceImportMode =
  copy
  extract_archive

WorkspaceImportStatus =
  pending
  imported
  failed
```

## 4. HTTP API

Any API change must update `shared/openapi.yaml` first.

### 4.1 Create Upload

```http
POST /api/v1/uploads
Content-Type: multipart/form-data
Authorization: Bearer <token>
```

Fields:

| Field | Required | Description |
|---|---:|---|
| `file` | yes | Binary file payload |
| `purpose` | yes | `UploadPurpose` |
| `conversation_id` | no | Required for `workspace_import` and message attachment in an existing chat |
| `client_platform` | no | `web | ios | android | desktop` |
| `client_last_modified_at` | no | Optional client file mtime |

Response `201`:

```json
{
  "id": "uuid",
  "filename": "mockup.png",
  "content_type": "image/png",
  "detected_content_type": "image/png",
  "size_bytes": 123456,
  "sha256": "hex",
  "purpose": "message_attachment",
  "status": "ready",
  "safety_status": "passed",
  "preview": {
    "kind": "image",
    "width": 1280,
    "height": 720,
    "thumbnail_url": "/api/v1/uploads/<id>/download?variant=thumbnail"
  }
}
```

Error responses:

| Status | Code | Meaning |
|---:|---|---|
| 400 | `invalid_upload_purpose` | purpose not supported |
| 400 | `missing_conversation_id` | purpose requires conversation |
| 413 | `upload_too_large` | file exceeds size limit |
| 415 | `unsupported_media_type` | extension/MIME not allowed |
| 422 | `upload_safety_blocked` | unsafe archive/path/content |
| 429 | `upload_rate_limited` | user exceeded upload rate |

### 4.2 Get Upload Metadata

```http
GET /api/v1/uploads/{upload_id}
```

Returns metadata only. It must verify `owner_user_id` and optional conversation ownership.

### 4.3 Download Upload

```http
GET /api/v1/uploads/{upload_id}/download
```

Query:

- `variant=original | thumbnail | preview_text`

Rules:

- Owner-only unless the upload is linked to a conversation the user can access.
- Use `Content-Disposition: attachment` for unsafe/unknown binary files.
- Use short-lived signed URLs if production storage is object storage.

### 4.4 Delete Upload

```http
DELETE /api/v1/uploads/{upload_id}
```

Rules:

- Marks row as `deleted`.
- Deletes or tombstones object storage payload.
- Deleting an upload already attached to a persisted message should keep the message block but make download unavailable with `410 Gone`.
- Deleting a source upload must not delete files already imported into workspace.

### 4.5 Send Message With Attachments

Existing send/stream endpoints must accept:

```json
{
  "content": "参考这张图优化页面",
  "attachment_ids": ["upload-id-1", "upload-id-2"]
}
```

Validation:

- All upload ids belong to the current user.
- All uploads are `ready`.
- All uploads match the target conversation or have no conversation and can be attached.
- Max attachments per message default: 10.

Persistence:

- Create `MessageAttachment` rows after user message is persisted.
- Persist an `attachment` ContentBlock in the user message content for UI replay.

### 4.6 Workspace Import

```http
POST /api/v1/workspaces/{conversation_id}/imports
Content-Type: application/json
```

Request:

```json
{
  "upload_id": "uuid",
  "mode": "copy",
  "target_path": "."
}
```

Response:

```json
{
  "id": "uuid",
  "upload_id": "uuid",
  "conversation_id": "uuid",
  "mode": "copy",
  "target_path": ".",
  "status": "imported",
  "imported_paths": ["mockup.png"],
  "tree_version": 12
}
```

Rules:

- Requires conversation ownership.
- `copy` writes one file under `target_path`.
- `extract_archive` safely extracts archive entries under `target_path`.
- Import must call existing workspace path validation and must never write `.agenthub/`.
- Workspace tree should invalidate after success.

## 5. ContentBlock Contract

Add a new union member:

```ts
type AttachmentBlock = {
  type: "attachment";
  upload_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  purpose: UploadPurpose;
  safety_status: UploadSafetyStatus;
  preview?: {
    kind: "image" | "archive" | "document" | "text" | "code" | "unknown";
    url?: string;
    thumbnail_url?: string;
    width?: number;
    height?: number;
    page_count?: number;
    entries_preview?: string[];
    text_preview?: string;
    truncated?: boolean;
  };
  workspace_import?: {
    status: WorkspaceImportStatus;
    imported_paths?: string[];
  };
};
```

OpenAPI update checklist:

- Add `UploadOut`, `UploadPreview`, `AttachmentBlock`, `WorkspaceImportOut`.
- Add `attachment` to `ContentBlock` discriminator mapping.
- Add `attachment_ids` to message send request schemas.
- Regenerate frontend types with `pnpm gen:types`.

## 6. Storage Strategy

Local dev:

```text
data/uploads/<user_id>/<upload_id>/<safe_filename>
```

Production:

- Use an object-storage-compatible driver behind an `UploadStorage` interface.
- DB stores only metadata and storage key.
- All downloads go through an authenticated API or short-lived signed URL.

Filename handling:

- Store original filename for display.
- Use sanitized filename for workspace import.
- If target exists, default import strategy is `rename` with suffix, not overwrite. Overwrite requires explicit request in a later revision.

## 7. Validation And Safety

Default limits:

| Type | Limit |
|---|---:|
| Attachments per message | 10 |
| Image/document/text/code file | 20 MB |
| Archive upload | 100 MB |
| Extracted files | 2,000 |
| Extracted total size | 300 MB |
| Single text preview read | 1 MB |

Required checks:

- MIME sniffing, not only client-provided MIME.
- Extension allowlist by purpose.
- SHA-256 hash.
- Archive zip-slip rejection: `../`, absolute paths, Windows drive letters, symlink entries escaping root.
- Reject nested archive extraction by default.
- Reject encrypted archives for MVP.
- Reject suspicious decompression ratio.
- Secret scanning before `agent_knowledge` or `workspace_import` when feasible.
- Do not execute uploaded content.

Archive inspection:

- Inspect central directory without extracting first.
- Return preview metadata: file count, total size, top entries, blocked reason.
- `extract_archive` only proceeds if inspection passes.

## 8. Agent Context And B2 Materialization

B1 provides B2 with structured attachment metadata, never raw DB rows.

For message context:

```python
class RuntimeAttachment:
    upload_id: str
    filename: str
    content_type: str
    size_bytes: int
    purpose: str
    safe_local_path: Path | None
    preview_text: str | None
    preview: dict[str, Any]
```

Rules:

- Image attachments may enter multimodal model inputs only when selected adapter supports images.
- Text/code documents may be materialized as bounded preview text.
- Archive/document binaries are metadata-only until user imports or B1 extracts/indexes them.
- Unsupported binary files are summarized as filename/type/size only.
- B2 must not unpack archives or read object storage directly.
- B2 must not pass signed URLs to external runtimes unless the runtime contract explicitly allows it and URL expiry is short.

## 9. Failure Isolation

Upload failures:

- Do not clear composer text.
- Mark failed upload item with retry/remove.
- Sending is blocked only for messages referencing non-ready attachments.

Workspace import failures:

- Do not modify partial workspace state. Use temp directory then atomic move/copy where possible.
- Return imported paths only after success.
- Workspace tree remains usable after failure.

Safety failures:

- Persist upload metadata as `failed` or `blocked` with reason.
- UI can show the file but cannot download unsafe content unless policy allows admin review.

## 10. Tests

B1 unit/integration:

- `POST /uploads` persists metadata and SHA-256.
- Reject oversized uploads.
- Reject unsupported MIME/extension.
- Reject zip-slip archive.
- Reject encrypted/nested archive where unsupported.
- Download requires owner permission.
- Delete tombstones upload and blocks later download.
- Message send rejects non-ready or foreign upload ids.
- Message send creates `MessageAttachment` and `AttachmentBlock`.
- Workspace import copy writes inside sandbox only.
- Workspace import archive extracts inside sandbox only.
- Import failure leaves workspace tree unchanged.

B2 targeted:

- Runtime receives bounded `RuntimeAttachment` metadata.
- Image attachment is included only for image-capable backend.
- Archive is not unpacked by B2.
- Secret/blocked attachment is omitted from model context with visible warning.

## 11. Implementation Order

1. OpenAPI schemas and generated frontend types.
2. Upload DB models and migration.
3. Storage interface with local filesystem driver.
4. `POST/GET/DELETE /uploads`.
5. Message `attachment_ids` validation and `AttachmentBlock` persistence.
6. Workspace import copy.
7. Archive safe inspection and `extract_archive`.
8. B2 runtime attachment metadata adapter.
9. Object storage driver and optional background safety scanner.

## 12. Acceptance Criteria

- User can upload image/text/archive through API.
- User can send a message referencing ready uploads.
- Persisted chat replay shows attachment blocks.
- User can download own upload.
- User can import a safe file into current workspace.
- Safe archive import rejects traversal and does not write outside workspace.
- Agent receives only bounded, safe attachment context.
- Failed upload/import does not break chat stream or workspace APIs.
