# B2 文档索引

> B2 负责 Agent Runtime Layer：ExternalAgentAdapter（Claude Code / Codex / OpenCode）、BuiltinAgent Framework、ModelGateway、Orchestrator 与任务分发记录。

## 当前接手入口

| 入口 | 用途 |
|---|---|
| [spec/README.md](spec/README.md) | B2 spec 总索引：阅读顺序、状态分类、唯一事实来源、更新规则 |
| [spec/b2-pdf-gap-todo.spec.md](spec/b2-pdf-gap-todo.spec.md) | 对照课程 PDF 后的 B2 缺口 TODO 清单 |
| [spec/orchestrator/README.md](spec/orchestrator/README.md) | Orchestrator spec package：主契约、planning、tools、memory、conflict、E2E |
| [spec/orchestrator/live-e2e-report.spec.md](spec/orchestrator/live-e2e-report.spec.md) | Orchestrator 真实 E2E、回归部署与 bugfix 证据 |
| [spec/orchestrator/core.spec.md](spec/orchestrator/core.spec.md) | Orchestrator 当前行为契约 |
| [spec/orchestrator/clarification-gate.spec.md](spec/orchestrator/clarification-gate.spec.md) | Orchestrator 代码产物请求进入 planner/子 Agent 调度前的需求澄清闸门 |
| [spec/external-runtime-adapters.spec.md](spec/external-runtime-adapters.spec.md) | Claude Code / Codex / OpenCode adapter 细节 |
| [spec/external-direct-chat-routing.spec.md](spec/external-direct-chat-routing.spec.md) | External Agent 纯问答 / Runtime 路由 |
| [spec/model-gateway.spec.md](spec/model-gateway.spec.md) | ModelGateway backend 与 resilience |
| [../spec/next-major-modules.spec.md](../spec/next-major-modules.spec.md) | 下一阶段：interrupt 传播、附件进入 runtime context、深度自定义 Agent/skills/MCP |

## 当前模块地图

| 区域 | 当前主要文件 | 状态 |
|---|---|---|
| Orchestrator 主流程 | `backend/app/agents/orchestrator/__init__.py`、`backend/app/agents/orchestrator/adapter.py` | 已 package 化，公开入口保持 `from app.agents.orchestrator import OrchestratorAdapter` |
| Orchestrator helper | `backend/app/agents/orchestrator/*.py` | helper 已迁入 package，去掉平铺 `orchestrator_*` 文件前缀 |
| Stream 接入 | `backend/app/api/v1/stream.py`、`stream_accumulator.py`、`stream_orchestrator_context.py`、`stream_preview.py` | endpoint 已变薄，B2 上下注入和平台 preview autostart 移到独立 helper |
| External runtime | `external/claude_code.py`、`external/codex.py`、`external/opencode.py`、`external/runtime_prelude.py`、`external/sdk_stream.py`、`external/runtime_utils.py` | direct chat / SDK stream / 小型 runtime utility 公共逻辑已收敛 |
| Config schema | `config_validation.py`、`config_fields.py`、`schemas/agent.py` | numeric bounds、seed 默认值和 OpenAPI contract 检查已收敛，OpenAPI 自动生成仍未做 |
| Workspace preview | `backend/app/services/workspace_preview.py`、`backend/app/api/v1/workspaces.py` | 平台侧 static preview MVP：`POST/GET/DELETE /workspaces/{id}/preview`，端口池默认从 8082 开始；agent 只能请求 preview，实际 PID/端口由平台 tool 管理 |
| Orchestrator DAG 并行 | `orchestrator/execution.py`、`orchestrator/task_planning.py` | DAG 并行默认开启，属于 Orchestrator 执行器能力 |
| Workspace conflict detection | `orchestrator/workspace_changes.py`、`orchestrator/summary.py`、`services/orchestrator_memory.py` | snapshot / file changes / conflict summary 已通过真实 E2E |
| Orchestrator platform tools | `orchestrator/tools.py`、`orchestrator/tool_loop.py`、`services/orchestrator_platform_tools.py` | `start_workspace_preview`、`verify_web_preview`、`create_custom_agent` |
| Live E2E report | `backend/scripts/orchestrator_live_e2e.py` | 真实部署链路报告脚本，断言 Orchestrator 完成后自动触发平台 `start_workspace_preview`，输出 `/tmp/agenthub_orchestrator_8082_{sse,report}` |

## External runtime contract

- OpenCode is a backend-container CLI dependency, not a Python package. The
  adapter launches `opencode run --format json --dir <workspace> <prompt>` and
  consumes JSONL events from stdout.
