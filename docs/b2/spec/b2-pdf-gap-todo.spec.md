# B2 PDF Gap TODO

> 目的：根据课程 PDF《AgentHub - 多 Agent 协作平台设计》对照当前 B2 实现，维护 B2 当前完成度、剩余缺口和建议执行顺序。
>
> 状态：P1 complete / P2 active backlog / B2-TODO-08 backend E2E passed
> 最后更新：2026-06-04
>
> Spec 整理入口：当前契约、验证报告和剩余 backlog 见 [README.md](README.md)。

---

## 1. 总体结论

B2 已经完成 Agent Runtime Layer 和 Orchestrator 的主体能力：

- `BaseAgentAdapter` / `StreamChunk` 统一协议。
- Claude Code / Codex / OpenCode external runtime 接入。
- Builtin Agent Framework + ModelGateway。
- 对话式自建 Agent 与 builtin `allowed_tools` 白名单 MVP。
- Orchestrator 任务拆解、DAG 并行、失败降级、workspace conflict detection。
- Artifact tracking、platform preview、8082 static preview、browser quality gate。
- 通用 Evaluation / Reflection MVP。
- Deployment / Release 演示 MVP：static release、source zip、container deployment、deployment repair/redeploy。

当前最影响课程设计完成度的缺口不再是 P1 三项基础能力，而是后续产品深化。B2-TODO-05 Deployment / Release production hardening 已通过 direct public API E2E 和 Orchestrator API/SSE queued worker 公网回归；B2-TODO-08 Capability Profile v2 / User Preference Memory 后端 MVP、本地验证和公网 API/SSE E2E 已完成，下一步是前端只读展示和 B2 后续扩展。按 B2 owner 口径，优先级收敛为：

1. **P1-B2-02 更多产物类型与预览**：文档、PPT、图片、附件、archive、manifest API 后端 MVP 和公网 API/SSE E2E 已完成；版本历史和局部编辑仍属于前端/后续产品化。
2. **P1-B2-03 Evaluation / Reflection 深化**：Workflow validation / runtime dry-run、PPT outline、`.pptx` 轻量解析、图片、archive、文档结构质量、`manual_review_required`、deployment health 和 evaluator repair loop 已有 MVP 或公网 E2E 证据；更多 runner、生产 LLM-as-judge 仍待后续扩展。
3. **B2-TODO-08 Capability Profile v2 / User Preference Memory**：后端 MVP 已新增跨 conversation 用户级长期画像、时间衰减、样本权重和 deterministic 用户偏好记忆；公网 E2E `p2_agent_capability_profile_v2` 已通过。
4. **P2-B2-01 Workflow runtime 扩展**：本地无副作用 dry-run runner / run history / health check 已完成；后续如需真实外部 step、队列化长任务或平台 tool step，再按 P2 扩展。

跨团队最高优先级交接项：

- **F-P1 Review thread 前端产品化**：Agent-to-Agent Review Thread 后端 MVP、并行动态 repair、memory/API 元数据和 live E2E 已完成；前端 handoff timeline 已交接，见 [../../frontend/agent-review-thread-handoff.md](../../frontend/agent-review-thread-handoff.md)。该项不再作为 B2 后端阻塞项。
- **F-P1 Rich artifact 前端产品化**：B2 后端已提供 `file` ContentBlock、`artifact_kind`、preview metadata、artifact manifest 只读 API 和 evaluation status；前端 rich card、manifest 消费、版本历史和局部编辑入口已交接，见 [../../frontend/rich-artifact-preview-handoff.md](../../frontend/rich-artifact-preview-handoff.md)。该项不再作为 B2 后端阻塞项。

2026-06-03 更新：原最高优先级 **Orchestrator 合流消息归属** 已完成公网 live E2E；B2 会给 Orchestrator plan/summary、子 Agent text/code/tool/failure/fallback chunk 写入结构化 `agent_id`，前端可按 block `agent_id` 分段展示。Workflow 产物产品化也已完成 MVP 和公网 live E2E：正式 `workflow` ContentBlock、parser / accumulator、OpenAPI 和前端 workflow card 已接入。Workflow runtime / dry-run 也已完成本地无副作用 MVP 和公网 live E2E：支持 allowlist DAG dry-run、run history / health API、Orchestrator 自动 dry-run 和 persisted workflow block 状态回填。Agent-to-Agent Review Thread 也已完成后端 MVP 和公网 live E2E：关键 implementation task 可自动 handoff 给其他 Agent review，review outcome 会进入 summary / memory，并能在 needs_repair / failed outcome 下追加 repair task。Rich Artifact manifest 和 Evaluation repair loop 也已完成公网 API/SSE E2E：`p1_rich_artifacts` 覆盖 document / ppt / image / archive file block、manifest API 和 path/kind/agent 对齐；`p1_evaluation_repair` 覆盖 document_quality failed -> reflection -> repair/fallback -> final passed，且 manifest 无 false passed。

本轮继续按要求暂缓 External runtime 最小权限与 worker 隔离；该项保留为安全 hardening backlog，不进入当前建议执行顺序。

---

## 2. PDF 核心要求对照

