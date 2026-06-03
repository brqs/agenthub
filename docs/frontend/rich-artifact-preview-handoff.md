# Rich Artifact Preview Handoff

> Owner：F
> 后端状态：B2 后端 MVP 与公网 Rich Artifact / Evaluation repair API/SSE E2E 已完成。
> 最后更新：2026-06-03

## 当前结论

B2 已把 rich artifact 的后端契约收口到 API / SSE / persisted message / manifest 四个入口。前端后续不需要等待新的 B2 基础能力即可开始产品化；公网 Rich Artifact / Evaluation repair E2E 已通过，前端只需要按本契约消费和展示。

本交接后的前端目标是把 document / PPT / image / archive 从“文件链接或普通块”提升为可理解的 artifact card，并把 evaluator 状态明确呈现给用户。

## 后端契约

B2 现在会为 Orchestrator 产出的 `document`、`ppt`、`image`、`archive` 追加正式 `file` content block：

- `path`
- `artifact_kind`
- `filename`
- `size`
- `mime_type`
- `url`
- `agent_id`
- `preview_text`
- `preview_truncated`
- `metadata`

`file` block 不直接包含 `task_id`、`run_id`、`evaluation_status` 或 `evaluation_results`。前端需要按 `path` 调用 manifest API 对齐这些运行态字段。

平台同时维护内部 `.agenthub/artifacts.json` v1，并通过只读 API 暴露：

```text
GET /api/v1/workspaces/{conversation_id}/artifacts
```

response:

```json
{
  "items": [
    {
      "path": "docs/report.md",
      "artifact_kind": "document",
      "filename": "report.md",
      "size": 1024,
      "mime_type": "text/markdown",
      "url": "/api/v1/workspaces/{conversation_id}/files/docs/report.md",
      "agent_id": "codex-helper",
      "task_id": "task-report",
      "run_id": "orchestrator-run-uuid",
      "preview_text": "# Report...",
      "preview_truncated": false,
      "metadata": {},
      "evaluation_status": "passed",
      "evaluation_results": [],
      "created_at": "2026-06-03T12:00:00Z",
      "updated_at": "2026-06-03T12:00:00Z"
    }
  ]
}
```

`.agenthub/artifacts.json` 仍不能通过 workspace file API 读取。

公网后端证据：

```text
p1_rich_artifacts:
  report: /tmp/agenthub_p1_rich_artifacts_report.json
  sse: /tmp/agenthub_p1_rich_artifacts_sse.jsonl
  conversation_id: c6da3473-b338-4321-ba7d-eb0f877e70ae
  passed: true
  covered: document, ppt, image, archive

p1_evaluation_repair:
  report: /tmp/agenthub_p1_evaluation_repair_report.json
  sse: /tmp/agenthub_p1_evaluation_repair_sse.jsonl
  conversation_id: 5186e757-6a7c-4d0f-8643-c9b3defbc181
  passed: true
```

## Evaluation 状态语义

前端展示时应使用 manifest API 的 `evaluation_status`：

- `passed`：自动 evaluator 已通过。
- `failed`：自动 evaluator 明确失败，优先展示 `evaluation_results[].issues` 或错误摘要。
- `manual_review_required`：后端无法 deterministic 判断质量，需要人工确认，不能显示成自动通过。
- `unknown`：没有可用评价结果或历史数据不足，应作为中性未知态。

`evaluation_results` 是后端 evaluator payload 的透传摘要；前端只做展示和筛选，不在 UI 层重新判断是否通过。

## 前端待办

- Rich card 产品化：document / PPT / image / archive 使用专门卡片，而不是只展示普通链接。
- 消费 manifest API：对 persisted message 的 `file` block 做 path 对齐，补齐 `task_id`、`run_id`、`evaluation_status`。
- Evaluation 展示：`failed`、`manual_review_required`、`passed`、`unknown` 用清晰状态呈现；不要把 `unknown` 或 manual review 显示成自动通过。
- 版本历史：同一路径多次更新时展示时间线和 responsible agent。
- 局部编辑：为 document / code / workflow 后续接入 “edit this section / revise artifact” 入口。
- PPT 深度预览：当前后端只提供 OpenXML 文本层 preview 和 slide count，前端深度版式预览另行设计。
- Image 深度预览：当前后端提供安全 metadata 和 file URL，前端负责缩略图、大图、下载入口。
- Archive 深度预览：当前后端提供 file count / total size / top entries，前端负责目录摘要和下载入口。

这些都是前端产品化增强，不作为 B2 后端阻塞项。

## 建议前端实现

建议先做一个纯函数 model，再接 UI：

```ts
type RichArtifactViewModel = {
  path: string;
  artifactKind: 'document' | 'ppt' | 'image' | 'archive' | 'code' | 'workflow' | 'other';
  filename: string;
  url: string;
  agentId?: string | null;
  taskId?: string | null;
  runId?: string | null;
  previewText?: string | null;
  previewTruncated?: boolean | null;
  metadata: Record<string, unknown>;
  evaluationStatus: 'passed' | 'failed' | 'manual_review_required' | 'unknown';
};
```

构建规则：

- 先从 persisted message content 读取 `type="file"` blocks，作为聊天内 artifact card 的基础。
- 再调用 `GET /api/v1/workspaces/{conversation_id}/artifacts`，按 `path` 合并 manifest 字段。
- 如果 manifest 暂不可用，仍展示 file block 基础卡片，不阻断聊天渲染。
- 如果同一路径出现多条 manifest entry，以 API 返回的最新 entry 为准；版本历史 UI 后续可基于 `updated_at` 扩展。
- 所有文件打开/下载都使用后端返回的 `url`，不要自行拼接 `.agenthub` 内部路径。

## 验收标准

- document / PPT / image / archive 至少有四类不同卡片语义或图标标签。
- image card 使用 `url` 展示缩略图或打开大图入口。
- archive card 展示 file count / total size / top entries。
- PPT card 展示 slide count 和文本摘要；`.pptx` 不要求还原版式。
- Evaluation 状态区分 `passed`、`failed`、`manual_review_required`、`unknown`。
- Manifest API 不可用时，消息主内容仍可展示 file block。
- 前端测试覆盖 model 合并、缺 manifest 降级、长文件名、小屏布局和 evaluation 状态渲染。

## B2 边界

B2 负责后端契约、artifact metadata、manifest API、evaluation status 和公网 API/SSE E2E 证据。前端负责视觉呈现、manifest 聚合视图、版本历史、局部编辑入口和交互测试。

若前端发现字段缺失，先以本文件中的契约为准提出具体字段需求；不要绕过 workspace file API 读取 `.agenthub/artifacts.json`，也不要把 `manual_review_required` 或 `unknown` 当作自动通过。
