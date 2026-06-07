# Orchestrator Memory & Context Management Spec

> 定义 AgentHub 当前上下文/记忆体系、真实 external agent 的消息管理方式，以及 Orchestrator 结构化长期记忆的目标设计。
>
> 状态：Current contract
> 最后更新：2026-06-04

---

## 1. 背景与现状

AgentHub 当前已经有多层上下文，但它们解决的问题不同。

### 1.1 会话级 ContextBuilder

`ContextBuilder` 是所有 agent 进入 `BaseAgentAdapter.stream()` 前的统一会话上下文来源：

```text
messages table
-> conversation memory refresh
-> compressed summary
-> critical facts
-> pinned messages
-> recent raw messages
-> list[ChatMessage]
```

当前特征：

- 读取 `status in ("done", "streaming")` 的消息。
- 将 `Message.content` block flatten 成文本。
- 长历史进入 `ConversationMemory.summary_text`。
- pin 消息优先保留，超预算时压缩。
- 最近消息按 token budget 逆序选取。
- `tool_call` block 会被 flatten，保留工具名、状态、call id、path 和 output preview。

限制：

- 它是文本摘要，不是结构化项目状态。
- 它不知道 Orchestrator 的 task graph、attempt、artifact 是否验证过。
- 历史压缩后，下一轮 Orchestrator 只能从自然语言里推断“上次发生了什么”。

### 1.2 群聊成员上下文

stream 层在目标 agent 是 `orchestrator` 且 conversation 是 group 时，会注入：

- `conversation_agents`
- `available_agents`
- overridden `managed_agent_ids`

这些数据来自 `Conversation.agent_ids` 和对应 `Agent` 行，是 Orchestrator 回答“当前群聊有哪些 agent / 模型 / 能力”和 planner 调度边界的事实源。

### 1.3 External Agent 上下文管理

`claude-code`、`codex-helper`、`opencode-helper` 是真实 runtime agent，但它们不直接读取数据库，也没有自己的 AgentHub 长期记忆表。

它们的上下文来源是：

1. stream 层传入的 `messages`。
2. `workspace_guard_prompt(workspace_path)` 注入的 workspace 规则。
3. `format_runtime_messages()` 对历史消息的重排：
   - 旧消息放入 `Previous conversation context (not the active task)`。
   - 最新用户消息放入 `Current user request (answer this now)`。
4. direct identity shortcut：
   - 身份问题直接回答，不启动 SDK/CLI。
5. external direct chat routing：
   - 普通问答走 `ModelGateway` direct chat。
   - 任务型请求才启动真实 SDK/CLI runtime。

所以 external agents 的“记忆”实际是 AgentHub 提供的消息上下文；真实 CLI/SDK runtime 只负责本轮执行，不拥有 AgentHub 后端结构化状态。

### 1.4 BuiltinAgent 上下文管理

BuiltinAgent 有自己的 model/tool loop：

```text
model stream
-> collect tool_call
-> execute native/MCP tool
-> append tool results to current_messages
-> next loop iteration
```

它的工具结果上下文只在本轮 loop 内追加，不形成跨轮结构化任务记忆。

### 1.5 Orchestrator 当前上下文管理

Orchestrator 已有单轮运行上下文：

- `OrchestratorRunContext`
- `TaskResult`
- `TaskAttempt`

它会在单次 stream 内记录：

- task state
- attempt agent
- text preview
- tool summaries
- artifact paths
- missing artifact paths
- error reason

后续子任务会收到 `Previous sub-agent results` system message。ReAct replanner 也会基于最近 observation 动态 `add_task/update_task/skip_task/finish`。

当前缺口：

- `OrchestratorRunContext` 只存在于当前 Python 调用栈。
- SSE 结束后，结构化 task graph 和 attempts 不会持久化。
- 下一轮继续任务时，只能依赖普通聊天历史和压缩摘要。
- artifact 没有长期索引，不知道哪个 agent 创建、哪个任务验证、最后失败原因是什么。

---

## 2. 目标

新增 Orchestrator 专属结构化记忆层，让 Orchestrator 在后续回合能读取真实编排状态，而不是从聊天文本中猜测。