| PDF 核心功能 | B2 当前状态 | 完成度 | 当前结论 |
|---|---|---:|---|
| 1. IM 聊天式交互 | 支撑消息流、群聊 Orchestrator、消息 block、deployment card；子 Agent block 归属和前端分段展示已完成 live E2E | 基本达标 | 保持回归 |
| 2. 主 Agent 协调器 | 任务拆解、DAG 并行、失败降级、冲突检测、summary、Evaluation MVP、Agent-to-Agent Review Thread / repair live E2E 已完成 | 基本达标 | 前端 handoff timeline 已交接给 F |
| 3. 多 Agent 接入 | Claude Code / Codex / OpenCode 接入；自建 Agent 和 `allowed_tools` MVP 完成 | 基本达标 | external runtime 最小权限暂缓 |
| 4. 产物预览与编辑 | HTML / Diff / preview / deployment card 强；Workflow card、runtime dry-run、run history / health API MVP 已完成；文档、PPT、图片、archive 后端 MVP 和公网 API/SSE E2E 已完成；版本历史、局部编辑弱 | 部分达标 | 前端产品化 |
| 5. 部署发布 | static release、source zip、container deployment、status card、repair/redeploy 已完成演示 MVP；生产默认与队列化 worker hardening 已通过公网 direct API E2E | 基本达标 | 后续仅剩更强生产隔离和外部队列 |
| 6. 多端支持 | Web 端为主；桌面/移动端非 B2 主责 | 部分达标 | B2 不作为当前主线 |

---

## 3. 已完成项

### B2-DONE-01 Agent Runtime 统一协议

对应 PDF：

- 统一适配器层，屏蔽不同 Agent runtime 差异。

当前状态：

- `BaseAgentAdapter`、`StreamChunk`、tool events、workspace 参数已形成统一协议。
- Agent config validation、runtime test matrix 已有当前契约。

相关 spec：

- [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)
- [agent-config-validation.spec.md](agent-config-validation.spec.md)
- [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md)

### B2-DONE-02 多 Agent Runtime 接入

对应 PDF：

- 至少接入 2 个主流 Agent 平台。

当前状态：

- Claude Code / Codex / OpenCode external runtime 已接入。
- direct chat routing、lifecycle、timeout、heartbeat、cancel、process cleanup、日志脱敏已有。

相关 spec：

- [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md)
- [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)
- [external-direct-chat-routing.spec.md](external-direct-chat-routing.spec.md)

### B2-DONE-03 Builtin Agent 与自建 Agent

对应 PDF：

- 支持用户自建 Agent，设定 System Prompt + 工具集。

当前状态：

- Builtin Agent Framework + ModelGateway 已完成。
- Orchestrator 可通过 `create_custom_agent` 平台 tool 对话式创建自建 Agent。
- 新建 builtin Agent 默认 `allowed_tools=[]`，显式授权后才暴露 native/MCP tools。
- 缺少必要字段时返回 `needs_user_input=true`，不创建半成品。

相关 spec：

- [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md)
- [model-gateway.spec.md](model-gateway.spec.md)
- [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)

### B2-DONE-04 Orchestrator 核心执行

对应 PDF：

- 自动理解意图、拆解任务、分派子 Agent、聚合产出。
- 支持并行调度、失败降级、代码冲突处理。

当前状态：

- 任务规划、DAG 并行、fallback、summary 已完成。
- Workspace snapshot / diff / conflict detection 已完成。
- 冲突当前记录和展示，不自动 merge、rollback 或加文件锁。

相关 spec：

- [orchestrator/core.spec.md](orchestrator/core.spec.md)
- [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md)
- [orchestrator/workspace-conflict.spec.md](orchestrator/workspace-conflict.spec.md)

### B2-DONE-05 Preview 与 Evaluation / Reflection MVP

对应 PDF：

- 产物内联预览。
- 生成效果质量。

当前状态：

- `start_workspace_preview` / `verify_web_preview` 已作为正式 platform tools。
- Browser quality gate 支持 desktop/mobile、资源、JS error、按钮交互等检查。
- 通用 evaluator 已覆盖 `artifact_exists`、`document_quality`、`code_static_quality`、`workflow_validation`、`ppt_validation`、受控 `test_report_quality`、`browser_preview_quality`、`deployment_health`。
- Evaluation 失败会生成 reflection，并进入 repair / re-evaluate MVP。

相关 spec：

- [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)
- [orchestrator/evaluation-reflection.spec.md](orchestrator/evaluation-reflection.spec.md)

### B2-DONE-06 Deployment / Release 演示 MVP

对应 PDF：

- 聊天中直接发送“部署”指令，Agent 返回部署状态卡片。
- 一键生成预览 URL / 静态站点部署 / 容器化部署 / 源码打包下载。

当前状态：

- `create_deployment`、`get_deployment_status`、`stop_deployment`、`package_workspace_source` 已完成。
- `deployment_status` 消息块和前端卡片已对齐。
- Static release 使用不可变 release snapshot 和 token URL。
- Source zip 支持 digest、size、file count、过期和 janitor。
- Container deployment 默认走受控 `ContainerDeployWorker`，支持 build/run/health check/stop/cleanup。
- Deployment 失败后已接入 `deployment_health -> reflection -> repair agent -> redeploy`。
- Container build/run/health 失败路径会清理 build context、container、image；janitor 已覆盖 container build root 和 managed runtime orphan cleanup。

相关 spec：

- [deployment-release-backend.execution.spec.md](deployment-release-backend.execution.spec.md)
- [orchestrator/native-deployment.execution.spec.md](orchestrator/native-deployment.execution.spec.md)
- [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)

