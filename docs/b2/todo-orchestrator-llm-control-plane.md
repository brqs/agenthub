# Orchestrator LLM Control Plane TODO

> 目的：临时跟踪 Orchestrator LLM 控制面渐进增强工作，按模块推进，不按日期排序。
>
> 状态：Temporary development checklist
> 删除条件：全部模块完成、进入正式 spec、targeted tests 和至少一组 fresh live E2E 通过后删除本文档。

---

## 总体原则

当前稳定主链保持不变：

```text
LLM Planner -> static DAG executor -> sub Agent runtime -> evaluation/review/summary
```

后续增强目标：

```text
Initial Planner
-> DAG Executor Batch
-> Batch-level Re-planner
-> controlled repair / review / fallback decision
-> evaluator evidence
-> final summary
```

开发约束：

- 所有新行为先加配置开关，默认关闭，避免影响当前线上 Orchestrator。
- 每个模块独立开发、测试、验证，不做一次性大重构。
- 优先复用现有 `run_react_loop()`、`_run_parallel_tasks()`、`llm_control_points`、run detail 和 live E2E harness。
- 不改变子 Agent runtime 协议，不改变 SSE wire shape。
- 不改 OpenAPI，除非某模块明确需要新增公开配置字段。
- 任一模块失败时，能通过关闭新开关回到当前稳定行为。

E2E 分层策略：

- `targeted unit/integration tests`：每个模块默认必须跑，作为模块阶段验收主证据。
- `on-demand live E2E`：只在当前模块需要真实 HTTP/SSE 证据，或用户明确要求时运行；每次只跑该模块对应的最小场景。
- `full robustness E2E`：Module B/C/D/E 全部完成、正式 spec 沉淀、targeted tests 通过后统一运行；单模块开发阶段不跑全量、多场景鲁棒性或 nightly E2E。
- 真实 E2E 如被明确要求，报告只允许写入对应 `/tmp/agenthub_<scenario>_report.json` 与 SSE jsonl，不写入账号密码、token、env、raw stderr、完整 prompt 或 hidden reasoning。

模块执行协议：

- 主 agent 负责模块拆解、实现、最终集成、冲突处理、验收结论和用户汇报。
- 每个模块必须有清晰 ownership、允许修改的文件范围、必须运行的验证命令和禁止事项。
- 当前工作区可能已有用户或历史改动；模块实现时不能 revert 不相关改动。
- 不同模块的写入范围应尽量不重叠；如果不可避免，合并前先复审 diff。
- 每个模块完成后必须记录修改文件、测试结果、未完成项和风险，再进入下一模块。
- 任何真实账号、密码、token、env、runtime stderr、完整 prompt 或 workspace 敏感内容都不能写入代码、文档、report 或日志。
- Live E2E 遵循上方分层策略；默认模块开发阶段只跑 targeted unit / integration tests。

---

## Module A - 文档与状态对齐

目标：

- 确认正式 spec 中的状态标签一致：`Implemented`、`Partially implemented`、`Proposed`、`Future`。
- 避免把 proposed 能力写成已实现能力。

当前状态：

- `agent-architecture-patterns.spec.md` 已描述主流 Agent 架构映射。
- `llm-orchestrated-flow.spec.md` 已标记 batch-level Re-planner 为
  `Partially implemented / default off`，LLM fallback decision 为
  `Partially implemented / default off`。
- `core.spec.md` 已说明当前默认主链仍是静态 DAG executor。

执行记录：

- `Done (2026-06-18)`: 已完成一次 Module A 文档一致性检查。
- `README.md` 已链接 `agent-architecture-patterns.spec.md`。
- 正式 spec 已明确：LLM Planner 和静态 DAG executor 是 `Implemented`；ReAct replanner 是
  `Partially implemented`；parallel batch 后进入 Re-planner 是
  `Partially implemented / default off`；LLM fallback decision 和 evaluator-optimizer 统一
  repair loop 分别是 `Partially implemented / default off` 与 `Proposed`；完整
  autonomous tool-loop orchestrator 是 `Future / optional`。
