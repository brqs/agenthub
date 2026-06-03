# Deployment / Release Frontend Handoff Spec

> 状态：Optional frontend enhancement handoff
> 最后更新：2026-06-03

## 1. 当前结论

当前后端 Static Release 实现保持现有 UI 兼容；后续 Orchestrator 原生容器部署仍复用同一类状态卡。已有状态卡继续使用：

```text
deployment_id
kind
status
url
download_url
error
logs_preview
size_bytes
```

因此本轮后端上线不要求立即修改或重新发布前端。

当前前端仍未完成完整部署发布 UI 时，第五点后端验收以 API E2E 与 SSE 数据为准：

- 直接调用 preview / deployments / download API 验证后端能力。
- 通过 Orchestrator 消息流验证正式 tool call 和 `deployment_status` block 数据。
- 不把远端前端是否渲染状态卡作为 B2 后端阻断项。

2026-06-03 后端 Deployment / Release hardening MVP 已通过 live E2E：container 部署失败会触发
evaluation/reflection/repair/redeploy，并最终返回 `published` 的 `deployment_status`。前端后续可选择展示
repair round、failure issue 和 redeploy 过程，但不影响当前后端验收。

## 2. 新增可选字段

`deployment_status` block 与 Workspace deployment API 新增可选 metadata：

```text
artifact_digest
file_count
published_at
stopped_at
expires_at
```

前端后续可以展示：

- 静态版本摘要。
- 发布文件数。
- 发布时间与停止时间。
- 源码包过期时间。

## 3. 既有交互

联调时检查：

- 静态发布状态卡可以打开、复制 URL。
- 源码包状态卡可以下载 zip。
- Stop 操作后卡片刷新为 `stopped`。
- `publishing` 状态可以轮询刷新。
- 发布历史列表可以读取 deployment API。
- Container 默认开启原生部署后的 `publishing/published/failed/stopped`，以及管理员关闭 worker 时的 `not_supported`，都使用明确中文文案，不渲染为前端运行时错误。

## 4. 接入增强后的发布动作

若前端开发人员接入可选 metadata：

```bash
cd /home/ubuntu/agenthub/frontend
pnpm exec tsc --noEmit
pnpm test -- --run
pnpm lint
pnpm build
```

然后按前端独立发布流程更新 `frontend/dist/`。B2 后端不直接修改远端前端静态资源。

## 5. 后端接口参考

- 原生部署执行计划：
  [../../b2/spec/orchestrator/native-deployment.execution.spec.md](../../b2/spec/orchestrator/native-deployment.execution.spec.md)
- 后端实现：
  [../../b2/spec/deployment-release-backend.execution.spec.md](../../b2/spec/deployment-release-backend.execution.spec.md)
- OpenAPI：
  [shared/openapi.yaml](../../../shared/openapi.yaml)