### B2-DONE-07 Orchestrator 合流消息归属

对应 PDF：

- 群聊协作中多个 Agent 像群聊成员一样依次回复各自的产出。
- Agent 回复中的代码、Diff、文件、部署状态等产物需要保留真实来源。

当前状态：

- B1 / OpenAPI 已为 content block 增加 optional `agent_id` 字段。
- B1 `StreamContentAccumulator` 已能持久化 block 级 `agent_id`。
- B2 Orchestrator 已给 plan / summary / platform fact / direct answer 标记 `agent_id="orchestrator"`。
- B2 子 Agent stream remap 已对子 Agent `block_start` / `delta` / `block_end` / `tool_call` / `tool_result` / `heartbeat` 附加实际 attempt `agent_id`。
- 子 Agent 失败文本不再使用正文 `@<agent_id>` header，而是用 `agent_id=<failed_agent_id>` 的 text block 表示。
- fallback attempt 输出使用 fallback agent id。
- 前端 SSE 类型、流式 store 和 ContentRenderer 已能消费 block `agent_id`，并按连续 Agent 分段展示 Orchestrator 合流消息。

验证：

- `uv run pytest tests/test_orchestrator.py -q`
- `uv run ruff check app/agents/orchestrator tests/test_orchestrator.py`
- `uv run mypy app/agents/orchestrator`
- `pnpm test -- --run src/components/blocks/ContentRenderer.test.tsx src/stores/chatStore.test.ts`
- `pnpm exec tsc --noEmit`
- Live E2E：`AGENTHUB_E2E_SCENARIO=p1_attribution uv run python scripts/orchestrator_live_e2e.py`
  - report: `/tmp/agenthub_p1_attribution_report.json`
  - sse: `/tmp/agenthub_p1_attribution_sse.jsonl`
  - conversation_id: `6df2b527-cc76-4881-bb24-f8aed18e433b`
  - passed: true

相关 spec：

- [orchestrator/message-attribution.spec.md](orchestrator/message-attribution.spec.md)
- [../../frontend/spec/orchestrated-message-rendering.spec.md](../../frontend/spec/orchestrated-message-rendering.spec.md)

### B2-DONE-08 Workflow 产物产品化 MVP

对应 PDF：

- 通过对话式交互创建网页、Workflow 等产物。
- Agent 回复中内联展示富媒体产物。

当前状态：

- 新增正式 `workflow` ContentBlock / OpenAPI schema。
- `StreamChunk.block_type` 支持 `workflow`。
- `StreamingArtifactParser` 可识别 `workflow` / `workflow-json` / `workflow-yaml` fenced block。
- SSE accumulator 可持久化 workflow block，并可将符合 workflow schema 的普通 JSON/YAML code block 升级为 workflow block。
- SSE accumulator 可从真实外部 Agent 的普通 text block 中提取 fenced workflow，并追加正式 workflow block。
- Workflow block 会输出 `validation_status`、`runtime_status`、`dry_run_status`、`health_status`。
- 前端 `WorkflowBlock` card 可展示名称、path、节点、边、validation/runtime/dry-run/health 状态和原始定义。
- 上下文压缩会保留 workflow 摘要，后续对话不会把 workflow 产物静默丢失。

当前边界：

- 已有 `workflow_validation` evaluator 继续负责 workspace 文件级验证。
- 现在的 `runtime_status="ready"` 表示 schema valid 且当前 allowlist runtime 支持。
- `dry_run_status="passed"` 表示本地无副作用 dry-run 已通过；shell、HTTP、部署、workspace 写入、外部 Agent 调用类 step 仍不支持。
- 队列化长任务 runtime、平台 tool step、外部 workflow worker 属于后续 P2 扩展。

验证：

- `uv run pytest tests/test_artifact_parser.py tests/test_stream_content_blocks.py tests/test_stream_tool_calls.py::test_openapi_includes_tool_call_block -q`
- `uv run ruff check app/agents/types.py app/agents/artifact_parser.py app/api/v1/stream_accumulator.py app/schemas/message.py app/services/context/compression.py tests/test_artifact_parser.py tests/test_stream_content_blocks.py tests/test_stream_tool_calls.py`
- `uv run mypy app/agents/types.py app/agents/artifact_parser.py app/api/v1/stream_accumulator.py app/schemas/message.py app/services/context/compression.py`
- `pnpm test -- --run src/components/blocks/ContentRenderer.test.tsx src/stores/chatStore.test.ts`
- `pnpm exec tsc --noEmit`
- Live E2E：`AGENTHUB_E2E_SCENARIO=p1_workflow uv run python scripts/orchestrator_live_e2e.py`
  - report: `/tmp/agenthub_p1_workflow_report.json`
  - sse: `/tmp/agenthub_p1_workflow_sse.jsonl`
  - conversation_id: `a6bdaa88-e142-4a56-9cf2-1f45afd47119`
  - passed: true

相关 spec：

- [workflow-artifact.spec.md](workflow-artifact.spec.md)
- [artifact-parser-v2.spec.md](artifact-parser-v2.spec.md)
- [orchestrator/evaluation-reflection.spec.md](orchestrator/evaluation-reflection.spec.md)

---

## 4. P1 Active TODO

### B2-TODO-01 Orchestrator 合流消息归属

