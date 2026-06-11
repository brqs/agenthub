# AgentHub

> IM-style multi-agent collaboration workspace for building, previewing, reviewing, repairing, and deploying real deliverables.

[简体中文](README.md) | [English](README.en.md)

[![status](https://img.shields.io/badge/status-MVP-yellow)]()
[![python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![react](https://img.shields.io/badge/react-18-61dafb)]()
[![fastapi](https://img.shields.io/badge/FastAPI-0.115%2B-009688)]()

AgentHub turns AI collaboration into a chat-native workspace. Users can talk to individual coding agents, ask an Orchestrator to split work across multiple runtimes, and inspect generated files, previews, deployments, tool calls, task cards, memory, and conversation context in one product surface.

- Demo site: [ag.brqs.link](http://ag.brqs.link/login)
- Demo video: [demo.mp4](demo.mp4)
- API contract: [shared/openapi.yaml](shared/openapi.yaml)
- AI collaboration guide: [AGENTS.md](AGENTS.md)

## Demo

[![Watch the AgentHub demo](release-assets/demo-cover.png)](demo.mp4)

Watch or download the full demo: [demo.mp4](demo.mp4).

## Highlights

- **Chat-native multi-agent work**: direct chats, group chats, Orchestrator scheduling, task cards, child-agent messages, and handoff timelines.
- **Real workspace artifacts**: each conversation has a workspace with file tree, code preview, diffs, uploads, artifact manifest, and publish history.
- **Multiple agent runtimes**: built-in Orchestrator, Claude Code, Codex Helper, OpenCode Helper, external CLI/SDK adapters, and a restricted builtin runtime for read-only custom agents.
- **Planning and repair loops**: clarification gate, large-context Planner, DAG execution, parallel dispatch, fallback visibility, review handoff, evaluation, reflection, and repair loops.
- **Preview and deployment**: static workspace preview, browser quality checks, static releases, source packages, and controlled container deployment paths.
- **Contract-driven development**: OpenAPI-first API changes, generated frontend types, backend adapter contracts, and spec-backed E2E evidence.

## Current Built-in Agents

AgentHub currently seeds four built-in agents:

| Agent | Role |
| --- | --- |
| `orchestrator` | Coordinates group work, plans tasks, dispatches agents, runs platform tools, and summarizes results. It is not a normal subtask target. |
| `codex-helper` | Architecture, repository analysis, planning, final review, escalation, and difficult bug fixing. |
| `claude-code` | Implementation, file editing, code generation, debugging, repair, review, and workspace changes. |
| `opencode-helper` | CLI-oriented implementation, verification, repair, and parallel execution. |

Custom agents do not inherit these built-in planning profiles from their provider name. User-created external wrappers are based on one of the built-in runtime agents. User-created `builtin` agents are restricted read-only reader/review agents and may expose only `read_file`.

## Technical Architecture

### Repository Layout

```text
agenthub/
├── backend/                 FastAPI backend, async services, Agent runtime layer
│   ├── app/api/v1/           Auth, conversations, stream, agents, uploads,
│   │                         memories, workspaces, shares, events
│   ├── app/agents/           Base adapter contract, external runtimes,
│   │                         builtin runtime, model gateway, orchestrator
│   ├── app/models/           SQLAlchemy models
│   ├── app/schemas/          Pydantic schemas
│   ├── app/services/         Workspace, deployment, memory, platform tools
│   └── alembic/              Database migrations
├── frontend/                React + Vite client
│   └── src/
│       ├── components/       Chat, agents, artifacts, layout, blocks
│       ├── hooks/            Query and streaming hooks
│       ├── lib/              API client, generated OpenAPI types, SSE helpers
│       ├── pages/            Login, chat, agents, archive, share
│       └── stores/           Zustand stores
├── shared/
│   └── openapi.yaml          API contract and frontend type source
├── docs/                     Product, architecture, specs, collaboration logs
└── docker-compose.yml        Local Postgres, Redis, backend, workspace volumes
```

### Backend Layers

```text
API layer -> Service layer -> Models/Schemas/Infrastructure
                    |
                    v
              Agent registry -> BaseAgentAdapter implementations
```

The key boundary is `backend/app/agents/base.py`: application services call agents through the registry and adapter contract. Raw model providers stay behind the ModelGateway layer and are not registered as top-level agents.

Main backend modules:

| Module | Purpose |
| --- | --- |
| `app/api/v1` | HTTP API, SSE stream, workspace, agent, auth, upload, memory, and event entry points. |
| `app/services` | Business logic, including workspace files, artifact manifest, deployment, memory, and platform tool execution. |
| `app/agents` | Agent adapter contract, external runtime adapters, builtin runtime, ModelGateway, and Orchestrator. |
| `app/models` | SQLAlchemy async ORM for users, conversations, messages, agents, workspace deployments, Orchestrator runs, and memory. |
| `app/schemas` | Pydantic v2 schemas used by backend validation, OpenAPI, and frontend type generation. |
| `alembic` | Database migrations. The Compose backend runs `alembic upgrade head` on startup. |

### Orchestrator Request Flow

A typical Orchestrator turn follows this pipeline:

```text
user message
-> stream layer builds context, workspace, available_agents, memory
-> direct answer / platform facts / clarification gate
-> LLM Planner or explicit config.tasks
-> task graph validation, agent whitelist filtering, DAG dependency analysis
-> parallel or sequential sub-agent dispatch
-> collect TaskResult, artifacts, tool evidence, child messages
-> evaluation / reflection / repair loop
-> preview / browser verify / deployment / source package platform tools
-> final process block + user-facing summary
```

Important rules:

- Planner can only select agents available in the current group, unless an internal/E2E task explicitly sets `available_agents_authoritative=false`.
- Planner uses a dedicated large-context path. The default `planner_context_max_tokens` is `128000`, configurable up to `1000000`.
- Normal Orchestrator execution context defaults to `64000 tokens`; sub-agent dispatch context also defaults to `64000 tokens`.
- Planner prompt keeps allowlisted memory signals, agent profiles, and recent conversation context, but does not expose raw structured memory.
- Task cards must show the actual execution agent. When fallback happens, run detail and reports preserve `planned/current/final agent` evidence.
- Sub-agents do not start long-running services. Preview, browser verification, deployment, and source packaging are platform tools.

### Agent Runtime Layer

Top-level Agent providers are separated from raw model providers:

| Type | Purpose |
| --- | --- |
| `claude_code` | Claude Code runtime. SDK by default, with CLI fallback support. |
| `codex` | Codex Helper runtime. CLI by default, with SDK opt-in support. |
| `opencode` | OpenCode CLI runtime with local auth/state directory support. |
| `builtin` | Backend AgentLoop + ModelGateway. User-created builtin agents are currently read-only and may expose only `read_file`. |
| `mock` | Testing and development path. |

`ModelGateway` normalizes Claude / OpenAI-compatible / DeepSeek-style model backends into a unified stream interface. It powers builtin agents, direct answers, planner calls, evaluation, and related model-backed paths.

### SSE and Content Blocks

The frontend and backend communicate through SSE. Core events include:

- `message_start` / `message_done` / `message_error`
- `block_start` / `delta` / `block_end`
- `tool_call` / `tool_result`
- `agent_switch`
- `task_card` / process block / deployment status / artifact references

The backend turns execution progress and final answers into structured ContentBlocks. The frontend renders task cards, code, diffs, files, tool calls, deployment status, review timelines, and final summaries according to block type.

### Workspace, Preview, and Deployment

- Each conversation owns an isolated workspace for generated files, uploads, artifact manifest, and publish records.
- Workspace file access goes through path guards and must not read `.env`, `.ssh`, secrets, runtime auth directories, or platform manifests.
- Static preview is managed by the platform preview service and uses the configured preview port range.
- Static releases expose immutable snapshots under `/releases/{release_token}`.
- Source packages filter sensitive paths so local auth state and secrets are not included in zip files.
- Container deployment is handled by a controlled worker. Docker requires trusted host mode; Podman can be used as a rootless runtime. The LLM never directly constructs `docker run`.

### Data and State

| Storage | Contents |
| --- | --- |
| PostgreSQL | Users, conversations, messages, agent configs, workspace deployments, Orchestrator run/task/attempt/event records, memory. |
| Redis | Cache and realtime/async support paths. |
| `workspaces/` | Conversation workspace files. |
| Docker volumes | Postgres data, uploads, Claude/OpenCode runtime auth state. |

## Tech Stack

| Area | Implementation |
| --- | --- |
| Frontend | React 18, Vite, TypeScript, React Router, Tailwind CSS, shadcn-style components, Zustand, TanStack Query |
| Streaming | Server-Sent Events via `@microsoft/fetch-event-source` |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 async |
| Storage | PostgreSQL 15, Redis 7, local workspace and upload volumes |
| Agent runtimes | Claude Agent SDK, Codex adapter, OpenCode CLI adapter, Builtin Agent runtime, ModelGateway |
| Quality | pytest, pytest-asyncio, ruff, mypy, vitest, Testing Library, ESLint, Prettier |
| Clients | Web app, Tauri desktop hooks, Capacitor mobile build scripts |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+
- pnpm 9+
- Optional runtime credentials for Claude Code, Codex, OpenCode, Anthropic/OpenAI-compatible/DeepSeek model backends

### 1. Configure Environment

```bash
cp .env.example .env
```

For a local smoke run, keep the default Postgres/Redis values and set only the provider keys or runtime auth paths you need. At least one configured provider/runtime is required for non-mock agent execution.

Important variables:

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET` | Auth token signing secret. Replace it in any non-local environment. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` | Provider credentials used by runtime probes and model backends. |
| `CORS_ORIGINS` | Allowed frontend origins. Defaults include local Vite and Tauri origins. |
| `WORKSPACE_BASE_DIR` | Root directory for generated conversation workspaces. |
| `UPLOAD_STORAGE_DIR` | Persistent upload storage path inside the backend container. |
| `PREVIEW_*` | Workspace preview controls and public base URL. |
| `DEPLOYMENT_CONTAINER_*` | Controlled container deployment runtime, ports, and health-check settings. |
| `VITE_API_BASE_URL` | Frontend API base URL. Defaults to `http://localhost:8000`. |

Never commit real `.env`, auth tokens, runtime state, or provider keys.

### 2. Start Backend Services

```bash
docker compose up -d
```

The backend container runs Alembic migrations on startup. To seed or refresh built-in agents explicitly:

```bash
docker compose exec backend python -m app.seeds.seed_agents
```

Useful local endpoints:

- Frontend: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

### 3. Start Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open <http://localhost:5173>.

The frontend can run against mock data, a local backend, or a remote backend depending on `.env.local`:

```bash
cp .env.example .env.local
# Set VITE_USE_MOCK_API=false to use a real backend.
# Set VITE_API_BASE_URL or VITE_DEV_PROXY_TARGET as needed.
```

## Runtime Setup Notes

The seeded runtime agents depend on local or container-visible runtime auth:

```bash
docker compose exec backend opencode --version
docker compose exec backend opencode auth list
docker compose exec backend env | grep OPENCODE
```

```bash
docker compose exec backend python -c "import claude_agent_sdk; print('sdk ok')"
docker compose exec backend sh -lc 'ls -la $AGENTHUB_CLAUDE_AUTH_DIR'
docker compose exec backend env | grep -E 'ANTHROPIC|CLAUDE|AGENTHUB_CLAUDE'
```

OpenCode login state is persisted in the `opencode-state` Docker volume through `AGENTHUB_OPENCODE_AUTH_DIR`. Claude Code login state is persisted in the `claude-state` Docker volume through `AGENTHUB_CLAUDE_AUTH_DIR`.

## Development Commands

### Backend

```bash
docker compose logs -f backend
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seeds.seed_agents
docker compose exec backend pytest
docker compose exec backend ruff check
docker compose exec backend mypy app
```

Local backend-only development is managed from `backend/` with `uv`:

```bash
cd backend
uv venv
uv pip install -e ".[dev]"
uv run pytest
uv run ruff check
uv run mypy app
```

Backend tests intentionally refuse to run against the default development database unless you opt in. Prefer an isolated test database. For a deliberate local one-off run:

```bash
cd backend
AGENTHUB_ALLOW_DEV_DB_TESTS=1 uv run pytest
```

### Frontend

```bash
cd frontend
pnpm gen:types
pnpm test
pnpm lint
pnpm build
```

Run `pnpm gen:types` whenever [shared/openapi.yaml](shared/openapi.yaml) changes. Generated API types live in [frontend/src/lib/types.gen.ts](frontend/src/lib/types.gen.ts).

### Desktop and Mobile

```bash
cd frontend
pnpm desktop:dev
pnpm tauri:build
pnpm cap:sync
```

These surfaces depend on local native toolchains in addition to the web app requirements.

## Live E2E and Repair Loop

The live E2E harness validates real HTTP/SSE flows, preview, deployment, multi-agent planning, fallback, and repair behavior.

```bash
cd backend
AGENTHUB_E2E_BASE_URL=http://111.229.151.159:8000 \
AGENTHUB_E2E_USERNAME="$AGENTHUB_E2E_USERNAME" \
AGENTHUB_E2E_PASSWORD="$AGENTHUB_E2E_PASSWORD" \
AGENTHUB_E2E_SCENARIO=fullstack_task_manager_parallel_repair_v2 \
uv run python scripts/orchestrator_live_e2e.py
```

Recent robustness scenarios include:

- `fullstack_task_manager_parallel_repair_v2`
- `cyberpunk_site_quality_repair_8082_v2`
- `im_context_pin_followup_repair`
- `group_chat_attribution_process_matrix`
- `custom_agent_reader_review_repair`
- `static_package_deploy_repair_matrix`
- `group_member_fallback_repair_visibility`
- `im_dialogue_no_artifact_turn_taking_v2`

Credentials must be provided through environment variables. Do not write real accounts, passwords, access tokens, or refresh tokens into source files, reports, or logs.

## API Surface

The backend mounts API v1 under `/api/v1`:

| Area | Router |
| --- | --- |
| Auth | `/api/v1/auth` |
| Conversations and messages | `/api/v1/conversations`, message routes, `/api/v1/stream` |
| Agents | `/api/v1/agents` |
| Workspaces and artifacts | `/api/v1/workspaces` |
| Uploads | `/api/v1/uploads` |
| Memories and context compression | `/api/v1/memories`, `/api/v1/context-compression` |
| Realtime events | `/api/v1/events` |
| Local runtime connectors | `/api/v1/local-runtime-connectors` |
| Shares | `/api/v1/conversations/{conversation_id}/shares`, `/api/v1/conversation-shares/{token}` |
| Static releases | `/releases/{release_token}` |

For request/response details, use [shared/openapi.yaml](shared/openapi.yaml) or the local Swagger UI at <http://localhost:8000/docs>.

## Documentation Map

| Need | Document |
| --- | --- |
| AI collaboration rules | [AGENTS.md](AGENTS.md) |
| Product design | [docs/product-design.md](docs/product-design.md) |
| Technical architecture | [docs/tech-architecture.md](docs/tech-architecture.md) |
| Team ownership | [docs/team-division.md](docs/team-division.md) |
| API guide | [docs/api-spec.md](docs/api-spec.md) |
| Runtime pivot ADR | [docs/spec/agent-runtime-pivot.adr.md](docs/spec/agent-runtime-pivot.adr.md) |
| Agent adapter contract | [docs/b2/spec/agent-runtime-adapter.spec.md](docs/b2/spec/agent-runtime-adapter.spec.md) |
| Builtin Agent framework | [docs/b2/spec/builtin-agent-framework.spec.md](docs/b2/spec/builtin-agent-framework.spec.md) |
| Orchestrator specs | [docs/b2/spec/orchestrator/README.md](docs/b2/spec/orchestrator/README.md) |
| Workspace sandbox | [docs/b1/spec/workspace-sandbox.spec.md](docs/b1/spec/workspace-sandbox.spec.md) |

## Collaboration Rules

This repository is contract-driven. Before changing code, read [AGENTS.md](AGENTS.md). The short version:

- API changes start in [shared/openapi.yaml](shared/openapi.yaml), then schemas/services/routes/frontend types follow.
- Backend services use `agents.registry.get_adapter(...)`; they do not import concrete external runtimes directly.
- Agent adapters implement the BaseAgentAdapter v2 contract and should not access the database.
- Content block changes must stay aligned across backend schemas, OpenAPI, and frontend renderers.
- Keep ownership boundaries clear: `frontend/**`, backend core/services/API, and `backend/app/agents/**` have different owners.

## Repository Status

AgentHub is an MVP-stage project with active runtime, workspace, deployment, and orchestration development. Some docs may describe planned or recently pivoted behavior; when in doubt, prefer the current code, [shared/openapi.yaml](shared/openapi.yaml), and [AGENTS.md](AGENTS.md).

## License

No repository license file is currently present.
