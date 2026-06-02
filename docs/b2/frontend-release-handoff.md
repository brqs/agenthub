# AgentHub 前端发布交接说明

> 用途：B2 部署发布能力与前端开发人员对接。
> 最后核对：2026-06-01

## 当前结论

当前后端静态发布能力不要求立即修改或重新发布远端前端；后续 Orchestrator 原生容器部署仍会复用同一类状态卡：

- 前端地址：`http://154.44.25.94:1573`
- 后端公网地址：`http://111.229.151.159:8000`
- 已有 `deployment_status` 卡片继续兼容。
- Static Release URL 由 Preview 端口 URL 改为稳定 `/releases/{token}` URL，字段名仍是 `url`。
- 新增 metadata 均为可选字段，不影响旧 UI。

前端增强需求与联调清单已经收敛到：

[deployment-release-frontend-handoff.spec.md](spec/deployment-release-frontend-handoff.spec.md)

## 可选增强

前端后续可以展示：

- artifact digest。
- 发布文件数。
- 发布时间、停止时间。
- Source zip 过期时间。
- 统一中文状态文案。

接入增强后再执行类型生成、测试、构建和远端 `dist/` 发布。

## 发布权限边界

B2 后端不直接操作远端前端服务器。前端人员应使用现有 CI/CD 或受控 SSH 发布流程；不要在聊天中发送
密码或私钥。
