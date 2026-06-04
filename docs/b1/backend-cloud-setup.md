# 后端云端联调环境

> 本文记录当前 AgentHub 后端云端联调环境。
> 不要提交真实 `.env`、API Key、数据库密码或模型服务密钥。

## 当前环境

- 服务器 IP：`111.229.151.159`
- 后端 API 基础地址：`http://111.229.151.159:8000`
- 健康检查：`http://111.229.151.159:8000/health`
- Swagger 文档：`http://111.229.151.159:8000/docs`

## 服务状态

云服务器当前通过 Docker Compose 运行后端服务栈：

- FastAPI backend：已运行，宿主机端口 `8000`
- PostgreSQL：已在 Docker 中运行，容器端口 `5432`
- Redis：已在 Docker 中运行，容器端口 `6379`

PostgreSQL 和 Redis 主要供后端服务内部访问。除非团队明确确认防火墙规则、账号权限和访问范围，否则不要把它们暴露到公网。

## 前端联调

前端联调时，可以把 Vite API 地址指向云端后端：

```env
VITE_API_BASE_URL=http://111.229.151.159:8000
```

前端只应访问后端 API，不应直接连接 PostgreSQL 或 Redis。

## 后端环境变量

服务器上从模板创建 `.env`：

```bash
cp .env.example .env
```

关键配置示例：

```env
DATABASE_URL=postgresql+asyncpg://agenthub:<password>@postgres:5432/agenthub
REDIS_URL=redis://redis:6379/0
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
ENVIRONMENT=development
```

注意：

- 真实数据库密码只写在服务器 `.env` 中。
- OpenAI、Anthropic 等 Provider API Key 只写在服务器 `.env` 中。
- `.env` 已被 Git 忽略，禁止提交。

## Docker 代理

云服务器使用 v2rayA 解决 Docker 拉取镜像的网络问题。Docker daemon 代理配置位于仓库外：

```text
/etc/systemd/system/docker.service.d/http-proxy.conf
```

这是服务器系统级配置，不属于项目代码，不要提交到仓库。

## 常用命令

在云服务器仓库根目录执行：

```bash
cd /home/ubuntu/agenthub
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seeds.seed_agents
docker compose ps
curl -i http://127.0.0.1:8000/health
docker compose logs --tail=80 backend
```

每次 `git pull` 或同步主仓库后，都必须先执行：

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

当前期望 head：

```text
4b5c6d7e8f90
```

如果未执行最新 migration，workspace preview / deployment API 会因为
`workspace_deployments` 缺少 release、snapshot 或 container runtime 字段而失败。

停止服务栈：

```bash
docker compose down
```

只重启后端：

```bash
docker compose restart backend
```

## 数据库初始化

当前项目已经包含完整 Alembic migration。新服务器、空数据库或旧服务器代码更新后，都应执行：

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seeds.seed_agents
```

当前迁移链：

```text
829867f35d97_init.py
-> c2f8e1d9a4b7_add_conversation_memories.py
-> f4a3b2c1d0e9_add_workspaces.py
-> 9a1b2c3d4e5f_add_orchestrator_memory.py
-> 2f3a4b5c6d7e_add_workspace_deployments.py
-> 3a4b5c6d7e8f_harden_workspace_releases.py
-> 4b5c6d7e8f90_add_container_deployment_runtime_metadata.py
```

`9a1b2c3d4e5f_add_orchestrator_memory.py` 新增 Orchestrator structured memory 表：

- `orchestrator_runs`
- `orchestrator_tasks`
- `orchestrator_task_attempts`
- `orchestrator_run_events`

这些表用于 Orchestrator 跨轮结构化记忆。如果不执行 `alembic upgrade head`，Orchestrator 仍可启动，但真实任务编排时 structured memory 写入和 debug API 会不可用。

后续三条 deployment migration 新增：

- `workspace_preview_sessions` 快照隔离字段。
- `workspace_deployments`、release token、snapshot、digest、file count、过期时间。
- container deployment runtime metadata，包括 runtime id、image/container id、host port、healthcheck、logs tail。

这些字段用于 preview、static release、source zip 和 container deployment。

验证当前数据库版本：

```bash
docker compose exec postgres psql -U ${POSTGRES_USER:-agenthub} -d ${POSTGRES_DB:-agenthub} -c "select * from alembic_version;"
```

期望版本：

```text
4b5c6d7e8f90
```

验证 Orchestrator structured memory 表：

```bash
docker compose exec postgres psql -U ${POSTGRES_USER:-agenthub} -d ${POSTGRES_DB:-agenthub} -c "\dt orchestrator_*"
```

期望包含：

```text
orchestrator_runs
orchestrator_tasks
orchestrator_task_attempts
orchestrator_run_events
```

`seed_agents` 会 upsert 内置 agent。每次更新内置 agent 配置后都建议执行一次，确保 `orchestrator` 的 `orchestrator_memory_*` 配置同步到数据库。

## Preview / Deployment 运维配置

Workspace preview 和 deployment 均由平台后端管理，Agent runtime 不直接启动 8082 服务，也不直接执行部署命令。

常用环境变量：

```env
PREVIEW_PORT_START=8082
PREVIEW_PORT_END=8182
PREVIEW_SNAPSHOT_DIR=/tmp/agenthub_preview_snapshots
PREVIEW_SESSION_TTL_SECONDS=3600

DEPLOYMENT_PUBLIC_BASE_URL=http://111.229.151.159:8000
DEPLOYMENT_STATIC_ROOT=/tmp/agenthub_static_releases
DEPLOYMENT_EXPORT_TTL_SECONDS=86400
DEPLOYMENT_JANITOR_INTERVAL_SECONDS=300

DEPLOYMENT_CONTAINER_ENABLED=true
DEPLOYMENT_CONTAINER_RUNTIME=docker
DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=true
DEPLOYMENT_CONTAINER_PUBLIC_BASE_URL=http://111.229.151.159
DEPLOYMENT_CONTAINER_PORT_START=8081
DEPLOYMENT_CONTAINER_PORT_END=8085
```

运维规则：

- Preview 是临时开发预览，服务隔离快照，不直接暴露原始 workspace。
- Static release 是不可变发布版本，stop 后 token 立即失效。
- Source zip 有过期时间，janitor 清理过期文件。
- Container deployment 必须经过平台 worker 和 policy 校验，不允许 Agent 直接执行任意 Docker 命令。
- 如果服务器不允许容器部署，设置 `DEPLOYMENT_CONTAINER_ENABLED=false`，API 会返回受控的 not_supported / error 状态，而不是让 runtime 自行部署。

## B1 云端 E2E Checklist

更新服务器后建议至少验证：

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/docs
docker compose exec backend alembic current
docker compose exec backend python -m app.seeds.seed_agents
docker compose exec backend pytest tests/test_workspace_api.py tests/test_stream_tool_calls.py -q
```

真实联调时再补：

- 登录 / 注册。
- 创建 group conversation。
- 发送 Orchestrator 消息生成 HTML。
- 调用 workspace tree / file API。
- 调用 preview API。
- 调用 deployments API 创建 static site。
- 调用 source zip download。
- stop preview / deployment 后确认 URL 失效。

## 安全注意事项

- 不要提交 `.env`。
- 不要提交真实数据库凭据。
- 不要提交 OpenAI、Anthropic 或其他 Provider API Key。
- 不要把 Redis 暴露到公网。
- 除非有经过团队确认的临时联调需求，否则不要把 PostgreSQL 暴露到公网。
- 前端和联调测试优先通过后端 API 访问数据。
