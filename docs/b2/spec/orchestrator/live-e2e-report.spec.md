# Orchestrator Live E2E Report

> 状态：Passed
> 最后更新：2026-05-31

---

## 1. Summary

本报告记录 Orchestrator 真实部署链路的验收结果。它只作为 evidence，不承载能力契约；能力契约分别见：

- DAG 并行：[core.spec.md](core.spec.md) 与 [task-planning.spec.md](task-planning.spec.md)
- 平台 tools / 自建 Agent：[tool-calling.spec.md](tool-calling.spec.md)
- Workspace 冲突：[workspace-conflict.spec.md](workspace-conflict.spec.md)
- Preview / browser verify：[../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)

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

最终结论：`passed=true`。

---

## 2. Case Results

| Case | 验收点 | 结果 |
|---|---|---|
| Case 0 - Config | 数据库内置 Orchestrator config 包含 `llm_planning=true`、`orchestrator_parallel_enabled=true`、`orchestrator_parallel_max_concurrency=3` | passed |
| Case 1 - 8082 Quality Gate | 生成 `index.html/styles.css/app.js`；正式调用 `start_workspace_preview` 与 `verify_web_preview`；`http://111.229.151.159:8082/index.html` 返回 200；桌面/移动端截图非空；无 JS error、console error、同源资源 404 | passed |
| Case 2 - Parallel DAG | `claude-code` 与 `opencode-helper` 并行生成前置文件，`codex-helper` 等待后生成 `review.md` | passed |
| Case 3 - Workspace Conflict | `shared-conflict.md` 同一 run 内被多个 task 修改，summary / memory event 记录 conflict，run 不崩溃 | passed |
| Case 4 - Create Custom Agent | `LiveCopywriter-{timestamp}` 创建成功、加入群聊，tool result 返回 id/name/provider/capabilities | passed |

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
