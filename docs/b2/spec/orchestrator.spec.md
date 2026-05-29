# Orchestrator Spec

> 定义 AgentHub 多 Agent 编排器的当前行为契约，包括任务规划、任务分配、子任务流转、事件聚合和失败处理。
>
> 版本：v1.1
> 最后更新：2026-05-29

---

## 1. 目标

`OrchestratorAdapter` 是 AgentHub 群聊和复杂任务编排入口。它不直接完成文件生成、代码实现或工具调用，而是根据用户请求生成子任务，并把子任务派发给真实的子 Agent。

Orchestrator 负责：

1. 判断请求是否只是普通问答；若是，走 direct answer，不启动子 Agent runtime。
2. 解析或生成结构化任务计划。
3. 按优先级和依赖顺序调度子 Agent。
4. 把多个子 Agent 的 `StreamChunk` 合并为单个 SSE 流。
5. 对 `block_index` 和 `tool_call.call_id` 做全局重映射，避免前端渲染冲突。
6. 将子 Agent 失败转换为普通文本失败块，继续执行可独立任务。
7. 输出最终 execution summary，并以 `done` 结束非 fatal 的部分失败流程。

Orchestrator 不负责：

- 直接访问数据库。
- 直接 import 或调用具体 provider SDK。
- 并发执行子任务。
- 启动 preview/deploy/server 等长驻端口服务。
- 判断 workspace artifact 是否真实生成成功；当前仅以子 Agent stream 成功/失败作为任务状态。

---

## 2. Adapter 契约

Orchestrator 实现 `BaseAgentAdapter.stream()`，签名必须和基类保持一致：

```python
async def stream(
    self,
    messages: list[ChatMessage],
    *,
    system_prompt: str | None = None,
    config: dict[str, Any] | None = None,
    workspace_path: Path | None = None,
    tool_specs: list[ToolSpec] | None = None,
) -> AsyncIterator[StreamChunk]
```

参数语义：

| 参数 | 说明 |
|---|---|
| `messages` | ContextBuilder 组装好的会话历史。 |
| `system_prompt` | Orchestrator 自身 prompt override；会传给 planner/direct answer prompt 组合逻辑。 |
| `config` | Orchestrator 专属配置和运行时注入项。 |
| `workspace_path` | 当前 conversation workspace root，透传给子 Agent。 |
| `tool_specs` | 工具白名单/schema，透传给子 Agent。 |

`config` 支持的关键字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `tasks` | `list[dict]` | 显式任务计划；存在时优先于自动规划。 |
| `sub_adapters` | `dict[str, BaseAgentAdapter]` | 单测或注入式运行时直接提供子 Adapter。 |
| `adapter_factory` | callable | 生产 registry 注入；按 `agent_id` 延迟获取子 Adapter。 |
| `managed_agent_ids` | `list[str]` | 可被 Orchestrator 管理的子 Agent 白名单。 |
| `default_sub_agents` | `list[str]` | `managed_agent_ids` 的兼容别名。 |
| `available_agents` | `list[dict]` | planner 可用 Agent 描述；优先于 `managed_agent_ids` 用于 LLM planner。 |
| `llm_planning` | `bool` | 为 `true` 时启用 LLM planner。 |
| `planner_gateway` | object | 注入式 planner gateway；存在时启用 LLM planner。 |
| `orchestrator_llm_config` | `dict` | planner 模型参数；存在且为 object 时启用 LLM planner。 |
| `planner_model_backend` | `str` | planner 使用的 ModelGateway backend；默认回退到 `model_backend`，再回退到 `claude`。 |
| `planner_fallback_to_template` | `bool` | planner 失败后是否回退 legacy template 任务。 |
| `direct_answer_on_planner_failure` | `bool` | planner 协议错误时是否回退 direct answer。 |
| `fallback_adapter` | `BaseAgentAdapter` | 任务规划失败时的单 Agent fallback。 |
| `fallback_adapter_factory` | callable | 延迟创建 fallback adapter。 |
| `fallback_agent_id` | `str` | fallback 展示用 agent id，默认 `fallback`。 |
| `answer_gateway` | object | direct answer 使用的注入式 gateway。 |
| `answer_model_backend` | `str` | direct answer 使用的 ModelGateway backend；默认回退到 `model_backend`，再回退到 `claude`。 |
| `orchestrator_answer_config` | `dict` | direct answer 模型参数。 |