状态：DONE 2026-06-03；保留本节作为历史验收说明。

对应 PDF：

- 群聊协作中多个 Agent 像群聊成员一样依次回复各自的产出。
- Agent 回复中的代码、Diff、文件、部署状态等产物需要保留真实来源。

当前状态：

- B1 / OpenAPI 已为 content block 增加 optional `agent_id` 字段。
- B1 `StreamContentAccumulator` 已能持久化 block 级 `agent_id`。
- B2 spec 已定义 Orchestrator 合流时由 B2 生产真实 `StreamChunk.agent_id`。
- B2 子 Agent stream remap 已稳定 attach 实际 attempt `agent_id`。
- `_text_block()` / `_text_block_with_next()` 已支持 `agent_id`，默认 `orchestrator`。
- 当前执行流默认不再输出普通正文 `@<agent_id>` header。
- 前端 grouped rendering 已完成基础实现。

已完成：

- Orchestrator `_text_block()` / `_text_block_with_next()` 支持 `agent_id` 参数。
- Orchestrator plan / summary / platform fact / fallback summary 明确写 `agent_id="orchestrator"`。
- `orchestrator/streams.py` 新增 `attach_agent_id()`，对子 Agent `block_start` / `delta` / `block_end` / `tool_call` / `tool_result` 附加实际 attempt `agent_id`。
- 移除默认 `@<agent_id>` 正文 header。
- 子 Agent 失败文本改为 `failed: ...`，并将 text block `agent_id` 标记为失败的实际 Agent。
- fallback attempt 的所有输出使用 fallback agent id。
- 已补 B2 后端测试：text/code/tool/failure/fallback attribution、summary attribution、不再输出正文 header。
- 前端按 block `agent_id` 分组渲染 Orchestrator 消息。

建议影响文件：