目标：

1. 持久化每次 Orchestrator run 的 task graph、attempts、artifact、error、ReAct decisions 和 final summary。
2. 下一轮 Orchestrator 请求自动注入最近结构化 run 摘要。
3. 保留现有 `ConversationMemory` 文本压缩机制，不替换它。
4. 保持 `BaseAgentAdapter`、`StreamChunk`、SSE wire contract 不变。
5. Orchestrator adapter 继续不直接访问数据库。
6. 先提供 dev/debug API，前端正式 UI 不在本轮范围。

非目标：

- 不为所有 agent 建统一长期 memory。
- 不让 Orchestrator 直接执行 tool/bash。
- 不新增 SSE event type。
- 不对 artifact 内容做质量评审。
- 不改变 external direct chat / runtime routing。

---

## 3. 数据模型

新增四张表。

### 3.1 `orchestrator_runs`

记录一次 Orchestrator 对用户消息的编排。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | run id |
| `conversation_id` | UUID FK | 所属 conversation |
| `agent_message_id` | UUID FK nullable | 本次 Orchestrator assistant message |
| `user_message_id` | UUID FK nullable | 触发 run 的 user message |
| `status` | string | `running` / `done` / `error` / `cancelled` |
| `user_request` | text | 最新用户请求快照 |
| `plan_source` | string | `llm` / `direct_routing` / `legacy_template` / `config` |
| `final_summary` | text | 最终 execution summary |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |
| `completed_at` | datetime nullable | 完成时间 |

索引：

- `(conversation_id, created_at)`
- `(agent_message_id)`

### 3.2 `orchestrator_tasks`

记录 run 内任务图。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | row id |
| `run_id` | UUID FK | 所属 run |
| `task_id` | string | Orchestrator 内部 task id |
| `agent_id` | string | 目标 agent |
| `title` | text | 任务标题 |
| `instruction` | text | 子任务指令快照 |
| `depends_on` | JSONB list[str] | 依赖 task id |
| `priority` | int | 排序 |
| `expected_output` | text nullable | 期望产物 |
| `include_history` | bool | 是否带原始 conversation history |
| `final_state` | string | `pending` / `succeeded` / `failed` / `skipped` / `artifact_missing` |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

约束：

- `(run_id, task_id)` 唯一。

### 3.3 `orchestrator_task_attempts`

记录每次任务尝试。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | row id |
| `run_id` | UUID FK | 所属 run |
| `task_row_id` | UUID FK | 对应 `orchestrator_tasks.id` |
| `task_id` | string | 冗余 task id，方便查询 |
| `attempt_index` | int | 第几次 attempt |
| `agent_id` | string | 实际执行 agent |
| `state` | string | attempt state |
| `text_preview` | text | 子 agent 文本摘要 |
| `tool_summaries` | JSONB list[str] | 工具调用摘要 |
| `artifact_paths` | JSONB list[str] | 发现的 artifact path |
| `missing_artifact_paths` | JSONB list[str] | 缺失 artifact path |
| `error` | text nullable | 错误原因 |
| `created_at` | datetime | 创建时间 |
| `completed_at` | datetime nullable | 完成时间 |

约束：

- `(task_row_id, attempt_index)` 唯一。

### 3.4 `orchestrator_run_events`

记录时间线，便于调试 ReAct 和真实流转。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | event id |
| `run_id` | UUID FK | 所属 run |
| `event_type` | string | `planned` / `task_started` / `task_result` / `react_decision` / `finished` / `error` |
| `task_id` | string nullable | 关联 task |
| `agent_id` | string nullable | 关联 agent |
| `payload` | JSONB | 结构化事件内容 |
| `created_at` | datetime | 创建时间 |

---

## 4. 后端接入设计

### 4.1 Memory writer 注入

新增 `OrchestratorMemoryWriter` protocol，Orchestrator 只依赖 protocol，不 import DB model。

建议方法：

