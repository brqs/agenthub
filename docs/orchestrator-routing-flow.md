# Orchestrator 群聊消息路由流程与任务流转说明

## 概述

Orchestrator 是 AgentHub 的核心协调器，负责接收用户消息并将其路由到合适的处理路径。整个路由逻辑采用瀑布式优先级路由，每一层都可以短路返回。

## 核心入口

**文件**: `backend/app/agents/orchestrator/adapter.py:246`
**方法**: `OrchestratorAdapter.stream()`

## 群聊成员上下文与调度边界

一次普通群聊消息开始时，stream 层会先读取当前 `Conversation.agent_ids`，再为
Orchestrator 注入两类信息：

1. `build_context()` 生成的通用上下文：
   - Orchestrator system prompt / group observer prompt。
   - 当前群聊成员列表。
   - 最新用户消息。
   - pinned / critical facts / MemoryHub / compressed memory / recent messages。
   - agent 历史消息会保留 `[Agent: <agent_id>]` 标签，避免把其他 Agent 的话误当成当前 Agent 自己的输出。
2. `apply_orchestrator_stream_context()` 生成的调度配置：
   - `conversation_agents`：当前会话里所有 Agent 的安全 profile。
   - `available_agents`：当前群聊里可运行的非 Orchestrator 子 Agent。
   - `managed_agent_ids`：从 `available_agents` 推导出的可执行子 Agent id。
   - `planning_agent_ids`：同样来自当前可执行子 Agent，不再从全局 seed/defaults 补全。
   - `available_agents_authoritative=true` 与 `conversation_scoped_agents=true`：表示普通群聊必须以当前群成员作为唯一调度边界。

因此，任务开始时传给 Orchestrator / Planner 的核心不是“所有内置 Agent”，而是：

- 系统提示词和 Orchestrator 行为约束。
- 当前群聊真实成员及其安全 planning profile。
- 用户本轮提示词。
- bounded conversation / memory / workspace evidence。

如果当前群聊只有 Orchestrator、Claude Code、Codex Helper，Planner 不应看到或选择
`opencode-helper`。如果模型仍幻觉输出了群聊外 Agent，后端会先触发一次 planner retry；
retry 后仍非法时会 remap 到当前群内可执行 Agent，或在没有可执行子 Agent 时返回可读降级错误。
ReAct replanner、tool loop `dispatch_agent`、fallback 和 dialogue next speaker 使用同一群聊边界。

## 完整路由链路（按优先级从高到低）

### ① Clarification Gate（澄清门控）

**优先级**: 最高
**文件**: `backend/app/agents/orchestrator/clarification.py:327`
**函数**: `maybe_handle_clarification()`

**触发条件**:
- 有待处理的澄清问题（`pending` 状态）
- `/grill-me`、`/grill-with-docs`、`/setup-matt-pocock-skills` 等斜杠命令
- 需求对齐模式（`requirement_alignment`）下的模糊请求

**处理逻辑**:
1. 检查是否有待处理的澄清状态（`_latest_pending_clarification()`）
2. 解析斜杠命令（`_parse_command()`）
3. 判断是否需要自动澄清（`_should_auto_clarify()`）
4. 返回澄清问题或继续处理

**输出**:
- `ClarificationOutcome.done = True`: 返回澄清问题，流程结束
- `ClarificationOutcome.done = False`: 注入上下文，继续处理
- `None`: 无澄清需求，继续下一优先级

### ② Previous Output Followup（上一次输出的跟进）

**优先级**: 高
**文件**: `backend/app/agents/orchestrator/_internal/routing/previous_output_followup.py:106`
**函数**: `resolve_previous_output_followup()`

**触发条件**:
- 短请求包含跟进标记（"改一下"、"修改"、"润色"、"优化"等）
- 请求长度 ≤ 160 字符
- 包含显式引用标记（"刚刚"、"之前"、"上一"等）

**处理逻辑**:
1. 加载最近的 Orchestrator 运行记录（`_load_candidates()`）
2. 查找可修改的产物（文本文件、代码等）
3. 如果找到单一候选：注入上下文，继续处理
4. 如果找到多个候选：返回选择界面让用户选择
5. 如果未找到候选：返回澄清问题

