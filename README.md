# AgentHub

> IM 聊天式的多 Agent 协作平台 —— 像聊微信一样，与多个 AI 协作完成复杂任务。

[![status](https://img.shields.io/badge/status-MVP-yellow)]() [![python](https://img.shields.io/badge/python-3.11+-blue)]() [![react](https://img.shields.io/badge/react-18-61dafb)]() [![license](https://img.shields.io/badge/license-MIT-green)]()

**演示站点**：[ag.brqs.link](http://ag.brqs.link/login)

---

## ✨ 核心特性

- 💬 **IM 体验**：类似飞书 / 微信的聊天界面，零学习成本
- 🤖 **多 Agent 协作**：单聊 + 群聊，Orchestrator 自动拆解任务
- ⚡ **流式响应**：SSE 实时逐字输出，无加载等待焦虑
- 🎨 **富媒体产物**：代码高亮、Diff 视图、网页预览内联展示
- 🔌 **生态开放**：接入 Claude Code / Codex / OpenCode runtime，支持团队自建 BuiltinAgent
- 🌐 **跨平台**：Web / Tauri 桌面 / PWA 移动一份代码

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Node.js 20+ & pnpm 8+
- 按需准备 Claude Code / Codex / OpenCode runtime 环境；BuiltinAgent 的 ModelGateway 需要 Anthropic API Key 和/或 OpenAI-compatible API Key

### 一键启动

```bash
# 1. 克隆并进入项目
cd agenthub

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，按需填入 runtime / ModelGateway 所需配置

# 3. 启动后端（Postgres + Redis + FastAPI）
docker compose up -d

# 4. 运行数据库迁移 + Seed 内置 Agent
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seeds.seed_agents

# 5. 启动前端（独立终端）
cd frontend
pnpm install
pnpm dev

# 6. 打开浏览器
open http://localhost:5173
```

### 验证

- 前端：http://localhost:5173
- 后端 API 文档：http://localhost:8000/docs
- 后端健康检查：http://localhost:8000/health

### External runtime smoke checks

OpenCode is executed inside the backend container as a CLI runtime. After
building and starting Docker, verify it with:

```bash
docker compose exec backend opencode --version
docker compose exec backend opencode auth list
docker compose exec backend env | grep OPENCODE
docker compose exec backend sh -lc 'rm -rf /tmp/opencode-smoke && mkdir -p /tmp/opencode-smoke && opencode run --format json --model deepseek/deepseek-chat --dir /tmp/opencode-smoke "create index.html, styles.css, and app.js, then summarize briefly"'
```

OpenCode credentials can be provided through backend `.env` provider keys, or by
running `docker compose exec backend opencode auth login`. The compose file keeps
that login state in the `opencode-state` volume.

Claude Code is also executed inside the backend container. Verify the SDK and
runtime auth surface with:

```bash
docker compose exec backend python -c "import claude_agent_sdk; print('sdk ok')"
docker compose exec backend sh -lc 'ls -la $AGENTHUB_CLAUDE_AUTH_DIR'
docker compose exec backend env | grep -E 'ANTHROPIC|CLAUDE|AGENTHUB_CLAUDE'
docker compose exec backend sh -lc 'HOME=$AGENTHUB_CLAUDE_AUTH_DIR claude -p "只回复 OK" --output-format text'
```

Claude Code credentials can be provided through backend `.env` provider keys
such as `ANTHROPIC_API_KEY`, or through persisted CLI login state in the
`claude-state` volume. To populate that volume interactively, run Claude with
`HOME=$AGENTHUB_CLAUDE_AUTH_DIR` inside the backend container so `.claude.json`
and `.claude/` are stored in the shared auth directory.

Simple direct-chat shortcut replies can use the configured QA model backend and
do not prove that Claude SDK/CLI task execution is available. Artifact/build
tasks use the Claude SDK runtime first, then the CLI fallback only if the SDK
module is absent; both runtime paths must pass AgentHub's backend auth probe.

## 📁 项目结构

```
agenthub/
├── CLAUDE.md              ← AI 协作宪法（必读）
├── docs/                  ← 全部文档
│   ├── development-plan.md
│   ├── team-division.md
│   ├── tech-architecture.md
│   ├── api-spec.md
│   └── product-design.md
├── shared/
│   └── openapi.yaml       ← 前后端契约（唯一真相源）
├── backend/               ← FastAPI 后端
│   └── app/
│       ├── core/          【B1】配置、DB、认证基础
│       ├── models/        【B1】SQLAlchemy 模型
│       ├── schemas/       【共享】Pydantic Schema
│       ├── api/v1/        【B1】路由层
│       ├── services/      【B1】业务逻辑
│       └── agents/        【B2】External runtime、BuiltinAgent、ModelGateway、Orchestrator
└── frontend/              ← React + Vite 前端
    └── src/
        ├── lib/           API 客户端、SSE、类型
        ├── stores/        Zustand 状态
        ├── hooks/         业务 Hook
        ├── pages/         页面
        └── components/    UI 组件
```

## 👥 团队分工

- **F**（前端）：`frontend/**`
- **B1**（后端核心）：`backend/app/{core,models,services,api}/**`
- **B2**（Agent 集成）：`backend/app/agents/**`

详见 [docs/team-division.md](docs/team-division.md)。

## 📖 文档导航

| 你想做什么 | 看哪个文档 |
|-----------|-----------|
| 了解项目全貌 | [development-plan.md](docs/development-plan.md) |
| 知道谁负责什么 | [team-division.md](docs/team-division.md) |
| 写代码 / 改架构 | [tech-architecture.md](docs/tech-architecture.md) |
| 调 API / 加 API | [api-spec.md](docs/api-spec.md) |
| 做 UI / 改交互 | [product-design.md](docs/product-design.md) |
| AI 协作（必读） | [CLAUDE.md](CLAUDE.md) |

## 🛠 常用命令

```bash
# ─── Backend ───
docker compose up -d                              # 启动
docker compose logs -f backend                    # 看日志
docker compose exec backend alembic upgrade head  # 迁移
docker compose exec backend pytest                # 测试

# ─── Frontend ───
cd frontend
pnpm dev                                          # 启动
pnpm gen:types                                    # 重新生成 OpenAPI 类型
pnpm test                                         # 测试
pnpm build                                        # 构建

# ─── 完整重置 ───
docker compose down -v   # 删除所有数据
```

当前迁移链包含 Orchestrator structured memory 表。更新代码后请确认已执行 `alembic upgrade head`，否则 Orchestrator 编排记忆和调试接口不可用。详见 [backend/alembic/README.md](backend/alembic/README.md) 与 [Orchestrator Memory Spec](docs/b2/spec/orchestrator/memory-context.spec.md)。

## 🧪 技术栈

| 层级 | 选型 |
|------|------|
| 前端 | React 18 + Vite + TypeScript + Tailwind + shadcn/ui |
| 后端 | Python 3.11 + FastAPI + Uvicorn |
| 数据库 | PostgreSQL 15 + Redis 7 |
| AI SDK | anthropic + openai |
| 实时 | SSE (Server-Sent Events) |
| 容器 | Docker Compose |

## 📝 License

MIT
