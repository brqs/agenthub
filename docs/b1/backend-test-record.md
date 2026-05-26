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
