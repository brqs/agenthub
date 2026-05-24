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

```bash
# 创建迁移（首次或模型变更后）
docker compose exec backend alembic revision --autogenerate -m "msg"

# 应用迁移
docker compose exec backend alembic upgrade head

# Seed 内置 Agent
docker compose exec backend python -m app.seeds.seed_agents
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
