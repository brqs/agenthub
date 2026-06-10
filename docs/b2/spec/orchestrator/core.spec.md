# Orchestrator Spec

> 定义 AgentHub 多 Agent 编排器的当前行为契约，包括任务规划、任务分配、子任务流转、事件聚合和失败处理。
>
> 版本：v1.6
> 最后更新：2026-06-07

---

## 1. 目标

`OrchestratorAdapter` 是 AgentHub 群聊和复杂任务编排入口。它不直接完成文件生成、代码实现或工具调用，而是根据用户请求生成子任务，并把子任务派发给真实的子 Agent。

Orchestrator 负责：

1. 判断请求是否只是普通问答；若是，走 direct answer，不启动子 Agent runtime。
2. 解析或生成结构化任务计划。
3. 按优先级和依赖顺序调度子 Agent；默认启用 DAG 并行执行。
4. 把多个子 Agent 的 `StreamChunk` 合并为单个 SSE 流。
5. 对 `block_index` 和 `tool_call.call_id` 做全局重映射，避免前端渲染冲突。
6. 将子 Agent 失败转换为普通文本失败块，继续执行可独立任务。
7. 收集子任务结果，并把依赖任务结果注入后续子任务上下文。
8. 对 `expected_output` 中明确提到的 workspace artifact 做只读存在性校验。
9. 默认对 artifact 执行通用 Evaluation / Reflection MVP，并在失败时复用 per-task fallback 修复再验证。
10. 对每个 task attempt 记录 workspace snapshot / file changes，并在同一 run 内检测冲突。
11. 对前端 preview/deploy 意图调用平台 preview / browser verify tool，执行质量门和最多 2 轮修复。
12. 支持通过正式平台 tool `create_custom_agent` 在聊天中创建自建 Agent 并加入当前群聊。
13. 输出最终 execution summary，并以 `done` 结束非 fatal 的部分失败流程。
14. 在配置开启时，将真实编排 run、task、attempt、event 写入 Orchestrator structured memory，并在后续回合注入最近结构化记忆。

Orchestrator 不负责：

- 直接访问数据库。
- 直接 import 或调用具体 provider SDK。
- 由 Agent runtime 启动 preview/deploy/server 等长驻端口服务。
- 自行管理 preview/deploy 进程；这些动作必须通过平台 tool/service 执行。
- 直接写数据库；结构化 memory 由 stream/service 层通过 writer protocol 注入完成。
- 自动 merge 多 Agent 文件冲突；v1.4 只记录和展示冲突。

能力分层：

