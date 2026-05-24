# Alembic Migrations

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
