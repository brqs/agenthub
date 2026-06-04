# B1 Backend Test Record

Date: 2026-06-03
Role: B1 Backend Core Engineer
Workspace: `C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github`

## Current Baseline

当前 B1 主链路已经完成并合入 `main`：

- 认证、JWT、Swagger Bearer Token。
- Conversation / Message 用户权限校验。
- SSE `done` / `error` 状态持久化。
- Workspace 沙箱、文件树、读文件、写文件。
- SSE `tool_call` / `tool_result` 配对持久化为 `ToolCallBlock`。
- 前端二次编辑回写后，下一轮 Agent 继续使用同一 `workspace_path`。
- 单聊 / 群聊会话级上下文记忆与压缩。
- 群聊 Agent 旁观者身份提示与 `[Agent: <agent_id>]` 历史标签。
- ContentBlock block-level `agent_id` 归属持久化。
- Workspace preview、static release、source zip、container deployment API。
- Conversation 删除时清理 workspace preview / release / zip / deployment 资源。

## Required Local Startup Checklist

每次同步主仓库后，先执行：

```bash
docker compose up -d --build backend
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents
```

原因：当前迁移链已经到：

```text
4b5c6d7e8f90
```

如果没有执行 `alembic upgrade head`，deployment 相关测试和 API 会因为缺少
`workspace_deployments.release_token`、runtime metadata 等字段而失败。

## Latest Automated Verification

Date: 2026-06-03

```text
docker compose exec -T backend alembic current
4b5c6d7e8f90 (head)

docker compose exec -T backend pytest -q
521 passed, 7 skipped, 1 warning

docker compose exec -T backend ruff check
All checks passed!
```

中途曾出现过 deployment 相关测试失败，根因是本地数据库未执行最新 Alembic migration。
执行 `alembic upgrade head` 后，相关回归测试通过：

```text
docker compose exec -T backend pytest \
  tests/test_orchestrator_platform_tools.py \
  tests/test_stream_content_blocks.py \
  tests/test_workspace_api.py -q

52 passed
```

## B1 Quality Items

| Item | Status | Coverage |
| --- | --- | --- |
| Validate `agent_ids` when creating conversations | Done | Rejects missing, duplicate, invalid, inaccessible, and invalid count combinations |
| Enforce `user_id` on conversation/message APIs | Done | Conversation read/update/delete/list and message list/send/update/delete/regenerate/stream check parent ownership |
| Password over bcrypt 72 bytes returns 422 | Done | Pydantic validators on register/login request schemas |
| Swagger auth uses Bearer Token | Done | `HTTPBearer` security scheme is exposed in OpenAPI |
| SSE success marks agent message `done` | Done | Stream generator persists final content and status |
| SSE error marks agent message `error` | Done | Missing agent, adapter error chunks, adapter lookup errors, and exceptions persist `error` |
| Workspace path sandbox | Done | Traversal, absolute paths, sensitive paths, `.agenthub`, symlink escape, file size limits |
| Workspace HTTP API | Done | Tree, read file, write file, preview, deployment, download |

## Workspace / Artifact / Deployment

| Capability | Status | Coverage |
| --- | --- | --- |
| Workspace lazy create | Done | `tests/test_workspace_service.py` |
| File tree / read / write API | Done | `tests/test_workspace_api.py` |
| HTML file safety headers | Done | CSP / `X-Frame-Options` / `nosniff` assertions |
| Frontend edit writeback | Done | `tests/test_workspace_edit_flow_e2e.py` |
| Static preview lifecycle | Done | `tests/test_workspace_api.py` |
| Preview snapshot isolation | Done | Sensitive path and snapshot rebuild tests |
| Browser preview verifier API | Done | `POST /preview/verify` coverage |
| Static site deployment | Done | immutable release, stable URL, stop invalidation |
| Source zip deployment | Done | sensitive path exclusion, download, expiry cleanup |
| Container deployment MVP | Done | policy validation, worker path, stop handling |
| Cleanup on conversation delete | Done | preview / release / zip / workspace resource cleanup |

## SSE / ContentBlock Contract

