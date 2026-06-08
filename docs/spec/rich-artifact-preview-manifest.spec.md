# Rich Artifact Preview and Manifest Aggregation Spec

## Status

Implementation target: 2026-06-08.

## Goal

Upgrade artifact display from generic file cards to product-specific previews
for document, ppt, image, and archive outputs, and add a manifest aggregation
view in the workspace panel.

## Backend

### Existing Contract

`GET /api/v1/workspaces/{conversation_id}/artifacts` returns
`WorkspaceArtifactListResponse`.

Each artifact includes:

- `path`, `filename`, `artifact_kind`, `mime_type`, `size`, `url`
- `preview_text`, `preview_truncated`
- `metadata`
- `task_id`, `run_id`, `agent_id`
- `evaluation_status`, `evaluation_results`

### Metadata Expectations

Backend should populate when available:

Document:

- `page_count`
- `word_count`
- `headings`

PPT:

- `slide_count`
- `slide_titles`
- `preview_slides`

Image:

- `width`
- `height`
- `thumbnail_url`

Archive:

- `file_count`
- `total_size`
- `top_entries`

The frontend must tolerate missing fields.

### No New Backend Endpoint

MVP uses the existing manifest endpoint. If metadata is missing, frontend shows
graceful fallback and does not read `.agenthub/artifacts.json` directly.

## Frontend

### FileBlock Rich Cards

Render specialized content by `artifact_kind`:

- `image`: thumbnail, dimensions, click to large preview.
- `archive`: file count, total size, top entries list.
- `ppt`: slide count, slide titles, preview text.
- `document`: page/word count, headings, Markdown/text preview.

Evaluation status must remain explicit:

- `passed`: 评估通过
- `failed`: 评估失败
- `manual_review_required`: 需人工复核
- `unknown`: 评估未知

Never display `unknown` or `manual_review_required` as passed.

### Manifest Aggregation View

Workspace panel adds an `Artifacts` aggregation section:

- Counts by kind.
- Counts by evaluation status.
- List of artifacts grouped by kind.
- Clicking an artifact selects the corresponding workspace file when possible.
- Manifest fetch failure must not break file tree or selected file preview.

### Fullscreen Preview

Rich preview modal supports:

- Image large view.
- Document/PPT markdown/text preview.
- Archive entries list.
- Evaluation details summary.

## Acceptance

- File blocks no longer feel identical across image/document/ppt/archive.
- Workspace panel shows manifest-level artifact overview.
- Manifest unavailable: chat and workspace file tree still render normally.
- Evaluation statuses are displayed accurately.
- Mobile layout remains within viewport.

