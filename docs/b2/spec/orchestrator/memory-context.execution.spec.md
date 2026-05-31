# Orchestrator Memory & Context Manager v1 Execution Spec

> 记录 Orchestrator 结构化记忆 v1 的真实实现结果，并对照
> [memory-context.spec.md](memory-context.spec.md)
> 中的 Proposed 方案说明完成度、偏差和后续边界。
>
> 状态：Implemented
> 最后更新：2026-05-31

> 维护说明：本文是 Orchestrator structured memory v1 的实现报告，部分历史段落仍保留当时的旧路径描述。当前 Orchestrator 已 package 化，主入口为 `backend/app/agents/orchestrator/adapter.py`，memory hooks 为 `backend/app/agents/orchestrator/memory_hooks.py`，stream 注入为 `backend/app/api/v1/stream_orchestrator_context.py`。

---

## 1. 实现结论

本轮已实现 **Orchestrator Memory & Context Manager v1**。

Orchestrator 现在在真实任务编排路径中可以：

- 创建结构化 run。
- 持久化初始 task graph。
- 记录 task started / task result / ReAct decision / finish event。
- 持久化 task attempts、agent、状态、文本摘要、tool 摘要、artifact、missing artifact 和 error。
- 在下一轮 Orchestrator 调用前注入最近结构化 run memory。
- 提供 development-only debug API 查看 run/task/attempt/event。

保持不变：

- 不改 `BaseAgentAdapter`。
- 不改 `StreamChunk`。
- 不改 SSE wire event type。
- 不让 Orchestrator 直接访问数据库。
- 不改变 external agent runtime / direct chat 路由。

---

## 2. 代码落点

### 2.1 数据模型与 migration

新增：

- `backend/app/models/orchestrator_memory.py`
- `backend/alembic/versions/9a1b2c3d4e5f_add_orchestrator_memory.py`

表：

- `orchestrator_runs`
- `orchestrator_tasks`
- `orchestrator_task_attempts`
- `orchestrator_run_events`

并更新：

- `backend/app/models/__init__.py`

实际实现使用 PostgreSQL `JSONB` 保存：

- `depends_on`
- `tool_summaries`
- `artifact_paths`
- `missing_artifact_paths`
- `payload`

### 2.2 Service 层

新增：

- `backend/app/services/orchestrator_memory.py`

包含：

- `OrchestratorMemoryStore`
- `build_orchestrator_memory_context(...)`
- `inject_orchestrator_memory_context(...)`
- debug API 查询 helper：
  - `list_orchestrator_runs(...)`
  - `get_orchestrator_run_detail(...)`

实现细节：

- store 在单次 SSE transaction 内维护 run/task row id 映射。
- task row 支持 upsert 行为，ReAct 新增 task 在首次 result 写入时也能落库。
- context formatter 默认读取最近 terminal runs：`done` / `error` / `cancelled`。
- context system message 标题固定为：

```text
Previous Orchestrator structured memory:
```

### 2.3 Adapter protocol

更新：

- `backend/app/agents/orchestrator_types.py`

新增：

- `OrchestratorMemoryWriter` protocol
- `OrchestratorRunContext.memory_run_id`

Orchestrator adapter 只依赖 protocol，不 import DB model。

### 2.4 Stream 接入

更新：

- `backend/app/api/v1/stream.py`

实际流程：

```text
get_adapter()
build_context()
_orchestrator_conversation_config()
adapter.merged_config(stream_config)
build_orchestrator_memory_context()
inject before latest user request
create OrchestratorMemoryStore
adapter.stream(...)
on disconnect: cancel_active_run()
commit message + memory rows
```

规则：

- 只对 `message.agent_id == "orchestrator"` 生效。
- `orchestrator_memory_enabled=false` 时不注入 structured memory，也不创建 writer。
- memory context 注入在最新 user request 之前，最新请求仍保持 active request 位置。
- structured memory 查询失败时跳过，不中断 SSE。

### 2.5 Orchestrator 写入 hooks

更新：

- `backend/app/agents/orchestrator/adapter.py`
- `backend/app/agents/orchestrator/memory_hooks.py`
- `backend/app/agents/orchestrator/react.py`

写入点：

- task plan 解析且 adapter source 校验通过后：`start_run`
- 每次 attempt 开始前：`record_task_started`
- task 完成后：`record_task_result`
- dependency skipped：记录 skipped task result
- ReAct decision 应用后：`react_decision` event
- final summary 生成后：`finish_run(status="done")`

不创建 run 的路径：

- platform fact deterministic answer
- direct answer
- planner fatal error 且未得到可执行 tasks
- missing adapter source fatal error

### 2.6 Debug API

更新：

- `backend/app/api/v1/conversations.py`
- `backend/app/schemas/conversation.py`
- `shared/openapi.yaml`

新增 development-only endpoint：

```text
GET /api/v1/conversations/{conv_id}/orchestrator-runs?limit=20
GET /api/v1/conversations/{conv_id}/orchestrator-runs/{run_id}
```

