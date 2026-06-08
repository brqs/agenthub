# Deployment Status Productization Spec

## Status

Implementation target: 2026-06-08.

## Goal

Make deployment cards and history feel like a real release console:

- Clear Chinese lifecycle labels.
- Timeline from queued to published/failed/stopped.
- Foldable logs with sensible height.
- Health check result and runtime metadata.
- Stop and retry actions.

## Backend

### Existing Fields

`WorkspaceDeploymentResponse` already exposes:

- `status`
- `logs`, `logs_tail`
- `state_events`
- `healthcheck_url`
- `runtime_status`
- `host_port`, `container_port`
- `container_id`, `image_id`
- `last_error_code`, `failure_category`
- `attempt_count`
- timestamps: `queued_at`, `started_at`, `published_at`, `completed_at`,
  `stopped_at`, `last_checked_at`.

### Retry API

New endpoint:

```http
POST /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}/retry
```

Rules:

- Only same owner can retry.
- Retry is allowed for `failed`, `stopped`, and `not_supported` records.
- Retry creates a new deployment record using the previous deployment request
  parameters where possible.
- Response is `WorkspaceDeploymentResponse` for the new deployment.
- Source zip retry packages the current workspace snapshot.
- Static site retry reuses previous `entry_path`.
- Container retry reuses previous `container_port` and health path if present.

### Health Presentation

No separate health endpoint is required for MVP. Frontend derives display from:

- `runtime_status`
- `healthcheck_url`
- `last_checked_at`
- status and state events.

## Frontend

### Deployment Card

Card sections:

- Header: kind, status badge, deployment id, size.
- Summary grid: file count, digest, ports, runtime, container/image ids.
- Health panel: health URL, last checked, runtime status, interpreted health.
- Timeline: vertical on mobile, compact horizontal or vertical on desktop.
- Logs: collapsed by default, expandable, copy button optional.
- Actions: open URL, copy URL, download source, stop, retry.

### Retry UX

- Show retry for `failed`, `stopped`, `not_supported`.
- Disable while mutation pending.
- On success, invalidate deployment list and show new card/history item.
- Retry failure displays inline error.

### History

History item should expose the same stop/retry/open/copy/download actions in a
compact form. Logs can remain card-only unless user opens the item.

## Acceptance

- User can understand queued/building/health/published/failed lifecycle without
  reading raw logs.
- Logs do not dominate chat unless expanded.
- Failed deployment can be retried from card/history.
- Stopped deployment can be retried and yields a new deployment record.
- Source zip, static site, and container all render consistent Chinese status.

