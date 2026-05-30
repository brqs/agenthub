# B2 Refactor Plan

> 目标：降低 B2 Agent Runtime Layer 的业务代码复杂度、重复实现和文档分叉风险，同时保持现有 `BaseAgentAdapter`、`StreamChunk`、SSE、DB schema 和前端契约稳定。
>
> 状态：business-main refactor implemented / orchestrator package implemented
> 最后更新：2026-05-30

---

## 0. 当前执行状态

本文件最初是 B2 重构计划，现在同时作为本轮重构的执行索引。当前已经完成的工作集中在“拆薄入口文件、抽出重复 helper、保留外部契约不变”。

| 阶段 | 当前状态 | 主要结果 |
|---|---|---|
| Phase 1 Orchestrator extraction | implemented | 抽出 memory hooks、artifact tracking、summary/context formatting、stream remap helper、direct answer path、task planning path、adapter/fallback helper、static execution state machine，并迁移为 `app.agents.orchestrator` package |
| Phase 2 Orchestrator test split | mostly implemented | 抽出 `tests/orchestrator_fakes.py`、platform facts、planner、ReAct 测试文件；按当前边界不再继续拆 execution/artifact/fallback |
| Phase 3 Stream boundary extraction | mostly implemented | 抽出 stream content accumulator 与 Orchestrator runtime context 注入 |
| Phase 4 External runtime common layer | mostly implemented | 抽出 external runtime prelude、SDK stream folding、argv/error/truncate runtime utils |
| Phase 5 Config schema single source | mostly implemented | 抽出 numeric config metadata、seed 默认值，并让 validation / `AgentConfig` / OpenAPI contract 测试共用 |
| Phase 6 Docs re-index | implemented | README 已建立 spec 入口，本文件记录当前状态与不继续扩大的边界 |

当前仍未完成：

- `backend/tests/test_orchestrator.py` 已抽 fake helper、platform facts、planner 和 ReAct 测试；按当前边界停止继续拆 execution/artifact/fallback，保留主干执行测试集中可见。
- OpenCode JSONL 主循环仍保留在 adapter 内；继续抽象需要单独设计 JSONL event contract，避免为了形式增加间接层。
- 静态 `shared/openapi.yaml` 仍未自动生成；当前通过测试确保 `AgentConfig` 字段与 numeric bounds 不漂移。
- 未把全部 spec 迁移到 `current/proposals/execution` 目录；当前选择保留历史链接稳定，只在 B2 README 建立接手入口。

最近一次已记录的综合验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py tests/test_stream_tool_calls.py tests/test_adapter_smoke.py tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_external_direct_chat.py tests/test_agent_config_validation.py tests/test_registry.py -q
# 207 passed, 1 skipped

uv run python -m ruff check app/agents app/services/orchestrator_memory.py app/api/v1/stream.py app/api/v1/stream_orchestrator_context.py tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py tests/orchestrator_fakes.py
# passed

uv run python -m mypy app/agents app/services/orchestrator_memory.py app/schemas/agent.py
# passed

