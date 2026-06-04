# B2 Spec Index

> 目的：作为 B2 Agent Runtime Layer 的当前 spec 总入口。
>
> 状态：Current index
> 最后更新：2026-06-04

---

## 1. 当前范围

B2 当前只保留必要契约和当前验证报告：

- Agent Runtime：`BaseAgentAdapter`、`StreamChunk`、Agent config validation、runtime test matrix。
- External Runtime：Claude Code / Codex / OpenCode adapter、direct chat routing、lifecycle。
- Builtin Agent：自建 Agent loop、native/MCP tools、ModelGateway、`allowed_tools` 权限边界。
- Orchestrator：任务规划、DAG 并行、tool calling、memory、message attribution、workspace conflict、Evaluation / Reflection、native deployment。
- Workspace Artifact / Preview / Deployment：artifact、workflow runtime dry-run、preview、static release、source zip、container deployment 的平台边界。
- B2 PDF gap：当前完成状态和剩余 backlog。

过时过程文档、旧 proposal、重复 execution report 已删除；跨 B1 / Frontend owner 的文档已移出 B2。

---

## 2. 推荐阅读顺序

新人接手：

1. [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md)
2. [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)
3. [orchestrator/README.md](orchestrator/README.md)
4. [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)
5. [workflow-artifact.spec.md](workflow-artifact.spec.md)
6. [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)

下一阶段工作：

1. [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md) 的 `B2-TODO-08 Capability Profile v2 / User Preference Memory` 完成状态和后续前端消费边界
2. [orchestrator/memory-context.spec.md](orchestrator/memory-context.spec.md)

修改 Orchestrator：

1. [orchestrator/core.spec.md](orchestrator/core.spec.md)
2. [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md)
3. [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)
4. [orchestrator/evaluation-reflection.spec.md](orchestrator/evaluation-reflection.spec.md)
5. [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)

修改 Agent Runtime：

1. [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)
2. [agent-config-validation.spec.md](agent-config-validation.spec.md)
3. [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md)

修改 External Runtime：

1. [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md)
2. [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)
3. [external-direct-chat-routing.spec.md](external-direct-chat-routing.spec.md)

修改 Builtin Agent / ModelGateway：

1. [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md)
2. [model-gateway.spec.md](model-gateway.spec.md)
3. [agent-config-validation.spec.md](agent-config-validation.spec.md)

修改 Artifact / Preview / Deployment：

1. [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)
2. [workflow-artifact.spec.md](workflow-artifact.spec.md)
3. [deployment-release-backend.execution.spec.md](deployment-release-backend.execution.spec.md)
4. [orchestrator/native-deployment.execution.spec.md](orchestrator/native-deployment.execution.spec.md)
5. [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)

---

## 3. Spec 总表

### Agent Runtime

| Spec | 状态 | 说明 |
|---|---|---|
| [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md) | Current contract | `BaseAgentAdapter v2`、`StreamChunk`、tool events、workspace 参数 |
| [agent-config-validation.spec.md](agent-config-validation.spec.md) | Current contract | Agent provider/config 校验、seed 内置 Agent 配置约束 |
| [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md) | Current contract | Unit / integration / API-SSE / live smoke 测试分层 |

### External Runtime

| Spec | 状态 | 说明 |
|---|---|---|
| [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md) | Current contract | Claude Code / Codex / OpenCode provider-specific 启动、事件映射、清理 |
| [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md) | Current contract | timeout、heartbeat、cancel、process cleanup、诊断日志 |
| [external-direct-chat-routing.spec.md](external-direct-chat-routing.spec.md) | Current contract | 普通问答绕过真实 runtime，任务类请求进入 external runtime |

### Builtin Agent / ModelGateway

| Spec | 状态 | 说明 |
|---|---|---|
| [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md) | Current contract | 自建 Agent loop、ToolRegistry、MCP、Context/Memory、`allowed_tools` 边界 |
| [model-gateway.spec.md](model-gateway.spec.md) | Current contract | raw LLM backend 只作为内部 ModelGateway，不作为顶层 Agent |

### Orchestrator

