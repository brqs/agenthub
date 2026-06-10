# Orchestrator Agent Turn-Taking Spec

> 状态：Implemented locally; public E2E pending user command
> 最后更新：2026-06-09
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
- `participants`：参与 Agent id 列表，必须来自当前 conversation 可用 Agent。
- `roles`：每个参与者的角色、立场或职责。
- `turn_order`：轮次顺序，每个元素包含 agent、role、turn index 和本轮目标。
- `max_turns`：最大轮次，默认 2 个参与者各 1 轮；用户要求“展开辩论 / 继续反驳 / 多轮”时可扩展到每人 2 轮，总上限 8 轮。
- `handoff_policy`：`planned_order`。子 Agent 的 `@mention` 可作为证据记录，但不覆盖计划。
- `done_condition`：所有计划轮次完成，或可用 Agent 全部失败且无 fallback。

### dialogue_turn

`dialogue_turn` 是内部 task type。它表示一个 Agent 的一次独立发言：

- 只能以当前 Agent 的角色发言。
- 必须回应原始主题；第二轮及之后必须回应前文。
- 不得代写其他 Agent 的完整发言。
- 不得只主持、邀请别人登场、转述任务或只说已完成。
- 不得创建 workspace 文件，除非用户明确要求把讨论结果沉淀为文档。

## 3. 触发条件

命中以下任一意图并且当前 group 至少有两个可用非 Orchestrator Agent 时，进入 turn-taking：

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
- 公网 E2E 需要用户明确命令后执行；本轮只完成本地实现与本地验收。

## 7. 2026-06-09 本地实现记录

- 后端新增 `dialogue_turn` task type，planner/tool schema、legacy fallback、artifact check、execution summary 与 output contract 均已支持。
- 对 turn-taking 请求，legacy fallback 会生成 `dialogue-turn-*` 任务；后续轮次通过 `depends_on` 接收上一轮摘要。
- group send/queue 入口支持“目标指向第一个 Agent，但文本要求多 Agent 接力”时改派给 Orchestrator 托管；普通单 Agent 私聊不受影响。
- `dialogue_turn` 输出合同要求本轮只写自己观点；后一轮必须回应、补充或反驳上一轮；代写多 Agent 剧本会触发 `output_incomplete`。
- E2E 脚本已注册 `agent_turn_taking_dialogue_repair` 与 `agent_turn_taking_matrix`，但公网 E2E 未执行。
