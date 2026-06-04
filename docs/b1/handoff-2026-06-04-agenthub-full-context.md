# AgentHub Handoff - 2026-06-04

> Purpose: help the next agent take over this AgentHub thread with enough project, technical, and collaboration context to continue work without relying on the chat history.
>
> Scope: local handoff document. The user previously said handoff files do not need to be submitted to GitHub unless explicitly requested.

## 0. First Rules For The Next Agent

1. Talk to the user in Chinese by default. The user often asks for plain-language explanations and concrete steps.
2. Default to executing concrete tasks, not only proposing plans, unless the user explicitly asks for analysis/design only.
3. Before code changes, read the relevant `AGENTS.md`, spec, skill, OpenAPI, and tests. Do not assume an old chat answer is still the source of truth.
4. Do not commit or push handoff files unless the user explicitly says to include them.
   - 2026-06-04 update: the user explicitly requested this handoff file be updated and included with the current stream recovery work.
5. Never commit `.env`, real API keys, runtime state, generated workspace artifacts, or local logs.
6. The user expects automatic conflict handling when pushing PRs, but if a conflict affects product/architecture decisions, explain the options and ask.
7. Preserve unrelated dirty worktree changes. There are many active edits from B1/B2/F work; do not revert them.

## 1. Local Repository And Environment

Repo path:

```text
C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github
```

Current project is a fork of:

```text
brqs/agenthub
```

The user also has their own fork/remote. Historically, they want PRs to the upstream `brqs/agenthub`, and branches should preferably include `b1` in the branch name.

Local services:

```text
Backend API: http://localhost:8000
Backend docs: http://localhost:8000/docs
Frontend dev: http://localhost:5173
PostgreSQL: localhost:5432
Redis: localhost:6379
```

Docker Compose is the preferred backend environment because PostgreSQL/Redis and deployment runtime behavior depend on it.

Common backend startup:

```powershell
cd C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github
docker compose up -d --build
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents
```

Common frontend startup:

```powershell
cd C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github\frontend
pnpm install
pnpm dev --host 0.0.0.0 --port 5173
```

If `pnpm install` says `packages field missing or empty`, check that the command is being run in the actual frontend package root and inspect `frontend/package.json`. This has happened before when the frontend package layout changed or the wrong directory was used.

## 2. Must-Read Collaboration Documents

Read these first:

```text
AGENTS.md
docs/README.md
docs/development-plan.md
docs/team-division.md
docs/tech-architecture.md
docs/api-spec.md
docs/product-design.md
docs/spec/agent-runtime-pivot.adr.md
```

For B1 contract/API/SSE changes:

```text
docs/ai-skills/b1-contract-change/SKILL.md
docs/b1/README.md
docs/b1/backend-test-record.md
docs/b1/spec/workspace-sandbox.spec.md
docs/b1/spec/group-observer-context.spec.md
docs/b1/spec/message-content-block-attribution.spec.md
shared/openapi.yaml
```

For B2 runtime/orchestrator work:

```text
docs/ai-skills/b2-ai-collaboration/SKILL.md
docs/b2/README.md
docs/b2/spec/agent-runtime-adapter.spec.md
docs/b2/spec/external-runtime-adapters.spec.md
docs/b2/spec/external-direct-chat-routing.spec.md
docs/b2/spec/orchestrator/core.spec.md
docs/b2/spec/orchestrator/task-planning.spec.md
docs/b2/spec/orchestrator/tool-calling.spec.md
docs/b2/spec/orchestrator/memory-context.spec.md
```

For deployment checks:

```text
docs/ai-skills/backend-deploy/SKILL.md
docs/b2/spec/deployment-release-backend.execution.spec.md
docs/b2/spec/orchestrator-native-deployment.execution.spec.md
docs/b1/backend-cloud-setup.md
```

For frontend rendering/workflow:

