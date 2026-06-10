# Orchestrator Task Planning Spec

## 2026-06-05 Update: Conversation-Scoped Planning

In group conversations, `available_agents` is the authoritative dispatch
boundary. If the field is present, even as an empty list, planner, ReAct,
fallback, tools, and execution code must not fall back to global
`managed_agent_ids` or seed defaults. An empty authoritative list means the
conversation has no runnable implementation agent, and artifact/build requests
must terminate with a clear retryable error instead of silently calling an agent
outside the group.

For internal static tasks and live E2E, `available_agents_authoritative=false`
is an explicit escape hatch. In that mode execution/fallback may use
`managed_agent_ids` and `task_fallback_agent_ids`, while the planner still sees
the current `available_agents` profile list.

Artifact/build/design requests must not use direct-answer fallback after planner
failure. They must either create real tasks for runnable conversation members or
return an explicit error. Direct answers that discuss recent task state must use
same-conversation structured Orchestrator memory before model-generated prose.

## 2026-06-07 Update: Built-in Planning Profiles And Clarification Gate MVP

Planner `available_agents` entries include richer scheduling signals:
`planning_profile`, `planning_strengths`, `planning_weaknesses`, and
`preferred_task_types`. Sensitive runtime details such as `api_key`, `token`,
`env`, `secret`, `command`, `args`, and `sdk_options` must not be exposed to the
planner.

The default built-in planning roles are:

- `codex-helper`: architecture, repository analysis, overall planning, final
  review, escalation, and difficult bug fixing. It should not absorb all
  routine parallel implementation work.
- `claude-code`: implementation, file editing, repair, review, and workspace
  changes. It is one of the two primary parallel implementation agents.
- `opencode-helper`: CLI-oriented implementation, verification, repair, and
  parallel execution. It is the second primary implementation/verification
  agent.

These defaults apply only to built-in agents. Custom agents do not inherit a
built-in profile from provider name; they are described by their own
`config.planning_profile` when present, otherwise by capabilities and a system
prompt summary.

Before artifact/build/code/design requests enter LLM planner or sub-agent
dispatch, Orchestrator runs a clarification gate. The gate determines
whether the request has enough product, artifact, constraint, and acceptance
detail to begin implementation. If a missing decision would materially change
the result, Orchestrator should ask exactly one high-value question with a
recommended default, end the message as `done`, and wait for the user's next
answer. It must not create `task_card`, emit `agent_switch`, call sub-agents, or
write workspace files while waiting for clarification.

The implemented MVP contract is [clarification-gate.spec.md](clarification-gate.spec.md).

## 2026-06-07 Update: Explicit Multi-Agent Rebalancing

用户明确要求“两个智能体”“多个智能体”“双智能体”“交由两个智能体”“并行开发”“并行执行”或“分工协作”时，planner 输出不能退化成同一个执行 Agent 吞掉全部 implementation tasks。

如果 LLM planner 产出的 task graph 只使用一个非 Orchestrator Agent，而当前 group 中至少有两个可运行 Agent，后端会在不改 task title / instruction 文案的前提下重平衡 implementation tasks。内置排序仍尊重当前可用性和显式 mention；`codex-helper` 可作为复杂任务架构/方案首选，但不能覆盖用户要求的 Claude / OpenCode 并行执行。

Review task 还必须避开自审：如果 planner 把 review 分配给被 review 的 implementation Agent，后端会改派给其他可用 Agent。该规则是通用 task-planning 修正，不针对前端 demo 或固定主题模板。

## 2026-06-08 Update: Pure Dialogue / Debate Tasks

Orchestrator 必须区分“生成文件/构建产物”和“纯对话群聊”：

- 命中 `辩论`、`对话场景`、`群组内`、`角色扮演`、`圆桌讨论`，并同时命中
  `不需要生成文件`、`不要生成文件`、`直接以对话形式输出` 等 no-artifact marker 时，规划层应生成
  `task_type="conversation"` 或等价内部类型。
- Conversation task 的 `expected_output` 必须为空或只描述自然语言发言，不得要求 workspace artifact。
- Legacy template fallback 不得为纯对话任务生成 `Analyze request / Produce solution` 这类 artifact 模板；应生成两个或多个独立发言任务，例如正方、反方、主持总结。
- 如果 LLM planner 把明确要求多个智能体的对话任务压成单个 conversation task，后端会拆成至少两个可用 Agent 的独立 conversation tasks。
- 执行层对 conversation task 不做 artifact missing 检查；子 Agent 文本作为成员发言常显展示，Orchestrator 只做主持/总结。
- Artifact path 提取必须跳过负向约束句，例如 `Do not create server.js/package.json`、`不要创建 ...`、`不需要生成文件`，不能把这些文件名反向当成 required artifacts。

