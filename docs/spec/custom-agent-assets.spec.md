# Custom Agent Knowledge and Skill Upload Spec

## Status

MVP implementation target: 2026-06-08.

This spec narrows the broader Deep Custom Agent Builder roadmap into the urgent
B2 handoff need: user-owned custom Agents can receive Markdown knowledge files
and uploaded skills, and users can delete those bindings.

## Goals

- Let users attach Markdown files to a custom Agent as explicit knowledge.
- Let users upload a Markdown skill definition for a custom Agent.
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

### Delete Skill

```http
DELETE /api/v1/agents/{agent_id}/skills/{skill_id}
```

Response: `204`.

Rules:

- Removes only the Agent config binding.
- Keeps the upload metadata/payload available through the upload API.

### Delete Agent Cleanup

`DELETE /api/v1/agents/{agent_id}` must remove the deleted Agent id from every
conversation owned by the same user before deleting the Agent row. This prevents
conversation `agent_ids` from referencing missing custom Agents.

## Frontend Contract

### Agent Detail Panel

For user-owned custom Agents, show two editable sections:

- `知识文件`: list `config.knowledge`, upload Markdown, delete binding.
- `Skills`: list `config.skills`, upload Markdown skill, delete binding.

Built-in Agents remain read-only and only display existing config assets if any.

### UX Rules

- Upload uses native file picker via `<input type="file">`.
- Accept `.md,.markdown,.txt` for knowledge.
- Accept `.md,.markdown` for skill MVP.
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

The runtime should treat these as user-approved context references. It must not
read deleted bindings because frontend/backend remove them from config. If B2
needs full content, it should ask B1 for an explicit read/download helper rather
than reading storage paths from untrusted config.

## Tests

Backend:

- Upload Markdown knowledge to custom Agent.
- Reject knowledge upload to builtin Agent.
- Upload Markdown skill to custom Agent and parse metadata.
- Delete skill binding.
- Delete custom Agent removes it from user conversations.

Frontend:

- Agent detail displays knowledge and skill sections.
- Upload buttons call the correct adapter and refresh local Agent state.
- Delete buttons call the correct adapter.