```python
class OrchestratorMemoryWriter(Protocol):
    async def start_run(
        self,
        *,
        conversation_id: UUID,
        agent_message_id: UUID,
        user_message_id: UUID | None,
        user_request: str,
        plan_source: str,
        tasks: list[SubTask],
    ) -> UUID: ...

    async def record_task_result(
        self,
        *,
        run_id: UUID,
        task: SubTask,
        result: TaskResult,
    ) -> None: ...

    async def record_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None: ...

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        final_summary: str,
    ) -> None: ...
```

生产实现放在 service 层，例如 `OrchestratorMemoryStore`。stream 层创建 store 并通过 `config` 注入：

```python
stream_config["orchestrator_memory_writer"] = store
stream_config["conversation_id"] = message.conversation_id
stream_config["agent_message_id"] = message.id
stream_config["user_message_id"] = message.reply_to_id
```

规则：

- writer 不存在时，Orchestrator 行为完全不变。
- writer 异常只记录日志，不中断 SSE。
- fatal Orchestrator error 前如果 run 已创建，应标记 `error`。
- request disconnected 时 stream 层可将 run 标记 `cancelled`。

### 4.2 Orchestrator 写入点

写入点必须对应真实流转：

1. `_resolve_tasks()` 成功后创建 run，并记录 `planned` event。
2. 每个 `_run_task()` 开始前记录 `task_started` event。
3. 每个 task 完成后记录 task row 和 attempts。
4. ReAct decision 解析并应用后记录 `react_decision` event。
5. summary 文本生成后 `finish_run(status="done")`。
6. planner/config fatal error 且未进入任务执行时不创建 run，或创建后标记 `error`，二者需在实现中保持一致；推荐“只有 tasks 已解析成功才创建 run”。

### 4.3 历史结构化上下文注入

新增 Orchestrator memory context builder。stream 层仅在目标 agent 是 `orchestrator` 时调用。

默认策略：

- `orchestrator_memory_enabled=true`。
- structured memory 查询最近 `3` 个 terminal runs。
- Agent capability profile 查询当前 conversation 最近 `20` 个 terminal runs，最大 `100`；不跨用户、不跨 workspace。
- 总预算 `6000` chars，capability profile 和 structured memory 共用该预算。
- structured memory 按时间从旧到新注入，便于模型理解延续。
- 有历史 terminal run 且能聚合出画像时，system message 先包含：

```text
Agent capability profile from recent Orchestrator runs:
```

- 随后包含 structured memory 标题：

```text
Previous Orchestrator structured memory:
```

注入内容示例：

```text
Agent capability profile from recent Orchestrator runs:
- @codex-helper: runs_considered=4; task_count=5; success_count=4; failure_count=1; artifact_missing_count=0; evaluation_failed_count=1; avg_attempts=1.2; repair_success_count=1; confidence=medium
  artifact_kinds: document=3, code=2
  review_outcomes: needs_repair=1
  recent_failure_reasons: document_quality: Replace placeholders with complete content.

Previous Orchestrator structured memory:

Run 2026-05-30 23:10 done
Request: 创建一个极简 HTML dashboard 并检查按钮行为
Summary: 2 succeeded, 1 artifact_missing
- artifact_missing @codex-helper Create dashboard
  Missing: react-dynamic-dashboard.html
  Error: missing artifact: react-dynamic-dashboard.html
- succeeded @opencode-helper Recover by creating dashboard
  Artifacts: react-dynamic-dashboard.html
  Text: Created react-dynamic-dashboard.html.
- succeeded @opencode-helper Verify dashboard artifact
  Text: VERIFIED_OK
```

#### 4.3.1 Agent Capability Profile v1 统计语义

Capability Profile v1 以“实际参与逻辑任务的 Agent”为统计对象：

- `task_count`：同一 Agent 在同一逻辑任务中无论重试多少次只计一次；全部 attempt 为 `skipped/pending` 时不进入画像。
- `avg_attempts`：该 Agent 的实际 attempt row 数除以其参与任务数。
- `success_count` / `failure_count`：由该 Agent 在该任务中的最后一次 attempt 判定；`succeeded` 计成功，`failed/artifact_missing/evaluation_failed` 计失败，`skipped/pending` 不计成功或失败。
- 同一 Agent 首次失败、重试后成功时，最终计一次成功、不计最终失败；此前的 `artifact_missing/evaluation_failed` 仍作为失败事件累计。
- 原 Agent 失败、fallback Agent 成功时，原 Agent 计失败，fallback Agent 计成功。
- repair task 经 fallback 成功时，`repair_success_count` 归属实际成功的 Agent。
- `artifact_kinds` 按 `(agent_id, task_row_id, artifact_kind)` 去重；attempt row、task result event、evaluation checked artifacts 不得重复累计同一任务同一 Agent 的同类产物。
- 对缺少 attempt row 的旧 task，使用 task row 的 `agent_id/final_state/task_type` 兼容降级；`avg_attempts=0`。

