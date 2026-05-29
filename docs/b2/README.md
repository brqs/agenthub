# B2 文档索引

> B2 负责 Agent Runtime Layer：ExternalAgentAdapter（Claude Code / Codex / OpenCode）、BuiltinAgent Framework、ModelGateway、Orchestrator 与任务分发记录。

| 文档 | 用途 |
|---|---|
| [ai-task-dispatch-template.md](ai-task-dispatch-template.md) | B2 AI 子任务分发模板 |
| [task-dispatch/README.md](task-dispatch/README.md) | B2 子任务索引 |
| [task-dispatch/B2-roadmap.md](task-dispatch/B2-roadmap.md) | B2 路线图 |

## Spec

| Spec | 用途 |
|---|---|
| [spec/agent-runtime-adapter.spec.md](spec/agent-runtime-adapter.spec.md) | BaseAgentAdapter v2 与 StreamChunk 协议 |
| [spec/agent-runtime-test-matrix.spec.md](spec/agent-runtime-test-matrix.spec.md) | Agent runtime 测试矩阵 |
| [spec/builtin-agent-framework.spec.md](spec/builtin-agent-framework.spec.md) | 自建 Agent Framework |
| [spec/model-gateway.spec.md](spec/model-gateway.spec.md) | ModelGateway backend 与 resilience |
| [spec/orchestrator.spec.md](spec/orchestrator.spec.md) | Orchestrator 行为契约 |
| [spec/orchestrator-task-planning.spec.md](spec/orchestrator-task-planning.spec.md) | Orchestrator 任务规划与分配规则 |
| [spec/orchestrator-react-dynamic-task-graph.spec.md](spec/orchestrator-react-dynamic-task-graph.spec.md) | Orchestrator ReAct 动态任务图设计 |
| [spec/agent-config-validation.spec.md](spec/agent-config-validation.spec.md) | Agent 配置校验 |
| [spec/artifact-parser-v2.spec.md](spec/artifact-parser-v2.spec.md) | ArtifactParser v2 |
| [spec/external-direct-chat-routing.spec.md](spec/external-direct-chat-routing.spec.md) | External Agent 纯问答 / Runtime 路由 |
| [spec/external-runtime-adapters.spec.md](spec/external-runtime-adapters.spec.md) | Claude Code / Codex / OpenCode adapter 细节 |
| [spec/external-runtime-lifecycle.spec.md](spec/external-runtime-lifecycle.spec.md) | External runtime timeout / heartbeat / cancel / cleanup |
| [spec/stream-error-status.spec.md](spec/stream-error-status.spec.md) | SSE error 状态持久化协同 |
| [spec/workspace-artifact-preview.spec.md](spec/workspace-artifact-preview.spec.md) | Workspace artifact / preview / deploy 边界 |
