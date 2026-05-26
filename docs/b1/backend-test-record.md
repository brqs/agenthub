# B1 Backend Test Record

Date: 2026-05-25
Role: B1 Backend Core Engineer
Workspace: `C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github`

## Environment

- `.env` copied from `.env.example` and present in the project root.
- `JWT_SECRET` is configured.
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are still placeholders/empty locally. Current automated tests use the mock provider path and do not require live provider keys.
- Docker services were rebuilt and started with `docker compose up -d --build`.
- Database migrations were applied with `docker compose exec -T backend alembic upgrade head`.
- Built-in agents were seeded with `docker compose exec -T backend python -m app.seeds.seed_agents`.

## Deployment Verification

| Check | Command / URL | Result |
| --- | --- | --- |
| Backend health | `http://localhost:8000/health` | `200 {"status":"ok"}` |
| Swagger UI | `http://localhost:8000/docs` | `200 OK` |
| Alembic migration | `docker compose exec -T backend alembic upgrade head` | Passed |
| Built-in agent seed | `docker compose exec -T backend python -m app.seeds.seed_agents` | Passed, existing agents skipped |
| Backend pytest | `docker compose exec -T backend pytest` | `17 passed, 1 warning` |
| Ruff | `docker compose exec -T backend ruff check` | Passed |

## B1 Quality Items

| Item | Status | Coverage |
| --- | --- | --- |
| Validate `agent_ids` when creating conversations | Done | Rejects missing, duplicate, invalid, inaccessible, and invalid count combinations |
| Enforce `user_id` on conversation/message APIs | Done | Conversation read/update/delete/list and message list/send/update/delete/regenerate/stream check parent ownership |
| Password over bcrypt 72 bytes returns 422 | Done | Pydantic validators on register/login request schemas |
| Swagger auth uses Bearer Token | Done | `HTTPBearer` security scheme is exposed in OpenAPI |
| SSE success marks agent message `done` | Done | Stream generator persists final content and status |
| SSE error marks agent message `error` | Done | Missing agent, adapter error chunks, adapter lookup errors, and exceptions persist `error` |
| Pytest coverage added | Done | `backend/tests/test_b1_quality.py` |

## Added Tests

- `test_create_conversation_rejects_missing_agent`
- `test_create_conversation_rejects_other_users_agent`
- `test_message_and_conversation_routes_forbid_other_user_resources`
- `test_send_message_rejects_agent_outside_conversation`
- `test_password_over_bcrypt_limit_returns_422`
- `test_openapi_uses_http_bearer_security`
- `test_stream_success_marks_agent_message_done`
- `test_stream_error_marks_agent_message_error`

## Latest Result

```text
docker compose exec -T backend pytest
17 passed, 1 warning in 3.32s

docker compose exec -T backend ruff check
All checks passed!
```

## Pivot P3: Workspace Artifact E2E

Date: 2026-05-26

| Item | Status | Coverage |
| --- | --- | --- |
| Fake Agent receives `workspace_path` and writes HTML | Done | `tests/test_workspace_artifact_e2e.py` |
| SSE emits `tool_call` / `tool_result` / `done` | Done | E2E success case |
| `ToolCallBlock` and text block persist together | Done | DB message content assertion |
| Artifact tree exposes generated file | Done | `GET /api/v1/workspaces/{conv}/tree` |
| HTML artifact read supports iframe preview headers | Done | CSP / `X-Frame-Options` / `nosniff` assertions |
| Workspace violation error path persists safely | Done | E2E failure case |

P3 curl / Swagger manual checklist:

```bash
# 1. Start services and prepare DB
docker compose up -d --build
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents

# 2. Health and Swagger
curl http://localhost:8000/health
# Expected: {"status":"ok"}
# Open: http://localhost:8000/docs

# 3. Register / login and save token
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"b1_p3_demo","password":"P@ssw0rd!"}'

# 4. Create conversation, send message, then stream agent response
curl -N http://localhost:8000/api/v1/messages/<agent_message_id>/stream \
  -H "Authorization: Bearer <token>"

# 5. Verify artifact APIs
curl http://localhost:8000/api/v1/workspaces/<conversation_id>/tree \
  -H "Authorization: Bearer <token>"
curl http://localhost:8000/api/v1/workspaces/<conversation_id>/files/hello.html \
  -H "Authorization: Bearer <token>"
```

Latest P3 verification:

```text
docker compose exec -T backend pytest tests/test_workspace_artifact_e2e.py -q
2 passed

docker compose exec -T backend pytest tests/test_workspace_api.py tests/test_stream_tool_calls.py tests/test_workspace_artifact_e2e.py -q
26 passed

docker compose exec -T backend pytest -q
198 passed, 3 skipped, 1 warning

docker compose exec -T backend ruff check
All checks passed!
```

## Pivot P4: Workspace Edit Flow and AgentRegistry v2 Contract

Date: 2026-05-26

| Item | Status | Coverage |
| --- | --- | --- |
| Monaco-style file save writes back through Artifact API | Done | `tests/test_workspace_edit_flow_e2e.py` |
| Edited file can be read back immediately | Done | PUT overwrite + GET readback assertion |
| Next stream can read the edited file through `workspace_path` | Done | Fake Registry v2 adapter reads `src/App.tsx` |
| Repeated PUT remains workspace-idempotent | Done | Only one workspace row per conversation |
| Registry v2 adapter contract remains provider-agnostic | Done | Stream layer only depends on adapter v2 keyword args |
| Edited HTML artifact keeps iframe safety headers | Done | CSP / `X-Frame-Options` / `nosniff` assertions |

P4 handoff note:

- B1 keeps the public API unchanged.
- Frontend can save Monaco edits with `PUT /api/v1/workspaces/{conversation_id}/files/{path}`.
- If the user wants the Agent to continue based on the edited file, frontend should send a normal follow-up chat message after saving.
- B2 AgentRegistry v2 only needs to return adapters compatible with `BaseAgentAdapter.stream(..., workspace_path=..., tool_specs=...)`.

Latest P4 verification:

```text
docker compose exec -T backend pytest tests/test_workspace_edit_flow_e2e.py -q
4 passed

docker compose exec -T backend pytest tests/test_workspace_api.py tests/test_workspace_artifact_e2e.py tests/test_workspace_edit_flow_e2e.py -q
22 passed

docker compose exec -T backend pytest -q
202 passed, 3 skipped, 1 warning

docker compose exec -T backend ruff check
All checks passed!
```

## Pivot P2: SSE Tool Events

Date: 2026-05-26

| Item | Status | Coverage |
| --- | --- | --- |
| `StreamChunk` supports `tool_call` / `tool_result` | Done | `tests/test_stream_tool_calls.py` |
| B1 stream passes `workspace_path` to Adapter v2 | Done | FakeAdapter asserts workspace path under `WORKSPACE_BASE_DIR/{conversation_id}` |
| Tool events persist as `ToolCallBlock` | Done | `tool_call + tool_result(ok/error)` persisted in `messages.content` |
| Orphan tool events mark message `error` | Done | Missing result and unmatched result both covered |
| Tool output / arguments preview truncation | Done | 2048-character preview limit covered |
| ContentBlock schema updated | Done | `backend/app/schemas/message.py` and `shared/openapi.yaml` |

Latest P2 verification:

```text
docker compose exec -T backend pytest tests/test_stream_tool_calls.py -q
8 passed

docker compose exec -T backend pytest -q
196 passed, 3 skipped, 1 warning

docker compose exec -T backend ruff check
All checks passed!
```
