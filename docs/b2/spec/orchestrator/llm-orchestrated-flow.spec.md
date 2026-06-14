# Orchestrator LLM-Driven Flow Spec

> 定义 Orchestrator 的 LLM-first 控制面：复杂任务优先由大模型完成意图理解、任务拆解、Agent 分工、依赖规划、过程重规划、repair/review 决策和最终总结；确定性代码保留为安全边界、平台工具执行、显式指令和失败 fallback。
>
> 版本：v0.2
> 最后更新：2026-06-14

---

## 1. 目标

AgentHub 的鲁棒性不应依赖“模板可识别 prompt”或固定脚本场景。对于真实群聊里的复杂任务，Orchestrator 默认应把任务流转交给 LLM 控制点判断：

- Planner：理解用户目标，生成 task graph、Agent 分工、依赖与产物要求。
- ReAct replanner：每个 task 完成或失败后判断是否继续、repair、review、补任务、跳过或收束。
- Dialogue controller：纯对话/辩论场景决定下一轮发言者、是否继续和最终总结。
- Tool loop：在安全工具白名单内，由模型决定读取、预览、部署、浏览器验证等平台动作顺序。
- Response polish：基于结构化事实组织最终回答，不暴露 raw trace 或隐藏推理。

确定性逻辑不删除，但必须退回到护栏位置：

- 显式 `config.tasks` 是 automation / E2E / 内部任务的最高优先级。
- 平台事实问答、纯 direct answer、自建 Agent 创建 tool 等非规划入口仍可短路。
- Legacy template 只作为兼容 fallback，不能抢占复杂任务主规划路径。
- 平台工具执行仍由后端安全实现，LLM 只能在允许范围内决定是否需要调用。

---

## 2. 控制模式

新增配置：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `orchestrator_control_mode` | `"auto" | "llm_first"` | 内置 Orchestrator 默认 `llm_first` | `llm_first` 下复杂任务优先进入 LLM 控制面；`auto` 保留旧兼容顺序。 |

行为：

- `llm_first`：
  - `config.tasks`、平台事实/direct answer/custom-agent tool 等显式非规划入口保留最高优先级。
  - 复杂 task intent 在 direct gate 之后优先调用 LLM Planner。
  - Planner 输出经后端校验、群聊白名单过滤、依赖规范化、循环依赖拆除、并行/自审重平衡后执行。
  - Planner 失败时，只有显式允许 legacy fallback 才使用 template；否则向上暴露可诊断错误或进入配置的 fallback adapter。
- `auto`：
  - 保留旧版本兼容行为，包括部分 deterministic template 在 Planner 前命中。
  - 用于低成本模式、旧测试和临时回退。

---

## 3. LLM 控制点

Run detail 通过 memory event 暴露安全摘要 `llm_control_points`。每个控制点只记录可公开诊断信息：

```json
{
  "phase": "planner",
  "model_backend": "deepseek",
  "status": "succeeded",
  "used_llm": true,
  "fallback_reason": null,
  "decision_summary": "Generated 4 tasks for codex-helper, claude-code, and opencode-helper."
}
```

字段规则：

- `phase`：至少覆盖 `clarification`、`planner`、`react_replanner`、`dialogue_controller`、`tool_loop`、`response_polish`。
- `model_backend`：只记录 backend 名称或 `test_gateway`，不记录 token、API key、env、命令、stderr。
- `status`：`succeeded`、`failed`、`skipped`、`fallback`。
- `used_llm`：该阶段是否真实尝试调用 LLM/gateway。
- `fallback_reason`：失败或跳过原因的短摘要。
- `decision_summary`：结果摘要，不保存完整 prompt 或 hidden reasoning。

`llm_control_points` 可以由 E2E report 从 `event_type="llm_control_point"` 的 run events 聚合生成；不需要新增数据库表。

---

## 4. 任务规划顺序

`llm_first` 模式下规划顺序：