生产接线：

- `registry.get_adapter("orchestrator")` 对 Orchestrator special-case，不走普通 provider map。
- registry 注入 `adapter_factory`，并默认设置 `managed_agent_ids` 为 `claude-code`、`codex-helper`、`opencode-helper`、`web-designer`。
- `adapter_factory` 禁止 Orchestrator 调度自身，避免递归。
- Orchestrator 顶层 `provider` 为 `builtin`，但 registry 对 `agent_id == "orchestrator"` 的 special-case 优先。

---

## 3. 子任务结构

当前实现中的 `SubTask` 字段如下：

```python
@dataclass(frozen=True, slots=True)
class SubTask:
    task_id: str
    agent_id: str
    title: str
    instruction: str
    depends_on: tuple[str, ...] = ()
    priority: int = 0
    expected_output: str | None = None
    include_history: bool = True
```

字段规则：

- `task_id` 必须唯一。
- `agent_id` 必须是允许调度的子 Agent。
- `title` 用于 `agent_switch.task` 和计划摘要。
- `instruction` 会作为子 Agent 的最新 user message。
- `depends_on` 里的 task id 必须存在；依赖未成功时当前任务跳过。
- `priority` 数字越小越先执行。
- `expected_output` 当前只保留为计划描述，不参与 artifact 判定。
- `include_history=false` 时只把当前 task instruction 发给子 Agent；用于直接多 Agent 路由，避免历史任务污染。

---

## 4. 任务规划入口

详细任务规划、任务分配和 planner 降级规则拆分到 [orchestrator-task-planning.spec.md](orchestrator-task-planning.spec.md)。

主执行流只依赖规划层产出的 `list[SubTask]`。当前解析顺序为：

1. Direct answer 短路。
2. 显式 `config.tasks`。
3. 直接多 Agent mention 路由。
4. LLM planner。
5. Legacy template fallback。

规划失败后可按配置回退到 direct answer、template tasks 或 fallback adapter；都不可用时才发 Orchestrator fatal `error`。

---

## 5. 任务执行流转

### 5.1 总体事件序列

普通任务流：

```text
start
block_start/planning delta/block_end
agent_switch(to_agent=A)
block_start/@A header/block_end
[A child stream remapped]
agent_switch(to_agent=B)
block_start/@B header/block_end
[B child stream remapped]
block_start/execution summary delta/block_end
done
```

direct answer 流：

```text
start
[answer gateway stream remapped]
done
```

fatal error 流：

```text
start
error
```

### 5.2 调度顺序

任务执行严格顺序，不并发：

1. 输出 planning text block，内容为 `Planned N sub-task(s) via <source>:`。
2. 初始化所有 task state 为 `pending`。
3. 按已排序 tasks 逐个执行。
4. 如果 `depends_on` 中任一任务不是 `succeeded`，当前任务标记为 `skipped`，不调用子 Agent。
5. 否则执行 `_run_task()`。
6. 全部任务结束后输出 `Execution summary`。
7. 发出 `done(total_blocks=<全局 block 数>)`。

当前 `TaskState` 只有：

```python
class TaskState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
```

### 5.3 `_run_task()` 子任务流转

每个子任务执行步骤：

1. 发出 `agent_switch(from_agent="orchestrator", to_agent=task.agent_id, task=task.title)`。
2. 输出一个 text header block，内容为 `@<agent_id>\n\n`。
3. 通过 `sub_adapters[agent_id]` 或 `adapter_factory(agent_id)` 获取子 Adapter。
4. 组装子 Agent messages：
   - `include_history=True`：原始 `messages + [task.instruction]`。
   - `include_history=False`：只传 `[task.instruction]`。
