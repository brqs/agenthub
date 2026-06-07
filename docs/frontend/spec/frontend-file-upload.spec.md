# Frontend File Upload Spec

> Status: Draft for next implementation phase
> Owner: F
> Last updated: 2026-06-07
> Backend contract: `docs/b1/spec/file-upload-backend.spec.md`

## 1. 目标

在 AgentHub Web、iOS Capacitor、Android Capacitor 中提供 Codex-like 文件上传体验：

- PC 支持点击选择、拖拽、粘贴图片；
- 移动端支持系统文件选择器、相册、拍照，以及后续分享入口；
- 上传文件可以作为对话附件，也可以显式导入 workspace；
- 上传、预览、下载、删除、重试、失败隔离都有清晰 UI。

## 2. 非目标

- 前端不执行压缩包解包、安全扫描、MIME 判定的最终决策。
- 前端不直接写 workspace 文件，workspace 导入必须调用后端 import API。
- MVP 不实现本地离线队列持久化。
- MVP 不把分享入口做成独立原生扩展；先保留 Capacitor bridge 设计和 smoke 标准。

## 3. 用户入口

### 3.1 Desktop Web

Composer 支持：

- Paperclip 点击选择文件；
- 文件拖拽到 composer 或聊天区域；
- 从剪贴板粘贴图片；
- 多文件选择；
- 上传队列中移除、重试、查看错误。

### 3.2 Mobile Web / PWA

Composer 支持：

- Paperclip 打开系统文件选择器；
- `accept="image/*"` 入口用于相册/拍照；
- 附件以紧凑 chips/card 横向滚动显示；
- 不依赖 drag/drop；
- 输入框和附件栏不得被软键盘遮挡。

### 3.3 iOS Capacitor

优先级：

1. Web `<input type="file">` 可用时直接走 Web Blob 上传。
2. WebView 不稳定时走原生 document/photo picker。
3. 原生 picker 返回 URI 后复制到 app cache，再上传。

约束：

- 避免把大文件转成 base64。
- 尊重 iOS 相册 limited access。
- 权限拒绝要显示可恢复提示。

### 3.4 Android Capacitor

优先级：

1. Web input / Android Photo Picker / Document Provider。
2. 必要时通过 Capacitor bridge 处理 `content://` URI。

约束：

- 对 `content://` URI 尽量申请 persistable permission。
- 虚拟文件无法打开时显示明确错误。
- 大文件上传不能冻结 UI。

## 4. 前端状态模型

```ts
type LocalUploadItem = {
  local_id: string;
  upload_id?: string;
  file: File | NativePickedFile;
  filename: string;
  content_type: string;
  size_bytes: number;
  purpose: UploadPurpose;
  status: "queued" | "uploading" | "processing" | "ready" | "failed" | "deleted";
  progress: number;
  preview?: AttachmentPreview;
  error_code?: string;
  error_message?: string;
  can_import_workspace: boolean;
};
```

Composer store:

```ts
type ComposerAttachmentState = {
  items: LocalUploadItem[];
  addFiles(files: FileList | File[]): void;
  retry(localId: string): void;
  remove(localId: string): void;
  clearAfterSend(sentUploadIds: string[]): void;
};
```

Rules:

- `local_id` is client-only and stable before backend returns `upload_id`.
- Send button is disabled if any referenced attachment is not `ready`.
- Failed attachment does not clear composer text.
- Removing a ready attachment detaches it from current composer; if already persisted in a message, use backend delete only from message/file detail UI.

## 5. API Client

Add typed adapter functions after OpenAPI update:

```ts
uploadFile(input: {
  file: File | Blob;
  filename: string;
  purpose: UploadPurpose;
  conversationId?: string;
  clientPlatform: "web" | "ios" | "android" | "desktop";
  onProgress?: (progress: number) => void;
}): Promise<UploadOut>

deleteUpload(uploadId: string): Promise<void>

downloadUpload(uploadId: string, variant?: "original" | "thumbnail" | "preview_text"): Promise<Blob>

importUploadToWorkspace(input: {
  conversationId: string;
  uploadId: string;
  mode: "copy" | "extract_archive";
  targetPath: string;
}): Promise<WorkspaceImportOut>
```

Implementation notes:

- Use `XMLHttpRequest` for upload progress in browser if `fetch` progress is insufficient.
- Keep auth headers consistent with existing API client.
- Abort upload when user removes a queued/uploading item.
- Do not hardcode paths outside the API adapter.

## 6. Composer UX

### 6.1 Attachment Queue

Placement:

- Desktop: above composer input, wrapping row/grid.
- Mobile: compact horizontal chips above input.

Each item shows:

- icon/thumbnail;
- filename;
- size;
- status;
- progress;
- retry/remove buttons;
- warning if safety scan blocked or manual review required.

States:

| State | UI |
|---|---|
| `queued` | pending chip |
| `uploading` | progress bar |
| `processing` | spinner and "解析中" |
| `ready` | normal chip/card |
| `failed` | red state with retry/remove |
| `deleted` | removed from active composer |

### 6.2 Drag And Drop

Desktop behavior:

- Drag over chat/composer highlights drop zone.
- Drop filters directories unless browser provides files.
- Unsupported files are added as failed local items with reason, not silently ignored.
- Dropping while stream is active is allowed; sending still follows current stream/queue rules.