- `backend/app/agents/orchestrator/execution.py`
- `backend/app/agents/orchestrator/streams.py`
- `backend/app/agents/orchestrator/adapter.py`
- `backend/app/agents/orchestrator/adapters.py`
- `backend/tests/test_orchestrator_attribution.py`
- `backend/tests/test_orchestrator.py`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/chat/messageGrouping.ts`
- `frontend/src/stores/chatStore.ts`

验收标准：

- SSE live event 中，子 Agent block/tool chunk 带真实 `agent_id`。
- B1 accumulator 落库后 content block 保留该 `agent_id`。
- Orchestrator planning / final summary block 明确归属 `orchestrator`。
- 子 Agent 失败和 fallback 输出归属实际 attempt agent。
- 默认不再通过普通正文 `@agent` header 表达归属。
- 前端刷新后能按真实 Agent 分段展示一条 Orchestrator 合流消息。

相关 spec：

- [orchestrator/message-attribution.spec.md](orchestrator/message-attribution.spec.md)
- [../../frontend/spec/orchestrated-message-rendering.spec.md](../../frontend/spec/orchestrated-message-rendering.spec.md)

### B2-DONE-10 Workflow runtime / dry-run MVP

状态：DONE 2026-06-03；本地无副作用 runtime / dry-run runner / run history / health API 已完成公网 live E2E。

对应 PDF：

- 通过对话式交互创建网页、Workflow 等产物。

当前状态：

- 已有 `workflow_validation` evaluator，可校验 JSON/YAML workflow 的 `version/name/nodes/edges`、节点唯一性、edge 悬空引用。
- 已有正式 `workflow` ContentBlock / artifact kind MVP。
- Artifact parser / SSE accumulator / OpenAPI / 前端 preview card 已接入。
- Workflow block 已暴露 validation / runtime / dry-run / health 状态。
- 已有本地 allowlist dry-run runner：支持 `trigger`、`task(set_context)`、`assert(equals)`、`end`。
- 已有 workflow run history / health API。
- Orchestrator 在 `workflow_validation` passed 后会自动 dry-run，并将结果写入 summary / memory / persisted workflow block。

已完成：

- 定义正式 Workflow artifact schema：`nodes`、`edges`、`inputs`、`outputs`、`trigger`、`steps`。
- 新增 artifact kind：`workflow`。
- Artifact parser / summary 能识别 workflow artifact。
- 前端用简单 DAG metadata 展示。
- 可执行 dry-run runner。
- workflow run history / health check API。
- 公网 live E2E 覆盖 `p1-runtime-workflow.yaml` 自动 dry-run、额外 API dry-run 和 history 增长。

后续 P2 扩展：

- Orchestrator 对“帮我做一个工作流/流程”的任务意图增加更明确的生成提示和 artifact handoff。
- Builtin Agent workflow 生成模板 / tool prompt。
- 外部 step、平台 tool step 或长任务队列化 runtime。

建议影响文件：

- `backend/app/agents/artifact_parser.py`
- `backend/app/schemas/message.py`
- `backend/tests/test_artifact_parser.py`
- `backend/tests/test_stream_content_blocks.py`
- `backend/tests/test_workflow_runtime.py`
- `frontend/src/components/blocks/WorkflowBlock.tsx`
- `frontend/src/components/blocks/ContentRenderer.tsx`
- `frontend/src/stores/chatStore.ts`

验收标准：

- workflow fenced block 可进入正式 `workflow` ContentBlock。
- workflow 文件通过平台 validator。
- 非法 workflow 不被标记为 ready。
- 前端能展示 workflow card。
- dry-run passed 后 workflow block 有 `last_run_id`、`dry_run_status="passed"`、`health_status="passed"`。
- Live E2E report：
  - report: `/tmp/agenthub_p1_workflow_runtime_report.json`
  - sse: `/tmp/agenthub_p1_workflow_runtime_sse.jsonl`
  - conversation_id: `12ac1864-0158-48ca-a9f3-6640da9ab6ab`
  - passed: true

### B2-DONE-06 Agent Capability Profile v1

优先级：P1；B2 后端实现、本地回归与公网 E2E 已完成。

目标：

- 在现有 Orchestrator structured memory 基础上，为当前 conversation 聚合近期 Agent 能力画像。
- 聚合不跨用户、不跨 workspace，不引入复杂推荐系统。
- Planner 在后续任务规划时能参考每个 Agent 的近期成功率、失败类型、擅长产物类型、review/repair 表现，并在 summary 或 memory 中体现选择依据。

当前实现范围：

- 新增 `build_agent_capability_profile()`，数据来源为 `orchestrator_runs`、`orchestrator_tasks`、`orchestrator_task_attempts`、`orchestrator_run_events`。
- 聚合当前 conversation 最近 `20` 个 terminal runs，API 参数最大 `100`。
- 每个 agent 输出 `runs_considered`、`task_count`、`success_count`、`failure_count`、`artifact_missing_count`、`evaluation_failed_count`、`avg_attempts`、`artifact_kinds`、`review_outcomes`、`repair_success_count`、`recent_failure_reasons`、`confidence`。
- `build_orchestrator_memory_context()` 在 `Previous Orchestrator structured memory` 前注入 `Agent capability profile from recent Orchestrator runs`，共同受 `orchestrator_memory_context_max_chars` 控制；没有历史数据时不注入。
- Planner system prompt 已要求按 requested task type、artifact kind、review、repair pattern 参考 capability profile，同时不得选择 available/managed agent ids 之外的 Agent。
- Planner 输入现在会从当前 conversation 的 memory system message 中提取 capability profile 段；不会把无关的 `Previous Orchestrator structured memory` 历史整体传给 planner。
- 新增只读 API：`GET /api/v1/conversations/{conversation_id}/agent-capability-profile`，复用 conversation ownership check。
- live E2E 脚本新增 scenario `p1_agent_capability_profile`：种子轮验证 `claude-code` evaluation failure 与 `opencode-helper` fallback success 的画像差异；follow-up 从最新 run detail 验证实际 task/attempt Agent 均为 `opencode-helper`。
- 统计语义已按实际参与 Agent 收口：同 Agent retry 只计一个逻辑任务、fallback 成败分别归属实际 Agent、repair success 归属实际成功 Agent、artifact kind 按 agent + task + kind 去重、旧 task 无 attempt 时兼容降级。
- `shared/openapi.yaml` 已同步 profile API 和 response schemas；前端类型生成与画像 UI 留给前端后续工作。

建议影响文件：

- `backend/app/services/orchestrator_memory.py`
- `backend/app/api/v1/conversations.py`
- `backend/app/schemas/conversation.py`
- `backend/app/agents/orchestrator/planner.py`
- `backend/scripts/orchestrator_live_e2e.py`
- `backend/tests/test_orchestrator_memory.py`
- `backend/tests/test_conversation_api.py`
- `backend/tests/test_orchestrator_planning.py`

本地验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator_memory.py tests/test_orchestrator.py tests/test_conversation_api.py tests/test_orchestrator_planning.py tests/test_orchestrator_live_e2e_script.py -q
uv run python -m ruff check app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py scripts/orchestrator_live_e2e.py tests
uv run python -m mypy app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py
```

公网 E2E：

```text
report: /tmp/agenthub_p1_agent_capability_profile_report.json
sse: /tmp/agenthub_p1_agent_capability_profile_sse.jsonl
conversation_id: 8dd905aa-e51a-4f68-b869-2cc4c6278a3d
passed: true
claude-code: success_count=0, failure_count=1, evaluation_failed_count=1
opencode-helper: success_count=1, failure_count=0
followup_task_agents: [opencode-helper]
followup_attempt_agents: [opencode-helper]
```

### B2-DONE-09 Agent-to-Agent Review Thread MVP

优先级：P1。

对应 PDF：

- 多 Agent 群聊协作，而不只是主 Agent 串行转述。

当前状态：

- `SubTask` 已支持 `task_type=implementation/review/repair`、`review_of`、`handoff_reason`。
- 开启 `orchestrator_agent_review_enabled=true` 后，关键 implementation task 会自动安排另一个当前群聊 Agent review。
- Review prompt 要求引用 artifact / diff / file changes / tool result / evaluation / deployment status，并首行返回 `review_outcome`。
- Review outcome 已写入 attempt、summary 和 memory event。
- 顺序和并行静态执行路径下，`review_outcome: failed` 或 `review_outcome: needs_repair` 会动态追加 repair task，repair agent 只从当前群聊成员中选择。
- 同一个 review task 只允许生成一个动态 repair task。
- `orchestrator_tasks` / `orchestrator_task_attempts` 和 run detail API 已暴露 `task_type`、`review_of`、`handoff_reason`、`review_outcome`，便于 live E2E 和前端读取。
- Review task 正常完成后不会把被审 artifact 当作 review 自己的交付物跑 document/workflow evaluator，避免 `needs_repair` 被质量 evaluator 覆盖成 `failed`。
- 公网 live E2E 已覆盖 implementation -> review(`needs_repair`) -> repair -> final summary。