- Local Docker images must include Node.js/npm and `opencode-ai`; check with
  `docker compose exec backend opencode --version`.
- Credentials must be available to the backend runtime through `.env` provider
  keys or through `docker compose exec backend opencode auth login`. The
  `opencode-state` compose volume persists `~/.local/share/opencode/auth.json`.
- If OpenCode is absent or unauthenticated, Orchestrator must treat
  `opencode-helper` as unavailable for task dispatch and surface a retryable
  runtime error instead of completing successfully.
- Claude Code is a backend-container runtime too. The adapter defaults to
  `runtime="sdk"` and uses `claude_agent_sdk`; it can be explicitly configured
  with `runtime="cli"` to launch the `claude` CLI through the shared CLI runner.
  If `runtime` is omitted, SDK remains the production default.
- Claude Code auth may come from backend `.env` provider keys (`ANTHROPIC_*` /
  `CLAUDE_*`) or from persisted CLI login state in the `claude-state` compose
  volume. The shared auth directory is `$AGENTHUB_CLAUDE_AUTH_DIR` and should
  contain `.claude.json` and/or `.claude/`.
- Per-message runtime HOME isolation remains required. The adapter copies only
  Claude auth files from the shared auth directory into the isolated HOME before
  launching SDK/CLI work.
- Runtime availability is active, not file-existence based: shared auth files or
  `.env` credentials only make Claude Code a candidate. AgentHub runs a short
  backend-container probe with the same isolated HOME/auth-copy contract, caches
  the result briefly, and marks `claude-code` runnable only when the probe
  succeeds.
- Codex defaults to CLI runtime and now honors `config.command`, allowing tests
  or deployments to point `codex-helper` at a specific executable. OpenCode is
  CLI-only and continues to honor `config.command` / `config.args`.
- Manual CLI smoke tests must set `HOME=$AGENTHUB_CLAUDE_AUTH_DIR`, for example
  `docker compose exec backend sh -lc 'HOME=$AGENTHUB_CLAUDE_AUTH_DIR claude -p "只回复 OK" --output-format text'`.
- The direct-chat shortcut is separate: simple Q&A may use `qa_model_backend`
  without launching Claude SDK/CLI, so a successful "你好" answer does not prove
  artifact/build runtime availability.
- If Claude Code is unauthenticated, Orchestrator must mark `claude-code`
  unavailable for dispatch and surface a retryable runtime error. Do not expose
  SDK wrapper text such as `Claude Code returned an error result: success`.

## Next major modules ownership

- Interrupt conversation: B2 adapters must accept cancellation signals from B1, stop SDK/CLI/tool loops, and report `interrupted` as a user-requested terminal state rather than runtime failure.
- File uploads: B2 should consume attachments through explicit metadata/workspace materialization. Images may enter multimodal context when a backend supports them; archives/documents should not be unpacked or indexed unless B1/F record explicit user intent.
- Deep custom Agent: B2 owns runtime interpretation of custom Agent profiles, including instructions, skills, MCP tool registry, permission policy, memory scope, and health-aware availability. Orchestrator must keep group-scoped dispatch and may only call validated conversation members.

## 重构状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| Orchestrator extraction | implemented | helper、direct answer、task planning、adapter/fallback、execution state machine 已拆出并 package 化 |
| Orchestrator test split | mostly implemented | fake helper、platform facts、planner、ReAct 测试已抽出；按当前边界不再继续拆 execution/artifact/fallback |
| Stream boundary extraction | partial implemented | content accumulator / orchestrator context 已拆出 |
| External runtime common layer | mostly implemented | prelude、SDK stream folding、argv/error/truncate utility 已拆出，OpenCode JSONL 主循环保留在 adapter 内 |
| Config schema single source | mostly implemented | numeric field metadata 与 seed 默认值已共享，OpenAPI 字段/bounds 有测试防漂移 |
| Docs re-index | implemented | 本 README 和 spec index 作为当前接手入口；过时过程文档已删除 |
| B2 P0 PDF gaps | implemented | 并行 DAG、workspace 冲突检测、对话式自建 Agent 已通过 live E2E，见对应架构 spec 与 live E2E report |

## AI 协作流程

| 文档 | 用途 |
|---|---|
| [../ai-skills/b2-ai-collaboration/SKILL.md](../ai-skills/b2-ai-collaboration/SKILL.md) | B2 AI 子任务分发、批量派工与 Codex 复审 Skill |
| [../ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md](../ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md) | Orchestrator 真实 E2E 测试与失败修复闭环 Skill |

## 相关外部协作文档

