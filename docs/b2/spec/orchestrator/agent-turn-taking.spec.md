# Orchestrator Agent Turn-Taking Spec

> 状态：Implemented + public E2E passed
> 最后更新：2026-06-10
> 范围：由 Orchestrator 托管的多 Agent 轮流发言、接力讨论、辩论、评审和 panel 协作。

## 1. 目标

Orchestrator 必须支持真实群聊中的 Agent-to-Agent 接力，而不是让某个子 Agent 在一条消息里模拟完整剧本。

目标场景：

- 用户要求两个或多个 Agent 轮流辩论、圆桌讨论、角色扮演、头脑风暴、观点对比。
- 用户要求多个 Agent 进行方案评审、代码 review panel、数据分析 panel 或需求澄清 panel。
- 用户直接点名第一个 Agent，但同时要求其他 Agent 后续回应。

后端行为：

- Orchestrator 生成并执行轮次计划。
- 每一轮由当前负责 Agent 生成一条独立 child message。
- 子 Agent 输出中的 `@agent-id` 只是 handoff hint，不直接调用后端 API。
- 下一位发言者由 Orchestrator 的计划决定。
- 纯对话 / no-artifact 任务不触发 workspace artifact check。

## 2. 术语

### DialoguePlan

内部计划结构，至少包含：

- `topic`：用户要求讨论或评审的主题。
- `participants`：参与 Agent id 列表，必须来自当前 conversation 的非 Orchestrator
  group members。执行阶段会再判断 runtime 可用性；不能因为某个 runtime 当前处于 cooldown
  就从计划和审计语义中删除用户明确要求的参与者。
- `roles`：每个参与者的角色、立场或职责。
- `turn_order`：初始最小轮次顺序，每个元素包含 agent、role、turn index 和本轮目标。
- `max_turns`：最大轮次，默认最多 8 轮；用户显式要求 `N 轮` 时按 `N * participant_count`
  计算并受 8 轮保护；用户明确“只要双方各说一句 / 只要一轮”时限制为每个参与者
  1 轮。
- `handoff_policy`：`planned_order`。子 Agent 的 `@mention` 可作为证据记录，但不覆盖计划。
- `done_condition`：双方/多方已完成最小有效发言、没有新的明确回应空间、达到用户要求或
  max turns，或可用 Agent 全部失败且无 fallback。

### dialogue_turn

`dialogue_turn` 是内部 task type。它表示一个 Agent 的一次独立发言：

- 只能以当前 Agent 的角色发言。
- 必须回应原始主题；第二轮及之后必须回应前文。
- 不得代写其他 Agent 的完整发言。
- 不得只主持、邀请别人登场、转述任务或只说已完成。
- 不得创建 workspace 文件，除非用户明确要求把讨论结果沉淀为文档。

## 3. 触发条件

命中以下任一意图并且当前 group 至少有两个非 Orchestrator Agent 时，进入 turn-taking：

- `轮流`、`一人一句`、`接力`、`展开辩论`、`回应对方`、`反驳对方`。
- `辩论`、`圆桌讨论`、`角色扮演`、`观点对比`、`群聊讨论`。
- `头脑风暴`、`互相 review`、`评审 panel`、`代码 review panel`、`数据分析 panel`、`需求澄清 panel`。
- 用户直接点名第一个 Agent，同时要求另一个 Agent 后续回复。

不进入 turn-taking：

- 普通单 Agent 私聊，例如 `@claude-code 你是什么模型`。
- 明确要求生成代码、文档、部署、修复文件的任务，除非同时明确要求“多 Agent 轮流讨论/评审”。
- Orchestrator direct answer、platform fact、context evidence answer。

## 4. 执行与消息归属

