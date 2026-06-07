# AgentHub Next Major Modules Spec

> Status: Draft architecture spec  
> Last updated: 2026-06-07  
> Scope: interruptible conversations, cross-platform file uploads, and deep custom Agent builder  
> Owners: B1 + B2 + F. This file is the handoff entry before implementation.

## 2026-06-07 Implementation Note: Conversation Interrupt

The conversation interrupt slice has moved from draft to implemented contract.

- B1 exposes `POST /api/v1/messages/{msg_id}/interrupt`.
- Message status now includes `interrupted`, alongside `pending | streaming | done | error`.
- The interrupt response state is `interrupted | already_terminal | interrupting`.
- SSE terminal events now include `interrupted`; Orchestrator child messages can emit `message_interrupted`.
- `task_card`, `process`, and process step statuses support `interrupted`.
- User interrupt is not transport failure, retry, regenerate, or delete. It preserves partial content, clears conversation busy state, and renders as a neutral terminal state.
- Client disconnect, conversation switching, StrictMode remount, and background SSE subscriber churn must not create `interrupted`.

The rest of this document still describes the wider next-major roadmap for uploads and custom Agents. For interrupt behavior, treat this implementation note, `shared/openapi.yaml`, B1 stream code, and frontend generated types as the current truth.

## 2026-06-07 Implementation Note: Queued Next Turn

Phase 1 of Codex-style "submit while running" is now an implemented contract:

- Message status now includes `queued`.
- B1 persists queued user turns in `message_queue_entries`.
- `POST /api/v1/conversations/{conversation_id}/queued-messages` creates a queued user message only while the same conversation already has a `pending` or `streaming` agent response.
- `PATCH /api/v1/queued-messages/{message_id}` edits queued text or target agent before dispatch.
- `DELETE /api/v1/queued-messages/{message_id}` physically removes an undispatched queued message.
- `POST /api/v1/conversations/{conversation_id}/messages` keeps the existing busy guard and still returns `409 CONVERSATION_BUSY` while an agent response is active.
- `done`, `error`, and `interrupted` SSE terminal payloads may include `queued_next`, containing the dispatched user message, newly-created pending agent message, and remaining queue count.
- The same conversation remains strictly serial: one active agent response at a time. Different conversations can continue streaming independently.
- Phase 1 is not "guide current thinking"; queued text is the next user turn and is not injected into the currently running agent context.

## 2026-06-07 Implementation Note: Conversation Control Plane

Phase 2/3 are now implemented as a conversation control plane layered on top of interrupt and queue:

- New persisted table: `conversation_turn_controls`.
- New content block: `turn_control`, with `kind=guidance | side_chat | queue_action | stop_and_run` and lifecycle `received | waiting_safe_point | applied | answered | cancelled | expired | failed`.
- Guidance is explicit. The default streaming submit path still creates a queued next turn; users must choose "guide current reply" to affect the active turn.
- Guidance is currently Orchestrator-only and safe-point based. Safe points include direct-answer/planner/task-dispatch/tool-result/replanner boundaries. External CLI/SDK runtimes do not receive live prompt injection.
- Side chat is a compact status question/answer about the active turn. It is persisted visibly but excluded from future main-task context.
- Queue actions include reorder, merge, convert queued message to guidance, and stop current reply then run a queued message.
- Same-conversation serial execution remains a hard invariant. Control actions do not create parallel active agent turns.

## 0. Summary

The next AgentHub work should be split into three product modules:

1. **Interrupt conversation**: let the user stop a running agent turn without losing the conversation, similar to Codex-style cancellation. The stopped turn becomes a visible terminal state, not a transport error.
2. **File upload**: support images, archives, documents, and other user files on web, iOS, and Android. Uploads are first-class message/workspace inputs, not ad hoc pasted text.
3. **Deep custom Agent builder**: let non-coding users create useful Agents by describing roles, goals, boundaries, knowledge, skills, MCP servers, and tool permissions through a guided UI.

These modules must follow existing AgentHub design philosophy:

- The UI should show facts and state transitions clearly.
- Orchestrator should not create hidden side effects.
- Runtime and tool capabilities must be explicit, health-checked, and permissioned.
- A non-technical user should be able to understand what will happen before it happens.
- Cross-platform behavior should preserve one React product surface and introduce native bridges only where web APIs are insufficient.

## 1. External Design References

The design below is based on the current state of mainstream agent products and official docs:

