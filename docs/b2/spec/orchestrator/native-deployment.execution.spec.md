# Orchestrator Native Deployment Execution Spec

> 状态：Production hardening API E2E passed
> 最后更新：2026-06-08
> 依据：课程设计第五点“部署发布”，以聊天中直接发送“部署”指令并返回部署状态卡片为产品目标。

## 1. 背景与重构目标

课程设计要求：

- 聊天中直接发送“部署”指令，Agent 返回部署状态卡片。
- 一键生成预览 URL / 静态站点部署 / 容器化部署 / 源码打包下载。

当前后端已经完成：

- Preview URL。
- 静态站点不可变发布。
- Source zip 打包下载。
- Deployment record 和 `deployment_status`。
- Container policy、受控 `ContainerDeployWorker`、queueable dispatcher；生产默认不启用 container runtime，demo 需显式开启 trusted Docker。

本轮重构目标是让 Orchestrator 具备一等部署编排能力：

```text
用户说部署
-> Orchestrator 判断部署类型
-> Orchestrator 调用正式 deploy tool
-> 平台 Deployment Worker 执行真实部署
-> Worker 回写 URL、状态、日志、资源 id
-> 聊天流返回 deployment_status 卡片
```

这里的“原生部署”不是让模型直接执行任意 shell，而是让 Orchestrator 可以调用平台级部署能力，
像日常使用 Claude Code / OpenCode / Codex 一样完成真实上线闭环。

## 2. 新的能力分层

### 2.1 Agent / Orchestrator 层

Orchestrator 获得更明确的一等部署 tool：

```text
create_deployment
get_deployment_status
stop_deployment
package_workspace_source
```

后续新增：

```text
run_deployment_check
read_deployment_logs
```

Orchestrator 职责：

- 理解用户是要 preview、static release、container deploy 还是 source package。
- 根据 workspace 产物选择部署类型。
- 用户明确要求“部署 / 发布 / 上线”时，不能把 preview URL 当成部署完成；必须调用 `create_deployment`，并以后续 deployment status / health 作为完成证据。
- 调用平台 deployment tool。
- 根据 tool result 生成状态卡片和总结。
- 若部署失败，调度子 agent 修复产物，再重新部署。

### 2.2 Platform Tool 层

平台 tool 是安全边界：

- 校验 conversation ownership。
- 校验 workspace path。
- 创建 deployment record。
- 创建快照。
- 提交任务给 Deployment Worker。
- 轮询或订阅 Worker 状态。
- 统一返回 `deployment_status`。

### 2.3 Deployment Worker 层

Worker 负责真实执行部署动作：

```text
StaticReleaseWorker
SourcePackageWorker
ContainerDeployWorker
```

当前 `StaticReleaseWorker` 和 `SourcePackageWorker` 的核心能力已经在 API 进程内实现。
Container deployment 已使用 queueable dispatcher contract；本轮默认实现为 in-process background worker，
后续可替换成外部队列。

## 3. Native Container Deployment MVP

为了贴近课程设计和日常 Agent 使用体验，容器化部署不再是永久 `not_supported`：
生产默认保持关闭，课程 demo 可通过显式 trusted Docker override 真实执行。启用后由平台执行受控
Docker/Podman build/run，API 初始返回 `queued` 并由 worker 后台推进状态。

### 3.1 MVP 范围

第一版只支持：

- 单机后端服务器。
- 单个 container deployment。
- workspace 内必须有 `Dockerfile`。
- 一个 HTTP 暴露端口。
- 端口池由平台分配，当前默认 `8081-8085`。
- 返回公网 URL。
- 支持 stop / cleanup。
- 支持 logs preview。

不做：

- 多容器 compose。
- HTTPS / 自定义域名。
- 自动扩缩容。
- 多副本。
- 滚动发布。
- 镜像仓库推送。

### 3.2 执行链路

```text
create_deployment(kind="container", entry_path=null)
-> 创建 deployment(status="queued")
-> ContainerDeployWorker 创建构建快照
-> 校验 Dockerfile 和 deploy policy
-> docker/podman build
-> 分配 host port
-> docker/podman run
-> 健康检查
-> 回写 deployment(status="published", url, runtime_id, logs)
```