git diff --check
# passed
```

## 1. 背景

B2 已从最初的 adapter / artifact parser 扩展到真实 external runtime、BuiltinAgent、ModelGateway、Orchestrator、structured memory、ReAct dynamic task graph、platform fact router、tool calling。功能增长后，当前主要问题不是单点 bug，而是边界逐渐变厚：

- 重构前 Orchestrator 主文件有 1700+ 行，承担入口路由、direct answer、task parsing、dispatch、artifact 解析、memory writer 包装、summary、fallback 等多种职责；本轮已降到约 330 行并抽出主干 helper。
- Orchestrator 周边模块数量增加，但部分职责仍重复散落在主文件、tool loop、platform facts、stream 层。
- External adapters 三个实现里存在相似的 direct chat shortcut、workspace guard、runtime budget、event mapping、CLI/SDK fallback 逻辑。
- Stream 层同时承担上下文构建、Orchestrator 群聊注入、memory writer 注入、SSE 持久化、tool block pairing。
- 文档已经覆盖多个迭代版本，但缺少一个“当前 B2 真实模块边界与重构路线”的收敛入口。

本计划不追求一次性大爆炸重写，而是分阶段把复杂代码移到明确边界内，并用现有测试矩阵保护行为。

---

## 2. 当前规模快照

初始计划记录的粗略行数：

| 区域 | 文件 | 行数 |
|---|---|---:|
| Orchestrator 主入口 | `backend/app/agents/orchestrator.py` | 1761 |
| Orchestrator planner | `backend/app/agents/orchestrator_planner.py` | 340 |
| Orchestrator platform facts | `backend/app/agents/orchestrator_platform_facts.py` | 532 |
| Orchestrator ReAct | `backend/app/agents/orchestrator_react.py` | 670 |
| Orchestrator tool loop | `backend/app/agents/orchestrator_tool_loop.py` | 556 |
| Orchestrator tools | `backend/app/agents/orchestrator_tools.py` | 468 |
| Orchestrator memory service | `backend/app/services/orchestrator_memory.py` | 499 |
| Stream API | `backend/app/api/v1/stream.py` | 467 |
| Orchestrator tests | `backend/tests/test_orchestrator.py` | 2494 |
| Orchestrator tool calling tests | `backend/tests/test_orchestrator_tool_calling.py` | 426 |

结论：优先重构对象是 Orchestrator 主入口、Orchestrator 测试拆分、Stream-Orchestrator 接入边界、External adapter 公共 runtime/direct-chat 逻辑。

当前执行后的关键行数快照：

| 区域 | 文件 | 行数 |
|---|---|---:|
| Orchestrator public package | `backend/app/agents/orchestrator/__init__.py` | 5 |
| Orchestrator adapter entry | `backend/app/agents/orchestrator/adapter.py` | 329 |
| Stream API | `backend/app/api/v1/stream.py` | 145 |
| Orchestrator tests | `backend/tests/test_orchestrator.py` | 1054 |
| Orchestrator platform facts tests | `backend/tests/test_orchestrator_platform_facts.py` | 491 |
| Orchestrator planner tests | `backend/tests/test_orchestrator_planning.py` | 427 |
| Orchestrator ReAct tests | `backend/tests/test_orchestrator_react.py` | 301 |
| Claude Code adapter | `backend/app/agents/external/claude_code.py` | 370 |
| Codex adapter | `backend/app/agents/external/codex.py` | 754 |
| OpenCode adapter | `backend/app/agents/external/opencode.py` | 620 |
| External runtime utils | `backend/app/agents/external/runtime_utils.py` | 82 |
| Orchestrator direct answer | `backend/app/agents/orchestrator/direct_answer.py` | 210 |
| Orchestrator task planning | `backend/app/agents/orchestrator/task_planning.py` | 361 |
| Orchestrator adapter/fallback | `backend/app/agents/orchestrator/adapters.py` | 184 |
| Orchestrator static execution | `backend/app/agents/orchestrator/execution.py` | 442 |

这个快照说明：stream 入口和 Orchestrator 主入口已经明显变薄，Orchestrator 已完成 package 化，external adapter 重复逻辑继续收敛；测试继续拆分和更深的 OpenCode JSONL 主循环抽象属于单独后续。

---

## 3. 重构原则

1. 保持外部契约不变：
   - 不改 `BaseAgentAdapter.stream()`。
   - 不改 `StreamChunk` 字段语义。
   - 不改 SSE event name。
   - 不新增 DB schema，除非单独开 migration spec。
   - 不要求前端同步改动。

2. 先移动代码，再改行为：
   - 第一阶段只做结构拆分和测试搬迁。
   - 行为变化必须有独立 spec 和测试。

3. Orchestrator 主文件目标：
   - 只保留 `OrchestratorAdapter.stream()` 主流程和少量 orchestration glue。
   - 将 helper 按职责搬出，不让主文件继续吸收新功能。

4. 每一阶段必须可独立验证：
   - 小步提交。
   - 每步跑对应测试。
   - 不依赖真实 external runtime 才能证明重构正确。

---

## 4. 目标模块边界

### 4.1 Orchestrator

建议收敛为：

```text
backend/app/agents/orchestrator/
  __init__.py
  adapter.py              # OrchestratorAdapter.stream 主入口
  routing.py              # platform fact / direct answer / tool loop / planner 分支选择
  direct_answer.py        # direct answer gateway/prompt/messages
  task_plan.py            # config.tasks / direct mention / planner fallback / legacy template
  execution.py            # _run_task / _run_static_tasks / fallback / dependency check
  stream_remap.py         # block_index/tool_call_id remap + sub stream folding
  artifact_tracking.py    # artifact candidate extraction + workspace-relative exists check
  summary.py              # planning text / execution summary / task result context formatting
  memory_hooks.py         # writer protocol wrapper, start/record/finish no-op safety
  config.py               # positive int/bool helpers, agent id list helpers
```

当前已有模块继续保留并收敛：

```text
orchestrator_planner.py          -> orchestrator/task_plan.py 或保留为 planner.py
orchestrator_platform_facts.py   -> orchestrator/platform_facts.py
orchestrator_react.py            -> orchestrator/react.py
orchestrator_tool_loop.py        -> orchestrator/tool_loop.py
orchestrator_tools.py            -> orchestrator/tools.py
orchestrator_types.py            -> orchestrator/types.py
```

迁移方式：

- 先创建 package，不删除旧 import。
- 用 wrapper re-export 保持 `from app.agents.orchestrator import OrchestratorAdapter` 可用。
- 测试全部通过后，再移除旧平铺文件或保留兼容 shim。

### 4.2 External Runtime

建议新增公共边界：

```text
backend/app/agents/external/
  direct_chat.py          # 已有，继续作为三方 QA shortcut 统一入口
  runtime_budget.py       # 已有，统一 timeout/heartbeat/idle
  workspace_prompt.py     # 已有，统一 workspace guard prompt
  event_mapping.py        # 新增：tool_call/tool_result/text/error 映射公共工具
  cli_common.py           # 新增：CLI argv、stderr、exit error、safe output、process cleanup
  identity.py             # 新增：identity shortcut / model/runtime identity helper
```

目标：

- `claude_code.py`、`codex.py`、`opencode.py` 保留 provider-specific SDK/CLI 接入。
- 相同的 runtime safety、event mapping、direct answer、workspace prompt 不再复制三份。

### 4.3 Stream API

建议把 `stream.py` 的 B2 注入逻辑挪出：

```text
backend/app/services/stream_content_accumulator.py
backend/app/services/orchestrator_runtime_context.py
```

目标：

- `stream.py` 只负责 HTTP/SSE 生命周期、DB message persistence、disconnect。
- `orchestrator_runtime_context.py` 负责：
  - conversation agents 注入
  - available agents 计算
  - orchestrator memory context message
  - memory writer 构造
  - cancel active run
- `stream_content_accumulator.py` 负责 tool block pairing、block accumulation、diff parsing。

---

## 5. 冗余与复杂度热点

### 5.1 Orchestrator 主文件

待拆分职责：

- direct answer prompt/gateway/config。
- direct mention routing 和 agent alias。
- task parse / derive / validation。
- fallback adapter 调用。
- sub stream block/tool id remap。
- artifact path extraction。
- memory writer no-op wrappers。
- summary 和 context formatting。

验收：

- `orchestrator.py` 或新 `adapter.py` 控制在 350 行以内。
- 原有 `tests/test_orchestrator.py` 全部通过。
- public import 不变。

### 5.2 Orchestrator 测试

当前 `tests/test_orchestrator.py` 过大，建议拆成：

```text
tests/orchestrator/
  test_entry_routing.py
  test_task_planning.py
  test_static_execution.py
  test_react_execution.py
  test_platform_facts.py
  test_artifact_tracking.py
  test_fallback_attempts.py
  test_stream_remap.py