Profile 仍只查询当前 `conversation_id` 的 terminal runs；API ownership check 保证不跨用户，conversation/workspace 一一关联保证不跨 workspace。

Planner 使用规则：

- stream context 仍把完整 capability profile + structured memory 注入 Orchestrator 消息历史。
- planner 只从当前 conversation 的 system memory message 中提取 `Agent capability profile from recent Orchestrator runs` 段，不接收后续的 `Previous Orchestrator structured memory` 详情。
- 没有 capability profile 时不增加 planner profile section，不影响现有规划流程。
- capability profile 是 planner 的结构化软选择依据；不新增硬编码评分器，同时仍严格限制在 available/managed agent ids 内。
- 当画像对匹配 task/artifact kind 呈现清晰强弱差异时，planner 应直接选择近期成功 Agent，不应先探测弱 Agent 再依赖 fallback。

注入位置：

```text
ContextBuilder summary / critical facts / pinned
-> Agent capability profile from recent Orchestrator runs
-> Previous Orchestrator structured memory
-> recent messages
```

如果实现上不方便插入中间位置，可以先在 `build_context()` 返回后、调用 adapter 前插入到第一个 latest user message 之前；不得放在最新 user request 之后。

#### 4.3.2 Agent Capability Profile v1 公网 E2E

2026-06-04 公网后端 API/SSE 验收已通过：

```text
scenario: p1_agent_capability_profile
report: /tmp/agenthub_p1_agent_capability_profile_report.json
sse: /tmp/agenthub_p1_agent_capability_profile_sse.jsonl
conversation_id: 8dd905aa-e51a-4f68-b869-2cc4c6278a3d
passed: true
```

种子 run 的真实 attempt 统计：

```text
claude-code: task_count=1, success_count=0, failure_count=1, evaluation_failed_count=1
opencode-helper: task_count=1, success_count=1, failure_count=0, evaluation_failed_count=0
```

follow-up 用户请求没有点名执行 Agent；planner 看到 profile 后，最新 run detail 中唯一 task Agent 和全部实际 attempt Agent 均为 `opencode-helper`，并成功创建 `capability-followup.md`。该证据同时验证 memory context 出现 capability profile、选择依据可见、profile API 返回至少两个 Agent。

#### 4.3.3 Agent Capability Profile v2 / User Preference Memory

B2-TODO-08 v2 MVP 已实现为实时只读聚合，不新增表或 migration。

统计语义：

- v2 输入为当前 `user_id` 拥有的多个 conversation 的 terminal Orchestrator runs；可传 `conversation_id` 作为当前 conversation 加权 boost，但不把查询限制为单 conversation。
- v2 继承 v1 的实际参与 Agent 归属语义：fallback success 归属实际成功 Agent，原 Agent 失败仍计失败，`skipped/pending` 不进入画像，legacy task 无 attempt 时按 task row 降级。
- `weighted_task_count/success/failure` 使用 run 时间衰减，默认 half-life `30` 天；当前 conversation 证据加权，避免远古跨 conversation 样本压过近期本轮上下文。
- `timeout_count` 从 attempt state/error 中的 timeout markers 计数；`evaluation_failed/artifact_missing/timeout` 都会进入 `score_reasons`。
- `task_types` 来自 task row 的 `task_type`；`task_taxonomy` 使用 allowlist 关键词粗分 `document/frontend/backend/deployment/workflow/presentation/data/review/repair/general`。
- `score` 是 deterministic soft score：近期成功、repair success、success rate 加分；weighted failure、evaluation failed、artifact missing、timeout 扣分；低样本会降低 score 并标记 `low_sample_confidence`。
- `confidence` 仍按样本数和 run 数分为 `low/medium/high`；低样本不应在 UI 或 planner 中呈现为强推荐。