### 3.3 Docker / Podman 策略

本项目可以支持两种部署模式：

| 模式 | 配置 | 用途 |
|---|---|---|
| `rootless_podman` | `DEPLOYMENT_CONTAINER_RUNTIME=podman` | 更适合长期安全运行 |
| `trusted_docker` | `DEPLOYMENT_CONTAINER_RUNTIME=docker` | 适合课程 Demo / 单机可信环境 |

生产默认：

```text
DEPLOYMENT_CONTAINER_ENABLED=false
DEPLOYMENT_CONTAINER_RUNTIME=podman
DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=false
DEPLOYMENT_CONTAINER_PORT_START=8081
DEPLOYMENT_CONTAINER_PORT_END=8085
```

前端交互策略：

- “容器化部署”按钮不以 workspace 是否已有 `Dockerfile` 作为静默禁用条件。
- 只要有 conversation / workspace，前端可以发起 `create_deployment(kind="container")`。
- 缺少 `Dockerfile`、容器 worker 未启用或平台策略拒绝时，由后端返回受控 `failed` / `not_supported` 状态和可读原因。
- 按钮可点击不代表生产默认启用容器 worker；生产默认仍是 `DEPLOYMENT_CONTAINER_ENABLED=false`。

课程 demo 如需继续真实 Docker container deployment，必须显式 override：

```text
DEPLOYMENT_CONTAINER_ENABLED=true
DEPLOYMENT_CONTAINER_RUNTIME=docker
DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=true
```

Docker runtime 只有在 `trusted_host_mode=true` 时允许；Podman runtime 不要求 trusted host mode。
开启后仍必须经过平台 Worker 和 policy 校验，不允许 LLM 直接拼接任意 `docker run` 命令。

## 4. Container Policy

MVP 即使使用 Docker，也必须限制：

- 禁止 `--privileged`。
- 禁止 `--network host`。
- 禁止挂载宿主机任意路径。
- 禁止挂载 Docker socket。
- 禁止透传完整宿主机 env。
- 限制 CPU、memory、pids、runtime TTL。
- 限制容器暴露端口只能来自平台分配端口池。
- 构建上下文必须是 workspace snapshot，不是原始 workspace。
- 日志必须截断和脱敏。

配置：

```text
DEPLOYMENT_CONTAINER_ENABLED=true
DEPLOYMENT_CONTAINER_RUNTIME=docker
DEPLOYMENT_CONTAINER_TRUSTED_HOST_MODE=true
DEPLOYMENT_CONTAINER_PUBLIC_BASE_URL=http://111.229.151.159
DEPLOYMENT_CONTAINER_BUILD_ROOT=/tmp/agenthub_container_deployments
DEPLOYMENT_CONTAINER_PORT_START=8081
DEPLOYMENT_CONTAINER_PORT_END=8085
DEPLOYMENT_CONTAINER_MAX_CPU=1
DEPLOYMENT_CONTAINER_MAX_MEMORY_MB=512
DEPLOYMENT_CONTAINER_MAX_RUNTIME_SECONDS=3600
DEPLOYMENT_CONTAINER_HEALTH_TIMEOUT_SECONDS=30
DEPLOYMENT_CONTAINER_HEALTH_RETRY_INTERVAL_SECONDS=1
DEPLOYMENT_CONTAINER_HEALTH_MAX_ATTEMPTS=30
DEPLOYMENT_CONTAINER_HEALTH_BACKOFF_MULTIPLIER=1.5
DEPLOYMENT_CONTAINER_LOG_TAIL_BYTES=20000
```

Docker run 约束示例：

```text
docker run
  --detach
  --cpus 1
  --memory 512m
  --pids-limit 256
  --read-only
  --tmpfs /tmp:rw,noexec,nosuid,size=64m
  --security-opt no-new-privileges
  --network bridge
  -p {host_port}:{container_port}
```

如果某项目必须写入目录，只允许挂载平台创建的临时数据目录，不允许挂载 workspace 或宿主路径。

