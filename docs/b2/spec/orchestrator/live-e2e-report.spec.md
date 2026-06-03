# Orchestrator Live E2E Report

> 状态：Passed
> 最后更新：2026-06-03

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
- `/tmp/agenthub_deployment_flow_report.json`
- `/tmp/agenthub_deployment_repair_flow_report.json`
- `/tmp/agenthub_custom_agent_tools_report.json`

最终结论：`passed=true`。

第五点部署发布后端直连 E2E 结论：`passed=true`。2026-06-03 已补跑 deployment
repair/redeploy 与自建 builtin Agent `allowed_tools` 白名单 live E2E。前端未完成期间，这些结果只验收
API/SSE 数据、运行时权限和公网 URL，不验收远端前端 UI 卡片渲染。

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
| Case 7 - Custom Agent Tool Allowlist | 真实聊天创建 builtin 自建 Agent，`allowed_tools=["read_file"]` 持久化；后续运行可读文件，未授权 `write_file` / `bash` 不进入模型 tool list | passed |

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

---

## 3. Regression And Deployment

回归结果：

```bash
cd backend
uv run pytest -q
# 440 passed, 7 skipped, 1 warning in 46.93s
```

```bash
uv run ruff check app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/browser_preview_verifier.py app/core/config.py app/schemas/agent.py app/api/v1/stream_orchestrator_context.py app/agents/registry.py
# passed
```

```bash
uv run mypy app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/browser_preview_verifier.py app/core/config.py app/schemas/agent.py
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
