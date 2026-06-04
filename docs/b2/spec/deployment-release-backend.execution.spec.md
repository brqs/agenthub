# Deployment / Release Backend Execution Spec

> 状态：Production hardening API E2E passed
> 最后更新：2026-06-04
> 范围：第五点部署发布的后端基础能力实现

## 1. 架构

```text
WorkspaceStaticSnapshotService
├── Preview snapshot -> WorkspaceStaticPreview server -> 8082-8182
└── Static release snapshot -> /releases/{release_token}/{path}
```

Preview 是临时浏览器验收环境；Static Release 是独立、不可变、可停止的发布版本。

## 2. 共享安全快照

`WorkspaceStaticSnapshotService`：

- 仅复制 HTML、CSS、JS、JSON、图片、SVG、字体、favicon 等静态资源。
- 支持嵌套相对路径。
- 排除 `.agenthub/.git/.env/.env.* .ssh/secrets/node_modules/.venv/__pycache__`。
- 拒绝 symlink、路径穿越和非 HTML 入口。
- 使用 staging 目录构建并原子替换。
- 计算 sha256、文件数和总体积。
- 限制单文件大小、文件总数和总体积。

配置：

```text
STATIC_SNAPSHOT_MAX_FILE_COUNT=1000
STATIC_SNAPSHOT_MAX_SINGLE_FILE_BYTES=5000000
STATIC_SNAPSHOT_MAX_TOTAL_BYTES=25000000
```

## 3. Preview

保留 API：

```text
POST   /api/v1/workspaces/{conversation_id}/preview
GET    /api/v1/workspaces/{conversation_id}/preview
DELETE /api/v1/workspaces/{conversation_id}/preview
POST   /api/v1/workspaces/{conversation_id}/preview/verify
```

Preview 不再公开 workspace，而是服务：

```text
/tmp/agenthub_preview_snapshots/{conversation_id}/
```

受控 server 禁止目录列表，并添加 CSP、`X-Content-Type-Options: nosniff`、
`Cache-Control: no-store`。`requested_port=8082` 被占用时明确失败，不静默 fallback。
内容 digest 变化时重建快照并重启 Preview；TTL janitor 回收闲置 session 和孤儿快照。

## 4. Static Release

`create_deployment(kind="static_site")`：

1. 校验 HTML 入口。
2. 构建 `/tmp/agenthub_static_releases/{deployment_id}/` 不可变快照。
3. 生成 24 字节随机 token。
4. 返回稳定公开 URL：
   ```text
   GET /releases/{release_token}
   GET /releases/{release_token}/{path:path}
   ```
5. Stop 时清理快照并使 token 立即失效。

`requested_port` 为兼容字段；Static Release 不分配端口并记录忽略日志。后续修改 workspace
不会改变旧发布版本。

配置：

```text
DEPLOYMENT_PUBLIC_BASE_URL=http://111.229.151.159:8000
DEPLOYMENT_STATIC_ROOT=/tmp/agenthub_static_releases
DEPLOYMENT_RELEASE_TOKEN_BYTES=24
```

## 5. Source Zip

源码包排除敏感与无关目录，记录压缩包 sha256、文件数、字节数和过期时间。janitor 定时清理
过期 zip 和孤儿目录。

配置：

```text
DEPLOYMENT_MAX_EXPORT_BYTES=25000000
DEPLOYMENT_MAX_FILE_COUNT=1000
DEPLOYMENT_MAX_SINGLE_FILE_BYTES=5000000
DEPLOYMENT_EXPORT_TTL_SECONDS=86400
DEPLOYMENT_JANITOR_INTERVAL_SECONDS=300
```

## 6. Container 原生部署 MVP

当前已实现容器部署的安全接口底座、queueable worker 状态流和真实 build/run worker：