- 未发现正式 spec 把 `Proposed` 能力写成已默认实现。

最小改动：

- 只维护文档一致性，不改代码。
- 新增实现时，把最终契约沉淀回正式 spec，本文档只保留开发进度。

验收标准：

- `rg "batch-level Re-planner|agent-architecture-patterns|Proposed" docs/b2/spec` 能找到正式说明。
- 正式 spec 不声称 parallel batch 后 Re-planner 已默认接入。

风险控制：

- 如果文档和代码状态不一致，以代码为准，并修正文档状态。

删除条件：

- 相关状态说明已进入正式 spec，且后续模块完成后不再需要临时跟踪。

---

## Module B - Batch-level Re-planner 接入

执行方式：

- Ownership：Orchestrator parallel DAG execution、batch-level Re-planner 接入、对应 targeted tests。
- 如果需要新增公开配置字段，先更新 spec/TODO 再改代码。

目标：

- 静态 DAG 每个 parallel batch 完成后，可选调用 ReAct Re-planner。
- 让 Orchestrator 基于真实 task result、artifact、evaluation evidence 决定下一步。

当前状态：

- 静态 DAG executor 已能并行执行 ready batch。
- ReAct replanner 已存在，但默认不会覆盖多任务并行 DAG 主链的每个 batch。
- `Done (2026-06-18)`: 已实现 `orchestrator_batch_replanner_enabled=false`
  默认关闭开关；开启后每个 parallel batch 完成后调用受限 Re-planner。
- `Review (2026-06-18)`: 已完成一次只读复审。复审发现 malformed task payload
  可能逃出容错、batch action 合同混用通用 `add_task`、单轮新增任务缺少上限、文档状态存在旧表述。
  本轮已按复审结果修正前三项，并同步正式 spec/TODO。

最小改动：

- 新增配置开关，默认关闭：
  - `orchestrator_batch_replanner_enabled=false`
- 开关开启时，在每个 parallel batch 完成后调用受限 Re-planner。
- 首版只允许动作：
  - `continue`
  - `add_repair`
  - `add_review`
  - `finish`
- Re-planner 输出必须经过后端校验后才能影响 task graph。
- Module B 首版 action 合同为 `continue / add_repair / add_review / finish`；通用
  `add_task/update_task/skip_task` 不属于 batch-level Re-planner 输入合同。

验收标准：

- 开关关闭时，现有静态 DAG 行为完全不变。
- 开关开启时，每个关键 batch 后产生 `phase="react_replanner"` 或等价 `llm_control_point`。
- 新增 repair/review task 不产生循环依赖。
- `finish` 不允许跳过仍处于 pending 的 task；更细的 required artifacts / command
  fulfillment / evaluation finish guard 归入 Module D evaluator-optimizer 统一 repair loop
  继续收敛。

已执行验证：

- `py_compile`: `execution.py`、config/schema 和新增测试文件通过。
- `ruff check`: Module B 相关后端文件通过。
- `pytest`: `test_orchestrator_parallel_takes_precedence_over_react_for_multi_task`、
  `test_orchestrator_parallel_batch_replanner_adds_repair_task`、
  `test_orchestrator_parallel_batch_replanner_failure_continues_dag` 和配置校验 targeted test 通过。
- 回归：Orchestrator parallel/react 相关 targeted tests `16 passed`；`test_agent_config_validation.py`
  `103 passed`。
- Live E2E：本模块阶段不跑全量 E2E；如需真实验证，只按需运行
  `parallel_batch_replanner_repair` 最小场景。

风险控制：

- 限制每轮新增 task 数量。
- 首版每个 batch decision 最多新增 1 个 repair/review task。
- 设置最大 Re-planner 调用次数，避免无限循环。
- Re-planner failure 时回到原 DAG 继续执行，不让整条 SSE fatal。