User Preference Memory 语义：

- 从当前用户历史 `OrchestratorRun.user_request`、`final_summary` 和实际 artifact kinds 中确定性提取，不调用 LLM。
- 只使用 allowlist 关键词，输出 `domains`、`artifact_preferences`、`deployment_preferences`、`language_style_hints` 和短 `summary`。
- 偏好是只读 soft signal，不是用户手动配置，也不允许覆盖本轮显式指令。

Planner 使用规则：

- planner 白名单提取 `Agent capability profile v2 from recent user Orchestrator runs`、`User preference memory from recent Orchestrator runs` 和 v1 profile 三段。
- planner 不接收完整 `Previous Orchestrator structured memory` 历史详情。
- user-scope v2 profile 优先作为长期软信号；当前 conversation v1 高置信近期证据可作为冲突时 tie-breaker。
- 当前用户请求中的显式 Agent、技术、风格选择优先于历史画像和偏好；available/managed agent 校验仍是硬边界。

新增 memory sections：

```text
Agent capability profile v2 from recent user Orchestrator runs:
User preference memory from recent Orchestrator runs:
Agent capability profile from recent Orchestrator runs:
Previous Orchestrator structured memory:
```

实现注意：

- v2/user preference 不依赖当前 conversation 已有 run；只要 owner user 有历史 terminal Orchestrator runs，新 conversation 的 memory context 也可以注入 user-scope v2 signals。
- `Previous Orchestrator structured memory` 仍只展示当前 conversation 的历史 run；当前 conversation 无 run 时不注入该 section。

#### 4.3.4 Agent Capability Profile v2 公网 E2E

2026-06-04 公网后端 API/SSE 验收已通过：

```text
scenario: p2_agent_capability_profile_v2
report: /tmp/agenthub_p2_agent_capability_profile_v2_report.json
sse: /tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl
temporary_account: cap_v2_e2e_1780571438_4042116
seed_conversation_id: d9c96baf-2e4e-4b3a-a4a0-39ee68bf2f27
followup_conversation_id: 0d7ed6d6-dcbf-4212-9150-55d410af622c
passed: true
```

follow-up conversation 在发送用户请求前 `orchestrator_runs=0`，但 v2 API 已返回同一用户 seed conversation 的 user-scope profile：

```text
scope: user
runs_considered: 1
source_conversation_count: 1
claude-code: task_count=1, success_count=0, failure_count=1, evaluation_failed_count=1, score=-0.945
opencode-helper: task_count=1, success_count=1, failure_count=0, evaluation_failed_count=0, score=1.35
preferences: artifact_preferences document=2, other=1
```

follow-up 用户请求未点名具体执行 Agent；planner 通过 v2 profile 和 user preference memory 选择 `opencode-helper`。最新 run detail 中唯一 task Agent 和全部实际 attempt Agent 均为 `opencode-helper`，并成功创建 `p2-capability-v2-followup.md`。该证据验证 v2 user-scope API、空新 conversation 的 memory 注入、planner 白名单读取 v2/preference sections，以及“不用历史偏好覆盖本轮明确指令”的软选择边界。

#### 4.3.5 Memory service 内部模块边界

2026-06-05 将原单文件 memory service 拆为 `backend/app/services/_orchestrator_memory/` 内部 package。`backend/app/services/orchestrator_memory.py` 保留为唯一稳定公共导入门面，现有 API、stream context 和测试调用方无需迁移。

内部职责：

- `types.py`：公共 profile/preference dataclass、内部 accumulator/event insight 与常量。
- `store.py`：run、task、attempt、event 持久化生命周期。
- `queries.py`：terminal runs、owned user runs、tasks、attempts、events 的共享查询和排序规则。
- `capability_v1.py`：conversation-scope v1 聚合，以及 v1/v2 共用的实际参与 Agent、artifact、failure insight 与 confidence 规则。
- `capability_v2.py`：user-scope v2 聚合、时间衰减、taxonomy、timeout、score 与 score reasons。
- `preferences.py`：deterministic User Preference Memory 提取。
- `context.py`：固定 section 顺序的 memory context 构建、格式化与注入。
- `run_reader.py`：run list/detail 读取和 structured run 格式化。
- `serialization.py`：payload sanitization、文本截断、去重和 payload helper。