**输出**:
- `PreviousOutputFollowupOutcome.done = True`: 返回选择/澄清界面
- `PreviousOutputFollowupOutcome.done = False`: 注入上下文，继续处理
- `None`: 不是跟进请求，继续下一优先级

### ③ Clarification Gate（二轮，allow_auto_start=True）

**优先级**: 中高
**文件**: `backend/app/agents/orchestrator/clarification.py:327`
**函数**: `maybe_handle_clarification()`

**触发条件**:
- 与①相同逻辑，但 `allow_auto_start=True`
- 仅在②未触发时执行

**处理逻辑**:
- 与①相同，但允许自动启动需求对齐

### ④ Platform Fact Routing（平台事实路由）

**优先级**: 中
**文件**: `backend/app/agents/orchestrator/_internal/routing/platform_facts/classifier.py:105`
**函数**: `platform_fact_intent()`

**触发条件**:
- 用户询问平台相关信息（"群里有哪些agent"、"你用什么模型"等）

**处理逻辑**:
1. **规则匹配**（`_rule_platform_fact_intent()`）:
   - 群聊 Agent 列表（`group_agents`）
   - 群聊模型列表（`group_models`）
   - 群聊能力列表（`group_capabilities`）
   - 自身模型信息（`self_model`）

2. **LLM 分类器**（`_classify_platform_fact_intent()`）:
   - 仅在规则未命中且 `platform_fact_classifier_enabled` 开启时调用
   - 使用小模型做意图分类
   - 置信度 ≥ 0.65 才生效

**输出**:
- 返回 `list[str]`: 检测到的平台事实类型列表
- 直接生成回答，流程结束

### ⑤ Direct Answer Routing（直接回答路由）

**优先级**: 中低
**文件**: `backend/app/agents/orchestrator/_internal/routing/direct_answer.py:107`
**函数**: `should_direct_answer()`

**触发条件**（全部满足才直接回答）:
1. `config` 中没有预配置 `tasks`
2. 用户没有 `@` 指定任何子 agent
3. 消息匹配 `META_QUESTION_MARKERS`（中英文问候、元问题、任务状态查询）
4. 或者是简单的 evidence followup
5. 不包含 task intent 标记（build/create/generate/implement 等）

**处理逻辑**:
1. 检查是否为简单问候（`_is_simple_greeting()`）
2. 检查是否为元问题（`META_QUESTION_MARKERS`）
3. 检查是否为最近任务状态查询（`RECENT_TASK_STATUS_MARKERS`）
4. 调用 LLM 生成直接回答（`run_direct_answer()`）

**输出**:
- `True`: Orchestrator 直接回答，流程结束
- `False`: 继续下一优先级

### ⑥ Context Action Answer（上下文动作回答）

**优先级**: 中低
**文件**: `backend/app/agents/orchestrator/_internal/routing/evidence.py:186`
**函数**: `context_action_answer_text()`

**触发条件**:
- 请求包含动作标记（"继续"、"修复"、"修改"等）
- 且包含部署相关标记（"部署"、"发布"、"上线"）
- 但证据显示操作已完成，无需继续

**处理逻辑**:
1. 收集证据包（`collect_evidence_pack()`）
2. 检查是否真的需要继续操作
3. 如果已完成：直接告知无需操作

**输出**:
- `str`: 直接回答文本
- `None`: 需要继续处理

### ⑦ Evidence Context Injection（证据上下文注入）

**优先级**: 中
**文件**: `backend/app/agents/orchestrator/_internal/routing/evidence.py:160`
**函数**: `build_evidence_context_message()`

**触发条件**:
- 请求包含上下文动作标记

**处理逻辑**:
1. 收集历史运行记录（`_load_candidates()`）
2. 收集产物信息（文件列表、预览URL等）
3. 收集部署记录
4. 收集评估结果
5. 格式化为系统消息

**输出**:
- 注入为 `system` message，继续后续处理

### ⑧ Custom Agent Creation（自定义Agent创建）

**优先级**: 中低
**文件**: `backend/app/agents/orchestrator/_internal/routing/custom_agent.py:44`
**函数**: `custom_agent_tool_arguments()`

**触发条件**:
- 请求包含 "agent" 或 "智能体" 或 "代理"
- 且包含 "创建" 或 "新建" 或 "create"

