# Orchestrator Spec Package

> 目的：作为 Orchestrator 相关 spec 的包级入口，区分当前契约和当前验证报告。
>
> 状态：Current package index
> 最后更新：2026-06-08

---

## 1. Package 结构

| 文档 | 状态 | 作用 |
|---|---|---|
| [core.spec.md](core.spec.md) | Current contract | Orchestrator 主行为契约：调度、DAG 并行、summary、失败处理、preview 边界 |
| [task-planning.spec.md](task-planning.spec.md) | Current contract | direct answer、direct mention、LLM planner、legacy fallback、DAG 依赖语义 |
| [command-fulfillment.spec.md](command-fulfillment.spec.md) | Backend MVP implemented | 显式命令逐项履约、平台 preview/verify/deploy 闭环和 final summary 不误报 |
| [context-routing.spec.md](context-routing.spec.md) | Backend hardening implemented + Live E2E Passed | 多轮追问、workspace/run evidence answer 和继续/修复命令 evidence pack 注入 |
| [clarification-gate.spec.md](clarification-gate.spec.md) | Implemented MVP | Orchestrator 进入任务规划和子 Agent 调度前的结构化需求澄清闸门 |
| [tool-calling.spec.md](tool-calling.spec.md) | Current contract | `dispatch_agent`、workspace tools、preview/verify、自建 Agent 与 deployment platform tools |
| [memory-context.spec.md](memory-context.spec.md) | Current contract | Orchestrator structured memory 与上下文注入设计 |
| [workspace-conflict.spec.md](workspace-conflict.spec.md) | Current contract | Workspace snapshot、file changes、同一 run 内冲突检测 |
| [message-attribution.spec.md](message-attribution.spec.md) | Current contract | Orchestrator 合流 stream 中 block 归属与真实 Agent 子消息后端契约 |
| [process-block.spec.md](process-block.spec.md) | Implemented MVP | 用户可见 structured process ContentBlock，展示公开执行事实 |
| [presentation-collapse.spec.md](presentation-collapse.spec.md) | Planned for implementation | 执行过程折叠、成员 summary 与 Orchestrator final answer 展示标记 |
| [agent-review-thread.spec.md](agent-review-thread.spec.md) | Implemented MVP + Live E2E Passed | Agent-to-Agent review、handoff、repair thread |
| [native-deployment.execution.spec.md](native-deployment.execution.spec.md) | Implemented hardening MVP | Orchestrator 原生部署 tool、container E2E、deployment repair/redeploy |
| [live-e2e-report.spec.md](live-e2e-report.spec.md) | Implemented report | 真实部署链路、deployment repair/redeploy、自建 Agent 工具白名单 E2E 证据 |
| [evaluation-reflection.spec.md](evaluation-reflection.spec.md) | Current contract | 通用 Evaluation / Reflection：“生成 -> 验证 -> 修复 -> 再验证”闭环 |
| [markdown-preservation-feedback.spec.md](markdown-preservation-feedback.spec.md) | Backend MVP implemented | 用户可见 Orchestrator trace / observation / final summary 展示边界 |

---

## 2. 阅读顺序

修改 Orchestrator 主执行流：

1. [core.spec.md](core.spec.md)
2. [task-planning.spec.md](task-planning.spec.md)
3. [command-fulfillment.spec.md](command-fulfillment.spec.md)
4. [clarification-gate.spec.md](clarification-gate.spec.md)
5. [workspace-conflict.spec.md](workspace-conflict.spec.md)
6. [live-e2e-report.spec.md](live-e2e-report.spec.md)

修改 Orchestrator 需求澄清 / 代码前追问：

1. [clarification-gate.spec.md](clarification-gate.spec.md)
2. [context-routing.spec.md](context-routing.spec.md)
3. [task-planning.spec.md](task-planning.spec.md)
4. [memory-context.spec.md](memory-context.spec.md)
5. [markdown-preservation-feedback.spec.md](markdown-preservation-feedback.spec.md)

