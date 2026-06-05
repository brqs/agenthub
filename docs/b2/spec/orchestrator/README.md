# Orchestrator Spec Package

> 目的：作为 Orchestrator 相关 spec 的包级入口，区分当前契约和当前验证报告。
>
> 状态：Current package index
> 最后更新：2026-06-05

---

## 1. Package 结构

| 文档 | 状态 | 作用 |
|---|---|---|
| [core.spec.md](core.spec.md) | Current contract | Orchestrator 主行为契约：调度、DAG 并行、summary、失败处理、preview 边界 |
| [task-planning.spec.md](task-planning.spec.md) | Current contract | direct answer、direct mention、LLM planner、legacy fallback、DAG 依赖语义 |
| [tool-calling.spec.md](tool-calling.spec.md) | Current contract | `dispatch_agent`、workspace tools、preview/verify、自建 Agent 与 deployment platform tools |
| [memory-context.spec.md](memory-context.spec.md) | Current contract | Orchestrator structured memory 与上下文注入设计 |
| [workspace-conflict.spec.md](workspace-conflict.spec.md) | Current contract | Workspace snapshot、file changes、同一 run 内冲突检测 |
| [message-attribution.spec.md](message-attribution.spec.md) | Current contract | Orchestrator 合流 stream 中每个 content/tool chunk 的真实 Agent 归属 |
| [agent-review-thread.spec.md](agent-review-thread.spec.md) | Implemented MVP + Live E2E Passed | Agent-to-Agent review、handoff、repair thread |
| [native-deployment.execution.spec.md](native-deployment.execution.spec.md) | Implemented hardening MVP | Orchestrator 原生部署 tool、container E2E、deployment repair/redeploy |
| [live-e2e-report.spec.md](live-e2e-report.spec.md) | Implemented report | 真实部署链路、deployment repair/redeploy、自建 Agent 工具白名单 E2E 证据 |
| [evaluation-reflection.spec.md](evaluation-reflection.spec.md) | Current contract | 通用 Evaluation / Reflection：“生成 -> 验证 -> 修复 -> 再验证”闭环 |
| [markdown-preservation-feedback.spec.md](markdown-preservation-feedback.spec.md) | Backend MVP implemented | 用户可见 Orchestrator trace / observation / final summary 展示边界 |

---

## 2. 阅读顺序

修改 Orchestrator 主执行流：

