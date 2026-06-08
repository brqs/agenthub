# Orchestrator Clarification Gate Spec

> 定义 Orchestrator 在进入任务规划、子 Agent 调度和代码产物生成之前，如何判断需求是否足够明确，以及如何向用户逐步追问。
>
> 状态：Implemented MVP
> 最后更新：2026-06-07

## 2026-06-08 Implementation Note: 需求对齐

Clarification Gate 的自动触发入口已经改为用户可控的 **需求对齐** 模式。

- 用户可见名称统一为 `需求对齐`，不再称为计划模式。
- 默认 `off`：普通 Orchestrator 对话、辩论、分析、闲聊、构建请求都不会因为自动 gate 被拦截。
- 每个 turn 可通过 `requirement_alignment: "strict"` 开启严格需求对齐；该选项会写入 `messages.turn_options`，并复制到对应 agent message 和 queued dispatch 后的新 agent message。
- 显式 slash command `/grill-me`、`/grill-with-docs`、`/setup-matt-pocock-skills` 仍然保留，不依赖开关。
- strict 模式下，Orchestrator 在调度前只问影响执行方向的关键问题；如果需求已经足够明确，则输出假设 brief 并等待用户明确确认。
- 推荐答案必须基于当前请求场景动态生成：网页/游戏/组件推荐前端产物边界；辩论/讨论推荐对话式输出与角色/轮次/总结方式；文档、分析、代码修改分别推荐对应结构、维度、范围和验收标准。
- LLM 生成的问题必须通过确定性校验；如果把非前端任务推荐成静态前端产物，必须丢弃并使用对应 `task_kind` fallback。

---

## 1. 背景与来源分析

`mattpocock/skills` 中相关能力主要由两个 skill 表达：