本次拆分不改变 v1/v2 统计、评分、衰减、排序、关键词、summary 文案、section 顺序、字符预算、API wire shape、数据库模型或 planner 行为；它不是 Capability Profile v3，也不需要更新历史公网 E2E acceptance。

### 4.4 配置字段

新增 builtin/orchestrator config：

| 字段 | 类型 | 默认 | 说明 |
|---|---:|---:|---|
| `orchestrator_memory_enabled` | bool | `true` | 是否启用结构化 Orchestrator memory |
| `orchestrator_memory_recent_runs` | int | `3` | 注入最近 run 数，建议校验 `1..10` |
| `orchestrator_memory_context_max_chars` | int | `6000` | 注入文本预算，建议校验 `1..32000` |

同步更新：

- config validation。
- `AgentConfig` schema。
- OpenAPI。
- seed builtin `orchestrator`。

---

## 5. Debug API

新增 dev-only Orchestrator run list/detail API，生产环境返回 404，与现有 conversation memory debug API 保持一致。

新增只读 Agent capability profile API，供 debug、E2E 和后续前端展示使用：

```text
GET /api/v1/conversations/{conversation_id}/agent-capability-profile
```

返回当前用户拥有的当前 conversation 内画像 items。聚合字段包括 `runs_considered`、`task_count`、`success_count`、`failure_count`、`artifact_missing_count`、`evaluation_failed_count`、`avg_attempts`、`artifact_kinds`、`review_outcomes`、`repair_success_count`、`recent_failure_reasons` 和 `confidence`。该 API 不新增 mutation，必须复用 conversation ownership check。

新增只读 v2 API：

```text
GET /api/v1/conversations/{conversation_id}/agent-capability-profile-v2
```

返回 `scope=user`、`items`、`preferences`、`source_conversation_count`、`runs_considered`、`generated_at` 和 `total`。查询参数包括 `recent_runs=60`、`half_life_days=30.0` 和 `limit=10`，均有上限。该 API 复用 conversation ownership check，并基于 owner user 聚合跨 conversation 画像。

```text
GET /api/v1/conversations/{conv_id}/orchestrator-runs?limit=20
GET /api/v1/conversations/{conv_id}/orchestrator-runs/{run_id}
```

要求：

- 必须做 conversation ownership check。
- `limit` 范围 `1..100`，默认 `20`。
- list 返回 run 摘要，不需要包含完整 instruction。
- detail 返回 run、tasks、attempts、events。
- 不暴露 API key、环境变量、CLI args、SDK options。

---

## 6. 与真实 Agent 的关系

该 memory 层不改变真实 agent 的执行方式。

### 6.1 External agents

`claude-code`、`codex-helper`、`opencode-helper` 继续：

- 普通问答命中 direct chat 时不启动真实 runtime。
- 任务请求进入真实 SDK/CLI runtime。
- 从 `messages` 和 workspace guard prompt 获取上下文。
- 通过 stdout/SDK event 返回 text、tool_call、tool_result、error。

Orchestrator memory 只记录它们在 Orchestrator 编排中的结果，不改它们的 runtime prompt 或内部记忆。

### 6.2 BuiltinAgent

BuiltinAgent 的 model/tool loop 继续只维护本轮 `current_messages`。MCP/native tool result 是否成为长期事实，取决于上层 message persistence 和 Orchestrator attempt 记录。

### 6.3 Orchestrator

Orchestrator 的 memory 是“项目经理记忆”：

- 记住谁做了什么。
- 记住哪个 artifact 出现或缺失。
- 记住哪个检查任务通过或失败。
- 记住 ReAct 为什么新增/跳过任务。

它不是“执行工具记忆”，也不是“模型私有思考记录”。

---

## 7. 失败与降级

必须保证 memory 失败不会影响用户任务：

