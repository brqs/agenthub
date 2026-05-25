# Orchestrator Spec

> 定义 AgentHub 多 Agent 编排器（Orchestrator）的行为契约、事件流规则、任务拆解格式和失败降级策略。
> 本 Spec 为 B2-09（顺序调度与 block_index 重映射）和 B2-10（失败降级与部分成功输出）提供实现边界。
>
> 版本：v1.0
> 最后更新：2026-05-25

---

## 1. 目标

OrchestratorAdapter（以下简称 Orchestrator）是 AgentHub 群聊模式的核心协调者。当用户在 group chat 中 `@Orchestrator` 发起请求时，Orchestrator 负责：

1. **任务拆解**：分析用户意图，将复杂请求拆分为多个可并行/顺序执行的子任务。
2. **子 Agent 调度**：按依赖关系顺序调用子 Agent，每个子 Agent 通过 registry 抽象获取 Adapter。
3. **流式聚合**：将多个子 Agent 的流式输出合并为统一的 `StreamChunk` 序列回传客户端。
4. **失败降级**：单个子 Agent 失败不中断主流程，最终输出包含执行摘要和部分失败说明。

**本 Spec 不实现生产代码**，只定义 B2-09/B2-10 必须遵守的契约、数据结构和验收标准。

---

## 2. 输入 / 输出

### 2.1 输入

Orchestrator 的 `stream()` 签名与 `BaseAgentAdapter` 完全一致（不得修改）：

```python
async def stream(
    self,
    messages: list[ChatMessage],
    system_prompt: str | None = None,
    config: dict[str, Any] | None = None,
) -> AsyncIterator[StreamChunk]
```

额外注入参数（由外层 Service 层传入，**Orchestrator 不直接访问数据库**）：

| 参数 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `available_agents` | `list[AgentInfo]` | Service 层查询 `agents` 表后注入 | 当前群聊中可用的子 Agent 列表 |
| `orchestrator_llm_config` | `dict[str, Any]` | `config` 或 `self.default_config` | Orchestrator 自身拆解任务时使用的 LLM 参数（model, temperature, max_tokens） |

```python
class AgentInfo(BaseModel):
    agent_id: str
    name: str
    provider: str
    capabilities: list[str]  # e.g. ["code", "frontend", "review"]
    system_prompt: str | None
```

### 2.2 输出

Orchestrator 的输出必须是标准 `StreamChunk` 序列，**不新增字段、不修改 StreamChunk schema**。

正常事件序列（按时间顺序）：

```
start
  └─ block_start(block_index=0, block_type="text")
  └─ delta(block_index=0, text_delta="📋 拆解为 N 个子任务...")
  └─ block_end(block_index=0)
  └─ agent_switch(to_agent="<agent_id>", task="<task_title>")
  └─ block_start(block_index=1, block_type="text")
  └─ delta(block_index=1, text_delta="💬 **@<agent_id>**\n\n")
  └─ block_end(block_index=1)
  └─ [子 Agent 输出的 block_start/delta/block_end，block_index 已重映射]
  └─ [下一个 agent_switch...]
  └─ ...
  └─ block_start(block_index=M, block_type="text")
  └─ delta(block_index=M, text_delta="📋 执行摘要...")
  └─ block_end(block_index=M)
done
```

异常事件序列（某个子 Agent 失败）：

```
...（正常前缀）...
  └─ agent_switch(to_agent="<agent_id>", task="<task_title>")
  └─ block_start(block_index=K, block_type="text")
  └─ delta(block_index=K, text_delta="⚠️ @<agent_id> 执行失败：...")
  └─ block_end(block_index=K)
  └─ [继续下一个 agent_switch 和子 Agent...]
  └─ ...
  └─ block_start(block_index=M, block_type="text")
  └─ delta(block_index=M, text_delta="📋 部分任务失败摘要...")
  └─ block_end(block_index=M)
done
```

**约束**：
- 只允许使用现有 `event_type`：`start`, `block_start`, `delta`, `block_end`, `agent_switch`, `done`, `error`。
- `error` 仅在 Orchestrator 自身严重异常时发出（如所有子 Agent 均不可用、任务拆解失败）。单个子 Agent 失败用文本块描述，不走 `error` 事件。

---

## 3. Orchestrator 在 Group Chat 中的职责

### 3.1 职责边界