1. 解析显式 `config.tasks`。
2. 处理平台事实、direct answer、previous-output follow-up、clarification 和 custom-agent tool 等非任务规划入口。
3. 如果有 runnable group agents 且请求有 task intent，调用 LLM Planner。
4. 对 Planner 输出做安全校验：
   - 只允许当前群聊或显式 E2E 白名单中的 Agent。
   - 保留用户明确产物和验收要求。
   - 过滤 preview/deploy/port service 这类不应交给子 Agent 的任务。
   - 校验 `depends_on` 指向已知 task，并移除 self-dependency。
   - 拆除 review/repair 与 implementation/planning 之间的循环依赖；review 依赖被审阅产物，普通 implementation/planning 不应依赖后续 review。
   - 如果任意剩余依赖边仍会形成 cycle，后端丢弃该边，保证 executor 能继续选择 runnable task。
   - 对“两个/多个 Agent 并行”请求做 implementation 重平衡。
   - 避免自审。
5. Planner 失败且 `planner_fallback_to_template=true` 时，才进入 legacy template。
6. 都不可用时返回可见错误或配置的 fallback adapter。

`auto` 模式保留旧顺序，便于灰度和兼容测试。

---

## 5. 过程重规划

ReAct replanner 是 LLM-first 的第二控制点，职责不是重新执行 Planner，而是在已有 graph 和真实 task result 基础上判断下一步：

- 成功：继续后续依赖任务，或在所有验收满足时 `finish`。
- 失败：选择 repair、fallback、skip 或补充验证任务。
- Review：根据产物、diff、evaluation/reflection 结果决定是否需要独立 review 或二次修复。
- Deployment / Browser Verify：平台工具失败时生成最小修复任务，修复后重新验证。

静态 DAG executor 仍可用于多任务并行执行；当使用静态并行时，ReAct 可以作为并行阶段后的后续控制点，而不是完全替代并行调度。

---

## 6. 安全边界

LLM-first 不等于 LLM 任意执行：

- LLM 不直接执行 shell、读写数据库、启动端口服务或绕过工具白名单。
- 子 Agent 调度必须经过 `available_agents` / `managed_agent_ids` / fallback whitelist。
- 平台 preview、browser verify、package、deploy 由后端 service/tool 执行。
- 不保存完整 prompt、密钥、token、认证文件、环境变量、runtime stderr。
- 用户自建 Agent 不自动继承内置 planning profile；只暴露自己的安全 profile。
- Planner 只生成 DAG 草案；并行 batch 由后端基于 normalized DAG、task state 和 concurrency limit 确定性选择，不由模型逐步决定。

---

## 7. E2E 验收口径

鲁棒性 E2E 不应只检查 `planner_used_llm=true`。新的验收口径是：

- 每个复杂任务场景至少包含一个关键 LLM 控制点。
- 复杂 artifact/task 场景必须包含 `phase="planner"` 且 `used_llm=true`。
- Repair 场景必须包含 `react_replanner` 或等价 LLM repair decision。
- 对话场景必须包含 `dialogue_controller` 或 Planner 生成的 `dialogue_turn` 证据。
- Tool/deploy/browser 场景应包含 tool loop 或平台质量门事件；平台工具仍由后端执行。
- Report 中保留 `task_graph`、`repair_trace`、`artifact_list`、`browser_report` 和 `llm_control_points`。

本 spec 只定义脚本和报告要求；真实 HTTP/SSE E2E 由测试执行者单独触发。

---

## 8. 当前实现状态

截至 2026-06-13，代码侧已接入以下 LLM control point 观测：

- `planner`：LLM Planner 成功、失败、fallback 都会记录安全摘要。
- `react_replanner`：task 完成 / 失败后的 repair、skip、finish 等决策会记录安全摘要。
- `dialogue_controller`：纯对话 / 辩论的续轮决策和最终 judgement 会记录安全摘要。
- `tool_loop`：Orchestrator tool loop 的模型工具决策会记录安全摘要。
- `response_polish`：最终回答润色模型的成功、失败和 fallback 会记录安全摘要。

当前约束：

- `clarification` 暂不强制改造成 LLM 调用；只有真实 LLM clarification 路径存在并调用时才记录。
- `llm_control_points` 只保存 `phase`、`model_backend`、`status`、`used_llm`、
  `fallback_reason` 和 `decision_summary`，不保存完整 prompt、token、stderr、env、认证文件或 workspace 敏感内容。
- 2026-06-11 的 8 个鲁棒性 E2E report 是历史功能证据，生成时还没有完整
  `llm_control_points` 硬验收；LLM-first 验收必须使用重跑后的 fresh report。
- 新增纯对话场景 `dialogue_ai_benefits_risks_llm_moderated` 已进入 E2E harness，待真实
  HTTP/SSE 执行后再写入 passed evidence。