删除条件：

- batch-level Re-planner 行为稳定并写入 `llm-orchestrated-flow.spec.md` 和 `core.spec.md`。
  当前已写入实验开关状态；后续 fresh E2E 通过后可从 TODO 迁移为正式完成项。

---

## Module C - 受控 LLM Repair/Fallback Decision

执行方式：

- Ownership：失败后 LLM fallback/repair suggestion、白名单校验、fallback/retry targeted tests。
- 不接触 Module B 的 batch executor 主循环，除非通过稳定 helper 接口接入。

目标：

- 失败后允许 LLM 在当前群聊白名单内建议 repair/fallback agent。
- 后端继续负责最终安全裁决。

当前状态：

- fallback agent 候选、retry 条件、cooldown、max attempts 主要由确定性规则控制。
- task card / timeline 已能展示 planned/current/final agent 归因。
- `Done (2026-06-18)`: 已实现 `orchestrator_llm_fallback_decision_enabled=false`
  默认关闭开关；失败 attempt 后、下一次 `_agent_for_attempt()` 选择前会调用受控 LLM
  suggestion helper。
- `Done (2026-06-18)`: suggestion 合同固定为
  `retry_original / fallback / add_repair / stop`；`add_repair` 在 Module C 只映射为当前
  task 的一次受控 retry/fallback，不新增 DAG task。
- `Done (2026-06-18)`: 已新增内部 run detail 事件 `task_fallback_llm_decision`，并继续复用
  `phase="react_replanner"` 记录 `llm_control_point` 安全摘要。

最小改动：

- 新增配置开关，默认关闭：
  - `orchestrator_llm_fallback_decision_enabled=false`
- 首版只让 LLM 产出 suggestion，不直接执行；后端只允许薄 override 当前 retry 选择。
- suggestion 合同固定为：
  - `action`: `retry_original | fallback | add_repair | stop`
  - `agent_id`: `string | null`
  - `reason`: `string`
  - `summary`: `string | optional`
- 后端按当前群聊可运行 Agent、cooldown、max attempts、tool allowlist 校验。
- 非法 JSON、空输出、非法 action、群聊外 agent、模型异常或 cooldown/hard-failure 冲突时，
  只能回退 deterministic fallback，不能打断 DAG。

验收标准：

- 非法 agent suggestion 被丢弃或 remap，不调用群聊外 Agent。
- report 记录模型建议和后端实际选择，但不保存完整 prompt。
- 关闭开关时沿用现有 deterministic fallback。
- Live E2E：本模块阶段不跑全量 E2E；如需真实验证，只按需运行
  `fallback_llm_decision_whitelist` 最小场景。

已执行验证：

- `py_compile`: `fallback_llm.py`、`attempts.py`、`execution.py`、fallback LLM E2E
  runner/test 文件通过。
- `ruff check`: Module C 相关后端与 E2E 文件通过。
- `pytest`: `backend/tests/test_orchestrator.py -k 'llm_fallback_decision or batch_replanner'`
  通过。
- `pytest`: `backend/tests/test_agent_config_validation.py -k 'batch_replanner or llm_fallback_decision'`
  通过。
- Live E2E：本轮只新增并校验 `fallback_llm_decision_whitelist` 场景、默认 report/SSE 路径和
  evaluator；没有跑真实 live E2E，也没有跑 full robustness E2E。

风险控制：

- LLM 不能扩大 fallback 候选集合。
- LLM 不能突破 `max_task_attempts`。
- LLM suggestion failure 不影响现有 fallback 流程。

删除条件：

- LLM fallback decision 成为正式契约，或明确决定保留 deterministic fallback 为唯一生产策略。

---

## Module D - Evaluator-Optimizer Repair Loop 统一

执行方式：

- Ownership：document/code/browser evaluator failure observation 标准化、repair decision 接入、相关 tests。
- 保持现有 evaluator deterministic fallback 可用；不一次性迁移所有 evaluator。

