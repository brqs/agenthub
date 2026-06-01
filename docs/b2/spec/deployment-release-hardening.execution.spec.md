# Deployment / Release Hardening Execution Spec

> 状态：Backlog execution plan
> 范围：部署发布能力完善，不作为当前已实现事实
> 最后更新：2026-06-01
> 执行约束：先完成修复和本地自动化验证；真实任务流转 E2E 必须等待用户后续明确命令。

## 1. 背景

课程设计中的部署发布要求：

- 聊天中直接发送“部署”指令，Agent 返回部署状态卡片。
- 一键生成预览 URL。
- 静态站点部署。
- 容器化部署。
- 源码打包下载。

当前 Deployment / Release MVP 已完成：

- Orchestrator 已注册 `create_deployment`、`get_deployment_status`、`package_workspace_source`。
- `WorkspaceDeployment` record、Workspace deployment API、`deployment_status` 消息块已实现。
- 静态站点发布能够返回 URL。
- 源码 zip 可以下载，并排除敏感目录。
- 容器化部署会创建 `not_supported` 状态记录，不执行 Docker、shell 或 SSH。
- 前端 `DeploymentStatusBlock` 组件已经存在。

MVP 可以完成课程演示，但与完整部署发布能力仍有距离。本计划只处理这些差距，不扩展 Workflow、长期记忆或通用 Evaluation 等其他方向。

## 2. 当前不足

### 2.1 静态部署仍复用 Preview 生命周期

当前 `WorkspaceDeploymentService.create_static_site()` 调用 `WorkspacePreviewService.start()`。

影响：

- Deployment URL 实际仍由临时 Preview 进程提供。
- 同一 conversation 重新启动 Preview 时，旧静态部署可能被替换或停止。
- Preview TTL、端口复用和发布生命周期没有真正分离。
- 无法把 deployment 清晰解释为“可追踪、稳定、独立于开发预览的发布版本”。

### 2.2 Stop 语义不完整

当前删除 deployment 时：

- `source_zip` 会删除 zip 文件。
- `static_site` 仅将 record 标记为 `stopped`。
- 静态发布对应的 Preview 进程不会因该 deployment 被停止而自动关闭。

影响：

- API 状态与实际端口服务可能不一致。
- 端口、PID 和发布记录之间缺少一一对应关系。

### 2.3 静态发布缺少版本快照

当前静态发布直接读取 conversation workspace。

影响：

- Agent 后续修改 workspace 文件后，已发布 URL 的内容会随之变化。
- 同一个 deployment id 不能表示一个稳定版本。
- 无法可靠对比历史发布。

### 2.4 Container 仍是占位能力

当前 `container` deployment 返回：

```text
status = not_supported
```

这是合理的安全默认值，但不等于真正容器化部署。当前没有：

- 隔离构建。
- rootless runtime。
- 镜像或运行实例记录。
- CPU / memory / timeout 限制。
- 容器日志。
- 停止与清理。
- 容器 URL。

### 2.5 远端前端尚未发布状态卡 UI

仓库内已经实现 `DeploymentStatusBlock.tsx`，但远端前端 `http://154.44.25.94:1573` 尚未重新发布构建。

影响：

- API / SSE 中已经存在 `deployment_status`。
- 远端聊天页面不一定能展示新的状态卡、下载按钮和发布 URL 入口。

### 2.6 Deployment 可观测性仍较浅

当前 record 有 status、URL、error 和 logs，但缺少：

- 发布版本摘要，例如 artifact sha256。
- 发布时间、停止时间。
- runtime id / release id。
- Preview 与 Deployment 的关联来源。
- 列表页面或聊天中的状态刷新。

## 3. 目标边界

### 3.1 本轮目标

1. 静态部署与 Preview 生命周期解耦。
2. 每次静态发布生成不可变 release snapshot。
3. Stop deployment 时真正停止对应发布服务并清理资源。
4. 扩充 deployment record，使状态与实际 runtime 一致。
5. 完成远端前端状态卡发布准备，并在获得部署权限后发布前端。
6. 为真正容器化部署实现安全底座；默认仍保持 feature flag 关闭。

### 3.2 本轮不做

- 不让 Orchestrator 或子 Agent 获得宿主机 shell、Docker 或 SSH 权限。
- 不允许 Agent runtime 自行执行 `npm run dev`、`vite --host`、`python -m http.server`。
- 不把 Preview 当作生产级静态部署。
- 不在本计划生成后立即执行真实任务流转 E2E。
- 不在缺少隔离、限额和清理机制时打开 container deployment。

## 4. 分阶段执行计划

### Phase 0 - 收敛当前契约与配置

目标：先把 Preview、Static Release、Container Release 的语义拆清。

新增或调整配置：

