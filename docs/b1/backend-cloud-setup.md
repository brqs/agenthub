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
docker compose ps
curl -i http://127.0.0.1:8000/health
docker compose logs --tail=80 backend
```

停止服务栈：

```bash
docker compose down
```

只重启后端：

```bash
docker compose restart backend
```

## 数据库初始化

当前已在云服务器确认数据库状态：

- `backend/alembic/versions/` 目录只有 `.gitkeep`，没有 migration 文件。
- `alembic heads` 为空。
- 数据库中不存在 `alembic_version` 表。
- PostgreSQL 当前是空库，没有业务表。

因此现在不要直接把 `alembic upgrade head` 当作已完成初始化的标志。当前项目还没有可执行的初始建表 migration，需要先由 B1 补齐初始迁移文件。

当 Alembic migration 文件准备好后，执行数据库迁移：

```bash
docker compose exec backend alembic upgrade head
```

初始化内置 Agent：

```bash
docker compose exec backend python -m app.seeds.seed_agents
```

建议后续分支：

```text
feat/B1-initial-db-migration
```

迁移文件合并并部署到云服务器后，再执行 `alembic upgrade head` 和 `seed_agents`。

## 安全注意事项

- 不要提交 `.env`。
- 不要提交真实数据库凭据。
- 不要提交 OpenAI、Anthropic 或其他 Provider API Key。
- 不要把 Redis 暴露到公网。
- 除非有经过团队确认的临时联调需求，否则不要把 PostgreSQL 暴露到公网。
- 前端和联调测试优先通过后端 API 访问数据。