```text
docs/frontend/README.md
docs/frontend/test-plan.md
docs/frontend/spec/frontend-chat-demo.spec.md
docs/frontend/spec/frontend-content-blocks.spec.md
docs/frontend/spec/orchestrated-message-rendering.spec.md
docs/b2/frontend-release-handoff.md
```

## 3. High-Level Project State

AgentHub pivoted from a simple multi-provider LLM chat wrapper into a multi-agent runtime orchestration platform.

Current architecture:

```text
F  - frontend chat UI, stream supervisor, artifact display, agent management
B1 - backend platform core, auth, conversations, messages, SSE gateway, workspace sandbox,
     artifact APIs, deployment/preview APIs, content persistence, OpenAPI contract
B2 - agent runtime layer, external runtime adapters, builtin agents, orchestrator,
     task planning, tool calling, direct-chat routing
```

Important architecture rule:

```text
B1 should not know whether an agent is Claude Code, Codex, OpenCode, builtin, or orchestrator.
B1 talks to BaseAgentAdapter v2 and persists StreamChunk results.
B2 owns runtime behavior.
F consumes SSE and persisted ContentBlocks.
```

## 4. B1 Capabilities Already Built

The B1 backend core has implemented, in broad terms:

1. Auth and user isolation.
2. Conversation and message APIs.
3. Agent message lifecycle: `pending -> streaming -> done/error`.
4. SSE stream endpoint.
5. Stream content accumulation and persistence.
6. `ToolCallBlock` persistence from `tool_call/tool_result`.
7. Workspace sandbox:
   - per-conversation root
   - safe read/write/list
   - path traversal protection
   - symlink escape protection
   - sensitive path protection
8. Workspace Artifact API:
   - tree
   - file read
   - file write
9. Static preview and deployment APIs.
10. Container deployment backend support.
11. Conversation memory and compression:
   - single conversation memory
   - group conversation memory
   - hybrid LLM memory with rules fallback
12. Group observer context:
   - agent messages are labeled
   - current agent can read other agents' previous messages as an observer
13. ContentBlock attribution:
   - optional `agent_id` per block
   - frontends should render with `block.agent_id ?? message.agent_id`
14. SSE/concurrency hardening is in progress or recently implemented:
   - active stream ownership should be `message_id + conversation_id`
   - avoid cross-conversation stream delivery
   - stale cleanup and terminalization of stuck messages
   - in-process stream run manager lets multiple SSE clients attach to the same running agent message
   - client disconnects should not cancel the backend runtime task

## 5. B2 Capabilities Known From Recent Work

B2 has implemented or was working on:

1. External runtime adapters:
   - Claude Code
   - Codex
   - OpenCode
2. Direct-chat routing for simple questions:
   - greetings
   - identity/model questions
   - simple capability questions
   - history/task questions
   These should not start expensive file/runtime workflows.
3. Orchestrator:
   - task planning
   - sub-agent dispatch
   - task cards / task events
   - workspace conflict summaries
   - concise default visibility for sub-agent output
4. Runtime isolation:
   - per-message runtime context
   - separate runtime state directories
   - avoid cross-conversation Claude Code/Codex/OpenCode contamination
5. Preview/deploy command filtering:
   - external agents should generate files, not suggest or start random preview servers.

Known product expectation:

```text
Simple input should get a simple answer.
Complex build/deploy/file tasks can trigger Orchestrator planning and sub-agent execution.
```

## 6. Frontend Capabilities Known From Recent Work

F has implemented or was working on:

1. Chat UI with single and group conversations.
2. StreamSupervisor / active stream tracking.
   - StreamSupervisor is global under AppLayout and can subscribe to multiple message streams concurrently.
3. Message hydration merge rules:
   - do not overwrite local streaming content with empty server snapshots.
   - preserve active streaming messages when switching conversations.
   - hydrated `pending`/`streaming` agent messages are recoverable active streams; terminal `done/error` snapshots clear active stream state.
4. Message pagination:
   - default load recent messages.
   - scroll up to load older messages.