| 职责 | Orchestrator 做 | Orchestrator 不做 |
|------|----------------|------------------|
| 任务拆解 | 分析用户请求，输出结构化子任务列表 | 不持久化消息到 DB |
| 子 Agent 选择 | 根据 `available_agents` 匹配最合适的 agent_id | 不直接查询 `agents` 表 |
| 流式调度 | 顺序 yield 子 Agent 的 StreamChunk | 不做并发调度（B2-09 明确顺序） |
| block_index 重映射 | 确保多个子 Agent 的 block 索引全局连续 | 不修改子 Agent 输出的 delta 内容 |
| 失败降级 | 捕获子 Agent 异常，yield 说明文本块，继续后续任务 | 不重试失败子 Agent（B2-11 处理重试） |
| 最终摘要 | 输出执行结果摘要（成功/失败/跳过） | 不替子 Agent 生成内容 |

### 3.2 群聊触发方式

用户在 group chat 输入框中 `@Orchestrator 做一个 Todo App`，前端解析 mention 后：

1. `MessageService` 创建 pending agent message（`agent_id="orchestrator"`）。
2. `StreamRouter` 通过 `registry.get_adapter("orchestrator")` 拿到 `OrchestratorAdapter`。
3. `StreamRouter` 将当前群聊的 `available_agents`（除 Orchestrator 自身外）通过 `config` 注入：
   ```python
   adapter.stream(
       history,
       config={
           "available_agents": [...],
           "orchestrator_llm_config": {"model": "claude-sonnet-4-6", ...},
       }
   )
   ```
4. Orchestrator 内部先调 LLM 拆解任务，再顺序调度子 Agent。

> **BaseAgentAdapter 签名约束**：`stream()` 只接受 `messages`, `system_prompt`, `config`。**不得新增关键字参数**。所有 Orchestrator 专属参数（`available_agents`, `tasks`, `sub_adapters` 等）统一通过 `config` dict 注入。

### 3.3 Registry 接入的已知 Gap（B2-09 之前必须解决）

当前 `backend/app/seeds/seed_agents.py` 中 orchestrator 的 `provider` 为 `"custom"`：

```python
{
    "id": "orchestrator",
    "provider": "custom",
    ...
}
```

而 `backend/app/agents/registry.py` 的 `PROVIDER_MAP` 把 `"custom"` 映射到 `CustomAdapter`，不是 `OrchestratorAdapter`。

**这意味着当前生产链路无法调用到 `OrchestratorAdapter`**。该 gap 必须在 Orchestrator 进入真实群聊联调前解决，但**不阻塞 B2-09 的注入式单元测试实现**。推荐拆分为独立 B1/B2 协同任务（如 B2-09a），方案（二选一）：

**方案 A（推荐）**：新增 `provider="orchestrator"`
- 在 `registry.py` 的 `PROVIDER_MAP` 中新增 `"orchestrator": OrchestratorAdapter`。
- 同步修改 `seed_agents.py` 中 orchestrator 的 `provider` 为 `"orchestrator"`。
- 优点：语义清晰，registry 路由自然。

**方案 B**：`registry.get_adapter()` special-case
- 在 `get_adapter()` 中检测 `agent_id == "orchestrator"`，直接返回 `OrchestratorAdapter`。
- 不改 seed。
- 缺点：hard-code agent_id，不利于后续多 Orchestrator。

**约束**：本 Spec 阶段不改 registry/seed 代码，只记录 gap。B2-09 的注入式实现和单元测试不依赖该 gap 修复；registry/seed 生产接线由后续 B1/B2 协同任务完成。

---

## 4. 任务拆解格式（TaskDecomposition）

### 4.1 内部结构化表示

Orchestrator 通过 LLM function calling / tool use 拆解任务，输出必须能稳定解析为以下结构：

```python
class SubTask(BaseModel):
    task_id: str           # 唯一标识，建议格式 "task-{n}"
    agent_id: str          # 目标子 Agent 的 ID，必须存在于 available_agents
    title: str             # 简短标题（1-10 字），用于展示和 agent_switch
    instruction: str       # 完整任务指令，作为子 Agent 的用户消息
    depends_on: list[str]  # 依赖的 task_id 列表；空列表表示无依赖
    priority: int          # 优先级，数字越小越优先（默认 0）
    expected_output: str   # 期望输出形式描述，用于最终验收
```

### 4.2 拆解 Prompt 设计原则

