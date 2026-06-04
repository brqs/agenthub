# B1 文档索引

> B1 负责后端核心平台：配置、数据库、API、服务层、Workspace 与后端质量验证。

| 文档 | 用途 |
|---|---|
| [backend-cloud-setup.md](backend-cloud-setup.md) | 后端云端联调环境记录 |
| [backend-test-record.md](backend-test-record.md) | B1 后端测试记录 |
| [spec/stream-error-status.spec.md](spec/stream-error-status.spec.md) | SSE error 状态持久化协同规则 |
| [pivot-demo-script.md](pivot-demo-script.md) | B1 Workspace / Artifact / SSE demo 讲解脚本 |
| [spec/workspace-sandbox.spec.md](spec/workspace-sandbox.spec.md) | Workspace 沙箱隔离规范 |
| [spec/group-observer-context.spec.md](spec/group-observer-context.spec.md) | 群聊 Agent 旁观者上下文与记忆契约 |
| [spec/message-content-block-attribution.spec.md](spec/message-content-block-attribution.spec.md) | ContentBlock block-level `agent_id` 归属契约 |

## 当前 B1 能力快照

| 能力 | 状态 | 主要验证 |
|---|---|---|
| 认证 / 会话 / 消息权限 | Done | `tests/test_b1_quality.py` |
| SSE 状态持久化 | Done | `tests/test_b1_quality.py`, `tests/test_stream_tool_calls.py` |
| Workspace 沙箱 | Done | `tests/test_workspace_service.py` |
| Workspace Artifact API | Done | `tests/test_workspace_api.py` |
| 前端二次编辑回写 | Done | `tests/test_workspace_edit_flow_e2e.py` |
| Preview / Deployment API | Done | `tests/test_workspace_api.py`, `tests/test_workspace_container_release.py` |
| ToolCallBlock 持久化 | Done | `tests/test_stream_tool_calls.py` |
| ContentBlock `agent_id` 归属 | Done | `tests/test_stream_content_blocks.py` |
| 单聊 / 群聊上下文记忆 | Done | `tests/test_context_builder.py` |
| 群聊旁观者身份强化 | Done | `tests/test_context_builder.py`, `tests/test_stream_tool_calls.py` |

## 每次同步后必跑

```bash
docker compose up -d --build backend
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

当前期望迁移版本：

```text
4b5c6d7e8f90
```

如果 deployment / preview 相关测试出现 `workspace_deployments.<column> does not exist`，
优先检查是否漏跑 `alembic upgrade head`。

相关全局文档：

| 文档 | 用途 |
|---|---|
| [../api-spec.md](../api-spec.md) | API 契约说明 |
| [../tech-architecture.md](../tech-architecture.md) | 后端架构上下文 |
| [../team-division.md](../team-division.md) | B1 任务边界 |
