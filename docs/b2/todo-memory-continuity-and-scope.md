# TODO: 群聊记忆连贯性与 MemoryHub 作用域修复

状态：已实现，待手动 smoke
优先级：P1
涉及范围：Frontend、B1 Context、B2 Orchestrator、MemoryHub
记录日期：2026-06-10

## 2026-06-10 实施结果

- 已新增 `PreviousOutputFollowupResolver`，在已有澄清/显式 slash command 之后、自动澄清和 planner 之前运行。
- follow-up 只读取当前 conversation 最近 terminal run，并按 Workspace 文本产物、attempt `text_preview`、子 Agent 可见文本、run/task 摘要的顺序构建最多 12,000 字符的受限上下文。
- planner 只新增白名单段 `Previous output follow-up context:`，仍不开放完整历史 structured memory。
- 已新增 `GET /api/v1/conversations/{conversation_id}/memory-hub`，后端统一区分 scoped 与 user、active 与 candidate。
- 右侧 Memory 面板已改为当前会话优先、全局用户记忆默认折叠，query key 包含 conversationId。
- “动态挂载”已改名为“本会话已注入记录”，并增加 `not_attempted / no_match / mounted` 状态。
- 自动抽取现在只读取父级用户消息；一次性请求、问题、Agent 状态/道歉/总结不再生成长期记忆。
- 新 migration `f3a4b5c6d7e8` 只归档可确定的 `rules-v1` 历史污染数据，并保留原状态和 cleanup reason。

## 背景

当前群聊中已出现两组相互关联的记忆问题：

1. 用户在 Orchestrator 完成任务后使用“改得厉害一点”“继续优化”“把刚刚那个改一下”等省略表达时，系统不能稳定关联上一轮任务及产物。
2. 右侧工作台 Memory 面板会展示其他单聊或群聊产生的记忆，但“动态挂载”却可能显示为空，导致用户无法理解哪些记忆属于当前会话、哪些记忆实际参与了回复。

本任务的目标不是单纯增加更多上下文，而是明确记忆的事实源、作用域和挂载生命周期，使后续请求能够连续、可解释地使用上一轮事实。

## TODO 1：修复上一轮任务 Follow-up 断链

### 用户现象

上一轮请求：

> 请你帮我编写一个中科大招聘的文案

任务完成后，用户继续请求：

> 能不能帮我改得厉害一点

Orchestrator 没有把“改”关联到上一轮中科大招聘文案，反而重新询问需要夸赞什么内容。

### 已确认根因

- `stream_orchestrator_context` 已注入 `Previous Orchestrator structured memory`。
- planner 构造输入时没有完整读取该结构化 run/task memory，主要读取能力画像、用户偏好和 evidence context。
- `is_context_action_request()` 对“修改、优化、继续”等表达有部分支持，但没有稳定覆盖“改得厉害一点、再狠一点、换个风格”等口语化省略句。
- 当前 evidence 路由更偏向“是否完成、生成了哪些文件”等事实查询，不是通用的上一轮产物 follow-up resolver。
- Orchestrator memory 主要保存任务标题、状态、Agent、少量 `text_preview` 和 artifact path。上一轮正文如果没有作为完整文本或 workspace artifact 保存，下一轮即使知道任务存在，也可能拿不到实际修改对象。

### 待实现

- [ ] 在 planner memory extraction 中纳入 `Previous Orchestrator structured memory`。
- [ ] 新增“上一轮产物 follow-up resolver”，在 clarification、direct-answer 和 planning 之前运行。
- [ ] 识别以下表达及同义句：
  - 改一下、修改一下、优化一下、润色一下。
  - 改得更厉害、更专业、更正式、更简洁。
  - 再狠一点、再活泼一点、换个风格。
  - 继续、接着做、基于刚刚那个。
- [ ] 将省略请求解析为明确请求，例如：
  - 原始请求：`能不能帮我改得厉害一点`
  - 解析后：`修改上一轮“中科大招聘文案”，加强表达力度，同时保留原主题和事实约束。`