- DAG 并行属于 Orchestrator 静态任务执行器能力，不是 platform tool。
- `dispatch_agent` 是 tool calling 模式下的单个子 Agent 调度工具；当前默认主链仍是 LLM planning + 静态 DAG executor。
- Workspace conflict detection 的详细规则拆分到 [workspace-conflict.spec.md](workspace-conflict.spec.md)。

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
| `available_agents_authoritative` | `bool` | 为 `true` 时，`available_agents` 是 planner / fallback / execution 的强边界；显式 `false` 允许内部静态任务使用 `managed_agent_ids` / `task_fallback_agent_ids`。 |
| `conversation_scoped_agents` | `bool` | 为 `true` 时，当前群聊成员 scope 是调度边界；生产群聊默认开启。 |
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
| `task_fallback_agent_ids` | `list[str]` | 子任务失败、artifact 缺失或 evaluation 失败时可尝试的 fallback Agent 列表；默认空。 |
| `sub_agent_config_overrides` | `dict[str, dict]` | 执行子 Agent attempt 时叠加的 per-agent runtime config；用于 E2E/内部静态任务，不改变 Agent 表中的持久配置。 |
| `max_task_attempts` | `int` | 单个子任务最大 attempt 数；默认 `1`，建议范围 `1..3`。 |
| `context_max_tokens` | `int` | 通用 agent 会话上下文 token 预算；默认 `64000`，范围 `1..200000`。 |
| `orchestrator_context_max_tokens` | `int` | Orchestrator 主流程上下文 token 预算；默认 `64000`，范围 `1..200000`。 |
| `orchestrator_subagent_context_max_tokens` | `int` | Orchestrator 分发给子 Agent 的最终消息 token 预算；默认 `64000`，范围 `1..200000`。 |
| `planner_context_max_tokens` | `int` | Orchestrator LLM Planner 专用输入上下文 token 预算；默认 `128000`，范围 `1..1000000`。 |
| `task_result_context_max_chars` | `int` | 注入后续子任务的前序结果总字符预算；默认 `24000`。 |
| `task_result_item_max_chars` | `int` | 单个任务结果摘要字符预算；默认 `6000`。 |
| `orchestrator_memory_writer` | protocol object | stream/service 层注入的结构化记忆 writer；Orchestrator 不直接访问 DB。 |
| `orchestrator_memory_enabled` | `bool` | 是否启用结构化 run memory；默认 `true`。 |
| `orchestrator_memory_recent_runs` | `int` | 后续回合注入最近 terminal run 数；默认 `3`，范围 `1..10`。 |
| `orchestrator_memory_context_max_chars` | `int` | 结构化 memory system message 字符预算；默认 `24000`，范围 `1..32000`。 |
| `orchestrator_parallel_enabled` | `bool` | 是否启用静态 DAG 并行执行；默认 `true`。 |
| `orchestrator_parallel_max_concurrency` | `int` | 静态 DAG 最大并发任务数；默认 `3`，范围 `1..16`。 |
| `orchestrator_evaluation_enabled` | `bool` | 是否启用 artifact Evaluation / Reflection MVP；默认 `true`。 |
| `orchestrator_evaluation_read_max_bytes` | `int` | 单个 artifact 只读评估字节上限；默认 `262144`，范围 `1..1048576`。 |
| `orchestrator_evaluation_judge` | callable | 可选注入式 requirements coverage judge；生产默认不接 LLM judge。 |
| `orchestrator_test_runner_enabled` | `bool` | 是否启用受控 test runner evaluator；默认 `false`。 |
| `orchestrator_test_command_allowlist` | `list[str]` | 允许执行的测试 evaluator alias；MVP 支持 `python_compile_artifacts`。 |
| `orchestrator_quality_gate_enabled` | `bool` | 是否对网页 preview/deploy 请求执行平台 preview + browser verify 质量门。 |
| `orchestrator_quality_max_repair_rounds` | `int` | 质量门失败后最多自动修复轮数；默认 `2`。 |
| `orchestrator_platform_tool_executor` | protocol object | stream/service 层注入的平台 tool executor，支持 preview、browser verify、自建 Agent 等平台能力。 |

默认模型上下文预算说明：即使底层 DeepSeek backend 支持更大上下文（例如 1M），
AgentHub 默认仍使用 `64000` tokens 作为产品级安全预算，用于控制延迟、成本和跨
provider 兼容性；需要更大上下文时通过上述 `context_*_max_tokens` 字段显式配置。

生产接线：

- `registry.get_adapter("orchestrator")` 对 Orchestrator special-case，不走普通 provider map。
- registry 注入 `adapter_factory`，并默认设置 `managed_agent_ids` 为 `claude-code`、`codex-helper`、`opencode-helper`。
- 当前内置 Agent 白名单只包含 `orchestrator`、`claude-code`、`codex-helper`、`opencode-helper`。旧内置 `writer`、`web-designer`、`deepseek-assistant`、`browser-validator` 等 seed 残留会在启动/seed 清理中移除；用户自建 Agent 不受 `is_builtin=True` 清理影响。
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
- `expected_output` 可用于提取 workspace artifact path 候选；只做存在性校验，不评审内容质量。
- `include_history=false` 时只把当前 task instruction 发给子 Agent；用于直接多 Agent 路由，避免历史任务污染。

---

## 3.1 运行上下文与结构化记忆

v1.2 引入 Orchestrator 内部运行上下文。v1.3 在不改变 `BaseAgentAdapter` / `StreamChunk` / SSE 契约的前提下，新增 Orchestrator structured memory：运行期仍用 `OrchestratorRunContext` 聚合结果，stream/service 层通过 `orchestrator_memory_writer` 把真实流转写入数据库。

建议内部结构：

```python
@dataclass(slots=True)
class TaskAttempt:
    attempt_index: int
    agent_id: str
    state: TaskState
    text_preview: str = ""
    tool_summaries: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    file_changes: dict[str, list[str]] = field(default_factory=dict)
    conflict_paths: list[str] = field(default_factory=list)
    error: str | None = None

@dataclass(slots=True)
class TaskResult:
    task_id: str
    title: str
    final_state: TaskState
    attempts: list[TaskAttempt] = field(default_factory=list)
    workspace_conflicts: list[dict[str, Any]] = field(default_factory=list)

@dataclass(slots=True)
class OrchestratorRunContext:
    results: dict[str, TaskResult] = field(default_factory=dict)
    memory_run_id: UUID | None = None
```