## 5. 数据模型扩展

`WorkspaceDeployment` 需要支持 container runtime 元数据：

```text
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
queued_at
started_at
completed_at
last_checked_at
```

`status` 保持：

```text
queued | publishing | published | failed | stopped | not_supported
```

后续如果引入异步队列，可增加：

```text
queued
building
starting
checking
```

为了兼容现有前端，API 可以先把中间态映射为 `publishing`，并通过 `logs` 提供细节。

## 6. API 与 Tool Contract

保留现有 API：

```text
POST   /api/v1/workspaces/{conversation_id}/deployments
GET    /api/v1/workspaces/{conversation_id}/deployments
GET    /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}
DELETE /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}
GET    /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}/download
```

`create_deployment(kind="container")` 新增参数：

```json
{
  "kind": "container",
  "container_port": 8000,
  "health_path": "/health",
  "start_command": null
}
```

规则：

- `Dockerfile` 必须存在。
- `container_port` 必须明确，或由 Dockerfile `EXPOSE` 唯一推断。
- `start_command` 默认不允许由用户自由传入；如开放必须通过 allowlist。
- 返回 `deployment_status`，包含 `deployment_id`、`kind`、`runtime_kind`、`runtime_status`、
  `failure_category`、`last_error_code`、`state_events` 摘要，以及 `url`、`logs_preview`、`error`。

## 7. Orchestrator 行为重构

当前不合理点：

- 文档容易把 container deployment 固化成 `not_supported` 终点。
- Orchestrator 虽有 deployment tool，但缺少“部署失败 -> 修复 -> 再部署”的正式闭环。
- 静态发布、源码包、容器发布的 tool result 语义没有统一成“发布作业”。

重构后：

1. 用户说“预览”：调用 `start_workspace_preview`。
2. 用户说“部署网页 / 发布静态站点”：调用 `create_deployment(static_site)`。
3. 用户说“打包源码 / 下载源码”：调用 `package_workspace_source`。
4. 用户说“容器化部署 / 部署后端服务”：调用 `create_deployment(container)`。
5. 如果 container worker 被管理员关闭：返回可解释的 `not_supported`。
6. 生产默认 container worker 关闭并返回 `not_supported`；demo override 后才真实构建运行。
7. 启用后 `create_deployment(container)` 初始返回 `queued` 或 `publishing`，worker 后台推进终态。
8. `deployment_health` 对 `queued/publishing` 返回 skipped/pending-style summary，不触发 repair。
9. 如果部署失败：Orchestrator 优先读取 `failure_category` / `last_error_code` 和 state events，
   再结合 logs 生成修复任务，调度子 agent 修改 workspace，再重新部署。

## 8. 后端实现步骤

### Phase 1 - Worker 抽象落地

- 已新增 `DeploymentWorker` protocol。
- 已新增 `ContainerDeployWorker` 与 worker result schema。
- static release / source zip 保持兼容实现，后续可继续薄封装成 worker。
- `WorkspaceDeploymentService` 负责 DB 状态、权限边界、cleanup 和 worker 调用。

### Phase 2 - Container Docker Worker MVP

- 已新增 `ContainerDeployWorker`。
- 已校验 Dockerfile、`container_port` / `EXPOSE`、`health_path`。
- 已构建 container snapshot，排除敏感目录并限制文件大小。
- 已调用 Docker / Podman CLI，并固定受控 run 参数。
- 已分配 `8081-8085` host port。
- 已执行健康检查。
- stop / conversation cleanup / TTL janitor 会停止容器并清理 snapshot。
- build/run/health 失败路径会清理本轮 build context、container 和 image，避免失败发布留下孤儿资源。
- container build/run 资源带有 managed label，janitor 在 runtime 可用时可按 label 清理未被 DB 追踪的
  orphan container/image。

### Phase 3 - Orchestrator 原生部署闭环