- Orchestrator 父 message 承载 plan、process 和最终总结。
- 每个 `dialogue_turn` 创建独立 child message，即使同一个 Agent 多次发言，也必须是多条消息。
- child message 使用现有 `message_start` / block events / `message_done` / `message_error`。
- 每轮的 raw stream text 标记为 `execution_text`，验收通过后追加常显 `agent_summary`。
- Orchestrator 在下一轮 prompt 中只提供 bounded context：原始请求、当前 Agent 角色、本轮目标、前几轮发言的必要片段或摘要。
- Orchestrator final answer 只做主持总结，不吞并或重写所有成员发言。
- 辩论 / 反驳 / 接力类任务采用动态 session：初始只需要最小轮次；每轮完成后
  Orchestrator 根据本轮 `agent_summary`、handoff hint、用户要求、已完成攻防轮次和
  max turns 判断是否追加下一轮 `dialogue_turn`。
- `一人一句` 只约束单轮输出简短，不自动表示总轮数固定；只有“只要双方各说一句 /
  只要一轮”等明确短答约束才固定为双方各一轮。
- 明确辩论任务结束时，Orchestrator 生成 deterministic `debate_judgement` run event，
  并在 final answer 中给出“更有说服力的一方”或“势均力敌”。评分只基于公开发言，
  维度包括回应针对性、证据具体性、风险覆盖、逻辑一致性和是否直接回应对方。
- 对明确接力任务，planner / legacy dialogue fallback 应保留完整参与者名单；runtime cooldown
  或 preflight unavailable 只影响该轮执行选择，不改变 DialoguePlan 里“谁本应发言”的事实。
- 如果某个计划参与者在执行前已知不可用，Orchestrator 需要为该参与者创建清洗后的独立
  `message_error` child message，说明该轮未完成并记录 fallback，而不是静默跳过。普通非对话
  task 仍可只在 process / memory 记录 preflight skip，不创建失败 child message。

## 5. 输出合同

`dialogue_turn` 复用子 Agent 实质输出合同，并增加轮次要求：

- 第一轮必须包含自己的立场、角色观点、分析结论或建议。
- 第二轮及以后必须回应前一轮内容，包含反驳、补充、让步、风险、证据或下一步建议。
- 如果输出像主持词、邀请别人登场、完整多角色剧本、空泛完成语，则判为 `output_incomplete`。
- 第一次不合格时，同一 child message 内追加 `output-correction` process step 并重试一次。
- 仍不合格时，该 child message 以清洗后的 `message_error` 结束，并按现有 fallback 选择其他可用 Agent 接手。

## 6. 兼容边界

- 不新增数据库 migration。
- 不新增 ContentBlock 类型。
- 不新增 SSE event type。
- 不改变直接 Agent 私聊行为。
- 不改变普通 artifact/code/deploy 任务的 artifact / tool / fulfillment 校验。
- 公网 E2E 已完成 `manual_two_agent_turn_taking` 与 `agent_turn_taking_matrix` 验证；报告见
  [live-e2e-report.spec.md](live-e2e-report.spec.md)。

## 7. 2026-06-09 本地实现记录

- 后端新增 `dialogue_turn` task type，planner/tool schema、legacy fallback、artifact check、execution summary 与 output contract 均已支持。
- 对 turn-taking 请求，legacy fallback 会生成 `dialogue-turn-*` 任务；后续轮次通过 `depends_on` 接收上一轮摘要。
- group send/queue 入口支持“目标指向第一个 Agent，但文本要求多 Agent 接力”时改派给 Orchestrator 托管；普通单 Agent 私聊不受影响。
- `dialogue_turn` 输出合同要求本轮只写自己观点；后一轮必须回应、补充或反驳上一轮；代写多 Agent 剧本会触发 `output_incomplete`。
- E2E 脚本已注册 `agent_turn_taking_dialogue_repair` 与 `agent_turn_taking_matrix`。

## 8. 2026-06-10 Dynamic Debate Update

本轮将辩论 / 反驳 / 接力类 `dialogue_turn` 从固定初始轮次升级为动态 session：

- 初始 plan 仍可只包含双方最小轮次，避免 planner 一次性展开完整剧本。
- 执行层在每轮 child message `done` 后判断是否追加下一轮；同一 Agent 多轮发言仍创建
  独立 child message。
