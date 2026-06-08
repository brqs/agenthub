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
14. `clarification` ContentBlock persistence:
   - used by Orchestrator requirement clarification before planner/runtime dispatch
   - persisted by the stream accumulator and included in OpenAPI message content union
15. SSE/concurrency hardening is in progress or recently implemented:
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
   - clarification gate before direct planning/runtime dispatch
   - slash commands: `/grill-me`, `/grill-with-docs`, `/setup-matt-pocock-skills`
   - waiting clarification must not create `task_card`, `agent_switch`, or runtime attempts
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

Clarification gate expectation:

```text
Underspecified artifact/build/design/code requests may first receive a structured
clarification card. The card asks one high-value question and provides a recommended
answer. Recommendation chips only fill the input; side effects require explicit positive confirmation such as "按这个做" or "按默认开始实现". Negated phrases like "不要按默认" must not continue.

Pending clarification replies are routed before handling: current-answer, reference-context, new-topic, explicit-switch, control, or ambiguous. New topics ask for direction confirmation instead of being swallowed as answers.

`/grill-with-docs` and `/setup-matt-pocock-skills` only write the current
conversation workspace. They must not modify AgentHub's main repository files.
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
   - `clarification` card with question, reason, recommended answer, option chips, history, and summary.
   - clarification option chips only fill the input box; the user still sends the answer manually.
7. Frontend session cleanup:
   - logout should clear auth, agents, conversations, messages, React Query cache.
8. MessageInput:
   - slash command suggestions for `/grill-me`, `/grill-with-docs`, `/setup-matt-pocock-skills`.

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

### Orchestrator delegation truth contract

Orchestrator must not claim delegation unless the stream contains the matching execution facts.

```text
delegation language -> task_card or agent_switch in the same message stream
```

Artifact/design/build requests such as "design a web snake game" must enter task dispatch. If LLM planner output is invalid, empty, or unavailable, B2 should use deterministic task fallback before considering any direct-answer path. If no current conversation agent can execute the request, return an explicit retryable `error`; never finish as `done` with text that promises future delegation.

Direct answer remains only for greeting, identity, capability, and simple meta questions. Group Orchestrator dispatch is conversation-scoped: it may only schedule agents present in the current conversation unless a future public product change explicitly adds cross-conversation/global dispatch.

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

2026-06-04 Workspace reliability update:

- The Workspace tab and deployment history are separate facts. Deployment
  history reads `workspace_deployments`; the Workspace file browser reads the
  live filesystem tree under `/workspaces/{conversation_id}`.
- Frontend must keep tree errors and file-preview errors separate. A failed
  `GET /workspaces/{conversation_id}/files/{path}` should only show a file
  preview error and retry action; it must not hide the tree or deployment
  history behind "Workspace failed to load".
- `WorkspaceService.get_or_create` is expected to repair stale DB roots by
  resetting `workspaces.root_path` to the current
  `settings.workspace_base_dir / conversation_id` and initializing the
  directory.
- Local dev DB was found with many test rows whose `root_path` pointed at
  `/tmp/pytest-of-root/...`; those are pytest pollution, not lost user
  workspaces. Do not delete real user conversations or `/workspaces/...`
  directories when cleaning this up.
- Pytest now refuses to run against the default development database
  `agenthub` unless `AGENTHUB_ALLOW_DEV_DB_TESTS=1` is explicitly set. The
  preferred path is an isolated test database/schema.
- Useful diagnostics:
  `GET /api/v1/workspaces/{id}/tree`,
  `GET /api/v1/workspaces/{id}/files/{path}`,
  `select conversation_id, root_path from workspaces where conversation_id='<id>';`,
  and
  `select kind, status, download_url, error from workspace_deployments where conversation_id='<id>';`.

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

Backend pytest must use an isolated test database/schema. If a maintainer
intentionally runs a one-off targeted test against the local dev DB, set
`AGENTHUB_ALLOW_DEV_DB_TESTS=1` for that command and inspect any created rows.

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

4. Orchestrator false delegation:
   - If Orchestrator says it will delegate/call a specialist but there is no `task_card`, no `agent_switch`, and no `orchestrator_runs` row, inspect task intent detection and planner-failure fallback.
   - Artifact/design requests must not fall back to direct-answer text.

5. Container deployment:
   - If backend says `[Errno 2] No such file or directory`, check `docker` exists inside backend.
   - If image builds but deployment fails healthcheck, check `DEPLOYMENT_CONTAINER_HEALTHCHECK_BASE_URL`.
   - If frontend sees server IP in local dev, check `DEPLOYMENT_CONTAINER_PUBLIC_BASE_URL`.

6. Frontend auth/session cache:
   - Logout must clear auth, agents, conversations, messages, and query cache.
   - If OpenCode Helper appears only for one user, check both frontend cache and seed data.

7. Handoff files:
   - Keep local unless explicitly requested.

8. OpenCode runtime availability:
   - Orchestrator can now genuinely dispatch artifact tasks to sub-agents, so
     `[Errno 2] No such file or directory` on `opencode-helper` means the
     backend container lacks the `opencode` CLI, not a fake-delegation bug.
   - Backend Docker must install Node.js/npm and `opencode-ai`; verify with
     `docker compose exec backend opencode --version`.
   - OpenCode credentials must come from backend `.env` provider keys or from
     `docker compose exec backend opencode auth login`; compose persists login
     state in the `opencode-state` volume.
   - Orchestrator stream context marks unavailable OpenCode runtime as
     `runtime_status=unavailable`, and task planning must skip it instead of
     selecting it as a fallback agent.
9. Claude Code runtime availability:
   - Claude Code runs inside the backend container through `claude_agent_sdk`
     when present, not through the user's host-side interactive chat session.
   - Auth may come from backend `.env` provider keys (`ANTHROPIC_*` /
     `CLAUDE_*`) or from persisted CLI login state in the `claude-state`
     compose volume.
   - Shared auth state lives at `$AGENTHUB_CLAUDE_AUTH_DIR` and should contain
     `.claude.json` and/or `.claude/`; the adapter copies only those files into
     each per-message isolated runtime HOME.
   - Verify with:
     `docker compose exec backend python -c "import claude_agent_sdk; print('sdk ok')"`,
     `docker compose exec backend sh -lc 'ls -la $AGENTHUB_CLAUDE_AUTH_DIR'`,
     and `docker compose exec backend env | grep -E 'ANTHROPIC|CLAUDE|AGENTHUB_CLAUDE'`.
   - If Claude Code is unauthenticated, Orchestrator should treat
     `claude-code` as unavailable for dispatch and show a retryable runtime
     error. The UI should not expose `Claude Code returned an error result:
     success`.

### 12.6 Orchestrator Group Scope And Structured Memory Fix

2026-06-05 update:

1. Group conversation dispatch is now a hard scope boundary.
   - `conversation.agent_ids` is the only source of schedulable sub-agents for
     group Orchestrator streams.
   - `available_agents=[]` is authoritative. It means there are no runnable
     current-conversation implementation agents and must not fall back to global
     `managed_agent_ids` or `default_sub_agents`.
   - The stream context always passes scoped `available_agents`,
     `managed_agent_ids`, `available_agents_authoritative=true`, and
     `conversation_scoped_agents=true`.
   - Planner, ReAct, tool-loop, and static fallback code must all use the same
     scoped candidate rule. This prevents a group containing only
     `orchestrator + claude-code` from silently calling `opencode-helper`.

2. Existing built-in Orchestrator config is self-healed on backend startup.
   - Stale local DB rows may still contain `planner_model_backend=claude` and
     `react_trace_visible=true` from older seeds.
   - Backend startup upgrades the built-in `orchestrator` row to
     `planner_model_backend=deepseek`, `answer_model_backend=deepseek`, and
     `react_trace_visible=false` without changing user-created agents.

3. Direct-answer must preserve Orchestrator structured memory.
   - The memory context message beginning with
     `Previous Orchestrator structured memory:` must remain in direct-answer
     model input.
   - Queries such as "执行完成了吗", "刚刚的任务", "上一个任务", and "我指刚刚"
     are answered deterministically from the latest `orchestrator_runs`,
     `orchestrator_tasks`, and `orchestrator_task_attempts` in the same
     conversation.

### 12.7 Empty Error Blocks And Claude Runtime Probe

2026-06-05 update:

1. SSE `event:error` must persist visible content.
   - A terminal error is not only a transient SSE event. B1 must append a safe
     text block to `message.content` before setting `status=error`, even when
     the adapter failed before producing any normal block.
   - The same helper is used for adapter `event:error`, accumulator errors,
     timeout/cancel/internal errors, missing agents, and no-runnable-agent
     failures.
   - Existing `task_card` blocks are finalized as failed before the error text
     is appended. Equivalent error text should not be duplicated.
   - Frontend keeps a legacy fallback for `status=error && content=[]` so old
     polluted rows no longer render as an empty red box.

2. Claude Code runtime availability is actively probed.
   - `.env` credentials or `$AGENTHUB_CLAUDE_AUTH_DIR/.claude.json` /
     `.claude/` only make the runtime a candidate. File presence alone is not
     proof of login.
   - `claude_code_runtime_status` now runs a short backend-container probe with
     the same isolated HOME and shared-auth-copy contract used by real adapter
     execution. Results are cached briefly and invalidated by auth/env
     fingerprint changes.
   - Auth failures such as `Not logged in`, `Please run /login`, and
     `Claude Code returned an error result: success` normalize to the same
     retryable authentication message.
   - Manual CLI smoke must set the shared auth HOME:
     `docker compose exec backend sh -lc 'HOME=$AGENTHUB_CLAUDE_AUTH_DIR claude -p "只回复 OK" --output-format text'`.

### 12.8 Claude Code Read-Before-Write Workspace Contract

2026-06-05 update:

1. Conversation workspaces are persistent product state.
   - Do not clear or recreate a workspace for each new artifact task.
   - A later task may overwrite `index.html`, `styles.css`, `app.js`, or other
     files produced by an earlier task in the same conversation.

2. Claude Code requires read-before-write for existing files.
   - External runtime prompts must say that existing target files should be
     read or inspected before they are overwritten.
   - Sub-agent task messages include a lightweight workspace inventory with
     root-relative filenames and expected artifact paths. This context is
     injected even when `include_history=false` because it is execution
     environment state, not chat history.
   - The inventory must not include host paths or large file contents.

3. Read-before-write failures are recoverable once.
   - Tool output containing `File has not been read yet. Read it first before
     writing to it.` is classified as `read_before_write_required`.
   - If the first Claude Code attempt fails for this reason, Orchestrator
     retries the same task once with the same Agent and previous-attempt
     context. It must not use a non-conversation fallback Agent.
   - If retry succeeds, the run can finish `done`. If retry fails, the run and
     message remain `error`, with the user-facing summary preferring the
     read-before-write explanation over a later idle-timeout wrapper.
   - A direct-chat shortcut success only proves the QA/direct-answer path. It
     does not prove Claude SDK/CLI artifact runtime availability.
   - These status answers must not create a new task plan or promise delegation.

### 12.9 OpenCode Runtime Idle Timeout And Artifact Boundary

2026-06-05 update:

1. `External runtime exceeded idle_timeout_seconds` for OpenCode usually means
   AgentHub saw no stdout events for the idle window, not that the `opencode`
   process was never started.
   - Container smoke confirmed `opencode` is installed and can write files.
   - Failed Pac-Man runs emitted early tool events, then went silent until the
     external runtime idle watchdog killed the subprocess.
   - OpenCode logs showed the default model path selecting
     `deepseek/deepseek-v4-pro`, which can spend a long time in a later model
     step without emitting JSON events.

2. OpenCode default execution should be bounded and file-list driven.
   - `opencode-helper` now defaults to `model=deepseek/deepseek-chat`.
   - `opencode-helper` seed config uses `idle_timeout_seconds=360` and
     `max_runtime_seconds=600`; keep the hard timeout so genuinely stuck
     runtimes are still cleaned up.
   - The adapter passes `--model <config.model>` when no custom `args` are
     configured. Custom `args` remain an explicit escape hatch.

3. Prompt contract for static artifacts:
   - If the task names required artifact files such as `index.html`,
     `styles.css`, and `app.js`, OpenCode must create those exact
     workspace-relative files.
   - Empty workspace is not a reason to ask "what files should I create" when
     the current user request already describes the product and files.
   - OpenCode should write the requested artifacts, do at most a concise
     verification pass, and then summarize. It should not keep iterating on
     optional refinements after the requested files exist.

4. Useful smoke checks:

```powershell
docker compose exec backend opencode --version
docker compose exec backend opencode auth list
docker compose exec backend sh -lc 'rm -rf /tmp/opencode-smoke && mkdir -p /tmp/opencode-smoke && opencode run --format json --model deepseek/deepseek-chat --dir /tmp/opencode-smoke "创建 index.html、styles.css、app.js 三个文件，完成后简短总结"'
docker compose exec backend python -m app.seeds.seed_agents
```

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

## 17. Next Major Modules Draft (2026-06-07)

The user requested documentation-first planning for three next modules:

1. interruptible conversations, similar to Codex-style user cancellation;
2. web/iOS/Android file uploads for images, archives, documents, and workspace imports;
3. deep custom Agent creation for non-coding users, including role/function customization, knowledge files, skills, MCP servers, permissions, and testing.

Primary spec:

```text
docs/spec/next-major-modules.spec.md
```

Important handoff notes:

- This turn updated architecture/spec docs only; implementation code and OpenAPI were intentionally not changed.
- B1 should start from interrupt API, upload metadata/storage, safe archive extraction, and custom Agent persistence.
- B2 should start from runtime cancellation, attachment materialization, skills/MCP interpretation, permission policy, and group-scoped Orchestrator dispatch for validated custom Agents.
- F should start from stop-button UX, upload queue/cross-platform picker behavior, attachment blocks, Workspace import confirmation, and no-code custom Agent wizard.
- Capacitor upload constraints are recorded in `docs/frontend/spec/frontend-capacitor-shell.spec.md`.
## 2026-06-07 Handoff Addendum: User Interrupt Is Implemented

Conversation interrupt is now a first-class lifecycle terminal state.

- Public API: `POST /api/v1/messages/{msg_id}/interrupt`.
- Response state: `interrupted | already_terminal | interrupting`.
- Message status: `pending | streaming | done | error | interrupted`.
- SSE terminal events: top-level `interrupted`; Orchestrator child message `message_interrupted`.
- `StreamRunManager` is now shared by the stream route and interrupt route. It owns per-message runtime session state, subscriber queues, terminal state, and the `interrupt_event`.
- User Stop differs from client disconnect. Switching conversations, refreshing subscribers, StrictMode remount, and transport close must not interrupt backend runtime work.
- Pending agent messages without an active runtime can be finalized as `interrupted`. Streaming messages with an active runtime set the session interrupt event and wait briefly for terminalization. Streaming messages without a session remain stale/orphan cleanup and become retryable `error`, not fake user interrupt.
- Interrupted content preserves accumulated blocks. If no content exists, B1 writes a neutral text fallback instead of an empty red box.
- Running `task_card`, `process`, and process steps are finalized as `interrupted`.
- Orchestrator interrupt uses `interrupt_active_run()` and `interrupt_open_messages()`: active run/task attempts/child messages become `interrupted`; replanner, repair, fallback, and success summary are skipped.
- Frontend Stop replaces Send only for the current conversation active stream. Other conversation streams continue. Interrupted messages render neutral `已打断`, clear active stream state, and never show retry.

Validation already covers pending interrupt, active streaming interrupt with partial content preservation, non-agent rejection, interrupted content block finalization, frontend Stop behavior, stream/store terminal handling, and neutral rendering.

## 2026-06-07 Handoff Addendum: Orchestrator Clarification Repeat Semantics

Auto clarification remains the intended behavior for broad artifact/build requests such as "design a web game"; Orchestrator should not dispatch implementation agents until the user confirms delivery boundaries.

- Repeating the original request during a pending clarification is not confirmation to start.
- Repeated current requests should restate the current clarification question and ask the user to choose a boundary, add details, or cancel.
- Only explicit control phrases such as "按这个做", "开始实现", "go ahead", or "proceed" may resolve clarification and continue to planning/execution.
- A clearly different artifact/build request during pending clarification should route to topic confirmation, so the user can continue the current clarification, switch to the new request, or use it as reference.
- Identical clarification cards in separate conversations are deterministic template behavior, not evidence of cross-conversation message or SSE stream leakage. Each response must still have its own conversation/message/run identity.

## 2026-06-07 Handoff Addendum: Queued Next Turn Phase 1

Running-time submit is now implemented as a persisted same-conversation queue.

- Message status now includes `queued`.
- New table: `message_queue_entries`.
- Public APIs:
  - `POST /api/v1/conversations/{conversation_id}/queued-messages`
  - `PATCH /api/v1/queued-messages/{message_id}`
  - `DELETE /api/v1/queued-messages/{message_id}`
- Queue API is only for active conversations with a `pending` or `streaming` agent response. Normal `POST /messages` still returns `409 CONVERSATION_BUSY` in that state.
- The active turn remains serial. Queued user messages are not injected into the current agent runtime context.
- On `done`, `error`, or `interrupted`, B1 dispatches the queue head: queued user message becomes `done`, a new pending agent message is created, and terminal SSE may include `queued_next`.
- Frontend consumes `queued_next` to replace the queued bubble, append the new pending agent message, and start streaming it immediately.
- Queued bubbles are neutral, editable, and deletable before dispatch. Deleted queued messages are physically removed.
- If the queued target agent is no longer in the conversation at dispatch time, B1 creates a visible agent error message and continues queue processing instead of silently falling back to a global agent.
- Phase 1 intentionally excludes "guide current thinking"; that will need a separate runtime-control contract if implemented later.

Validation run for this slice:

- `uv run ruff check app tests`
- `uv run pytest -q tests/test_conversation_api.py tests/test_stream_tool_calls.py tests/test_b1_quality.py`
- `uv run pytest -q tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_stream_content_blocks.py`
- `pnpm exec tsc -b`
- `pnpm exec vitest run`

## 2026-06-07 Handoff Addendum: Conversation Control Plane Phase 2/3

Phase 2 "guide current thinking" and Phase 3 queue experience are now implemented as a Conversation Control Plane.

- New table: `conversation_turn_controls`.
- `message_queue_entries` now has `position`; queue dispatch order is `position, created_at, id`.
- New ContentBlock: `turn_control`.
  - `kind`: `guidance | side_chat | queue_action | stop_and_run`
  - `status`: `received | waiting_safe_point | applied | answered | cancelled | expired | failed`
- New APIs:
  - `POST /api/v1/messages/{active_message_id}/guidance`
  - `POST /api/v1/messages/{active_message_id}/side-chat`
  - `POST /api/v1/conversations/{conversation_id}/queued-messages/reorder`
  - `POST /api/v1/conversations/{conversation_id}/queued-messages/merge`
  - `POST /api/v1/queued-messages/{message_id}/convert-to-guidance`
  - `POST /api/v1/queued-messages/{message_id}/stop-and-run`
- SSE can emit `turn_control` events to update visible control cards during an active stream.
- Guidance is explicit. Running-time text still defaults to queued next turn unless the user chooses the guidance action.
- Guidance is currently Orchestrator safe-point only. Safe points include direct-answer, planner, task-dispatch, tool-loop, quality-gate, replanner/repair boundaries where available.
- External CLI/SDK runtimes do not accept live guidance injection in this phase. If the active message is not an Orchestrator safe-point runtime, return `409 GUIDANCE_NOT_SUPPORTED`.
- Side-chat creates visible status Q&A messages but `context_builder` excludes `turn_control.kind=side_chat` messages from future main-task context.
- Queue actions support reorder, merge, convert-to-guidance, and stop-and-run. They never create parallel active turns.

## 2026-06-07 Handoff Addendum: MemoryHub Important Memory + Dynamic Mount

AgentHub now has a local Supermemory-style MemoryHub layer.

- New tables:
  - `memories`
  - `memory_mounts`
- New public APIs:
  - `GET /api/v1/memories`
  - `PATCH /api/v1/memories/{id}`
  - `DELETE /api/v1/memories/{id}`
  - `GET /api/v1/conversations/{id}/memory-mounts`
- `ContextBuilder` now asks `MemoryHubService` for a per-turn mounted context. When MemoryHub returns useful context, legacy `ConversationMemory.summary_text` is not injected as the primary long-term memory. The old summary remains fallback/debug only.
- Mounted context is headed `MemoryHub mounted context:` and is recorded in `memory_mounts` when an `agent_message_id` exists.
- Terminal agent messages may extract deterministic memory candidates/active memories. The first implementation is conservative: it focuses on explicit user preferences, constraints, decisions, and stable facts; it filters credential-like content and marks temporary facts with expiry.
- Orchestrator run/task/attempt/event records remain authoritative execution facts. MemoryHub must not override group-scoped dispatch, runtime availability, queue/interrupt state, retry state, or workspace audit data.
- Frontend right panel has a new `Memory` tab for active memories, candidate memories, and recent dynamic mounts. Users can confirm candidates, edit memory content, or forget memories.

Validation run for this slice:

- `AGENTHUB_ALLOW_DEV_DB_TESTS=1 uv run pytest -q tests/test_memory_hub.py tests/test_context_builder.py`
- `uv run ruff check app tests`
- `pnpm exec tsc -b`
- `pnpm exec vitest run`

Validation run for this slice:

- `uv run ruff check app tests`
- `DATABASE_URL=postgresql+asyncpg://agenthub:agenthub_dev_pw@localhost:5432/agenthub_test uv run pytest tests/test_conversation_api.py tests/test_context_builder.py -q`
- `pnpm exec tsc -b`
- `pnpm exec vitest run src/components/chat/MessageInput.test.tsx src/components/chat/MessageBubble.test.tsx`