- 已更新 platform tool executor，支持 `container_port`、`health_path`、`start_command` validation。
- 已新增 `stop_deployment` tool。
- `create_deployment(container)` 在生产默认下返回 `not_supported`；demo override 后真实 build/run。
- 已返回 runtime metadata、healthcheck URL、logs tail、failure_category、last_error_code、state_events。
- 质量门失败后会调度 repair agent；repair 修改 workspace 后必须刷新 preview snapshot，再重新执行 browser verify，避免验证旧快照。
- 部署阶段已接入 `deployment_health` evaluation：失败时生成结构化 reflection，repair instruction
  包含 deployment kind、error、logs/logs_tail 和原始 tool arguments；repair agent 修改 workspace 后会重新调用
  同一个 deployment tool。`queued/publishing` 视为 pending/skipped，`not_supported` 仅记录平台限制，不触发自动修复。
- 2026-06-04 B2-TODO-05 direct public API E2E 已验证 production-default
  `not_supported` 和 trusted Docker demo override `queued -> published` 两条路径。

### Phase 4 - E2E 与前端联调

- 直接 API E2E 已扩展 container case；当前生产默认应返回 `not_supported`，demo override 下才要求 `published`。
- 前端发布操作中的“容器化部署”按钮可以发起受控 `create_deployment(kind="container")`
  请求；按钮可点不表示生产默认已启用容器 worker。缺少 Dockerfile 或
  `DEPLOYMENT_CONTAINER_ENABLED=false` 时，应展示后端返回的受控失败 / `not_supported`
  状态，而不是静默禁用入口。
- 前端未完成时，后端验收以直接 API E2E 和 Orchestrator API/SSE E2E 为准，不要求远端 UI 渲染状态卡。
- 历史 Orchestrator API/SSE E2E 已在 demo override 下验证静态发布、源码包和容器发布链路。
- 2026-06-04 direct API E2E 证据：
  - production default report：`/tmp/agenthub_b2_todo_05_prod_default_e2e_report.json`，
    conversation `42b7d9e4-1243-4b4c-9394-1ebb54568ed3`，container `not_supported`，
    runtime_kind `podman`。
  - demo override report：`/tmp/agenthub_b2_todo_05_demo_container_e2e_report.json`，
    conversation `8b5088bd-161b-4f68-aa74-4ab1e8547546`，container `queued -> published`，
    worker `inproc-container-aacc169897e0`，`attempt_count=1`，`state_event_count=13`。
- 2026-06-04 Orchestrator API/SSE queued worker E2E 证据：
  - production default report：`/tmp/agenthub_b2_todo_05_orch_prod_default_report.json`，
    SSE `/tmp/agenthub_b2_todo_05_orch_prod_default_sse.jsonl`，conversation
    `963afa42-0549-4fa0-81b0-8fad6b013a4b`，container final `not_supported`，
    `deployment_status` block 可见，`not_supported` 未触发 repair/reflection。
  - trusted Docker demo report：`/tmp/agenthub_b2_todo_05_orch_demo_report.json`，
    SSE `/tmp/agenthub_b2_todo_05_orch_demo_sse.jsonl`，conversation
    `ce767e6f-b03c-41fb-af85-fe637983c356`，container `publishing -> published`，
    worker `inproc-container-71038d04c528`，`attempt_count=1`，`state_event_count=12`，
    healthcheck OK，stop cleanup OK。
  - optional repair report：`/tmp/agenthub_b2_todo_05_orch_repair_report.json` 未通过；
    已观察到 `failure_category=build_failed`、`last_error_code=container_build_failed`，
    但未观察到 `reflection_created` 和第二次 redeploy；作为后续 repair loop 稳定性补项。
- Orchestrator live E2E 增加 deployment repair 专用场景：首次容器部署失败后必须观察到
  `deployment_health` failure、`reflection_created`、repair agent attempt、第二次 `create_deployment` 和最终
  `published=true`。
- 前端状态卡新增字段为可选 metadata，旧 UI 兼容；前端联调不影响后端部署能力验收。

## 9. 测试计划

单元 / API：

