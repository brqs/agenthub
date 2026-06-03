---
name: backend-deploy
description: Use when deploying or restarting the AgentHub backend, checking whether local code is synced with the running service, reseeding built-in agents after config changes, or verifying local and public backend health.
---

# AgentHub Backend Deploy Skill

## When To Use

Use this skill when the user asks to:

- 部署或重启 AgentHub 后端。
- 检查当前本地代码是否已同步到运行中的后端服务。
- 修改 `seed_agents.py`、`ORCHESTRATOR_DEFAULTS` 或内置 Agent 配置后重新 seed。
- 验证本机后端与公网后端健康状态。
- 部署后端代码
- 前端不变，只更新本机后端服务。

## Environment Facts

| Item | Value |
|------|-------|
| Backend host | 本机，公网 IP `111.229.151.159` |
| Backend port | `8000` |
| Frontend | `http://154.44.25.94:1573`，独立部署，默认不操作 |
| Backend cwd | `/home/ubuntu/agenthub/backend` |
| Repo cwd | `/home/ubuntu/agenthub` |
| Preferred runner | `uv run ...` |
| Possible systemd service | `agenthub-backend` |

Preview `8082` 由平台 preview service 管理。不要让 Agent runtime 或部署流程自行启动 `npm run dev`、`vite --host`、`python -m http.server` 等长驻前端服务。

## Safety Rules

- 先检查，再部署；不要默认 `git pull`、`git stash` 或覆盖本地修改。
- 不部署前端，除非用户明确要求。
- 真实 E2E 前不能只检查 `/health`。`/health` 只能证明服务存活，不能证明运行实例已加载本轮代码。
- 不输出 `.env`、API key、JWT secret、数据库密码等敏感信息。
- 不使用宽泛的 `pkill -f python`、`killall python` 等命令。
- 不停止 preview 进程，除非明确确认它就是当前测试需要释放的 session。
- 新增或修改 Alembic migration 后，必须执行 `uv run alembic upgrade head`。
- 修改 seed 或 Orchestrator 默认配置后，必须执行 `uv run python -m app.seeds.seed_agents`。

## Standard Workflow

### 1. Inspect Code And Runtime

```bash
cd /home/ubuntu/agenthub
git status --short
git branch --show-current
git log -1 --oneline
git diff --name-only
git ls-files --others --exclude-standard
```

检查当前后端运行方式：

```bash
systemctl status agenthub-backend --no-pager
ps aux | rg 'uvicorn|app.main:app' | rg -v rg
```

如果 systemd 服务不存在或未使用 systemd，按现有 `uvicorn` 进程方式重启；不要假设一定是 systemd。

记录重启前 PID，后续必须和重启后 PID 对比：

```bash
pgrep -af 'uvicorn app.main:app.*--port 8000'
```

### 2. Classify Sync Actions

根据本轮变更范围决定部署动作：

| 变更范围 | 必须执行 |
|---|---|
| `backend/app/**`、`backend/scripts/**`、后端依赖或配置 | 重启后端 |
| `backend/alembic/versions/**`、数据库模型 | migration upgrade + 重启后端 |
| `seed_agents.py`、`ORCHESTRATOR_DEFAULTS`、内置 Agent config | 重启后端 + seed |
| 仅 docs / tests | 不要求重启，但需在报告中明确记录 |
| `frontend/**` 且要求验收远端 UI | 进入单独的前端部署流程 |

当前后端与代码仓库在同一台机器，因此不需要额外复制文件。未来若后端迁移到独立服务器，必须先同步代码到目标服务器，再执行本文的 migration、重启和 seed。

### 3. Run Focused Validation

按变更范围选择测试。Orchestrator / B2 后端常用验证：

```bash
cd /home/ubuntu/agenthub/backend
uv run pytest tests/test_agent_config_validation.py tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_platform_tools.py -q
uv run ruff check app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/browser_preview_verifier.py app/core/config.py app/schemas/agent.py
uv run mypy app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/browser_preview_verifier.py app/core/config.py app/schemas/agent.py
```