```

验收：

- 共享 fake adapter/gateway 放入 `tests/orchestrator/conftest.py` 或 helper。
- 单个测试文件尽量小于 500 行。
- pytest node id 更容易定位失败域。

### 5.3 Config Validation

`config_validation.py` 逐渐吸收所有 provider 字段，建议改为分 provider schema：

```text
backend/app/agents/config/
  validation.py
  builtin.py
  external.py
  common.py
```

验收：

- `validate_agent_config()` 入口不变。
- `AgentConfig` / OpenAPI 字段继续同步。
- 新增字段必须在同一个地方声明校验范围，避免 schema/config/openapi 三处漂移。

### 5.4 文档

当前 spec 很完整，但存在历史文档、执行文档、设计文档同时存在的问题。建议整理为三层：

```text
docs/b2/spec/
  current/       # 当前真实契约
  proposals/     # 还未实现的设计
  execution/     # 已完成执行记录和验证结果
```

短期不立即搬目录，先在 `docs/b2/README.md` 明确状态：

- current contract
- implemented execution record
- proposal / future work
- historical task-dispatch

---

## 6. 分阶段执行计划

### Phase 0: Baseline Freeze

目标：先建立重构前证据。

动作：

1. 记录当前关键测试命令和结果。
2. 记录当前模块行数。
3. 确认 `git diff --check` 通过。
4. 确认 openapi yaml 可解析。

建议命令：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py tests/test_stream_tool_calls.py tests/test_registry.py tests/test_agent_config_validation.py -q
uv run python -m ruff check app tests
uv run python -m mypy app/agents app/schemas/agent.py
cd ..
git diff --check
python3 - <<'PY'
import yaml
from pathlib import Path
yaml.safe_load(Path("shared/openapi.yaml").read_text(encoding="utf-8"))
print("openapi yaml ok")
PY
```

完成标准：

- 当前基线绿色。
- 如果有既有失败，必须记录为非重构引入。

### Phase 1: Orchestrator Pure Extraction

目标：只搬代码，不改行为。

动作：

1. 新建 `backend/app/agents/orchestrator/` package。
2. 迁移 types / config helpers / memory hooks / stream remap / artifact tracking / summary。
3. 让旧 `backend/app/agents/orchestrator.py` 变成 compatibility wrapper，或将 `adapter.py` re-export 到旧路径。
4. 保持所有测试 import 不变。

完成标准：

- `OrchestratorAdapter` public import 不变。
- 所有 Orchestrator tests 通过。
- 主入口文件职责明显变薄。

### Phase 2: Orchestrator Test Split

目标：降低测试维护成本。

动作：

1. 拆分 `tests/test_orchestrator.py`。
2. 抽出 fake adapter/gateway/helper。
3. 每次搬迁一组测试后立即跑对应测试。

完成标准：

- 测试数量不少于拆分前。
- 每个测试文件有清晰主题。
- 失败时能快速定位是 routing、planning、execution、memory、tool loop 还是 remap。

### Phase 3: Stream Boundary Extraction

目标：让 B1 stream endpoint 不再直接承载 B2 Orchestrator runtime context 细节。

动作：

1. 抽出 `_ContentAccumulator` 到 service。
2. 抽出 `_orchestrator_conversation_config()`、memory context、cancel active run 到 `orchestrator_runtime_context.py`。
3. `stream.py` 只保留：
   - auth / conversation ownership
   - workspace 获取
   - adapter 获取
   - SSE lifecycle
   - message commit

完成标准：

- `tests/test_stream_tool_calls.py` 通过。
- Orchestrator group member 注入行为不变。
- Tool block orphan/pending 语义不变。

### Phase 4: External Runtime Common Layer

目标：减少 `claude_code.py`、`codex.py`、`opencode.py` 的重复逻辑。

动作：

1. 抽出 external event mapping 公共结构：
   - text delta
   - tool call
   - tool result
   - safe output truncation
   - error chunk
2. 抽出 CLI process common helper：
   - argv parsing
   - timeout / terminate
   - stderr reading
   - exit error
3. 保留 provider-specific SDK event parsing。

完成标准：

- `tests/test_claude_code_external_adapter.py`
- `tests/test_codex_external_adapter.py`
- `tests/test_opencode_external_adapter.py`
- `tests/test_external_direct_chat.py`
- `tests/test_cli_runtime.py`

全部通过。

### Phase 5: Config Schema Single Source

目标：减少 config validation / Pydantic schema / OpenAPI / seed 的字段漂移。

动作：

1. 定义 B2 config field registry，描述：
   - name
   - provider scope
   - type
   - min/max
   - default
   - openapi description
2. 先只用于测试校验字段同步，不急着自动生成 OpenAPI。
3. 后续再评估是否生成 schema/openapi。

完成标准：

- 新增测试能发现 config_validation、AgentConfig、OpenAPI、seed 字段缺失。
- 不改变 API 输出。

### Phase 6: Docs Re-index

目标：文档从“历史任务堆叠”变成“当前契约入口清晰”。

动作：

1. 更新 `docs/b2/README.md`：
   - 当前契约
   - 已实现 execution record
   - proposal / future work
   - historical task dispatch
2. 对每个 spec 增加状态：
   - current
   - implemented
   - proposal
   - historical
3. 保留历史任务文档，不强行重写。

完成标准：

- 新开发者能从 README 找到当前真实契约。
- 未实现 proposal 不会被误认为已上线能力。

---

## 7. 风险与保护线

