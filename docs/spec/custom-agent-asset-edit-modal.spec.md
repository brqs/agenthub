# Custom Agent Asset Edit Modal Spec

## Status

Implementation target: 2026-06-08.

## Goal

Replace browser `window.prompt` asset editing with a product-grade modal/sheet
for custom Agent knowledge and skill bindings.

This spec covers only the editing interaction. It relies on the existing asset
upload, metadata update, download, and unbind APIs.

## Backend

No new backend capability is required for the modal itself.

Existing endpoints:

- `PATCH /api/v1/agents/{agent_id}/knowledge/{upload_id}`
- `PATCH /api/v1/agents/{agent_id}/skills/{skill_id}`

Backend rules:

- Built-in Agents remain read-only.
- The update only changes binding metadata, not the uploaded file payload.
- Knowledge `usage` must remain one of `reference`, `policy`, `template`, or
  `example`.
- Empty strings should not clear required display fields; clients should keep
  the previous value or reject before submit.

## Frontend

### Entry Points

Each custom Agent asset list item exposes:

- Download original upload.
- Edit metadata.
- Unbind from Agent.

Clicking edit opens an in-app modal on desktop and a full-width bottom sheet
style panel on narrow/mobile layouts.

### Knowledge Form

Fields:

- `label`: required text input, max 160 chars.
- `usage`: required select with Chinese labels:
  - `reference`: 参考资料
  - `policy`: 规则/约束
  - `template`: 输出模板
  - `example`: 示例

Submit:

- Calls `updateKnowledge`.
- Shows pending state and disables repeated submit.
- On success closes modal and refreshes Agent store/query.
- On failure keeps modal open and shows inline error.

### Skill Form

Fields:

- `name`: required text input, max 160 chars.
- `description`: required textarea, max 240 chars.

Submit:

- Calls `updateSkill`.
- Same pending/success/error behavior as knowledge.

### Accessibility

- Dialog has `role="dialog"` and `aria-modal="true"`.
- Close button has visible or aria label.
- `Escape` closes the dialog without submitting.
- Primary submit button is reachable by keyboard.

## Acceptance

- No `window.prompt` remains in Agent asset editing.
- Knowledge edit can update label and usage.
- Skill edit can update name and description.
- Failed update displays inline error without breaking Agent page.
- Mobile sheet does not overflow viewport and respects safe area.