### 6.3 Paste Image

Rules:

- On paste, inspect `clipboardData.items`.
- Image blobs become attachment items.
- Text paste remains normal text input.
- If both text and image exist, preserve text and add image.

### 6.4 Send Behavior

On send:

1. Validate text or ready attachments exist.
2. Block send if any attachment is uploading/processing.
3. Send message with `attachment_ids`.
4. On success, clear only sent attachments.
5. On message send failure, keep attachments in composer for retry.

Queued next-turn behavior:

- If current conversation stream is busy and queued message is enabled, the queued payload must include `attachment_ids`.
- If an upload is still running, queue action remains disabled until ready.

## 7. Attachment Message Rendering

Add `AttachmentBlock` renderer under `frontend/src/components/blocks/`.

Required variants:

- `image`: thumbnail, full preview, download.
- `archive`: file count/top entries, "导入 Workspace" action.
- `document`: filename, size, preview text or page count, download.
- `text/code`: preview snippet, download, optional "导入 Workspace".
- `unknown`: safe metadata card and download if allowed.

Block actions:

- preview/open;
- download;
- delete if current user owns upload and message policy allows;
- import to workspace if conversation has workspace and upload is safe.

Failure behavior:

- Unknown preview kind must render fallback card.
- Download failure shows inline toast/error, does not remove block.
- Blocked unsafe upload shows reason and disables download/import.

## 8. Workspace Import UX

Entry points:

- From attachment card action.
- From upload queue after ready.
- From archive preview modal.

Import modal:

- Shows upload summary.
- Select mode:
  - `copy` for single file;
  - `extract_archive` for archive.
- Target path input with default `.`.
- For archive, show entries preview and warning that workspace will change.
- Confirm button calls workspace import API.

After success:

- Invalidate workspace tree query.
- Select imported file if one file was copied.
- Show imported paths summary.
- Preserve chat scroll position.

After failure:

- Show backend error reason.
- Keep attachment card actionable.
- Workspace tree remains unchanged.

## 9. Native Bridge Boundary

Web remains default path. Add a small platform abstraction:

```ts
type PickedUploadFile = {
  filename: string;
  contentType: string;
  sizeBytes?: number;
  file?: File;
  uri?: string;
  platform: "web" | "ios" | "android";
};
```

Bridge methods:

```ts
pickFiles(options): Promise<PickedUploadFile[]>
pickImages(options): Promise<PickedUploadFile[]>
captureImage(options): Promise<PickedUploadFile | null>
uploadNativeFile(file, metadata, onProgress): Promise<UploadOut>
```

Rules:

- If `file` exists, use web upload path.
- If only `uri` exists, use native file transfer path.
- Do not read large files into JS memory.
- Native errors must map to user-friendly codes:
  - `permission_denied`
  - `file_unavailable`
  - `file_too_large`
  - `provider_virtual_file`
  - `upload_cancelled`

## 10. Accessibility And Layout

- Paperclip button has `aria-label="添加附件"`.
- Drop zone has visible focus/drag state.
- Attachment remove/retry buttons have labels.
- Progress uses accessible text, not only color.
- Mobile chips are at least 44px high touch targets.
- Composer remains within safe-area and avoids keyboard overlap.
- Long filenames use middle truncation or tooltip; never cause horizontal overflow.

## 11. Tests

Frontend unit/component:

- File picker adds files to queue.
- Drag/drop adds files and rejects unsupported files visibly.
- Paste image adds image without losing text.
- Upload progress updates queue item.
- Retry reuses local item and updates status.
- Remove aborts uploading request.
- Send disabled while upload not ready.
- Send payload includes `attachment_ids`.
- Message send failure keeps attachments.
- `AttachmentBlock` renders image/archive/document/text/unknown variants.
- Workspace import modal calls import API and invalidates tree.
- Mobile composer chips do not overlap input.

Native smoke:

- iOS photo pick uploads image.
- iOS document pick uploads PDF/zip.
- Android Photo Picker uploads image.
- Android document provider uploads zip.
- Large file selection does not freeze UI.
- Permission denied shows recoverable error.

Manual E2E:

- PC drag image then send; persisted replay shows thumbnail.
- PC paste screenshot then send.
- Upload zip, inspect entries, import to workspace, tree refreshes.
- Delete upload before send removes it from composer.
- Upload failure does not clear message text.

## 12. Implementation Order

1. Generate OpenAPI types after B1 contract lands.
2. Add upload API adapter with progress and abort support.
3. Add composer attachment store/state.
4. Add paperclip picker and upload queue.
5. Add send payload `attachment_ids`.
6. Add `AttachmentBlock` renderer.
7. Add drag/drop and paste image.
8. Add workspace import modal and tree invalidation.
9. Add mobile compact chips.
10. Add Capacitor bridge fallback and native smoke.

## 13. Acceptance Criteria

- Desktop can upload via picker, drag/drop, and paste image.
- Mobile web can upload through system picker.
- Composer clearly shows upload status and failures.
- Send is blocked until selected uploads are ready.
- Sent messages replay attachment cards from persisted blocks.
- Safe archive can be imported into workspace only after explicit confirmation.
- Failed upload/import does not break chat stream or workspace panel.
- iOS/Android native shell has a verified path for image/archive upload.