| 风险 | 保护 |
|---|---|
| 搬模块破坏 import | 保持旧路径 wrapper；先不批量 rename public imports。 |
| 重构中误改 SSE 顺序 | `test_stream_tool_calls.py` 和 Orchestrator event 序列测试必须每阶段跑。 |
| tool_call/tool_result pairing 退化 | 保留 orphan/pending 测试；新增重构后 pairing fixture。 |
| group member 边界回退 | 保留 conversation `available_agents` / `managed_agent_ids` 覆盖测试。 |
| memory 写入重复或丢失 | 保留 memory writer fake tests；检查 run/task/attempt/event 数量。 |
| docs 和代码再次漂移 | 每次改 config 或入口顺序时同步 README/spec，并跑 OpenAPI 字段测试。 |

---

## 8. 非目标

本轮重构计划不做：

- 不实现 `run_test`。
- 不增加 browser validation。
- 不改变 Orchestrator 默认是否开启 tool calling。
- 不更改数据库 schema。
- 不重写 external runtime 的 provider SDK 接入。
- 不引入新的大型框架或依赖。

---

## 9. 推荐执行顺序

最推荐的实际执行顺序：

1. Phase 0 baseline。
2. Phase 1 只拆 Orchestrator 主文件。
3. Phase 2 拆 Orchestrator tests。
4. Phase 3 拆 stream B2 context。
5. Phase 4 抽 external runtime common layer。
6. Phase 5 config/schema 字段同步保护。
7. Phase 6 docs re-index。

原因：

- Orchestrator 是最大复杂度来源，也是最近变更最多的地方。
- 先拆代码再拆测试，会让测试搬迁有稳定目标。
- stream 边界涉及 B1/B2 协作，放在 Orchestrator 稳定后更稳。
- external runtime 抽共性需要更多 provider 行为确认，适合放在后半段。

---

## 10. 完成定义

B2 重构完成需要满足：

- Orchestrator 主入口职责清晰，单文件不再承载大部分 helper。
- Orchestrator tests 已按主题拆分。
- Stream endpoint 与 Orchestrator runtime context 解耦。
- External adapters 共享 direct chat / runtime budget / workspace prompt / CLI common / event mapping 中可安全共享的部分。
- Config 字段同步有测试保护。
- B2 README 能清晰区分 current / implemented / proposal / historical 文档。
- 回归命令通过：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py tests/test_stream_tool_calls.py tests/test_registry.py tests/test_agent_config_validation.py -q
uv run python -m pytest tests/test_external_direct_chat.py tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_cli_runtime.py -q
uv run python -m ruff check app tests
uv run python -m mypy app/agents app/schemas/agent.py
```

---

## 11. 执行记录

### 2026-05-30 Phase 1 partial: Orchestrator memory hooks

已完成：

- 新增 `backend/app/agents/orchestrator_memory_hooks.py`。
- 从 `backend/app/agents/orchestrator.py` 移出 structured memory writer 的 no-op-safe 包装：
  - `start_run`
  - `record_task_started`
  - `record_task_result`
  - `finish_run`
- `orchestrator.py` 继续负责计算 `user_request` 和 `plan_source`，避免新模块反向依赖主入口 helper。
- 外部契约未变化：
  - `OrchestratorAdapter` import path 不变。
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` 不变。
  - DB schema 不变。

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_memory_hooks.py tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_memory_hooks.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator artifact tracking

已完成：

- 新增 `backend/app/agents/orchestrator_artifacts.py`。
- 从 `backend/app/agents/orchestrator.py` 移出 artifact tracking 相关逻辑：
  - `finalize_artifact_candidates`
  - `check_attempt_artifacts`
  - `extract_artifact_paths_from_mapping`
  - `extract_artifact_paths_from_text`
  - artifact path keys / regex / sensitive path policy
- `orchestrator.py` 保留任务执行和 attempt 状态流转，只调用 artifact 模块完成候选路径归并与 workspace 存在性检查。
- 外部契约未变化：
  - `OrchestratorAdapter` import path 不变。
  - artifact missing / fallback 语义不变。
  - DB schema 不变。

行数变化：

- `backend/app/agents/orchestrator.py`: 约 `1687` -> `1611`
- 新增 `backend/app/agents/orchestrator_artifacts.py`: `109`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator summary/context formatting

已完成：

- 新增 `backend/app/agents/orchestrator_summary.py`。
- 从 `backend/app/agents/orchestrator.py` 移出 summary 和上下文文本格式化逻辑：
  - `planning_text`
  - `plan_source`
  - `fallback_summary_text`
  - `summary_text`
  - `task_result_context_message`
  - `format_task_result_context`
  - `format_attempt_context`
  - `truncate_preserving_edges`
- `orchestrator.py` 继续保留任务执行和消息组装，只负责把 config budget 传入 summary/context formatter。
- 外部契约未变化：
  - `OrchestratorAdapter` import path 不变。
  - ReAct / tool calling 仍通过 callback 使用同一 formatter。
  - SSE / DB schema 不变。

行数变化：

- `backend/app/agents/orchestrator.py`: 约 `1611` -> `1467`
- 新增 `backend/app/agents/orchestrator_summary.py`: `188`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_summary.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_summary.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator stream remapping

已完成：

- 新增 `backend/app/agents/orchestrator_streams.py`。
- 从 `backend/app/agents/orchestrator.py` 移出 sub-agent stream remap 相关逻辑：
  - `remapped_sub_stream`
  - `remap_block_index`
  - `remap_tool_call_id`
- `orchestrator.py` 继续保留 attempt 状态、文本/tool 累积 callback 和任务调度流程；stream helper 只负责子 agent 输出事件的折叠、block index 重映射、tool call id 前缀化，以及子 agent error/exception 到失败文本块的转换。
- 外部契约未变化：
  - `OrchestratorAdapter` import path 不变。
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` / SSE event shape 不变。
  - DB schema 不变。

行数变化：

- `backend/app/agents/orchestrator.py`: 约 `1467` -> `1392`
- 新增 `backend/app/agents/orchestrator_streams.py`: `113`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_streams.py app/agents/orchestrator_summary.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py --fix
# passed; 1 formatting issue fixed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_streams.py app/agents/orchestrator_summary.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py
# passed
```