- [`grill-me`](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md)：把需求对齐定义为一个追问会话。核心规则是沿着设计决策树逐个分支追问，每次只问一个问题，并为每个问题给出推荐答案；如果问题能通过读代码回答，就先读代码而不是打扰用户。
- [`grill-with-docs`](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md)：在 `grill-me` 基础上加入项目上下文约束。它会读取 `CONTEXT.md`、`docs/adr/`，对照现有领域语言和代码事实纠正用户说法，澄清术语，并在决策稳定时更新上下文或 ADR。
- [`setup-matt-pocock-skills`](https://github.com/mattpocock/skills/blob/main/skills/engineering/setup-matt-pocock-skills/SKILL.md)：说明这些 skill 不是硬编码流程，而是通过 repo 级 `AGENTS.md` / `CLAUDE.md` 与 `docs/agents/*` 建立长期规则和文档消费约定。

该机制的本质不是“多问几个问题”，而是一个代码前的需求收敛状态机：

1. 先判断当前需求是否足以开始实现。
2. 能从代码、历史记忆、已有文档推断的内容不问用户。
3. 不能推断且会影响实现结果的内容，一次只问一个最高价值问题。
4. 每个问题必须带推荐答案，降低用户回答成本。
5. 当术语或决策稳定时，沉淀到项目文档，避免下次重复问。

---

## 2. AgentHub 可行性判断

结论：可以应用到 AgentHub 的 Orchestrator 主 Agent，但不应直接照搬为 Claude Code slash command。

可行原因：

- Orchestrator 已经是群聊复杂任务入口，天然位于“理解需求 -> 规划任务 -> 调度子 Agent”之前。
- 现有 `task-planning.spec.md` 已区分 direct answer、task intent、LLM planner 和 fallback；clarification gate 可以作为 planner 前的独立阶段。
- 现有 structured memory 可保存最近 Orchestrator run/task/attempt；后续实现可以复用它保存“待澄清问题”和“已确认约束”。
- 现有 `ask_user` tool 已有 `needs_user_input=true` 语义，可作为早期最小实现的输出基础。
- 前端不需要新增请求 endpoint；MVP 已通过 `clarification` ContentBlock 产品化为结构化 clarification card。

限制与差距：

- 当前 `ask_user` v1 只在 tool-calling loop 中产生最终文本，不会真正暂停一个可恢复 run。
- 当前 Orchestrator task planner 直接从用户最新消息进入计划生成，缺少“需求充足度”判定。
- 当前 structured memory 主要记录执行事实；MVP 通过 `[Clarification state] ...`
  上下文文本恢复 pending state，并在存在 `orchestrator_memory_writer` 时写入
  clarification run events。
- 如果没有明确的 bypass 规则，追问会降低“随手让 Agent 快速做一个 demo”的效率。

因此本 spec 定义的是 Orchestrator 产品级行为。2026-06-07 MVP 已落地为
Orchestrator planner 前的确定性 clarification router，并通过新的
`clarification` ContentBlock 做前端结构化展示。

---

## 3. 设计目标

Clarification Gate 的目标：

1. 在 artifact/build/code/deploy/design 类请求进入实现前，阻止明显欠规格的任务被过早派给子 Agent。
2. 把“追问”限制在会影响实现结果的关键决策上，避免形式主义问答。
3. 每次只问一个问题，并给出推荐答案或可选默认值。
4. 优先利用当前 conversation、Orchestrator structured memory、workspace、已有 spec/rules/docs 和代码事实回答问题。
5. 用户补充后，Orchestrator 能把新答案与原始请求合并成稳定需求，再进入正常 planner。
6. 不破坏现有 direct answer、group-scoped dispatch、runtime availability 和 workspace sandbox 边界。

非目标：

- 不把所有请求都变成 PRD 访谈。
- 不要求用户在每次小 demo 前填写完整表单。
- 不让子 Agent 自行追问用户；用户需求澄清由 Orchestrator 统一处理。
- 不新增 endpoint 或修改 `POST /messages` 请求体。MVP 已扩展 OpenAPI message
  content block union，新增 `clarification` block 类型。

---

## 4. 触发规则

Clarification Gate 只处理“用户请求可能进入实现”的场景。

必须跳过 gate：

- 普通问候、身份、模型、能力、历史任务状态等 direct answer。
- 用户显式要求“不要问，直接按默认做”。
- 显式 `config.tasks` 已由可信调用方提供完整任务图。
- 用户只是要求解释、分析、审阅现有内容，不要求创建或修改产物。
- 请求足够具体，已有可执行 artifact contract、约束和验收标准。

应进入 gate 判定：

- artifact/build/design/code/deploy/file 请求缺少会影响结果的核心约束。
- 用户要求“做一个网页/游戏/工具/组件”，但没有说明目标用户、核心玩法/流程、内容范围、技术边界或验收标准。
- 用户给了多个互相冲突的要求。
- 用户使用项目内已有 glossary/spec 中冲突或重载的术语。
- 最近 structured memory 中有相关未解决问题，当前用户消息看起来是在回答它。

---

## 5. 需求充足度

进入实现前，Orchestrator 至少需要判断以下信息是否足够：

| 维度 | 示例 |
|---|---|
| 目标产物 | 静态 HTML、React 组件、后端接口、文档、测试、部署包 |
| 用户目标 | 给谁用、解决什么问题、成功体验是什么 |
| 范围边界 | 必须包含什么、明确不做什么 |
| 验收标准 | 如何判断完成、是否需要测试/预览/浏览器验证 |
| 技术约束 | 语言、框架、runtime、workspace、端口、API、认证 |
| 数据与内容 | 是否有现成文案、图片、数据、示例，还是允许生成占位内容 |
| 交互/视觉约束 | UI 风格、移动端、无障碍、主题、品牌或具体视觉参考 |
| 风险约束 | 安全、隐私、不可写路径、不可启动服务、不可调用群聊外 Agent |

“足够”不等于“完整”。如果缺失项有合理默认且风险低，Orchestrator 应采用默认值并在计划中写明；只有缺失项会明显改变实现方向时才追问。

---

## 6. 提问策略

Clarification Gate 的提问规则：

1. 一次只问一个问题。
2. 问最高价值的阻塞问题，而不是列清单。
3. 每个问题必须包含推荐答案或默认方案。
4. 如果可以通过读代码、workspace、历史 run、spec 或 rules 推断，就先推断，不问用户。
5. 问题应使用用户能判断的产品语言，不暴露 planner、adapter、tool schema 或内部 prompt 细节。
6. 追问次数应有预算，默认每个用户请求最多 3 轮；超过预算后使用已确认信息和安全默认值，或明确说明无法执行。
7. 如果用户只回答普通补充信息，Orchestrator 只能记录/总结该补充并继续等待确认；不得自动进入 planner、写 workspace 或调度 Agent。
8. 只有用户明确回答“按这个做”“开始实现”“按默认开始实现”“确认使用推荐配置”等正向确认语时，Orchestrator 才能产生 side effect 或进入 planner。
9. 否定表达优先级高于关键词匹配；“不要按默认”“还没确认，不要直接做”不得因为包含“按默认/直接做”而触发继续。
10. 如果用户明确要求继续追问或“grill me”，可以进入更完整的需求访谈模式，但仍一问一答。

问题格式建议：

```text
我需要先确认一个会影响实现方向的问题：<问题>

推荐默认：<推荐答案及理由>
```

不推荐：

- “请提供更多需求。”
- 一次列 8 个问题。
- 把内部 Agent、API key、runtime 或数据库细节包装成用户必须回答的问题。

---

## 7. 状态语义与 ContentBlock 契约

MVP 不新增 endpoint，不改变 `POST /messages` 请求体。澄清状态通过现有
message content / SSE block 流传输，新增 block 类型：

```ts
{
  type: "clarification",
  agent_id?: string | null,
  mode: "auto" | "grill_me" | "grill_with_docs" | "setup_matt_pocock_skills",
  title: string,
  status: "waiting" | "resolved" | "cancelled",
  current_question?: ClarificationQuestion | null,
  questions: ClarificationQuestion[],
  summary?: string | null,
  metadata?: Record<string, unknown>
}
```

`ClarificationQuestion` 字段：

```ts
{
  id: string,
  question: string,
  reason?: string | null,
  recommended_answer?: string | null,
  options?: string[],
  status: "pending" | "answered" | "skipped",
  answer?: string | null
}
```

MVP 状态流：

1. Orchestrator 收到用户请求。
2. `clarification.py` 在 platform/direct-answer/task planning 前判定是否需要澄清。
3. 如果需要，输出 `clarification(status=waiting)` block，顶层 message 以 `done`
   结束，不显示重试。
4. 等待期间不创建 `task_card`，不发 `agent_switch`，不调用子 Agent，不启动
   runtime。
5. 下一条用户消息若命中同 conversation 最新 pending clarification，先进入
   pending reply router；不得默认吞并为当前问题答案。
6. pending reply router 至少区分：
   `answer_current`、`reference_context`、`new_topic`、`explicit_switch`、
   `control`、`ambiguous`。
7. 用户回答“按这个做 / 开始实现 / 按默认开始实现”等明确确认语时，
   Orchestrator 把原始请求、已确认回答和推荐默认合并成新的 user message，
   再进入正常 planner。
8. 用户提到项目 B 时：
   - 如果语义是“参考项目 B”，归入当前项目 A 的澄清答案。
   - 如果语义是询问/改进项目 B，输出方向确认卡，不进入 planner。
   - 如果明确“先不做 A，改做 B”，取消 A 的 pending clarification，并对 B 重新走 gate。
9. `/setup-matt-pocock-skills` 和 `/grill-with-docs` 写 workspace 前必须有明确写入确认。
10. `/grill-me` 深度追问默认最多 8 轮；自动 gate 默认最多 3 轮。
11. `/grill-with-docs` 和 `/setup-matt-pocock-skills` 只写当前 conversation
   workspace，不修改 AgentHub 主项目仓库。

内部状态：

- 通过压缩上下文中的 `[Clarification state] ...` 文本恢复 pending state。
- 如果配置中存在 `orchestrator_memory_writer`，会写入
  `orchestrator_run_events`：
  - `clarification_question_asked`
  - `clarification_resolved`
  - `clarification_cancelled`

与现有 `ask_user` 的关系：

- `ask_user` v1 是 tool-calling loop 的工具结果，最终仍靠文本请求用户补充。
- Clarification Gate 是 planner 前的系统阶段，不应依赖模型在 tool loop 中“碰巧”调用 `ask_user`。
- 后续实现可以复用 `needs_user_input` 的展示语义，但必须有确定性的 gate classifier 和恢复逻辑。

---

## 8. 与 Orchestrator 规划顺序的关系

推荐顺序：

1. Platform facts / direct answer / recent task status。
2. 显式 `config.tasks`。
3. Clarification Gate。
4. 直接多 Agent mention 路由。
5. LLM planner。
6. Legacy template fallback。
7. Fatal error / retryable error。

Clarification Gate 不产生任务计划，只决定“是否可以进入任务计划”。

如果 gate 触发：

- 不允许调用群聊外 Agent。
- 不允许创建空承诺式“我会委托”回复。
- 不允许写 workspace。
- 不允许把“需要用户补充”标记成 error。

如果 gate 不触发：

- 后续 planner 仍必须遵守 group-scoped dispatch、runtime availability、artifact/build 不走 direct-answer fallback 等既有规则。

---

## 9. 文档沉淀策略

借鉴 `grill-with-docs`，但按 AgentHub 当前文档体系落地：

- 项目级规则更新到 `AGENTS.md` / `CLAUDE.md`。
- Orchestrator 行为契约更新到 `docs/b2/spec/orchestrator/*.spec.md`。
- 具体架构取舍只有在 hard to reverse、surprising、real trade-off 三个条件都满足时，才新增 ADR。
- 不把用户某一次产品需求写进 `AGENTS.md` / `CLAUDE.md`。
- 不把实现细节写进 glossary 类文档；`CONTEXT.md` 仅作为当前 conversation
  workspace 的领域语言/术语记录，不写入 AgentHub 主仓库。

---

## 10. 后续实施任务规划

### Phase 1 - 后端确定性 Gate MVP（已实现）

- 新增 clarification classifier：识别 artifact/build/design/code 请求是否欠规格。
- 新增 pending state：原始请求、当前问题、问题预算、推荐默认。
- 在 Orchestrator stream 入口加入 gate，位于 platform/direct answer 和 planner 之前。
- 输出 `clarification` block，`done` 终态，不创建 task_card。
- 下一轮用户回答时，读取同 conversation 最近 clarification state，先做 pending
  reply route，再决定记录答案、问方向确认、取消切换或等待明确执行确认。
- 测试覆盖：显式 `/grill-me`、自动 gate、明确确认后进入 planner、否定确认不继续、
  跨主题路由、`/setup-matt-pocock-skills` 和 `/grill-with-docs` 写入确认。

### Phase 2 - 结构化记忆与恢复

- 将 clarification events 写入 Orchestrator structured memory。
- 防止刷新、切换会话、重连后丢失待澄清状态。
- 对“刚刚那个按默认开始实现 / 按这个做”这类明确确认做确定性匹配。
- 将已确认约束注入 planner prompt，不让 planner 丢失追问结果。

### Phase 3 - 前端展示产品化（已实现 MVP）

- 新增 `ClarificationCard`，显示模式、当前问题、提问原因、推荐答案、选项
  chip、已回答历史和 summary。
- 选项 chip 只填入 `MessageInput`，由用户手动发送；第一版不新增按钮提交 API。
- `MessageInput` 新增 slash command suggestion：
  `/grill-me`、`/grill-with-docs`、`/setup-matt-pocock-skills`。

### Phase 4 - 文档/ADR 生产能力（部分实现）

- `/grill-with-docs` 已支持在用户明确确认后把定义追加到当前 workspace 的 `CONTEXT.md`。
- `/setup-matt-pocock-skills` 已支持在用户明确确认后写入当前 workspace 的 `AGENTS.md` 和
  `docs/agents/*`。
- ADR 建议/创建仍未实现；后续必须继续满足 hard to reverse、surprising、real
  trade-off 三个条件。

---

## 11. 验收标准

- “你好”“你是谁”“刚刚任务完成了吗”不触发 clarification gate。
- “做一个网页版小游戏”在缺少关键边界时，先问一个最高价值问题，带推荐默认，不调度子 Agent。
- 用户回复“按默认开始实现”或“按这个做”后，Orchestrator 能进入 planner，并把默认约束带入任务 instruction。
- 用户普通补充、提出项目 B 的新问题或否定“不要按默认”时，不进入 planner。
- 用户补充具体约束后，planner 不丢失原始请求和补充答案。
- Gate 期间没有 `task_card`、没有 `agent_switch`、没有 workspace 文件变更。
- Gate 产生的消息是 `done`，不是 `error`，不显示重试。
- 已有 group-scoped dispatch 规则不变。
- 如果用户明确要求“不要问，直接做”，在安全默认可行时跳过 gate。
- 单个请求默认最多 3 轮追问，防止陷入无限访谈。

---

## 12. 相关文件

| 文件 | 说明 |
|---|---|
| [task-planning.spec.md](task-planning.spec.md) | 规划顺序与 direct answer / planner / fallback 规则。 |
| [core.spec.md](core.spec.md) | Orchestrator 主执行契约。 |
| [tool-calling.spec.md](tool-calling.spec.md) | 现有 `ask_user` v1 语义。 |
| [memory-context.spec.md](memory-context.spec.md) | structured memory 和后续恢复入口。 |
| [../../../../backend/app/agents/orchestrator/clarification.py](../../../../backend/app/agents/orchestrator/clarification.py) | MVP clarification router、slash command、workspace docs 写入。 |
| [../../../../backend/app/agents/orchestrator/adapter.py](../../../../backend/app/agents/orchestrator/adapter.py) | Orchestrator stream 入口，planner 前接入 clarification gate。 |
| [../../../../backend/app/api/v1/stream_accumulator.py](../../../../backend/app/api/v1/stream_accumulator.py) | `clarification` block 持久化。 |
| [../../../../frontend/src/components/blocks/ClarificationCard.tsx](../../../../frontend/src/components/blocks/ClarificationCard.tsx) | 前端结构化澄清卡片。 |
| [../../../../frontend/src/components/chat/MessageInput.tsx](../../../../frontend/src/components/chat/MessageInput.tsx) | slash command suggestion 与 chip 填充输入框。 |