- 默认辩论至少保证双方各一次，并在需要时继续到一轮攻防；`@agent-id 你继续` 是继续
  信号，但最终是否继续由 Orchestrator 判断。
- 默认 max turns 为 8；显式短答请求可提前停止。
- 默认辩论在双方完成两轮有效攻防后停止；只有用户显式指定 `N 轮` 时才继续按
  `N * participant_count` 执行到受保护上限。这样避免每轮末尾 `@agent-id 你继续`
  造成无界接力。
- `dialogue_turn` 默认不允许跨 Agent fallback 代打对方角色。计划成员 runtime 失败时，
  该轮保留独立 error / partial 证据，不能让反方 Agent 代写正方、或正方 Agent 代写反方。
- 辩论类 final answer 需要包含 `debate_judgement` 的主持评判；非辩论 roundtable /
  brainstorm / data panel 不输出胜负判断。
- 只有所有已生成辩论轮次均成功时才输出 `debate_judgement`；如果某个追加轮次失败，
  final answer 必须按 partial/needs-attention 说明，不能误报完整结束。

本轮本地验证已通过：

```text
pytest:
  tests/test_orchestrator_planning.py
  tests/test_orchestrator_output_contracts.py
  tests/test_orchestrator_response_presentation.py
  tests/test_orchestrator_live_e2e_script.py
  tests/test_orchestrator.py::test_orchestrator_dynamic_debate_continues_after_handoff
  tests/test_orchestrator.py::test_orchestrator_dynamic_debate_respects_explicit_one_exchange
  result: 108 passed

ruff: passed
mypy app/agents/orchestrator: passed
git diff --check: passed
```

## 9. 2026-06-10 Public E2E Evidence

本轮完成 OpenCode / Codex 默认模型清理后，按真实账号路径执行公网 turn-taking repair loop：

```text
manual_two_agent_turn_taking:
  report: /tmp/agenthub_manual_two_agent_turn_taking_report.json
  sse: /tmp/agenthub_manual_two_agent_turn_taking_sse.jsonl
  passed: true
  acceptance:
    claude-code message_start -> message_done
    opencode-helper message_start -> message_done
    opencode-helper has visible agent_summary
    no artifact_missing / call_ / raw stderr / workspace absolute path
    fallback Agent cannot substitute for OpenCode in this strict case

agent_turn_taking_matrix:
  report: /tmp/agenthub_agent_turn_taking_matrix_report.json
  sse: /tmp/agenthub_agent_turn_taking_matrix_sse.jsonl
  passed: true
  cases:
    debate_no_artifacts
    roundtable_no_artifacts
    roleplay_dialogue
    strategy_brainstorm
    data_analysis_no_file
    code_artifact_with_summary
    review_requires_gaps
```

验证结论：

- 子 Agent 输出中的 `@agent-id` 仍只是 handoff hint；下一轮由 Orchestrator 调度。
- 明确 two-agent 接力场景中，OpenCode 必须自己完成 OpenCode child message，不能由 fallback
  代替通过。
- 所有完成的 child message 必须有通过 output contract 的常显 `agent_summary`。

## 10. 2026-06-10 Direct-Chat Timeout Hardening

`conversation` / `dialogue_turn` 是公开对话输出，不需要 workspace 文件、shell、preview 或部署时，
子 Agent 可继续走 external direct-chat 快捷路径；这不是 hidden chain-of-thought，也不是 Agent
之间直接互调，调度仍由 Orchestrator 托管。

为避免长辩论发言或上游首包慢被 10 秒默认 idle timeout 误杀，Orchestrator 在派发
`conversation` / `dialogue_turn` 子任务时为 direct-chat 注入更宽松的流式预算：

- idle timeout 至少 45 秒；
- hard runtime 至少 120 秒；
- heartbeat 间隔 10 秒。

该 override 只影响 Orchestrator 托管的纯对话子任务，不影响普通 Agent 私聊，也不改变真实
Claude Code / OpenCode / Codex CLI/SDK runtime budget。若某轮仍超时，该 child message 可以
进入 error，但 final answer 不得误报完整辩论结束。