### 2026-05-30 Phase 2 partial: Orchestrator test fakes extraction

已完成：

- 新增 `backend/tests/orchestrator_fakes.py`。
- 从 `backend/tests/test_orchestrator.py` 移出测试 fake/helper 代码：
  - `_collect`
  - `_assert_blocks_balanced`
  - `FakeSubAdapter`
  - `FakePartialThenExceptionAdapter`
  - `FakeWorkspaceWriterAdapter`
  - `FakeWorkspaceVerifierAdapter`
  - `FakePlannerGateway`
  - `FakeAnswerGateway`
  - `SequencedGateway`
  - `_react_decision_chunks`
  - `_task`
  - `_text_chunks`
- `test_orchestrator.py` 继续保留行为用例本身，helper 统一从 `tests.orchestrator_fakes` 引入。
- 外部契约未变化；仅测试组织结构变化。

行数变化：

- `backend/tests/test_orchestrator.py`: `2494` -> `2235`
- 新增 `backend/tests/orchestrator_fakes.py`: `282`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_streams.py app/agents/orchestrator_summary.py app/agents/orchestrator_artifacts.py app/agents/orchestrator_memory_hooks.py tests/test_orchestrator.py tests/orchestrator_fakes.py
# passed
```

### 2026-05-30 Phase 3 partial: Stream content accumulator extraction

已完成：

- 新增 `backend/app/api/v1/stream_accumulator.py`。
- 从 `backend/app/api/v1/stream.py` 移出 SSE content persistence 相关逻辑：
  - `StreamContentAccumulator`
  - diff block parsing
  - text/code/diff/web_preview block accumulation
  - `tool_call` / `tool_result` block accumulation
  - tool argument/output preview truncation
  - orphan tool call detection
- `stream.py` 保留 `_ContentAccumulator = StreamContentAccumulator` 兼容别名，避免既有 smoke tests 和旧调用路径断裂。
- 外部契约未变化：
  - `/api/v1/messages/{msg_id}/stream` endpoint 不变。
  - SSE event shape 不变。
  - persisted message content block shape 不变。
  - DB schema 不变。

行数变化：

- `backend/app/api/v1/stream.py`: `467` -> `277`
- 新增 `backend/app/api/v1/stream_accumulator.py`: `200`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_stream_tool_calls.py tests/test_adapter_smoke.py -q
# 18 passed

uv run python -m ruff check app/api/v1/stream.py app/api/v1/stream_accumulator.py tests/test_stream_tool_calls.py tests/test_adapter_smoke.py
# passed

uv run python -m py_compile app/api/v1/stream.py app/api/v1/stream_accumulator.py
# passed
```

说明：

- `uv run python -m mypy app/api/v1/stream.py app/api/v1/stream_accumulator.py` 仍会触发既有 `app/services/model_gateway.py` SDK 类型错误；该问题早于本次 stream accumulator 抽取，不作为本次拆分的阻断项。

### 2026-05-30 Phase 3 partial: Orchestrator stream context extraction

已完成：

- 新增 `backend/app/api/v1/stream_orchestrator_context.py`。
- 从 `backend/app/api/v1/stream.py` 移出 Orchestrator 专属 stream wiring：
  - 当前 group conversation agent metadata 注入
  - `conversation_agents` / `available_agents` / `managed_agent_ids` 构造
  - 安全 agent config 摘要字段过滤
  - Orchestrator structured memory context 注入
  - `orchestrator_memory_writer` 注入
  - 断连时 active run cancel helper
- `stream.py` 现在只保留 endpoint、ownership check、adapter/history/workspace 获取、SSE loop 和最终 message persistence。
- 外部契约未变化：
  - `/api/v1/messages/{msg_id}/stream` endpoint 不变。
  - Orchestrator group member/model fact behavior 不变。
  - Orchestrator memory DB schema 不变。
  - SSE event shape 和 persisted content block shape 不变。

行数变化：

- `backend/app/api/v1/stream.py`: `277` -> `145`
- 新增 `backend/app/api/v1/stream_orchestrator_context.py`: `166`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_stream_tool_calls.py tests/test_adapter_smoke.py tests/test_orchestrator_memory.py -q
# 20 passed

uv run python -m ruff check app/api/v1/stream.py app/api/v1/stream_accumulator.py app/api/v1/stream_orchestrator_context.py tests/test_stream_tool_calls.py tests/test_adapter_smoke.py tests/test_orchestrator_memory.py
# passed

uv run python -m py_compile app/api/v1/stream.py app/api/v1/stream_accumulator.py app/api/v1/stream_orchestrator_context.py
# passed
```

### 2026-05-30 Phase 4 partial: External runtime prelude extraction

已完成：

- 新增 `backend/app/agents/external/runtime_prelude.py`。
- 从三个 external runtime adapter 中抽出启动前公共分支：
  - workspace 必需校验
  - identity shortcut
  - direct chat routing
  - direct text result block 输出
- 已接入：
  - `backend/app/agents/external/claude_code.py`
  - `backend/app/agents/external/codex.py`
  - `backend/app/agents/external/opencode.py`
- 为了保留既有测试和运行时替换能力，`maybe_stream_direct_chat` 仍由各 adapter 模块传入 helper；测试中 monkeypatch adapter 模块变量的行为不变。
- 外部契约未变化：
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` / SSE event shape 不变。
  - direct chat 分类和 fallback 语义不变。
  - SDK/CLI runtime 主体未改。

行数变化：

- `backend/app/agents/external/claude_code.py`: `485` -> `482`
- `backend/app/agents/external/codex.py`: `871` -> `863`
- `backend/app/agents/external/opencode.py`: `636` -> `629`
- 新增 `backend/app/agents/external/runtime_prelude.py`: `82`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_external_direct_chat.py -q
# 67 passed, 1 skipped