- [ ] 优先绑定当前 conversation 最近一个可修改的成功 task，而不是跨 conversation 搜索。
- [ ] 优先复用上一轮执行 Agent；只有该 Agent 不可用或任务类型不匹配时才重新规划。
- [ ] 将上一轮可修改对象按顺序解析：
  1. workspace artifact 路径及文件内容；
  2. task attempt 的完整或受限文本输出；
  3. 上一轮可见 Agent 文本消息；
  4. task title、request 和 `text_preview`。
- [ ] 如果只能确认上一轮任务，但拿不到正文或产物，明确询问用户补充原文，不能假装已经拥有内容。
- [ ] 不允许从其他 conversation 自动选择产物作为“刚刚那个”。

### 目标行为

- 用户说“改得厉害一点”时，系统直接理解为修改上一轮中科大招聘文案。
- Orchestrator 应携带上一轮主题、正文或 artifact、执行 Agent 和验收事实进入新任务。
- 只有存在多个合理候选，或者上一轮没有可修改内容时，才向用户追问。

## TODO 2：修复 Memory 面板跨会话展示

### 用户现象

当前群聊的 Memory 面板中能看到其他单聊或群聊产生的记忆，例如与当前招聘文案无关的论文整理、代码产物确认等内容。

### 已确认根因

`MemoryPanel` 当前使用：

```ts
useMemories('active')
useMemories('candidate')
```

对应请求没有传递 `scope_type` 或 `scope_id`，因此后端返回当前用户的全部 active/candidate memories。

与此同时，“动态挂载”使用：

```text
GET /api/v1/conversations/{conversation_id}/memory-mounts
```

它严格限定当前 conversation。上下两个区域使用了不同作用域，却在同一面板中以相近语义展示。

### 待实现

- [ ] Memory 面板默认只展示当前 conversation 可见的记忆。
- [ ] 当前会话记忆至少包括：
  - `conversation + current conversation_id`
  - `workspace + current conversation_id`
  - `group + current conversation_id`（仅群聊）
- [ ] 用户级长期偏好单独放入“全局用户记忆”区域，不与当前会话记忆混排。
- [ ] 候选记忆也必须按当前会话作用域过滤。
- [ ] 面板切换 conversation 时，query key 必须包含 conversationId，禁止展示上一会话缓存残影。
- [ ] 编辑、提升、遗忘记忆后，只刷新受影响的 scoped query 和 mount query。
- [ ] 在卡片中明确展示来源：
  - 当前会话
  - 当前群聊
  - 当前 Workspace
  - 全局用户偏好
- [ ] 不允许用户在某个会话面板中误删或误编辑未明确标识的跨会话记忆。

### 推荐 UI 结构

```text
MemoryHub
├── 当前会话记忆
├── 候选记忆
├── 本会话已注入记录
└── 全局用户记忆（折叠，默认关闭）
```

“5 active”应改为明确的作用域描述，例如“当前会话 2 条”，避免把全局数量误认为当前聊天数量。

## TODO 3：修正“动态挂载”的生命周期和解释

### 当前语义

动态挂载不是“当前可以使用哪些记忆”，而是：

> 某一次 Agent 回复构造上下文时，MemoryHub 实际召回并注入了哪些记忆。

只有 `build_mount_context()` 召回成功，并且存在 `agent_message_id` 时，才会写入 `memory_mounts` 审计记录。

### 为什么会显示 0 mounts

- 面板上方展示的记忆可能属于其他 conversation，当前 conversation 无权挂载。
- 记忆可能刚从当前终态消息中抽取；它不会反向挂载到已经结束的回复，只能在后续回复中参与召回。
- recall 只使用 `status=active` 的记忆；candidate 不会动态挂载。
- recall 受当前 user、conversation、workspace、group、agent container tag 限制。
- 当前查询与记忆没有足够关联，或当前回复没有完成正常 context build，因此没有生成 mount 记录。

### 待实现

- [ ] 将“动态挂载”重命名为“本会话已注入记录”。
- [ ] 增加简短说明：“这里记录已经实际进入 Agent 回复上下文的记忆，不代表全部可用记忆。”
- [ ] 空态区分：
  - 当前尚未产生下一轮回复；
  - 当前没有匹配记忆；
  - 当前回复未使用 MemoryHub；
  - 挂载记录加载失败。
