# Alembic Migrations

## 当前迁移链

截至 2026-05-30，当前 head 为：

```text
829867f35d97_init.py
-> c2f8e1d9a4b7_add_conversation_memories.py
-> f4a3b2c1d0e9_add_workspaces.py
-> 9a1b2c3d4e5f_add_orchestrator_memory.py
```

`9a1b2c3d4e5f_add_orchestrator_memory.py` 新增 Orchestrator structured memory 表：

- `orchestrator_runs`
- `orchestrator_tasks`
- `orchestrator_task_attempts`
- `orchestrator_run_events`

这四张表用于记录 Orchestrator 真实编排流转、子任务、attempt、artifact、错误和 ReAct decision。对应模型在 `backend/app/models/orchestrator_memory.py`，service 在 `backend/app/services/orchestrator_memory.py`。部署或本地更新后必须执行：

```bash
docker compose exec backend alembic upgrade head
```

## 首次创建迁移

启动 Docker Compose 后：

```bash
docker compose exec backend alembic revision --autogenerate -m "init schema"
docker compose exec backend alembic upgrade head
```

## 后续变更

修改 `app/models/` 中的模型后：

```bash
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
```

## 回滚

```bash
docker compose exec backend alembic downgrade -1
```

## Seed 内置 Agent

```bash
docker compose exec backend python -m app.seeds.seed_agents
```