uv run python -m ruff check app/agents/external/claude_code.py app/agents/external/codex.py app/agents/external/opencode.py app/agents/external/runtime_prelude.py
# passed

uv run python -m mypy app/agents/external/claude_code.py app/agents/external/codex.py app/agents/external/opencode.py app/agents/external/runtime_prelude.py
# passed
```

### 2026-05-30 Phase 4 partial: External SDK stream folding extraction

已完成：

- 新增 `backend/app/agents/external/sdk_stream.py`。
- 从 Claude Code / Codex SDK runtime 路径中抽出共同 event folding：
  - `iter_with_runtime_budget` 包装
  - heartbeat 透传
  - mapped SDK event 到 text block 的 open / delta / flush / close
  - preview/deploy text filter
  - timeout 前 pending text flush
  - exception 前 pending text flush
  - done total block 计数
- 已接入：
  - `backend/app/agents/external/claude_code.py`
  - `backend/app/agents/external/codex.py`
- Codex 的 “SDK 早期失败且尚未产生 runtime chunk 时 fallback CLI” 语义通过 callback 保留。
- OpenCode JSONL 主循环未改，避免把不同协议强行塞进同一 helper。
- 外部契约未变化：
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` / SSE event shape 不变。
  - SDK timeout/error/direct chat 行为保持测试覆盖下兼容。

行数变化：

- `backend/app/agents/external/claude_code.py`: `482` -> `386`
- `backend/app/agents/external/codex.py`: `863` -> `761`
- 新增 `backend/app/agents/external/sdk_stream.py`: `111`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_external_direct_chat.py -q
# 67 passed, 1 skipped

uv run python -m ruff check app/agents/external/claude_code.py app/agents/external/codex.py app/agents/external/opencode.py app/agents/external/sdk_stream.py app/agents/external/runtime_prelude.py tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_external_direct_chat.py
# passed

uv run python -m mypy app/agents/external/claude_code.py app/agents/external/codex.py app/agents/external/opencode.py app/agents/external/sdk_stream.py app/agents/external/runtime_prelude.py
# passed
```

### 2026-05-30 Phase 5 partial: AgentConfig numeric field metadata extraction

已完成：

- 新增 `backend/app/agents/config_fields.py`。
- 将 AgentConfig numeric bounds 和 provider choice 常量从 `config_validation.py` 中抽到共享 metadata：
  - external runtime budget fields
  - external direct chat QA fields
  - builtin Orchestrator/ReAct/memory/tool fields
  - supported upstream providers / top-level providers / Codex runtime choices
- `backend/app/agents/config_validation.py` 改为遍历 shared numeric field metadata 做范围校验。
- `backend/app/schemas/agent.py` 的 `AgentConfig` Pydantic field bounds 改为引用同一份 shared metadata。
- `backend/tests/test_agent_config_validation.py` 新增 schema metadata 回归测试，确保 `AgentConfig.model_json_schema()` 的 numeric bounds 与 `NUMERIC_CONFIG_FIELDS` 保持一致。
- 静态 `shared/openapi.yaml` 未在本次自动生成；现有 OpenAPI 字段契约测试保持覆盖。

外部契约未变化：

- Agent config 字段名不变。
- Numeric min/max 值不变。
- `validate_agent_config()` 行为不变。
- `AgentConfig` schema 输出的约束值不变。

行数变化：

- 新增 `backend/app/agents/config_fields.py`: `70`
- `backend/app/agents/config_validation.py`: numeric validation 从逐字段调用收敛为 metadata loop
- `backend/app/schemas/agent.py`: numeric bounds 改为引用 shared metadata

已验证：

```bash
cd backend
uv run python -m pytest tests/test_agent_config_validation.py -q
# 53 passed

uv run python -m ruff check app/agents/config_fields.py app/agents/config_validation.py app/schemas/agent.py tests/test_agent_config_validation.py
# passed

uv run python -m mypy app/agents/config_fields.py app/agents/config_validation.py app/schemas/agent.py
# passed

uv run python -m py_compile app/agents/config_fields.py app/agents/config_validation.py app/schemas/agent.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator direct answer extraction

已完成：

- 新增 `backend/app/agents/orchestrator_direct_answer.py`。
- 从 `backend/app/agents/orchestrator.py` 抽出 direct answer path：
  - direct answer system prompt
  - meta-question marker 判断
  - answer `ModelGateway` 构造
  - answer config 合并与校验
  - direct answer stream block/tool remap
  - answer upstream error 映射
- `orchestrator.py` 只保留 direct answer 分支选择与回调注入，不再直接依赖 `ModelGateway`。
- 外部契约未变化：
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` / SSE event shape 不变。
  - direct answer 路径仍跳过 internal start/done，并保持错误时停止当前 Orchestrator 流。

行数变化：

- `backend/app/agents/orchestrator.py`: `1392` -> `1226`
- 新增 `backend/app/agents/orchestrator_direct_answer.py`: `210`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_direct_answer.py tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_direct_answer.py
# passed

uv run python -m py_compile app/agents/orchestrator.py app/agents/orchestrator_direct_answer.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator task planning extraction

已完成：

- 新增 `backend/app/agents/orchestrator_task_planning.py`。
- 从 `backend/app/agents/orchestrator.py` 抽出 task planning / request routing 相关职责：
  - config `tasks` 解析与 task id 去重
  - LLM planner payload 调用与校验
  - planner protocol error 到 direct answer fallback 的判断
  - direct multi-agent routing
  - legacy managed-agent template planning
  - managed agent id 清洗
  - latest user request 提取
  - agent alias / explicit mention 识别
  - task intent marker 判断
  - preview/deploy-only task pruning
- `orchestrator.py` 继续保留主编排流、fallback execution、子 agent dispatch 和 attempt 状态流转。
- 外部契约未变化：
  - `OrchestratorAdapter` public import 不变。
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` / SSE event shape 不变。
  - planner fallback、direct routing、platform fact callback 和 ReAct callback 语义保持不变。