```text
DEPLOYMENT_ENABLED=true
DEPLOYMENT_PUBLIC_BASE_URL=http://111.229.151.159
DEPLOYMENT_STATIC_ROOT=/tmp/agenthub_static_releases
DEPLOYMENT_PORT_START=8183
DEPLOYMENT_PORT_END=8283
DEPLOYMENT_START_TIMEOUT_SECONDS=15
DEPLOYMENT_CONTAINER_ENABLED=false
DEPLOYMENT_CONTAINER_RUNTIME=podman
DEPLOYMENT_CONTAINER_MAX_CPU=1
DEPLOYMENT_CONTAINER_MAX_MEMORY_MB=512
DEPLOYMENT_CONTAINER_MAX_RUNTIME_SECONDS=3600
```

约束：

- Preview 继续使用 `8082-8182`。
- Static deployment 使用独立端口池 `8183-8283`。
- Container 默认关闭。

### Phase 1 - 独立 Static Release Service

新增 `WorkspaceStaticReleaseService`，职责：

1. 校验 HTML entry path。
2. 创建 release snapshot：
   ```text
   /tmp/agenthub_static_releases/{deployment_id}/
   ```
3. 只复制允许发布的 workspace 文件。
4. 排除：
   ```text
   .agenthub/
   .git/
   node_modules/
   .venv/
   __pycache__/
   .env
   .ssh/
   secrets/
   ```
5. 计算 snapshot sha256。
6. 从独立 deployment 端口池分配端口。
7. 启动平台托管的只读静态服务。
8. 验证入口返回 `200`。
9. 返回 runtime id、PID、port、URL、snapshot path 和 artifact digest。

安全要求：

- 不允许目录列表。
- 服务只能暴露单个 release snapshot。
- HTML 响应保留 CSP、`X-Content-Type-Options` 等安全头。
- 不向发布进程传递 provider API key、数据库密码或 workspace 写权限。

### Phase 2 - Deployment Record 与生命周期完善

为 `WorkspaceDeployment` 增加：

```text
runtime_id
runtime_pid
port
snapshot_path
artifact_digest
published_at
stopped_at
source_preview_session_id
```

调整行为：

| 操作 | 目标行为 |
|---|---|
| 创建 `static_site` | 创建 snapshot，启动独立发布服务，状态变为 `published` |
| 查询 deployment | 刷新实际进程状态；进程丢失时标记 `failed` |
| 停止 `static_site` | 停止该 deployment 的进程，清理 snapshot，状态变为 `stopped` |
| 停止 `source_zip` | 删除 zip 文件，状态变为 `stopped` |
| 删除 conversation | 停止相关 runtime，删除 snapshot 和 zip |
| 后续修改 workspace | 不影响已发布 snapshot |

数据库变更：

- 新增 Alembic migration。
- 部署时必须执行：
  ```bash
  cd /home/ubuntu/agenthub/backend
  uv run alembic upgrade head
  uv run alembic current
  ```

### Phase 3 - Source Zip 完善

保留现有安全打包规则，并增加：

- zip 内文件总数上限。
- 单文件体积上限。
- 总体积上限。
- 压缩后体积记录。
- artifact digest。
- 统一清理过期导出文件。
- 测试 symlink、路径穿越和敏感文件排除。

### Phase 4 - 前端 Deployment UI 完善与发布准备

在已有 `DeploymentStatusBlock` 基础上完善：

- 静态发布：展示 URL、复制、打开、停止入口。
- 源码包：展示下载入口、大小、失败重试。
- Container：展示 `not_supported` 或明确的 feature flag 关闭说明。
- 状态刷新：对 `publishing` 状态轮询 `get_deployment_status`。
- 部署历史：在 workspace 或聊天侧提供最小列表入口。
- 文案统一为中文，保留可读日志摘要。

远端前端发布要求：

1. 先完成前端 lint、type check、build。
2. 按独立前端部署流程发布到 `http://154.44.25.94:1573`。
3. 未发布前，不将远端状态卡 UI 计为已验收。

### Phase 5 - Container Deployment 安全底座

容器部署必须由平台 Worker 执行，不由 Orchestrator 或子 Agent 执行命令。

建议新增：

```text
WorkspaceContainerReleaseService
DeploymentWorker
ContainerPolicyValidator
```

执行流程：

```text
create_deployment(kind="container")
-> 创建 queued record
-> Worker 创建 workspace snapshot
-> 校验发布策略
-> rootless Podman 构建
-> 以非 root 用户启动
-> 限制 CPU / memory / runtime
-> 禁止 privileged / host network / host path mount
-> 分配平台端口
-> 健康检查
-> 回写 URL、logs、runtime id 和 published 状态
```

安全约束：

- `DEPLOYMENT_CONTAINER_ENABLED=false` 时继续返回 `not_supported`。
- 只允许 rootless Podman 或等价隔离 runtime。
- 禁止 Docker socket 透传。
- 禁止 privileged、host network、任意 volume mount。
- 默认拒绝外网访问；需要外网时单独 allowlist。
- 构建和运行日志必须脱敏。
- 达到 timeout 后自动停止并清理。
- Worker 与 API 进程分离。

本阶段可以先完成 policy、数据结构、Worker 接口和 feature flag；在部署环境未具备 rootless runtime 前，不打开真实 container 发布。