用途：

- 在子 stream 消费过程中累积文本、工具调用摘要、错误原因和 artifact path 候选。
- 在 task attempt 前后记录 workspace snapshot，计算 created / modified / deleted。
- 同一 run 内多个 task 修改同一文件时记录 conflict。
- 每个子任务完成后写入 `results[task_id]`。
- 后续任务根据 `depends_on` 和执行顺序读取前序结果，生成上下文注入。
- 最终 summary 基于 `TaskResult` 输出，而不是只输出简单状态列表；summary 还必须展示 workspace conflict。

结构化 memory 表：

| 表 | 说明 |
|---|---|
| `orchestrator_runs` | 一次 Orchestrator 编排 run，包含 conversation、触发消息、状态、用户请求、plan source 和 final summary。 |
| `orchestrator_tasks` | run 内的 task graph，包含 task id、agent、依赖、priority、expected output 和最终状态。 |
| `orchestrator_task_attempts` | 每个 task 的每次 attempt，包含实际 agent、状态、text preview、tool 摘要、artifact、missing artifact 和 error。 |
| `orchestrator_run_events` | planned、task_started、task_result、workspace_snapshot、workspace_file_changes、workspace_conflict_detected、react_decision、finished/cancelled 等时间线事件。 |

实现入口：

- Model：`backend/app/models/orchestrator_memory.py`
- Migration：`backend/alembic/versions/9a1b2c3d4e5f_add_orchestrator_memory.py`
- Service：`backend/app/services/orchestrator_memory.py`

下一轮 Orchestrator 请求前，stream 层会读取最近 terminal runs，并在最新 user request 之前插入 system message：

```text
Previous Orchestrator structured memory:
```

该 structured memory 不替代 `ConversationMemory` 文本压缩；它只记录 Orchestrator 编排状态。

---

## 4. 任务规划入口

详细任务规划、任务分配和 planner 降级规则拆分到 [task-planning.spec.md](task-planning.spec.md)。

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

并行 DAG 模式下，多个 ready tasks 可以同时执行；SSE 仍按可读顺序 flush 子流事件，前端无需新增 event type。

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

默认调度为 DAG 并行执行；显式关闭 `orchestrator_parallel_enabled=false` 时回到旧的串行执行。

1. 输出 planning text block，内容为 `Planned N sub-task(s) via <source>:`。
2. 初始化所有 task state 为 `pending`。
3. 如果启用并行 DAG，每一轮选择所有依赖已满足的 pending tasks。
4. ready tasks 按 priority、task id 排序，最多并发 `orchestrator_parallel_max_concurrency` 个。
5. 如果 `depends_on` 中任一任务是 terminal failure，当前任务标记为 `skipped`，不调用子 Agent。
6. 否则执行 `_run_task()`。
7. 每个 attempt 前后记录 workspace snapshot 与 file changes。
8. 全部任务结束后检测并汇总同一 run 内 file conflict。
9. 全部任务结束后输出 `Execution summary`。
10. 发出 `done(total_blocks=<全局 block 数>)`。

并行模式下仍保持：

- `_run_task()` 是唯一子任务执行入口。
- DAG executor 不通过 `dispatch_agent` tool 实现；它直接调度内部 `SubTask`，以保证默认群聊任务稳定、可测、可控制并发。
- 子任务失败不会让整个 Orchestrator SSE 直接变成 fatal error。
- 依赖 task 只读取已成功依赖的结果。
- memory writer 调用由 stream 层注入 lock 串行化，避免同一个 AsyncSession 并发写入。

当前 `TaskState`：

```python
class TaskState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ARTIFACT_MISSING = "artifact_missing"
    EVALUATION_FAILED = "evaluation_failed"
```

### 5.3 `_run_task()` 子任务流转

每个子任务执行步骤：

