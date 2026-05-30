# AgentHub Backend

FastAPI + PostgreSQL + Redis。

## 启动

通常通过项目根的 `docker compose up -d` 启动。

## 本地纯 Python 开发（不用 Docker）

```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 本地必须自行起 postgres / redis 并改 DATABASE_URL
uvicorn app.main:app --reload --port 8000
```

## 数据库迁移

当前 Docker Compose 不会在 backend 容器启动时自动执行 migration。新服务器、空库或代码更新后必须手动执行：

```bash
# 应用迁移
docker compose exec backend alembic upgrade head

# Seed 内置 Agent
docker compose exec backend python -m app.seeds.seed_agents
```

当前 head 包含 Orchestrator structured memory migration：`9a1b2c3d4e5f_add_orchestrator_memory.py`。该迁移会创建：

- `orchestrator_runs`
- `orchestrator_tasks`
- `orchestrator_task_attempts`
- `orchestrator_run_events`

验证：

```bash
docker compose exec postgres psql -U ${POSTGRES_USER:-agenthub} -d ${POSTGRES_DB:-agenthub} -c "select * from alembic_version;"
docker compose exec postgres psql -U ${POSTGRES_USER:-agenthub} -d ${POSTGRES_DB:-agenthub} -c "\dt orchestrator_*"
```

创建新迁移（模型变更后）：

```bash
docker compose exec backend alembic revision --autogenerate -m "msg"
```

## 测试

```bash
docker compose exec backend pytest
```

## Lint / 类型检查

```bash
docker compose exec backend ruff check
docker compose exec backend mypy app
```

## 目录约定

| 路径 | 归属 |
|------|------|
| `app/core/` | B1 |
| `app/models/` | B1 |
| `app/schemas/` | B1 + B2（共享） |
| `app/api/v1/` | B1（除 `agents.py` 由 B2 主导） |
| `app/services/` | B1 |
| `app/agents/` | **B2** |
| `alembic/` | B1 |
| `tests/` | 全员 |