## 2026-06-09 Update: Agent-to-Agent Turn-Taking

`conversation` task 表示多个 Agent 各自完成独立发言；`dialogue_turn` 表示 Orchestrator
托管的一轮接力发言。二者必须区分：

- 命中 `轮流`、`一人一句`、`接力`、`展开辩论`、`回应对方`、`反驳对方`、`panel`
  等 marker 时，应优先生成 `dialogue_turn` 轮次计划。
- 适用场景包括辩论、圆桌、角色扮演、头脑风暴、观点对比、设计评审、代码 review panel、
  数据分析 panel 和需求澄清 panel。
- 用户直接点名某个 Agent 作为第一位发言者时，如果请求同时要求其他 Agent 后续回应，
  后端仍应进入 Orchestrator 托管 turn-taking，而不是只让被点名 Agent 单独回答。
- `@agent-id` 出现在子 Agent 输出中只是 handoff hint；实际下一轮发言者由 Orchestrator 的
  `DialoguePlan.turn_order` 决定。
- 普通 `@agent 你是什么模型`、单 Agent 私聊、artifact/code/deploy 请求不应被
  turn-taking 抢占，除非用户明确要求多 Agent 轮流讨论或 panel 评审。

详细契约见 [agent-turn-taking.spec.md](agent-turn-taking.spec.md)。

> 定义 Orchestrator 的任务规划、任务分配和 planner 降级规则。子任务执行流转、事件聚合和失败状态汇总见 [core.spec.md](core.spec.md)。
>
> 版本：v1.3
> 最后更新：2026-06-08

---

## 1. 范围

本文件只覆盖 Orchestrator 从用户请求到 `list[SubTask]` 的规划过程：

- direct answer 短路判定。
- clarification gate 判定。
- 显式 `config.tasks` 解析。
- 直接多 Agent mention 路由。
- LLM planner 调用、输出解析和校验。
- preview/deploy/port 服务任务过滤。
- planner 失败后的 direct answer、template、fallback adapter、fatal error 降级顺序。

本文件不覆盖：

- 子 Agent stream 调度。
- `block_index` 和 `tool_call.call_id` 重映射。
- 子 Agent `heartbeat` / `error` 事件处理。
- execution summary 输出。
- workspace artifact 成功判定。

---

## 2. 输入来源

规划层读取：

| 输入 | 来源 | 说明 |
|---|---|---|
| `messages` | `BaseAgentAdapter.stream()` | 只把最新 user message 作为 active request。 |
| `system_prompt` | `BaseAgentAdapter.stream()` | 合并进 planner/direct answer system prompt。 |
| `config.tasks` | runtime config | 显式任务计划，优先级最高。 |
| `config.available_agents` | runtime config | planner 可用 Agent 描述，优先于 managed ids。 |
| `config.managed_agent_ids` | registry/default config | Orchestrator 管理的子 Agent 白名单。 |
| `config.default_sub_agents` | legacy config | `managed_agent_ids` 的兼容别名。 |
| `config.planner_gateway` | runtime config | 注入式 planner gateway。 |
| `config.orchestrator_llm_config` | runtime config | planner 模型参数。 |
| `config.answer_gateway` | runtime config | direct answer gateway。 |
| `config.fallback_adapter` | runtime config | 规划失败后的单 Agent fallback。 |
| `config.fallback_adapter_factory` | runtime config | 延迟创建 fallback adapter。 |

---

## 3. 总体解析顺序

Orchestrator 的任务解析顺序固定，前一个分支命中后不会继续尝试后续分支。

当前实现顺序：

1. Platform facts / direct answer / recent task status / clarification gate 入口判定。
2. 显式 `config.tasks` 自动跳过 clarification gate，并直接解析。
3. Clarification Gate 命中时输出 `clarification` block 并等待用户补充。
4. 直接多 Agent mention 路由。
5. LLM planner。
6. Legacy template fallback。

规划失败后的降级顺序：

1. `planner_fallback_to_template is True` 时先回退 template。
2. planner 协议错误可按配置回退 direct answer。
3. 有 fallback adapter 时回退单 Agent fallback。
4. 都不可用时返回 Orchestrator fatal `error`。