剩余 hardening：

- 前端独立 review thread / handoff timeline UI 已交接给 F，不作为 B2 后端阻塞项。

建议影响文件：

- `backend/app/agents/orchestrator/task_planning.py`
- `backend/app/agents/orchestrator/execution.py`
- `backend/app/agents/orchestrator/quality.py`
- `backend/app/agents/orchestrator/summary.py`
- `backend/app/models/orchestrator_memory.py`
- `backend/tests/test_orchestrator.py`
- `backend/tests/test_orchestrator_quality_gate.py`

验收标准：

- 构建任务后至少一个群聊内其他 Agent 能执行 review。已完成。
- Review 明确指出通过/失败/需修复。已完成，解析 `review_outcome`。
- 修复任务只使用当前群聊成员。已完成，顺序和并行执行 MVP。
- 最终 summary 展示 review 结论。已完成。
- Run detail / memory event 可稳定断言 review metadata。已完成。
- Live E2E report：
  - report: `/tmp/agenthub_p1_review_thread_report.json`
  - sse: `/tmp/agenthub_p1_review_thread_sse.jsonl`
  - conversation_id: `5d0373e4-3801-4242-b812-f03ddacd3fb1`
  - passed: true

相关 spec：

- [orchestrator/agent-review-thread.spec.md](orchestrator/agent-review-thread.spec.md)
- [../../frontend/agent-review-thread-handoff.md](../../frontend/agent-review-thread-handoff.md)

### B2-TODO-04 产物类型与预览增强

优先级：P1；B2 后端 DONE 2026-06-03，公网 API/SSE Live E2E 已通过。

对应 PDF：

- Agent 回复中内联产物预览卡片：网页 iframe、文档渲染、PPT 浏览。
- 支持 Diff 视图、版本历史、对话式局部修改。

当前状态：

- HTML / code / diff / web preview / deployment status 较强。
- `document`、`ppt`、`image`、`archive` 已作为 `FileBlock.artifact_kind` 进入消息块和 manifest API。
- `FileBlock` 已支持 `path`、`preview_text`、`preview_truncated`、`metadata`，并使用 workspace file API 作为 URL。
- 文档/PPT outline 可文本预览，图片可通过 workspace file URL 预览，archive 可展示 file count/top entries。
- 平台内部 `.agenthub/artifacts.json` v1 已落地，并通过 `GET /api/v1/workspaces/{conversation_id}/artifacts` 只读暴露 entries。
- 版本历史、局部编辑和更复杂附件工作流仍未产品化。

已完成：

- 复用 `file` ContentBlock，新增 artifact kind 和 preview metadata。
- `StreamChunk.block_type` 支持 `file`，SSE accumulator 可持久化 file block。
- Artifact path extraction 已支持 `.pptx/.pdf/.docx/.zip/.tar/.tar.gz/.tgz/.csv` 等常见产物。
- 为 markdown/report/document 提供稳定识别和 summary。
- Orchestrator artifact check 成功后会为 document/ppt/image/archive 追加 file block，并保留真实子 Agent `agent_id`。
- Orchestrator 会将 file block 同步写入 artifact manifest，并回填 `task_id`、`run_id`、`evaluation_status` 和 `evaluation_results`。
- 前端产品化边界已交接：B2 只保证 API / SSE / persisted ContentBlock / manifest 契约；卡片视觉、manifest 聚合视图、版本历史和局部编辑属于 F 侧。
- 公网 Live E2E `p1_rich_artifacts` 已通过：report `/tmp/agenthub_p1_rich_artifacts_report.json`，SSE `/tmp/agenthub_p1_rich_artifacts_sse.jsonl`，conversation `c6da3473-b338-4321-ba7d-eb0f877e70ae`。

后续待办：

- B2：保持 rich artifact manifest / file block 回归；后续只按新增字段需求做契约调整。
- F：版本历史、局部编辑与前端编辑器联动作为后续增强。

验收标准：

- Agent 生成 README / report 时能被识别为 document artifact。
- 生成 PPT outline 或 PPT 文件时能进入明确 artifact / preview / evaluator 路径。
- 打包下载时能包含所有相关产物。

---

## 5. P1/P2 Hardening / Long-Term TODO

### B2-TODO-05 Deployment / Release 生产 hardening

优先级：P2 长期 follow-up；当前 direct API 与 Orchestrator API/SSE E2E 门禁已完成。

当前状态：