1. 发出 `agent_switch(from_agent="orchestrator", to_agent=task.agent_id, task=task.title)`。
2. 输出一个 text header block，内容为 `@<agent_id>\n\n`。
3. 通过 `sub_adapters[agent_id]` 或 `adapter_factory(agent_id)` 获取子 Adapter。
4. 组装子 Agent messages：
   - `include_history=True`：原始 `messages + [前序结果 system context] + [task.instruction]`。
   - `include_history=False`：只传 `[前序结果 system context] + [task.instruction]`。
   - 如果没有可注入的前序结果，则不添加 system context。
5. 调用子 Adapter 的 `stream(..., workspace_path=workspace_path, tool_specs=tool_specs)`。
6. 对子 stream 做事件重映射和过滤，同时累积 `TaskAttempt`。
7. attempt 前后记录 workspace snapshot，计算 file changes。
8. 子 stream 正常结束后，如果存在明确 artifact path 候选，则只读校验文件是否存在。
9. 子 stream 正常结束且 artifact 存在或无需校验时，进入 Evaluation / Reflection MVP。
10. 子 stream 出现 error chunk 或抛异常则任务标记为 `failed`。
11. 子 stream 正常结束但 expected artifact 缺失时，任务标记为 `artifact_missing`。
12. Evaluation 失败时，attempt 标记为 `evaluation_failed`，并生成 reflection repair instruction。
13. 如果配置开启 per-task fallback，失败、artifact 缺失或 evaluation 失败任务可进入下一次 attempt。
14. 子 Agent stream config 会叠加 `sub_agent_config_overrides[agent_id]`，但该 override 只影响本次 attempt，不写回 Agent 持久配置。

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

### 5.5 依赖结果上下文注入

Orchestrator 应把已完成子任务的结果作为后续子任务上下文的一部分。

注入规则：

- 注入内容使用 `role="system"` 的 `ChatMessage`，标题固定为 `Previous sub-agent results`。
- 如果当前任务声明了 `depends_on`，优先注入这些依赖任务的结果。
- 如果当前任务没有 `depends_on`，注入按执行顺序已经完成的前序任务结果。
- 只注入简短摘要：task id、agent id、状态、文本 preview、tool 摘要、artifact path、错误原因。
- 默认总预算 `task_result_context_max_chars=24000`。
- 默认单个任务预算 `task_result_item_max_chars=6000`。
- 子 Agent 消息组装后会按 `orchestrator_subagent_context_max_tokens=64000`
  做最终 token 裁剪；裁剪时保留当前 task instruction、最新用户请求、
  MemoryHub / critical facts、前序任务结果和 workspace inventory，优先丢弃旧普通历史。
- LLM Planner 可使用独立的 `planner_context_max_tokens=128000`
  构造更大的规划输入；该预算不放大 Orchestrator direct answer、tool loop
  或子 Agent runtime 的默认输入。
- `include_history=false` 只表示不带原 conversation history；不禁止带依赖任务结果。

注入文本示例：

```text
Previous sub-agent results:

- task-a @claude-code succeeded
  Text: Created snake.html and updated styles.
  Artifacts: snake.html

- task-b @codex-helper failed
  Error: runtime_idle_timeout
```

### 5.6 Fallback Adapter 流转

任务规划失败或 config 校验失败时，如果配置了 `fallback_adapter` 或 `fallback_adapter_factory`：

1. 输出 `Task plan unavailable; falling back to @<fallback_agent_id>.`
2. 发出 `agent_switch(to_agent=<fallback_agent_id>, task="fallback")`。
3. 用原始 `messages` 调用 fallback adapter。
4. 按子 stream 规则重映射 block、tool call 和 heartbeat。
5. fallback adapter error/exception 会转为普通失败 text block。
6. 输出 fallback summary。
7. 发出 `done`。

fallback adapter 只用于规划失败后的单 Agent 降级，不是每个子任务失败后的重试机制。

### 5.7 Per-task Fallback 流转

per-task fallback 是 v1.2 的子任务级重试机制，和规划失败 fallback adapter 分开。

配置：

| 字段 | 默认 | 说明 |
|---|---:|---|
| `task_fallback_agent_ids` | `["claude-code", "opencode-helper", "codex-helper"]` | 可用于子任务 fallback 的 Agent id 列表；运行时会按当前会话可用性、cooldown 和显式配置过滤。 |
| `max_task_attempts` | `3` | 单任务最大 attempt 数；限制 `1..3`。 |

规则：

