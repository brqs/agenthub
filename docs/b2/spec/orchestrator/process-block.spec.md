# Orchestrator Process Block Spec

> Owner: B2
> Related: [markdown-preservation-feedback.spec.md](markdown-preservation-feedback.spec.md), [message-attribution.spec.md](message-attribution.spec.md), [core.spec.md](core.spec.md)
> Status: Implemented MVP
> Last updated: 2026-06-05

## 1. Summary

已新增正式 `process` ContentBlock，用于展示 Orchestrator 的“整理后的执行过程摘要”。它对齐 Claude / OpenCode 类产品里的“过程 + 最终回答”体验，但只展示可公开的执行事实，不展示隐藏思维链、raw ReAct trace、prompt、stderr、call id 或完整 tool output。

`process` block 不替代 memory、run detail、tool block、artifact block 或 raw execution summary。它只是普通聊天流中的安全过程面板，放在最终 response presentation text 之前。

## 2. Public Contract

### 2.1 ProcessBlock

```ts
type ProcessBlock = {
  type: "process";
  agent_id?: string | null;
  title: string;
  status: "running" | "done" | "partial" | "error";
  default_collapsed: boolean;
  steps: ProcessStep[];
  summary?: string | null;
  metadata?: Record<string, unknown>;
};
```

### 2.2 ProcessStep

```ts
type ProcessStep = {
  id?: string | null;
  label: string;
  kind:
    | "routing"
    | "planning"
    | "dispatch"
    | "tool"
    | "review"
    | "evaluation"
    | "workflow"
    | "deployment"
    | "artifact"
    | "repair"
    | "summary";
  status: "done" | "running" | "error" | "skipped";
  detail?: string | null;
  agent_id?: string | null;
};
```

`status="partial"` 用于部分完成、部分未执行、review / evaluation 仍需注意等场景，避免最终过程摘要误报 done。

## 3. Streaming / Persistence Contract

- `StreamChunk.BlockType` 增加 `"process"`。
- 不新增 SSE event；复用 `block_start` / `delta` / `block_end`。
- `block_start(process)` 放置基础 payload；`delta.metadata.process_delta` 持续 upsert 公开步骤或设置 summary。
- `process_delta` 仅支持 `upsert_step` 和 `set_summary` 两类操作，降低前端消费复杂度。
- `StreamContentAccumulator` 在 `block_start(process)` 时创建 block，并在后续 delta 中原地更新，`block_end` 后保留完整结果。
- `MessageOut`、`SendMessageRequest` 和 OpenAPI `ContentBlock` union 增加 `ProcessBlock`。
- `agent_id` 默认是 `orchestrator`，但保留 optional 字段以符合既有 block 归属契约。

## 4. Orchestrator Output Rules

输出顺序固定：

1. 子 Agent / tool / artifact / evaluation / deployment 等既有 blocks 保持原有顺序。
2. `process` block 尽早出现，并通过 process delta 持续更新。
3. 最终 answer 继续使用 response presentation 层。

覆盖路径：

- platform fact：输出 process start / route delta / process end，再输出事实回答 text。
- direct answer：输出 process start / route delta / process end，再进入 direct answer stream。
- custom-agent tool route：保留 tool call/result，再在最终结果前输出 process block。
- static / parallel / ReAct / tool-loop：任务执行中持续 upsert planning、task、tool、review/evaluation/artifact/deployment 等公开步骤，收尾时 set summary。

## 5. Safety Rules

`process` block 只能来自 deterministic facts，不做 LLM 二次加工。所有 `title`、`label`、`detail`、`summary`、`metadata` 文本必须经过 sanitizer。

禁止出现：

- `ReAct step`
- `Observation:`
- `Action:`
- `Tools:`
- `result ok`
- `call_`
- task id / call id
- planner/debug prompt
- raw stderr
- 完整 tool output
- 长代码片段或完整子 Agent Markdown 正文

尺寸限制：

- `steps` 最多 20 条。
- `label` 建议不超过 80 字符。
- `detail` 建议不超过 240 字符。
- `summary` 建议不超过 400 字符。
- artifact / URL / validation 列表只取最关键条目，超出后汇总为数量。

## 6. Frontend MVP Boundary

本轮前端只做最小兼容和基础展示：

- 手写 `ContentBlock` 类型和 generated OpenAPI types 同步 `process`。
- `chatStore` / `useStream` 能从 `block_start(process)` 创建 process block，不误写成 text block。
- `ContentRenderer` 新增基础 `ProcessBlock` renderer，显示紧凑过程面板。
- `default_collapsed` 字段先保留，不实现展开/折叠状态管理。

后续交互增强：

- 折叠/展开。
- step 分组。
- 与 run detail / review timeline / deployment history 联动。

## 7. Test Plan

Backend targeted tests:

