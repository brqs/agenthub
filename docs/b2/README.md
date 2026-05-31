# B2 文档索引

> B2 负责 Agent Runtime Layer：ExternalAgentAdapter（Claude Code / Codex / OpenCode）、BuiltinAgent Framework、ModelGateway、Orchestrator 与任务分发记录。

## 当前接手入口

| 入口 | 用途 |
|---|---|
| [spec/b2-refactor-plan.spec.md](spec/b2-refactor-plan.spec.md) | B2 业务代码与文档重构计划、当前执行状态、后续拆分边界 |
| [spec/orchestrator.spec.md](spec/orchestrator.spec.md) | Orchestrator 当前行为契约 |
| [spec/external-runtime-adapters.spec.md](spec/external-runtime-adapters.spec.md) | Claude Code / Codex / OpenCode adapter 细节 |
| [spec/external-direct-chat-routing.spec.md](spec/external-direct-chat-routing.spec.md) | External Agent 纯问答 / Runtime 路由 |
| [spec/model-gateway.spec.md](spec/model-gateway.spec.md) | ModelGateway backend 与 resilience |

## 当前模块地图

| 区域 | 当前主要文件 | 状态 |
|---|---|---|
| Orchestrator 主流程 | `backend/app/agents/orchestrator/__init__.py`、`backend/app/agents/orchestrator/adapter.py` | 已 package 化，公开入口保持 `from app.agents.orchestrator import OrchestratorAdapter` |
| Orchestrator helper | `backend/app/agents/orchestrator/*.py` | helper 已迁入 package，去掉平铺 `orchestrator_*` 文件前缀 |
| Stream 接入 | `backend/app/api/v1/stream.py`、`stream_accumulator.py`、`stream_orchestrator_context.py`、`stream_preview.py` | endpoint 已变薄，B2 上下注入和平台 preview autostart 移到独立 helper |
| External runtime | `external/claude_code.py`、`external/codex.py`、`external/opencode.py`、`external/runtime_prelude.py`、`external/sdk_stream.py`、`external/runtime_utils.py` | direct chat / SDK stream / 小型 runtime utility 公共逻辑已收敛 |
| Config schema | `config_validation.py`、`config_fields.py`、`schemas/agent.py` | numeric bounds、seed 默认值和 OpenAPI contract 检查已收敛，OpenAPI 自动生成仍未做 |
| Workspace preview | `backend/app/services/workspace_preview.py`、`backend/app/api/v1/workspaces.py` | 平台侧 static preview MVP：`POST/GET/DELETE /workspaces/{id}/preview`，端口池默认从 8082 开始；agent 只能请求 preview，实际 PID/端口由平台 tool 管理 |
| Live E2E report | `backend/scripts/orchestrator_live_e2e.py` | 真实部署链路报告脚本，断言 Orchestrator 完成后自动触发平台 `start_workspace_preview`，输出 `/tmp/agenthub_orchestrator_8082_{sse,report}` |

## 重构状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| Orchestrator extraction | implemented | helper、direct answer、task planning、adapter/fallback、execution state machine 已拆出并 package 化 |
| Orchestrator test split | mostly implemented | fake helper、platform facts、planner、ReAct 测试已抽出；按当前边界不再继续拆 execution/artifact/fallback |
| Stream boundary extraction | partial implemented | content accumulator / orchestrator context 已拆出 |
| External runtime common layer | mostly implemented | prelude、SDK stream folding、argv/error/truncate utility 已拆出，OpenCode JSONL 主循环保留在 adapter 内 |
| Config schema single source | mostly implemented | numeric field metadata 与 seed 默认值已共享，OpenAPI 字段/bounds 有测试防漂移 |
| Docs re-index | implemented | 本 README 和 refactor plan 作为当前接手入口，历史 spec 暂不大搬迁以保留链接稳定 |

## Task Dispatch

| 文档 | 用途 |
|---|---|
| [ai-task-dispatch-template.md](ai-task-dispatch-template.md) | B2 AI 子任务分发模板 |
| [task-dispatch/README.md](task-dispatch/README.md) | B2 子任务索引 |
| [task-dispatch/B2-roadmap.md](task-dispatch/B2-roadmap.md) | B2 路线图 |

## Spec

| Spec | 用途 |
|---|---|
| [spec/b2-refactor-plan.spec.md](spec/b2-refactor-plan.spec.md) | B2 业务代码与文档重构计划 |
| [spec/agent-runtime-adapter.spec.md](spec/agent-runtime-adapter.spec.md) | BaseAgentAdapter v2 与 StreamChunk 协议 |
| [spec/agent-runtime-test-matrix.spec.md](spec/agent-runtime-test-matrix.spec.md) | Agent runtime 测试矩阵 |
| [spec/builtin-agent-framework.spec.md](spec/builtin-agent-framework.spec.md) | 自建 Agent Framework |
| [spec/model-gateway.spec.md](spec/model-gateway.spec.md) | ModelGateway backend 与 resilience |
| [spec/orchestrator.spec.md](spec/orchestrator.spec.md) | Orchestrator 行为契约 |
| [spec/orchestrator-task-planning.spec.md](spec/orchestrator-task-planning.spec.md) | Orchestrator 任务规划与分配规则 |
| [spec/orchestrator-react-dynamic-task-graph.spec.md](spec/orchestrator-react-dynamic-task-graph.spec.md) | Orchestrator ReAct 动态任务图设计 |
| [spec/orchestrator-memory-context-management.spec.md](spec/orchestrator-memory-context-management.spec.md) | Orchestrator 结构化记忆与上下文管理 |
| [spec/orchestrator-memory-context-management.execution.spec.md](spec/orchestrator-memory-context-management.execution.spec.md) | Orchestrator 结构化记忆 v1 真实执行结果 |
| [spec/orchestrator-tool-calling-agent.spec.md](spec/orchestrator-tool-calling-agent.spec.md) | Orchestrator 原生 Tool Calling Agent 设计 |
| [spec/agent-config-validation.spec.md](spec/agent-config-validation.spec.md) | Agent 配置校验 |
| [spec/artifact-parser-v2.spec.md](spec/artifact-parser-v2.spec.md) | ArtifactParser v2 |
| [spec/external-direct-chat-routing.spec.md](spec/external-direct-chat-routing.spec.md) | External Agent 纯问答 / Runtime 路由 |
| [spec/external-runtime-adapters.spec.md](spec/external-runtime-adapters.spec.md) | Claude Code / Codex / OpenCode adapter 细节 |
| [spec/external-runtime-lifecycle.spec.md](spec/external-runtime-lifecycle.spec.md) | External runtime timeout / heartbeat / cancel / cleanup |
| [spec/stream-error-status.spec.md](spec/stream-error-status.spec.md) | SSE error 状态持久化协同 |
| [spec/workspace-artifact-preview.spec.md](spec/workspace-artifact-preview.spec.md) | Workspace artifact / preview / deploy 边界 |