行数变化：

- `backend/app/agents/orchestrator.py`: `1226` -> `898`
- 新增 `backend/app/agents/orchestrator_task_planning.py`: `361`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed

uv run python -m py_compile app/agents/orchestrator.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator adapter/fallback extraction

已完成：

- 新增 `backend/app/agents/orchestrator_adapters.py`。
- 从 `backend/app/agents/orchestrator.py` 抽出 adapter lookup 与 fallback streaming 相关职责：
  - `sub_adapters` / `adapter_factory` source 校验
  - 子 agent adapter lookup
  - fallback adapter / fallback factory lookup
  - planner failure fallback stream folding
  - fallback agent switch event
  - fallback block index / tool call id remap
- `orchestrator.py` 继续保留主编排流和 task attempt 状态机，只通过 helper 调用子 agent / fallback agent。
- 外部契约未变化：
  - `OrchestratorAdapter` public import 不变。
  - `BaseAgentAdapter` 不变。
  - fallback SSE event shape 不变。
  - adapter factory exception 仍作为 task failure 处理，不升级为顶层 error。

行数变化：

- `backend/app/agents/orchestrator.py`: `898` -> `753`
- 新增 `backend/app/agents/orchestrator_adapters.py`: `184`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed

uv run python -m py_compile app/agents/orchestrator.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed
```

### 2026-05-30 Phase 1 partial: Orchestrator static execution extraction

已完成：

- 新增 `backend/app/agents/orchestrator_execution.py`。
- 从 `backend/app/agents/orchestrator.py` 抽出 static task execution / attempt state machine：
  - dependency satisfied check
  - static task loop
  - single task attempt loop
  - per-task fallback agent selection
  - max attempts / retry 判断
  - task message assembly
  - sub-agent stream remap callback glue
  - artifact candidate finalize / missing artifact check
  - text/tool event accumulation
  - tool summary formatting
  - shared text block helpers
  - `_positive_int_config` / `_error_reason` / `_error_code`
- `orchestrator.py` 现在基本只保留入口路由：platform facts、direct answer、tool loop、planner resolve、fallback branch、memory run start、ReAct/static execution branch。
- 外部契约未变化：
  - `OrchestratorAdapter` public import 不变。
  - `BaseAgentAdapter` 不变。
  - `StreamChunk` / SSE event shape 不变。
  - ReAct 仍通过 callback 调用同一个 `_run_task`。
  - static execution summary、attempt fallback、artifact missing 语义保持测试覆盖下兼容。

行数变化：

- `backend/app/agents/orchestrator.py`: `753` -> `329`
- 新增 `backend/app/agents/orchestrator_execution.py`: `442`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check app/agents/orchestrator.py app/agents/orchestrator_execution.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_execution.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed

uv run python -m py_compile app/agents/orchestrator.py app/agents/orchestrator_execution.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed
```

### 2026-05-30 Phase 2 partial: Orchestrator platform facts test split

已完成：

- 新增 `backend/tests/test_orchestrator_platform_facts.py`。
- 从 `backend/tests/test_orchestrator.py` 拆出 platform facts / direct-answer routing 测试：
  - meta question direct answer
  - group agents deterministic answer
  - group models deterministic answer
  - combined group agents + self model variants
  - model follow-up context
  - self model deterministic answer
  - group capabilities deterministic answer
  - platform fact classifier invalid JSON / low confidence / error fallback
- 继续复用 `backend/tests/orchestrator_fakes.py`，没有复制 fake adapter/gateway 实现。
- 行为契约未变化，测试 node id 更容易定位 platform fact router 问题。

行数变化：

- `backend/tests/test_orchestrator.py`: `2235` -> `1757`
- 新增 `backend/tests/test_orchestrator_platform_facts.py`: `491`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check tests/test_orchestrator.py tests/test_orchestrator_platform_facts.py tests/orchestrator_fakes.py app/agents/orchestrator.py app/agents/orchestrator_execution.py
# passed

uv run python -m mypy app/agents/orchestrator.py app/agents/orchestrator_execution.py app/agents/orchestrator_adapters.py app/agents/orchestrator_direct_answer.py app/agents/orchestrator_task_planning.py
# passed
```

### 2026-05-30 Phase 2 partial: Orchestrator planner test split

已完成：

- 新增 `backend/tests/test_orchestrator_planning.py`。
- 从 `backend/tests/test_orchestrator.py` 拆出 task planning / planner failure routing 测试：
  - planner allowed agents boundary
  - direct routing only matching managed agents
  - planner tool-call plan submission
  - preview/deploy-only task pruning
  - planner JSON text payload parsing
  - planner unknown agent rejection
  - planner error / empty output / invalid JSON visibility
  - invalid JSON optional direct-answer fallback
  - legacy template fallback opt-in
- 继续复用 `backend/tests/orchestrator_fakes.py`，没有复制 fake adapter/gateway 实现。
- 行为契约未变化，planner 协议和错误路由测试现在有独立 node id。

行数变化：

- `backend/tests/test_orchestrator.py`: `1757` -> `1343`
- 新增 `backend/tests/test_orchestrator_planning.py`: `427`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check tests/test_orchestrator.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/orchestrator_fakes.py
# passed
```

### 2026-05-30 Phase 2 partial: Orchestrator ReAct test split

已完成：

- 新增 `backend/tests/test_orchestrator_react.py`。
- 从 `backend/tests/test_orchestrator.py` 拆出 ReAct dynamic task graph 测试：
  - ReAct disabled 时保留 static flow
  - failure 后 add_task 修复并 finish
  - add_task agent 边界校验
  - 禁止更新已完成任务
  - skip_task 阻止后续执行
  - max_iterations 不触发 replanner
  - 新增任务接收 previous results
  - trace hidden 模式
