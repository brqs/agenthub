# Orchestrator Agent Review Thread Spec

> 状态：Implemented MVP + Live E2E Passed
>
> 最后更新：2026-06-13

---

## 1. 目标

让 Orchestrator 的多 Agent 协作从“主 Agent 转派和汇总”进一步具备群聊协作感：一个 Agent 产出关键 artifact 后，另一个 Agent 可以接手 review / 质疑 / handoff confirmation；如果 review 明确失败或需要修复，Orchestrator 会在当前群聊成员中安排 repair task。

---

## 2. 任务类型

`SubTask` 支持三类协作任务：

- `implementation`：默认任务类型，负责生成或修改产物。
- `review`：检查前序 Agent 的产物、diff/file changes、tool output、evaluation 或 deployment status。
- `repair`：根据 review outcome 修复前序产物。

新增字段：

- `task_type`：`implementation | review | repair`，默认 `implementation`。
- `review_of`：review / repair 指向的 task id 列表。
- `handoff_reason`：Orchestrator 安排 handoff 的原因。
- `TaskAttempt.review_outcome`：`passed | failed | needs_repair | unknown`。

---

## 3. 自动 Review

当 config 开启 `orchestrator_agent_review_enabled=true` 或 `agent_to_agent_review_enabled=true` 时，Orchestrator 会对关键 implementation task 自动追加 review task。

触发条件：

- task 是 `implementation`。
- task 有 `expected_output`，或 title / instruction 命中 artifact 生成语义。
- 当前群聊中存在不同于实现 Agent 的其他 Agent。
- 该 task 尚未被显式 review task 覆盖。

review task 指令必须要求 reviewer：

- 使用注入的 `Previous sub-agent results`。
- 引用具体 artifact path、diff/file-change summary、tool result、evaluation output 或 deployment status。
- 首行返回 `review_outcome: passed`、`review_outcome: failed` 或 `review_outcome: needs_repair`。
- 给出 handoff confirmation；如需修复，明确 repair instruction。

---

## 4. Repair Handoff

顺序静态执行路径和并行 DAG 执行路径中，如果 review task 成功运行但文本 outcome 是 `failed` 或 `needs_repair`，Orchestrator 会动态追加 repair task：

- repair agent 优先使用被 review 的原 implementation agent。
- repair task 只从当前 task group 的 Agent 中选择，不引入新 Agent。
- repair task 依赖 review task，并通过上下文读取 review finding。
- repair task 继承原 implementation task 的 `expected_output`。
- 并行 DAG 路径会在当前 batch 中识别 review outcome，并将 repair task 加入 pending DAG 队列。
- 同一个 review task 只允许生成一个动态 repair task，避免重复修复。

---

## 5. Stream / Summary / Memory

- `agent_switch` 会显示 review / repair task title，并沿用真实 sub-agent `agent_id`。
- planning text 会对 `review` / `repair` task 显示任务类型标签。
- summary 会展示 `review_of`、`handoff` 和 `review outcome`。
- memory event 会记录 `agent_review_completed` 与 `agent_review_repair_scheduled`。
- run detail / memory payload 会暴露 `task_type`、`review_of`、`handoff_reason` 和 attempt 级 `review_outcome`，供 E2E 和前端稳定读取。

---

## 6. Timeline Ordering Contract

Review / Handoff Timeline 必须表达真实流转顺序，而不是内部数组或 priority 的偶然顺序：

- `implementation` / 被 review 的任务先展示。
- `review` 必须排在其 `review_of` 和 `depends_on` 指向的任务之后。
- `repair` 必须排在触发它的 `review` / failed task 之后。
- 同一层并行任务可按 attempt 创建时间排序；时间缺失时再用 priority 作为稳定兜底。
- 如果 run detail 中存在 fallback，timeline 展示的 agent 应使用最终执行 / latest attempt agent；
  planned/current/final agent 差异保留在 run detail 证据中，不应让用户误以为原计划 Agent 完成了任务。

该契约对应前端模型 `reviewThreadModel`：构建 timeline 时同时考虑 `depends_on` 与 `review_of`，
避免出现 Review / Handoff Timeline 倒序展示。

---

## 7. 当前边界

已完成：

- 通用 task 类型字段和 planner schema。
- 自动 review task 扩展。
- review outcome 解析。
- failed / needs_repair review 的顺序 repair handoff。
- failed / needs_repair review 的并行 DAG 动态 repair 队列化。
- summary / context / memory event / run detail API 暴露。
- 防重复 repair 调度。
- 单元测试覆盖 passed review、needs_repair repair、并行 repair 调度和 metadata 暴露。
- 公网 live E2E 覆盖 implementation -> review(`needs_repair`) -> repair -> final summary。

验收证据：

- scenario: `p1_review_thread_repair`
- report: `/tmp/agenthub_p1_review_thread_report.json`
- sse: `/tmp/agenthub_p1_review_thread_sse.jsonl`
- conversation_id: `5d0373e4-3801-4242-b812-f03ddacd3fb1`
- agent_message_id: `b694d579-cb62-4dbd-83c6-8434a6e49cf8`
- passed: `true`

后续增强：

- 前端独立 review thread / handoff timeline UI。

前端交接：

- [Agent-to-Agent Review Thread 前端交接说明](../../../frontend/agent-review-thread-handoff.md)
