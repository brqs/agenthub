# AgentHub Frontend Real Backend Integration Plan

> Target backend: `http://111.229.151.159:8000`
> Source checked: `http://111.229.151.159:8000/openapi.json`
> Date: 2026-05-27
> Owner: F

This plan is for connecting the existing frontend to the deployed backend. Do not run a local backend for this work. Use the deployed Swagger/OpenAPI as the live contract and keep Mock mode available for demo fallback.

## Context Read Before Development

Read these before implementing:

- `AGENTS.md`
- `frontend/README.md`
- `docs/frontend/development-plan.md`
- `docs/frontend/api-adapter-plan.md`
- `docs/frontend/spec/frontend-content-blocks.spec.md`
- `docs/product-design.md`
- Deployed OpenAPI: `http://111.229.151.159:8000/openapi.json`

Useful existing frontend files:

- `src/lib/api.ts`
- `src/lib/env.ts`
- `src/lib/sse.ts`
- `src/lib/types.ts`
- `src/lib/adapters/*`
- `src/hooks/useAgents.ts`
- `src/hooks/useConversations.ts`
- `src/hooks/useMessages.ts`
- `src/hooks/useSendMessage.ts`
- `src/hooks/useStream.ts`
- `src/stores/chatStore.ts`
- `src/stores/agentStore.ts`
- `src/components/agents/RightAgentPanel.tsx`
- `src/components/artifact/*`
- `src/components/chat/MessageInput.tsx`
- `src/components/chat/MessageBubble.tsx`
- `src/components/blocks/ContentRenderer.tsx`

## Backend Contract Snapshot

The deployed backend exposes:

| Area | Endpoints | Frontend use |
| --- | --- | --- |
| Auth | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` | Login/register, token validation |
| Conversations | `GET/POST /api/v1/conversations`, `GET/PATCH/DELETE /api/v1/conversations/{conv_id}` | Sidebar, create chat, pin/archive/delete |
| Messages | `GET/POST /api/v1/conversations/{conv_id}/messages`, `PATCH/DELETE /api/v1/messages/{msg_id}`, `POST /api/v1/messages/{msg_id}/regenerate` | Message list, send, pin, delete, retry |
| SSE | `GET /api/v1/messages/{msg_id}/stream` | Stream pending agent message |
| Agents | `GET/POST /api/v1/agents`, `GET/PATCH/DELETE /api/v1/agents/{agent_id}` | Agent list and CRUD |
| Workspaces | `GET /api/v1/workspaces/{conversation_id}/tree`, `GET/PUT /api/v1/workspaces/{conversation_id}/files/{path}` | File tree, artifact preview, editor save |
| Context compression | `/api/v1/context-compression/config*` | Optional later settings panel |

Important deployed contract details:

- Auth uses HTTP Bearer tokens.
- `CreateAgentRequest.provider` only accepts `claude_code`, `codex`, `opencode`, `builtin`.
- `AgentOut.provider` can also include legacy/raw providers: `mock`, `claude`, `deepseek`, `openai`, `custom`.
- `ConversationOut.agent_ids`, `is_pinned`, and `is_archived` are not marked required in the generated OpenAPI, but the UI depends on them. Keep `src/lib/types.ts` overrides or normalize responses.
- `MessageOut.content` supports `text`, `code`, `diff`, `web_preview`, `file`, `tool_call`.
- `WorkspaceTreeNode.type` is `directory | file`; current mock workspace tree uses `dir | file`, so adapters must normalize for UI components or components must be updated.
- OpenAPI currently describes SSE/file responses loosely as JSON schemas. Treat SSE as `text/event-stream` and workspace file reads as raw `Blob`/text based on response headers.

## Environment For Real Backend

Recommended `.env.local` for remote backend through Vite proxy:

```bash
VITE_API_BASE_URL=
VITE_DEV_PROXY_TARGET=http://111.229.151.159:8000
VITE_USE_MOCK_API=false
VITE_USE_MOCK_SSE=false
```

Direct backend mode is also possible:

```bash
VITE_API_BASE_URL=http://111.229.151.159:8000
VITE_USE_MOCK_API=false
VITE_USE_MOCK_SSE=false
```

Prefer proxy mode during development so same-origin `/api/...` and SSE behavior stays close to deployment.

## Current Frontend Gap Analysis

Already mostly ready:

- Axios client with JWT interceptor.
- Auth adapter exists.
- Conversations, messages, agents adapters exist for core list/create/send flows.
- Hooks already have Mock/API mode branches.
- Real SSE subscription exists and sends `Authorization`.
- Chat page starts stream from returned `agent_message.id`.
- `ToolCallBlock` UI exists.

Must fix before reliable real-backend demo:

1. Group chat send fallback
   - Current `useSendMessage` only sends `target_agent_id` when the user types `@agent-id`.
   - Deployed backend requires `target_agent_id` for group conversations.
   - If no mention exists, send `orchestrator` when present in `conversation.agent_ids`; otherwise send the first agent id.

2. Remove render-time dependency on mock agents
   - `MessageInput`, `MessageBubble`, `ContentRenderer`, `RightAgentPanel`, and orchestrator status helpers still call `mockData.getAgent` or read `mockAgents`.
   - Real API mode should resolve agents from `agentStore`.

3. Persist pin/archive actions
   - `toggleMessagePin`, `toggleConversationPin`, and `toggleConversationArchive` are currently local-only.
   - Add API mutations:
     - `PATCH /api/v1/messages/{msg_id}` with `{ is_pinned }`
     - `PATCH /api/v1/conversations/{conv_id}` with `{ is_pinned }` or `{ is_archived }`

4. Real retry/regenerate flow
   - Current retry resets the old message locally and streams the old id.
   - Real flow must call `POST /api/v1/messages/{msg_id}/regenerate`, replace/remove the old agent message, then stream the new message id.

5. Workspace artifact API
   - `RightAgentPanel` still uses `mockWorkspace`.
   - Add `src/lib/adapters/workspaces.ts` and hooks for tree/file reads.
   - Show real workspace files after tool calls and after stream completion.

6. Response normalization
   - Normalize optional defaults for conversations, agents, and messages at adapter boundaries.
   - This keeps UI code from needing defensive checks everywhere.

7. SSE polish
   - Handle `heartbeat` explicitly as no-op.
   - Split mock SSE generation out of `src/lib/sse.ts` only if the touched code grows.
   - On `done`, optionally refetch the final message or message list so persisted `ToolCallBlock`/status matches DB.

8. Agent create copy and validation
   - `AgentsPage` copy still says "Mock 创建流程".
   - Ensure create dialog sends a valid config for `builtin`, `claude_code`, `codex`, and `opencode`.

## Development Phases

### Phase 1: Remote Backend Smoke Path

Goal: login/register, list real agents, create conversation, send message, receive SSE.

Tasks:

- Update `LoginPage` to use `authAdapter.login/register`.
- Confirm `AuthGuard` works against remote `/auth/me`.
- Keep `.env.example` guidance aligned with remote backend.
- Fix group chat fallback target agent.
- Add adapter response normalizers:
  - `normalizeConversation`
  - `normalizeAgent`
  - `normalizeMessage`
- Make `MessageInput` receive available agents from real `useAgents()`/store instead of `mockAgents`.

Acceptance:

- With `VITE_USE_MOCK_API=false` and `VITE_USE_MOCK_SSE=false`, a fresh user can register or login.
- Agent list shows deployed backend agents.
- Creating a single conversation succeeds.
- Creating a group conversation succeeds.
- Sending in group mode without an explicit mention does not 422.
- SSE updates the pending agent message and exits with `done` or visible `error`.

### Phase 2: Real Mutations For Existing UI

Goal: all visible sidebar/message actions persist to backend.

Tasks:

- Extend `src/lib/adapters/conversations.ts`:
  - `updateConversation`
  - `deleteConversation`
  - convenience `pinConversation`, `archiveConversation` if useful.
- Extend `src/lib/adapters/messages.ts`:
  - `updateMessage`
  - `deleteMessage`
  - `regenerateMessage` already exists; wire it into UI.
- Add hooks:
  - `useUpdateConversation`
  - `useUpdateMessage`
  - `useRegenerateMessage`
- Replace direct local-only toggles in `ChatPage` with mutations in API mode.
- Keep optimistic UI only if rollback is simple; otherwise update after successful response and invalidate queries.

Acceptance:

- Pinning/unpinning a conversation survives refresh.
- Archiving a conversation moves it out of the active list and survives refresh.
- Pinning/unpinning a message survives refresh and appears in the right panel pinned list.
- Retry creates a new agent message id and streams that id.

### Phase 3: Workspace And Artifact Preview

Goal: show real files generated by Agent tool calls.

Tasks:

- Add `src/lib/adapters/workspaces.ts`:
  - `getWorkspaceTree(conversationId, maxDepth?)`
  - `readWorkspaceFile(conversationId, path)` returning `{ content, mimeType, size? }`
  - `writeWorkspaceFile(conversationId, path, content, mimeType?)`
- Add hooks:
  - `useWorkspaceTree`
  - `useWorkspaceFile`
  - optional `useWriteWorkspaceFile`
- Normalize backend tree:
  - backend `directory` -> frontend directory node
  - preserve file `path`, `size`, `mime_type`
- Update `WorkspaceFileTree` types away from mock-only `WorkspaceNode`.
- Update `ArtifactPreview` types away from `MockArtifactFile`.
- In API mode, refetch workspace tree after stream `done` or after a `tool_result` for file-writing tools.

Acceptance:

- Right panel shows real workspace root and file tree.
- Selecting text/code/HTML files reads from backend.
- HTML files render in iframe preview.
- Empty workspace state is clear and not labeled Mock.
- File read errors show a non-crashing error state.

### Phase 4: Agent Registry Real Mode

Goal: Agent management page behaves honestly against deployed backend.

Tasks:

- Update page copy to remove Mock wording in API mode.
- Ensure `useCreateAgent` sends backend-valid provider/config.
- Add update/delete wiring if not already complete in UI controls.
- For built-in agents, keep read-only UI behavior.
- Validate create form by provider:
  - `builtin`: needs usable `model_backend`, `max_iterations`, optional `mcp_servers`.
  - `claude_code`: `sdk_options`.
  - `codex`: `model`, `timeout_seconds`.
  - `opencode`: `command`, `args`, `timeout_seconds`.

Acceptance:

- Built-in and user-created agents render separately.
- Creating a valid custom agent succeeds.
- Invalid config displays backend validation error.
- Built-in agents cannot be modified or deleted in UI.

### Phase 5: Hardening And Demo Readiness

Goal: make real backend mode stable enough for presentation.

Tasks:

- Add empty/loading/error states for:
  - conversations
  - messages
  - agents
  - workspace tree
  - workspace file read
  - SSE stream failure
- Stop showing Mock labels in API mode.
- Verify browser console has no avoidable errors.
- Add focused tests:
  - adapter normalizers
  - group fallback target agent
  - stream tool call/result block updates
  - workspace tree normalization
  - retry/regenerate flow
- Run:
  - `pnpm tsc --noEmit`
  - `pnpm lint`
  - `pnpm test`

Acceptance:

- Real mode and Mock mode both still work.
- Refreshing after major actions preserves server-backed state.
- The app can demonstrate: login -> agents -> conversation -> stream -> tool call -> workspace preview.

## Suggested Implementation Order

1. Response normalizers and type cleanup.
2. Group send fallback + real agent resolution in message input/bubbles.
3. LoginPage adapter cleanup.
4. Pin/archive/message pin real mutations.
5. Regenerate real flow.
6. Workspace adapter + hooks + right panel real data.
7. Agent page copy/config polish.
8. Tests and final browser smoke.

This order gets the chat loop working first, then makes existing controls persistent, then adds artifact value.

## Data Normalization Notes

Keep normalizers close to adapters, not components.

Expected defaults:

```ts
Conversation:
  agent_ids: []
  is_pinned: false
  is_archived: false
  last_message_preview: null