5. TaskCardBlock rendering for orchestrator events.
6. ContentBlock rendering:
   - text, code, diff, web/file/artifact, tool blocks.
7. Frontend session cleanup:
   - logout should clear auth, agents, conversations, messages, React Query cache.

Known frontend bugs previously discussed and current expectations:

1. Switching conversations during streaming must not interrupt other conversations' active streams.
2. A stale `streaming` status can keep the top status bar alive forever; frontend recovery should resubscribe, while B1 should terminalize orphaned streaming messages.
3. 409 SSE responses must be treated as fatal/no-retry, not infinite reconnect.
4. Refresh recovery is best-effort: if the same backend process still owns the in-memory stream session, the frontend can reattach; if the process lost the session, B1 converts the orphaned `streaming` message to retryable `error`.
5. Frontend must never route SSE chunks by 鈥渃urrently open conversation鈥? chunks belong to the `message_id` stream they came from.

## 7. Current Docker Deployment Work Completed On 2026-06-04

The user chose option 1 for local container deployment:

```text
Install Docker CLI inside backend container and mount host Docker socket.
```

Changes made:

```text
backend/Dockerfile
  - install docker-cli and docker.io

docker-compose.yml
  - mount /var/run/docker.sock into backend
  - set DEPLOYMENT_CONTAINER_PUBLIC_BASE_URL=http://localhost for local dev
  - set DEPLOYMENT_CONTAINER_HEALTHCHECK_BASE_URL=http://host.docker.internal

backend/app/core/config.py
  - add deployment_container_healthcheck_base_url

backend/app/services/workspace_container_release.py
  - use separate internal healthcheck base URL instead of always 127.0.0.1

.env.example
  - add container deployment environment variables
```

Why this was needed:

1. Backend container originally had no `docker` binary.
2. Backend container originally had no host Docker socket.
3. After Docker worked, container healthcheck still failed because backend checked `127.0.0.1:{host_port}` inside the backend container. Published ports are on the host Docker side, so local Docker Desktop needs `host.docker.internal:{host_port}`.

Validation already run:

```text
docker --version inside backend: OK
docker ps inside backend: OK
GET /health: OK
alembic current: 4b5c6d7e8f90 (head)
container deployment smoke: published
host fetch http://localhost:8081: 200 OK, body "ok"
targeted backend tests: 13 passed
ruff targeted files: passed
```

Security warning:

```text
Mounting /var/run/docker.sock lets backend control host Docker.
This is acceptable for trusted local development/testing, but must be reviewed before public/server deployment.
```

## 8. Current Dirty Worktree Situation

The worktree is dirty with many changes across B1/B2/F. Do not assume all changes are yours. Before committing, inspect:

```powershell
git status --short
git diff --stat
git diff -- <file>
```

Known untracked handoff files:

```text
docs/b1/handoff-2026-05-31-runtime-integration.md
docs/b1/handoff-2026-06-01-contentblock-attribution.md
docs/b1/handoff-2026-06-04-agenthub-full-context.md
```

Default rule: do not include handoff files in PRs unless the user says otherwise.

2026-06-04 exception: the user explicitly requested this handoff document be updated and included when pushing the current concurrent stream recovery work.

## 9. Known User Preferences And Working Agreements

1. The user is B1 Backend Core Engineer, but often asks for whole-project analysis.
2. The user wants beginner-friendly explanations when asking 鈥渨hat should I do鈥?or 鈥渨hy鈥?
3. The user often asks for a plan first, then says `PLEASE IMPLEMENT THIS PLAN`.
4. Once implementation is requested, do the work end-to-end: code, tests, review, and clear outcome.
5. For PR titles/descriptions, Chinese is preferred unless the target repo convention demands English.
6. The user does not want real secrets committed.
7. The user may provide keys in chat. Treat them as local `.env` only. Do not echo them back in full.
8. The user expects local web testing, not just backend tests.
9. The user values AI collaboration artifacts:
   - spec
   - skill
   - rules
   - collaboration log