---

## 4. Direct Answer 短路

在以下条件全部满足时，Orchestrator 不创建任务、不调用子 Agent runtime，只通过 `answer_gateway` 或 ModelGateway 直接回答：

- `config.tasks` 不存在。
- 最新用户消息没有显式提到任何 managed 子 Agent。
- 最新用户消息命中身份、模型、能力、职责等 meta question marker。
- 最新用户消息不命中生成、创建、实现、修复、部署、review、coordinate 等 task intent marker。

这个分支用于“你是谁”“你是什么模型”“你能做什么”等普通问答。

direct answer 使用：

- `answer_gateway` 优先。
- 否则创建 ModelGateway。
- backend 取 `answer_model_backend`，再取 `model_backend`，默认 `claude`。
- 模型参数来自 `orchestrator_answer_config`，并兼容顶层 `model`、`max_retries`、`request_timeout_seconds`。

---

## 4.1 Clarification Gate（Implemented MVP）

Clarification Gate 是进入 planner 前的需求充足度检查，不生成 `SubTask`。
MVP 由 `orchestrator/clarification.py` 实现，并通过 `clarification` ContentBlock
持久化和展示。

规则：

- 只针对 artifact/build/code/design/deploy/file 等可能创建或修改产物的请求。
- 普通 direct answer、历史任务状态询问和平台事实问答必须跳过。
- 如果缺失信息可以通过 conversation、structured memory、workspace、spec/rules/docs 或代码事实推断，不追问用户。
- 如果缺失信息会明显改变实现方向，一次只问一个最高价值问题，并给出推荐默认。
- 等待用户补充时，Orchestrator message 以 `done` 结束；这不是 runtime error。
- 等待期间不得创建 task card、发 `agent_switch`、调用子 Agent 或写 workspace。
- 下一轮用户回答会与原始请求、推荐默认合并后，再进入 planner。
- 显式支持 `/grill-me`、`/grill-with-docs`、`/setup-matt-pocock-skills`。
- `/grill-with-docs` 和 `/setup-matt-pocock-skills` 只写当前 conversation workspace。

详细行为、状态语义和后续实施任务见 [clarification-gate.spec.md](clarification-gate.spec.md)。

---

## 5. 显式 `config.tasks`

如果 `config.tasks` 存在，Orchestrator 直接解析它：

1. `tasks` 必须是非空 list。
2. 每个 task 必须是 object，并满足 `SubTask` 字段校验。
3. `task_id` 必须唯一。
4. 解析后按 `priority` 升序排序。

显式任务不会再走 direct multi-agent routing、LLM planner 或 template fallback。