- `ContainerPolicyValidator`
- `ContainerDeploymentDispatcher` queueable contract
- `InProcessContainerDeploymentDispatcher` MVP
- `ContainerDeployWorker`
- 生产默认 `DEPLOYMENT_CONTAINER_ENABLED=false`
- 生产推荐 `DEPLOYMENT_CONTAINER_RUNTIME=podman`
- 默认 `DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=false`

Policy 拒绝 privileged、host network、host path mount、Docker socket，以及超过 CPU、memory、
runtime TTL、端口池限额的请求。Docker runtime 只允许在
`DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=true` 时运行；Podman 不要求 trusted host mode。
课程 demo 如需真实 Docker container deployment，必须显式设置
`DEPLOYMENT_CONTAINER_ENABLED=true`、`DEPLOYMENT_CONTAINER_RUNTIME=docker`、
`DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=true`。平台 Worker 会从 workspace snapshot 执行受控
Docker/Podman build/run、分配 `8081-8085` host port、执行 retry/backoff health check，并在 stop /
cleanup 时删除容器、image 和快照。

2026-06-03 hardening MVP 已补齐：

- container build / run / health check 失败路径清理 build context、container、image。
- `deployment_health` evaluation 失败时生成 structured issue 与 reflection repair instruction。
- Orchestrator quality repair agent 修复 workspace 后会重新调用同一个 deployment tool。
- `not_supported` 只记录平台限制，不触发自动修复。
- janitor 纳入 `DEPLOYMENT_CONTAINER_BUILD_ROOT` orphan cleanup；runtime 可用时按 managed label
  清理 orphan container / image。

2026-06-04 production hardening 已补齐：

- container API 创建后立即返回 `status="queued"`，后台 worker 推进
  `queued -> publishing -> published|failed|stopped`。
- `WorkspaceDeployment` 暴露 `worker_id`、`attempt_count`、`failure_category`、
  `last_error_code`、`state_events`，但 API schema 仍不暴露 `snapshot_path`、`release_token`
  或宿主文件路径。
- health check 使用 `DEPLOYMENT_CONTAINER_HEALTH_RETRY_INTERVAL_SECONDS`、
  `DEPLOYMENT_CONTAINER_HEALTH_MAX_ATTEMPTS`、
  `DEPLOYMENT_CONTAINER_HEALTH_BACKOFF_MULTIPLIER`，总耗时仍受
  `DEPLOYMENT_CONTAINER_HEALTH_TIMEOUT_SECONDS` 约束。
- 稳定失败分类：`build_failed`、`run_failed`、`health_check_failed`、`policy_rejected`、
  `port_pool_exhausted`、`runtime_unavailable`、`cleanup_failed`、`timeout`。
- repeated stop 幂等返回 `stopped`；queued/publishing stop 记录 cancellation intent，worker 在边界检查。

详细行为见
[orchestrator/native-deployment.execution.spec.md](orchestrator/native-deployment.execution.spec.md)。

## 7. 数据库与 API

Migration：

```text
3a4b5c6d7e8f_harden_workspace_releases.py
4b5c6d7e8f90_add_container_deployment_runtime_metadata.py
7e8f9012abcd_add_deployment_worker_state.py
```

`WorkspaceDeployment` 增加：

```text
release_token
snapshot_path
artifact_digest
file_count
published_at
stopped_at
expires_at
runtime_id
image_id
container_id
host_port
container_port
runtime_kind
runtime_status
healthcheck_url
logs_tail
worker_id
attempt_count
failure_category
last_error_code
state_events
```

API 响应不暴露内部 `snapshot_path` 和原始 `release_token`。

## 8. 自动化与直接 API E2E

后端自动化重点覆盖：

- Preview 敏感路径、目录列表和快照隔离。
- Static Release 不占 Preview 端口、不可变、Stop 后失效。
- Conversation 删除后 Preview、Release、zip 和 workspace 清理。
- Source zip 敏感路径、digest、过期下载清理。
- Container policy 危险配置拒绝。