5. 调用子 Adapter 的 `stream(..., workspace_path=workspace_path, tool_specs=tool_specs)`。
6. 对子 stream 做事件重映射和过滤。
7. 子 stream 正常结束则任务标记为 `succeeded`。
8. 子 stream 出现 error chunk 或抛异常则任务标记为 `failed`。

### 5.4 子 Stream 事件处理

| 子事件 | Orchestrator 行为 |
|---|---|
| `start` / `done` | 吞掉，不透传。 |
| `block_start` / `delta` / `block_end` | 重映射 `block_index` 后透传。 |
| `tool_call` / `tool_result` | 透传，但 `call_id` 改为 `<task_id>.<原 call_id>`。 |
| `heartbeat` | 原样透传，不写入 message content，不影响 task state。 |
| `error` | 不透传；关闭已打开 block 后输出普通失败 text block。 |
| 其他未知事件 | 忽略。 |

子 Agent 抛异常时，Orchestrator 同样输出普通失败 text block，不让整个 SSE message 变成 `error`。

### 5.5 Fallback Adapter 流转

任务规划失败或 config 校验失败时，如果配置了 `fallback_adapter` 或 `fallback_adapter_factory`：

1. 输出 `Task plan unavailable; falling back to @<fallback_agent_id>.`
2. 发出 `agent_switch(to_agent=<fallback_agent_id>, task="fallback")`。
3. 用原始 `messages` 调用 fallback adapter。
4. 按子 stream 规则重映射 block、tool call 和 heartbeat。
5. fallback adapter error/exception 会转为普通失败 text block。
6. 输出 fallback summary。
7. 发出 `done`。

fallback adapter 只用于规划失败后的单 Agent 降级，不是每个子任务失败后的重试机制。

---

## 6. `agent_switch` 事件语义

`agent_switch` 使用现有 `StreamChunk` schema，不新增字段：

```python
StreamChunk(
    event_type="agent_switch",
    from_agent="orchestrator",
    to_agent=task.agent_id,
    task=task.title,
)
```

规则：

- 在切换到某个子 Agent 之前发出。
- `from_agent` 固定为 `orchestrator`。
- `to_agent` 是目标子 Agent id。
- `task` 是当前子任务标题。
- 不占用 `block_index`。
- fallback 流中 `task="fallback"`。

前端可以用它展示当前正在工作的 Agent，但不得把它当作文本内容写入最终 message content。

---

## 7. `block_index` 和 `call_id` 重映射

### 7.1 Block 重映射

每个子 Agent 都可能从 `block_index=0` 开始输出。Orchestrator 为每个子 stream 维护局部 `index_map`：

```python
index_map: dict[int, int] = {}
next_block_index = current_global_index

if child_chunk.block_index not in index_map:
    index_map[child_chunk.block_index] = next_block_index
    next_block_index += 1

yield child_chunk.model_copy(
    update={"block_index": index_map[child_chunk.block_index]}
)
```

约束：

- 全局 `block_index` 不重复。
- 子 Agent 的原始 block index 不要求连续。
- planning block、agent header block、failure block、summary block 都占用全局 block index。
- 如果子 Agent 在 block 未闭合时失败，Orchestrator 先补一个 `block_end`，再输出失败说明块。

### 7.2 Tool Call 重映射

多个子 Agent 的 `call_id` 也可能冲突。Orchestrator 对 tool events 做前缀：

```text
<task_id>.<child_call_id>
```

fallback 流使用：

```text
fallback.<child_call_id>
```

---

## 8. 失败处理与状态汇总

### 8.1 子任务失败

以下情况视为单个子任务失败：

- 获取子 Adapter 失败。
- 子 Adapter stream 抛异常。
- 子 Adapter yield `event_type="error"`。

处理规则：

- 转成普通 text block：`@<agent_id> failed: <reason>`。
- 当前任务标记为 `failed`。
- 不直接透传子 Agent `error`。
- 继续执行后续依赖已满足的任务。
- 最终 Orchestrator 仍可 `done`。

### 8.2 依赖跳过