- 配置 `task_fallback_agent_ids=[]` 或 `max_task_attempts=1` 时不重试。
- `failed`、`artifact_missing` 或 `evaluation_failed` 会触发 fallback。
- fallback agent 不能与本 attempt 使用的 agent 相同。
- 每次 attempt 前必须过滤当前会话不可运行 Agent、全局 cooldown Agent、本次 run 内已硬失败 Agent，以及不在 group scope 内的 Agent。
- 如果首选 Agent 已由 `available_agents` 声明为不可运行，Orchestrator 不创建该 Agent child message，也不先输出失败气泡；process / memory 只记录“检测到不可用并改派”。
- 任意 Agent 出现 auth/quota/credential/CLI missing/provider runtime unavailable/明确 runtime timeout 等硬失败后，Orchestrator 会将该 Agent 写入本次 run-local unavailable，并可放入短期 cooldown；本次 run 的后续 task、后续并行 batch 和 fallback selection 会跳过 run-local unavailable Agent，全局 cooldown 则可影响后续 planner / fallback selection。
- `artifact_missing`、普通文件 `not found`、业务验证失败、构建/test 失败不等同 runtime hard failure；这些状态只触发当前 task fallback / repair，不让 Agent 进入 runtime cooldown。
- 首选 Agent 会先尝试，除非执行前已知不可运行；失败后从当前会话可用 Agent、配置 fallback Agent、managed/default Agent 中选择能力范围内的替代者。显式 Orchestrator-routed mention 也会先尝试被点名 Agent，失败后透明 fallback。
- 生产群聊默认使用 conversation-scoped boundary：`available_agents_authoritative=true` 且 `conversation_scoped_agents=true`。内部 E2E 或静态任务可显式设置 `available_agents_authoritative=false`，让 `task_fallback_agent_ids` / `managed_agent_ids` 参与 fallback selection。
- fallback attempt 使用同一 `task.instruction`，并额外注入上一次失败原因。
- fallback attempt 的 tool call id 前缀使用 `<task_id>.attempt-<n>.<child_call_id>`。
- 所有 attempts 失败后，任务最终状态为最后一次失败状态。
- summary 必须列出每次 attempt 的 agent、状态和原因。
- 真实群聊中，失败 child message 与 `message_error.error` 必须走用户可见错误清洗，不暴露 `Permission denied`、`[Errno`、`.claude.json`、`/root/.agenthub`、raw stderr、stack trace 或 `call_`。

Task card 展示语义：

- task card 初始 task 必须记录 `planned_agent_id=<原计划 agent>`。
- fallback 发生后，task card 的展示 agent 使用最终/当前执行 agent，而不是原计划 agent。
- `agent_id` 表示当前 UI 应展示的执行 Agent；fallback 成功后等于最终 attempt agent。
- `current_agent_id` 可在 streaming 中表示正在执行的 attempt agent。
- `final_agent_id` 在 task terminal 后记录最终 attempt agent。
- 如果 `planned_agent_id != final_agent_id`，前端可展示类似 `@final <- @planned` 的重分配关系，避免用户误以为原 Agent 完成了任务。

Command fulfillment 语义：

- Orchestrator run-local context 会保存从用户原始请求 deterministic 提取的显式要求：文档、代码产物、多智能体分工、审阅、预览、浏览器验收、部署、Diff、源码打包等。
- 这些要求通过 `command_fulfillment_status` memory/run detail event 持续记录，payload 包含 `stage` 与 `items`；不新增数据库 migration，也不新增 ContentBlock 类型。
- task graph 完成不等于用户命令全部完成。最终用户可见 summary 必须读取 fulfillment 状态；存在 `pending`、`failed` 或 `skipped` item 时，只能说明已完成可完成部分，并列出需要注意的未满足项。
- 平台动作 item 由正式 tool result 满足：`start_workspace_preview` 满足 preview，`verify_web_preview` passed 满足 browser verification，`create_deployment` published/running 满足 deployment。
- Preview / deployment / browser verify 的完整规则见 [command-fulfillment.spec.md](command-fulfillment.spec.md) 与 [tool-calling.spec.md](tool-calling.spec.md)。

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

### 8.3 Artifact Missing

如果任务正常结束，但 `expected_output` 或任务文本中提到的 workspace-relative artifact path 不存在：

- 当前 attempt 标记为 `artifact_missing`。
- 如果开启 per-task fallback，进入下一次 attempt。
- 如果没有 fallback attempt，任务最终状态为 `artifact_missing`。
- 最终 Orchestrator 仍可 `done`，并在 summary 中说明缺失路径。