| 文档 | 用途 |
|---|---|
| [../b1/spec/stream-error-status.spec.md](../b1/spec/stream-error-status.spec.md) | B1 SSE error 状态持久化协同 |
| [../frontend/deployment-release-handoff.md](../frontend/deployment-release-handoff.md) | 前端远端发布交接：状态卡发布步骤和联调信息清单 |
| [../frontend/agent-review-thread-handoff.md](../frontend/agent-review-thread-handoff.md) | Agent-to-Agent Review Thread 前端 timeline 产品化交接 |
| [../frontend/rich-artifact-preview-handoff.md](../frontend/rich-artifact-preview-handoff.md) | Rich Artifact / manifest API / evaluation status 前端产品化交接 |
| [../frontend/agent-capability-profile-handoff.md](../frontend/agent-capability-profile-handoff.md) | Agent Capability Profile v1 API、类型生成与后续只读 UI 交接 |

## Spec

完整阅读顺序、状态分类和唯一事实来源见 [spec/README.md](spec/README.md)。下表保留为快速跳转。

| Spec | 用途 |
|---|---|
| [spec/README.md](spec/README.md) | B2 spec 总索引 |
| [spec/b2-pdf-gap-todo.spec.md](spec/b2-pdf-gap-todo.spec.md) | 对照课程 PDF 后的 B2 缺口 TODO 清单 |
| [spec/orchestrator/README.md](spec/orchestrator/README.md) | Orchestrator spec package 总入口 |
| [spec/orchestrator/live-e2e-report.spec.md](spec/orchestrator/live-e2e-report.spec.md) | Orchestrator 真实 E2E、回归部署与 bugfix 证据 |
| [spec/orchestrator/workspace-conflict.spec.md](spec/orchestrator/workspace-conflict.spec.md) | Workspace snapshot、file changes 与冲突检测 |
| [spec/agent-runtime-adapter.spec.md](spec/agent-runtime-adapter.spec.md) | BaseAgentAdapter v2 与 StreamChunk 协议 |
| [spec/agent-runtime-test-matrix.spec.md](spec/agent-runtime-test-matrix.spec.md) | Agent runtime 测试矩阵 |
| [spec/builtin-agent-framework.spec.md](spec/builtin-agent-framework.spec.md) | 自建 Agent Framework |
| [spec/model-gateway.spec.md](spec/model-gateway.spec.md) | ModelGateway backend 与 resilience |
| [spec/orchestrator/core.spec.md](spec/orchestrator/core.spec.md) | Orchestrator 行为契约 |
| [spec/orchestrator/task-planning.spec.md](spec/orchestrator/task-planning.spec.md) | Orchestrator 任务规划与分配规则 |
| [spec/orchestrator/clarification-gate.spec.md](spec/orchestrator/clarification-gate.spec.md) | Orchestrator 需求澄清闸门 |
| [spec/orchestrator/memory-context.spec.md](spec/orchestrator/memory-context.spec.md) | Orchestrator 结构化记忆与上下文管理 |
| [spec/orchestrator/tool-calling.spec.md](spec/orchestrator/tool-calling.spec.md) | Orchestrator 原生 Tool Calling Agent 设计 |
| [spec/agent-config-validation.spec.md](spec/agent-config-validation.spec.md) | Agent 配置校验 |
| [spec/artifact-parser-v2.spec.md](spec/artifact-parser-v2.spec.md) | ArtifactParser v2 |
| [spec/external-direct-chat-routing.spec.md](spec/external-direct-chat-routing.spec.md) | External Agent 纯问答 / Runtime 路由 |
| [spec/external-runtime-adapters.spec.md](spec/external-runtime-adapters.spec.md) | Claude Code / Codex / OpenCode adapter 细节 |
| [spec/external-runtime-lifecycle.spec.md](spec/external-runtime-lifecycle.spec.md) | External runtime timeout / heartbeat / cancel / cleanup |
| [spec/workspace-artifact-preview.spec.md](spec/workspace-artifact-preview.spec.md) | Workspace artifact / preview / deploy 边界 |
## 2026-06-07 Interrupt Runtime Contract

B2 adapters and Orchestrator must treat user Stop as `interrupted`, not as runtime failure.

- Adapter config can receive `runtime_interrupt_event` / `runtime_control.interrupt_event`.
- SDK/CLI loops should stop at safe wait boundaries and clean up child processes or async iterators quietly.
- User interrupt must not emit user-facing `runtime_cancelled` errors.
- Orchestrator interrupt marks active run/task attempts and open child messages as `interrupted`, and must not start replanner, repair, fallback, or final success summary.