**处理逻辑**:
1. 提取 Agent 名称（`_extract_named_value()`）
2. 提取基础 Agent ID（`_extract_base_agent_id()`）
3. 提取系统提示词（`_extract_named_value()`）
4. 提取能力标签、任务类型等
5. 调用平台工具创建 Agent

**输出**:
- 调用 `create_custom_agent` 工具
- 返回创建结果，流程结束

### ⑨ Tool Loop（工具调用循环）

**优先级**: 中
**文件**: `backend/app/agents/orchestrator/_internal/tools/loop.py:104`
**函数**: `run_orchestrator_tool_loop()`

**触发条件**:
- `tool_calling_enabled(merged_config)` 返回 `True`
- `config.tasks` 为 `None`

**处理逻辑**:
1. 初始化工具规范（`orchestrator_tool_specs()`）
2. 进入工具调用循环（最多 12 次迭代）
3. 调用 LLM 生成工具调用
4. 执行工具（`execute_workspace_tool()`）
5. 收集工具结果
6. 生成最终总结

**输出**:
- 进入工具循环，流程结束

### ⑩ LLM Planner（主要路径）

**优先级**: 低
**文件**: `backend/app/agents/orchestrator/task_planning.py:158`
**函数**: `resolve_tasks()`

**触发条件**:
- 所有前置路由都未命中

**处理逻辑**（按优先级）:

#### a. 直接广播任务（@多个agent）
- 用户提到 2+ agent 名称时
- 创建直接广播任务，跳过 LLM planner

#### b. 纯对话 / Turn-taking 对话任务
- 包含“开始一场辩论 / 利弊讨论 / 圆桌 / 角色扮演 / 轮流 / debate / brainstorm”等标记，且没有文件、代码、部署等产物意图时，进入纯对话路径。
- 默认 `orchestrator_dialogue_llm_control_enabled=true` 时，先由 Orchestrator LLM planner 生成 `dialogue_turn` 计划：参与 Agent、角色 / 立场、最小发言顺序和 no-artifact guard。
- LLM planner 不可用或输出无效时，才回退 legacy dialogue template。
- `dialogue_turn` 任务带 `depends_on` 链确保初始轮次按顺序执行；后续轮次由执行层 LLM decision 动态追加。

#### c. Workspace冲突任务
- 检测到 workspace 文件冲突
- 创建冲突解决任务

#### d. 全栈交付任务（模板）
- 前端开发任务
- 使用模板生成任务计划

#### e. LLM planner 生成任务计划
- 调用 planner LLM（`plan_task_payload()`）
- 输出结构化的 `submit_task_plan` 工具调用
- 包含 `agent_id`、`instruction`、`depends_on`、`priority` 等

#### f. 模板兜底 `_derive_tasks()`
- LLM planner 失败时的兜底方案
- 使用模板生成任务计划

**模板类型**:

1. **全栈交付任务模板**（`delivery.py`）:
   - 适用于前后端开发任务
   - 包含规划、前端开发、后端开发、代码审查四个阶段
   - 优先级：claude-code > opencode-helper > codex-helper

2. **工作区冲突任务模板**（`conflicts.py`）:
   - 适用于文件冲突场景
   - 创建基线文件 → 设计视角修改 → 实现视角修改
   - 用于演示多agent协作处理同一文件

3. **遗留模板**（`legacy.py`）:
   - 通用任务模板
   - 根据请求内容动态生成任务
   - 支持对话、辩论、头脑风暴等场景

**输出**:
- `list[SubTask]`: 任务列表
- `PlannerResolutionError`: 规划失败

### ⑪ Multi-Agent Balancing（多Agent均衡）

**优先级**: 低
**文件**: `backend/app/agents/orchestrator/task_planning.py:341`
**函数**: `balance_requested_multi_agent_plan()`

**触发条件**:
- 任务列表已生成

**处理逻辑**:
1. 单任务→拆分并行任务（如果用户请求多agent）
2. Round-robin 分配（`ordered_agents[offset % len(ordered_agents)]`）
3. 避免自审（`_avoid_self_review_tasks()`）
4. 优先级：claude-code > opencode-helper > codex-helper

**输出**:
- 均衡后的任务列表

