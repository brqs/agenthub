# AgentHub

> 面向真实交付物的 IM 式多 Agent 协作工作台：对话、规划、生成、预览、审阅、修复与部署都在一个界面里完成。

[English](README.md) | [简体中文](README.zh-CN.md)

[![status](https://img.shields.io/badge/status-MVP-yellow)]()
[![python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![react](https://img.shields.io/badge/react-18-61dafb)]()
[![fastapi](https://img.shields.io/badge/FastAPI-0.115%2B-009688)]()

AgentHub 把 AI 协作做成聊天原生的工作空间。用户可以和单个代码 Agent 对话，也可以让 Orchestrator 把任务拆给多个运行时协作执行，并在同一个产品界面里查看生成文件、预览、部署、工具调用、任务卡片、记忆和上下文。

- 演示站点：[ag.brqs.link](http://ag.brqs.link/login)
- 演示视频：[demo.mp4](demo.mp4)
- API 契约：[shared/openapi.yaml](shared/openapi.yaml)
- AI 协作指南：[AGENTS.md](AGENTS.md)

## 演示

[![Watch the AgentHub demo](release-assets/demo-cover.png)](demo.mp4)

观看或下载完整演示：[demo.mp4](demo.mp4)。

## 核心能力

- **聊天原生的多 Agent 协作**：支持单聊、群聊、Orchestrator 调度、任务卡片、子 Agent 独立消息和 handoff 时间线。
- **真实 workspace 产物**：每个会话都有独立 workspace，支持文件树、代码预览、Diff、上传、artifact manifest 和发布历史。
- **多运行时接入**：内置 Orchestrator、Claude Code、Codex Helper、OpenCode Helper；支持外部 CLI/SDK adapter，以及受限只读 builtin 自建 Agent。
- **Orchestrator 规划与修复闭环**：clarification gate、大上下文 Planner、DAG 执行、并行调度、fallback 可见性、审阅交接、evaluation、reflection 和 repair loop。
- **预览与部署**：支持静态 workspace preview、浏览器级质量验收、静态发布、源码打包和受控容器部署路径。
- **契约驱动开发**：OpenAPI 优先、前端类型生成、后端 adapter contract、spec 与真实 E2E evidence 同步维护。

## 当前内置 Agent

当前 seed 的内置 Agent 只有 4 个：

| Agent | 职责 |
| --- | --- |
| `orchestrator` | 负责群聊协调、任务规划、Agent 调度、平台工具调用和最终总结；不作为普通子任务执行目标。 |
| `codex-helper` | 适合架构判断、仓库理解、总体规划、最终审阅、疑难 bug 和兜底修复。 |
| `claude-code` | 适合实现、文件编辑、代码生成、调试、修复、审阅和 workspace 修改。 |
| `opencode-helper` | 适合 CLI 风格实现、验证、修复和并行执行。 |

自建 Agent 不会按 provider 自动继承这些内置 planning profile。用户自建 external wrapper 会基于某个内置运行时 Agent；用户自建 `builtin` Agent 是受限只读的 Reader/Review Agent，只能暴露 `read_file`。

## 架构

```text
agenthub/
├── backend/                 FastAPI 后端、异步服务、Agent runtime 层
│   ├── app/api/v1/           Auth、会话、stream、agents、uploads、
│   │                         memories、workspaces、shares、events
│   ├── app/agents/           Base adapter contract、外部运行时、
│   │                         builtin runtime、model gateway、orchestrator
│   ├── app/models/           SQLAlchemy models
│   ├── app/schemas/          Pydantic schemas
│   ├── app/services/         Workspace、部署、记忆、平台工具
│   └── alembic/              数据库迁移
├── frontend/                React + Vite 客户端
│   └── src/
│       ├── components/       Chat、agents、artifacts、layout、blocks
│       ├── hooks/            Query 和 streaming hooks
│       ├── lib/              API client、OpenAPI 生成类型、SSE helper
│       ├── pages/            Login、chat、agents、archive、share
│       └── stores/           Zustand stores
├── shared/
│   └── openapi.yaml          API 契约和前端类型源
├── docs/                     产品、架构、spec、协作日志
└── docker-compose.yml        本地 Postgres、Redis、backend、workspace volumes
```

后端核心依赖方向：

```text
API layer -> Service layer -> Models/Schemas/Infrastructure
                    |
                    v
              Agent registry -> BaseAgentAdapter implementations
```

关键边界是 `backend/app/agents/base.py`：业务服务通过 registry 和 adapter contract 调用 Agent。原始模型 provider 被收敛在 ModelGateway 层，不作为顶层 Agent 注册。

## 技术栈

| 领域 | 实现 |
| --- | --- |
| 前端 | React 18、Vite、TypeScript、React Router、Tailwind CSS、shadcn 风格组件、Zustand、TanStack Query |
| 流式传输 | 基于 `@microsoft/fetch-event-source` 的 Server-Sent Events |
| 后端 | Python 3.11+、FastAPI、Uvicorn、Pydantic v2、SQLAlchemy 2.0 async |
| 存储 | PostgreSQL 15、Redis 7、本地 workspace 和 upload volumes |
| Agent 运行时 | Claude Agent SDK、Codex adapter、OpenCode CLI adapter、Builtin Agent runtime、ModelGateway |
| 质量保障 | pytest、pytest-asyncio、ruff、mypy、vitest、Testing Library、ESLint、Prettier |
| 客户端 | Web app、Tauri 桌面预留、Capacitor 移动端构建脚本 |

## 快速开始

### 前置要求

- Docker 和 Docker Compose
- Node.js 20+
- pnpm 9+
- 可选：Claude Code、Codex、OpenCode、Anthropic / OpenAI-compatible / DeepSeek 后端所需的 runtime 凭据

### 1. 配置环境变量

```bash
cp .env.example .env
```

本地 smoke run 可以保留默认 Postgres/Redis 配置，只填写你需要的 provider key 或 runtime auth 路径。要执行非 mock Agent，至少需要一个可用 provider/runtime。

常用变量：

| 变量 | 作用 |
| --- | --- |
| `JWT_SECRET` | 登录 token 签名密钥。任何非本地环境都必须替换。 |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` | runtime 探活和 ModelGateway 后端使用的 provider 凭据。 |
| `CORS_ORIGINS` | 允许访问后端的前端 origin，默认包含本地 Vite 和 Tauri origin。 |
| `WORKSPACE_BASE_DIR` | 会话 workspace 根目录。 |
| `UPLOAD_STORAGE_DIR` | backend 容器内的持久化上传目录。 |
| `PREVIEW_*` | workspace preview 控制和公网 base URL。 |
| `DEPLOYMENT_CONTAINER_*` | 受控容器部署 runtime、端口和健康检查配置。 |
| `VITE_API_BASE_URL` | 前端 API base URL，默认 `http://localhost:8000`。 |

不要提交真实 `.env`、auth token、runtime state 或 provider key。

### 2. 启动后端服务

```bash
docker compose up -d
```

backend 容器启动时会执行 Alembic migration。需要显式刷新内置 Agent 时：

```bash
docker compose exec backend python -m app.seeds.seed_agents
```

常用本地地址：

- 前端：<http://localhost:5173>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

### 3. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

打开 <http://localhost:5173>。

前端可以连接 mock 数据、本地后端或远端后端，取决于 `.env.local`：

```bash
cp .env.example .env.local
# 设置 VITE_USE_MOCK_API=false 可连接真实后端。
# 按需设置 VITE_API_BASE_URL 或 VITE_DEV_PROXY_TARGET。
```

## Runtime 配置检查

seed 的运行时 Agent 依赖容器内可见的 runtime auth：

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

OpenCode 登录状态通过 `AGENTHUB_OPENCODE_AUTH_DIR` 持久化在 `opencode-state` Docker volume 中。Claude Code 登录状态通过 `AGENTHUB_CLAUDE_AUTH_DIR` 持久化在 `claude-state` Docker volume 中。

## 开发命令

### 后端

```bash
docker compose logs -f backend
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seeds.seed_agents
docker compose exec backend pytest
docker compose exec backend ruff check
docker compose exec backend mypy app
```

纯后端本地开发使用 `backend/` 下的 `uv`：

```bash
cd backend
uv venv
uv pip install -e ".[dev]"
uv run pytest
uv run ruff check
uv run mypy app
```

后端测试默认拒绝直接打到开发库。优先使用隔离测试库；如果只是本地一次性确认：

```bash
cd backend
AGENTHUB_ALLOW_DEV_DB_TESTS=1 uv run pytest
```

### 前端

```bash
cd frontend
pnpm gen:types
pnpm test
pnpm lint
pnpm build
```

每次修改 [shared/openapi.yaml](shared/openapi.yaml) 后都要运行 `pnpm gen:types`。生成的类型文件在 [frontend/src/lib/types.gen.ts](frontend/src/lib/types.gen.ts)。

### 桌面与移动端

```bash
cd frontend
pnpm desktop:dev
pnpm tauri:build
pnpm cap:sync
```

这些端需要额外安装对应的本地 native toolchain。

## Live E2E 与 Repair Loop

Live E2E harness 用真实 HTTP/SSE 验证 preview、deployment、多 Agent 规划、fallback 和 repair 行为。

```bash
cd backend
AGENTHUB_E2E_BASE_URL=http://111.229.151.159:8000 \
AGENTHUB_E2E_USERNAME="$AGENTHUB_E2E_USERNAME" \
AGENTHUB_E2E_PASSWORD="$AGENTHUB_E2E_PASSWORD" \
AGENTHUB_E2E_SCENARIO=fullstack_task_manager_parallel_repair_v2 \
uv run python scripts/orchestrator_live_e2e.py
```

近期鲁棒性场景包括：

- `fullstack_task_manager_parallel_repair_v2`
- `cyberpunk_site_quality_repair_8082_v2`
- `im_context_pin_followup_repair`
- `group_chat_attribution_process_matrix`
- `custom_agent_reader_review_repair`
- `static_package_deploy_repair_matrix`
- `group_member_fallback_repair_visibility`
- `im_dialogue_no_artifact_turn_taking_v2`

测试账号密码必须通过环境变量注入。不要把真实账号、密码、access token 或 refresh token 写入源码、报告或日志。

## API 范围

后端 API v1 挂载在 `/api/v1`：

| 领域 | Router |
| --- | --- |
| Auth | `/api/v1/auth` |
| Conversations 和 messages | `/api/v1/conversations`、message routes、`/api/v1/stream` |
| Agents | `/api/v1/agents` |
| Workspaces 和 artifacts | `/api/v1/workspaces` |
| Uploads | `/api/v1/uploads` |
| Memories 和 context compression | `/api/v1/memories`、`/api/v1/context-compression` |
| Realtime events | `/api/v1/events` |
| Local runtime connectors | `/api/v1/local-runtime-connectors` |
| Shares | `/api/v1/conversations/{conversation_id}/shares`、`/api/v1/conversation-shares/{token}` |
| Static releases | `/releases/{release_token}` |

请求和响应细节见 [shared/openapi.yaml](shared/openapi.yaml)，或本地 Swagger UI：<http://localhost:8000/docs>。

## 文档索引

| 需求 | 文档 |
| --- | --- |
| AI 协作规则 | [AGENTS.md](AGENTS.md) |
| 产品设计 | [docs/product-design.md](docs/product-design.md) |
| 技术架构 | [docs/tech-architecture.md](docs/tech-architecture.md) |
| 团队分工 | [docs/team-division.md](docs/team-division.md) |
| API 指南 | [docs/api-spec.md](docs/api-spec.md) |
| Runtime pivot ADR | [docs/spec/agent-runtime-pivot.adr.md](docs/spec/agent-runtime-pivot.adr.md) |
| Agent adapter contract | [docs/b2/spec/agent-runtime-adapter.spec.md](docs/b2/spec/agent-runtime-adapter.spec.md) |
| Builtin Agent framework | [docs/b2/spec/builtin-agent-framework.spec.md](docs/b2/spec/builtin-agent-framework.spec.md) |
| Orchestrator specs | [docs/b2/spec/orchestrator/README.md](docs/b2/spec/orchestrator/README.md) |
| Workspace sandbox | [docs/b1/spec/workspace-sandbox.spec.md](docs/b1/spec/workspace-sandbox.spec.md) |

## 协作规则

本仓库是契约驱动的。改代码前请先读 [AGENTS.md](AGENTS.md)。简版规则：

- API 变更从 [shared/openapi.yaml](shared/openapi.yaml) 开始，然后同步 schema、service、route 和前端类型。
- 后端服务通过 `agents.registry.get_adapter(...)` 调用 Agent，不直接 import 具体外部 runtime。
- Agent adapter 实现 BaseAgentAdapter v2 contract，不访问数据库。
- ContentBlock 变更必须同步 backend schema、OpenAPI 和前端渲染器。
- 保持所有权边界清晰：`frontend/**`、后端 core/services/API、`backend/app/agents/**` 分属不同模块。

## 仓库状态

AgentHub 仍处于 MVP 阶段，runtime、workspace、deployment 和 Orchestrator 能力都在快速迭代。部分文档可能描述计划中或刚 pivot 的行为；如果不确定，以当前代码、[shared/openapi.yaml](shared/openapi.yaml) 和 [AGENTS.md](AGENTS.md) 为准。

## License

当前仓库尚未提供 license 文件。