Agent:
  avatar_url: ''
  capabilities: []
  config: {}
  is_builtin: false

Message:
  agent_id: null
  content: []
  reply_to_id: null
  status: 'done'
  is_pinned: false
```

Avoid scattering `?? []` and `?? false` through UI components.

## SSE Event Handling

Expected event names:

- `start`
- `block_start`
- `delta`
- `block_end`
- `done`
- `error`
- `agent_switch`
- `heartbeat`
- `tool_call`
- `tool_result`

Rules:

- `heartbeat`: no-op.
- `tool_call`: append `ToolCallBlock` with pending state.
- `tool_result`: find matching block by `call_id`, set status/output/error.
- `error`: mark message error and stop stream.
- `done`: mark message done, stop stream, invalidate/refetch messages and workspace tree.
- If a stream closes without `done`, show a recoverable error state and allow retry.

## Workspace Preview Notes

Use `api.get(..., { responseType: 'blob' })` or `fetch` with Authorization for file reads.

For rendering:

- Text-like MIME: read as text and show in `<pre>` or future Monaco.
- `text/html`: show in sandboxed iframe.
- Other binary: show file metadata and download/open action only.

Backend may include safety headers for HTML; the frontend should still use a restrictive iframe sandbox.

## Open Questions For Backend Team

These do not block Phase 1:

- Should remote OpenAPI mark `ConversationOut.agent_ids`, `is_pinned`, `is_archived`, `MessageOut.content/status/is_pinned`, and `AgentOut.capabilities/config/is_builtin/avatar_url` as required?
- Should SSE OpenAPI advertise `text/event-stream` instead of generic JSON?
- Should workspace file `GET` advertise raw text/html/octet-stream content types in the generated OpenAPI?
- Is `orchestrator` guaranteed to be seeded in deployed backend?
- Which deployed Agent providers are expected to work with live runtime credentials today?

## Definition Of Done

Real backend integration is complete when:

- `VITE_USE_MOCK_API=false` and `VITE_USE_MOCK_SSE=false` can run the main chat workflow against `http://111.229.151.159:8000`.
- No visible UI copy incorrectly says Mock in real mode.
- Core mutations persist after refresh.
- SSE stream renders text/code/tool events without corrupting message content.
- Workspace files generated by agents can be browsed and previewed.
- Mock mode remains usable for offline demo fallback.
- `pnpm tsc --noEmit`, `pnpm lint`, and `pnpm test` pass.
