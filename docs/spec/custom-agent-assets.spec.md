# Custom Agent Knowledge and Skill Upload Spec

## Status

MVP implementation target: 2026-06-08.

This spec narrows the broader Deep Custom Agent Builder roadmap into the urgent
B2 handoff need: user-owned custom Agents can receive Markdown knowledge files
and uploaded skills, users can edit their binding metadata, and users can
delete those bindings.

## Goals

- Let users attach Markdown files to a custom Agent as explicit knowledge.
- Let users upload a Markdown skill definition for a custom Agent.
- Let users edit knowledge labels/usages and skill name/description after upload.
- Let users download the original uploaded asset from the Agent detail panel.
- Let users remove Agent knowledge and Agent skills without deleting the source
  upload record for historical audit.
- Keep B2 runtime consumption simple: assets are persisted in `Agent.config` so
  adapters can read `config.knowledge` and `config.skills`.
- Make frontend, web mobile, iOS WebView, and Android WebView use the same
  multipart upload path.

## Non-Goals

- Full no-code Agent builder wizard.
- Skill package zip extraction or script execution.
- Vector indexing, long-term memory promotion, or automatic model ingestion.
- MCP server config upload.
- Sharing uploaded skills across users or marketplace publication.

## Existing References

- `docs/spec/next-major-modules.spec.md` Module C: full custom Agent roadmap.
- `docs/spec/upload-memory-alignment.spec.md`: upload purposes and memory flow.
- `docs/b1/spec/file-upload-backend.spec.md`: general upload API.
- `docs/frontend/spec/frontend-file-upload.spec.md`: cross-platform upload UX.

## Backend Contract

All endpoints require bearer auth. Built-in Agents are read-only. Users can only
operate on their own non-builtin Agents.

### Upload Purposes

`UploadPurpose` must include:

```text
message_attachment
workspace_file
workspace_import
agent_knowledge
agent_icon
skill_package
mcp_config
```

### Agent Config Shape

MVP stores Agent assets inside `Agent.config`:

```ts
type AgentKnowledgeRef = {
  upload_id: string;
  filename: string;
  label: string;
  usage: "reference" | "policy" | "template" | "example";
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
};

type AgentSkillRef = {
  skill_id: string;
  upload_id: string;
  name: string;
  description: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
  metadata?: Record<string, unknown>;
};
```

Config keys:

- `knowledge`: `AgentKnowledgeRef[]`
- `skills`: `AgentSkillRef[]`

Future versions may migrate these arrays into normalized tables. The API shape
should remain stable.

### Create Knowledge

```http
POST /api/v1/agents/{agent_id}/knowledge
Content-Type: multipart/form-data
```

Fields:

- `file`: required Markdown/text file.
- `label`: optional display label. Defaults to filename.
- `usage`: optional, defaults to `reference`.

Response: `AgentKnowledgeOut`.

Validation:

- File extension must be `.md`, `.markdown`, or `.txt`.
- Upload purpose is persisted as `agent_knowledge`.
- Duplicate `upload_id` is ignored by replacing the existing ref.

### Delete Knowledge

```http
DELETE /api/v1/agents/{agent_id}/knowledge/{upload_id}
```

Response: `204`.

Rules:

- Removes only the Agent config binding.
- Keeps the upload metadata/payload available through the upload API unless the
  user separately deletes the upload.

### Update Knowledge Metadata

```http
PATCH /api/v1/agents/{agent_id}/knowledge/{upload_id}
Content-Type: application/json
```

Body:

```json
{
  "label": "Updated display name",
  "usage": "template"
}
```

Response: `AgentKnowledgeOut`.

Rules:

- `label` is optional and normalized to a short display string.
- `usage` is optional and must be one of `reference`, `policy`, `template`, or
  `example`.
- The endpoint edits only the Agent config binding. It does not rewrite the
  upload payload.

### Create Skill

```http
POST /api/v1/agents/{agent_id}/skills
Content-Type: multipart/form-data
```

Fields:

- `file`: required Markdown file.
- `name`: optional override. Defaults to YAML frontmatter `name`, first heading,
  or filename stem.
- `description`: optional override. Defaults to YAML frontmatter `description`
  or the first non-empty body line.

