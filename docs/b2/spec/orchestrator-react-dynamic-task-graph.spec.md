# Orchestrator ReAct Dynamic Task Graph Spec

> 定义 Orchestrator 从当前 `plan once -> execute sequentially -> summarize` 升级为 ReAct-style 动态任务图编排器的设计契约。
>
> 状态：Proposed
> 最后更新：2026-05-30

---

## 1. 校验结论

该设计与当前 Orchestrator 架构兼容，可以复用现有 `SubTask`、`TaskResult`、`TaskAttempt`、`OrchestratorRunContext`、`_run_task()`、任务结果注入和 summary 逻辑。

必须锁定以下边界，避免实现时破坏现有契约：

- `react_enabled` 在运行时默认 `false`，旧配置和旧测试继续走现有静态执行流。
- seed 里的 builtin `orchestrator` 默认设置 `react_enabled=true`，让产品默认体验启用 ReAct。
- ReAct 不新增 endpoint、不改 DB schema、不改 `BaseAgentAdapter`、`StreamChunk` 或 SSE wire contract。
- ReAct 不暴露模型内部 `thought` / `chain_of_thought`；用户只看到步骤、动作和 observation 的摘要。
- ReAct 仍然单任务顺序执行；本版本不实现并行调度。
- 动态任务图采用受控 action patch，不允许 replanner 任意重写已执行任务。

---

## 2. 目标

当前 Orchestrator 是一次性规划执行器：

```text
initial plan -> for task in tasks -> collect result -> final summary
```

ReAct Dynamic Task Graph 的目标是改为：

```text
initial plan
-> execute one runnable task
-> observe result
-> replanner decides add/update/skip/finish
-> repeat until finish or max_iterations
-> final summary
```

Orchestrator 仍不直接完成文件生成、代码实现或命令执行；它只负责规划、调度、观察、动态调整任务图和汇总。

---

## 3. 配置契约

新增 builtin agent config 字段：

| 字段 | 类型 | 默认 | 说明 |
|---|---:|---:|---|
| `react_enabled` | bool | `false` | 是否启用 ReAct 动态任务图执行。 |
| `react_trace_visible` | bool | `true` | 是否向用户输出 ReAct step/action/observation 摘要。 |
| `react_decision_max_tokens` | int | `1024` | replanner 单次决策最大 token，建议校验范围 `1..4096`。 |

复用现有字段：

| 字段 | 说明 |
|---|---|
| `max_iterations` | ReAct loop 最大轮数；沿用现有 `1..50` 校验。 |
| `planner_model_backend` | replanner ModelGateway backend；缺省回退 `model_backend`。 |
| `orchestrator_llm_config` | planner/replanner 可复用的模型参数。 |
| `available_agents` / `managed_agent_ids` | allowed agent 白名单，仍由 group conversation 注入优先覆盖。 |
| `task_result_context_max_chars` / `task_result_item_max_chars` | observation 和后续任务结果注入的字符预算。 |

配置校验、`AgentConfig` schema、OpenAPI 和 seed 必须同步更新。seed 中 builtin `orchestrator` 应设置：

```json
{
  "react_enabled": true,
  "react_trace_visible": true
}
```

---

## 4. ReAct 执行模型

### 4.1 入口顺序

`OrchestratorAdapter.stream()` 的前置分支保持不变：

1. 发出 `start`。
2. 平台事实问题短路。
3. direct answer 短路。
4. `_resolve_tasks()` 生成初始任务图。
5. `_ensure_adapter_source()` 校验子 agent 来源。
6. `react_enabled=true` 时进入 ReAct loop，否则走现有静态 `for task in tasks` 流程。

### 4.2 Loop 语义

每轮 ReAct loop：

1. 从任务图中选择第一个 runnable task。
2. runnable task 定义为 `PENDING` 且所有 `depends_on` 都是 `SUCCEEDED`。
3. 调用现有 `_run_task()` 执行该任务。
4. 从 `TaskResult` 生成 observation。
5. 调用 replanner 获取严格 JSON decision。
6. 校验并应用 action。
7. 遇到 `finish`、fatal replanner error 或达到 `max_iterations` 时结束。

如果没有 runnable task，但仍有 pending/skipped/failing graph 状态，也应调用 replanner，让它选择 `add_task`、`skip_task` 或 `finish`，避免静默卡死。

### 4.3 Observation 内容

Observation 只使用 Orchestrator 已经收集到的事实：

- task id、title、final state、final agent。
- text preview。
- tool summaries。
- artifact paths。
- missing artifact paths。
- error reason。
- previous attempt failure。