artifact 判定只允许只读检查 workspace 内路径：

- 接受相对路径，如 `snake.html`、`src/App.tsx`、`dist/index.html`。
- 拒绝绝对路径、包含 `..` 的路径、`.env` / `secrets/` / `.ssh/` 等敏感路径。
- 不做 glob 全盘扫描。
- 不执行 shell 命令。
- 不读取文件内容，只检查存在性和普通文件/目录状态。

### 8.4 Fatal Error

只有 Orchestrator 自身无法继续时才发 `error`：

- 任务计划缺失且没有 fallback。
- 显式 `config.tasks` 格式非法且没有 fallback。
- planner 输出不可用且没有 fallback/direct answer/template 降级。
- 缺少 `sub_adapters` 和 `adapter_factory`。
- direct answer gateway 配置非法。

### 8.5 Summary

summary 是普通 text block。v1.2 应包含 task、attempt、agent、状态、artifact 和错误摘要：

```text
Execution summary

- succeeded: @claude-code - Produce solution
  artifacts: snake.html
- artifact_missing: @codex-helper - Verify artifact
  missing: snake.html
- failed: @opencode-helper - Review and refine
  attempts:
  - attempt 1 @opencode-helper: runtime_idle_timeout
```

summary 不新增 event type，不包含 artifact diff 判定，不评审文件内容质量。

v1.4 summary 还必须包含 workspace conflict 摘要：

```text
Workspace conflicts

- shared-conflict.md
  tasks: conflict-design, conflict-implementation
  agents: claude-code, opencode-helper
```

---

## 9. Preview / Deploy 边界

Orchestrator 和子 Agent runtime 不得自行启动 preview/deploy/server 进程。

当前规则：

- planner prompt 明确禁止规划启动、部署、预览、管理长驻端口服务。
- planner message 再次提示 port preview/deploy 只能规划文件生成和验证。
- `_remove_port_service_tasks()` 会过滤纯端口服务任务。
- 如果任务同时包含 artifact 生成 marker，允许保留为文件生成任务。
- 真正的 workspace preview/deploy 生命周期属于平台能力，见 [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)。
- Orchestrator 可以正式调用平台 tool `start_workspace_preview`，但实际 PID、端口、URL 均由平台 service 管理。
- Orchestrator 可以正式调用平台 tool `verify_web_preview`，由平台 Playwright verifier 做浏览器级质量验收。
- 如果用户指定 `8082`，平台 preview 必须使用 requested port；端口不可用时返回失败，不静默 fallback。

---

## 10. Artifact 判定与 Evaluation 边界

Orchestrator v1.2 的 artifact-aware 能力只做最小存在性校验：

- 优先从 `expected_output` 中提取明确 path 候选。
- 如果 `expected_output` 已给出路径，以它作为 artifact contract，不把子 Agent 文本里的随口文件名当硬性产物。
- 如果没有 `expected_output` path，再从任务 instruction、子 Agent 文本和 tool arguments 中提取明确 path 候选。
- 只检查 workspace root 内的相对路径是否存在。
- 会把 `workspace/foo.md`、`/workspace/foo.md`、`/workspaces/{id}/foo.md` 归一化为 workspace-relative path。
- artifact existence 仍只做 workspace 内只读路径检查。
- 平台 preview/deploy 生命周期仍属于 [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)。

Orchestrator v1.5+ Evaluation / Reflection MVP：

