# Orchestrator Spec Package

> 目的：作为 Orchestrator 相关 spec 的包级入口，区分当前契约、实现报告和后续 proposal。
>
> 状态：Current package index
> 最后更新：2026-06-01

---

## 1. Package 结构

| 文档 | 状态 | 作用 |
|---|---|---|
| [core.spec.md](core.spec.md) | Current contract | Orchestrator 主行为契约：调度、DAG 并行、summary、失败处理、preview 边界 |
| [task-planning.spec.md](task-planning.spec.md) | Current contract | direct answer、direct mention、LLM planner、legacy fallback、DAG 依赖语义 |
| [tool-calling.spec.md](tool-calling.spec.md) | Current contract | `dispatch_agent`、workspace tools、preview/verify、自建 Agent 与 deployment platform tools |
| [memory-context.spec.md](memory-context.spec.md) | Current contract | Orchestrator structured memory 与上下文注入设计 |
| [workspace-conflict.spec.md](workspace-conflict.spec.md) | Current contract | Workspace snapshot、file changes、同一 run 内冲突检测 |
| [memory-context.execution.spec.md](memory-context.execution.spec.md) | Implemented report | structured memory v1 真实执行结果 |
| [live-e2e-report.spec.md](live-e2e-report.spec.md) | Implemented report | 真实部署链路 E2E、回归部署和 bugfix 证据 |
| [react-dynamic-task-graph.proposal.md](react-dynamic-task-graph.proposal.md) | Backlog / proposal | ReAct 动态任务图方案；不是当前默认主链 |

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
2. [memory-context.execution.spec.md](memory-context.execution.spec.md)
3. [core.spec.md](core.spec.md)

---

## 3. 当前边界

- 当前默认主链是 `llm_planning=true` + 静态 DAG 并行 executor。
- ReAct 动态任务图仍是 proposal，不作为当前代码事实来源。
- DAG 并行是 Orchestrator execution 能力，不是 platform tool。
- Preview / browser verify / create custom agent / deployment 是 Orchestrator 可调用的平台 tool，但实际执行由平台 service 完成。
- 自建 Agent 的显式 `allowed_tools` 尚未进入 v1 tool schema；当前只完成基础创建和入群链路。
- Workspace conflict detection 当前只记录和展示，不做自动 merge、rollback 或文件级 lock。

---

## 4. 对外依赖

- Adapter / StreamChunk 契约：[../agent-runtime-adapter.spec.md](../agent-runtime-adapter.spec.md)
- External runtime 生命周期：[../external-runtime-lifecycle.spec.md](../external-runtime-lifecycle.spec.md)
- Workspace artifact / preview：[../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md)
- B2 PDF gap：[../b2-pdf-gap-todo.spec.md](../b2-pdf-gap-todo.spec.md)
