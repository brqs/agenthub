# Orchestrator Presentation Collapse Spec

> 状态：Implemented MVP
> 最后更新：2026-06-08
> 范围：Orchestrator 与子 Agent 消息的用户可见展示分区、执行过程折叠、成员 summary 与全局 final answer 标记。

## 1. 目标

前端需要稳定区分“执行过程”和“最终回答”。后端必须提供结构化展示标记，前端不能依赖文案、最后一个 text block 或工具名猜测。

目标展示：

- `process`、tool call、agent switch、中间执行 text 默认进入折叠区。
- 成员 Agent 的阶段性总结常显。
- Orchestrator 的全局 final answer 常显。
- direct answer / evidence answer 不创建执行折叠区，只输出 final answer。

`process` block 只表示公开过程摘要，不表示 hidden chain-of-thought。

## 2. Presentation Metadata

每个 ContentBlock 可带可选字段：

```json
{
  "presentation": {
    "role": "execution_process",
    "collapsible": true,
    "group_id": "execution-main",
    "boundary": "execution_start",
    "closes_group_id": null,
    "label": "执行过程"
  }
}
```

字段：

- `role`：
  - `execution_process`：公开过程摘要，例如 `process` block。
  - `tool_trace`：工具调用过程，例如 Read/Edit/Bash/Grep/platform tool。
  - `execution_text`：成员 Agent 执行过程中的中间说明文本。
  - `artifact_evidence`：file / preview / deployment / workflow 等结构化证据。
  - `agent_summary`：成员 Agent 当前阶段的结果总结。
  - `final_answer`：Orchestrator 面向用户的全局最终回答。
- `collapsible`：该 block 是否默认进入折叠区。
- `group_id`：折叠组 id，默认 `execution-main`。
- `boundary`：
  - `execution_start`：该 block 是执行过程折叠组的开始。
  - `answer_start`：该 block 是常显回答区的开始。
- `closes_group_id`：常显回答区开始时关闭的执行组。
- `label`：前端折叠标题的可读文案。

## 3. 默认规则

后端应尽量提供 `presentation`。旧消息或缺失 metadata 时，前端使用兼容规则：

- `process`、`tool_call`、`agent_switch` 默认 `collapsible=true`。
- `text` 默认常显。
- `file`、`web_preview`、`deployment_status` 默认按普通证据渲染；有 marker 时按 marker 分组。

Orchestrator final answer text 必须标记：

```json
{
  "presentation": {
    "role": "final_answer",
    "collapsible": false,
    "boundary": "answer_start",
    "closes_group_id": "execution-main"
  }
}
```

子 Agent 阶段总结 text 必须标记：

```json
{
  "presentation": {
    "role": "agent_summary",
    "collapsible": false,
    "boundary": "answer_start",
    "closes_group_id": "execution-main"
  }
}
```

子 Agent 原始流式文本默认属于执行过程：

```json
{
  "presentation": {
    "role": "execution_text",
    "collapsible": true,
    "group_id": "execution-main"
  }
}
```

执行层在子任务结束前运行实质输出合同；只有通过合同后的阶段性总结才标记为 `agent_summary`。如果第一次原始输出只是“请登场 / 已完成 / 我来主持”等无效内容，它仍可保留在折叠执行区，但不得升级为常显 summary。纠偏通过后，`agent_summary` 只展示清洗后的实质段落。

对 `dialogue_turn`：

- 每一轮 child message 的原始流式文本仍标记为 `execution_text`，默认折叠。
- 该轮通过实质输出合同后追加一个常显 `agent_summary`，代表本轮正式发言或阶段结论。
- 同一 Agent 的下一轮发言必须生成新的 child message 和新的 `agent_summary`。
- Orchestrator final answer 只做主持总结，不把所有成员发言重新吞并进父消息。

执行过程 block 标记示例：

```json
{
  "presentation": {
    "role": "tool_trace",
    "collapsible": true,
    "group_id": "execution-main"
  }
}
```

## 4. Stream / Persistence

- 不新增 SSE event type。
- `block_start.metadata.presentation` 进入正在流式渲染的 block。
- `tool_call` / `tool_result` event 可通过 `metadata.presentation` 标记 tool block。
- `StreamContentAccumulator` 必须把 `presentation` 持久化到 ContentBlock。
- 对外 ContentBlock union 不新增类型，只给现有 block 增加可选字段。

## 5. Frontend Rendering

前端根据 `presentation` 分组：

- streaming 中执行区默认展开。
- terminal 状态 `done / error / interrupted` 后执行区默认折叠。
- `agent_summary` 和 `final_answer` 始终常显。
- 折叠区标题默认：
  - Orchestrator：`执行过程`
  - 子 Agent：`思考与执行`
- 折叠区显示 step/tool 数量和状态。

## 6. Verification

本地测试覆盖：

- persisted content 保留 `presentation`。
- direct answer 只有 `final_answer`。
- Orchestrator final text 是 `final_answer`。
- 子 Agent 最后 summary text 是 `agent_summary`。
- process/tool trace 是 collapsible execution group。
- 旧消息无 `presentation` 时仍兼容渲染。

已落地实现：

- `PresentationMetadata` 已进入后端 schema、OpenAPI 与前端生成类型。
- `block_start.metadata.presentation`、`tool_call.metadata.presentation` 与 `tool_result.metadata.presentation` 均会持久化到 ContentBlock。
- 前端会把可折叠 execution block 归入执行过程折叠组；streaming 默认展开，terminal 默认折叠。
- 折叠标题区展示步骤数量、工具数量、block 数量和当前可见状态。
- `agent_summary` 与 `final_answer` 按常显 block 渲染，不进入折叠组。

Live E2E scenario：

```text
presentation_collapse_markers_smoke
```

验收：

- SSE / persisted message 有 `presentation.role`。
- 至少一个 block 有 `boundary=execution_start`。
- 至少一个 block 有 `boundary=answer_start`。
- 至少一个子 Agent message 有 `agent_summary`。
- Orchestrator 最终 text 有 `final_answer`。
- final answer / agent summary 无 `ReAct step`、`Observation:`、`Action:`、`call_`、raw stderr、workspace absolute path。