- 默认启用 `orchestrator_evaluation_enabled=true`。
- `artifact_exists` 包装现有存在性检查；缺失仍标记为 `artifact_missing`。
- `document_quality` 只读取 `.md` / `.txt`，检查空文件、placeholder-only 和明显未完成内容。
- `code_static_quality` 只解析 `.py`、`.json`、`.toml`；其他代码类型先跳过，不阻断。
- `workflow_validation` 校验 JSON/YAML workflow 的 `version/name/nodes/edges`、节点唯一性和 edge 悬空引用。
- `ppt_validation` 校验 `ppt_outline.json` / `ppt.md` 的标题、slides 和每页内容；`.pptx` 二进制深度解析暂不阻断。
- `test_report_quality` 仅在 `orchestrator_test_runner_enabled=true` 且 allowlist 包含 `python_compile_artifacts` 时执行受控 Python compile runner。
- `browser_preview_quality` 包装现有网页 preview/browser quality gate，继续保持 `start_workspace_preview` / `verify_web_preview` SSE tool event 兼容。
- `deployment_health` 记录部署 tool 结果健康状态；失败会生成 structured issue / reflection，并复用 repair agent 修复 workspace 后重新调用同一个 deployment tool；`not_supported` 仅记录平台限制，不触发修复。
- `requirements_coverage` 只有注入 `orchestrator_evaluation_judge` 时执行；生产默认 skipped。
- 读取 artifact 遵守 `orchestrator_evaluation_read_max_bytes`，并跳过 `.agenthub`、`.env`、`.ssh`、`secrets` 等敏感路径。
- evaluation 失败会生成结构化 reflection，并把 repair instruction 注入下一次 fallback attempt 的上下文。
- 不新增 DB migration；`evaluation_started`、`evaluation_result`、`reflection_created`、`evaluation_finished` 写入现有 memory event payload。
- `run_quality_gate()` 保留为兼容包装，语义上属于 `browser_preview_quality` evaluator 路径。

---

## 11. 验收标准

当前 Orchestrator spec 的最小验收：

- direct answer 问答不启动子 Agent runtime。
- 显式 `config.tasks` 优先级最高，按 `priority` 执行。
- 显式提到两个或更多 managed agents 时生成 direct tasks，且 `include_history=False`。
- LLM planner 只允许使用白名单 agent id。
- planner 不规划 preview/deploy/server 长驻端口任务。
- planner 失败按 direct answer、template、fallback adapter、fatal error 的配置顺序降级。
- 默认启用 DAG 并行；互不依赖的 ready tasks 可以并发执行。
- 关闭 `orchestrator_parallel_enabled` 后，子任务回到旧串行执行。
- 依赖失败时后续依赖任务标记 `skipped`。
- 前序任务结果会注入依赖任务上下文。
- `include_history=false` 不带原始历史，但仍可带依赖任务结果。
- 明确 expected artifact 缺失时任务标记 `artifact_missing`。
- artifact evaluation 失败时任务标记 `evaluation_failed`，summary 展示 evaluator、issue 和 repair hint。
- 开启 per-task fallback 后，`evaluation_failed` 可改派 fallback agent 修复并再验证。
- 网页 preview/browser 请求会产生 `browser_preview_quality` evaluation event；部署请求会产生 `deployment_health` evaluation event，部署失败可进入 reflection/repair/redeploy 闭环。
- 同一 run 内多个 task 修改同一文件时，summary 和 memory event 记录 workspace conflict。
- preview/deploy 请求必须通过平台 `start_workspace_preview` / `verify_web_preview` tool，不由 Agent runtime 启动服务。
- 聊天中创建自建 Agent 时可以调用 `create_custom_agent` tool。
- 开启 per-task fallback 后，失败、`artifact_missing` 或 `evaluation_failed` 可改派 fallback agent。
- 子 Agent `start/done` 被吞掉。
- 子 Agent `error` 被转换为普通失败 text block。
- 子 Agent `heartbeat` 透传，且不进入最终 message content。
- 子 Agent `tool_call/tool_result.call_id` 加 task 前缀。
- 所有内容 block 的 `block_index` 全局唯一。
- 部分子任务失败时 Orchestrator 输出 summary 并 `done`。
- summary 包含每个 task 的 attempts、最终 agent、artifact path 和失败原因摘要。
- Orchestrator 自身 fatal error 才输出 `error`。

---

## 12. 相关文件