- 继续复用 `backend/tests/orchestrator_fakes.py`，没有复制 `SequencedGateway` / decision chunk helper。
- 行为契约未变化，ReAct loop 问题现在有独立测试入口。

行数变化：

- `backend/tests/test_orchestrator.py`: `1343` -> `1054`
- 新增 `backend/tests/test_orchestrator_react.py`: `301`

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_tool_calling.py tests/test_orchestrator_memory.py -q
# 63 passed

uv run python -m ruff check tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/orchestrator_fakes.py
# passed
```

### 2026-05-30 follow-up: Config defaults and external runtime utility convergence

已完成：

- `backend/app/agents/config_fields.py` 继续从 numeric bounds 扩展为 B2 config metadata 入口：
  - `EXTERNAL_DIRECT_CHAT_DEFAULTS`
  - `ORCHESTRATOR_DEFAULTS`
- `backend/app/seeds/seed_agents.py` 不再手写重复 direct-chat 和 orchestrator 默认值，改为引用共享默认配置。
- `backend/tests/test_agent_config_validation.py` 的 OpenAPI contract 测试改为从 `AgentConfig.model_json_schema()` 反查字段，并校验静态 `shared/openapi.yaml` 的 numeric bounds 与 `NUMERIC_CONFIG_FIELDS` 一致。
- 新增 `backend/app/agents/external/runtime_utils.py`，抽出三类 external adapter 共用小工具：
  - command argv parsing
  - external error chunk creation
  - exception/runtime output sanitization and truncation
- Claude Code / Codex / OpenCode adapter 改为复用上述 helper；不改变 runtime 路由、SDK/CLI fallback、JSONL event mapping 或 SSE event shape。

边界决定：

- 不继续把 `test_orchestrator.py` 的 execution/artifact/fallback 测试拆出去。
- 不在本轮把 `backend/app/agents/orchestrator.py` 迁移为 package；当前文件已经是薄入口，继续迁移主要是路径形态变化，会牵动大量历史文档链接。
- 不在本轮重排全部 B2 spec 目录；通过 `docs/b2/README.md` 和本文件建立当前接手入口，保留既有链接稳定。
- OpenCode JSONL 主循环暂不抽成 generic parser；它包含较多 provider-specific event shape 与进程生命周期处理，后续应单独设计 contract 后再做。

已验证：

```bash
cd backend
uv run python -m pytest tests/test_agent_config_validation.py tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_external_direct_chat.py -q
# 121 passed, 1 skipped

uv run python -m ruff check app/agents/config_fields.py app/seeds/seed_agents.py app/agents/external/claude_code.py app/agents/external/codex.py app/agents/external/opencode.py app/agents/external/runtime_utils.py tests/test_agent_config_validation.py
# passed
```
### 2026-05-30 follow-up: Orchestrator package migration

已完成：

- 新增 `backend/app/agents/orchestrator/` package。
- `backend/app/agents/orchestrator.py` 迁移为 `backend/app/agents/orchestrator/adapter.py`。
- 平铺 helper 模块迁移并去掉重复前缀：
  - `orchestrator_adapters.py` -> `orchestrator/adapters.py`
  - `orchestrator_artifacts.py` -> `orchestrator/artifacts.py`
  - `orchestrator_direct_answer.py` -> `orchestrator/direct_answer.py`
  - `orchestrator_execution.py` -> `orchestrator/execution.py`
  - `orchestrator_memory_hooks.py` -> `orchestrator/memory_hooks.py`
  - `orchestrator_planner.py` -> `orchestrator/planner.py`
  - `orchestrator_platform_facts.py` -> `orchestrator/platform_facts.py`
  - `orchestrator_react.py` -> `orchestrator/react.py`
  - `orchestrator_streams.py` -> `orchestrator/streams.py`
  - `orchestrator_summary.py` -> `orchestrator/summary.py`
  - `orchestrator_task_planning.py` -> `orchestrator/task_planning.py`
  - `orchestrator_tool_loop.py` -> `orchestrator/tool_loop.py`
  - `orchestrator_tools.py` -> `orchestrator/tools.py`
  - `orchestrator_types.py` -> `orchestrator/types.py`
- `backend/app/agents/orchestrator/__init__.py` re-export `OrchestratorAdapter`，保持外部入口 `from app.agents.orchestrator import OrchestratorAdapter` 不变。
- 应用和测试 import 已更新到 package 内部路径，例如 `app.agents.orchestrator.types`。

边界决定：

- 历史 task-dispatch/spec 记录中提到旧平铺路径的内容不逐条改写，避免破坏历史执行记录语义；当前接手入口以本文件顶部状态和 `docs/b2/README.md` 为准。
- 不新增 wrapper 兼容旧 helper 路径；这些 helper 是 B2 内部模块，代码侧已全部更新。
已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py tests/test_registry.py -q
# 68 passed

uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py tests/test_stream_tool_calls.py tests/test_adapter_smoke.py tests/test_claude_code_external_adapter.py tests/test_codex_external_adapter.py tests/test_opencode_external_adapter.py tests/test_external_direct_chat.py tests/test_agent_config_validation.py tests/test_registry.py -q
# 207 passed, 1 skipped

uv run python -m ruff check app/agents app/services/orchestrator_memory.py app/api/v1/stream.py app/api/v1/stream_orchestrator_context.py tests/test_orchestrator.py tests/test_orchestrator_react.py tests/test_orchestrator_planning.py tests/test_orchestrator_platform_facts.py tests/test_orchestrator_memory.py tests/test_orchestrator_tool_calling.py tests/orchestrator_fakes.py
# passed

uv run python -m mypy app/agents app/services/orchestrator_memory.py app/schemas/agent.py
# passed

git diff --check
# passed
```