修改 Orchestrator tools：

1. [tool-calling.spec.md](tool-calling.spec.md)
2. [core.spec.md](core.spec.md)
3. [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

修改 Orchestrator memory：

1. [memory-context.spec.md](memory-context.spec.md)
2. [core.spec.md](core.spec.md)

修改 Orchestrator 合流消息归属：

1. [message-attribution.spec.md](message-attribution.spec.md)
2. [core.spec.md](core.spec.md)
3. [../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)

修改 Orchestrator 用户可见回复：

1. [markdown-preservation-feedback.spec.md](markdown-preservation-feedback.spec.md)
2. [process-block.spec.md](process-block.spec.md)
3. [presentation-collapse.spec.md](presentation-collapse.spec.md)
4. [message-attribution.spec.md](message-attribution.spec.md)
5. [memory-context.spec.md](memory-context.spec.md)

修改 Orchestrator 原生部署：

1. [native-deployment.execution.spec.md](native-deployment.execution.spec.md)
2. [command-fulfillment.spec.md](command-fulfillment.spec.md)
3. [tool-calling.spec.md](tool-calling.spec.md)
4. [../deployment-release-backend.execution.spec.md](../deployment-release-backend.execution.spec.md)
5. [live-e2e-report.spec.md](live-e2e-report.spec.md)

---

## 3. 当前边界

- 当前默认主链是 `llm_planning=true` + 静态 DAG 并行 executor。
- 通用 Evaluation / Reflection Phase 2 MVP 已实现；网页 preview/browser verify、Workflow validation + allowlist dry-run、PPT outline、受控 test runner 和 deployment health 已接入 evaluator / health gate 语义，workflow runtime 与 deployment repair/redeploy live E2E 已通过。
- DAG 并行是 Orchestrator execution 能力，不是 platform tool。
- Preview / browser verify / create custom agent / deployment 是 Orchestrator 可调用的平台 tool，但实际执行由平台 service 完成。
- 自建 Agent 的显式 `allowed_tools` 已进入 tool schema；builtin native/MCP 最小权限 MVP 已实现并通过 live E2E，external runtime 权限映射仍属后续 hardening。
- Agent-to-Agent review thread MVP 已实现：关键 implementation task 可自动 handoff 给其他 Agent review，并在 failed / needs_repair outcome 下顺序或并行追加 repair task；前端 handoff timeline 交接见 [../../../frontend/agent-review-thread-handoff.md](../../../frontend/agent-review-thread-handoff.md)。
- Workspace conflict detection 当前只记录和展示，不做自动 merge、rollback 或文件级 lock。
- Orchestrator 最终用户可见 text block 已通过 response presentation 层生成：raw execution summary 继续写入 memory / run detail，聊天最终回复只暴露自然、简洁、面向结果的摘要。
- Orchestrator 会在最终 text 前输出 `process` ContentBlock：只展示公开执行事实，不展示 hidden thinking、raw ReAct trace、prompt、stderr、call id 或完整 tool output；可通过 `orchestrator_process_block_enabled=false` 关闭。
- Orchestrator group 模式已支持真实 Agent 子消息后端契约：子 Agent 输出会创建独立 `messages` 行，并通过 `message_start` / `message_done` / `message_error` SSE lifecycle 事件和带 `message_id` 的 block/tool events 归属到子消息；可通过 `orchestrator_group_messages_enabled=false` 回退到旧合流消息模式。
- Orchestrator clarification gate MVP 已实现：artifact/build/code/design 请求在进入 LLM planner 和子 Agent 调度前，会先判断需求是否足够明确；缺少关键约束时输出 `clarification` ContentBlock，一轮只问一个最高价值问题，并给出推荐默认。显式支持 `/grill-me`、`/grill-with-docs`、`/setup-matt-pocock-skills`。
- 2026-06-05 真实群聊后端 smoke 已通过：`/tmp/agenthub_group_messages_report.json`、`/tmp/agenthub_group_messages_sse.jsonl`，conversation `0948e3a6-1fc4-40a2-8cf7-3e348b2047ae`，run `34f5ef15-e649-4827-84e4-0808037f8cfe`；SSE 出现 2 个 `message_start` 和 2 个 terminal child lifecycle event，子消息均未停留在 `streaming`。
- 2026-06-06 真实群聊 + OpenCode 式过程展示 repair loop 已通过：`/tmp/agenthub_architected_frontend_group_chat_report.json`、`/tmp/agenthub_architected_frontend_group_chat_sse.jsonl`、`/tmp/agenthub_architected_frontend_group_chat_browser.json`，conversation `fbcd2fc5-ef65-4e0a-971a-6f700437a82c`，run `aa968e64-aeb4-4eca-b74b-ab51d26dff53`，`passed=true`。
- 该 repair loop 覆盖 Codex Helper 独立架构消息、Claude Code / OpenCode Helper 独立后续消息、每个 child message 的流式 `process_delta`、workspace `planning.md` / `index.html` / `styles.css` / `app.js` / `diff.md`、8082 preview 200、browser verify passed 和父 Orchestrator 不内嵌子 Agent 输出。
- 前端 stream/store 已支持 `message_start` / `message_done` / `message_error` 和带子 `message_id` 的 block/tool/process delta；本地 targeted tests、`tsc --noEmit`、`pnpm build` 通过。公网 `154.44.25.94:1573` 静态资源不在当前后端主机上，本轮未执行远端前端静态发布。
- ReAct trace 默认不再进入普通聊天流；调试证据仍记录在 run detail / memory event。需要调试可显式开启 `react_trace_visible=true`。
- 可选 LLM response polish 只接收结构化事实，失败、空输出或包含内部 trace 词时回退 deterministic summary。
- Command fulfillment backend MVP 已实现：Orchestrator 会 deterministic 提取文档、代码产物、多智能体、审阅、预览、浏览器验收、部署、Diff、源码打包等显式要求，写入 run detail `command_fulfillment_status` event，并让最终用户可见 summary 只根据 fulfillment 状态说明完成或未完成。
- 用户要求“部署/发布/上线”时，平台 preview URL 不等于部署完成；Orchestrator 需要在 preview/browser verify 后调用 `create_deployment`，失败时不得在 final text 中误报“已部署”。
- Orchestrator context routing hardening 已实现：状态/文件/预览/部署/验收追问会在 planner 前走 bounded evidence answer；继续/修复类命令先读取 evidence，已有完成证据时直接回答，确实需要继续执行时再携带 `Orchestrator evidence pack:` system message 进入 planner / tool-loop / 子 Agent 调度。
- 2026-06-07 command fulfillment 公网 repair loop 已通过：`/tmp/agenthub_command_fulfillment_report.json`、`/tmp/agenthub_command_fulfillment_sse.jsonl`、`/tmp/agenthub_command_fulfillment_browser.json`，conversation `25ff9e75-7776-46b2-8549-babb78555177`，`passed=true`；覆盖 Codex/OpenCode runtime failure 后 fallback/repair、Orchestrator coordination review fallback 生成 `review.md`、8082 preview、browser verify 和 static release deployment。
- 2026-06-08 02:24 E2E repair loop 已通过：同一 `command_fulfillment_cyberpunk_group_deploy` 场景 conversation `9fd3cd30-6b65-45a4-8833-dcadffd78f64`，`passed=true`；SSE `message_error.error` 不再泄露 raw runtime transcript，final summary 不早于 preview/verify/deploy 完成，container deployment smoke 在当时 worker 默认关闭配置下返回受控 `not_supported`。
- 2026-06-08 context follow-up repair loop 已通过：`orchestrator_context_followup_repair` 场景 conversation `7488f39a-4eda-4f06-b21a-4540a35eb89a`，run `230826eb-7e99-4ae2-961a-31ffc6e3a84b`，`passed=true`；追问“生成了吗 / 预览地址是什么 / 浏览器验收通过了吗 / 改了哪些文件 / 继续完成缺失的部署”均走 evidence answer，不创建子 Agent message，不泄露 planner/debug/raw runtime。
- 2026-06-08 presentation collapse markers smoke 已通过：`presentation_collapse_markers_smoke`
  场景 conversation `35d4a022-684f-4a0d-8650-58f56ad9be89`，run
  `a75b19fd-2e76-4303-99ab-2e3a722c3af9`，`passed=true`；SSE 与 persisted
  ContentBlock 均包含 `presentation.role`，覆盖 `execution_start` / `answer_start`、
  child `agent_summary`、父 Orchestrator `final_answer` 和可折叠 execution group，且可见
  text 无内部 trace 或 workspace 绝对路径。远端前端静态资源不在当前后端主机，本轮未做远端
  前端发布；前端折叠消费由本地 Vitest / `tsc --noEmit` 覆盖。

---

## 4. 对外依赖

- Adapter / StreamChunk 契约：[../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)
- External runtime 生命周期：[../external-runtime-lifecycle.spec.md](../external-runtime-lifecycle.spec.md)
- Workspace artifact / preview：[../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
- B2 PDF gap：[../b2-pdf-gap-todo.spec.md](../b2-pdf-gap-todo.spec.md)

---

## 5. Behavior-preserving Refactor 记录

2026-06-04 的 Orchestrator package 瘦身为内部维护性重构：

- 保持 `OrchestratorAdapter.stream()`、`StreamChunk` 顺序、`block_index` remap、`agent_id` attribution、planner task schema、evaluator payload 语义不变。
- `execution.py` 仅拆出 attempt 配置/message、review repair、artifact file block/manifest、evaluation/workflow dry-run、workspace conflict、stream event accumulation helper。
- `task_planning.py` 保留 `resolve_tasks()` 主入口，拆出 direct routing、legacy template derivation、agent review task expansion。
- `evaluation.py` 保留 `evaluate_attempt()` 与 payload/reflection helper 的导入路径，拆出 evaluator types 与 artifact/test-runner evaluator 实现。
- `quality.py` 保留 browser quality gate 主流程，拆出 preview/deployment tool chunk、repair instruction/entry discovery、deployment health/release helper。
- 本轮不新增功能，不改 public API、数据库 migration、seed、OpenAPI 或前端代码；不执行公网 E2E。

2026-06-05 在不改变上述边界的前提下进一步整理目录：

- 根目录只保留 package 入口、稳定导入契约与主要 orchestration facade：`adapter.py`、`artifacts.py`、`evaluation.py`、`execution.py`、`planner.py`、`quality.py`、`task_planning.py`、`tools.py`、`types.py`、`workspace_changes.py`。
- routing、execution helper、planning templates、evaluation evaluator、quality、tools/tool loop、ReAct、memory 与 stream helper 按功能收进 `_internal/`。
- planning templates 按 delivery、workspace conflict、legacy fallback 分组；evaluation evaluator 按 document/static、workflow、media/archive、runner/judge 与安全文件访问分组。
- `tools.py` 保留稳定 facade，catalog、workspace executor、dispatch、stream/result construction 与 loop 分开；ReAct 按 runtime、decision/parser、task graph mutation 分开。
- 无仓库调用方的旧根模块不保留转发 facade，避免根目录再次变成平铺 helper 集合。
- `_internal` 下模块不是 public API；外部调用继续通过根目录 facade。
- 本地 Orchestrator targeted pytest：`176 passed`；Ruff、Mypy、`git diff --check` passed。
- 本轮未执行公网 E2E，未改数据库、OpenAPI、seed/default config 或前端代码。

同日完成 Memory / Capability Profile service 的 behavior-preserving 可读性重构：

- `backend/app/services/orchestrator_memory.py` 保留为稳定兼容门面，公共导入路径不变。
- 实现按 store、queries、capability v1/v2、preferences、context、run reader、serialization 和 types 收进 `backend/app/services/_orchestrator_memory/`。
- v1/v2 共用实际参与 Agent、artifact、failure insight 与 confidence 规则；查询、聚合和格式化职责分离。
- 本轮不是 Capability Profile v3；不改统计、score、decay、taxonomy、preference、section 文本/顺序/预算、API wire shape、数据库或 planner 行为。
- Memory targeted pytest `102 passed`；Ruff、Mypy、`git diff --check` passed。
- 未执行公网 E2E；历史 Capability Profile acceptance 不做适配。

## 6. 用户可见 Response Presentation 记录

2026-06-05 完成 Orchestrator 用户可见消息整理：

- 新增内部 response presentation 层，输入 task graph、task results、artifact / preview / deployment / evaluation / review / workflow 状态和 raw summary，输出最终聊天 text。
- 最终聊天 text 禁止输出 `ReAct step`、`Observation:`、`Action:`、`Tools:`、`result ok`、`call_`、planner/debug prompt、raw tool result 和长日志。
- `summary_text()` 仍保留 raw execution summary，用于 Orchestrator structured memory、run detail 和既有调试证据；ContentBlock 类型不变。
- 新增配置 `orchestrator_response_polish_enabled`、`orchestrator_response_polish_model_backend`、`orchestrator_response_polish_max_tokens`，默认使用 answer/planner/model backend 做最终回复润色，并带 deterministic fallback。
- seed/default config 将 `react_trace_visible` 默认改为 `false`；需要显示 trace 的测试或调试场景可显式开启。
- 已执行 `seed_agents`，本机与公网 `/health` 正常；公网轻量 smoke 验证普通问答和轻量任务最终可见 text 不含内部 trace。
- 本轮未修改数据库 migration 或前端代码；未执行全功能公网 E2E。

复审回修：

- 完整后端 pytest 中旧 planning 文案断言已同步为新的用户可见 step/title 文案。
- Response presentation 将 `TaskState.PENDING` 计入 `needs_attention`，ReAct 达到 `max_iterations` 且仍有 pending task 时最终回复为 partial/failed，不再误报 “Done”。

公网 API/SSE 验证：

- `/tmp/agenthub_response_presentation_report.json` 与 `/tmp/agenthub_response_presentation_sse.jsonl` 均已生成，`passed=true`。
- 覆盖 `direct_answer_identity`、`light_task_failure_readable`、`react_trace_hidden` 三个场景；最终 message 均为 `done`。
- SSE text 与 persisted text 均不包含 `ReAct step`、`Observation:`、`Action:`、`Tools:`、`result ok`、`Execution summary`、`LLM planner`、`call_`、runtime stderr 或 raw stack trace。
- `process_block_present=false`；Process Block 仍属于后续 `B2-TODO-11` planned scope，本轮未新增 schema、OpenAPI 或前端 renderer。
- 任务场景 run detail 仍保留结构化证据：`light_task_failure_readable` run `458c138f-2568-4b4d-b77d-faab168e06c6`，`react_trace_hidden` run `39cb3d45-ad24-4990-9169-8bd836ad895f`。
- 完整后端 pytest `650 passed, 7 skipped`；Ruff、Mypy、`git diff --check` passed。后端已重启，PID `687089`；本机与公网 `/health` 正常；轻量公网 smoke passed。

## 7. Structured Process Block 记录

2026-06-05 完成 Orchestrator `process` ContentBlock MVP：

- 新增公开契约：后端 `StreamChunk.BlockType`、Pydantic `ContentBlock` union、OpenAPI/shared types 和前端手写 `ContentBlock` union 均包含 `process`。
- Stream / persistence 继续复用 `block_start` / `block_end`；前序 MVP 使用 `block_start.metadata` 放完整 payload。
- Orchestrator route / execution / ReAct / tool-loop 均在最终用户可见 text 前插入 deterministic process block；raw memory summary 和 run detail 证据不变。
- 新增配置 `orchestrator_process_block_enabled=true`，支持关闭 process block；seed/default config 已覆盖，需 seed 后刷新内置 Orchestrator。
- 前端新增基础 `ProcessBlock` 面板，不实现折叠状态管理；`default_collapsed` 字段保留给后续交互增强。
- 本地门禁：backend targeted `112 passed`，agent config validation `73 passed`，frontend process tests `28 passed`，backend Ruff/Mypy、frontend `tsc --noEmit`、`git diff --check` passed。
- 部署与 smoke：后端 PID `858990 -> 1037330`，已执行 `seed_agents`；本机与公网 `/health` 正常；report `/tmp/agenthub_process_block_smoke_report.json`、SSE `/tmp/agenthub_process_block_smoke_sse.jsonl` `passed=true`。公网 smoke 覆盖 direct answer `process -> text`，以及轻量任务既有 block 后追加 `process -> text`；final text 与 process block 均无内部 trace forbidden terms。

2026-06-05 追加完成后端流式 process 契约：

- 不新增 SSE event，继续复用 `block_start` / `delta` / `block_end`；`delta.metadata.process_delta` 支持 `upsert_step` 和 `set_summary`。
- `ProcessStep` 新增公开 `id` 字段，用于前端原地更新 step；该 id 不使用内部 task id 或 tool call id。
- direct answer / platform fact 会先输出 process start + route delta；static / parallel / ReAct / native tool-loop 在执行中持续 upsert 公开步骤，最终 text 仍由 response presentation 输出。
- `StreamContentAccumulator` 会原地应用 process delta 并持久化完整 block；`orchestrator_process_block_enabled=false` 时不输出 process block 或 process delta。
- 本轮只改 B2 后端契约、SSE、持久化和测试；不做前端 renderer、折叠交互或前端静态资源部署。
- 部署与 smoke：后端 PID `1152309 -> 1155645`，已执行 `seed_agents`；report `/tmp/agenthub_streaming_process_report.json`、SSE `/tmp/agenthub_streaming_process_sse.jsonl` `passed=true`，覆盖 direct answer `process_delta_count=1` 与轻量任务 `process_delta_count=7`。

同例前端演示 repair loop：

- 2026-06-05 使用用户原始“任务拆解、代码产物、Diff、网页预览、按钮交互、移动端适配、赛博朋克风、8082、浏览器级质量验收” prompt 重跑公网 API/SSE E2E。
- 修复范围：OpenCode shared auth 权限归一化、planner 空 task payload fallback、managed preview 8082 端口接管。
- 最终证据：report `/tmp/agenthub_same_prompt_repair_report_final.json`，SSE `/tmp/agenthub_same_prompt_repair_sse_final.jsonl`，conversation `ddb4837b-d4f9-4a2a-b42c-a1ab59bc5ae7`，run `74251fbc-55b6-44e7-9b5d-b1c2edef04fa`，`passed=true`。

2026-06-06 边界更正：

- 前端开发演示 prompt 只是 live smoke 示例，不是 Orchestrator 的产品级任务模板。
- 真实 Agent 群聊和流式公开 process 是通用执行层能力，适用于所有通过 planner / explicit config / legacy fallback 产生的子任务。
- LLM planner 输出不得被“前端质量演示”模板覆盖；planner 协议错误默认暴露为可见错误，只有显式 `planner_fallback_to_template=true` 时才走 legacy generic fallback。
- 已撤销前端质量演示专用 planner override、`frontend-architecture` fallback planning.md 和缺 HTML 时 static demo scaffold。

2026-06-06 通用 E2E case 扩展：

- 新增 `group_process_document_strategy`、`group_process_data_analysis`、
  `group_process_workflow_delivery`、`group_process_failure_readable`、
  `group_process_frontend_preview` 五个 live scenarios，用于覆盖真实群聊 /
  process stream 在不同任务类型下的后端 API/SSE 证据。
- Generic cases 不依赖前端质量演示模板；验收重点是独立 child message、
  child process block、`process_delta`、父 Orchestrator 不内嵌子 Agent 输出、
  workspace required files、可见文本无内部 trace。
- Planning 层新增通用保护：用户明确要求“两个/多个 Agent”或真实群聊时，
  如果 LLM planner 把多个 implementation task 全部派给同一 Agent，
  Orchestrator 会按用户明确点名的多个 Agent 或通用偏好顺序平衡负责人；
  保持 task id/title/instruction 不变。
- 当前 live repair loop 未完成 `passed=true`：Codex CLI 手动 smoke 显示账号额度限制
  到 `2026-06-11 17:54`，且公网 `111.229.151.159:8000` 请求未命中本机
  已重启 PID `1650213` 的 uvicorn access log。后续重跑前需先修正公网落点和 Codex
  runtime 可用性。

2026-06-06 通用 Agent fallback repair loop：

- 所有 Orchestrator 委派任务共享同一套失败自动调度机制：首选 Agent 失败、runtime 不可用、认证/权限/CLI/timeout 等硬失败、产物缺失或 evaluation failed 均可进入 fallback。
- 失败 Agent 会进入短期 cooldown；planner 和 fallback selection 会跳过 cooldown / unavailable Agent，避免反复派给已失败 runtime。
- `agent_fallback_matrix` 公网 API/SSE E2E 已通过：report `/tmp/agenthub_agent_fallback_matrix_report.json`，SSE `/tmp/agenthub_agent_fallback_matrix_sse.jsonl`，`passed=true`。
- Matrix 覆盖 `codex-helper`、`claude-code`、`opencode-helper` 三个首选 Agent 失败后自动切换到可用 fallback Agent；失败 attempt 与 fallback attempt 分别持久化为独立 child message，父 Orchestrator 不内嵌子 Agent 输出，可见文本无内部 trace。

2026-06-07 fallback / 真实群聊体验 hardening：

- `_run_task()` attempt 前会过滤当前会话不可运行、cooldown、run-local 已硬失败和非 group scope Agent；已知不可运行 Agent 不再先创建失败 child message。
- 单次 Orchestrator run 内新增 run-local failed runtime 状态；某 Agent 一旦出现 runtime hard failure，后续 task 和后续 batch 立即避开它。
- Run-local failed runtime 只影响当前 run 的执行选择；全局 cooldown 才可能影响后续 planner / fallback selection。
- 并行 executor 会按首选可运行 Agent 去重选取 batch，避免同一坏 runtime 在同批任务中刷出多条失败消息。
- runtime hard failure 判定收窄为 auth / quota / credential / CLI missing / provider runtime unavailable / 明确 runtime timeout；artifact missing、普通 not found、验证/构建/test 失败只触发当前 task fallback，不进入 runtime cooldown。
- 子 Agent error chunk 会保留 `error_code` 信号；即使用户可读 `error` 只是 `process exited`，`external_runtime_error` / `runtime_idle_timeout` 等 code 仍能触发 run-local unavailable。
- 子 Agent `message_error.error` 与空 error child message 统一走可见错误清洗，不暴露 `Permission denied`、`[Errno`、`.claude.json`、`/root/.agenthub`、raw stderr、stack trace 或 `call_`。
- Legacy fullstack fallback 不再硬编码“团队 OKR 轻量看板”；只保留用户请求中的主题和产物要求，无法抽取时使用通用产品交付演示语义。
- 本地 targeted gate：`tests/test_orchestrator.py`、`tests/test_orchestrator_planning.py`、`tests/test_orchestrator_response_presentation.py`、`tests/test_stream_content_blocks.py`、`tests/test_orchestrator_live_e2e_script.py` 共 `180 passed`；Ruff、Mypy、`git diff --check` passed。
- 公网 `agent_fallback_matrix` 已重跑通过：report `/tmp/agenthub_agent_fallback_matrix_report.json`，SSE `/tmp/agenthub_agent_fallback_matrix_sse.jsonl`，`passed=true`。Codex / OpenCode case 覆盖 preflight skip 后直接改派 writer；Claude case 覆盖先出现清洗后的 error child message 再改派 writer。
