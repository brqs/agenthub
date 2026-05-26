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
| [spec/builtin-agent-framework.spec.md](spec/builtin-agent-framework.spec.md) | 自建 Agent Framework |
| [spec/orchestrator.spec.md](spec/orchestrator.spec.md) | Orchestrator 行为契约 |
| [spec/provider-resilience.spec.md](spec/provider-resilience.spec.md) | ModelGateway / legacy raw provider retry / timeout / 错误映射 |
| [spec/adapter-smoke-tests.spec.md](spec/adapter-smoke-tests.spec.md) | Adapter smoke tests（含 legacy shim 与 runtime adapter） |
| [spec/agent-config-validation.spec.md](spec/agent-config-validation.spec.md) | Agent 配置校验 |
| [spec/artifact-parser-v2.spec.md](spec/artifact-parser-v2.spec.md) | ArtifactParser v2 |
| [spec/stream-error-status.spec.md](spec/stream-error-status.spec.md) | SSE error 状态持久化协同 |