目标：

- evaluation / browser / deploy / review 失败后统一进入 Re-planner 决策，而不是散落在多处规则里。

当前状态：

- Evaluation / Reflection、review thread、quality repair loop 已部分实现。
- 不同失败来源的 repair 触发点仍比较分散。

最小改动：

- 首版只接入高价值场景：
  - document quality failure
  - code static quality failure
  - browser preview quality failure
- 将 evaluator failure 汇总成标准 observation，交给 Re-planner。
- Re-planner 只能建议最小 repair task 或 finish-with-failure。

验收标准：

- report 保留 first failure evidence、repair decision、repair attempt、final pass evidence。
- 修复后重新验证，不用旧 snapshot 宣称通过。
- 不把 reviewer/evaluator 的失败误归因为子 Agent runtime failure。
- Live E2E：本模块阶段不跑全量 E2E；如需真实验证，只按需运行
  `evaluator_optimizer_repair_loop` 最小场景。

风险控制：

- 每类 evaluator 先保留原 deterministic fallback。
- 统一 observation 时截断敏感输出和长日志。
- Repair loop 设置轮次上限。

删除条件：

- 核心 evaluator repair flow 进入正式 spec，并由 fresh E2E 证明。

---

## Module E - Observability 与 Live E2E Evidence

执行方式：

- Ownership：E2E scenario registry/report evaluator、`llm_control_points` report 聚合、fresh report 验收脚本。
- 默认不使用真实账号跑 live E2E；只有用户明确要求时才执行真实 HTTP/SSE。
- Module E 只准备/刷新 report evaluator 和场景定义，不默认执行 full matrix、鲁棒性或 nightly E2E。

目标：

- 每个新增 LLM 控制点都能在 run detail / report 中被安全验证。

当前状态：

- `llm_control_points` 已覆盖 planner、react_replanner、dialogue_controller、tool_loop、response_polish。
- 旧 report 可作为历史功能证据，但不能证明新控制点。

最小改动：

- 新增或刷新 live E2E 场景：
  - `parallel_batch_replanner_repair`
  - `fallback_llm_decision_whitelist`
  - `evaluator_optimizer_repair_loop`
- report 聚合：
  - planner evidence
  - batch replanner evidence
  - LLM suggestion vs backend final decision
  - repair trace
  - artifact/evaluation/browser evidence

验收标准：

- 场景和 report evaluator 可被按需执行；只有用户明确要求运行时，才生成对应 fresh report 和 SSE。
- report 不包含账号密码、token、env、认证文件、raw stderr、完整 prompt 或 hidden reasoning。
- 群聊场景不得调用群聊外 Agent。
- full matrix 与鲁棒性 E2E 等 Module B/C/D/E 全部完成后统一执行。

风险控制：

- E2E 失败先分类为产品 bug、断言过严或环境 blocker。
- 只根据 report/SSE/browser evidence 修复。

删除条件：

- 新场景通过并写入正式 E2E report spec。

---

## Module F - 删除 TODO 文档

执行方式：

- Ownership：确认 B/C/D/E 已沉淀到正式 spec、删除临时 TODO、跑文档引用检查。
- 仅在能力完成、targeted tests 通过且至少一组 fresh live E2E 通过后执行。

目标：

- 确保本文档不会长期漂移成第二套 spec。

删除条件：

- Module B/C/D/E 的最终行为已沉淀到正式 spec。
- Targeted tests 通过。
- 至少一组 live E2E fresh report 通过。
- 全量和鲁棒性 E2E 已在 Module B/C/D/E 全部完成后统一执行并完成结果归档。
- 本文档所有未完成项已关闭、迁移或明确废弃。

删除步骤：

- 删除 `docs/b2/todo-orchestrator-llm-control-plane.md`。
- 确认正式 spec 中保留最终状态、配置、验收口径和 E2E 证据。
- `rg "todo-orchestrator-llm-control-plane" docs` 不再返回引用。