10. When a workflow repeats, update a skill. When a contract changes, update a spec. When a stable rule emerges, update `AGENTS.md` or an appropriate rule document.

## 10. Important Implementation Conventions

### SSE and message lifecycle

All live stream data belongs to:

```text
message_id + conversation_id
```

Never route or persist stream output based on the currently visible frontend conversation.

Backend stream endpoint rules:

```text
pending    -> can start a real backend runtime stream
streaming  -> attach to in-process StreamRunManager session when present
streaming  -> if no in-process session exists, terminalize as retryable error
done/error -> cannot re-stream; use regenerate/retry path
```

The frontend may have multiple active streams across conversations. The backend still allows only one `pending` or `streaming` agent message per conversation; send/regenerate must return `409 CONVERSATION_BUSY` for the same conversation while another agent response is active.

Any agent message must eventually become:

```text
done
or
error
```

Never leave a conversation permanently locked by stale `pending` or `streaming`.

### ContentBlock attribution

B1 persists attribution, B2 produces attribution, F consumes attribution.

Rendering rule:

```text
effectiveAgentId = block.agent_id ?? message.agent_id
```

Do not infer attribution by parsing markdown text such as `@agent`.

### Workspace and deployment

All workspace actions are scoped to:

```text
/workspaces/{conversation_id}
```

For local container deployment:

```text
public URL: http://localhost:{port}
backend healthcheck: http://host.docker.internal:{port}
```

For server deployment, override:

```text
DEPLOYMENT_CONTAINER_PUBLIC_BASE_URL=http://<server-ip-or-domain>
DEPLOYMENT_CONTAINER_HEALTHCHECK_BASE_URL=http://127.0.0.1
```

or another address appropriate to the server network.

### Orchestrator behavior

Desired UX:

```text
simple question -> simple answer
complex task -> task planning and sub-agent dispatch
```

Default orchestrator/sub-agent output should be concise:

```text
show task card / agent switch / tool status / final summary
hide large sub-agent raw text/code unless debug mode says otherwise
```

## 11. Common Test Commands

Backend core:

```powershell
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

B1/B2 stream and workspace targeted:

```powershell
docker compose exec -T backend pytest `
  tests/test_b1_quality.py `
  tests/test_stream_tool_calls.py `
  tests/test_stream_content_blocks.py `
  tests/test_workspace_api.py `
  tests/test_workspace_container_release.py `
  -q
```

B2 orchestrator/runtime targeted:

```powershell
docker compose exec -T backend pytest `
  tests/test_orchestrator.py `
  tests/test_orchestrator_tool_calling.py `
  tests/test_claude_code_external_adapter.py `
  -q