### ⑫ Task Execution（任务执行）

**优先级**: 最低
**文件**: `backend/app/agents/orchestrator/execution.py`
**函数**: `_run_static_tasks()` 或 `run_react_loop()`

**触发条件**:
- 任务列表已生成且均衡完成

**处理逻辑**:
1. **ReAct loop**（如果启用）:
   - 动态任务调度
   - 工具调用循环

2. **静态顺序/并行执行**（默认）:
   - 按依赖关系执行任务
   - 每个任务→子agent adapter
   - 产物检查 + 评估 + 重试

3. **群聊消息写入**:
   - 每个子 agent 的输出作为独立 Message 行写入数据库
   - 通过 `OrchestratorGroupMessageWriter` 管理

**输出**:
- 任务执行结果
- 产物文件
- 评估报告

## 关键路由判定逻辑详解

### ④ Platform Fact（classifier.py:105）

采用双重策略：

1. **规则匹配**:
   - 中英文标记字符串（如"群里有哪些agent"、"group agents"）
   - 模型相关标记（"模型"、"model"、"runtime"）
   - 能力相关标记（"能做什么"、"capabilities"）

2. **LLM 分类器**:
   - 规则未命中且 `platform_fact_classifier_enabled` 开启时
   - 调用小模型做意图分类
   - 置信度 ≥ 0.65 才生效

### ⑤ Direct Answer（direct_answer.py:107）

判定条件（全部满足才直接回答）:

```python
def should_direct_answer(config, messages, ...):
    # 1. config 中没有预配置 tasks
    if config.get("tasks") is not None:
        return False
    
    # 2. 用户没有 @ 指定任何子 agent
    if explicit_agent_mentions(agent_ids, user_request):
        return False
    
    # 3. 消息匹配 META_QUESTION_MARKERS
    # 或者是简单的 evidence followup
    if is_evidence_followup_request(normalized):
        return True
    
    # 4. 不包含 task intent 标记
    if has_task_intent(normalized):
        return False
    
    # 5. 简单问候或元问题
    if _is_simple_greeting(normalized):
        return True
    return any(marker in normalized for marker in META_QUESTION_MARKERS)
```

### ⑩ LLM Planner 任务分配（task_planning.py:158）

Planner LLM 收到的上下文包括：

1. 用户请求原文
2. 当前群聊内可运行 agent 的 `planning_profile`（优势、劣势、擅长任务类型）
3. 历史成功/失败记忆
4. recent conversation context（保留 `[Agent: <agent_id>]` 标签）
5. 输出结构化的 `submit_task_plan` 工具调用

Planner 输出后会经过白名单校验。如果出现群聊外 `agent_id`：

1. Orchestrator 追加一次安全 retry 指令，列出唯一合法 agent ids 和非法 ids。
2. retry 仍非法时，按任务类型 remap 到当前群聊内最合适的可运行 Agent。
3. 如果没有可运行子 Agent，返回可读错误，不直接展示 raw `invalid_task_plan`。

## 群聊特有的路由逻辑

### 显式 @mention 路由
- 用户提到 2+ agent 名称时
- 创建直接广播任务
- 跳过 LLM planner

### Turn-taking 检测
- 包含"轮流"、"debate"、"brainstorm"等标记时
- 创建 `dialogue_turn` 类型任务
- 带 `depends_on` 链确保顺序执行

### 群聊消息写入
- 每个子 agent 的输出作为独立 Message 行写入数据库
- 通过 `OrchestratorGroupMessageWriter` 管理

### Agent 可用性过滤
- `scoped_runnable_agent_ids()` 过滤掉冷却中、错误、不可用的 agent
- 硬失败默认冷却 30 分钟（`DEFAULT_RUNTIME_COOLDOWN_SECONDS`）

## 任务流转详细过程

### 阶段1：消息接收与预处理

**输入**: 用户消息（`list[ChatMessage]`）
**处理**:
1. 合并配置（`merged_config`）
2. 标准化配置（`_normalize_stream_config()`）
3. 应用指导安全点（`_apply_guidance_safe_point()`）

**输出**: 预处理后的消息和配置

### 阶段2：路由决策

**输入**: 预处理后的消息
**处理**: 按优先级执行上述12个路由判断
**输出**: 路由决策（直接回答/任务计划/工具调用等）