Observation 不包含模型内部推理。

---

## 5. Replanner 契约

建议新增 helper 模块 `backend/app/agents/orchestrator_react.py`，负责 replanner prompt、JSON 解析、action 校验和 action 应用。

replanner 输入：

- 最新用户请求。
- 当前 allowed agents 描述。
- 当前 task graph。
- 当前 task states。
- recent observations。
- artifact / missing artifact / error 摘要。
- 已执行 iteration count 和 `max_iterations`。

replanner 输出必须是严格 JSON：

```json
{
  "actions": [
    {
      "type": "add_task",
      "task": {
        "task_id": "fix-html",
        "agent_id": "codex-helper",
        "title": "Fix HTML behavior",
        "instruction": "Fix the missing click behavior.",
        "depends_on": ["verify-html"],
        "priority": 3,
        "expected_output": "orchestrator-flow-smoke.html",
        "include_history": true
      }
    },
    {
      "type": "finish",
      "reason": "All required artifacts verified."
    }
  ],
  "summary": "Verification failed, adding a fix task."
}
```

允许的 action：

| Action | 规则 |
|---|---|
| `add_task` | 追加新的 pending `SubTask`；`task_id` 唯一；`agent_id` 必须在 allowed agents 内。 |
| `update_task` | 只允许修改未执行任务；可 patch `agent_id/title/instruction/depends_on/priority/expected_output/include_history`。 |
| `skip_task` | 只允许跳过未执行任务；必须记录 reason。 |
| `finish` | 结束 loop 并输出最终 summary。 |

禁止：

- 调度 `orchestrator` 自身。
- 调度群聊外 agent，例如 group 中不存在的 `web-designer`。
- 创建重复 `task_id`。
- 引用未知 `depends_on`。
- 修改已 `SUCCEEDED`、`FAILED`、`ARTIFACT_MISSING` 或 `SKIPPED` 的任务。
- 执行未通过校验的 action。

---

## 6. 用户可见输出

ReAct 不新增 SSE event type。继续使用现有 `text` block、`agent_switch`、子 agent stream 和 final `done`。

当 `react_trace_visible=true` 时，用户可见摘要示例：

```text
ReAct step 2
Observation: verify-html failed: missing click behavior
Action: add_task fix-html -> @codex-helper
```

输出要求：

- 不输出原始 replanner JSON。
- 不输出 `thought` / `chain_of_thought`。
- `react_trace_visible=false` 时隐藏 ReAct step 摘要，但仍显示子 agent 输出和最终 `Execution summary`。
- 最终 summary 复用现有 `_summary_text()`，并包含动态新增、跳过和失败任务。

---

## 7. 失败处理

- 子任务失败时，先走现有 per-task fallback/retry。
- retry 后仍失败，将 failure observation 交给 replanner。
- replanner 无效 JSON、未知 action、非法 agent、非法依赖、非法修改已完成任务时，不执行任何 action。
- replanner fatal error 后应安全停止，并输出可见错误摘要或 final summary。
- 达到 `max_iterations` 后停止，不再调用 replanner；仍输出 final summary。
- 未执行且无法继续的 pending task 应在 summary 中保留状态，或由 replanner 明确 `skip_task`。

---

## 8. 测试计划

必须覆盖：

1. `react_enabled=false` 时旧静态执行流不变。
2. `react_enabled=true` 时：初始计划执行 verify，verify 失败，replanner `add_task` 创建 fix，fix 成功，replanner `finish`。
3. `add_task` 使用群聊外 agent 被拒绝。
4. `update_task` 不能修改 succeeded task。
5. `skip_task` 标记未执行 task 为 skipped 且不执行。
6. `max_iterations` 到达后停止。
7. 输出不包含 `thought` / `chain_of_thought`。
8. ReAct 新增任务能收到 `Previous sub-agent results`。
9. Stream/API 测试确认 group conversation 只调度当前 `Conversation.agent_ids` 内 agent。
10. 配置校验、OpenAPI、seed agents 校验包含新增 ReAct 字段。

建议回归命令：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py -q
uv run python -m pytest tests/test_stream_tool_calls.py tests/test_registry.py -q
uv run python -m pytest tests/test_agent_config_validation.py -q
uv run python -m ruff check app tests
uv run python -m mypy app/agents app/schemas/agent.py
```

---

## 9. 非目标

本版本不实现：

- 并行执行子任务。
- 持久化 task graph 到数据库。
- 新增任务运行 API。
- 前端专用 ReAct timeline event type。
- 暴露完整模型推理链。
- 让子 agent 互相直接通信；所有交接仍经过 Orchestrator。

