# AgentHub

> 面向真实交付物的 IM 式多 Agent 协作工作台：对话、规划、生成、预览、审阅、修复与部署都在一个界面里完成。

[简体中文](README.md) | [English](README.en.md)

[![status](https://img.shields.io/badge/status-MVP-yellow)]()
[![python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![react](https://img.shields.io/badge/react-18-61dafb)]()
[![fastapi](https://img.shields.io/badge/FastAPI-0.115%2B-009688)]()

AgentHub 把 AI 协作做成聊天原生的工作空间。用户可以和单个代码 Agent 对话，也可以让 Orchestrator 把任务拆给多个运行时协作执行，并在同一个产品界面里查看生成文件、预览、部署、工具调用、任务卡片、记忆和上下文。

- 演示站点：[ag.brqs.link](http://ag.brqs.link/login)
- 演示视频：[demo.mp4](demo.mp4)
- API 契约：[shared/openapi.yaml](shared/openapi.yaml)
- AI 协作指南：[AGENTS.md](AGENTS.md)

## 快速入口

这里保留最常用入口；更细的设计、架构、spec 和 E2E 证据放在后面的[项目文档](#项目文档)里。

| 想看什么 | 入口 |
| --- | --- |
| 直接体验 | [ag.brqs.link](http://ag.brqs.link/login) |
| 演示视频 | [demo.mp4](demo.mp4) |
| API 契约 | [shared/openapi.yaml](shared/openapi.yaml)、[docs/api-spec.md](docs/api-spec.md) |
| 文档索引 | [docs/README.md](docs/README.md) |
| AI 协作指南 | [AGENTS.md](AGENTS.md) |

## 项目概览

AgentHub 是一个以 IM 为核心交互的多 Agent 协作平台。用户可以像新建聊天一样创建任务会话，和单个 Agent 对话，也可以在群聊中让 Orchestrator 拆解任务、调度多个真实 Agent runtime 协作，并把过程和产物留在同一个工作台里。

一条典型链路是：用户发起需求 → Orchestrator 规划任务 → Claude Code / Codex Helper / OpenCode Helper 分工执行 → workspace 生成文件、Diff 和 artifact manifest → 平台启动预览、浏览器验收、审阅与修复 → 输出可读总结、发布记录或部署结果。

## 核心协作流转

Orchestrator 不是简单地把所有消息都丢给 Planner。一次群聊消息会先经过瀑布式路由：澄清门控、上一轮产物跟进、平台事实问答、直接回答、自定义 Agent 创建和平台工具循环都有机会先处理；只有这些路径都不命中时，才进入任务规划。规划也不只有一种方式：显式 `@` 多 Agent 会走广播任务，讨论类请求会走 turn-taking，配置好的 `config.tasks` 会跳过 LLM Planner，复杂交付任务则由 Planner 根据当前群聊成员、agent profile、上下文和 workspace 状态生成 DAG。

任务委派以“当前群聊真实成员”为边界。Planner 只能选择当前会话可用的 Agent，并看到内置 Agent 的 planning profile 与自建 Agent 的安全白名单信息。生成的 task graph 会经过 agent 白名单、依赖关系和 workspace 冲突校验；没有依赖的任务可以并行执行，有依赖的任务会注入前序结果摘要、workspace inventory 和最新用户请求再交给子 Agent。执行过程中 task card 展示实际执行 Agent，run detail 保留 planned/current/final agent 证据；如果目标 Agent 不可用，fallback 只会在群聊可用 Agent 中发生。

执行结果会继续进入 review handoff、evaluation/reflection 和 repair loop。子 Agent 负责生成或修改 workspace 产物，Orchestrator 负责收集结果、判断是否需要修复，并通过平台工具完成预览、浏览器质量验收、源码打包、静态发布或受控容器部署。这样用户看到的不是一段黑盒回复，而是一条可追踪的“路由 → 计划 → 委派 → 执行 → 验收 → 修复 → 总结”链路。

相关材料：[Orchestrator 路由流程](docs/orchestrator-routing-flow.md)、[core spec](docs/b2/spec/orchestrator/core.spec.md)、[task planning spec](docs/b2/spec/orchestrator/task-planning.spec.md)、[message attribution spec](docs/b2/spec/orchestrator/message-attribution.spec.md)、[evaluation/reflection spec](docs/b2/spec/orchestrator/evaluation-reflection.spec.md)、[live E2E report spec](docs/b2/spec/orchestrator/live-e2e-report.spec.md)。

## 产品主线与实现

### IM 式多 Agent 工作台

产品保留 IM 的熟悉感：会话列表、单聊、群聊、`@ Agent`、多会话并行、Pin/上下文、文件与富媒体消息都围绕聊天流组织。前端使用结构化 ContentBlock 渲染文本、代码、Diff、文件、预览、任务卡片、工具调用和部署状态，让对话不是单纯文本，而是可以承载产物和操作。

相关材料：[产品设计](docs/product-design.md)、[前端文档索引](docs/frontend/README.md)、[ContentBlock spec](docs/frontend/spec/frontend-content-blocks.spec.md)、[orchestrated message rendering spec](docs/frontend/spec/orchestrated-message-rendering.spec.md)。

### Orchestrator 协作闭环

Orchestrator 是群聊里的协调者：它读取当前群聊成员、上下文和 workspace 状态，选择可用 Agent，生成 DAG 任务计划，并在执行中处理并行调度、依赖结果注入、fallback、review handoff、evaluation/reflection 和 repair loop。task card 和 run detail 会保留 planned/current/final agent 证据，避免协作过程变成黑盒。

相关材料：[Orchestrator spec](docs/b2/spec/orchestrator/README.md)、[task planning spec](docs/b2/spec/orchestrator/task-planning.spec.md)、[message attribution spec](docs/b2/spec/orchestrator/message-attribution.spec.md)、[live E2E report spec](docs/b2/spec/orchestrator/live-e2e-report.spec.md)。

### 真产物、预览与验收

Agent 输出会落到会话 workspace，而不是只留在聊天气泡里。当前主链路覆盖代码文件、文档、Diff、artifact manifest、静态 preview、浏览器质量验收、静态发布、源码打包和受控容器部署。文档、PPT、图片、archive、workflow 等扩展产物已有后端契约和部分 E2E 证据；版本历史、局部编辑和更完整的富媒体前端体验在对应 handoff/spec 中继续产品化。

相关材料：[workspace preview spec](docs/b2/spec/workspace-artifact-preview.spec.md)、[deployment release spec](docs/b2/spec/deployment-release-backend.execution.spec.md)、[evaluation/reflection spec](docs/b2/spec/orchestrator/evaluation-reflection.spec.md)、[rich artifact handoff](docs/frontend/rich-artifact-preview-handoff.md)。

### AI 协作工程化

项目把 AI 协作方式沉淀成 rules、spec、skill 和日志，而不是临时口头约定。任务如何拆、上下文如何传、失败后如何 fallback、repair loop 如何收敛、E2E 如何留证据，都有文档、脚本或测试承接。完整沉淀见 [docs/](docs/)；AI 协作相关可以优先看 [AGENTS.md](AGENTS.md)、[AI 协作开发记录](docs/ai-collaboration-log.md)、[B2 协作 Skill](docs/ai-skills/b2-ai-collaboration/SKILL.md) 和 [Orchestrator E2E repair loop Skill](docs/ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md)。

### 多端与扩展方向

Web 是当前主力端；桌面端通过 Tauri 复用前端体验，移动端通过 PWA / Capacitor 复用同一套 React 页面和真实 API/SSE 客户端。多端、上传、桌面 bridge、移动壳层和后续自定义 Agent 深化都在 frontend/spec 与 next-major-modules 中拆分记录。

相关材料：[frontend README](docs/frontend/README.md)、[mobile development spec](docs/frontend/spec/frontend-mobile-development.spec.md)、[Capacitor shell spec](docs/frontend/spec/frontend-capacitor-shell.spec.md)、[macOS Tauri shell spec](docs/frontend/spec/frontend-macos-tauri-shell.spec.md)、[Windows desktop spec](docs/frontend/spec/windows-desktop-client.spec.md)。

## 项目文档

| 文档 / 材料 | 位置 |
| --- | --- |
| 文档总索引 | [docs/README.md](docs/README.md) |
| 产品设计文档 | [docs/product-design.md](docs/product-design.md) |
| 技术架构文档 | [docs/tech-architecture.md](docs/tech-architecture.md) |
| API 文档与契约 | [docs/api-spec.md](docs/api-spec.md)、[shared/openapi.yaml](shared/openapi.yaml) |
| B1 / B2 / Frontend 分模块文档 | [docs/b1/README.md](docs/b1/README.md)、[docs/b2/README.md](docs/b2/README.md)、[docs/frontend/README.md](docs/frontend/README.md) |
| Orchestrator 路由与任务流转 | [docs/orchestrator-routing-flow.md](docs/orchestrator-routing-flow.md)、[docs/b2/spec/orchestrator/README.md](docs/b2/spec/orchestrator/README.md) |
| AI 协作记录与规则 | [docs/ai-collaboration-log.md](docs/ai-collaboration-log.md)、[AGENTS.md](AGENTS.md)、[docs/ai-skills/](docs/ai-skills/) |
| 真实 E2E 与 repair loop 证据 | [docs/b2/spec/orchestrator/live-e2e-report.spec.md](docs/b2/spec/orchestrator/live-e2e-report.spec.md) |
| 原始设计资料 | [docs/archive/AgentHub- 多Agent协作平台设计.md](<docs/archive/AgentHub- 多Agent协作平台设计.md>)、[PDF](<docs/archive/AgentHub- 多Agent协作平台设计.pdf>) |

## 演示

[![Watch the AgentHub demo](release-assets/demo-cover.png)](demo.mp4)

观看或下载完整演示：[demo.mp4](demo.mp4)。

## 核心能力一览

- **聊天原生的多 Agent 协作**：支持单聊、群聊、Orchestrator 调度、任务卡片、子 Agent 独立消息和 handoff 时间线。
- **真实 workspace 产物**：每个会话都有独立 workspace，支持文件树、代码预览、Diff、上传、artifact manifest 和发布历史。
- **多运行时接入**：内置 Orchestrator、Claude Code、Codex Helper、OpenCode Helper；支持外部 CLI/SDK adapter，以及受限只读 builtin 自建 Agent。
- **Orchestrator 规划与修复闭环**：clarification gate、大上下文 Planner、DAG 执行、并行调度、fallback 可见性、审阅交接、evaluation、reflection 和 repair loop。
- **预览与部署**：支持静态 workspace preview、浏览器级质量验收、静态发布、源码打包和受控容器部署路径。
- **契约驱动开发**：OpenAPI 优先、前端类型生成、后端 adapter contract、spec 与真实 E2E evidence 同步维护。

## 内置 Agent 与协作角色

当前 seed 的内置 Agent 只有 4 个：

| Agent | 职责 |
| --- | --- |
| `orchestrator` | 负责群聊协调、任务规划、Agent 调度、平台工具调用和最终总结；不作为普通子任务执行目标。 |
| `codex-helper` | 适合架构判断、仓库理解、总体规划、最终审阅、疑难 bug 和兜底修复。 |
| `claude-code` | 适合实现、文件编辑、代码生成、调试、修复、审阅和 workspace 修改。 |
| `opencode-helper` | 适合 CLI 风格实现、验证、修复和并行执行。 |

自建 Agent 不会按 provider 自动继承这些内置 planning profile。用户自建 external wrapper 会基于某个内置运行时 Agent；用户自建 `builtin` Agent 是受限只读的 Reader/Review Agent，只能暴露 `read_file`。

## 技术架构

### 目录结构

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

### 后端分层

```text
API layer -> Service layer -> Models/Schemas/Infrastructure
                    |
                    v
              Agent registry -> BaseAgentAdapter implementations
```

关键边界是 `backend/app/agents/base.py`：业务服务通过 registry 和 adapter contract 调用 Agent。原始模型 provider 被收敛在 ModelGateway 层，不作为顶层 Agent 注册。

后端主要模块：

| 模块 | 说明 |
| --- | --- |
| `app/api/v1` | HTTP API、SSE stream、workspace、agent、auth、upload、memory 等入口。 |
| `app/services` | 业务逻辑层，包括 workspace 文件、artifact manifest、deployment、memory、平台工具执行器。 |
| `app/agents` | Agent adapter contract、外部 runtime adapter、builtin runtime、ModelGateway、Orchestrator。 |
| `app/models` | SQLAlchemy async ORM，覆盖用户、会话、消息、Agent、workspace deployment、orchestrator run 记录等。 |
| `app/schemas` | Pydantic v2 schema，是 API、OpenAPI 和前端类型生成的核心来源之一。 |
| `alembic` | 数据库迁移。Compose backend 启动时会执行 `alembic upgrade head`。 |

### Orchestrator 执行链路

典型 Orchestrator 请求会经过以下阶段：

```text
用户消息
-> stream 层构造上下文、workspace、available_agents、memory
-> direct answer / platform facts / clarification gate
-> LLM Planner 或显式 config.tasks
-> task graph 校验、agent 白名单过滤、DAG 依赖分析
-> 并行或顺序调度子 Agent
-> 收集 TaskResult、artifact、tool evidence、child message
-> evaluation / reflection / repair loop
-> preview / browser verify / deployment / source package 等平台工具
-> 最终 process block + 用户可读总结
```

重要规则：

- Planner 只能选择当前群聊可用 Agent，除非 E2E/内部任务显式设置 `available_agents_authoritative=false`。
- Planner 使用专用大上下文路径，默认 `planner_context_max_tokens=128000`，最大可配置到 `1000000`。
- 普通 Orchestrator 主流程上下文默认 `64000 tokens`，子 Agent 分发上下文默认 `64000 tokens`。
- Planner prompt 只保留白名单 memory signals、agent profile 和 recent conversation context，不直接暴露 raw structured memory。
- task card 必须展示实际执行 Agent；发生 fallback 时，run detail/report 保留 `planned/current/final agent` 证据。
- 子 Agent 不负责启动长驻服务；preview、browser verify、部署、源码打包都通过平台 tool 完成。

### Agent Runtime 层

AgentHub 顶层 Agent provider 与底层模型 provider 是分离的：

| 类型 | 说明 |
| --- | --- |
| `claude_code` | Claude Code runtime。默认走 SDK，可配置 CLI fallback。 |
| `codex` | Codex Helper runtime。默认 CLI，可支持 SDK opt-in。 |
| `opencode` | OpenCode CLI runtime，支持本地 auth/state 目录。 |
| `builtin` | 后端内置 AgentLoop + ModelGateway。用户自建 builtin 当前仅允许只读 `read_file`。 |
| `mock` | 测试和开发路径。 |

`ModelGateway` 负责把 Claude / OpenAI-compatible / DeepSeek 等模型后端收敛为统一 stream 接口。它是 builtin agent、direct answer、planner、evaluation 等路径的底层模型访问层。

### SSE 与 ContentBlock

前后端通过 SSE 传输流式事件。核心事件包括：

- `message_start` / `message_done` / `message_error`
- `block_start` / `delta` / `block_end`
- `tool_call` / `tool_result`
- `agent_switch`
- `task_card` / process block / deployment status / artifact references

后端会把执行过程和最终回答拆成结构化 ContentBlock，前端按 block 类型渲染任务卡片、代码、Diff、文件、工具调用、部署状态、review timeline 和最终总结。

### Workspace、预览与部署

- 每个 conversation 对应独立 workspace，生成文件、上传文件、artifact manifest 和发布记录都围绕该 workspace 管理。
- Workspace 文件访问必须经过 path guard，禁止越权读取 `.env`、`.ssh`、secrets、认证目录和平台内部 manifest。
- 静态 preview 由平台 preview service 管理，默认使用 8082 起的端口区间。
- 静态发布通过 `/releases/{release_token}` 暴露不可变快照。
- 源码打包会过滤敏感路径，避免把本地认证状态或密钥打进 zip。
- 容器部署通过受控 worker 执行，Docker 需要 trusted host mode，Podman 可作为 rootless runtime；LLM 不直接拼接 `docker run`。

### 数据与状态

| 存储 | 内容 |
| --- | --- |
| PostgreSQL | 用户、会话、消息、Agent 配置、workspace deployment、orchestrator run/task/attempt/event、memory。 |
| Redis | 缓存、实时/异步辅助能力预留。 |
| `workspaces/` | 会话 workspace 文件。 |
| Docker volumes | Postgres 数据、上传文件、Claude/OpenCode runtime auth state。 |

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
| 完整文档总览 | [docs/README.md](docs/README.md) |
| AI 协作规则 | [AGENTS.md](AGENTS.md) |
| 产品设计 | [docs/product-design.md](docs/product-design.md) |
| 技术架构 | [docs/tech-architecture.md](docs/tech-architecture.md) |
| 团队分工 | [docs/team-division.md](docs/team-division.md) |
| API 指南 | [docs/api-spec.md](docs/api-spec.md) |
| B1 后端/Workspace | [docs/b1/README.md](docs/b1/README.md) |
| B2 Agent Runtime / Orchestrator | [docs/b2/README.md](docs/b2/README.md)、[docs/b2/spec/README.md](docs/b2/spec/README.md) |
| 前端与多端 | [docs/frontend/README.md](docs/frontend/README.md) |
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