1. **可用 Agent 白名单**：Prompt 中必须只包含 `available_agents` 里列出的 agent，防止 Orchestrator 幻觉出不存在的 Agent。
2. **能力匹配**：每个子任务的 `agent_id` 应匹配 Agent 的 `capabilities`。
3. **依赖最小化**：默认子任务之间无依赖（`depends_on=[]`），只有明确需要前后顺序时才声明依赖。
4. **指令自包含**：`instruction` 必须包含完成该任务所需的全部上下文，不依赖子 Agent 读取群聊历史。
5. **输出严格 JSON**：LLM 必须输出可解析的 JSON array，错误时 Orchestrator yield 文本说明并 fallback 到单 Agent 模式。

### 4.3 示例拆解

用户输入：`@Orchestrator 做一个 Todo App，前端用 React，后端用 FastAPI`

```json
{
  "tasks": [
    {
      "task_id": "task-1",
      "agent_id": "claude-code",
      "title": "后端 API 设计",
      "instruction": "设计并实现一个 FastAPI Todo 后端，包含 CRUD 接口、Pydantic schema、SQLAlchemy 模型。输出完整代码。",
      "depends_on": [],
      "priority": 0,
      "expected_output": "可运行的 FastAPI 代码片段"
    },
    {
      "task_id": "task-2",
      "agent_id": "codex-frontend",
      "title": "前端 React 实现",
      "instruction": "基于以下后端 API 设计，实现 React + TypeScript 前端 Todo 应用。后端 API 为：GET /todos, POST /todos, PATCH /todos/{id}, DELETE /todos/{id}。输出完整组件代码。",
      "depends_on": ["task-1"],
      "priority": 1,
      "expected_output": "可运行的 React 组件代码"
    }
  ]
}
```

---

## 5. 子 Agent 调度顺序

### 5.1 调度策略（B2-09 实现）

B2-09 **只实现顺序调度**，不做并发：

1. 对拆解出的 `tasks` 按 `priority` 升序排序。
2. 遍历排序后的任务列表，对每个任务：
   - 检查 `depends_on` 中所有任务是否已成功完成；若有未完成的依赖，跳过该任务并在摘要中标记 "skipped (unmet dependency)".
   - 发出 `agent_switch` 事件。
   - 调用子 Agent 的 `stream()`。
   - 将子 Agent 输出的所有 StreamChunk 的 `block_index` 重映射后 yield。
3. 所有任务处理完毕后，输出 final summary text block 和 `done`.

### 5.2 与子 Agent 的交互（两阶段）

#### 阶段 1：B2-09 注入式调度（当前）

B2-09 不做 registry DB 接线，子 Agent Adapter 由外层通过 `config` 注入：

```python
# config 注入形态示例
config = {
    "tasks": [...],
    "sub_adapters": {
        "claude-code": fake_adapter_a,
        "codex-frontend": fake_adapter_b,
    },
}

# Orchestrator 内部直接使用注入的 adapter
sub_adapter = config["sub_adapters"][task.agent_id]
```

**约束**：
- B2-09 通过注入的 `sub_adapters` / `adapter_factory` 获取子 Agent Adapter，**不调用 `registry.get_adapter()`**。
- **不得直接 `import` 具体 Provider SDK**。
- 子 Agent 的 `messages` 由 Orchestrator 组装：原始 `messages` + `[ChatMessage(role="user", content=task.instruction)]`。
- 子 Agent 的 `system_prompt` 使用子 Agent 自身的 `system_prompt`（由注入配置提供），Orchestrator 不覆盖。

#### 阶段 2：生产接线（后续协同任务）

当 §3.3 的 registry/seed gap 修复后， Orchestrator 可切换为通过 `registry.get_adapter(task.agent_id, db=db)` 获取真实 Adapter。该接线改动应单独作为一个 B1/B2 协同任务，不在 B2-09 范围内。

---

## 6. `agent_switch` 事件语义

### 6.1 事件定义

`agent_switch` 是现有 `StreamChunk` 已支持的 `event_type`（见 `backend/app/agents/types.py`）。

```python
StreamChunk(
    event_type="agent_switch",
    from_agent="orchestrator",      # 固定为 "orchestrator"
    to_agent=task.agent_id,          # 即将调用的子 Agent ID
    task=task.title,                 # 当前子任务标题
    block_index=None,                # agent_switch 不关联具体 block
)
```

### 6.2 语义规则