| 文件 | 说明 |
|---|---|
| [adapter.py](../../../../backend/app/agents/orchestrator/adapter.py) | Orchestrator 主入口。 |
| [execution.py](../../../../backend/app/agents/orchestrator/execution.py) | 静态任务执行、DAG 并行、attempt 状态机。 |
| [evaluation.py](../../../../backend/app/agents/orchestrator/evaluation.py) | Artifact Evaluation / Reflection MVP。 |
| [task_planning.py](../../../../backend/app/agents/orchestrator/task_planning.py) | direct answer、direct mention、planner fallback 和任务解析。 |
| [planner.py](../../../../backend/app/agents/orchestrator/planner.py) | LLM planner helper。 |
| [tools.py](../../../../backend/app/agents/orchestrator/tools.py) | Orchestrator tool specs。 |
| [tool_loop.py](../../../../backend/app/agents/orchestrator/tool_loop.py) | Orchestrator tool loop。 |
| [workspace_changes.py](../../../../backend/app/agents/orchestrator/workspace_changes.py) | Workspace snapshot / diff / conflict detection。 |
| [orchestrator_platform_tools.py](../../../../backend/app/services/orchestrator_platform_tools.py) | 平台 tool executor：preview、browser verify、自建 Agent。 |
| [registry.py](../../../../backend/app/agents/registry.py) | Orchestrator production special-case 和 `adapter_factory` 注入。 |
| [base.py](../../../../backend/app/agents/base.py) | `BaseAgentAdapter.stream()` 契约。 |
| [types.py](../../../../backend/app/agents/types.py) | `StreamChunk`, `ChatMessage`, `ToolSpec`。 |
| [task-planning.spec.md](task-planning.spec.md) | Orchestrator 任务规划和分配规则。 |
| [agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md) | Adapter 总体事件契约。 |
| [external-runtime-lifecycle.spec.md](../external-runtime-lifecycle.spec.md) | external runtime timeout、heartbeat、cancel 规则。 |
| [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md) | workspace artifact 与 preview/deploy 平台边界。 |
## 2026-06-07 User Interrupt Addendum

Current Orchestrator behavior includes a first-class user interrupt terminal state.

- When the parent agent message receives `POST /api/v1/messages/{msg_id}/interrupt`, the stream layer calls `interrupt_active_run()` instead of the older cancellation/error path.
- `orchestrator_runs.status` and open task attempts can become `interrupted`.
- Open child agent messages are finalized with `message_interrupted` and persisted as `interrupted`.
- User interrupt must not run replanner, repair, per-task fallback, or final success summary.
- User interrupt is neutral UI state, not a failed task retry state.
- Group-scoped dispatch remains authoritative: in group conversations, `available_agents` / `managed_agent_ids` are derived from runnable current conversation members. An unavailable or non-member agent must not be pulled back in by global defaults during planning, fallback, or recovery.

## 2026-06-07 Queued Next Turn Addendum

Queued next turns are owned by B1/F message lifecycle, not by Orchestrator planning:

- While an Orchestrator run is active, new user text can be persisted as a `queued` user message, but it must not be injected into the active run, planner, replanner, repair loop, or child agent context.
- Orchestrator still sees exactly one user turn per run.
- When the active parent message reaches `done`, `error`, or `interrupted`, B1 may dispatch the queue head and create a new pending Orchestrator agent message.
- The new pending message is a normal fresh Orchestrator turn and should rebuild context from persisted conversation history.
- Queue dispatch must preserve group-scoped scheduling rules. A queued message with an invalid or removed target agent should become a visible platform error turn, not a silent fallback to a global agent.
- Phase 1 does not implement "guide current thinking"; that future feature will require a separate runtime-control contract.

## 2026-06-07 Conversation Control Plane Addendum

The runtime-control contract now exists for Orchestrator safe-point guidance and side chat:

- Guidance is explicit and separate from queued next turns. Default running-time submit still queues the next turn.
- B1 creates `conversation_turn_controls` rows and streams `turn_control` events; Orchestrator only consumes pending `guidance` controls at safe points.
- Safe points include direct-answer before generation, planner before/after, task dispatch before, tool-loop entry, quality-gate/replanner/repair boundaries, and child-task switch boundaries where available.
- Applied guidance is injected as a scoped system/context instruction for the remaining active Orchestrator turn, then recorded as `orchestrator_run_event=guidance_applied`.
- Unapplied guidance expires when the active parent message reaches `done`, `error`, or `interrupted`.
- External CLI/SDK child runtimes do not receive live prompt injection in this phase. If the active message is not an Orchestrator safe-point runtime, guidance must return `409 GUIDANCE_NOT_SUPPORTED`.
- Side-chat messages answer status questions from active stream/run/task/queue/workspace summaries and must not create `task_card`, `agent_switch`, or runtime attempts.
- Context building excludes `turn_control.kind=side_chat` messages from future main-task context so status questions do not become hidden task requirements.
- Queue actions remain platform-level controls. They may reorder/merge/convert queued messages or interrupt-then-dispatch, but they must not bypass group-scoped dispatch or same-conversation serial execution.
