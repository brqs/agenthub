# B1 文档索引

> B1 负责后端核心平台：配置、数据库、API、服务层、Workspace 与后端质量验证。

| 文档 | 用途 |
|---|---|
| [backend-cloud-setup.md](backend-cloud-setup.md) | 后端云端联调环境记录 |
| [backend-test-record.md](backend-test-record.md) | B1 后端测试记录 |
| [spec/stream-error-status.spec.md](spec/stream-error-status.spec.md) | SSE error 状态持久化协同规则 |
| [pivot-demo-script.md](pivot-demo-script.md) | B1 Workspace / Artifact / SSE demo 讲解脚本 |
| [spec/workspace-sandbox.spec.md](spec/workspace-sandbox.spec.md) | Workspace 沙箱隔离规范 |
| [spec/file-upload-backend.spec.md](spec/file-upload-backend.spec.md) | 文件上传后端 API、存储、安全扫描、AttachmentBlock 与 Workspace 导入契约 |
| [spec/group-observer-context.spec.md](spec/group-observer-context.spec.md) | 群聊 Agent 旁观者上下文与记忆契约 |
| [spec/message-content-block-attribution.spec.md](spec/message-content-block-attribution.spec.md) | ContentBlock block-level `agent_id` 归属契约 |
| [../spec/next-major-modules.spec.md](../spec/next-major-modules.spec.md) | 下一阶段 B1 相关契约：interrupt API、upload storage/API、自定义 Agent 配置持久化 |

## 当前 B1 能力快照

| 能力 | 状态 | 主要验证 |
|---|---|---|
| 认证 / 会话 / 消息权限 | Done | `tests/test_b1_quality.py` |
| SSE 状态持久化 | Done | `tests/test_b1_quality.py`, `tests/test_stream_tool_calls.py` |
| Workspace 沙箱 | Done | `tests/test_workspace_service.py` |
| Workspace Artifact API | Done | `tests/test_workspace_api.py` |
| 前端二次编辑回写 | Done | `tests/test_workspace_edit_flow_e2e.py` |
| Preview / Deployment API | Done | `tests/test_workspace_api.py`, `tests/test_workspace_container_release.py` |
| ToolCallBlock 持久化 | Done | `tests/test_stream_tool_calls.py` |
| ContentBlock `agent_id` 归属 | Done | `tests/test_stream_content_blocks.py` |
| 单聊 / 群聊上下文记忆 | Done | `tests/test_context_builder.py` |
| 群聊旁观者身份强化 | Done | `tests/test_context_builder.py`, `tests/test_stream_tool_calls.py` |
| 对话打断 API / 终态 | Done | `POST /messages/{id}/interrupt`、`message.status=interrupted`、StreamRunManager interrupt token、`tests/test_b1_quality.py` |
| 运行中提交排队 | Done | `message.status=queued`、`message_queue_entries`、`POST /conversations/{id}/queued-messages`、`tests/test_conversation_api.py` |
| 需求对齐 turn option | Done | `messages.turn_options.requirement_alignment`、Send/Queue/Update queued request fields、`ClarificationBlock.mode=requirement_alignment` |
| Conversation control plane | Done | `conversation_turn_controls`、`turn_control` block、guidance/side-chat/queue action APIs、`tests/test_conversation_api.py` |
| 文件上传与 Workspace 导入 | Planned | `uploads` metadata/storage、multipart upload、archive safe extraction、owner permission |
| 自定义 Agent 配置持久化 | Planned | Agent profile、knowledge uploads、skill package metadata、MCP secret refs / health status |

## 每次同步后必跑

```bash
docker compose up -d --build backend
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

当前期望迁移版本：

```text
4b5c6d7e8f90
```

如果 deployment / preview 相关测试出现 `workspace_deployments.<column> does not exist`，
优先检查是否漏跑 `alembic upgrade head`。

相关全局文档：

| 文档 | 用途 |
|---|---|
| [../api-spec.md](../api-spec.md) | API 契约说明 |
| [../tech-architecture.md](../tech-architecture.md) | 后端架构上下文 |
| [../team-division.md](../team-division.md) | B1 任务边界 |
## 2026-06-07 Interrupt API Contract

B1 now owns user interrupt as a neutral terminal lifecycle state:

- `POST /api/v1/messages/{msg_id}/interrupt`
- `message.status=interrupted`
- SSE terminal event `interrupted`
- Orchestrator child terminal event `message_interrupted`
- `interrupted` clears conversation busy and does not trigger retry/regenerate/error UI

## 2026-06-07 Queued Next Turn Contract

B1 now persists same-conversation queued user turns:

- `message.status=queued` is used only for user messages waiting behind an active agent response.
- `message_queue_entries` records queue order and dispatch state.
- `POST /api/v1/conversations/{conversation_id}/queued-messages` is allowed only while the conversation has an active `pending` or `streaming` agent response.
- `PATCH /api/v1/queued-messages/{message_id}` and `DELETE /api/v1/queued-messages/{message_id}` are allowed only before dispatch.
- Current `POST /messages` busy protection remains unchanged; queueing is explicit and does not bypass serial execution.
- After `done`, `error`, or `interrupted`, B1 dispatches the queue head and may include `queued_next` in the terminal SSE payload.
- Queued messages do not enter the active turn's context. They become normal `done` user messages only when dispatched as the next turn.

## 2026-06-08 Requirement Alignment Turn Option

B1 now persists the user-controlled `需求对齐` choice per turn:

- `messages.turn_options` stores `requirement_alignment: off | strict`.
- `POST /api/v1/conversations/{id}/messages`, queued-message create, and queued-message update accept the same option.
- User message and paired agent message receive the same option.
- Queued dispatch copies the queued user message option to the new pending agent message.
- The default is `off`; automatic Orchestrator clarification only runs when the current turn option is `strict`.

## 2026-06-07 Conversation Control Plane Contract

B1 now persists active-turn controls separately from next-turn queue entries:

- `conversation_turn_controls` stores guidance, side-chat, queue-action, and stop-and-run control state.
- `message_queue_entries.position` is the queue ordering source; dispatch uses `position, created_at, id`.
- `turn_control` content blocks allow the frontend to recover guidance/side-chat state after refresh.
- `POST /api/v1/messages/{active_message_id}/guidance` is accepted only for active Orchestrator messages that support safe-point guidance.
- `POST /api/v1/messages/{active_message_id}/side-chat` creates visible side-chat messages but B1 context building excludes them from future main-task context.
- Queue reorder/merge/convert-to-guidance/stop-and-run APIs only operate on undispatched queued messages in the current conversation.
- Terminal stream cleanup marks unapplied guidance as `expired`, preserving the fact that the user tried to guide a turn that finished first.
- These controls never create a second active agent message in the same conversation.