1. **触发时机**：在切换到某个子 Agent **之前**发出，客户端可据此更新 UI（如显示 "@claude-code 正在工作中..."）。
2. **from_agent**：固定为 `"orchestrator"`，表示由 Orchestrator 发起的切换。
3. **to_agent**：目标子 Agent 的 `agent_id`。
4. **task**：当前子任务的 `title`，用于客户端展示。
5. **无 block_index**：`agent_switch` 本身不是内容块，不占用 `block_index`。
6. **客户端处理**：前端收到 `agent_switch` 时，可在消息气泡旁展示 Agent 头像和状态指示器，提升群聊临场感。

### 6.3 事件序列示例

```
agent_switch(from_agent="orchestrator", to_agent="claude-code", task="后端 API 设计")
block_start(block_index=1, block_type="text")
delta(block_index=1, text_delta="💬 **@claude-code**\n\n")
block_end(block_index=1)
block_start(block_index=2, block_type="code")
delta(block_index=2, code_delta="from fastapi import FastAPI...")
block_end(block_index=2)
agent_switch(from_agent="orchestrator", to_agent="codex-frontend", task="前端 React 实现")
block_start(block_index=3, block_type="text")
...
```

---

## 7. `block_index` 重映射规则

### 7.1 问题背景

每个子 Agent 内部独立维护自己的 `block_index`（从 0 开始）。若直接透传，多个子 Agent 的 block 索引会冲突，导致前端渲染混乱。

### 7.2 重映射算法

Orchestrator 维护一个全局偏移量 `global_block_offset`：

```python
global_block_offset = 0

# 1. Task planning block
yield block_start(block_index=0, block_type="text")
# ... deltas ...
yield block_end(block_index=0)
global_block_offset = 1

for task in tasks:
    yield agent_switch(...)
    
    # 2. Agent header block（固定一个 text block 标识当前 Agent）
    header_index = global_block_offset
    yield block_start(block_index=header_index, block_type="text")
    yield delta(block_index=header_index, text_delta=f"💬 **@{task.agent_id}**\n\n")
    yield block_end(block_index=header_index)
    global_block_offset += 1
    
    # 3. 子 Agent 输出重映射
    sub_start_offset = global_block_offset
    async for chunk in sub_adapter.stream(sub_messages):
        if chunk.event_type in ("start", "done"):
            continue  # 子 Agent 的内部生命周期事件不外发
        if chunk.event_type == "error":
            # 子 Agent 的 error 必须在 Orchestrator 内部拦截，
            # 转换为普通 text 失败说明块。不能直接外发 error chunk，
            # 否则 B1 SSE 层会把整个 message 标为 error 并终止。
            yield StreamChunk(
                event_type="block_start",
                block_index=sub_start_offset,
                block_type="text",
            )
            yield StreamChunk(
                event_type="delta",
                block_index=sub_start_offset,
                text_delta=f"⚠️ @{task.agent_id} 执行失败：{chunk.error or 'unknown error'}\n",
            )
            yield StreamChunk(
                event_type="block_end",
                block_index=sub_start_offset,
            )
            global_block_offset = sub_start_offset + 1
            break
        if chunk.block_index is not None:
            chunk = chunk.model_copy(update={
                "block_index": chunk.block_index + sub_start_offset
            })
        yield chunk
        # 更新偏移量，为下一个子 Agent 预留空间
        if chunk.event_type == "block_end" and chunk.block_index is not None:
            global_block_offset = chunk.block_index + 1
    else:
        # 子 Agent 正常结束，global_block_offset 已在 block_end 时更新
        pass
```

### 7.3 关键约束

1. **单调递增**：重映射后的 `block_index` 在整个 Orchestrator 流中严格单调递增，无重复、无回退。
2. **跳过子 Agent 生命周期事件**：子 Agent 的 `start` 和 `done` 被吞掉，不对外发送； Orchestrator 自己控制整体生命周期。
3. **子 Agent error 必须内部拦截**：子 Agent 发出的 `error` chunk 不得在 Orchestrator 流中直接透传，必须在 Orchestrator 内部转换为普通 `text` block（失败说明），否则 B1 SSE 层会把整个 message 标为 `error` 并终止。只有 Orchestrator 自身 fatal error 才 yield `error`。
4. **预留空间**：每个子 Agent 之间不硬性预留固定数值，而是按实际输出 block 数动态推进偏移量。

---

## 8. 子 Agent 失败降级策略

### 8.1 失败定义

单个子 Agent 失败包含以下情形：