- OpenAI Codex manual: Codex supports user cancellation, image attachment in CLI, `AGENTS.md`, custom prompts, skills, MCP, plugins, and subagents. Local cache generated from `https://developers.openai.com/codex/codex-manual.md`.
- OpenAI GPT Builder: custom GPTs combine instructions, knowledge, capabilities, actions/apps, conversation starters, preview testing, versioning, and workspace controls. See [Creating and editing GPTs](https://help.openai.com/en/articles/8554397-creating-a-gpt/) and [Configuring actions in GPTs](https://help.openai.com/en/articles/9442513-gpt-actions-domain-settings-chatgpt-enterprise).
- Claude Code custom subagents: subagents have descriptions, prompts, tools, models, permissions, skills, MCP servers, memory, background execution, and isolation. See [Create custom subagents](https://docs.claude.com/en/docs/claude-code/sub-agents).
- Claude Code skills: skills are directories with `SKILL.md` plus optional scripts/resources/templates, discovered by description and optionally restricted by `allowed-tools`. See [Extend Claude with skills](https://docs.claude.com/en/docs/claude-code/skills).
- Claude Code MCP: MCP connects tools/data sources via stdio, HTTP, and other transports, with auth, resource references, and elicitation. See [Connect Claude Code to tools via MCP](https://docs.claude.com/en/docs/claude-code/mcp).
- MCP official docs: clients discover tools from connected servers and combine them into a tool registry; tool responses can contain rich multi-format content. See [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) and [MCP sampling](https://modelcontextprotocol.io/docs/concepts/sampling).
- Cursor rules/MCP: mainstream coding agents separate reusable rules, `AGENTS.md`, MCP config, and tool permissions. See [Cursor Rules](https://docs.cursor.com/context/rules-for-ai) and [Cursor MCP](https://docs.cursor.com/context/model-context-protocol).
- Capacitor APIs: native file handling differs from web Blob handling; Capacitor Filesystem notes Blob support is web-only for read/write results, and Camera supports multiple image selection. See [Capacitor Filesystem](https://capacitorjs.com/docs/apis/filesystem) and [Capacitor Camera](https://capacitorjs.com/docs/apis/camera).

## 2. Module A - Interrupt Conversation

### 2.1 Product Goal

Users must be able to interrupt a currently running agent reply when:

- the agent is going in the wrong direction;
- the user wants to add a correction;
- a long-running runtime task is no longer useful;
- the user changes conversation while background streams are running.

Interrupt is not retry, not failure, and not deletion. It is an explicit user terminal action:

```text
running -> interrupted
```

### 2.2 UX Contract

- While the current conversation has a pending or streaming agent message, the send button becomes a stop button.
- The user can still switch conversations; interrupt targets only the selected message/run.
- After interrupt succeeds, the message remains visible with partial content and a small terminal label such as `已打断`.
- The input unlocks and encourages a follow-up, for example "可以继续补充你的要求".
- No red failure frame and no retry button should appear for `interrupted`.
- If the stream has already finished, interrupt is idempotent and leaves `done` unchanged.

### 2.3 Backend Contract

Add an internal/public API endpoint in the next OpenAPI revision:

```http
POST /api/v1/messages/{message_id}/interrupt
```

Response:

```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "status": "interrupted",
  "interrupted_at": "2026-06-07T00:00:00Z",
  "reason": "user_requested"
}
```

Rules:

- Only the owner of the conversation can interrupt.
- If the message is `pending` or `streaming`, B1 marks an interrupt request and asks the active stream manager to cancel runtime work.
- If the message is already `done`, `error`, or `interrupted`, return 200 with current terminal state.
- If DB says `streaming` but no in-process stream session exists, do stale cleanup. Only explicit user interrupt should become `interrupted`; orphaned backend restart remains a retryable `error`.
- Persist partial message content before terminalization.
- Emit SSE terminal event:

```text
event: interrupted
data: {"message_id":"...","status":"interrupted"}
```

### 2.4 B1 State Machine

Extend message status:

```text
pending -> streaming -> done
pending -> streaming -> error
pending -> streaming -> interrupted
pending -> interrupted
```

Implementation notes:

- `StreamRunManager` owns a per-message cancellation token.
- `interrupt` sets token, then gives adapter/tool loop a short grace period.
- After grace period, B1 should terminate subprocesses if still alive.
- Persist `interrupted` atomically with latest accumulated content.
- `conversation busy` checks must treat `interrupted` as terminal and allow the next user message.

### 2.5 B2 Runtime Contract

All adapters should accept a cancellation signal:

- Claude Code SDK/CLI: cancel SDK query if supported; otherwise terminate child process.
- OpenCode/Codex CLI: terminate subprocess tree, collect stderr tail for diagnostics, but do not mark error if interrupt was user-requested.
- Builtin/ModelGateway: stop token streaming, do not continue tool calls.
- Orchestrator: propagate interrupt to active child attempt, mark attempt/task/run as `interrupted`, and write an event:

```text
orchestrator_run_interrupted
orchestrator_task_attempt_interrupted
```

Interrupt must not trigger planner retry, repair, or task fallback.

### 2.6 Frontend Contract

- `StreamSupervisor` must expose `interruptActiveStream(messageId)`.
- The active message bubble should show partial content and terminal state.
- `StreamingStatusBar` should switch from "正在处理" to "已打断".
- The stop button should be disabled while interrupt request is in flight.
- If the SSE connection closes before the interrupt response returns, hydrate decides final state.
- Mobile UI must place stop control where the send button already lives; do not introduce a second destructive-looking button.

### 2.7 Tests

B1:

- Interrupt `pending` message returns `interrupted` and clears busy.
- Interrupt `streaming` message cancels runtime and persists partial content.
- Interrupt already `done` message is idempotent and does not rewrite content.
- Orchestrator child attempt becomes `interrupted`, not `error`.

F:

- Send button becomes stop button during current conversation stream.
- Interrupted message shows partial content without retry.
- Switching conversations does not interrupt other streams.
- Hydrate from `interrupted` clears local active stream.

Manual smoke:

- Start long task, interrupt, then send a correction. New turn should start normally.

## 3. Module B - Web/iOS/Android File Upload

### 3.1 Product Goal

AgentHub should support Codex-like attachments:

- images for multimodal questions and UI references;
- zip/tar/gz archives for importing existing projects or assets;
- documents such as PDF, Markdown, CSV, JSON, and text;
- source packages that can be imported into the current conversation workspace.

Attachments are not only chat decorations. They can become:

- message context;
- read-only workspace assets;
- explicit workspace imports;
- skill packages;
- MCP configuration candidates.

### 3.2 Core Concepts

```text
Upload
  id
  owner_user_id
  conversation_id?
  purpose
  filename
  content_type
  size_bytes
  sha256
  storage_key
  safety_status
  created_at

MessageAttachment
  message_id
  upload_id
  role
  disposition
```

Suggested upload purposes:

```text
message_attachment
workspace_import
agent_knowledge
agent_icon
skill_package
mcp_config
```

### 3.3 API Design

Add in a future OpenAPI revision:

```http
POST /api/v1/uploads
Content-Type: multipart/form-data
```

Fields:

- `file`: required.
- `conversation_id`: optional; required for workspace import.
- `purpose`: required enum.
- `client_platform`: optional enum `web | ios | android | desktop`.

Response:

```json
{
  "id": "uuid",
  "filename": "mockup.png",
  "content_type": "image/png",
  "size_bytes": 123456,
  "sha256": "hex",
  "purpose": "message_attachment",
  "status": "ready",
  "preview": {
    "kind": "image",
    "width": 1280,
    "height": 720
  }
}
```

Message send should reference uploads by id:

```json
{
  "content": "参考这张图帮我做页面",
  "attachment_ids": ["upload-id-1"]
}
```

Download/delete:

```http
GET /api/v1/uploads/{upload_id}/download
DELETE /api/v1/uploads/{upload_id}
```

Workspace import:

```http
POST /api/v1/workspaces/{conversation_id}/imports
{
  "upload_id": "uuid",
  "mode": "copy" | "extract_archive",
  "target_path": "."
}
```

### 3.4 Storage and Safety

Local dev:

```text
data/uploads/<user_id>/<upload_id>/<filename>
```

Production:

- object storage is preferred;
- DB stores only metadata and storage key;
- workspace import copies or extracts into the conversation workspace.

Validation:

- MIME sniffing, extension allowlist, and SHA-256.
- Default max files per message: 10.
- Default max image/document size: 20 MB.
- Default max archive size: 100 MB.
- Default max extracted files: 2,000.
- Default max extracted total size: 300 MB.
- Reject archive path traversal (`../`, absolute paths, drive letters).
- Reject nested archives by default unless user explicitly imports again.
- Do not execute uploaded scripts during upload/import.
- Run secret scanning before using attachments as Agent knowledge when feasible.

### 3.5 Message ContentBlock

Add a content block:

```ts
type AttachmentBlock = {
  type: "attachment";
  upload_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  preview?: {
    kind: "image" | "archive" | "document" | "text" | "unknown";
    url?: string;
    width?: number;
    height?: number;
    entries_preview?: string[];
  };
};
```

For model routing:

- image attachments can be passed to multimodal model backends when supported;
- archives and documents are indexed or materialized into workspace only after explicit action;
- unsupported binary files are summarized as metadata until imported.

### 3.6 Frontend Web UX

Desktop web:

- drag and drop onto composer;
- paperclip file picker;
- paste image from clipboard;
- upload queue with progress, retry, and remove;
- thumbnail grid for images;
- archive card with file count after server inspection;
- send disabled while selected attachment upload is not `ready`.

Mobile web/PWA:

- paperclip opens native browser file chooser;
- camera/photo library entry for images where supported;
- compact attachment chips above composer;
- do not rely on drag/drop.

### 3.7 iOS and Android Interface

AgentHub should keep one React product surface. Native bridges are used only when the WebView cannot reliably provide file bytes or save downloads.

iOS:

- Use browser `<input type="file">` first in PWA/web.
- In Capacitor shell, use native document/photo picker for stable URI access.
- Copy picked files into app cache before upload.
- Stream multipart upload from file URI where possible; avoid base64 for large files.
- Respect iOS photo-library limited access and permission prompts.

Android:

- Use Android Photo Picker/Document Provider through browser input or Capacitor bridge.
- Handle `content://` URIs with persistable permission where needed.
- Stream upload from URI/cache file; avoid loading large archives into JS memory.
- Show clear error if the selected provider returns a virtual file that cannot be opened.

Bridge rule:

- Web Blob path remains default for web.
- Native path uses `Filesystem`/file transfer only when upload/download cannot be handled reliably by the WebView.
- Capacitor docs note Blob support is web-only for some Filesystem read/write results, so native large-file handling must prefer file URI streaming over base64 strings.

### 3.8 Workspace Import UX

For archive uploads:

1. Upload completes.
2. Server inspects archive safely and returns preview.
3. UI asks: "作为聊天附件" or "导入当前 Workspace".
4. Import requires explicit target path.
5. Workspace tree invalidates after import.

Archive import is not automatic because it changes workspace state.

### 3.9 Tests

B1:

- Upload metadata persisted with sha256.
- Reject oversized and disallowed MIME files.
- Reject zip slip archive.
- Workspace import extracts within sandbox only.
- Download requires owner permission.

F:

- Drag/drop, paste image, and picker upload queue.
- Mobile layout chips do not overlap composer.
- Send waits for upload readiness.
- Workspace import prompts before side effect.

Native smoke:

- iOS image pick and archive pick upload to backend.
- Android content URI upload of image/archive.
- Large file does not freeze UI.

## 4. Module C - Deep Custom Agent Builder

### 4.1 Product Goal

AgentHub should let a non-coding user create a useful Agent without writing JSON, YAML, or code.

The user should be able to say:

```text
我想要一个会帮我整理论文资料的 Agent，语气温和，能读 PDF，
能按我的模板输出，不能擅自改我的原文。
```

AgentHub should turn that into a validated Agent configuration with:

- name and avatar;
- role and behavior instructions;
- conversation starters;
- knowledge files;
- skills;
- MCP servers/tools;
- permissions;
- memory policy;
- runtime/model preference;
- test prompts and health checks.

### 4.2 Mainstream Capability Baseline

The builder should combine common patterns from mainstream agent systems:

- **Instructions/rules**: OpenAI GPTs, Codex `AGENTS.md`, Cursor rules, and Claude subagent prompts all use persistent instructions to shape behavior.
- **Knowledge/files**: GPT Knowledge and coding-agent docs let users attach reference materials.
- **Skills**: Claude/Codex style skills package reusable expertise in folders with `SKILL.md` and optional scripts/templates.
- **MCP/tools**: MCP exposes external tools, resources, prompts, and structured tool calls through standardized server connections.
- **Actions/apps**: GPT Actions connect APIs through schemas and auth; in AgentHub this maps to MCP or platform tools.
- **Permissions and scopes**: subagents/custom agents should have explicit tool allowlists, memory scopes, and workspace boundaries.
- **Preview/test**: custom agents need a preview prompt sandbox before publishing.

### 4.3 UX: No-code Builder

Wizard steps:

1. **Basics**
   - Agent name, icon, one-sentence purpose.
   - Template picker: "前端设计师", "代码审查", "论文助手", "客服助手", "部署助手", "数据分析".
2. **Role and behavior**
   - Plain-language questions:
     - "它主要帮你完成什么？"
     - "遇到不确定时应该追问还是自行决定？"
     - "它的语气应该像老师、同事、秘书还是专家？"
     - "它绝对不能做什么？"
   - UI writes structured instructions behind the scenes.
3. **Knowledge**
   - Upload files or choose existing workspace docs.
   - Mark each file as reference, policy, template, or examples.
4. **Skills**
   - Import skill package zip/folder with `SKILL.md`.
   - Choose from built-in skills.
   - Show "when this skill is used" in non-code language.
5. **MCP and tools**
   - Catalog of known MCP servers plus manual config.
   - Health check before enabling.
   - Tool permission checklist grouped by risk:
     - read-only;
     - write workspace;
     - run commands;
     - network/API;
     - deploy/publish;
     - external account data.
6. **Memory**
   - None, conversation-only, project memory, or user memory.
   - Explain what is remembered and how to delete it.
7. **Test and publish**
   - User tests with starter prompts.
   - AgentHub shows expected tools and actual tools used.
   - Publish as private, conversation-only, team-shared, or template.

### 4.4 Data Model Draft

```ts
type CustomAgentProfile = {
  id: string;
  owner_user_id: string;
  visibility: "private" | "team" | "template";
  display: {
    name: string;
    description: string;
    avatar_upload_id?: string;
    color?: string;
  };
  behavior: {
    role: string;
    goals: string[];
    tone: string;
    do_not_do: string[];
    clarification_policy: "ask_first" | "balanced" | "decide_with_defaults";
    output_style?: string;
    examples?: Array<{ input: string; ideal_output: string }>;
  };
  runtime: {
    kind: "builtin" | "external" | "model_gateway";
    provider?: "openai" | "deepseek" | "claude" | "codex" | "opencode" | string;
    model_preference?: string;
    effort?: "low" | "medium" | "high";
  };
  knowledge: Array<{
    upload_id: string;
    label: string;
    usage: "reference" | "policy" | "template" | "example";
  }>;
  skills: Array<{
    skill_id: string;
    source: "builtin" | "uploaded" | "workspace" | "marketplace";
    enabled: boolean;
    allowed_tools?: string[];
  }>;
  mcp_servers: Array<{
    id: string;
    transport: "stdio" | "http" | "sse" | "streamable-http";
    config_ref: string;
    auth_ref?: string;
    enabled_tools?: string[];
    health_status: "unknown" | "ready" | "unavailable";
  }>;
  permissions: {
    workspace_read: boolean;
    workspace_write: boolean;
    run_commands: "never" | "ask" | "auto_low_risk";
    network: "never" | "ask" | "allowlisted";
    deploy: "never" | "ask";
    external_accounts: "never" | "ask";
  };
  memory_policy: "none" | "conversation" | "project" | "user";
  starters: string[];
  validation_status: "draft" | "valid" | "invalid";
};
```

### 4.5 Skills Import Contract

Skill package shape:

```text
my-skill/
  SKILL.md
  scripts/
  templates/
  references/
```

Validation:

- `SKILL.md` required.
- YAML frontmatter required fields: `name`, `description`.
- Optional: `allowed_tools`, `version`, `author`, `license`.
- Package max size default: 50 MB.
- No executable code runs during import.
- Scripts require permission at runtime and run only inside workspace/runtime sandbox.
- Skill descriptions must be readable in the UI because model invocation depends on clear "when to use" text.

### 4.6 MCP Server Contract

Supported configuration:

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${secret:GITHUB_TOKEN}"
      }
    },
    "local-docs": {
      "type": "stdio",
      "command": "node",
      "args": ["server.js"]
    }
  }
}
```

Rules:

- Secrets are stored as secret refs, never plain text in prompts or Git.
- MCP servers are health-checked before use.
- Tool list is cached with version/mtime and refreshes on list-changed events where supported.
- User sees tools in friendly language before enabling.
- Destructive tools default to `ask`.
- For HTTP/OAuth MCP, auth flow must be explicit and revocable.
- MCP resources can be referenced as context; MCP tools can act.
- MCP elicitation requests must surface as UI prompts, not hidden model calls.

### 4.7 Orchestrator Integration

- Custom Agents become normal conversation members only after validation.
- Orchestrator sees:
  - display name;
  - capability profile;
  - runtime availability;
  - allowed tools;
  - current conversation membership.
- Group-scoped dispatch still applies. Orchestrator cannot call a custom Agent unless it is in the current conversation.
- If a custom Agent has disabled or unhealthy MCP servers/skills, Orchestrator should treat those capabilities as unavailable and explain why.
- Custom Agent creation/editing is a platform workflow, not an Orchestrator hidden side effect unless the user explicitly asks Orchestrator to create one and confirms.

### 4.8 Non-coder Copy Rules

Avoid:

```text
Edit YAML
Configure JSON schema
Set stdio transport
Tool allowlist
```

Prefer:

```text
这个 Agent 可以读取文件吗？
它可以修改你的 Workspace 吗？
它需要连接哪些外部工具？
这个技能什么时候应该被使用？
```

Advanced details can be visible behind "高级设置".

### 4.9 Tests

B1:

- Custom Agent CRUD with ownership.
- Upload knowledge file and link to agent.
- Skill package validation rejects missing `SKILL.md`.
- MCP config stores secret refs only.
- Health check status affects agent availability.

B2:

- Builtin custom Agent loads instructions, knowledge summary, skills, MCP tool registry, and permissions.
- Tool deny/allow policies are enforced.
- Orchestrator dispatch uses only conversation-scoped validated agents.
- Unhealthy MCP/skill does not become silently available.

F:

- Non-code wizard creates a valid Agent from natural-language answers.
- Advanced mode can import skill package and MCP config.
- Test sandbox shows what tools would be used.
- Mobile UI supports basic create/edit without complex tables.

Manual smoke:

- Create a "论文资料整理助手" without writing code.
- Upload a PDF/Markdown knowledge file.
- Add a read-only skill.
- Add a mock MCP server and see health check.
- Start a group chat and verify Orchestrator can dispatch only after adding the custom Agent.

## 5. Cross-module Architecture

### 5.1 Shared Principles

- Interrupt, upload, and custom Agent creation all introduce side effects. Side effects require explicit user action.
- Every long-running operation has a terminal state.
- Every terminal failure has visible, actionable content.
- Runtime availability must be probed, not inferred from config presence.
- Workspace changes happen only through workspace APIs or runtime tools with permission.

### 5.2 Suggested Delivery Order

1. Interrupt API and frontend stop control.
2. Upload metadata/storage API and web upload UI.
3. Workspace archive import.
4. iOS/Android upload bridge smoke.
5. Custom Agent data model and no-code wizard MVP.
6. Skill import validation.
7. MCP server catalog/config/health.
8. Orchestrator dispatch integration for custom Agents.

### 5.3 Documentation Updates Required During Implementation

When implementation starts, update:

- `docs/api-spec.md` and `shared/openapi.yaml` for new APIs/content blocks.
- `docs/b1/README.md` for B1 API/storage state.
- `docs/b2/spec/builtin-agent-framework.spec.md` for skills/MCP/custom Agent runtime behavior.
- `docs/b2/spec/orchestrator/core.spec.md` and `task-planning.spec.md` for interrupt and dispatch behavior.
- `docs/frontend/spec/frontend-capacitor-shell.spec.md` for native upload bridge decisions.
- `docs/frontend/spec/frontend-content-blocks.spec.md` for attachment blocks.

## 6. Open Questions

- Should `interrupted` be a new DB enum value or a terminal metadata flag on `error/done`? Recommendation: new enum value for clarity.
- Should upload storage be local filesystem only for MVP or object-storage-compatible from day one? Recommendation: local driver with object-storage interface.
- Should image attachments be passed directly to model backends or first stored and referenced by signed URL? Recommendation: store first, then adapter-specific materialization.
- Should custom Agent MCP support stdio in hosted production? Recommendation: local Docker/dev supports stdio; hosted production defaults to remote HTTP unless an admin-managed worker sandbox exists.
- Should skills be shared globally? Recommendation: start with owner-private and conversation/workspace scoped; marketplace later.