- PDF 第五点演示 MVP 已达标。
- repair/redeploy 与清理 MVP 已完成。
- 2026-06-04 后端 production hardening 已通过公网 direct API E2E：container 默认关闭、生产推荐 Podman、Docker 仅 trusted demo override；container API 返回 `queued` 后由 in-process queueable worker 推进状态。
- Production-default E2E：container 最终 `not_supported`，runtime_kind `podman`；preview、static release、source zip、cleanup 均通过。
- Demo override E2E：container `queued -> published`，`worker_id`、`attempt_count=1`、`state_events` 已写入报告；healthcheck / stop / cleanup 均通过。
- 2026-06-04 Orchestrator API/SSE queued worker 回归已通过：
  - Production-default report：`/tmp/agenthub_b2_todo_05_orch_prod_default_report.json`，
    conversation `963afa42-0549-4fa0-81b0-8fad6b013a4b`，container 最终 `not_supported`，
    `deployment_status` block 和 runtime metadata 均可见，`not_supported` 未触发 repair/reflection。
  - Demo override report：`/tmp/agenthub_b2_todo_05_orch_demo_report.json`，
    conversation `ce767e6f-b03c-41fb-af85-fe637983c356`，container `publishing -> published`，
    worker `inproc-container-71038d04c528`，`attempt_count=1`，`state_event_count=12`，
    healthcheck / stop cleanup 均通过。
- 可选 repair/redeploy confirmation 本轮记录为未通过：`/tmp/agenthub_b2_todo_05_orch_repair_report.json`
  观察到 `build_failed` / `container_build_failed`，但未触发 `reflection_created` 和 redeploy；不作为本轮主验收阻断。

长期 follow-up：

- Rootless Podman 生产部署实机验证。
- 外部队列 worker（Redis/Celery/RQ 等）替换当前 in-process MVP。
- Orchestrator repair/redeploy 在 queued worker 新语义下的稳定复验。
- 更强宿主隔离。
- 前端部署历史 / 状态卡的更细粒度 repair 展示。

验收标准：

- Container deployment 不依赖 trusted Docker host mode 作为长期默认。
- Worker 可队列化执行并隔离 API 进程。
- 部署失败路径有稳定、可审计、可恢复的状态流。

### B2-TODO-08 Capability Profile v2 / User Preference Memory

优先级：P2；后端 MVP implemented，本地验证完成，公网 E2E 已通过。

当前状态：

- 新增 user-scope `build_agent_capability_profile_v2()`，从当前用户拥有的多个 conversation 的 terminal Orchestrator runs 实时聚合，不新增数据库表或 migration。
- v2 保留 v1 的实际参与 Agent 归属语义，并增加 `conversation_count`、weighted success/failure、`success_rate`、`timeout_count`、`task_types`、`task_taxonomy`、`score` 和 `score_reasons`。
- 新增 deterministic `UserPreferenceMemory`，从历史 request/summary/artifact kind 中提取 domains、artifact、deployment 和 language/style hints；不调用 LLM。
- Memory context 已注入 v2 profile、user preference、v1 profile 和 structured memory，并共用 `orchestrator_memory_context_max_chars`。
- Planner 白名单读取 v2 profile、user preference 和 v1 profile，不读取完整 structured memory；当前请求显式 Agent/技术/风格优先，available/managed agent 校验仍是硬边界。
- 新增只读 API：`GET /api/v1/conversations/{conversation_id}/agent-capability-profile-v2`；v1 API wire shape 保持不变。
- `shared/openapi.yaml` 已同步 `AgentCapabilityProfileV2Out`、`AgentCapabilityProfileV2ItemOut` 和 `UserPreferenceMemoryOut`。
- 公网 API/SSE E2E `p2_agent_capability_profile_v2` 已通过：report `/tmp/agenthub_p2_agent_capability_profile_v2_report.json`，SSE `/tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl`，seed conversation `d9c96baf-2e4e-4b3a-a4a0-39ee68bf2f27`，follow-up conversation `0d7ed6d6-dcbf-4212-9150-55d410af622c`。

