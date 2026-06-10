# AgentHub

> IM-style multi-agent collaboration workspace for building, previewing, and iterating on real deliverables.

[![status](https://img.shields.io/badge/status-MVP-yellow)]()
[![python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![react](https://img.shields.io/badge/react-18-61dafb)]()
[![fastapi](https://img.shields.io/badge/FastAPI-0.115%2B-009688)]()

AgentHub turns AI collaboration into a chat-native workspace. Users can talk to coding agents, create custom agents, let an Orchestrator split work across specialist runtimes, and inspect generated files, previews, deployments, tool calls, and conversation context in one product surface.

- Demo site: [ag.brqs.link](http://ag.brqs.link/login)
- Demo video: [demo.mp4](demo.mp4)
- API contract: [shared/openapi.yaml](shared/openapi.yaml)
- AI collaboration guide: [AGENTS.md](AGENTS.md)

## Demo

<video src="demo.mp4" controls width="100%">
  Your browser does not support embedded video. Download the demo instead: https://github.com/brqs/agenthub/blob/main/demo.mp4
</video>

If the embedded player is unavailable in your Markdown viewer, open [demo.mp4](demo.mp4) directly.

## What It Does

AgentHub is built around three product loops:

1. **Chat with agents**
   - Direct or orchestrated conversations with built-in and custom agents.
   - SSE streaming for text, tool activity, task progress, and rich content blocks.
   - Message controls for interruption, regeneration, queuing, archives, and share links.

2. **Generate real artifacts**
   - Per-conversation workspace sandbox for generated files.
   - Inline rendering for text, code, diffs, files, web previews, task cards, workflow/process states, deployment status, and tool calls.
   - Workspace file tree, code preview, upload support, static preview, and deployment history surfaces.

3. **Coordinate multiple runtimes**
   - Built-in agents seeded from backend code: `Claude Code`, `Codex Helper`, `OpenCode Helper`, and `Orchestrator`.
   - External runtime adapters for Claude Code, Codex CLI by default with SDK opt-in, and OpenCode CLI.
   - Builtin Agent runtime backed by the ModelGateway layer for Claude, OpenAI-compatible, and DeepSeek-style model backends.
   - Orchestrator planning with clarification gate, task execution, memory/context support, and managed sub-agent dispatch.

## Architecture

```text
agenthub/
├── backend/                 FastAPI backend, async services, Agent runtime layer
│   ├── app/api/v1/           Auth, conversations, messages, stream, agents,
│   │                         uploads, memories, workspaces, shares, events
│   ├── app/agents/           Base adapter contract, external runtimes,
│   │                         builtin runtime, model gateway, orchestrator
│   ├── app/models/           SQLAlchemy models
│   ├── app/schemas/          Pydantic schemas
│   ├── app/services/         Business logic, workspace, deployment, memory
│   └── alembic/              Database migrations
├── frontend/                React + Vite client
│   └── src/
│       ├── components/       Chat, agents, artifact, desktop, layout, blocks
│       ├── hooks/            Query and streaming hooks
│       ├── lib/              API client, generated OpenAPI types, SSE helpers
│       ├── pages/            Login, chat, agents, archive, share
│       └── stores/           Zustand stores
├── shared/
│   └── openapi.yaml          API contract and frontend type source
├── docs/                     Product, architecture, specs, collaboration logs
└── docker-compose.yml        Local Postgres, Redis, backend, workspace volumes
```

Core backend dependency direction:

```text
API layer -> Service layer -> Models/Schemas/Infrastructure
                    |
                    v
              Agent registry -> BaseAgentAdapter implementations
```

The important boundary is `backend/app/agents/base.py`: application services call agents through the registry and adapter contract. Raw model providers are kept behind the ModelGateway layer and are not registered as top-level agents.

## Tech Stack

| Area | Implementation |
| --- | --- |
| Frontend | React 18, Vite, TypeScript, React Router, Tailwind CSS, shadcn-style components, Zustand, TanStack Query |
| Streaming | Server-Sent Events via `@microsoft/fetch-event-source` |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 async |
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

For a local smoke run, keep the default Postgres/Redis values and set only the provider keys you need. At least one configured provider/runtime is required for non-mock agent execution.

Common variables:

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET` | Auth token signing secret. Replace in any non-local environment. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` | Provider credentials used by runtime probes and model backends. |
| `CORS_ORIGINS` | Allowed frontend origins. Defaults include local Vite and Tauri origins. |
| `WORKSPACE_BASE_DIR` | Root directory for generated conversation workspaces. |
| `UPLOAD_STORAGE_DIR` | Persistent upload storage path inside the backend container. |
| `PREVIEW_*`, `DEPLOYMENT_CONTAINER_*` | Workspace preview and container deployment controls. |
| `VITE_API_BASE_URL` | Frontend API base URL. Defaults to `http://localhost:8000`. |

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

## Runtime Checks

These commands verify that the backend container can see the external runtime surfaces used by the seeded agents.

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

OpenCode login state is persisted in the `opencode-state` Docker volume. Claude Code login state is persisted in the `claude-state` Docker volume through `AGENTHUB_CLAUDE_AUTH_DIR`.

## Development Commands

### Backend

```bash
docker compose logs -f backend
docker compose exec backend alembic upgrade head
docker compose exec backend pytest
docker compose exec backend ruff check
docker compose exec backend mypy app
```

Local backend-only development is managed from `backend/` with `uv`:

```bash
cd backend
uv run pytest
uv run ruff check
uv run mypy app
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

The frontend includes Tauri and Capacitor scripts:

```bash
cd frontend
pnpm desktop:dev
pnpm tauri:build
pnpm cap:sync
```

These surfaces depend on local native toolchains in addition to the web app requirements.

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

## Collaboration Rules

This repository is contract-driven. Before changing code, read [AGENTS.md](AGENTS.md). The short version:

- API changes start in [shared/openapi.yaml](shared/openapi.yaml), then schemas/services/routes/frontend types follow.
- Backend services use `agents.registry.get_adapter(...)`; they do not import concrete external runtimes directly.
- Agent adapters implement the BaseAgentAdapter v2 contract and should not access the database.
- Content block changes must stay aligned across backend schemas, OpenAPI, and frontend renderers.
- Keep ownership boundaries clear: `frontend/**`, backend core/services/API, and `backend/app/agents/**` have different owners.

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
| Workspace sandbox | [docs/b1/spec/workspace-sandbox.spec.md](docs/b1/spec/workspace-sandbox.spec.md) |

## Repository Status

AgentHub is an MVP-stage project with active runtime, workspace, and orchestration development. Some docs may describe planned or recently pivoted behavior; when in doubt, prefer the current code, [shared/openapi.yaml](shared/openapi.yaml), and [AGENTS.md](AGENTS.md).

## License

No license file is currently included. Add a project license before public redistribution.