## 5. Public Interfaces

保留现有 API：

```text
POST   /api/v1/workspaces/{conversation_id}/deployments
GET    /api/v1/workspaces/{conversation_id}/deployments
GET    /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}
DELETE /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}
GET    /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}/download
```

可选新增：

```text
POST /api/v1/workspaces/{conversation_id}/deployments/{deployment_id}/stop
```

兼容策略：

- 保留现有 `DELETE` 停止语义。
- 若新增 `POST .../stop`，前端优先使用显式 stop，`DELETE` 保持兼容。
- `deployment_status` block 向后兼容，仅增加可选 metadata。

## 6. 预计影响文件

后端：

```text
backend/app/core/config.py
backend/app/models/workspace.py
backend/app/services/workspace_deployment.py
backend/app/services/workspace_static_release.py
backend/app/services/workspace_container_release.py
backend/app/api/v1/workspaces.py
backend/app/schemas/workspace.py
backend/app/schemas/message.py
backend/alembic/versions/<revision>_harden_workspace_deployments.py
backend/tests/test_workspace_api.py
backend/tests/test_orchestrator_platform_tools.py
```

前端：

```text
frontend/src/components/blocks/DeploymentStatusBlock.tsx
frontend/src/components/blocks/ContentRenderer.test.tsx
frontend/src/lib/types.ts
frontend/src/lib/types.gen.ts
shared/openapi.yaml
```

文档：

```text
docs/b2/spec/workspace-artifact-preview.spec.md
docs/b2/spec/orchestrator/tool-calling.spec.md
docs/b2/spec/b2-pdf-gap-todo.spec.md
docs/b2/spec/orchestrator/live-e2e-report.spec.md
```

## 7. 本地自动化验证计划

实现修复后，先只运行本地自动化测试：

### 单元与 API

- Static release 与 Preview 使用不同端口池。
- Static deployment 生成不可变 snapshot。
- 修改 workspace 后，已发布页面内容不变。
- 停止 static deployment 后，端口不可访问，record 为 `stopped`。
- 删除 conversation 后，runtime、snapshot 和 zip 被清理。
- Source zip 排除敏感目录、symlink 和路径穿越。
- Container feature flag 默认关闭时返回 `not_supported`。
- Container policy 拒绝 privileged、host network、host mount。

### Orchestrator

- “预览”只调用 `start_workspace_preview`。
- “部署 / 发布 / 上线”调用 `create_deployment(kind="static_site")`。
- “源码打包”调用 `package_workspace_source`。
- “容器化部署”在 feature flag 关闭时返回 `not_supported`。
- Agent 输出不包含自行启动服务或容器的命令。

### 前端

- `deployment_status` 的 `published`、`failed`、`stopped`、`not_supported` 均可渲染。
- 下载、打开、停止和刷新状态按钮具备测试覆盖。
- `publishing` 状态轮询后能够更新。

建议命令：

```bash
cd /home/ubuntu/agenthub/backend
uv run pytest tests/test_workspace_api.py tests/test_orchestrator_platform_tools.py tests/test_orchestrator_tool_calling.py -q
uv run ruff check app tests scripts
uv run mypy app scripts

cd /home/ubuntu/agenthub/frontend
pnpm exec tsc --noEmit
pnpm test -- --run src/components/blocks/ContentRenderer.test.tsx
pnpm lint
pnpm build
```

## 8. 暂缓的真实 E2E

本计划生成后，不立即执行真实任务流转 E2E。

当用户后续明确要求执行时，再按照：

```text
docs/ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md
```

完成：

```text
检查 diff
-> 本地自动化测试
-> alembic upgrade head（如有 migration）
-> 重启本机后端
-> seed（如有内置 Agent 配置变更）
-> health + 关键 API 断言
-> 发布远端前端（如验收状态卡 UI）
-> 真实任务流转 E2E
```

真实 E2E 至少覆盖：

1. 聊天发送“部署”并看到远端状态卡。
2. Static release URL 可访问。
3. 修改 workspace 后，旧 release 内容保持不变。
4. 停止 deployment 后，旧 URL 不可访问。
5. Source zip 下载并验证敏感目录排除。
6. Container feature flag 关闭时返回 `not_supported`。
7. 若环境具备 rootless runtime 且用户明确要求，再测试真实 container 发布。

## 9. 完成判定

### MVP 已完成

- 部署状态 record。
- Orchestrator deployment tools。
- 静态 URL。
- Source zip。
- Container `not_supported`。

### Hardening 完成

- 静态部署不再复用 Preview 生命周期。
- Static release snapshot 不可变。
- Stop deployment 真正停止 runtime。
- 删除 conversation 后资源清理完整。
- 远端前端能展示 deployment 状态卡。
- Container 安全底座具备 feature flag、policy 和 Worker 边界。

### 完整 Container 发布完成

- rootless 隔离 runtime 可用。
- Container 发布、查询、停止、清理和日志链路全部可验证。
- 真实 E2E 通过。