- DB 写入失败：记录日志，继续 SSE。
- 历史 memory 查询失败：跳过结构化 memory 注入。
- 单个 run 数据不完整：formatter 跳过坏记录，保留其他 run。
- attempt payload 超长：按字段截断，不写超大 JSON。
- disconnected：message 状态按现有逻辑处理，run 尽量标记 `cancelled`。

状态映射：

| 情况 | run status |
|---|---|
| 所有流转正常结束，即使部分子任务 failed/artifact_missing | `done` |
| Orchestrator fatal error | `error` |
| 客户端断开导致 stream 中止 | `cancelled` |
| writer 不可用 | 不创建 run，不影响 SSE |

---

## 8. 测试计划

### 8.1 Orchestrator 单测

- task 执行完成后 writer 收到 run、task、attempt、summary。
- ReAct 动态新增任务后记录 `react_decision` event。
- artifact_missing、fallback attempt、子 agent error 都能写入 attempt。
- writer 抛异常时 SSE 仍然 `done`。
- platform fact 和 direct answer 不创建 run。

### 8.2 Context 注入测试

- 最近 terminal runs 被格式化成 `Previous Orchestrator structured memory`。
- 有历史 terminal runs 时，memory context 在 structured memory 前包含 `Agent capability profile from recent Orchestrator runs`。
- planner 输入包含 capability profile 段，但不包含无关的 structured memory 历史详情。
- 超预算时 profile + structured memory 共同受 `max_chars` 控制。
- 没有 run 时不注入空 system message。
- 只对 Orchestrator 目标注入，不对 external agent 注入。
- 注入后最新用户请求仍是最后的 active request。

### 8.3 API / DB 测试

- Alembic migration 创建四张表和关键索引。
- dev list/detail API 返回 run/task/attempt/event。
- Agent capability profile API 返回当前 conversation 的 profile items。
- production mode debug API 返回 404。
- ownership check 防止跨用户读取。

### 8.4 回归

建议验证：

```bash
uv run python -m pytest tests/test_orchestrator.py tests/test_stream_tool_calls.py tests/test_context_builder.py tests/test_registry.py -q
uv run python -m pytest tests/test_agent_config_validation.py tests/test_b1_quality.py -q
uv run python -m ruff check app tests
uv run python -m mypy app/agents app/services app/schemas/agent.py
```

---

## 9. 实现入口建议

建议新增或修改：

- `backend/app/models/orchestrator_memory.py`
- `backend/app/services/orchestrator_memory.py`（稳定公共门面）
- `backend/app/services/_orchestrator_memory/`（内部实现）
- `backend/app/api/v1/conversations.py`
- `backend/app/api/v1/stream.py`
- `backend/app/api/v1/stream_orchestrator_context.py`
- `backend/app/agents/orchestrator/adapter.py`
- `backend/app/agents/orchestrator/memory_hooks.py`
- `backend/app/agents/orchestrator/react.py`
- `backend/app/agents/config_validation.py`
- `backend/app/schemas/agent.py`
- `backend/app/schemas/conversation.py`
- `shared/openapi.yaml`
- `backend/alembic/versions/<revision>_add_orchestrator_memory.py`

实现顺序：

1. DB model + migration + schema。
2. Memory store + formatter。
3. Agent capability profile 聚合 service。
4. stream 层注入 writer、capability profile 和 structured memory context。
5. Orchestrator 写入 hooks。
6. Debug/API。
7. 测试和 OpenAPI/config/seed 回归。

---

## 10. 与现有 Spec 的关系

- [core.spec.md](core.spec.md) 描述当前 Orchestrator 主行为契约，已包含 structured memory 边界。
- [task-planning.spec.md](task-planning.spec.md) 描述 planner 和 task schema。
- 本文档描述 Orchestrator 跨轮结构化记忆和上下文注入。
## 2026-06-07 Memory Status Addendum

Structured Orchestrator memory now treats `interrupted` as a terminal run/task-attempt state. It is distinct from `cancelled`: `interrupted` means the user explicitly clicked Stop on the agent turn; `cancelled` remains legacy/system cancellation language. Recent-run memory injection may include interrupted runs so Orchestrator can answer follow-up questions about stopped work.
