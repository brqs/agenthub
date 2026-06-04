# B1 Runtime Integration Handoff - 2026-05-31

## Current State

- Local repository: `C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github`
- Current branch: `b1/runtime-integration-e2e`
- Base synced from upstream: `brqs/main` at `617fece`
- Latest local commits before this handoff:
  - `d02f5b9 Merge upstream main into B1 integration branch`
  - `1498993 Fix verification environment for latest runtime features`

This branch contains the latest upstream architecture plus the B1 group conversation memory work.

## What Was Integrated

### 1. Upstream Main Sync

`brqs/main` was merged into `b1/runtime-integration-e2e`.

The upstream update includes major B2 and frontend changes:

- Orchestrator split from a large single file into `backend/app/agents/orchestrator/`.
- New Orchestrator structured memory tables and service.
- Workspace preview session support.
- Browser preview verification service.
- Stream layer split into smaller helpers.
- External runtime adapter updates for Claude Code, Codex, and OpenCode.
- Frontend v2 real-backend state and workspace UI updates.

One merge conflict occurred in:

```text
backend/app/services/context_compression.py
```

Resolution:

- Kept upstream `tool_call` block-to-text support.
- Kept B1 group-chat `[Agent: <agent_id>]` labeling support.

### 2. B1 Group Conversation Memory

Group conversations now use the same conversation-level memory path as single conversations.

Key behavior:

- `build_context()` detects `Conversation.mode == "group"`.
- Group context starts with a system message explaining that assistant history may come from multiple agents.
- Agent messages in group history are labeled as:

```text
[Agent: claude-code]
[Agent: codex-helper]
```

- Compression also preserves agent labels when summarizing group history.
- Pinned messages still enter context.
- `pending` and `error` messages remain excluded.

Important files:

```text
backend/app/services/context_builder.py
backend/app/services/context_compression.py
backend/tests/test_context_builder.py
backend/tests/test_stream_tool_calls.py
backend/tests/test_orchestrator.py
```

### 3. Verification Environment Fixes

After syncing upstream, full backend tests initially failed because the new upstream features expected environment pieces that Docker Compose did not provide yet.

Fixes added:

- `docker-compose.yml`
  - Added `./shared:/shared:ro` so backend OpenAPI contract tests can read `/shared/openapi.yaml`.

- `backend/Dockerfile`
  - Added Playwright Chromium and system dependency installation for browser preview verification.

- `backend/app/core/config.py`
  - Added a focused `noqa` comment for the container-local browser screenshot directory.

- `frontend/src/lib/types.gen.ts`
  - Regenerated from `shared/openapi.yaml`.

## Validation Results

Backend:

```bash
docker compose exec -T backend alembic upgrade head
# passed

docker compose exec -T backend python -m app.seeds.seed_agents
# passed

docker compose exec -T backend pytest -q
# 428 passed, 7 skipped, 1 warning

docker compose exec -T backend ruff check
# All checks passed
```

Frontend:

```bash
cd frontend
pnpm gen:types
# passed

$env:VITE_USE_MOCK_API='true'
$env:VITE_USE_MOCK_SSE='true'
pnpm exec vitest run
# 99 passed

pnpm lint
# passed

pnpm build
# passed, with existing Vite large chunk warning
```

Note:

- Frontend tests fail if `VITE_USE_MOCK_API` is not set to `true`, because some tests then attempt real API calls and receive `401`.
- This is a test-environment mode issue, not a backend regression.

## Known Caveats

- `docker compose build backend` could not be fully verified earlier because Docker Hub DNS/HTTPS access was temporarily failing.
- The running container was used to validate the updated code path after manually installing Playwright dependencies inside the container.
- If the next agent has stable Docker Hub access, rerun:

```bash
docker compose build backend
docker compose up -d --build
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

## Recommended Next Steps

1. Push the current branch to both remotes:

```bash
git push origin b1/runtime-integration-e2e
git push upstream b1/runtime-integration-e2e
```

2. Check the existing PR for `b1/runtime-integration-e2e` on `brqs/agenthub`.

3. If CI fails:

- First inspect whether Docker image build can access Docker Hub.
- Then check whether frontend tests are running with `VITE_USE_MOCK_API=true`.
- Finally inspect any real code failure.

4. Optional follow-up test:

Add one integration test that confirms B1 conversation memory and B2 Orchestrator structured memory can coexist in the same Orchestrator stream context without exceeding context budget.