行为：

- production 环境返回 404。
- 使用 conversation ownership check。
- list 返回 run 摘要。
- detail 返回 run、tasks、attempts、events。

### 2.7 配置

更新：

- `backend/app/agents/config_validation.py`
- `backend/app/schemas/agent.py`
- `backend/app/seeds/seed_agents.py`
- `shared/openapi.yaml`

新增 builtin/orchestrator config：

| 字段 | 默认 | 校验 |
|---|---:|---|
| `orchestrator_memory_enabled` | `true` | bool |
| `orchestrator_memory_recent_runs` | `3` | `1..10` |
| `orchestrator_memory_context_max_chars` | `6000` | `1..32000` |

seed 中 builtin `orchestrator` 已启用上述默认值。

---

## 3. 与 Proposed Spec 的对照

| Proposed 项 | 实现状态 | 说明 |
|---|---|---|
| 四张 DB 表 | 已实现 | 表名与 proposed 一致。 |
| `OrchestratorMemoryWriter` protocol | 已实现 | 增加 `record_task_planned`、`record_task_started`、`cancel_active_run`。 |
| writer 从 stream 注入 | 已实现 | 通过 `config["orchestrator_memory_writer"]` 注入。 |
| Orchestrator 不直接访问 DB | 已实现 | adapter 只调用 protocol。 |
| `_resolve_tasks()` 后创建 run | 已实现 | 严格在 adapter source 校验通过后创建，避免不可执行 plan 产生 run。 |
| task started/result 写入 | 已实现 | 每个 attempt started，每个 task final result。 |
| ReAct decision event | 已实现 | 在 decision apply 后记录。 |
| summary 后 finish run | 已实现 | static / ReAct 路径都写入 final summary。 |
| structured memory context 注入 | 已实现 | stream 层在 latest user request 前插入 system message。 |
| dev/debug API | 已实现 | list/detail endpoint。 |
| config/schema/openapi/seed | 已实现 | 三个 memory config 字段已同步。 |
| writer 异常不中断 SSE | 已实现于 adapter hook | hook 捕获 writer 异常。DB transaction 级异常仍依赖上层 session 状态。 |
| fatal Orchestrator error 标记 `error` | 部分实现 | v1 只在已进入正常 summary 的路径 finish；plan/source fatal error 不创建 run。运行中未捕获 fatal error 的 error 标记留到后续增强。 |
| request disconnected 标记 `cancelled` | 已实现 | stream 层调用 `cancel_active_run()`。 |

---

## 4. 当前行为边界

### 4.1 什么时候会产生 Orchestrator run

会产生：

- Orchestrator 解析到可执行 task plan。
- adapter source 存在。
- 后续进入 static task execution 或 ReAct task execution。

不会产生：

- 用户问平台事实，例如“当前群聊有哪些 agent / 模型”。
- 用户问 Orchestrator 身份或模型，命中 direct answer。
- planner 输出无效且没有可执行 fallback plan。
- Orchestrator 缺少 sub adapter / adapter factory。

### 4.2 ReAct 动态 task

ReAct 新增 task 的处理：

- `react_decision` event 会记录完整 action payload。
- 新增 task 如果后续执行，会在 `record_task_result()` 时写入 `orchestrator_tasks`。

保留项：

- 如果 ReAct 新增 task 后又跳过且从未执行，v1 只在 event 中可见，不一定有独立 task row。

### 4.3 Memory 不是全局 Agent 记忆

该实现只记录 Orchestrator 的编排状态：

- 谁执行了哪个 task。
- 哪些 artifact 出现或缺失。
- 哪些 attempt 失败。
- ReAct 做了哪些决策。

它不改变 external agents 的上下文来源，也不替代 `ConversationMemory` 文本压缩。

---

## 5. 测试结果

已通过：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator_memory.py tests/test_agent_config_validation.py -q
# 51 passed

uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_context_builder.py tests/test_stream_tool_calls.py tests/test_registry.py tests/test_agent_config_validation.py -q
# 138 passed

uv run python -m ruff check app tests alembic/versions/9a1b2c3d4e5f_add_orchestrator_memory.py
# passed

uv run python -m mypy app/agents app/services/orchestrator_memory.py app/schemas/agent.py app/schemas/conversation.py
# passed
```

已知 mypy 情况：

```bash
uv run python -m mypy app/agents app/services/orchestrator_memory.py app/api/v1/stream.py app/api/v1/conversations.py app/schemas/agent.py app/schemas/conversation.py
```

该命令仍会触发既有 `app/services/model_gateway.py` SDK 类型问题，不是本轮
Orchestrator memory 改动引入。

---

## 6. 后续建议

下一步可以补强：

- 对运行中未捕获 fatal error 的 run 标记 `error`。
- ReAct `add_task` 后立即写入 task row，即使后续被 skip。
- Debug API 增加更精简的 timeline view。
- 在前端 Context 面板展示 Orchestrator structured memory。
- 与未来 Orchestrator native tool calling spec 共享 run memory schema。