```

Frontend:

```powershell
cd frontend
pnpm gen:types
pnpm exec vitest run
pnpm build
```

Container deployment smoke:

1. Start Docker Desktop.
2. `docker compose up -d --build`.
3. Create user/conversation.
4. Write `server.py` and `Dockerfile` into workspace.
5. `POST /api/v1/workspaces/{conversation_id}/deployments` with:

```json
{
  "kind": "container",
  "container_port": 8000,
  "health_path": "/"
}
```

Expected local response:

```text
status = published
runtime_kind = docker
url = http://localhost:8081
GET http://localhost:8081 -> ok
```

## 12. Known Bugs / Risk Areas To Watch

1. SSE stuck status:
   - If UI shows 鈥滄鍦ㄧ粍缁囧洖澶嶁€?forever, inspect DB message status and backend stream logs.
   - Likely causes: adapter never yielded done/error, direct-chat stream timeout missing, frontend activeStream not cleared, or stale `streaming` snapshot.

2. Cross-conversation contamination:
   - If one group chat receives another group's generated content, inspect runtime isolation, workspace path, and StreamSupervisor routing.
   - Runtime state must be per message/conversation.

3. Orchestrator over-processing:
   - If `@orchestrator 浣犲ソ` triggers planning, B2 intent classification is too aggressive.
   - Simple Q&A should use direct answer.

4. Container deployment:
   - If backend says `[Errno 2] No such file or directory`, check `docker` exists inside backend.
   - If image builds but deployment fails healthcheck, check `DEPLOYMENT_CONTAINER_HEALTHCHECK_BASE_URL`.
   - If frontend sees server IP in local dev, check `DEPLOYMENT_CONTAINER_PUBLIC_BASE_URL`.

5. Frontend auth/session cache:
   - Logout must clear auth, agents, conversations, messages, and query cache.
   - If OpenCode Helper appears only for one user, check both frontend cache and seed data.

6. Handoff files:
   - Keep local unless explicitly requested.

## 13. Suggested Next Agent Startup Checklist

1. Read this handoff.
2. Read `AGENTS.md`.
3. Read the relevant skill/spec based on the user's next request.
4. Run:

```powershell
cd C:\Users\qq\Documents\Codex\2026-05-25\c-users-qq-desktop-agenthub-github\agenthub-github
git status --short
docker compose ps
```

5. If working on backend:

```powershell
docker compose exec -T backend alembic current
docker compose exec -T backend python -m app.seeds.seed_agents
```

6. If working on frontend:

```powershell
cd frontend
pnpm install
pnpm exec vitest run
```

7. Before committing:
   - exclude `.env`
   - exclude handoff files unless requested
   - current exception: include this handoff for the 2026-06-04 concurrent stream recovery push
   - run targeted tests and relevant lint/build
   - update spec/skill/log if the task changes contracts or reusable workflow

## 14. What To Tell The User If They Ask "Where Are We?"

Short version:

```text
AgentHub 宸茬粡浠庢櫘閫氬璇濆櫒鎺ㄨ繘鍒板彲鏈湴杩愯鐨勫 Agent 鍗忎綔骞冲彴搴曞骇銆?B1 鐨勬牳蹇冭兘鍔涘熀鏈氨缁細浼氳瘽銆丼SE銆乄orkspace銆丄rtifact銆佽蹇嗐€乀oolCallBlock銆丄ttribution銆侀儴缃?棰勮銆?B2 宸叉帴鍏ュ閮?runtime 鍜?Orchestrator锛屼粛闇€缁х画鎵撶（鐪熷疄浠诲姟鎴愬姛鐜囥€佺畝鍗曢棶绛斿垎娴佸拰杩愯闅旂銆?F 宸叉湁鑱婂ぉ涓荤晫闈㈠拰娴佸紡灞曠ず锛屼絾浠嶉渶瑕佺户缁畬鍠勬鍦ㄦ墽琛岀姸鎬併€佷换鍔″崱銆丄rtifact/Deployment 鐨勭敤鎴蜂綋楠屻€?褰撳墠鏈湴 Docker 鐜宸茬粡鑳借 backend 璋冪敤瀹夸富 Docker锛屽苟璺戦€?container deployment smoke銆?```

## 15. PR Hygiene

When the user asks to push/PR:

1. Sync upstream first:

```powershell
git fetch upstream
git fetch origin
```

2. Inspect branch and dirty changes.
3. Do not include handoff docs unless requested.
   - For the concurrent stream recovery task on 2026-06-04, the user requested including `docs/b1/handoff-2026-06-04-agenthub-full-context.md`.
4. Prefer a branch name like:

```text
b1/<short-topic>
```

5. Chinese PR title/description is acceptable and usually preferred by the user.
6. PR description should include:
   - Summary
   - Key Changes
   - Tests
   - Owner boundary if B1/B2/F contract is involved
   - Notes about any intentionally excluded local files

## 16. Final Reminder

This project is partly evaluated on AI collaboration practice, not only code. Good work should leave behind:

```text
code
tests
spec
skill/rules when reusable
collaboration log for important decisions
clear PR description
```

Do not let the chat history become the only place where decisions live.
