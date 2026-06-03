# Orchestrator Spec Package

> 目的：作为 Orchestrator 相关 spec 的包级入口，区分当前契约和当前验证报告。
>
> 状态：Current package index
> 最后更新：2026-06-03

---

## 1. Package 结构

| 文档 | 状态 | 作用 |
|---|---|---|
| [core.spec.md](core.spec.md) | Current contract | Orchestrator 主行为契约：调度、DAG 并行、summary、失败处理、preview 边界 |
| [task-planning.spec.md](task-planning.spec.md) | Current contract | direct answer、direct mention、LLM planner、legacy fallback、DAG 依赖语义 |
| [tool-calling.spec.md](tool-calling.spec.md) | Current contract | `dispatch_agent`、workspace tools、preview/verify、自建 Agent 与 deployment platform tools |
| [memory-context.spec.md](memory-context.spec.md) | Current contract | Orchestrator structured memory 与上下文注入设计 |
| [workspace-conflict.spec.md](workspace-conflict.spec.md) | Current contract | Workspace snapshot、file changes、同一 run 内冲突检测 |
| [message-attribution.spec.md](message-attribution.spec.md) | Current contract | Orchestrator 合流 stream 中每个 content/tool chunk 的真实 Agent 归属 |
| [agent-review-thread.spec.md](agent-review-thread.spec.md) | Implemented MVP + Live E2E Passed | Agent-to-Agent review、handoff、repair thread |
| [native-deployment.execution.spec.md](native-deployment.execution.spec.md) | Implemented hardening MVP | Orchestrator 原生部署 tool、container E2E、deployment repair/redeploy |
| [live-e2e-report.spec.md](live-e2e-report.spec.md) | Implemented report | 真实部署链路、deployment repair/redeploy、自建 Agent 工具白名单 E2E 证据 |
| [evaluation-reflection.spec.md](evaluation-reflection.spec.md) | Current contract | 通用 Evaluation / Reflection：“生成 -> 验证 -> 修复 -> 再验证”闭环 |

---

## 2. 阅读顺序

修改 Orchestrator 主执行流：

1. [core.spec.md](core.spec.md)
2. [task-planning.spec.md](task-planning.spec.md)
3. [workspace-conflict.spec.md](workspace-conflict.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

修改 Orchestrator tools：

1. [tool-calling.spec.md](tool-calling.spec.md)
2. [core.spec.md](core.spec.md)
3. [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

修改 Orchestrator memory：

1. [memory-context.spec.md](memory-context.spec.md)
2. [core.spec.md](core.spec.md)

修改 Orchestrator 合流消息归属：

1. [message-attribution.spec.md](message-attribution.spec.md)
2. [core.spec.md](core.spec.md)
3. [../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)

修改 Orchestrator 原生部署：

1. [native-deployment.execution.spec.md](native-deployment.execution.spec.md)
2. [tool-calling.spec.md](tool-calling.spec.md)
3. [../deployment-release-backend.execution.spec.md](../deployment-release-backend.execution.spec.md)
4. [live-e2e-report.spec.md](live-e2e-report.spec.md)

---

## 3. 当前边界

- 当前默认主链是 `llm_planning=true` + 静态 DAG 并行 executor。
- 通用 Evaluation / Reflection Phase 2 MVP 已实现；网页 preview/browser verify、Workflow validation + allowlist dry-run、PPT outline、受控 test runner 和 deployment health 已接入 evaluator / health gate 语义，workflow runtime 与 deployment repair/redeploy live E2E 已通过。
- DAG 并行是 Orchestrator execution 能力，不是 platform tool。
- Preview / browser verify / create custom agent / deployment 是 Orchestrator 可调用的平台 tool，但实际执行由平台 service 完成。
- 自建 Agent 的显式 `allowed_tools` 已进入 tool schema；builtin native/MCP 最小权限 MVP 已实现并通过 live E2E，external runtime 权限映射仍属后续 hardening。
- Agent-to-Agent review thread MVP 已实现：关键 implementation task 可自动 handoff 给其他 Agent review，并在 failed / needs_repair outcome 下顺序或并行追加 repair task；前端 handoff timeline 交接见 [../../../frontend/agent-review-thread-handoff.md](../../../frontend/agent-review-thread-handoff.md)。
- Workspace conflict detection 当前只记录和展示，不做自动 merge、rollback 或文件级 lock。

---

## 4. 对外依赖

- Adapter / StreamChunk 契约：[../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)
- External runtime 生命周期：[../external-runtime-lifecycle.spec.md](../external-runtime-lifecycle.spec.md)
- Workspace artifact / preview：[../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
- B2 PDF gap：[../b2-pdf-gap-todo.spec.md](../b2-pdf-gap-todo.spec.md)