若是小改动，可先跑相关单测；正式交付前再跑更大范围回归。

### 4. Apply Database Migrations When Needed

新增或修改 `backend/alembic/versions/**`、数据库模型时：

```bash
cd /home/ubuntu/agenthub/backend
uv run alembic upgrade head
uv run alembic current
```

没有 migration 变更时，也建议在正式 live E2E 报告中保留一次 `uv run alembic current` 输出。

### 5. Restart Backend

优先使用当前实际运行方式。

Systemd:

```bash
sudo systemctl restart agenthub-backend
sleep 3
systemctl status agenthub-backend --no-pager | head -20
```

直接 `uvicorn` 方式：

```bash
cd /home/ubuntu/agenthub/backend
pgrep -af 'uvicorn app.main:app.*--port 8000'
# 只结束上一步确认出的旧 uvicorn PID。
kill <confirmed_old_uvicorn_pid>
nohup uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info > /tmp/agenthub_backend.log 2>&1 &
sleep 3
pgrep -af 'uvicorn app.main:app.*--port 8000'
tail -80 /tmp/agenthub_backend.log
```

如果端口已被旧后端占用，只结束确认后的旧 `uvicorn app.main:app --port 8000` 进程。重启后 PID 必须变化。

### 6. Seed Built-In Agents When Needed

当修改了以下内容时必须 seed：

- `app/seeds/seed_agents.py`
- `ORCHESTRATOR_DEFAULTS`
- 内置 Agent provider/config/capabilities
- Orchestrator `llm_planning`、并行 DAG、tool 配置

```bash
cd /home/ubuntu/agenthub/backend
uv run python -m app.seeds.seed_agents
```

seed 后通过 `/api/v1/agents` 或 live E2E 验证数据库里的旧配置已更新。

### 7. Health And Runtime Checks

```bash
curl --noproxy '*' -sS http://127.0.0.1:8000/health
curl --noproxy '*' -sS http://111.229.151.159:8000/health
uv run alembic current
```

两者都应返回健康状态。公网健康检查失败时，前端真实链路仍不可用，即使 localhost 正常。

最后根据本轮变更增加至少一个关键 API 断言。例如：

- Agent config 改动：登录后检查 `/api/v1/agents`。
- 新增 API：检查 OpenAPI 是否暴露新路由。
- Preview / deployment：请求对应 API 并检查状态字段。

部署发布后端或原生部署相关变更可直接执行公网 API E2E，不依赖远端前端重新发布：

```bash
cd /home/ubuntu/agenthub/backend
uv run python scripts/deployment_release_api_e2e.py
```

报告写入：

```text
/tmp/agenthub_deployment_release_api_e2e_report.json
```

只有“PID 已变化 + health 正常 + migration 正确 + 关键 API 断言通过”才能说明运行实例已经同步到本轮代码。

## Troubleshooting

服务启动失败：

```bash
journalctl -u agenthub-backend -n 80 --no-pager
tail -120 /tmp/agenthub_backend.log
```

数据库或容器依赖：

```bash
cd /home/ubuntu/agenthub
docker compose ps
```

公网不可达：

- 确认后端监听 `0.0.0.0:8000`。
- 确认安全组 / UFW 放行 `8000/tcp`。
- 使用 `--noproxy '*'` 排除代理误判。

## Quick Checklist

- `git status --short` 已查看，没有误部署无关修改。
- 已根据 diff 判断是否需要 migration、重启、seed 或前端部署。
- 相关测试 / lint / type check 已运行或明确记录未运行原因。
- 如改了 migration 或数据库模型，已执行 `uv run alembic upgrade head`。
- 如改了后端运行代码，重启前后 PID 已记录且确实变化。
- 如改了内置 Agent 配置，已执行 `uv run python -m app.seeds.seed_agents`。
- `127.0.0.1:8000/health` 与 `111.229.151.159:8000/health` 都正常。
- 已执行至少一个与本轮改动对应的关键 API 断言。
- 如是 Orchestrator 改动，已运行对应 live E2E 或记录阻断原因。