### 阶段3：任务规划

**输入**: 用户请求、可用agent列表、历史记忆
**处理**:
1. 分析请求类型（实现/讨论/文档等）
2. 选择合适的agent
3. 生成任务计划（`SubTask` 列表）
4. 平衡多agent分配

**输出**: `list[SubTask]`（任务列表）

### 阶段4：任务执行

**输入**: 任务列表、消息历史
**处理**:
1. 按依赖关系排序任务
2. 为每个任务创建子agent adapter
3. 执行任务（`_run_task()`）
4. 收集产物和结果
5. 运行评估（`run_quality_gate()`）

**详细执行流程**（`_run_task()` 函数）:

1. **Agent选择与回退**:
   - 选择执行agent（`_agent_for_attempt()`）
   - 如果agent不可用，尝试fallback agent
   - 记录跳过的agent和原因

2. **工作区快照**:
   - 执行前拍摄工作区快照（`snapshot_workspace()`）
   - 用于后续检测文件变更

3. **群聊消息创建**:
   - 如果启用群聊消息（`_group_messages_enabled()`）
   - 创建子agent消息（`_start_group_message()`）
   - 记录子agent的执行过程

4. **子agent适配器调用**:
   - 获取子agent适配器（`_get_sub_adapter()`）
   - 准备任务消息（`_task_messages()`）
   - 调用子agent的stream方法
   - 收集文本输出、工具调用、产物文件

5. **结果验证与评估**:
   - 产物检查（`_check_attempt_artifacts()`）
   - 评估执行结果（`_run_attempt_evaluation()`）
   - 生成artifact文件块（`_artifact_file_blocks()`）

6. **重试机制**:
   - 检查是否可重试（`can_retry_task()`）
   - 选择fallback agent
   - 记录重试原因

7. **工作区变更检测**:
   - 执行后拍摄工作区快照
   - 检测文件变更（`diff_workspace_snapshots()`）
   - 刷新工作区冲突（`refresh_workspace_conflicts()`）

**输出**: 任务结果、产物文件、评估报告

### 阶段5：结果汇总与响应

**输入**: 任务执行结果
**处理**:
1. 汇总所有任务结果（`_summary_text()`）
2. 生成最终响应
3. 写入数据库（`OrchestratorGroupMessageWriter`）

**输出**: 最终响应（`StreamChunk` 流）

## 群聊特有的路由逻辑

### 显式 @mention 路由

**触发条件**: 用户提到 2+ agent 名称时
**处理逻辑**:
1. 检测显式agent提及（`explicit_agent_mentions()`）
2. 创建直接广播任务，跳过 LLM planner
3. 每个提及的agent都会收到任务

### 纯对话 / Turn-taking 检测与执行

**触发条件**: 包含“开始一场辩论 / 利弊讨论 / 圆桌 / 角色扮演 / 轮流 / debate / brainstorm”等标记，且没有文件、代码、部署等产物意图时。
**处理逻辑**:
1. 检测是否为纯对话任务（`pure_dialogue_requested()`），旧式轮流接力仍会经过 `turn_taking_requested()`。
2. 默认调用 Orchestrator LLM planner 生成 `dialogue_turn` 初始计划。
3. LLM 计划会经过当前群聊 Agent 白名单和 no-artifact guard 校验；非法 Agent、文件、preview、deploy、工具任务会被拒绝或规范化。
4. LLM 不可用或输出无效时，legacy template 生成最小 `dialogue_turn` 兜底计划。

**对话任务执行流程**（`_internal/execution/dialogue_llm.py` + `_internal/execution/dialogue.py`）:

1. **对话检测**:
   - `dialogue_requires_sequential()`: 检测是否为顺序对话
   - 要求所有任务都是 `dialogue_turn` 类型

2. **LLM 动态轮次生成**:
   - `maybe_next_dialogue_turn_with_model()`: 每轮 child message 完成后调用 LLM 生成 `dialogue_decision`
   - LLM 决定继续、下一位 Agent、下一轮焦点或进入总结
   - 结果写入 run detail `dialogue_decision`
   - 当前群聊 Agent 白名单、no-artifact guard 和最大轮次限制（默认 8 轮）仍是硬约束

