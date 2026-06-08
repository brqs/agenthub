# Orchestrator Live E2E Report

> 状态：Passed
> 最后更新：2026-06-07

---

## 1. Summary

本报告记录 Orchestrator 真实部署链路的验收结果。它只作为 evidence，不承载能力契约；能力契约分别见：

- DAG 并行：[core.spec.md](core.spec.md) 与 [task-planning.spec.md](task-planning.spec.md)
- 平台 tools / 自建 Agent：[tool-calling.spec.md](tool-calling.spec.md)
- Workspace 冲突：[workspace-conflict.spec.md](workspace-conflict.spec.md)
- Preview / browser verify：[../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
- Deployment / Release：[native-deployment.execution.spec.md](native-deployment.execution.spec.md)

真实链路：

- 前端入口：`http://154.44.25.94:1573`
- 后端公网：`http://111.229.151.159:8000`
- Preview：`http://111.229.151.159:8082/index.html`
- 真实账号：`12345678 / 12345678`

最终报告：

- `/tmp/agenthub_b2_p0_live_report.json`
- `/tmp/agenthub_orchestrator_quality_report.json`
- `/tmp/agenthub_orchestrator_quality_browser.json`
- `/tmp/agenthub_orchestrator_quality_sse.jsonl`
- `/tmp/agenthub_deployment_release_api_e2e_report.json`
- `/tmp/agenthub_b2_todo_05_prod_default_e2e_report.json`
- `/tmp/agenthub_b2_todo_05_demo_container_e2e_report.json`
- `/tmp/agenthub_b2_todo_05_orch_prod_default_report.json`
- `/tmp/agenthub_b2_todo_05_orch_demo_report.json`
- `/tmp/agenthub_b2_todo_05_orch_repair_report.json`
- `/tmp/agenthub_deployment_flow_report.json`
- `/tmp/agenthub_deployment_repair_flow_report.json`
- `/tmp/agenthub_custom_agent_tools_report.json`
- `/tmp/agenthub_p1_agent_capability_profile_report.json`
- `/tmp/agenthub_p2_agent_capability_profile_v2_report.json`
- `/tmp/agenthub_p1_attribution_report.json`
- `/tmp/agenthub_p1_evaluation_repair_report.json`
- `/tmp/agenthub_p1_review_thread_report.json`
- `/tmp/agenthub_p1_rich_artifacts_report.json`
- `/tmp/agenthub_fullstack_flow_report.json`
- `/tmp/agenthub_frontend_ui_smoke_report.json`
- `/tmp/agenthub_group_messages_report.json`
- `/tmp/agenthub_agent_fallback_matrix_report.json`
- `/tmp/agenthub_agent_fallback_matrix_sse.jsonl`
- `/tmp/agenthub_agent_fallback_matrix_taskcard_report.json`
- `/tmp/agenthub_agent_fallback_matrix_taskcard_sse.jsonl`
- `/tmp/agenthub_command_fulfillment_report.json`
- `/tmp/agenthub_command_fulfillment_sse.jsonl`
- `/tmp/agenthub_command_fulfillment_browser.json`

最终结论：`passed=true`。

第五点部署发布后端直连 E2E 结论：`passed=true`。2026-06-03 已补跑 deployment
repair/redeploy 与自建 builtin Agent `allowed_tools` 白名单 live E2E。前端未完成期间，这些结果只验收
API/SSE 数据、运行时权限和公网 URL，不验收远端前端 UI 卡片渲染。

2026-06-05 重构后全功能回归结论：前端登录/群聊 smoke、后端 direct API、Orchestrator
API/SSE、workflow、rich artifacts、evaluation repair、review repair、fullstack preview/deploy、
Capability Profile v1/v2 均为 `passed=true`。本轮按 repair loop 修复了 3 个后端问题：
并行 executor 真实流式转发、Claude SDK task-scoped session isolation、evaluation repair
instruction 覆盖 placeholder/TODO 失败指令。后端 PID `247387 -> 268246`，Alembic
`7e8f9012abcd (head)`，本机与公网 `/health` 均正常。

2026-06-05 真实 Agent 群聊后端契约 smoke 结论：`/tmp/agenthub_group_messages_report.json`
与 `/tmp/agenthub_group_messages_sse.jsonl` `passed=true`。SSE 中出现 2 个子 Agent
`message_start` 和 2 个 terminal lifecycle event，最终持久化 child messages 均非 Orchestrator
且没有停留在 `streaming`。本轮只验收后端 SSE / persistence 契约，不验收前端真实群聊 UI。

---

## 2. Case Results

| Case | 验收点 | 结果 |
|---|---|---|
| Case 0 - Config | 数据库内置 Orchestrator config 包含 `llm_planning=true`、`orchestrator_parallel_enabled=true`、`orchestrator_parallel_max_concurrency=3` | passed |
| Case 1 - 8082 Quality Gate | 生成 `index.html/styles.css/app.js`；正式调用 `start_workspace_preview` 与 `verify_web_preview`；`http://111.229.151.159:8082/index.html` 返回 200；桌面/移动端截图非空；无 JS error、console error、同源资源 404 | passed |
| Case 2 - Parallel DAG | `claude-code` 与 `opencode-helper` 并行生成前置文件，`codex-helper` 等待后生成 `review.md` | passed |
| Case 3 - Workspace Conflict | `shared-conflict.md` 同一 run 内被多个 task 修改，summary / memory event 记录 conflict，run 不崩溃 | passed |
| Case 4 - Create Custom Agent | `LiveCopywriter-{timestamp}` 创建成功、加入群聊，tool result 返回 id/name/provider/capabilities | passed |
| Case 5 - Deployment / Release API-SSE | Orchestrator 直连后端 API/SSE，正式调用 preview、browser verify、static release、source zip、container deployment，并返回 3 个 `deployment_status` block | passed |
| Case 6 - Deployment Repair / Redeploy | 预置坏 Dockerfile，首次 container deployment 失败后产生 `deployment_health` failure、`reflection_created`、repair agent attempt、第二次 `create_deployment`，最终 container `published=true` | passed |
| Case 7 - Agent Capability Profile v2 | 临时用户隔离；seed conversation 产生 Claude evaluation failure 与 Opencode fallback success；新 conversation follow-up 前无当前 run，但 user-scope v2 profile / preference memory 注入 planner，最终 task/attempt 均为 Opencode | passed |
| Case 7 - Custom Agent Tool Allowlist | 真实聊天创建 builtin 自建 Agent，`allowed_tools=["read_file"]` 持久化；后续运行可读文件，未授权 `write_file` / `bash` 不进入模型 tool list | passed |
| Case 8 - Agent Capability Profile v1 | 当前 conversation 内形成 Claude failure / Opencode success 画像；planner 看到画像后将未点名的 follow-up 唯一 task/attempt 直接分配给 Opencode | passed |
| Case 9 - True Agent Group Messages | group + Orchestrator 运行中为实际负责 Agent 创建独立 child message；SSE 输出 `message_start` / `message_done` / `message_error` 与子 `message_id`；父 Orchestrator final text 无内部 trace | passed |
| Case 10 - Generic Agent Fallback Matrix | Codex / Claude Code / OpenCode Helper 任一首选 Agent 失败后，Orchestrator 自动切换到可用 fallback Agent；失败与成功 attempt 分别写入独立 child message | passed |
| Case 11 - Command Fulfillment Cyberpunk Group Deploy | 显式文档/代码/Diff/多 Agent/review/preview/browser verify/deploy 要求逐项履约；Codex/OpenCode 真实失败后 fallback/repair，最终生成 `review.md` 并发布静态站点 | passed |

Case 5 证据：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment
report: /tmp/agenthub_deployment_flow_report.json
sse: /tmp/agenthub_deployment_flow_sse.jsonl
browser_report: /tmp/agenthub_deployment_flow_browser.json
conversation_id: dfa956ab-9e76-4d06-bfbf-2a743428415b
passed: true
preview_url: http://111.229.151.159:8082/index.html
static_release_url: http://111.229.151.159:8000/releases/Qh2JFsw6lWNvTOydrBpW_Q8Y_9Bkmxiw/index.html
container_url: http://111.229.151.159:8083
deployment_status_blocks: 3
bugs: []
warnings: []
```

2026-06-03 Deployment / Release hardening 证据：

```text
script: backend/scripts/deployment_release_api_e2e.py
base_url: http://111.229.151.159:8000
report: /tmp/agenthub_deployment_release_api_e2e_report.json
conversation_id: 25474a7c-f9e3-42e1-9d11-8e43685c869b
passed: true
preview_url: http://111.229.151.159:8082/index.html
container_status: published
```

2026-06-04 B2-TODO-05 production hardening direct public API E2E 证据：

```text
script: backend/scripts/deployment_release_api_e2e.py
base_url: http://111.229.151.159:8000
report: /tmp/agenthub_b2_todo_05_prod_default_e2e_report.json
conversation_id: 42b7d9e4-1243-4b4c-9394-1ebb54568ed3
passed: true
expected_container_status: not_supported
container_initial_status: not_supported
container_status: not_supported
container_runtime_kind: podman
cleanup_checks: preview/release/source_zip unavailable
```

```text
script: backend/scripts/deployment_release_api_e2e.py
base_url: http://111.229.151.159:8000
report: /tmp/agenthub_b2_todo_05_demo_container_e2e_report.json
conversation_id: 8b5088bd-161b-4f68-aa74-4ab1e8547546
passed: true
expected_container_status: published
container_status_flow: queued -> published
container_runtime_kind: docker
container_worker_id: inproc-container-aacc169897e0
container_attempt_count: 1
container_state_event_count: 13
container_healthcheck_url: http://111.229.151.159:8081/health
container_stop_cleanup: true
production_default_restored_after_demo: true
```

2026-06-04 B2-TODO-05 Orchestrator API/SSE queued worker 公网回归证据：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment
report: /tmp/agenthub_b2_todo_05_orch_prod_default_report.json
sse: /tmp/agenthub_b2_todo_05_orch_prod_default_sse.jsonl
conversation_id: 963afa42-0549-4fa0-81b0-8fad6b013a4b
passed: true
expected_container_status: not_supported
container_initial_status: not_supported
container_status: not_supported
container_runtime_kind: podman
deployment_status_block_has_runtime_metadata: true
deployment_not_supported_no_repair: true
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment
report: /tmp/agenthub_b2_todo_05_orch_demo_report.json
sse: /tmp/agenthub_b2_todo_05_orch_demo_sse.jsonl
conversation_id: ce767e6f-b03c-41fb-af85-fe637983c356
passed: true
expected_container_status: published
container_status_flow: publishing -> published
container_runtime_kind: docker
container_worker_id: inproc-container-71038d04c528
container_attempt_count: 1
container_state_event_count: 12
container_healthcheck_url: http://111.229.151.159:8081/
container_stop_cleanup: true
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment_repair
report: /tmp/agenthub_b2_todo_05_orch_repair_report.json
sse: /tmp/agenthub_b2_todo_05_orch_repair_sse.jsonl
conversation_id: 8e9c8505-40bc-4753-8734-317744e98d9d
passed: false
observed_failure_category: build_failed
observed_last_error_code: container_build_failed
deployment_repair_initial_failure_seen: true
deployment_repair_reflection_created: false
deployment_repair_redeploy_called: false
note: optional repair/redeploy confirmation did not block the B2-TODO-05 queued worker acceptance.
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment
report: /tmp/agenthub_deployment_flow_report.json
sse: /tmp/agenthub_deployment_flow_sse.jsonl
browser_report: /tmp/agenthub_deployment_flow_browser.json
conversation_id: 04b2317a-a121-4364-aee5-56441f62b1ac
passed: true
preview_url: http://111.229.151.159:8082/index.html
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment_repair
report: /tmp/agenthub_deployment_repair_flow_report.json
sse: /tmp/agenthub_deployment_repair_flow_sse.jsonl
browser_report: /tmp/agenthub_deployment_repair_flow_browser.json
conversation_id: dcb2dbd6-e256-41a7-bd3f-1b99b0aaf66a
passed: true
deployment_repair_initial_failure_seen: true
deployment_repair_reflection_created: true
deployment_repair_redeploy_called: true
container_deployment_published: true
container_health_ok: true
```

2026-06-03 自建 Agent `allowed_tools` 白名单 live E2E 证据：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: custom_agent_tools
report: /tmp/agenthub_custom_agent_tools_report.json
sse: /tmp/agenthub_custom_agent_tools_sse.jsonl
conversation_id: 6eb8a60c-a92a-462e-bcea-420eb8104af4
passed: true
custom_agent_created: true
custom_agent_allowed_tools_persisted: true
custom_agent_added_to_group: true
custom_agent_read_file_available: true
custom_agent_unauthorized_tools_blocked: true
```

2026-06-03 P1 完善项公网 API/SSE live E2E 证据：

```text
preflight:
  backend pytest: tests/test_orchestrator.py tests/test_artifact_parser.py tests/test_stream_content_blocks.py - 90 passed
  backend ruff: scripts/orchestrator_live_e2e.py app/agents/orchestrator app/agents/artifact_parser.py app/api/v1/stream_accumulator.py app/schemas/message.py tests/... - passed
  backend mypy: app/agents/orchestrator app/agents/artifact_parser.py app/api/v1/stream_accumulator.py app/schemas/message.py - passed
  frontend tests: ContentRenderer.test.tsx chatStore.test.ts - 9 passed
  frontend tsc: pnpm exec tsc --noEmit - passed
deployment:
  old_pid: 2867994
  new_pid: 2872639
  alembic_current: 5c6d7e8f9012 (head)
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: p1_attribution
report: /tmp/agenthub_p1_attribution_report.json
sse: /tmp/agenthub_p1_attribution_sse.jsonl
conversation_id: 6df2b527-cc76-4881-bb24-f8aed18e433b
agent_message_id: 5e87c719-8fc6-4d8d-995f-c453c3bdc06f
duration_seconds: 25.134
passed: true
p1_attribution_two_sub_agent_switches: true
p1_attribution_sse_chunks_have_agent_id: true
p1_attribution_sse_child_chunks_have_real_agent_id: true
p1_attribution_persisted_blocks_have_agent_id: true
p1_attribution_persisted_child_blocks_segmented: true
p1_attribution_plan_summary_orchestrator: true
p1_attribution_no_raw_agent_header_semantics: true
p1_attribution_workspace_artifacts_created: true
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: p1_workflow
report: /tmp/agenthub_p1_workflow_report.json
sse: /tmp/agenthub_p1_workflow_sse.jsonl
conversation_id: a6bdaa88-e142-4a56-9cf2-1f45afd47119
agent_message_id: cfae2d61-aa36-405d-a1b5-7de71a3e9b6d
duration_seconds: 54.733
passed: true
p1_workflow_block_present: true
p1_workflow_block_has_agent_id: true
p1_workflow_block_has_name_path_format: true
p1_workflow_block_has_definition_nodes_edges: true
p1_workflow_validation_passed: true
p1_workflow_runtime_ready: true
p1_workflow_dry_run_not_supported: true
p1_workflow_workspace_file_exists: true
p1_workflow_summary_has_no_validation_failure: true
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: p1_workflow_runtime
report: /tmp/agenthub_p1_workflow_runtime_report.json
sse: /tmp/agenthub_p1_workflow_runtime_sse.jsonl
conversation_id: 12ac1864-0158-48ca-a9f3-6640da9ab6ab
agent_message_id: ae1cfadb-c0a5-46d6-a649-761091ef44eb
duration_seconds: 84.355
passed: true
p1_workflow_runtime_block_present: true
p1_workflow_runtime_block_has_last_run_id: true
p1_workflow_runtime_statuses_passed: true
p1_workflow_runtime_workspace_file_exists: true
p1_workflow_runtime_initial_run_present: true
p1_workflow_runtime_last_run_all_nodes_passed: true
p1_workflow_runtime_extra_run_passed: true
p1_workflow_runtime_history_increased: true
p1_workflow_runtime_health_passed: true
p1_workflow_runtime_summary_mentions_dry_run: true
last_run_id: 132b73b3-6916-4ef0-a121-02b586f6011a
extra_run_id: 9788adb3-fbf2-4aae-b2e3-5fd4006fddf4
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: p1_review_thread_repair
report: /tmp/agenthub_p1_review_thread_report.json
sse: /tmp/agenthub_p1_review_thread_sse.jsonl
conversation_id: 5d0373e4-3801-4242-b812-f03ddacd3fb1
agent_message_id: b694d579-cb62-4dbd-83c6-8434a6e49cf8
duration_seconds: 137.941
passed: true
review_config_patched: true
review_config_restored: true
p1_review_task_present: true
p1_repair_task_present: true
p1_review_events_present: true
p1_review_outcome_needs_repair: true
p1_repair_uses_group_member: true
p1_dispatch_only_group_members: true
p1_summary_includes_review_metadata: true
```

2026-06-03 P1-B2 Rich Artifact / Evaluation Repair 公网 API/SSE live E2E 证据：

```text
preflight:
  backend pytest: tests/test_artifact_parser.py tests/test_stream_content_blocks.py tests/test_orchestrator.py tests/test_orchestrator_evaluation.py tests/test_workspace_api.py tests/test_orchestrator_live_e2e_script.py - 156 passed
  backend ruff: app/agents/orchestrator app/agents/artifact_parser.py app/api/v1/stream_accumulator.py app/schemas/message.py app/schemas/workspace.py app/services scripts/orchestrator_live_e2e.py tests/... - passed
  backend mypy: app/agents/orchestrator app/agents/artifact_parser.py app/api/v1/stream_accumulator.py app/schemas/message.py app/schemas/workspace.py app/services - passed
deployment:
  old_pid: 3178588
  new_pid: 3192468
  alembic_current: 6d7e8f9012ab (head)
  local_health: {"status":"ok"} via --noproxy
  public_health: {"status":"ok"}
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: p1_rich_artifacts
report: /tmp/agenthub_p1_rich_artifacts_report.json
sse: /tmp/agenthub_p1_rich_artifacts_sse.jsonl
conversation_id: c6da3473-b338-4321-ba7d-eb0f877e70ae
duration_seconds: 212.097
passed: true
message_done: true
p1_rich_artifacts_file_blocks_present: true
p1_rich_artifacts_manifest_present: true
p1_rich_artifacts_block_manifest_aligned: true
p1_rich_artifacts_manifest_has_task_run_agent: true
covered_manifest_entries:
  docs/rich-report.md: document, claude-code, task-1
  slides/rich-deck.md: ppt, claude-code, task-2
  assets/rich-logo.svg: image, opencode-helper, task-3
  packages/rich-export.tar: archive, opencode-helper, task-4
```

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: p1_evaluation_repair
report: /tmp/agenthub_p1_evaluation_repair_report.json
sse: /tmp/agenthub_p1_evaluation_repair_sse.jsonl
conversation_id: 5186e757-6a7c-4d0f-8643-c9b3defbc181
duration_seconds: 153.341
passed: true
message_done: true
p1_evaluation_failed_seen: true
p1_evaluation_reflection_seen: true
p1_evaluation_repair_or_fallback_seen: true
p1_evaluation_final_passed_or_manual: true
p1_evaluation_manifest_not_false_passed: true
p1_evaluation_manifest_status_present: true
final_manifest_entry:
  repair-report.md: document, evaluation_status=passed, agent_id=opencode-helper
```

2026-06-04 Agent Capability Profile v1 统一公网 API/SSE live E2E 证据：

```text
preflight:
  backend pytest: tests/test_orchestrator_memory.py tests/test_orchestrator.py tests/test_conversation_api.py tests/test_orchestrator_planning.py tests/test_orchestrator_live_e2e_script.py - 105 passed
  backend ruff: app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py scripts/orchestrator_live_e2e.py tests - passed
  backend mypy: app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py - passed
deployment:
  initial_pid: 3783841
  final_pid: 3866485
  final_started_at: 2026-06-04 15:39:01 CST
  alembic_current: 6d7e8f9012ab (head)
  seed: not executed; no seed/default config changes
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  public_openapi_agent_capability_profile_route: true
  frontend_deployed: false
```

```text
scenario: p1_agent_capability_profile
report: /tmp/agenthub_p1_agent_capability_profile_report.json
sse: /tmp/agenthub_p1_agent_capability_profile_sse.jsonl
conversation_id: 8dd905aa-e51a-4f68-b869-2cc4c6278a3d
seed_user_message_id: f9518db3-431b-4112-b7ca-1b7c88d443b1
seed_agent_message_id: f5d9ef06-7916-40bd-b94b-30fbadb09008
followup_user_message_id: 0158fe71-7753-45d8-8c61-4b17d332badf
followup_agent_message_id: 826bc238-44ad-4298-ab45-f609b74ea546
duration_seconds: 146.204
passed: true
profile_before_followup:
  claude-code: task_count=1, success_count=0, failure_count=1, evaluation_failed_count=1
  opencode-helper: task_count=1, success_count=1, failure_count=0, evaluation_failed_count=0
followup_task_agents: [opencode-helper]
followup_attempt_agents: [opencode-helper]
memory_context_mentioned: true
selection_basis_visible: true
capability-followup.md: created
```

2026-06-04 Agent Capability Profile v2 / User Preference Memory 公网 API/SSE live E2E 证据：

```text
preflight:
  backend pytest: tests/test_orchestrator_memory.py tests/test_conversation_api.py tests/test_orchestrator_planning.py tests/test_orchestrator.py tests/test_orchestrator_live_e2e_script.py - 114 passed
  backend ruff: app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py scripts/orchestrator_live_e2e.py tests/test_orchestrator_memory.py tests/test_conversation_api.py tests/test_orchestrator_planning.py tests/test_orchestrator_live_e2e_script.py - passed
  backend mypy: app/services/orchestrator_memory.py app/api/v1/conversations.py app/schemas/conversation.py app/agents/orchestrator/planner.py - passed
deployment:
  initial_pid: 4026860
  final_pid: 4041153
  final_started_at: 2026-06-04 19:09:46 CST
  alembic_current: 7e8f9012abcd (head)
  seed: not executed; no seed/default config changes
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  public_openapi_agent_capability_profile_v2_route: true
  public_openapi_agent_capability_profile_v2_schema: true
  orchestrator_config: llm_planning=true, memory=true, evaluation=true, task_fallback_has_opencode=true
  frontend_deployed: false
```

```text
scenario: p2_agent_capability_profile_v2
report: /tmp/agenthub_p2_agent_capability_profile_v2_report.json
sse: /tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl
temporary_account: cap_v2_e2e_1780571438_4042116
register_status_code: 201
seed_conversation_id: d9c96baf-2e4e-4b3a-a4a0-39ee68bf2f27
followup_conversation_id: 0d7ed6d6-dcbf-4212-9150-55d410af622c
seed_user_message_id: 090dee01-24b7-44e4-a5e5-8263ffdb5860
seed_agent_message_id: b37861b5-8e80-4cf0-826d-77bbd5d22786
followup_user_message_id: 488ea6a5-c1b8-436f-9025-634f0a644245
followup_agent_message_id: 2c84472c-e958-41d6-acc5-aec12093645a
duration_seconds: 152.897
passed: true
followup_runs_before_count: 0
profile_v2_before_followup:
  scope: user
  runs_considered: 1
  source_conversation_count: 1
  claude-code: task_count=1, success_count=0, failure_count=1, evaluation_failed_count=1, score=-0.945
  opencode-helper: task_count=1, success_count=1, failure_count=0, evaluation_failed_count=0, score=1.35
preferences_before_followup:
  artifact_preferences: document=2, other=1
  domains: document=2, deployment=2, evaluation=1, frontend=1, data=1
followup_task_agents: [opencode-helper]
followup_attempt_agents: [opencode-helper]
memory_context_v2_mentioned: true
preference_memory_mentioned: true
p2-capability-v2-followup.md: created
```

统一回归场景：

```text
p1_attribution:
  report: /tmp/agenthub_p1_attribution_report.json
  conversation_id: 4ccfc31f-bd68-4b9c-9471-775445acd7ed
  duration_seconds: 68.896
  passed: true
p1_evaluation_repair:
  report: /tmp/agenthub_p1_evaluation_repair_report.json
  conversation_id: d696e947-9dd6-41e3-ab35-d3c363697255
  duration_seconds: 163.286
  passed: true
p1_review_thread_repair:
  report: /tmp/agenthub_p1_review_thread_report.json
  conversation_id: 87d8ec02-ff6e-4b9a-8dd9-6c6f8eb9546e
  duration_seconds: 108.255
  passed: true
  review_config_restored_via_public_agents_api: true
quality:
  report: /tmp/agenthub_orchestrator_quality_report.json
  browser_report: /tmp/agenthub_orchestrator_quality_browser.json
  sse: /tmp/agenthub_orchestrator_quality_sse.jsonl
  conversation_id: 5bf3d175-e0ed-49cd-a659-c0d9b3cfb99f
  duration_seconds: 536.104
  preview_url: http://111.229.151.159:8082/index.html
  passed: true
```

2026-06-05 重构后全功能前后端联调 / API fallback 回归证据：

```text
frontend_ui_smoke:
  report: /tmp/agenthub_frontend_ui_smoke_report.json
  screenshot: /tmp/agenthub_frontend_ui_smoke.png
  frontend_url: http://154.44.25.94:1573
  passed: true
deployment_release_api:
  report: /tmp/agenthub_deployment_release_api_e2e_report.json
  passed: true
p1_attribution:
  report: /tmp/agenthub_p1_attribution_report.json
  sse: /tmp/agenthub_p1_attribution_sse.jsonl
  passed: true
p1_workflow:
  report: /tmp/agenthub_p1_workflow_report.json
  sse: /tmp/agenthub_p1_workflow_sse.jsonl
  passed: true
p1_workflow_runtime:
  report: /tmp/agenthub_p1_workflow_runtime_report.json
  sse: /tmp/agenthub_p1_workflow_runtime_sse.jsonl
  passed: true
custom_agent_tools:
  report: /tmp/agenthub_custom_agent_tools_report.json
  passed: true
quality:
  report: /tmp/agenthub_orchestrator_quality_report.json
  browser_report: /tmp/agenthub_orchestrator_quality_browser.json
  sse: /tmp/agenthub_orchestrator_quality_sse.jsonl
  conversation_id: 715bb73d-8d6e-4889-b6bf-1335a6bba6d2
  passed: true
fullstack:
  report: /tmp/agenthub_fullstack_flow_report.json
  browser_report: /tmp/agenthub_fullstack_flow_browser.json
  sse: /tmp/agenthub_fullstack_flow_sse.jsonl
  conversation_id: 214f08b4-c23b-4279-89d3-d8a6beda6264
  preview_url: http://111.229.151.159:8082/index.html
  static_release_url: http://111.229.151.159:8000/releases/M0deVgY7XtEU7pMMNnOt4lJdi4DEYHUL/index.html
  passed: true
p1_review_thread_repair:
  report: /tmp/agenthub_p1_review_thread_report.json
  sse: /tmp/agenthub_p1_review_thread_sse.jsonl
  conversation_id: a0c92979-d5b1-4bc2-a770-7fe26bcaf93b
  passed: true
p1_rich_artifacts:
  report: /tmp/agenthub_p1_rich_artifacts_report.json
  sse: /tmp/agenthub_p1_rich_artifacts_sse.jsonl
  conversation_id: b9ec8187-fb1c-4fc5-ab7a-1d1574021922
  passed: true
p1_evaluation_repair:
  report: /tmp/agenthub_p1_evaluation_repair_report.json
  sse: /tmp/agenthub_p1_evaluation_repair_sse.jsonl
  conversation_id: 5d2f2e16-ca5f-4b4d-91c6-6c1fcba8f35b
  passed: true
p1_agent_capability_profile:
  report: /tmp/agenthub_p1_agent_capability_profile_report.json
  sse: /tmp/agenthub_p1_agent_capability_profile_sse.jsonl
  conversation_id: 4c304168-ae27-477d-ab29-5d172dd06c0d
  passed: true
p2_agent_capability_profile_v2:
  report: /tmp/agenthub_p2_agent_capability_profile_v2_report.json
  sse: /tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl
  seed_conversation_id: 7f573b3e-45a2-4016-9701-0eb6f73c7f16
  followup_conversation_id: 064c551a-a3d7-448b-944e-8c57975c526c
  followup_runs_before_count: 0
  passed: true
```

2026-06-05 Response Presentation 公网 API/SSE smoke 证据：

```text
response_presentation_smoke:
  report: /tmp/agenthub_response_presentation_report.json
  sse: /tmp/agenthub_response_presentation_sse.jsonl
  base_url: http://111.229.151.159:8000
  backend_pid_before: 715177
  backend_pid_after: 715177
  backend_restarted: false
  seed_agents_run: true
  alembic_current: 7e8f9012abcd (head)
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  config_assertions:
    react_trace_visible: false
    orchestrator_response_polish_enabled: true
    planner_model_backend: deepseek
  direct_answer_identity:
    conversation_id: ce5a3e9f-3a71-4564-9918-ddec2b7c0925
    message_id: 9daf6451-14af-4096-9552-ff22b7248eff
    status: done
    process_block_present: false
    forbidden_terms: []
    passed: true
  light_task_failure_readable:
    conversation_id: 6181f178-2b83-4a3c-94cb-e0df486effa8
    message_id: 4e738891-ef0e-4b62-8f69-f441e2230ce7
    run_id: 458c138f-2568-4b4d-b77d-faab168e06c6
    status: done
    run_detail: 1 task / 1 attempt / 11 events
    process_block_present: false
    forbidden_terms: []
    passed: true
  react_trace_hidden:
    conversation_id: 7a3506ef-aff5-4e1d-b839-13a5083f905f
    message_id: 032bfa33-08a6-453a-85ec-52dfaf1a4531
    run_id: 39cb3d45-ad24-4990-9169-8bd836ad895f
    status: done
    run_detail: 1 task / 1 attempt / 11 events
    process_block_present: false
    forbidden_terms: []
    passed: true
  raw_evidence_preserved: true
  process_block_expected: false
  passed: true
```

2026-06-05 Claude Code shared auth permission repair 公网 API/SSE smoke 证据：

```text
claude_auth_permission_repair:
  report: /tmp/agenthub_claude_auth_permission_report.json
  sse: /tmp/agenthub_claude_auth_permission_sse.jsonl
  base_url: http://111.229.151.159:8000
  backend_pid_before: 715177
  backend_pid_after: 779884
  backend_restarted: true
  alembic_current: 7e8f9012abcd (head)
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  forbidden_terms:
    - Permission denied
    - "[Errno 13]"
    - /root/.agenthub
    - claude-auth
    - .claude.json
    - Traceback (most recent call last)
  direct_greeting_with_claude_in_group:
    conversation_id: 117156b4-26e7-4f4c-aec1-5d72e7dac055
    message_id: 168691a0-a38f-42ef-b09a-b01c5b6a3d09
    status: done
    stream_final_event: done
    visible_sse_forbidden_terms: []
    persisted_text_forbidden_terms: []
    full_sse_forbidden_terms: []
    passed: true
  claude_task_degrades_without_permission_leak:
    conversation_id: a1962721-4b68-4fa4-be9a-3cb67ddf778e
    message_id: 04a2af8e-cdd6-4621-851f-7b914e721ff3
    status: error
    stream_final_event: error
    visible_sse_forbidden_terms: []
    persisted_text_forbidden_terms: []
    full_sse_forbidden_terms: []
    note: existing no_runnable_agent behavior preserved when Claude Code is unavailable
    passed: true
  passed: true
```

2026-06-05 Orchestrator 同例前端演示 repair loop 公网 API/SSE 证据：

```text
same_prompt_frontend_demo_repair:
  prompt: "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、按钮交互和移动端适配的前端开发演示，并行执行，主题赛博朋克风，部署在端口8082，并完成浏览器级质量验收"
  report: /tmp/agenthub_same_prompt_repair_report_final.json
  sse: /tmp/agenthub_same_prompt_repair_sse_final.jsonl
  browser_report: /tmp/agenthub_orchestrator_quality_browser.json
  base_url: http://111.229.151.159:8000
  backend_pid_final: 858990
  seed_agents_executed: true
  alembic_current: 7e8f9012abcd (head)
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  conversation_id: ddb4837b-d4f9-4a2a-b42c-a1ab59bc5ae7
  message_id: b2b955f0-3f4d-4d4d-8c76-dd9a1c239333
  run_id: 74251fbc-55b6-44e7-9b5d-b1c2edef04fa
  duration_seconds: 547.135
  root_causes:
    - OpenCode shared auth permission errors were not normalized.
    - Empty planner task payloads did not trigger frontend deterministic fallback.
    - A previous managed preview session could occupy requested port 8082 across live reruns.
  fixes:
    - OpenCode shared auth readability and copy errors are normalized; runtime status requires credentials or readable shared auth.
    - Empty planner task payload is treated as planner protocol failure for template fallback.
    - Explicit requested preview ports can replace older managed preview sessions; external port conflicts still fail.
  final_checks:
    orchestrator_llm_planning_enabled: true
    orchestrator_parallel_enabled: true
    orchestrator_parallel_concurrency_3: true
    message_done: true
    planner_used_llm: true
    has_html_artifact: true
    workspace_has_required_frontend_files: true
    preview_8082_public_accessible: true
    preview_uses_requested_8082: true
    platform_preview_tool_called: true
    browser_verify_passed: true
    browser_desktop_screenshot_exists: true
    browser_mobile_screenshot_exists: true
    browser_no_console_errors: true
    browser_no_page_errors: true
    browser_no_failed_requests: true
    browser_mobile_no_horizontal_overflow: true
    browser_button_interaction_ok: true
    artifact_covers_required_sections: true
    passed: true
```

2026-06-05 真实 Agent 群聊后端契约公网 API/SSE smoke 证据：

```text
group_messages_deterministic_smoke:
  report: /tmp/agenthub_group_messages_report.json
  sse: /tmp/agenthub_group_messages_sse.jsonl
  base_url: http://111.229.151.159:8000
  backend_pid_before: 1189179
  backend_pid_after: 1203019
  backend_restarted: true
  alembic_current: 7e8f9012abcd (head)
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  temporary_config_restored: true
  conversation_id: 0948e3a6-1fc4-40a2-8cf7-3e348b2047ae
  parent_message_id: fc81e594-5f4c-4eca-b593-570d629e6f71
  run_id: 34f5ef15-e649-4827-84e4-0808037f8cfe
  events_by_type:
    message_start: 2
    message_done: 1
    message_error: 1
    done: 1
  child_messages:
    writer:
      status: error
      note: business-level workspace path failure was isolated to the writer child message
      content_types: [tool_call, tool_call, tool_call, text, tool_call, text]
    web-designer:
      status: done
      content_types: [tool_call, text, code, text, file]
  checks:
    parent_done: true
    message_start_count_at_least_2: true
    child_terminal_event_count_at_least_2: true
    child_messages_created: true
    child_agents_are_not_orchestrator: true
    expected_child_agents_seen: true
    expected_terminal_agents_seen: true
    no_child_left_streaming: true
    all_child_messages_terminal: true
    child_content_present: true
    final_text_no_forbidden_terms: true
    child_text_no_core_trace: true
    sse_no_core_trace: true
  passed: true
```

2026-06-06 真实 Agent 群聊 + OpenCode 式过程展示 repair loop 公网证据：

```text
architected_frontend_group_chat_repair:
  report: /tmp/agenthub_architected_frontend_group_chat_report.json
  sse: /tmp/agenthub_architected_frontend_group_chat_sse.jsonl
  browser_report: /tmp/agenthub_architected_frontend_group_chat_browser.json
  base_url: http://111.229.151.159:8000
  frontend_url_checked: http://154.44.25.94:1573
  frontend_static_deployed: false
  frontend_static_deploy_note: 154.44.25.94:1573 is not served by this backend host;
    local frontend tests/build passed, remote static publishing must be done by the frontend host.
  backend_pid_before_final_restart: 1263466
  backend_pid_after_final_restart: 1271744
  alembic_current: 7e8f9012abcd (head)
  seed_agents_rerun_this_round: false
  local_health: {"status":"ok"}
  public_health: {"status":"ok"}
  conversation_id: fbcd2fc5-ef65-4e0a-971a-6f700437a82c
  user_message_id: 32d6f98f-d8a9-4ee5-9a29-fb5aa0393f4f
  parent_orchestrator_message_id: 675cde50-1dea-46b1-83d8-07a6e21f99bd
  run_id: aa968e64-aeb4-4eca-b74b-ab51d26dff53
  child_messages:
    codex-helper: 6fed1bbf-e054-43db-8d15-bf5013d902c2
    opencode-helper: d6aba3d0-4a27-4fb6-97ea-0f1cb175ece5
    claude-code: c660e36d-f9ab-44fe-a9f1-632c828515a0
  sse_counts:
    message_start: 3
    message_done: 3
    message_error: 0
    process_delta: 23
    done: 1
  agent_switch_order:
    - codex-helper
    - opencode-helper
    - claude-code
  workspace_files:
    - planning.md
    - index.html
    - styles.css
    - app.js
    - diff.md
  preview_8082:
    url: http://111.229.151.159:8082/index.html
    http_status: 200
  checks:
    group_child_message_start_all_agents: true
    group_persisted_child_messages_all_agents: true
    group_child_messages_have_process: true
    group_child_process_delta_seen: true
    group_codex_architect_first: true
    group_parent_does_not_embed_child_outputs: true
    workspace_has_required_frontend_files: true
    browser_verify_passed: true
    browser_desktop_screenshot_exists: true
    browser_mobile_screenshot_exists: true
    browser_no_console_errors: true
    browser_no_page_errors: true
    browser_no_failed_requests: true
    browser_mobile_no_horizontal_overflow: true
    browser_button_interaction_ok: true
    final_summary_no_missing_or_pending: true
    passed: true
```

2026-06-06 后续修正：

- 上述公网前端场景只作为真实群聊、子 `message_id` 路由、流式 `process_delta`
  和平台 preview/browser verify 的集成证据，不再作为“前端质量演示专用模板”
  的产品契约。
- 已撤销前端质量演示的 deterministic planner override、`frontend-architecture`
  fallback planning.md 和缺 HTML 时的 static demo scaffold。前端 prompt 只是示例，
  不能驱动 Orchestrator 进入硬编码任务模板。
- 当前不变量：真实 Agent 群聊与公开 process 流适用于所有 Orchestrator 子任务；
  LLM planner 输出不会被前端模板覆盖；planner 协议错误默认以可见错误暴露，
  只有显式 `planner_fallback_to_template=true` 才走 legacy generic fallback。
- 子 Agent child message 均应带独立 `process` block 和流式 `process_delta`；
  父 Orchestrator message 只保留调度、平台工具、质量门和最终总结。

2026-06-06 通用场景 E2E 扩展：

- 新增非前端模板 live scenarios：
  - `group_process_document_strategy`
  - `group_process_data_analysis`
  - `group_process_workflow_delivery`
  - `group_process_failure_readable`
  - `group_process_frontend_preview`
- 前四个 generic case 覆盖文档策略、数据分析、workflow 交付和可读失败处理；
  它们不再依赖前端质量演示模板，也不要求 `index.html/styles.css/app.js`。
- 新增默认证据路径：
  - `/tmp/agenthub_group_process_document_strategy_report.json`
  - `/tmp/agenthub_group_process_document_strategy_sse.jsonl`
  - `/tmp/agenthub_group_process_data_analysis_report.json`
  - `/tmp/agenthub_group_process_data_analysis_sse.jsonl`
  - `/tmp/agenthub_group_process_workflow_delivery_report.json`
  - `/tmp/agenthub_group_process_workflow_delivery_sse.jsonl`
  - `/tmp/agenthub_group_process_failure_readable_report.json`
  - `/tmp/agenthub_group_process_failure_readable_sse.jsonl`
  - `/tmp/agenthub_group_process_frontend_preview_report.json`
  - `/tmp/agenthub_group_process_frontend_preview_sse.jsonl`
- 本轮修复了明确 multi-agent 请求的保守归属平衡：当用户明确要求“两个/多个 Agent”
  或真实群聊，而 LLM planner 把多个 implementation task 全派给同一 Agent 时，
  Orchestrator 会按用户明确点名的多个 Agent 或通用偏好顺序重新分配责任人；
  不改 task id/title/instruction，不创建前端专用模板。
- 本地门禁：

```text
cd backend
AGENTHUB_ALLOW_DEV_DB_TESTS=1 uv run python -m pytest \
  tests/test_orchestrator_live_e2e_script.py \
  tests/test_orchestrator_planning.py \
  tests/test_stream_content_blocks.py -q
# 72 passed

uv run python -m ruff check \
  app/agents/orchestrator/adapter.py \
  app/agents/orchestrator/task_planning.py \
  scripts \
  tests/test_orchestrator_live_e2e_script.py \
  tests/test_orchestrator_planning.py
# passed

uv run python -m mypy \
  app/agents/orchestrator/adapter.py \
  app/agents/orchestrator/task_planning.py \
  scripts/orchestrator_e2e
# passed
```

- 后端本机运行代码已同步到 PID `1650213`；`alembic current` 为
  `7e8f9012abcd (head)`；本机 `/health` 为 `{"status":"ok"}`。
- 阻断记录：
  - 手动 Codex CLI smoke 复现 `You've hit your usage limit... try again at Jun 11th, 2026 5:54 PM`。
    因此当前环境不能把 Codex Helper 作为必须成功的 live execution gate。
  - `AGENTHUB_E2E_BASE_URL=http://111.229.151.159:8000` 的请求未出现在本机
    PID `1650213` 的 uvicorn access log 中；公网 8000 当前可能未命中本轮已重启的
    本机后端实例。公网 `/health` 仍返回 `{"status":"ok"}`，但不能证明加载了本轮未提交代码。
  - `group_process_document_strategy` 本机 API/SSE run 已生成
    `/tmp/agenthub_group_process_document_strategy_report.json` 和
    `/tmp/agenthub_group_process_document_strategy_sse.jsonl`；当前未达到 `passed=true`，
    主要失败层为 planner/live runtime 仍选择 Codex 并被额度限制阻断。
- 本轮不把上述 live 阻断伪装为通过；后续需要先确认公网 8000 落点与 Codex quota /
  runtime policy，再重跑五个新增场景。

2026-06-06 通用 Agent fallback matrix repair loop（历史证据，已被 2026-06-07 当前内置矩阵取代）：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: agent_fallback_matrix
report: /tmp/agenthub_agent_fallback_matrix_report.json
sse: /tmp/agenthub_agent_fallback_matrix_sse.jsonl
backend_pid: 1688851
alembic_current: 7e8f9012abcd (head)
local_health: {"status":"ok"}
public_health: {"status":"ok"}
passed: true
```

历史验收结论：

- 三个 case 均先尝试首选 Agent，再自动调配 fallback Agent。
- 失败 Agent 独立 child message 以 `message_error` / `status="error"` 结束；fallback Agent 独立 child message 以 `message_done` / `status="done"` 结束。
- persisted workspace 均包含对应 fallback markdown 产物。
- 父 Orchestrator message 不内嵌子 Agent block；最终可见文本不包含 `ReAct step`、`Observation:`、`Action:`、`Tools:`、`call_`、raw stderr 或 stack trace。
- 本轮曾使用旧内置 fallback 证据 Agent；当前产品内置 Agent 已收敛为 `claude-code`、`opencode-helper`、`codex-helper`，请以后续 2026-06-07 task card E2E 为当前验收依据。

2026-06-07 fallback task card display E2E：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://127.0.0.1:8000
scenario: agent_fallback_matrix
report: /tmp/agenthub_agent_fallback_matrix_taskcard_report.json
sse: /tmp/agenthub_agent_fallback_matrix_taskcard_sse.jsonl
backend_pid: 3220462
seed: not required; temporary orchestrator config restored
local_health: {"status":"ok"}
passed: true
```

Case evidence：

```text
agent_fallback_claude_unavailable:
  planned_agent_id: claude-code
  final_agent_id: opencode-helper
  task_card.agent_id: opencode-helper
  child_messages: claude-code=error, opencode-helper=done
  artifact: fallback-claude.md

agent_fallback_opencode_unavailable:
  planned_agent_id: opencode-helper
  final_agent_id: claude-code
  task_card.agent_id: claude-code
  child_messages: opencode-helper=error, claude-code=done
  artifact: fallback-opencode.md

agent_fallback_codex_unavailable:
  planned_agent_id: codex-helper
  final_agent_id: claude-code
  task_card.agent_id: claude-code
  child_messages: codex-helper=error, claude-code=done
  artifact: fallback-codex.md
```

验收结论：

- 三个 case 均通过真实 HTTP/SSE，首选 Agent 失败后由当前内置 Agent 之一完成 fallback。
- task card 不再展示“原计划 Agent 正在做”；fallback 后 `planned_agent_id` 保留原 Agent，`agent_id/final_agent_id` 指向最终 attempt Agent。
- 报告交叉校验了 task card、`orchestrator_run_detail.attempts/events`、child message terminal 状态和 workspace artifact。
- E2E 使用 per-agent `sub_agent_config_overrides` 制造可控 runtime 失败，不修改 Agent 表持久配置；执行结束后 Orchestrator config 已恢复。

2026-06-07 command fulfillment repair loop：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: command_fulfillment_cyberpunk_group_deploy
report: /tmp/agenthub_command_fulfillment_report.json
sse: /tmp/agenthub_command_fulfillment_sse.jsonl
browser_report: /tmp/agenthub_command_fulfillment_browser.json
conversation_id: 25ff9e75-7776-46b2-8549-babb78555177
backend_pid: 3398114
seed: not required after latest app/scripts-only changes
alembic_current: 7e8f9012abcd
local_health: {"status":"ok"}
public_health: {"status":"ok"}
passed: true
```

验收证据：

- `command_child_agents_at_least_2=true`，SSE 中出现 Codex / Claude / OpenCode 尝试与后续 Claude repair child message。
- `command_fulfillment_document/code_artifacts/multi_agent/review/preview/browser_verify/deployment/diff_satisfied=true`。
- workspace 包含 `planning.md`、`design-doc.md`、`index.html`、`styles.css`、`app.js`、`diff.md`、`review.md`。
- 正式平台闭环为 `start_workspace_preview -> verify_web_preview -> create_deployment`；8082 preview 可访问，browser report `passed=true`，static release URL `http://111.229.151.159:8000/releases/vw1Obog5VUQ1cY4lCNzBaevfgnDc1Epy/index.html` 返回 200。
- `agent_output_no_long_running_server_command=true`，Orchestrator 最终/中间可见文本不再建议用户手动运行 `python -m http.server`、`npm run dev` 等本地长运行服务命令。
- 本轮真实遇到 `codex-helper` 与 `opencode-helper` runtime failure；Orchestrator 没有停止整条命令，后续通过 fallback/repair 和 Orchestrator coordination review 生成 `review.md` 并完成部署。
- `planner_used_llm=false` 作为诊断项保留，但不属于该 scenario 的 hard acceptance：显式 command contract 下允许 LLM planner 失败后进入通用 command fallback，不视为产品失败。

---

## 3. Regression And Deployment

回归结果：

```bash
cd backend
uv run pytest -q
# 440 passed, 7 skipped, 1 warning in 46.93s
```

```bash
uv run ruff check app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/workspace/preview_verifier.py app/core/config.py app/schemas/agent.py app/api/v1/stream_orchestrator_context.py app/agents/registry.py
# passed
```

```bash
uv run mypy app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/workspace/preview_verifier.py app/core/config.py app/schemas/agent.py
# passed
```

后端部署：

```bash
cd /home/ubuntu/agenthub/backend
nohup uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info > /tmp/agenthub_backend.log 2>&1 &
uv run python -m app.seeds.seed_agents
curl --noproxy '*' http://127.0.0.1:8000/health
curl --noproxy '*' http://111.229.151.159:8000/health
```

健康检查均返回：

```json
{"status":"ok"}
```

部署注意：

- 改 Orchestrator 默认配置或 seed 后必须重新执行 `seed_agents`。
- 前端服务为 `http://154.44.25.94:1573`，本轮不需要部署前端。
- 8082 preview 由平台 preview service 管理，不由 Agent runtime 启动。

---

## 4. E2E Bugfixes

| 问题 | 现象 | 修复位置 |
|---|---|---|
| Parallel AsyncSession concurrency | 并行 DAG 中多个 task 同时获取 adapter 或写 memory 时触发 SQLAlchemy AsyncSession 并发错误 | `backend/app/agents/registry.py`、`backend/app/api/v1/stream_orchestrator_context.py`、`orchestrator/memory_hooks.py` |
| Direct routing over-match | “让 claude-code 生成文件”误判为 direct broadcast，绕过 planner/DAG | `orchestrator/task_planning.py` |
| Platform fact steals task intent | “创建 Agent 并加入群聊”被 platform fact router 当作能力问答 | `orchestrator/platform_facts.py` |
| Artifact path normalization | `workspace/foo.md`、`/workspace/foo.md` 被当成不可达路径，产生 false artifact missing | `orchestrator/artifacts.py` |
| Parallel diff false conflict | 并发 batch 中 after snapshot 看见其他 task 创建文件，误报 file change/conflict | `orchestrator/execution.py`、`orchestrator/workspace_changes.py` |
| Workflow text fence persistence | 真实外部 Agent 可能把 workflow fenced YAML 放在普通 text block 中，导致消息落库没有 workflow ContentBlock | `backend/app/api/v1/stream_accumulator.py` |
| Review task evaluator interference | review task 提到被审 markdown 时被 document evaluator 当作自己的交付产物，`needs_repair` 被覆盖成 `failed` | `backend/app/agents/orchestrator/execution.py` |
| Review config restore loop | live E2E 脚本分两次 `asyncio.run` patch/restore DB config 时复用 async engine，恢复可能遇到 event-loop mismatch | `backend/scripts/orchestrator_live_e2e.py` |
| Capability profile not visible to planner | planner system prompt 要求参考画像，但 `_planner_messages()` 丢弃传入 messages，planner 实际看不到 memory 中的 capability profile | `backend/app/agents/orchestrator/planner.py`、`backend/tests/test_orchestrator_planning.py` |
| Capability profile seed produced misleading evidence | planner 把 repair 拆成第二个 task，或子 Agent 在单次调用内模拟 fallback，导致画像强弱反转 | `backend/scripts/orchestrator_live_e2e.py`、`backend/tests/test_orchestrator_live_e2e_script.py` |