| Capability | Status | Coverage |
| --- | --- | --- |
| `tool_call` / `tool_result` stream events | Done | `tests/test_stream_tool_calls.py` |
| Tool events persist as `ToolCallBlock` | Done | ok / error / orphan / truncation cases |
| `DeploymentStatusBlock` content type | Done | stream autostart preview / formal tool fallback tests |
| Block-level `agent_id` attribution | Done | `tests/test_stream_content_blocks.py` |
| Metadata fallback `metadata["agent_id"]` | Done | accumulator tests |
| Old content blocks without `agent_id` | Done | backwards-compatible serialization |
| Agent stream terminalization | Done | cancelled / disconnected / exception paths mark message `error` |
| Stale stream busy cleanup | Done | `POST /messages` clears expired pending/streaming messages before busy check |

Bug note:

- The single-chat lockup seen during local manual testing was caused by an agent message
  remaining in `streaming` after the SSE/runtime path failed to reach a final `done` or
  `error`.
- B1 now owns the invariant that every claimed agent message must eventually become
  `done` or `error`; B2 owns runtime behavior, and F owns clear user feedback/retry UI.

## Conversation Memory

| Capability | Status | Coverage |
| --- | --- | --- |
| Single conversation memory | Done | context builder / compression tests |
| Group conversation shared memory | Done | `tests/test_context_builder.py` |
| Group observer system prompt | Done | current agent / other agent semantics tests |
| `[Agent: <agent_id>]` history labels | Done | regular, pinned, compressed memory cases |
| Pending / error messages excluded | Done | group exclusion tests |
| Orchestrator structured memory coexistence | Done | stream handoff and Orchestrator memory tests |

Design note:

- B1 conversation memory is scoped to one `conversation_id`.
- Orchestrator structured memory is B2-owned but injected through B1 stream context helper.
- B1 does not infer attribution by parsing text; it only stores structured `agent_id` fields.

## B1 / F Integration Checklist

The backend side is ready for frontend integration:

- `GET /api/v1/workspaces/{conversation_id}/tree`
- `GET /api/v1/workspaces/{conversation_id}/files/{path}`
- `PUT /api/v1/workspaces/{conversation_id}/files/{path}`
- `POST /api/v1/workspaces/{conversation_id}/preview`
- `GET /api/v1/workspaces/{conversation_id}/preview`
- `DELETE /api/v1/workspaces/{conversation_id}/preview`
- `POST /api/v1/workspaces/{conversation_id}/preview/verify`
- `POST /api/v1/workspaces/{conversation_id}/deployments`
- `GET /api/v1/workspaces/{conversation_id}/deployments`
- `GET /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}`
- `DELETE /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}`
- `GET /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}/download`

Frontend still needs full manual verification for:

- deployment history rendering.
- deployment status block interaction.
- source zip download.
- stop deployment.
- mobile workspace/deployment flows.

## B1 / B2 Integration Checklist

Backend tests cover the B1 side of the B2 contract:

- B1 passes `workspace_path` to adapter v2.
- B1 persists tool events from adapters.
- B1 preserves block-level `agent_id`.
- B1 injects group observer context before Orchestrator structured memory.
- B1 exposes platform preview / deployment APIs used by Orchestrator tools.

Recommended real smoke before final demo:

```text
User -> Orchestrator:
1. generate an HTML artifact
2. preview it
3. deploy it as static_site
4. package source zip
```

Expected:

- SSE contains `tool_call`, `tool_result`, `web_preview` or `deployment_status`.
- DB agent message status is `done`.
- Workspace deployment row exists.
- Frontend can fetch deployment status and download source zip.

## Debug API Safety

Development-only endpoints:

- `GET /api/v1/conversations/{id}/memory`
- `GET /api/v1/conversations/{id}/orchestrator-runs`
- `GET /api/v1/conversations/{id}/orchestrator-runs/{run_id}`

Expected production behavior:

- non-development environment hides debug endpoints with `404`.
- endpoints require current user ownership.
- responses must not expose provider API keys, environment variables, CLI args, or SDK options.

## Remaining B1 Follow-ups

| Priority | Item | Owner |
| --- | --- | --- |
| P0 | Frontend deployment API manual integration verification | F + B1 support |
| P0 | Real Orchestrator deployment smoke on server | B2 + B1 support |
| P1 | Server runbook update after every deployment-related env change | B1 |
| P1 | API docs drift check after OpenAPI/schema changes | B1 |
| P2 | Production debug endpoint smoke | B1 |