本地验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator_memory.py tests/test_conversation_api.py tests/test_orchestrator_planning.py tests/test_orchestrator.py -q
uv run python -m ruff check app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py tests/test_orchestrator_memory.py tests/test_conversation_api.py tests/test_orchestrator_planning.py
uv run python -m mypy app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py
git diff --check
```

后续待办：

- 前端重新生成类型并做只读展示；不提供 mutation、手动改分或硬编码调度控制。

验收标准：

- 同类失败多次后，Orchestrator 能在 planner memory signal 中看到该 Agent 的扣分原因。
- 调度理由中能说明选择某 Agent 的历史依据，同时不会覆盖本轮显式指令。

### B2-TODO-07 Evaluation / Reflection 深化

优先级：P1/P2；B2 deterministic evaluator MVP 已增强，公网 evaluator repair loop E2E 已通过。

当前状态：

- 通用 Evaluation / Reflection MVP 已实现。
- Workflow validation / runtime dry-run、PPT outline、受控 test runner、deployment health 已有 MVP evaluator 或 health gate。
- `.pptx` OpenXML 轻量解析、图片完整性、archive 安全检查、文档结构质量和 `manual_review_required` 已有本地回归。
- 公网 Live E2E `p1_evaluation_repair` 已通过：report `/tmp/agenthub_p1_evaluation_repair_report.json`，SSE `/tmp/agenthub_p1_evaluation_repair_sse.jsonl`，conversation `5186e757-6a7c-4d0f-8643-c9b3defbc181`。

待办：

- 扩展更多 allowlist test runner alias。
- 引入生产可用 LLM-as-judge。
- 将 workflow runtime 从本地 allowlist dry-run 扩展到外部 step、平台 tool step 或队列化长任务，并补对应健康检查策略。

验收标准：

- 可自动验证任务能进入“生成 -> 验证 -> 修复 -> 再验证”闭环。
- 最终交付带 evaluation summary。
- 无法自动验证的产物明确进入 `manual_review_required`，不假装通过。

---

## 6. Deferred Security TODO

### B2-DEFER-01 External Runtime 最小权限与 Worker 隔离

优先级：Deferred。

说明：

- 该项仍是重要安全 hardening，但本轮按要求暂缓，不进入当前执行顺序。

当前状态：

- External runtime 已统一使用 conversation workspace 作为 `cwd`。
- 已有 timeout、heartbeat、cancel、process group cleanup 和日志脱敏。
- 已有 workspace prompt guard 和 preview/server 命令过滤。
- `codex-helper` seed 默认仍使用 `sandbox_mode="danger-full-access"`。
- 当前 external runtime 仍在 API 服务宿主环境附近执行，缺少独立 worker、OS 级目录隔离和资源限额。

后续待办：

- 将默认 Codex sandbox 收紧为 `workspace-write`。
- 抽象独立 `ExternalRuntimeWorker`，将 CLI/SDK runtime 与 API 进程隔离。
- 为 worker 增加工作目录 allowlist、只读敏感目录、CPU、memory、process count 和 timeout 限额。
- 禁止把数据库密码、provider API key 之外的宿主 env 整体透传给 runtime。
- 对 runtime 出网能力增加 feature flag 和 allowlist。
- 增加残留进程、越界访问、敏感 env、危险 sandbox mode 的回归测试。

验收标准：

- 默认 external runtime 只能写当前 conversation workspace。
- API 进程不直接承载长时间 CLI 子进程。
- `danger-full-access` 不能作为 seed 默认值。
- Timeout、cancel、服务重启后不存在残留子进程。
- Runtime 日志和审计事件能够说明 provider、agent、sandbox mode、workspace 和退出原因。

---

## 7. 建议执行顺序

1. F-P1 Review Thread / Rich Artifact 前端产品化（B2 已交接）

   后端 review / repair / memory / live E2E 已完成；rich artifact 后端 `file` block、manifest API、evaluation status 和公网 API/SSE E2E 已完成。前端补 handoff timeline、rich artifact card、manifest 聚合、版本历史和局部编辑入口。交接文档：[../../frontend/agent-review-thread-handoff.md](../../frontend/agent-review-thread-handoff.md)、[../../frontend/rich-artifact-preview-handoff.md](../../frontend/rich-artifact-preview-handoff.md)。

2. B2-TODO-08 Capability Profile v2 / User Preference Memory 前端消费与后端观测

   Capability Profile v2 后端已完成跨 conversation 用户级长期画像、时间衰减、样本权重、timeout rate、task taxonomy、deterministic user preference memory、只读 API、OpenAPI 和公网 API/SSE E2E。下一阶段以前端只读展示、空态/低置信文案和线上观测为主，不新增 mutation 或手动改分入口。

3. P1-B2-03 后续扩展 / B2-TODO-07 Evaluation / Reflection 深化

   当前 deterministic evaluator MVP 和公网 repair loop E2E 已完成。更多 runner alias、生产 LLM-as-judge 和 workflow 外部 step 作为后续扩展。

4. B2-TODO-05 Deployment / Release 生产 hardening 长期 follow-up

   当前 production-default 和 trusted Docker demo override direct public API E2E 已通过；后续只保留 Rootless Podman 实机验证、外部队列 worker、更强宿主隔离和前端部署历史/状态卡增强。

暂缓：B2-DEFER-01 External Runtime 最小权限与 Worker 隔离。

---

## 8. Demo 验收矩阵

| 场景 | 当前能否演示 | 当前目标 |
|---|---:|---|
| 群聊 @orchestrator 做前端页面 | 可以 | 保持稳定 |
| 自动生成 workspace 代码产物 | 可以 | 保持稳定 |
| 并行调用多个 Agent | 可以 | 保持 DAG 并行和可观测性 |
| 多 Agent 修改同一文件冲突检测 | 可以 | 后续补 review / merge 策略 |
| 聊天中创建自建 Agent | 可以 | 后续补权限选择 UI |
| Builtin Agent `allowed_tools` | 可以 | 保持最小权限 MVP |
| 8082 静态预览 | 可以 | Preview 保持临时验收职责 |
| 浏览器质量验收 | 可以 | 保持 browser quality gate |
| 通用 Evaluation / Reflection | MVP 可以 | 后续扩展更多 evaluator |
| 部署状态卡片 | 可以 | 已达演示 MVP |
| Static release | 可以 | 已达演示 MVP |
| Source zip 下载 | 可以 | 已达演示 MVP |
| Container deployment | 可以 | production-default / demo override direct API E2E 已通过，后续生产隔离/外部队列 |
| Deployment repair/redeploy | 可以 | 已达演示 MVP，历史 API/SSE E2E 已过 |
| Orchestrator 子 Agent 分段显示 | 可以 | 保持 attribution / grouped rendering 回归测试 |
| Workflow 产物 | artifact / preview / runtime dry-run MVP 可以 | 后续按需扩展外部 step / 平台 tool step |
| Agent-to-Agent review | 可以 | 后端 repair live E2E 已过，前端 timeline 已交接给 F |
| 文档/PPT/图片/附件丰富产物 | 后端 API/SSE live E2E 可以 | 前端 rich card / manifest / 编辑入口已交接 |
| External runtime 强隔离 | 暂缓 | 后续安全 hardening |