直接公网 E2E 已适配 queued-first container worker，并支持
`AGENTHUB_E2E_EXPECT_CONTAINER_STATUS=not_supported|published|any`：

```bash
cd /home/ubuntu/agenthub/backend
uv run python scripts/deployment_release_api_e2e.py
```

报告：

```text
/tmp/agenthub_deployment_release_api_e2e_report.json
/tmp/agenthub_b2_todo_05_prod_default_e2e_report.json
/tmp/agenthub_b2_todo_05_demo_container_e2e_report.json
/tmp/agenthub_b2_todo_05_orch_prod_default_report.json
/tmp/agenthub_b2_todo_05_orch_demo_report.json
/tmp/agenthub_b2_todo_05_orch_repair_report.json
/tmp/agenthub_deployment_flow_report.json
/tmp/agenthub_deployment_repair_flow_report.json
```

2026-06-04 B2-TODO-05 production hardening 直接公网 API E2E 已通过：

```text
production_default:
  report: /tmp/agenthub_b2_todo_05_prod_default_e2e_report.json
  conversation_id: 42b7d9e4-1243-4b4c-9394-1ebb54568ed3
  passed: true
  container_initial_status: not_supported
  container_status: not_supported
  runtime_kind: podman
  cleanup_checks: preview/release/source_zip unavailable
demo_override:
  report: /tmp/agenthub_b2_todo_05_demo_container_e2e_report.json
  conversation_id: 8b5088bd-161b-4f68-aa74-4ab1e8547546
  passed: true
  container_initial_status: queued
  container_status: published
  container_poll_elapsed_seconds: 6.036
  runtime_kind: docker
  worker_id: inproc-container-aacc169897e0
  attempt_count: 1
  state_event_count: 13
  healthcheck_url: http://111.229.151.159:8081/health
  stop_cleanup: container URL unavailable after stop
```

2026-06-03 live E2E 已验证 container 部署失败后触发
`deployment_health failed -> reflection_created -> repair agent attempt -> second create_deployment -> published=true`，
并确认公网 URL 可访问、browser verifier report 通过。

2026-06-04 B2-TODO-05 Orchestrator API/SSE queued worker 公网回归：

```text
production_default:
  report: /tmp/agenthub_b2_todo_05_orch_prod_default_report.json
  sse: /tmp/agenthub_b2_todo_05_orch_prod_default_sse.jsonl
  conversation_id: 963afa42-0549-4fa0-81b0-8fad6b013a4b
  passed: true
  container_initial_status: not_supported
  container_status: not_supported
  runtime_kind: podman
  deployment_status_block_has_runtime_metadata: true
  deployment_not_supported_no_repair: true
demo_override:
  report: /tmp/agenthub_b2_todo_05_orch_demo_report.json
  sse: /tmp/agenthub_b2_todo_05_orch_demo_sse.jsonl
  conversation_id: ce767e6f-b03c-41fb-af85-fe637983c356
  passed: true
  container_initial_status: publishing
  container_status: published
  container_poll_elapsed_seconds: 2.013
  runtime_kind: docker
  worker_id: inproc-container-71038d04c528
  attempt_count: 1
  state_event_count: 12
  healthcheck_url: http://111.229.151.159:8081/
  stop_cleanup: true
optional_repair_confirmation:
  report: /tmp/agenthub_b2_todo_05_orch_repair_report.json
  passed: false
  observed_failure_category: build_failed
  observed_last_error_code: container_build_failed
  reason: no reflection_created/redeploy loop observed in this optional run
```

## 9. 2026-06-04 执行记录

2026-06-04 B2-TODO-05 production hardening 执行时包含 migration 和后端代码变更，实际部署同步命令为：

```bash
cd /home/ubuntu/agenthub/backend
uv run alembic upgrade head
uv run alembic current
sudo systemctl restart agenthub-backend
```

未修改 seed 或 `ORCHESTRATOR_DEFAULTS`，无需重新执行 `seed_agents`。

## 10. 真实执行证据

