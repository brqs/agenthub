# Agent-to-Agent Review Thread 前端交接说明

> 用途：B2 Agent-to-Agent Review Thread 后端 MVP 与前端产品化对接。
> 最后核对：2026-06-03

## 当前结论

B2 后端侧已完成 Review Thread 的核心链路，前端不需要再等待新的后端能力即可开始产品化：

- `implementation -> review -> repair` 已支持。
- `review_outcome` 已解析并进入 attempt、summary 和 memory event。
- run detail / memory payload 已暴露 `task_type`、`review_of`、`handoff_reason`、`review_outcome`。
- 顺序执行和并行 DAG 执行路径下，`failed` / `needs_repair` review 都会动态追加 repair task。
- repair task 只使用当前群聊成员，不会引入新 Agent。
- P1-3 公网 live E2E 已通过。

前端剩余工作是把这些结构化元数据展示成用户能感知的 review / handoff timeline，而不是继续把它当作普通 Orchestrator 总结文本。

## 后端可用数据

### 消息流与持久化消息

消息 ContentBlock 已支持 block 级 `agent_id`。Orchestrator 顶层消息仍是 `message.agent_id="orchestrator"`，但子 Agent 的 text / code / tool block 会带真实 `block.agent_id`。

前端应继续复用 [orchestrated-message-rendering.spec.md](spec/orchestrated-message-rendering.spec.md) 的分组规则：

- Orchestrator plan / summary 显示为 Orchestrator。
- implementation / review / repair 子 Agent 输出按 `block.agent_id` 分段。
- tool block 跟随自己的 `agent_id`。
- 不用正文中的 `@agent` header 做归属判断。

### Run Detail API

开发环境可读取 Orchestrator run detail：

```text
GET /api/v1/conversations/{conv_id}/orchestrator-runs?limit=20
GET /api/v1/conversations/{conv_id}/orchestrator-runs/{run_id}
```

`tasks[]` 中和 Review Thread 相关的字段：

```ts
type OrchestratorTask = {
  task_id: string;
  agent_id: string;
  title: string;
  task_type: 'implementation' | 'review' | 'repair' | string;
  review_of: string[];
  handoff_reason?: string | null;
  final_state: string;
  depends_on: string[];
};
```

`attempts[]` 中和 Review Thread 相关的字段：

```ts
type OrchestratorTaskAttempt = {
  task_id: string;
  agent_id: string;
  state: string;
  text_preview: string;
  review_outcome?: 'passed' | 'failed' | 'needs_repair' | 'unknown' | string | null;
  artifact_paths: string[];
  missing_artifact_paths: string[];
};
```

`events[]` 可用于补充时间线证据：

```ts
type OrchestratorRunEvent = {
  event_type: string;
  task_id?: string | null;
  agent_id?: string | null;
  payload: Record<string, unknown>;
};
```

Review Thread 重点事件：

- `agent_review_completed`
- `agent_review_repair_scheduled`

## 建议前端体验

目标是让用户看到“一个 Agent 交付，另一个 Agent 复审，发现问题后交回修复”的协作感。

建议新增一个轻量 Review Thread / Handoff Timeline 区域，可放在 Orchestrator 消息底部或 run detail 抽屉中：

- Implementation：显示实现 Agent、任务标题、产物路径、完成状态。
- Review：显示 reviewer、被 review 的 task、`review_outcome`、关键 review 摘要。
- Repair：显示 repair Agent、来源 review、handoff reason、修复状态。
- Summary：沿用 Orchestrator final summary 中的 `review_of`、`handoff`、`review outcome` 信息。

视觉语义建议：

- `passed`：通过态。
- `needs_repair`：需要修复态，后面应能看到 repair task。
- `failed`：失败态，后面应能看到 repair task 或最终失败说明。
- `unknown`：降级态，不阻断消息渲染。

## 前端实现建议

建议影响文件：

- `frontend/src/lib/types.ts`
- `frontend/src/lib/adapters/conversations.ts`
- `frontend/src/hooks/useOrchestratorRuns.ts`
- `frontend/src/components/chat/OrchestratedMessageBubble.tsx`
- `frontend/src/components/chat/ReviewThreadTimeline.tsx`
- `frontend/src/components/chat/reviewThreadModel.ts`
- `frontend/src/components/chat/reviewThreadModel.test.ts`

建议先做纯函数模型，再接 UI：

```ts
type ReviewThreadItem =
  | { kind: 'implementation'; taskId: string; agentId: string; title: string; state: string }
  | { kind: 'review'; taskId: string; agentId: string; reviewOf: string[]; outcome: string; summary: string }
  | { kind: 'repair'; taskId: string; agentId: string; reviewOf: string[]; handoffReason?: string | null; state: string };
```

构建规则：

- 从 `tasks[]` 按 `task_type` 找出 implementation / review / repair。
- 用 `review_of` 建立 review -> implementation 和 repair -> review 的关系。
- 用同 task_id 的最新 attempt 读取 `review_outcome` 和 `text_preview`。
- 如果缺 run detail，UI 只显示普通分组消息，不报错。
- 如果同一个 review 后没有 repair，但 outcome 是 `needs_repair` / `failed`，显示“等待修复/未调度”降级状态。

## 联调入口

公网后端：

```text
http://111.229.151.159:8000
```

P1-3 已通过的 live E2E 证据：

```text
scenario: p1_review_thread_repair
report: /tmp/agenthub_p1_review_thread_report.json
sse: /tmp/agenthub_p1_review_thread_sse.jsonl
conversation_id: 5d0373e4-3801-4242-b812-f03ddacd3fb1
agent_message_id: b694d579-cb62-4dbd-83c6-8434a6e49cf8
passed: true
```

如果前端要重新生成证据，可由 B2 侧临时开启 review config 后运行：

```text
cd backend
AGENTHUB_E2E_BASE_URL=http://111.229.151.159:8000 AGENTHUB_E2E_SCENARIO=p1_review_thread_repair uv run python scripts/orchestrator_live_e2e.py
```

## 验收标准

- Orchestrator 群聊消息中，implementation / review / repair 的文本和工具调用按真实子 Agent 分段展示。
- Timeline 能显示至少一个 `review` task 和一个动态 `repair` task。
- Review item 能显示 `review_outcome=needs_repair`。
- Repair item 能显示它对应的 `review_of` 或 handoff 来源。
- Timeline 使用当前群聊 Agent 信息展示名称/头像，未知 Agent 有文本兜底。
- 缺少 run detail 或 events 时，聊天主消息仍正常展示。
- 刷新页面后，持久化 message content 和 run detail 仍能重建同一条 timeline。
- 前端测试至少覆盖 review model 构建、缺字段降级、message block 分组兼容。

## B2 边界

B2 已交付后端链路、结构化元数据和 live E2E 证据；本交接后的工作属于前端产品化范围。若前端发现字段缺失或 API 在非开发环境不可见导致正式展示受限，再由前端提出具体契约变更，B1 / B2 协同确认是否需要开放生产级 run detail API。