- `StreamChunk(block_type="process")` 可序列化。
- `StreamContentAccumulator` 能持久化 `block_start(process)` + 多个 process delta 后的完整 `process` payload。
- `MessageOut` / OpenAPI schema 包含 `ProcessBlock` union。
- platform fact / direct answer 输出顺序为 `process -> text`。
- static / parallel / ReAct / tool-loop 在执行过程中产生 process delta，最终 text 仍最后输出。
- pending task 会让 process status 为 `partial`，且 step 显示未执行。
- `orchestrator_process_block_enabled=false` 时不输出 process block。
- process block 不包含 forbidden terms。

Frontend targeted tests:

- `chatStore` / `useStream` 创建并保留 process block。
- `ContentRenderer` 渲染 process panel，`UnknownBlock` 不再接管 `process`。
- 长 label/detail 与小屏布局不溢出。

本轮不以完整 backend pytest 作为 Process Block 唯一门禁；当前仓库仍有 external runtime auth / stream integration 类非 presentation 失败。Process Block 实现时应记录 targeted gate 与 full pytest 剩余失败边界。

## 7.1 Implementation Evidence

2026-06-05 已落地后端契约、stream persistence、OpenAPI/shared types 和前端基础 renderer：

- 后端：`StreamChunk.BlockType`、`ContentBlock` union、`ProcessBlock` / `ProcessStep` schema、`StreamContentAccumulator` 均支持 `process`。
- Orchestrator：platform fact、direct answer、custom-agent route、fallback、static / parallel execution、ReAct 和 native tool-loop 会在最终用户可见 text 前输出 deterministic process block；`orchestrator_process_block_enabled=false` 时完全关闭。
- Safety：process block 只由结构化 facts 生成，不走 LLM polish；文案经过 forbidden term sanitizer，限制 step/label/detail/summary 长度。
- 前端：基础 `ProcessBlock` 面板由前序 MVP 提供；本轮不新增前端实现，后续由前端消费 process delta。
- 本地门禁：backend targeted `114 passed`；tool/OpenAPI/config targeted `86 passed`；backend Ruff/Mypy passed；`git diff --check` passed。
- 部署证据：后端 PID `858990 -> 1037330`；`alembic current` 为 `7e8f9012abcd (head)`；本机与公网 `/health` 均为 `{"status":"ok"}`；已执行 `uv run python -m app.seeds.seed_agents`。
- 公网 smoke：report `/tmp/agenthub_process_block_smoke_report.json`，SSE `/tmp/agenthub_process_block_smoke_sse.jsonl`，`passed=true`。`direct_answer_identity` conversation `bfa2571a-34ba-48f4-bc09-c4aa385212bb`、message `5ea7f3d7-29db-4a04-90de-7d335ee3d8aa` 输出 block types `["process", "text"]`；`light_orchestrator_task` conversation `fa26dd50-3168-4f34-8fb2-b14dc0eec45b`、message `fa239880-ac71-41e6-9961-7258410b6e59`、run `ee57bc30-cb22-4fa3-acab-2d8568371d7c` 输出 block types `["task_card", "text", "text", "process", "text"]`。
- Smoke 断言：两个场景均满足 `process_before_final_text=true`，final text 与 process block 均无 forbidden terms；本轮仍不执行全功能公网 E2E。

2026-06-05 追加流式 process 后端升级证据：

- 本地门禁：stream / orchestrator / ReAct / response presentation / quality targeted `114 passed`；tool / conversation / agent config targeted `86 passed`；backend Ruff/Mypy passed；`git diff --check` passed。
- 部署证据：后端 PID `1152309 -> 1155645`；`alembic current` 为 `7e8f9012abcd (head)`；已执行 `seed_agents`；本机与公网 `/health` 正常。
- 公网 smoke：report `/tmp/agenthub_streaming_process_report.json`，SSE `/tmp/agenthub_streaming_process_sse.jsonl`，`passed=true`。`direct_answer_identity` conversation `7c9738d7-b107-4ef1-851d-2d0b59517c3a`、message `24afb2da-3290-4b20-95ef-51116c2043a0` 输出 `process_delta_count=1`；`light_task_streaming_process` conversation `563d4d19-b97f-4cb3-8c48-1222c45d76f9`、message `4213841d-0e9e-404c-8c5e-4f12db34c593` 输出 `process_delta_count=7`。
- Smoke 断言：SSE 中存在 `delta.metadata.process_delta`；persisted message 有完整 process block；process step ids 为公开稳定 id，未出现内部 task/call id；final text 与 process block 均无 forbidden terms。

## 8. Non-goals

- 不展示 hidden thinking。
- 不恢复 raw ReAct trace 到普通聊天流。
- 不替代 run detail / memory / tool block / artifact block。
- 前端实时 process renderer 不在 B2 本轮实现范围内。
- 不做折叠交互。
- 不执行全功能公网 E2E；实现后只要求普通问答和轻量 Orchestrator 任务 smoke。