如果任务依赖的任何 task state 不是 `succeeded`：

- 当前任务标记为 `skipped`。
- 不发 `agent_switch`。
- 不调用子 Adapter。
- 在 summary 中列出 `skipped`。

### 8.3 Fatal Error

只有 Orchestrator 自身无法继续时才发 `error`：

- 任务计划缺失且没有 fallback。
- 显式 `config.tasks` 格式非法且没有 fallback。
- planner 输出不可用且没有 fallback/direct answer/template 降级。
- 缺少 `sub_adapters` 和 `adapter_factory`。
- direct answer gateway 配置非法。

### 8.4 Summary

当前 summary 是普通 text block：

```text
Execution summary

- succeeded: @claude-code - Produce solution
- failed: @codex-helper - Review and refine
- skipped: @web-designer - Visual polish
```

summary 不新增 event type，也不包含 artifact diff 判定。

---

## 9. Preview / Deploy 边界

Orchestrator 和子 Agent runtime 不得负责启动 preview/deploy/server 进程。

当前规则：

- planner prompt 明确禁止规划启动、部署、预览、管理长驻端口服务。
- planner message 再次提示 port preview/deploy 只能规划文件生成和验证。
- `_remove_port_service_tasks()` 会过滤纯端口服务任务。
- 如果任务同时包含 artifact 生成 marker，允许保留为文件生成任务。
- 真正的 workspace preview/deploy 生命周期属于平台能力，见 [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)。

---

## 10. Artifact 判定边界

当前 Orchestrator 实现只根据子 stream 是否成功结束来判定 `succeeded`。它尚未实现：

- workspace diff 检查。
- expected artifact path 校验。
- `artifact_missing` task state。
- 每个子任务的 fallback agent 重试。
- fallback attempt 失败摘要注入。

这类能力属于 artifact-aware orchestration 后续扩展，应和 workspace artifact / preview 合约一起实现，避免把 runtime 文本成功误判为产物成功。

---

## 11. 验收标准

当前 Orchestrator spec 的最小验收：

- direct answer 问答不启动子 Agent runtime。
- 显式 `config.tasks` 优先级最高，按 `priority` 执行。
- 显式提到两个或更多 managed agents 时生成 direct tasks，且 `include_history=False`。
- LLM planner 只允许使用白名单 agent id。
- planner 不规划 preview/deploy/server 长驻端口任务。
- planner 失败按 direct answer、template、fallback adapter、fatal error 的配置顺序降级。
- 子任务严格顺序执行，不并发。
- 依赖失败时后续依赖任务标记 `skipped`。
- 子 Agent `start/done` 被吞掉。
- 子 Agent `error` 被转换为普通失败 text block。
- 子 Agent `heartbeat` 透传，且不进入最终 message content。
- 子 Agent `tool_call/tool_result.call_id` 加 task 前缀。
- 所有内容 block 的 `block_index` 全局唯一。
- 部分子任务失败时 Orchestrator 输出 summary 并 `done`。
- Orchestrator 自身 fatal error 才输出 `error`。

---

## 12. 相关文件

| 文件 | 说明 |
|---|---|
| [orchestrator.py](../../../backend/app/agents/orchestrator.py) | Orchestrator 主实现。 |
| [orchestrator_planner.py](../../../backend/app/agents/orchestrator_planner.py) | LLM planner helper。 |
| [registry.py](../../../backend/app/agents/registry.py) | Orchestrator production special-case 和 `adapter_factory` 注入。 |
| [base.py](../../../backend/app/agents/base.py) | `BaseAgentAdapter.stream()` 契约。 |
| [types.py](../../../backend/app/agents/types.py) | `StreamChunk`, `ChatMessage`, `ToolSpec`。 |
| [orchestrator-task-planning.spec.md](orchestrator-task-planning.spec.md) | Orchestrator 任务规划和分配规则。 |
| [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md) | Adapter 总体事件契约。 |
| [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md) | external runtime timeout、heartbeat、cancel 规则。 |
| [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) | workspace artifact 与 preview/deploy 平台边界。 |