- [ ] 每条 mount 展示：
  - 被注入的记忆摘要；
  - 注入原因；
  - 目标 Agent；
  - 对应回复时间；
  - rank score。
- [ ] 新记忆抽取完成后刷新 scoped memory query。
- [ ] 新一轮 Agent 回复完成后刷新 mount query。
- [ ] 检查所有 Agent adapter 是否都通过 `build_context(..., agent_message_id=...)`，保证 mount 审计一致。

## TODO 4：提高 MemoryHub 抽取质量

截图中的以下内容被错误保存为长期记忆：

- “能不能帮我改得厉害一点”
- Agent 的追问、道歉和临时说明。
- 大段 Skill 或任务操作说明。

这些更像当前任务消息，不是稳定偏好、约束或长期事实。

### 待实现

- [ ] 默认只从用户消息抽取长期记忆；Agent 输出仅允许从明确确认的决策结果中抽取。
- [ ] “帮我……”“能不能……”等一次性任务请求不得直接成为 critical constraint。
- [ ] Agent 的提问、道歉、状态通知和执行总结不得成为长期记忆。
- [ ] 大段 Markdown/Skill 内容不得作为单条 decision memory 自动保存。
- [ ] 只有明确长期表达才自动激活，例如：
  - “以后默认使用中文。”
  - “所有部署都必须先让我确认。”
  - “我偏好简洁、正式的文案风格。”
- [ ] 一次性任务事实默认保持 conversation scope，并设置合理有效期或在任务结束后归档。
- [ ] 自动抽取结果先进入 candidate；critical/high 自动 active 必须使用更严格规则。
- [ ] 增加 normalized key 和 supersede 测试，避免近似内容重复堆积。

## 测试计划

### Backend

- [ ] 当前 conversation 只能召回当前 conversation/workspace/group 与 user scope 记忆。
- [ ] 其他 conversation 的 conversation scope memory 不得召回。
- [ ] user scope preference 可以跨会话召回，但必须标记为全局用户偏好。
- [ ] “改得厉害一点”绑定最近成功任务及其产物。
- [ ] 多个候选任务存在时进入澄清，不静默猜测。
- [ ] 新抽取的记忆不会出现在同一条已完成回复的 mount 记录中，但可在下一轮被挂载。
- [ ] 一次性请求、Agent 追问和执行状态不被自动提取为 active memory。
- [ ] mount 写入包含正确 conversation、agent message 和 memory ID。

### Frontend

- [ ] Memory 面板切换会话后不显示旧会话 scoped memory。
- [ ] 当前会话记忆和全局用户记忆分区展示。
- [ ] 候选记忆按 conversation scope 过滤。
- [ ] mount 空态能解释“尚未实际注入”，不再只显示 `0 mounts`。
- [ ] 新回复完成后 mount 列表自动刷新。
- [ ] 记忆编辑/遗忘不会误操作其他 conversation 的记忆。

### 手动 Smoke

1. 在会话 A 中设置长期偏好：“以后默认用正式、简洁的中文回答。”
2. 在会话 A 中完成“编写中科大招聘文案”。
3. 输入“改得厉害一点”，确认系统关联上一轮文案。
4. 创建会话 B，确认不会展示会话 A 的任务型记忆。
5. 确认全局语言/风格偏好可在折叠的全局区域显示，并可被会话 B 动态挂载。
6. 在会话 B 完成一次回复后，检查“本会话已注入记录”出现对应 mount。

## 完成标准

- 群聊和单聊中的省略型 follow-up 能稳定关联当前 conversation 的上一轮任务和产物。
- Memory 面板默认不混入其他 conversation 的任务型记忆。
- 用户级长期偏好可以跨会话使用，但在 UI 中明确标识。
- 动态挂载区域准确表达“实际注入记录”，空态具有可解释性。
- 一次性任务请求和 Agent 临时话术不再污染长期记忆库。
- 不新增隐式跨会话数据泄漏，不削弱 group-scoped dispatch 约束。