1. **Adapter 异常**：`sub_adapter.stream()` 抛出未捕获异常（网络、API Key 缺失、rate limit 等）。
2. **Error Chunk**：子 Agent 内部 yield 了 `event_type="error"` 的 chunk。
3. **任务拆解失败**：Orchestrator 调 LLM 拆解任务时返回非 JSON 或格式非法。

### 8.2 降级规则（B2-10 实现）

| 失败场景 | 行为 | 输出 |
|----------|------|------|
| 单个子 Agent Adapter 异常 | 捕获异常，yield 失败说明 text block，标记该任务为 `failed`，继续后续任务 | `⚠️ @<agent_id> 执行失败：<error>` |
| 单个子 Agent yield error chunk | **拦截**该 error chunk，转换为 text 失败说明块外发，标记任务为 `failed`，继续后续任务 | `⚠️ @<agent_id> 执行失败：<error>` |
| 任务拆解失败（LLM 返回非法 JSON） | fallback 到单 Agent 模式：直接把所有可用 agents 信息 + 用户原始请求发给默认 Agent（如 Claude），yield 其完整输出 | 无子任务规划，直接输出 |
| 所有子 Agent 均失败 | yield 最终 summary 说明全部失败，然后 yield `done` | `所有子任务均失败...` |

### 8.3 任务状态追踪

Orchestrator 内部维护一个 `task_states` 字典，记录每个子任务的执行状态：

```python
task_states: dict[str, TaskState] = {}

class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"  # 依赖未满足
```

### 8.4 Final Summary 格式

所有子任务执行完毕后，Orchestrator 输出一个 final summary text block：

```
📋 执行摘要

✅ @claude-code — 后端 API 设计 — 已完成
❌ @codex-frontend — 前端 React 实现 — 失败（rate_limit）
⏭️ @reviewer — 代码审阅 — 已跳过（依赖 task-2 未完成）

部分任务失败，请稍后重试或调整请求。
```

**约束**：
- Summary 只作为文本块输出，不新增 `summary` event_type。
- B2-10 的验收标准中必须包含"单个子 Agent 失败时，最终 message status 仍为 `done`（而非 `error`）"的测试。

---

## 9. 不修改基类与契约的约束

### 9.1 明确不修改项

| 项目 | 当前状态 | 约束 |
|------|----------|------|
| `BaseAgentAdapter.stream()` 签名 | 已稳定 | **不得修改**参数列表和返回类型 |
| `StreamChunk` schema | 已包含 `agent_switch` / `from_agent` / `to_agent` / `task` | **不得新增字段**；现有字段足够表达 Orchestrator 语义 |
| `ContentBlock` 联合类型 | text / code / diff / web_preview / file | **不得新增 block 类型** |
| `shared/openapi.yaml` | 由 B1/F 维护 | Orchestrator 阶段不改 |
| `backend/app/schemas/message.py` | 由共享契约维护 | Orchestrator 阶段不改 |

### 9.2 允许依赖的现有能力

- `StreamChunk.event_type="agent_switch"` 已存在（`types.py`）。
- `StreamChunk.from_agent` / `to_agent` / `task` 已存在（`types.py`）。
- `registry.get_adapter(agent_id, db)` 已存在（`registry.py`）。
- `ChatMessage` / `StreamChunk` Pydantic model 的 `model_copy()` 已可用。

---

## 10. B2-09 / B2-10 验收标准

### 10.1 B2-09 验收标准（顺序调度与 block_index 重映射）

B2-09 的任务范围：`backend/app/agents/orchestrator.py` 的实现 + 单元测试。

**B2-09 只做注入式顺序调度和 block_index 重映射，不负责真实 LLM 任务拆解和 registry DB 接线。** 任务计划（`tasks`）和子 Agent Adapter（`sub_adapters` 或 `adapter_factory`）统一通过 `config` 注入。