Response: `AgentSkillOut`.

Validation:

- MVP accepts `.md`, `.markdown`, or a file named `SKILL.md`.
- Upload purpose is persisted as `skill_package`.
- No script or template execution happens during import.
- `name` and `description` are normalized to safe short strings.
- P1 requires both `name` and `description`. They can come from form fields,
  YAML frontmatter, a Markdown heading/body fallback, or a combination of those
  sources.

### Delete Skill

```http
DELETE /api/v1/agents/{agent_id}/skills/{skill_id}
```

Response: `204`.

Rules:

- Removes only the Agent config binding.
- Keeps the upload metadata/payload available through the upload API.

### Update Skill Metadata

```http
PATCH /api/v1/agents/{agent_id}/skills/{skill_id}
Content-Type: application/json
```

Body:

```json
{
  "name": "Draft Reviewer",
  "description": "Review draft Markdown files."
}
```

Response: `AgentSkillOut`.

Rules:

- `name` and `description` are optional, but at least one should be provided by
  the client.
- Values are normalized to safe short strings.
- The endpoint edits only the Agent config binding. It does not rewrite the
  upload payload or parsed Markdown metadata.

### Delete Agent Cleanup

`DELETE /api/v1/agents/{agent_id}` must remove the deleted Agent id from every
conversation owned by the same user before deleting the Agent row. This prevents
conversation `agent_ids` from referencing missing custom Agents.

## Frontend Contract

### Agent Detail Panel

For user-owned custom Agents, show two editable sections:

- `知识文件`: list `config.knowledge`, upload Markdown, download original file,
  edit label/usage, delete binding.
- `Skills`: list `config.skills`, upload Markdown skill, download original file,
  edit name/description, delete binding.

Built-in Agents remain read-only and only display existing config assets if any.

### UX Rules

- Upload uses native file picker via `<input type="file">`.
- Accept `.md,.markdown,.txt` for knowledge.
- Accept `.md,.markdown` for skill MVP.
- Let users choose knowledge `usage`.
- Let users provide skill `name` and `description` when the Markdown file does
  not include frontmatter.
- Let users download the original upload through the existing upload download
  API.
- Delete copy must say "解除绑定" because the original upload remains.
- Show uploading/deleting disabled state.
- After success, update the selected Agent in local store and invalidate Agent
  list query.
- On failure, display a compact error message inside the panel; do not break the
  whole Agent page.

### Cross-Platform Notes

- PC web, mobile web, iOS WebView, and Android WebView all use the same
  multipart endpoints.
- Native share sheet / camera support is out of this MVP because Agent skills
  and knowledge are text files.

## B2 Runtime Consumption

B2 can read:

- `agent.config["knowledge"]`
- `agent.config["skills"]`

The MVP runtime path is implemented at `agents.registry.get_adapter()`: before
an adapter is instantiated, B1's safe asset helper resolves ready/passed upload
refs owned by the Agent owner, reads bounded Markdown/text content, and appends
it to the adapter `system_prompt` inside an `<agent_uploaded_assets>` section.

Runtime rules:

- B2 must not read upload `storage_key` directly.
- Deleted bindings are not injected because frontend/backend remove them from
  config.
- Uploads with wrong owner, missing file, non-ready status, or blocked safety
  status are skipped.
- Context is bounded and may be truncated. Agents must not assume hidden content
  beyond what is shown.

This gives builtin/custom/external adapters the same P0 asset context because
all runtime adapter creation goes through the registry.

## Tests

Backend:

- Upload Markdown knowledge to custom Agent.
- Patch knowledge label and usage.
- Reject knowledge upload to builtin Agent.
- Upload Markdown skill to custom Agent and parse metadata.
- Reject skill upload without resolvable name/description.
- Patch skill name and description.
- Delete skill binding.
- Delete custom Agent removes it from user conversations.

Frontend:

- Agent detail panel upload controls for knowledge and skills.
- Knowledge usage select and skill name/description fields.
- Existing bindings expose download, edit, and unbind actions.
- Failed upload/edit/delete displays inline error and does not break the page.

Frontend:

- Agent detail displays knowledge and skill sections.
- Upload buttons call the correct adapter and refresh local Agent state.
- Delete buttons call the correct adapter.