| Spec | 状态 | 说明 |
|---|---|---|
| [orchestrator/README.md](orchestrator/README.md) | Current package index | Orchestrator spec 总入口 |
| [orchestrator/core.spec.md](orchestrator/core.spec.md) | Current contract | 规划、DAG 并行、调度、summary、conflict、preview/deploy 边界 |
| [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md) | Current contract | direct answer、direct mention、LLM planner、fallback 的规划顺序 |
| [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md) | Current contract | `dispatch_agent`、workspace tools、preview/verify、自建 Agent 与 deployment platform tools |
| [orchestrator/evaluation-reflection.spec.md](orchestrator/evaluation-reflection.spec.md) | Current contract | 通用 Evaluation / Reflection 闭环 |
| [orchestrator/memory-context.spec.md](orchestrator/memory-context.spec.md) | Current contract | Orchestrator structured memory、Capability Profile v1、Capability Profile v2 / User Preference Memory 当前契约与 E2E 证据 |
| [orchestrator/message-attribution.spec.md](orchestrator/message-attribution.spec.md) | Current contract | Orchestrator 合流消息按真实输出 Agent 标记 `agent_id` |
| [orchestrator/agent-review-thread.spec.md](orchestrator/agent-review-thread.spec.md) | Implemented MVP | Agent-to-Agent review / handoff / repair thread |
| [orchestrator/workspace-conflict.spec.md](orchestrator/workspace-conflict.spec.md) | Current contract | Workspace snapshot、file changes、冲突检测与 summary/memory 暴露 |
| [orchestrator/native-deployment.execution.spec.md](orchestrator/native-deployment.execution.spec.md) | Current report | Orchestrator 原生部署、container E2E、deployment repair/redeploy |
| [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md) | Current report | 真实 E2E、deployment repair/redeploy、自建 Agent 工具白名单证据 |

### Artifact / Preview / Deployment

| Spec | 状态 | 说明 |
|---|---|---|
| [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) | Current contract | workspace artifact、preview、static release、deployment 发布边界 |
| [deployment-release-backend.execution.spec.md](deployment-release-backend.execution.spec.md) | Current report | Preview 快照隔离、Static Release、Source Zip、Container Worker、API E2E |
| [artifact-parser-v2.spec.md](artifact-parser-v2.spec.md) | Current contract | text/code/diff/web_preview 解析规则 |
| [workflow-artifact.spec.md](workflow-artifact.spec.md) | Current contract / Runtime dry-run MVP | `workflow` ContentBlock、parser/accumulator、前端 workflow preview、allowlist dry-run、run history / health API |

### Backlog

| Spec | 状态 | 说明 |
|---|---|---|
| [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md) | Current backlog | 对照课程 PDF 的完成状态和剩余 TODO |

---

## 4. 外部协作文档

| Owner | 文档 | 用途 |
|---|---|---|
| B1 | [../../b1/spec/stream-error-status.spec.md](../../b1/spec/stream-error-status.spec.md) | SSE error 状态持久化 |
| B1 | [../../b1/spec/message-content-block-attribution.spec.md](../../b1/spec/message-content-block-attribution.spec.md) | ContentBlock `agent_id` 持久化 |
| Frontend | [../../frontend/spec/orchestrated-message-rendering.spec.md](../../frontend/spec/orchestrated-message-rendering.spec.md) | Orchestrator 消息分组渲染 |
| Frontend | [../../frontend/spec/deployment-release-handoff.spec.md](../../frontend/spec/deployment-release-handoff.spec.md) | Deployment / Release 状态卡交接 |
| Frontend | [../../frontend/agent-review-thread-handoff.md](../../frontend/agent-review-thread-handoff.md) | Agent-to-Agent review / handoff / repair timeline 产品化交接 |
| Frontend | [../../frontend/rich-artifact-preview-handoff.md](../../frontend/rich-artifact-preview-handoff.md) | Rich artifact card / manifest API / evaluation status 产品化交接 |
| Frontend | [../../frontend/agent-capability-profile-handoff.md](../../frontend/agent-capability-profile-handoff.md) | Agent capability profile API、类型生成与只读展示交接 |

---

## 5. 更新规则

1. 改 `BaseAgentAdapter` / `StreamChunk` / tool event：更新 [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)。
2. 改 Agent config：更新 [agent-config-validation.spec.md](agent-config-validation.spec.md)。
3. 改 External Runtime：更新 [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md) 或 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。
4. 改 Builtin Agent：更新 [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md)。
5. 改 Orchestrator 执行行为：更新 [orchestrator/core.spec.md](orchestrator/core.spec.md)。
6. 改 Orchestrator tool：更新 [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)。
7. 改 Evaluation / Reflection：更新 [orchestrator/evaluation-reflection.spec.md](orchestrator/evaluation-reflection.spec.md)。
8. 改 preview / deployment / artifact：更新 [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) 和相关 deployment spec。
9. 完成 PDF gap 或里程碑：更新 [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md) 与 [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)。