1. [core.spec.md](core.spec.md)
2. [task-planning.spec.md](task-planning.spec.md)
3. [workspace-conflict.spec.md](workspace-conflict.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

修改 Orchestrator tools：

1. [tool-calling.spec.md](tool-calling.spec.md)
2. [core.spec.md](core.spec.md)
3. [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

修改 Orchestrator memory：

1. [memory-context.spec.md](memory-context.spec.md)
2. [core.spec.md](core.spec.md)

修改 Orchestrator 合流消息归属：

1. [message-attribution.spec.md](message-attribution.spec.md)
2. [core.spec.md](core.spec.md)
3. [../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)

修改 Orchestrator 用户可见回复：

1. [markdown-preservation-feedback.spec.md](markdown-preservation-feedback.spec.md)
2. [message-attribution.spec.md](message-attribution.spec.md)
3. [memory-context.spec.md](memory-context.spec.md)

修改 Orchestrator 原生部署：

1. [native-deployment.execution.spec.md](native-deployment.execution.spec.md)
2. [tool-calling.spec.md](tool-calling.spec.md)
3. [../deployment-release-backend.execution.spec.md](../deployment-release-backend.execution.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

---

## 3. 当前边界

- 当前默认主链是 `llm_planning=true` + 静态 DAG 并行 executor。
- 通用 Evaluation / Reflection Phase 2 MVP 已实现；网页 preview/browser verify、Workflow validation + allowlist dry-run、PPT outline、受控 test runner 和 deployment health 已接入 evaluator / health gate 语义，workflow runtime 与 deployment repair/redeploy live E2E 已通过。
- DAG 并行是 Orchestrator execution 能力，不是 platform tool。
- Preview / browser verify / create custom agent / deployment 是 Orchestrator 可调用的平台 tool，但实际执行由平台 service 完成。
- 自建 Agent 的显式 `allowed_tools` 已进入 tool schema；builtin native/MCP 最小权限 MVP 已实现并通过 live E2E，external runtime 权限映射仍属后续 hardening。
- Agent-to-Agent review thread MVP 已实现：关键 implementation task 可自动 handoff 给其他 Agent review，并在 failed / needs_repair outcome 下顺序或并行追加 repair task；前端 handoff timeline 交接见 [../../../frontend/agent-review-thread-handoff.md](../../../frontend/agent-review-thread-handoff.md)。
- Workspace conflict detection 当前只记录和展示，不做自动 merge、rollback 或文件级 lock。
- Orchestrator 最终用户可见 text block 已通过 response presentation 层生成：raw execution summary 继续写入 memory / run detail，聊天最终回复只暴露自然、简洁、面向结果的摘要。
- ReAct trace 默认不再进入普通聊天流；调试证据仍记录在 run detail / memory event。需要调试可显式开启 `react_trace_visible=true`。
- 可选 LLM response polish 只接收结构化事实，失败、空输出或包含内部 trace 词时回退 deterministic summary。

---

## 4. 对外依赖

- Adapter / StreamChunk 契约：[../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)
- External runtime 生命周期：[../external-runtime-lifecycle.spec.md](../external-runtime-lifecycle.spec.md)
- Workspace artifact / preview：[../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
- B2 PDF gap：[../b2-pdf-gap-todo.spec.md](../b2-pdf-gap-todo.spec.md)

---

## 5. Behavior-preserving Refactor 记录

2026-06-04 的 Orchestrator package 瘦身为内部维护性重构：

- 保持 `OrchestratorAdapter.stream()`、`StreamChunk` 顺序、`block_index` remap、`agent_id` attribution、planner task schema、evaluator payload 语义不变。
- `execution.py` 仅拆出 attempt 配置/message、review repair、artifact file block/manifest、evaluation/workflow dry-run、workspace conflict、stream event accumulation helper。
- `task_planning.py` 保留 `resolve_tasks()` 主入口，拆出 direct routing、legacy template derivation、agent review task expansion。
- `evaluation.py` 保留 `evaluate_attempt()` 与 payload/reflection helper 的导入路径，拆出 evaluator types 与 artifact/test-runner evaluator 实现。
- `quality.py` 保留 browser quality gate 主流程，拆出 preview/deployment tool chunk、repair instruction/entry discovery、deployment health/release helper。
- 本轮不新增功能，不改 public API、数据库 migration、seed、OpenAPI 或前端代码；不执行公网 E2E。

2026-06-05 在不改变上述边界的前提下进一步整理目录：

- 根目录只保留 package 入口、稳定导入契约与主要 orchestration facade：`adapter.py`、`artifacts.py`、`evaluation.py`、`execution.py`、`planner.py`、`quality.py`、`task_planning.py`、`tools.py`、`types.py`、`workspace_changes.py`。
- routing、execution helper、planning templates、evaluation evaluator、quality、tools/tool loop、ReAct、memory 与 stream helper 按功能收进 `_internal/`。
- planning templates 按 delivery、workspace conflict、legacy fallback 分组；evaluation evaluator 按 document/static、workflow、media/archive、runner/judge 与安全文件访问分组。
- `tools.py` 保留稳定 facade，catalog、workspace executor、dispatch、stream/result construction 与 loop 分开；ReAct 按 runtime、decision/parser、task graph mutation 分开。
- 无仓库调用方的旧根模块不保留转发 facade，避免根目录再次变成平铺 helper 集合。
- `_internal` 下模块不是 public API；外部调用继续通过根目录 facade。
- 本地 Orchestrator targeted pytest：`176 passed`；Ruff、Mypy、`git diff --check` passed。
- 本轮未执行公网 E2E，未改数据库、OpenAPI、seed/default config 或前端代码。

同日完成 Memory / Capability Profile service 的 behavior-preserving 可读性重构：

- `backend/app/services/orchestrator_memory.py` 保留为稳定兼容门面，公共导入路径不变。
- 实现按 store、queries、capability v1/v2、preferences、context、run reader、serialization 和 types 收进 `backend/app/services/_orchestrator_memory/`。
- v1/v2 共用实际参与 Agent、artifact、failure insight 与 confidence 规则；查询、聚合和格式化职责分离。
- 本轮不是 Capability Profile v3；不改统计、score、decay、taxonomy、preference、section 文本/顺序/预算、API wire shape、数据库或 planner 行为。
- Memory targeted pytest `102 passed`；Ruff、Mypy、`git diff --check` passed。
- 未执行公网 E2E；历史 Capability Profile acceptance 不做适配。

## 6. 用户可见 Response Presentation 记录

2026-06-05 完成 Orchestrator 用户可见消息整理：

- 新增内部 response presentation 层，输入 task graph、task results、artifact / preview / deployment / evaluation / review / workflow 状态和 raw summary，输出最终聊天 text。
- 最终聊天 text 禁止输出 `ReAct step`、`Observation:`、`Action:`、`Tools:`、`result ok`、`call_`、planner/debug prompt、raw tool result 和长日志。
- `summary_text()` 仍保留 raw execution summary，用于 Orchestrator structured memory、run detail 和既有调试证据；ContentBlock 类型不变。
- 新增配置 `orchestrator_response_polish_enabled`、`orchestrator_response_polish_model_backend`、`orchestrator_response_polish_max_tokens`，默认使用 answer/planner/model backend 做最终回复润色，并带 deterministic fallback。
- seed/default config 将 `react_trace_visible` 默认改为 `false`；需要显示 trace 的测试或调试场景可显式开启。
- 已执行 `seed_agents`，本机与公网 `/health` 正常；公网轻量 smoke 验证普通问答和轻量任务最终可见 text 不含内部 trace。
- 本轮未修改数据库 migration 或前端代码；未执行全功能公网 E2E。

复审回修：

- 完整后端 pytest 中旧 planning 文案断言已同步为新的用户可见 step/title 文案。
- Response presentation 将 `TaskState.PENDING` 计入 `needs_attention`，ReAct 达到 `max_iterations` 且仍有 pending task 时最终回复为 partial/failed，不再误报 “Done”。
- 完整后端 pytest `650 passed, 7 skipped`；Ruff、Mypy、`git diff --check` passed。后端已重启，PID `687089`；本机与公网 `/health` 正常；轻量公网 smoke passed。