- 默认 container disabled -> `not_supported`。
- Docker trusted false -> `not_supported` / policy rejected；Podman trusted false 允许。
- Dockerfile 不存在 -> 初始 `queued`，worker 最终 `failed` + `failure_category="build_failed"`。
- Dockerfile 存在且健康检查通过 -> 初始 `queued`，worker 最终 `published`。
- host port 被占用 -> 换端口或失败，策略必须明确。
- repeated stop deployment -> 幂等 `stopped`；queued/publishing stop 记录 cancellation intent。
- 删除 conversation -> 容器、镜像/快照、zip、release 全部清理。
- Dockerfile 尝试 privileged / host mount 不应被平台 run 参数允许。
- 构建超时、运行超时、健康检查失败均写入 error/logs/state_events。

Orchestrator API/SSE queued worker 复验已覆盖 production-default `not_supported` 和 trusted Docker demo
override `queued/publishing -> published` 两条聊天编排链路；剩余补测集中在 repair/redeploy loop 对 queued
worker 新状态语义的稳定复验。

```text
@orchestrator 请生成一个最小 FastAPI 服务，包含 Dockerfile，
容器化部署后返回 URL，并验证 /health 返回 ok。
```

可选补测验收：

- SSE 出现 `create_deployment(kind="container")`。
- `deployment_status.status="published"`。
- URL 公网可访问。
- `/health` 返回 `ok`。
- stop 后 URL 不可访问。
- logs 不包含敏感环境变量。

前端未完成期间，使用 `http://111.229.151.159:8000` 直连后端执行 API/SSE E2E；只有需要验收 UI 卡片渲染时才走远端前端入口。

2026-06-02 后端直连 Orchestrator API/SSE E2E：

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

2026-06-03 Deployment / Release hardening live E2E：

```text
script: backend/scripts/orchestrator_live_e2e.py
base_url: http://111.229.151.159:8000
scenario: deployment_repair
report: /tmp/agenthub_deployment_repair_flow_report.json
sse: /tmp/agenthub_deployment_repair_flow_sse.jsonl
browser_report: /tmp/agenthub_deployment_repair_flow_browser.json
conversation_id: dcb2dbd6-e256-41a7-bd3f-1b99b0aaf66a
passed: true
preview_url: http://111.229.151.159:8082/index.html
deployment_repair_initial_failure_seen: true
deployment_repair_reflection_created: true
deployment_repair_redeploy_called: true
container_deployment_published: true
container_health_ok: true
```

本轮同时确认 container managed resources 中仍运行的 container 均有 DB 中 `published`
deployment 记录，不是 orphan；失败路径清理和 janitor orphan cleanup 已由单元/集成测试覆盖。

2026-06-08 Command Fulfillment repair loop container smoke：

```text
scenario: command_fulfillment_cyberpunk_group_deploy
report: /tmp/agenthub_command_fulfillment_report.json
conversation_id: 9fd3cd30-6b65-45a4-8833-dcadffd78f64
container_deployment_smoke_status_code: 201
container_deployment_smoke_status: not_supported
container_error: Container deployment is disabled. Enable DEPLOYMENT_CONTAINER_ENABLED to use it.
result: passed
```

## 10. 验收标准

- Orchestrator 能原生选择部署 tool，而不是只在 stream 后处理。
- Static site、source zip、container 三类部署都通过同一 deployment record 管理。
- Container deployment 在管理员开启后可以真实 build/run。
- Agent 不直接获得任意 shell，但可以通过平台 tool 完成真实部署。
- 部署失败能进入自动修复：`deployment_health` 失败生成 reflection，repair agent 修复后再次调用
  deployment tool。
- 所有资源都能 stop/cleanup。
- 真实 E2E report `passed=true`。

## 11. 风险与答辩解释

如果使用 `trusted_docker`：

- 这是课程 Demo / 单机可信部署模式。
- 风险由管理员显式开启并承担。
- 仍通过平台 Worker 限制参数、端口、资源和日志。

如果用于生产或多人环境：

- 应切换到 rootless Podman。
- API 进程与 Worker 分离。
- 增加队列、审计、资源配额和网络隔离。

这个方案符合设计文档“Agent 一键部署发布”的目标，同时保留平台对宿主能力的最终控制权。