3. **辩论 / 圆桌总结**:
   - `compute_dialogue_judgement_with_model()`: 对话结束后调用 Orchestrator LLM 生成 `dialogue_judgement`
   - 辩论输出核心争点、双方最强论据、薄弱点、胜负或平局、裁判理由
   - 圆桌 / panel 输出共识、分歧和建议，不输出胜负
   - `compute_debate_judgement()` 仅作为 LLM 不可用或输出无效时的 fallback

4. **对话轮次控制**:
   - 检测是否为简短对话（"只要一轮"等）
   - 检测是否为多轮对话（"三轮"等）
   - 动态调整最大轮次

5. **参与者管理**:
   - `_participant_order()`: 确定参与者顺序
   - `_completed_dialogue_tasks()`: 统计已完成轮次
   - 确保每个参与者都有发言机会

### 群聊消息写入

**处理逻辑**:
1. 每个子 agent 的输出作为独立 Message 行写入数据库
2. 通过 `OrchestratorGroupMessageWriter` 管理
3. 支持子agent消息嵌套（parent_agent_message_id）

### Agent 可用性过滤

**处理逻辑**:
1. `scoped_runnable_agent_ids()` 过滤掉冷却中、错误、不可用的 agent
2. 硬失败默认冷却 30 分钟
3. 支持动态冷却时间设置

## 子Agent接收的输入输出

### 子Agent输入

每个子agent（如 claude-code、codex-helper、opencode-helper）接收：

1. **系统提示词**: `system_prompt`（从配置继承或自定义）
2. **任务指令**: `task.instruction`（从任务计划中提取）
3. **消息历史**: `messages`（上下文）
4. **工具规范**: `tool_specs`（可用工具列表）
5. **工作区路径**: `workspace_path`（沙箱目录）

### 子Agent输出

每个子agent返回：

1. **文本输出**: 代码、文档、分析等
2. **工具调用**: 文件创建、命令执行等
3. **产物文件**: 保存在 `workspace_path` 中
4. **执行状态**: 成功/失败/部分完成

## 关键配置项

### 路由相关配置

```python
{
    # 澄清门控
    "clarification_gate_enabled": True,  # 是否启用澄清门控
    "auto_clarification_max_questions": 3,  # 自动澄清最大问题数
    "grill_max_questions": 8,  # /grill-me 最大问题数
    
    # 平台事实路由
    "platform_fact_classifier_enabled": False,  # 是否启用LLM分类器
    
    # 直接回答
    "answer_model_backend": "claude",  # 直接回答使用的模型
    "orchestrator_answer_config": {},  # 直接回答配置
    
    # LLM规划
    "llm_planning": True,  # 是否启用LLM规划
    "planner_model_backend": "claude",  # 规划器使用的模型
    "planner_fallback_to_template": True,  # 规划失败是否回退到模板
    
    # 工具循环
    "tool_calling_enabled": True,  # 是否启用工具调用
    "tool_max_iterations": 12,  # 工具调用最大迭代次数
    
    # 任务执行
    "orchestrator_parallel_enabled": False,  # 是否启用并行执行
    "max_task_attempts": 3,  # 任务最大重试次数
    
    # 质量门控
    "max_repair_rounds": 3,  # 最大修复轮数
}
```

## 错误处理

### 规划失败

1. **PlannerResolutionError**: LLM planner 输出无法使用
   - 尝试回退到模板（`_derive_tasks()`）
   - 如果仍然失败，返回错误

2. **直接回答回退**:
   - 如果 `should_direct_answer_after_planner_error()` 返回 `True`
   - 切换到直接回答模式

3. **Fallback 执行**:
   - 如果 `_has_fallback(merged_config)` 返回 `True`
   - 执行 fallback 逻辑

### 执行失败

1. **任务重试**:
   - 检查 `can_retry_task()`
   - 选择 fallback agent（`_task_fallback_agent_ids()`）
   - 重新执行任务

2. **冷却机制**:
   - 硬失败默认冷却 30 分钟
   - 通过 `mark_runtime_cooldown()` 标记

3. **质量门控**:
   - 浏览器验证失败时触发修复
   - 最多修复 3 轮（`max_repair_rounds`）

## 性能优化