2026-06-04 完成 B2-TODO-05 production hardening 本地门禁、部署同步和直接公网 API E2E：

```text
branch: feat/quality-gate-and-tools
head: 23b032b feat: orchestrator memory expansion, conversation API, e2e improvements
alembic current: 7e8f9012abcd (head)
backend PID: 3866485 -> 3951595
demo override PID: 3952370
restored production-default PID: 3953542
localhost health: {"status":"ok"}
public health: {"status":"ok"}
```

自动化：

```text
deployment regression: 81 passed
ruff: passed
mypy: passed
git diff --check: passed
```

直接公网 API E2E：

```text
prod_default_report: /tmp/agenthub_b2_todo_05_prod_default_e2e_report.json
prod_default_container_status: not_supported
prod_default_runtime_kind: podman
demo_report: /tmp/agenthub_b2_todo_05_demo_container_e2e_report.json
demo_container_status_flow: queued -> published
demo_container_health_ok: true
demo_container_stop_cleanup_ok: true
production_default_restored_after_demo: true
```

2026-06-01 已完成后端部署与直接公网 API E2E：

```text
alembic current: 3a4b5c6d7e8f (head)
backend PID: 11364 -> 1049368
localhost health: {"status":"ok"}
public health: {"status":"ok"}
```

自动化：

```text
focused regression: 51 passed
full backend pytest: 479 passed, 7 skipped
ruff: passed
mypy: passed
shared OpenAPI YAML parse: passed
```

直接公网 E2E：

```text
script: backend/scripts/deployment_release_api_e2e.py
report: /tmp/agenthub_deployment_release_api_e2e_report.json
conversation_id: 52860326-193c-4c3c-94c2-cbf535c7fcc1
passed: true
```

E2E 已证明：

- `http://111.229.151.159:8082/index.html` 在 Preview 生命周期内可访问。
- Static Release 返回稳定 `/releases/{token}/index.html` URL。
- 修改 workspace 后旧 release 内容保持不变。
- Stop 后旧 release URL 不可访问。
- Source zip 下载成功且不含敏感目录。
- Container 在当时 demo override 下执行真实 worker 发布；脚本要求 `published`，并验证 healthcheck 和 stop
  后 URL 不可访问。
- 删除 conversation 后 Preview、release 和 zip 均不可访问。

首次 E2E 发现的是测试脚本判定缺陷：Conversation 删除后 Preview 进程退出会导致连接拒绝，脚本原先
只接受 HTTP `404/410`。已将连接失败也视为“临时 Preview 已清理”，随后重跑通过。

2026-06-02 完成第五点部署发布后端直连复验：

```text
alembic current: 4b5c6d7e8f90 (head)
backend PID: 1804633 -> 1847784
localhost health: {"status":"ok"}
public health: {"status":"ok"}
seed_agents: 已重新执行，数据库 Orchestrator config 已同步
```

自动化：

```text
focused regression: 45 passed
full backend pytest: 485 passed, 7 skipped, 1 warning
ruff: passed
mypy: passed
```

直接公网 API E2E：

```text
script: backend/scripts/deployment_release_api_e2e.py
report: /tmp/agenthub_deployment_release_api_e2e_report.json
conversation_id: 357ff9ff-0083-43a9-a527-6c96466850d3
passed: true
preview_url: http://111.229.151.159:8082/index.html
release_url: http://111.229.151.159:8000/releases/CVodCZ8b4zlPk92ttYo2uI90xMMvZrpP/index.html
container_url: http://111.229.151.159:8081
container_healthcheck_url: http://111.229.151.159:8081/health
```

该轮 E2E 已证明：

- Preview 仍可通过 8082 访问，且目录和敏感路径不可访问。
- Static Release 使用不可变 release URL，workspace 修改后旧 release 不变。
- Source zip 可下载，且排除敏感路径。
- Container deployment 在当时 demo override 下真实发布，healthcheck 通过，stop 后 URL 不可访问。