- [ ] Orchestrator 从 `config` 中读取注入的任务计划（`tasks`）和子 Agent 映射（`sub_adapters` / `adapter_factory`）。
- [ ] 任务列表包含 `task_id`, `agent_id`, `title`, `instruction`, `depends_on`, `priority`。
- [ ] 按 `priority` 顺序遍历任务列表。
- [ ] 每个任务调用前发出 `agent_switch` 事件，包含正确的 `to_agent` 和 `task`。
- [ ] 每个子 Agent 通过注入的 `sub_adapters` / `adapter_factory` 获取，**不直接调用 `registry.get_adapter()`**，不直接 import 具体 Provider SDK。
- [ ] 子 Agent 的 `block_index` 被正确重映射，全局单调递增无冲突。
- [ ] 子 Agent 的 `start`/`done` 事件被吞掉，不外发。
- [ ] 子 Agent 的 `error` chunk 被内部拦截并转换为 text 失败说明块，**不直接外发 error chunk**。
- [ ] 输出序列以 Orchestrator 自己的 `start` 开头、`done` 结尾。
- [ ] 包含 task planning text block 和 final summary text block。
- [ ] 单元测试覆盖：单任务、多任务顺序、block_index 重映射、agent_switch 事件、error chunk 拦截。

**不在 B2-09 范围内（后续任务）**：
- 真实 LLM function calling / tool use 任务拆解。
- `registry.get_adapter()` 生产接线（需 §3.3 的 gap 先解决）。
- 子 Agent 失败后继续执行后续任务的完整降级策略（B2-10）。
- 并发调度。

### 10.2 B2-10 验收标准（失败降级与部分成功输出）

B2-10 的任务范围：在 B2-09 基础上增强 Orchestrator 的异常处理。

- [ ] 单个子 Agent `stream()` 抛异常时，Orchestrator 捕获并 yield 失败说明文本块，继续后续任务。
- [ ] 单个子 Agent yield `error` chunk 时，Orchestrator **拦截并转换为 text 失败说明块**，继续后续任务。
- [ ] 任务拆解 LLM 返回非法 JSON 时，fallback 到单 Agent 模式。
- [ ] 最终 summary text block 正确列出每个子任务的 `SUCCEEDED` / `FAILED` / `SKIPPED` 状态。
- [ ] 即使部分子任务失败，最终也 yield `done`（而非 `error`）。
- [ ] 依赖未满足的任务被标记为 `SKIPPED`，不在该任务上调用子 Agent。
- [ ] 单元测试覆盖：Adapter 异常、error chunk、非法 JSON fallback、全部失败、依赖跳过。

---

## 11. 接口设计草稿（供 B2-09 实现参考）

以下代码为**示意性草稿**，B2-09 实现时可调整内部细节，但外部行为必须符合本 Spec。

```python
# backend/app/agents/orchestrator.py
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import BaseAgentAdapter
from app.agents.types import ChatMessage, StreamChunk


class OrchestratorAdapter(BaseAgentAdapter):
    """Master agent that coordinates multiple sub-agents in group chat."""

    provider = "orchestrator"  # 需配合 §3.3 方案 A 同步更新 registry.py / seed_agents.py

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # ... B2-09 实现 ...
        pass
```

### 11.1 内部方法建议（非强制）

```python
async def _decompose_tasks(
    self,
    messages: list[ChatMessage],
    available_agents: list[AgentInfo],
    llm_config: dict[str, Any],
) -> list[SubTask]:
    """调用 LLM 拆解任务。B2-09 实现。"""

async def _run_subtask(
    self,
    task: SubTask,
    messages: list[ChatMessage],
    global_offset: int,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    """调度单个子 Agent，yield 重映射后的 chunk 和更新后的 offset。B2-09 实现。"""

async def _yield_summary(
    self,
    task_states: dict[str, TaskState],
    global_offset: int,
) -> AsyncIterator[tuple[StreamChunk, int]]:
    """输出 final summary。B2-10 实现。"""
```

---

## 12. 附录：相关文件索引

| 文件 | 说明 |
|------|------|
| `backend/app/agents/orchestrator.py` | Orchestrator 实现位置（B2-09/B2-10） |
| `backend/app/agents/base.py` | BaseAgentAdapter 契约 |
| `backend/app/agents/types.py` | StreamChunk / ChatMessage 定义 |
| `backend/app/agents/registry.py` | Adapter 注册表 |
| `backend/app/agents/adapters/claude.py` | Orchestrator 底层可委托的拆解 LLM |
| `docs/spec/orchestrator.spec.md` | 本 Spec |
| `docs/b2-task-dispatch/B2-08-orchestrator-spec.md` | B2-08 任务文档 |
| `docs/b2-task-dispatch/B2-09-orchestrator-dispatch.md` | B2-09 任务文档（待创建） |
| `docs/b2-task-dispatch/B2-10-orchestrator-fallback.md` | B2-10 任务文档（待创建） |