### 缓存机制

1. **Agent 可用性缓存**:
   - `runtime_cooldown_status()` 使用 `time.monotonic()` 缓存
   - 自动过期清理

2. **证据收集缓存**:
   - 证据包收集后缓存
   - 避免重复收集

### 并行执行

1. **任务并行**:
   - 无依赖关系的任务可并行执行
   - 通过 `parallel_enabled` 配置控制

2. **工具并行**:
   - 多个工具调用可并行执行
   - 通过 `parallel_max_concurrency` 控制并发数

## 监控与调试

### 日志记录

1. **内存事件记录**:
   - `memory_start_run()`: 记录运行开始
   - `memory_record_event()`: 记录关键事件
   - `memory_finish_run()`: 记录运行结束

2. **任务结果记录**:
   - `memory_record_task_started()`: 记录任务开始
   - `memory_record_task_result()`: 记录任务结果

### 调试工具

1. **路由过程块**:
   - `_route_process_chunks()`: 生成路由过程信息
   - 包含路由类型、状态、详情

2. **执行过程块**:
   - `_task_running_step()`: 任务执行中
   - `_task_result_step()`: 任务结果
   - `_skipped_task_step()`: 跳过的任务

## 质量门控详细说明

### 浏览器预览质量门控

**文件**: `backend/app/agents/orchestrator/quality.py`
**函数**: `run_quality_gate()`

**触发条件**:
- 用户请求包含前端开发相关内容
- 请求包含部署、预览、质量验收等标记

**处理流程**:

1. **入口文件检测**:
   - 查找工作区中的 `index.html`（`_find_preview_entry()`）
   - 如果未找到，触发修复任务

2. **浏览器验证**:
   - 调用平台工具 `verify_web_preview`
   - 检查页面是否可访问
   - 检查是否有JavaScript错误
   - 检查移动端响应式

3. **修复循环**:
   - 最多修复 3 轮（`max_repair_rounds`）
   - 每轮修复后重新验证
   - 记录修复历史

4. **部署健康检查**:
   - 检查部署状态（`deployment_health_result()`）
   - 验证预览URL是否可访问
   - 检查端口是否正确

**输出**:
- 质量通过：生成通过报告
- 质量失败：生成失败报告和修复建议

### 一键容器部署质量门控

**触发条件**:
- 用户请求包含容器部署相关内容
- 配置中启用一键容器部署

**处理流程**:
1. 检查容器部署配置
2. 执行部署工具
3. 验证部署状态
4. 生成部署报告

## 文件变更检测

### 工作区快照

**文件**: `backend/app/agents/orchestrator/workspace_changes.py`

**处理流程**:
1. **快照拍摄**:
   - `snapshot_workspace()`: 拍摄工作区快照
   - 记录文件列表和修改时间

2. **变更检测**:
   - `diff_workspace_snapshots()`: 比较快照差异
   - 识别新增、修改、删除的文件

3. **冲突刷新**:
   - `refresh_workspace_conflicts()`: 刷新工作区冲突
   - 检测多agent修改同一文件的情况

### 产物检查

**文件**: `backend/app/agents/orchestrator/artifacts.py`

**处理流程**:
1. **产物提取**:
   - `extract_artifact_paths_from_text()`: 从文本中提取产物路径
   - 识别文件扩展名和路径

2. **产物验证**:
   - `check_attempt_artifacts()`: 检查尝试的产物
   - 验证文件是否存在且有效

3. **产物最终化**:
   - `finalize_artifact_candidates()`: 最终化产物候选
   - 确定最终的产物列表

## 总结

Orchestrator 的路由流程是一个精心设计的瀑布式优先级系统，从最高优先级的澄清门控到最低优先级的任务执行，每一层都可以短路返回。这种设计确保了：

1. **用户体验优先**: 简单问题直接回答，无需等待任务规划
2. **需求明确性**: 通过澄清门控确保需求足够明确
3. **上下文感知**: 通过证据注入和历史记录提供上下文
4. **灵活性**: 支持多种路由策略和回退机制
5. **可扩展性**: 易于添加新的路由规则和处理逻辑

整个系统通过配置驱动，可以根据不同场景灵活调整行为，同时保持了良好的错误处理和性能优化机制。