当前 `SubTask` 字段见 [core.spec.md §3](core.spec.md#3-子任务结构)。

`expected_output` 语义：

- 可继续作为人类可读的输出描述。
- 如果包含明确 workspace-relative path，如 `snake.html`、`src/App.tsx`，执行层可将其作为 artifact path 候选。
- `expected_output` 不应要求 runtime 启动 preview/deploy/server。
- planner 不需要保证 path 一定存在；存在性由 Orchestrator 执行层在任务结束后只读校验。

---

## 6. 直接多 Agent 路由

如果没有显式 `tasks`，Orchestrator 会检查最新用户消息是否显式提到了两个或更多 managed 子 Agent。

支持的内置别名包括：

| Agent | 别名示例 |
|---|---|
| `claude-code` | `@claude-code`, `claude code`, `claudecode` |
| `codex-helper` | `@codex-helper`, `codex helper`, `codex` |
| `opencode-helper` | `@opencode-helper`, `open code`, `opencode` |

命中后会按 mention 在消息中的出现顺序创建一组 `direct-*` 任务：

- `title="Direct request"`。
- `include_history=False`。
- 如果用户消息中有引号内容，优先把引号内文本作为子 Agent 的 direct message。
- 子 Agent instruction 明确要求“只回答这条 direct request，不要联系、调用或模拟其他 agents/CLIs/APIs”。

这个分支用于“分别问 claude-code、codex-helper 你是什么模型”这类对比性直接问答。

---

## 7. LLM Planner

如果没有显式任务、没有直接多 Agent 路由，并且满足任一条件，则启用 LLM planner：

- `planner_gateway` 存在。
- `llm_planning is True`。
- `orchestrator_llm_config` 是 object。

planner 流程：

1. 可用 Agent id 优先来自 `available_agents`，否则来自 `managed_agent_ids/default_sub_agents`。
2. planner gateway 优先使用注入的 `planner_gateway`，否则创建 ModelGateway。
3. ModelGateway backend 取 `planner_model_backend`，再取 `model_backend`，默认 `claude`。
4. planner prompt 要求只使用白名单 agent id。
5. 有 tool support 时必须调用 `submit_task_plan`。
6. 没有 tool payload 时，从文本中解析 JSON。
7. planner 输出必须解析为 `{"tasks": [...]}` 或 tasks array。
8. Orchestrator 校验 `agent_id`、`depends_on` 和 task schema。
9. 纯 preview/deploy/port/server/service 任务会被过滤，除非该任务被其他任务依赖，或任务内容包含生成 artifact 的 marker。
10. 纯对话/辩论/角色扮演任务应使用 `task_type="conversation"`，且不应附带 artifact path。

`available_agents` 描述要求：

- 每个条目必须能明确映射到一个可调度 `agent_id`。
- 推荐包含：`id`、`name`、`capabilities`、`planning_profile`、`planning_strengths`、`planning_weaknesses`、`preferred_task_types`。
- planner prompt 应把这些描述传给模型，要求只选择白名单 id。
- planner prompt 必须说明 Codex 是架构/审阅/兜底负责人；并行实现优先拆给 Claude Code 与 OpenCode；Codex 不应吞掉所有普通实现任务。
- 示例：

```json
{
  "id": "codex-helper",
  "name": "Codex Helper",
  "capabilities": ["coding", "sandbox"],
  "planning_profile": "适合复杂 AgentHub 代码任务的方案拆解、总体规划、仓库理解、架构判断和任务验收；负责审阅其他 agent 完成并测试后的代码；当其他 agent 无法解决复杂 bug 或需要求助时接手处理；作为多 agent 工作流的总负责人和技术兜底者。除非任务需要最高复杂度判断或兜底修复，否则不要把普通并行实现任务全部交给它。",
  "planning_strengths": ["architecture", "repo_analysis", "task_planning", "final_review", "difficult_bug_fixing", "escalation_owner", "technical_lead"],
  "planning_weaknesses": ["routine_parallel_implementation", "simple_file_edits"],
  "preferred_task_types": ["planning", "architecture", "review", "repair", "escalation"]
}
```

依赖规划要求：

- 如果后续任务需要消费前序任务结果，planner 必须填写 `depends_on`。
- 依赖只能引用同一计划内已存在的 `task_id`。
- 依赖表达 DAG 约束；执行层会并发执行所有依赖已满足的 runnable tasks。
- 互不依赖的任务可以并行执行；需要等待其他产物的任务必须显式填写 `depends_on`。
- 执行层会把依赖任务结果注入后续任务上下文，planner 不需要把前序结果复制进 instruction。

planner config：

- 默认 `temperature=0`。
- 默认 `max_tokens=2048`。
- 默认 `tool_choice={"type": "auto"}`。
- 兼容顶层 `model`、`max_retries`、`request_timeout_seconds`。

---

## 8. Preview / Deploy Guard

planner guard：

- 不得创建启动、部署、预览、管理长驻端口服务的子任务。
- 用户要求 port preview/deploy 时，只规划文件生成和内容验证。
- 平台 preview/deploy 由 AgentHub 平台层处理，不由 runtime agent 或 Orchestrator 启动。

过滤规则：

- 命中 `preview/deploy/port/server/service/808/预览/部署/端口/服务` 等 marker 的任务，会被识别为候选端口服务任务。
- 如果任务同时命中 `create/generate/write/implement/build/file/artifact/html/创建/生成/编写/实现/文件/产物` 等 artifact marker，则保留为文件生成任务。
- 如果该任务被其他任务依赖，也会保留，避免破坏 planner 输出的依赖图。
- 如果过滤后没有任何任务，保留原始任务列表，避免 planner 输出被全部清空。

---

## 9. Planner 失败处理

LLM planner 抛出 `ValueError` 后，Orchestrator 按以下顺序处理：

1. 如果 `planner_fallback_to_template is True`，回退到 template 任务。
2. 否则包装为 `PlannerResolutionError`。
3. 如果 `direct_answer_on_planner_failure is True` 且错误属于 planner 协议错误，则走 direct answer。
4. 如果配置了 fallback adapter，则走单 Agent fallback。
5. 否则发出 Orchestrator fatal `error`。

注意：本节只描述“规划失败”的 fallback。v1.2 的 per-task fallback 属于执行层能力，用于单个子任务 `failed` 或 `artifact_missing` 后的重试，见 [core.spec.md](core.spec.md)。

planner 协议错误包括：

- invalid JSON。
- 空 planner 输出。
- planner stream `error`。

---

## 10. Legacy Template Fallback

未启用 LLM planner 时，或 planner 配置允许 fallback 时，Orchestrator 使用 template 生成任务：

1. 如果用户显式提到两个或更多 managed 子 Agent，生成 direct tasks。
2. 否则取前 3 个 managed agents，生成：
   - `Analyze request`
   - `Produce solution`
   - `Review and refine`
3. 若没有可用 managed agents，返回 `missing_task_plan` fatal error 或触发 fallback adapter。

template fallback 是历史兼容路径，不应替代 LLM planner 的长期规划能力。

对于纯对话任务，template fallback 是例外的受控路径：它只用于保证群聊辩论类请求在 planner 不可用或 planner 输出不合格时仍能创建真实 Agent 发言任务。该路径不得要求 workspace 文件、不得触发 preview/build/deploy，也不得将负向约束中的文件名作为 expected artifacts。

---

## 11. 子 Agent 实质输出合同

Orchestrator 不能只以 child message `status=done` 判断子任务完成。执行层会按任务类型做 deterministic output contract：

- `conversation/direct_output`：必须有常显 `agent_summary`，内容要直接完成指定角色、立场、主题或回答；只说“请登场 / 下面有请 / 我来主持 / 已完成”不合格。
- `analysis/strategy/data`：必须包含结论、依据、建议、风险或取舍，不要求 workspace 文件。
- `artifact/code/document`：以 expected artifacts、file changes、tool evidence 或 evaluation 为主要完成证据；如果 Agent 自然语言很少，后端可生成简洁阶段 summary。
- `review`：必须包含被审阅对象的 pass/fail、gaps、风险、missing 或 repair 信号；显式要求 `review.md` 时继续校验文件。
- `platform/preview/verify/deploy`：以平台 tool result、deployment status 和 fulfillment item 为完成证据，summary 只说明状态、URL 或受控失败原因。

如果子 Agent 第一次输出不合格，Orchestrator 在同一 child message 内追加 `output-correction` process step，并用强化 instruction 让同一 Agent 补充一次。仍不合格时，该 attempt 记为 `output_incomplete`，再走通用 fallback 到其他可用 Agent。

该合同是通用机制，覆盖纯对话、角色扮演、头脑风暴、策略/数据分析、代码产物、文档产物、审阅和平台动作；不是辩论或前端 demo 的特例。

---

## 12. 验收标准

- 普通身份/模型/能力问答走 direct answer，不启动子 Agent runtime。
- 显式 `config.tasks` 优先于所有自动规划。
- 显式提到两个或更多 managed agents 时生成 direct tasks。
- direct tasks 使用 `include_history=False`。
- LLM planner 只允许输出白名单 agent id。
- planner 输出的依赖必须引用已存在 task id。
- planner 不规划 preview/deploy/server 长驻端口任务。
- planner 失败按 template、direct answer、fallback adapter、fatal error 的配置顺序降级。
- 没有 managed agents 且没有 fallback 时返回清晰 fatal error。
- planner 会在需要消费前序结果时填写 `depends_on`。
- `expected_output` 中的明确 artifact path 可被执行层用于 artifact 存在性校验。
- 纯对话 `conversation` task 不做 artifact 存在性校验，负向约束中的文件名不会被提取为 required artifact。
- child message `done` 必须代表该 Agent 对应任务类型的实质贡献通过 output contract；否则先纠偏，仍失败再 fallback。

---

## 13. 相关文件

| 文件 | 说明 |
|---|---|
| [adapter.py](../../../../backend/app/agents/orchestrator/adapter.py) | Orchestrator 规划分支入口。 |
| [task_planning.py](../../../../backend/app/agents/orchestrator/task_planning.py) | direct answer、direct mention、legacy fallback 与任务解析。 |
| [planner.py](../../../../backend/app/agents/orchestrator/planner.py) | LLM planner helper。 |
| [core.spec.md](core.spec.md) | Orchestrator 主行为契约和执行流转。 |
| [model-gateway.spec.md](../model-gateway.spec.md) | ModelGateway backend 与调用边界。 |
| [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md) | preview/deploy 平台边界。 |
