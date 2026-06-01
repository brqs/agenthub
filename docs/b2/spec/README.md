# B2 Spec Index

> 目的：作为 B2 Agent Runtime Layer 的 spec 总入口，帮助接手者快速判断“现在真实契约是什么、哪些已经实现、哪些只是提案或后续 TODO”。
>
> 状态：Current index
> 最后更新：2026-05-31

---

## 1. 阅读结论

B2 当前主线已经从早期 raw LLM adapter 演进为 Agent Runtime Layer：

- External Agent Runtime：Claude Code / Codex / OpenCode。
- Builtin Agent Framework：团队自建 agent loop + tools + ModelGateway。
- Orchestrator：群聊主协调器，支持 LLM planning、DAG 并行、workspace conflict detection、平台 preview/browser verify tool、对话式自建 Agent。
- Workspace Artifact / Preview / Deployment：Agent 只生成文件，平台负责 preview、URL、浏览器验收、静态发布、源码 zip 和容器化占位状态。

对照课程 PDF，B2 P0 已完成并通过真实 E2E：

- 并行 DAG 调度。
- Workspace 冲突检测。
- 对话式自建 Agent。

剩余主要 backlog：

- Workflow artifact。
- Agent-to-Agent review thread。
- 长期 agent 能力画像。
- 通用 evaluation/reflection 闭环。
- Deployment hardening：静态发布与 Preview 生命周期解耦、不可变 release snapshot、真实 stop、远端状态卡发布和 container 安全底座。

---

## 2. 状态分类

| 状态 | 含义 | 使用方式 |
|---|---|---|
| Current contract | 当前代码应遵守的真实契约 | 改代码前必须读，行为变更后必须同步更新 |
| Implemented report | 真实实现与验证记录 | 用于答辩、交接、回归确认 |
| Backlog / proposal | 后续方案或未完成设计 | 不能直接当作当前代码事实 |
| Historical boundary | 历史协作或 B1/F/B2 边界记录 | 用于理解演进原因和跨组协作约束 |

---

## 3. 本轮整理决策

本轮精简目标是降低 B2 当前目录噪音，同时保留 AI 协作证据链：

- 原 `b2-p0-implementation-report.spec.md` 已拆分并删除；P0 内容按架构归位到 Orchestrator、Workspace conflict、Tool calling 和 Live E2E report。
- Orchestrator 相关 spec 已收进 [orchestrator/README.md](orchestrator/README.md) package，根目录不再平铺多个 `orchestrator-*` 文件。
- `docs/b2/task-dispatch/` 已移动到 `docs/archive/b2-task-dispatch/`，作为历史任务单证据，不再作为 B2 当前入口。
- `ai-task-dispatch-template.md` 与 `codex-review-template.md` 已合并为 [docs/ai-skills/b2-ai-collaboration/SKILL.md](../../ai-skills/b2-ai-collaboration/SKILL.md)。
- Orchestrator live E2E 修复闭环使用标准 Skill 目录：[docs/ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md](../../ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md)。
- proposal / historical 文档保留醒目标记；current contract 文档保持最新代码路径。

| 文档 | 本轮动作 | 原因 |
|---|---|---|
| `README.md` | 保留 | 作为 spec 总入口，避免接手者在 20 个文件里迷路 |
| `b2-pdf-gap-todo.spec.md` | 保留，作为 Current backlog | 直接对应课程 PDF 缺口和后续优先级 |
| `orchestrator/README.md` | 新增 package index | Orchestrator 主契约、规划、tool、memory、conflict、E2E 的统一入口 |
| `orchestrator/live-e2e-report.spec.md` | 新增 | 只保存真实 E2E、回归部署和 bugfix 证据，不承载能力契约 |
| `orchestrator/workspace-conflict.spec.md` | 新增 | Workspace snapshot / file changes / conflict detection 当前契约 |
| `b2-refactor-plan.spec.md` | 精简入口，不删 | 内容很长且含历史路径；保留追溯价值，但不作为首读 |
| `orchestrator/core.spec.md` | 保留，作为 Current contract | Orchestrator 当前主契约 |
| `orchestrator/task-planning.spec.md` | 保留，作为 Current contract | planner / direct routing / DAG 依赖语义仍有效 |
| `orchestrator/tool-calling.spec.md` | 修改旧路径，保留 | 平台 tool、preview verify、自建 Agent 均已落地 |
| `orchestrator/react-dynamic-task-graph.proposal.md` | 标记 Backlog proposal | 不是当前默认主链，避免误读为已实现 P0 |
| `orchestrator/memory-context.spec.md` | 保留，作为 Current contract | 结构化记忆仍是当前能力 |
| `orchestrator/memory-context.execution.spec.md` | 标记实现报告和历史路径说明 | 是真实实现记录，但部分路径是历史阶段描述 |
| `stream-error-status.spec.md` | 标记 Historical boundary | 规则仍有意义，但 stream 模块结构已拆分 |
| `agent-runtime-*` / `external-*` / `builtin-*` / `model-gateway` | 保留 | 当前 Agent Runtime 主契约 |
| `workspace-artifact-preview.spec.md` / `artifact-parser-v2.spec.md` | 保留 | artifact、preview、parser 边界仍是当前事实 |

如果后续一定要做目录级重排，建议新增 `current/`、`reports/`、`proposals/` 三层目录，并保留旧路径 redirect stub；本轮为避免破坏链接，不搬文件。

---

## 4. 推荐阅读顺序

### 4.1 新人接手 B2

1. [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md)  
   先看课程 PDF 对 B2 的缺口、P0 完成状态和剩余 backlog。

2. [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)  
   看 P0 真实 E2E 结果，确认当前系统不是只停留在设计。

3. [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)  
   看 `BaseAgentAdapter` / `StreamChunk` 统一协议。

4. [orchestrator/README.md](orchestrator/README.md)  
   看当前 Orchestrator 主行为契约。

5. [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)  
   看 artifact、preview、deploy 边界。

### 4.2 修改 Orchestrator

1. [orchestrator/core.spec.md](orchestrator/core.spec.md)
2. [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md)
3. [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)
4. [orchestrator/memory-context.spec.md](orchestrator/memory-context.spec.md)
5. [orchestrator/workspace-conflict.spec.md](orchestrator/workspace-conflict.spec.md)
6. [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)

注意：

- [orchestrator/react-dynamic-task-graph.proposal.md](orchestrator/react-dynamic-task-graph.proposal.md) 是 proposal/backlog，不是当前主执行路径。
- 当前默认路径是 LLM planning + 静态 DAG 并行 executor；ReAct 动态图不是 P0 已验收能力。

### 4.3 修改 External Runtime

1. [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)
2. [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md)
3. [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)
4. [external-direct-chat-routing.spec.md](external-direct-chat-routing.spec.md)
5. [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md)

### 4.4 修改 Builtin Agent / ModelGateway

1. [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md)
2. [model-gateway.spec.md](model-gateway.spec.md)
3. [agent-config-validation.spec.md](agent-config-validation.spec.md)
4. [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md)

### 4.5 修改 Artifact / Preview / 部署相关能力

1. [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)
2. [deployment-release-hardening.execution.spec.md](deployment-release-hardening.execution.spec.md)
3. [artifact-parser-v2.spec.md](artifact-parser-v2.spec.md)
4. [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)
5. [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md)

---

## 5. Spec 总表

### 5.1 总览与交接

| Spec | 状态 | 说明 |
|---|---|---|
| [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md) | Current backlog | 对照课程 PDF 的 B2 达标情况、P0 完成状态、P1/P2 TODO |
| [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md) | Implemented report | Orchestrator 真实 E2E、回归部署和 bugfix 证据 |
| [b2-refactor-plan.spec.md](b2-refactor-plan.spec.md) | Implemented report / roadmap | B2 重构状态、模块拆分边界、历史验证记录 |

### 5.2 Agent Runtime Core

| Spec | 状态 | 说明 |
|---|---|---|
| [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md) | Current contract | `BaseAgentAdapter v2`、`StreamChunk`、tool events、workspace 参数 |
| [agent-config-validation.spec.md](agent-config-validation.spec.md) | Current contract | Agent provider/config 校验、seed 内置 Agent 配置约束 |
| [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md) | Current contract | Unit / Integration / API-SSE / live smoke 测试分层 |

### 5.3 External Runtime

| Spec | 状态 | 说明 |
|---|---|---|
| [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md) | Current contract | Claude Code / Codex / OpenCode provider-specific 启动、事件映射、清理 |
| [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md) | Current contract | timeout、heartbeat、cancel、process cleanup、诊断日志 |
| [external-direct-chat-routing.spec.md](external-direct-chat-routing.spec.md) | Current contract | 普通问答绕过真实 runtime，任务类请求进入 external runtime |

### 5.4 Builtin Agent / ModelGateway

| Spec | 状态 | 说明 |
|---|---|---|
| [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md) | Current contract | 自建 Agent loop、ToolRegistry、MCP、Context/Memory 边界 |
| [model-gateway.spec.md](model-gateway.spec.md) | Current contract | raw LLM backend 只作为内部 ModelGateway，不作为顶层 Agent |

### 5.5 Orchestrator

| Spec | 状态 | 说明 |
|---|---|---|
| [orchestrator/README.md](orchestrator/README.md) | Current package index | Orchestrator 相关 spec 总入口 |
| [orchestrator/core.spec.md](orchestrator/core.spec.md) | Current contract | 当前 Orchestrator 主行为：规划、DAG 并行、调度、summary、conflict、preview tool |
| [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md) | Current contract | direct answer、direct mention、LLM planner、legacy fallback 的规划顺序 |
| [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md) | Current contract | `dispatch_agent`、workspace tools、preview/verify、自建 Agent platform tools |
| [orchestrator/memory-context.spec.md](orchestrator/memory-context.spec.md) | Current contract | Orchestrator structured memory 设计与当前上下文体系 |
| [orchestrator/memory-context.execution.spec.md](orchestrator/memory-context.execution.spec.md) | Implemented report | 结构化记忆 v1 真实执行结果 |
| [orchestrator/react-dynamic-task-graph.proposal.md](orchestrator/react-dynamic-task-graph.proposal.md) | Backlog / proposal | ReAct 动态任务图方案；不是当前默认执行主链 |
| [orchestrator/workspace-conflict.spec.md](orchestrator/workspace-conflict.spec.md) | Current contract | Workspace snapshot、file changes、冲突检测与 summary/memory 暴露 |

### 5.6 Artifact / Preview / Stream 协同

| Spec | 状态 | 说明 |
|---|---|---|
| [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) | Current contract + Hardening backlog | workspace artifact、preview API、deployment 发布边界 |
| [deployment-release-hardening.execution.spec.md](deployment-release-hardening.execution.spec.md) | Backlog execution plan | 静态发布与 Preview 解耦、不可变 snapshot、真实 stop、远端状态卡发布和 container 安全底座 |
| [artifact-parser-v2.spec.md](artifact-parser-v2.spec.md) | Current contract | text/code/diff/web_preview 解析规则 |
| [stream-error-status.spec.md](stream-error-status.spec.md) | Historical boundary / current rule | B1 SSE 层消费 B2 error chunk 时的状态持久化规则 |

---

## 6. 当前唯一事实来源

| 问题 | 优先看 |
|---|---|
| Agent adapter 接口怎么传 workspace 和 tools | [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md) |
| 顶层 Agent provider 有哪些 | [agent-config-validation.spec.md](agent-config-validation.spec.md) |
| Claude Code / Codex / OpenCode 怎么接入 | [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md) |
| external runtime 超时/心跳/取消怎么处理 | [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md) |
| BuiltinAgent 是否是真 Agent | [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md) |
| raw LLM API 放在哪里 | [model-gateway.spec.md](model-gateway.spec.md) |
| Orchestrator 当前怎么执行任务 | [orchestrator/core.spec.md](orchestrator/core.spec.md) |
| Orchestrator 怎么规划任务 | [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md) |
| Orchestrator 有哪些正式 tools | [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md) |
| Workspace 冲突如何检测 | [orchestrator/workspace-conflict.spec.md](orchestrator/workspace-conflict.spec.md) |
| Orchestrator 记忆怎么持久化 | [orchestrator/memory-context.spec.md](orchestrator/memory-context.spec.md) |
| 8082 preview 是谁启动的 | [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) |
| 部署发布还缺什么 | [deployment-release-hardening.execution.spec.md](deployment-release-hardening.execution.spec.md)、[workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) |
| B2 对照 PDF 还缺什么 | [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md) |
| Orchestrator 是否真实跑通 | [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md) |

---

## 7. Spec 更新规则

修改 B2 代码时，同步更新规则如下：

1. 改 `BaseAgentAdapter` / `StreamChunk` / tool event：
   - 必须更新 [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)。
   - 涉及 API content block 时同步 `shared/openapi.yaml` 和 B1/F 文档。

2. 改 external runtime：
   - 更新 [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md) 或 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。
   - 新增测试要求时更新 [agent-runtime-test-matrix.spec.md](agent-runtime-test-matrix.spec.md)。

3. 改 Orchestrator 执行行为：
   - 更新 [orchestrator/core.spec.md](orchestrator/core.spec.md)。
   - 如果是规划入口，更新 [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md)。
   - 如果是 tool，更新 [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md)。

4. 改 preview/deploy/artifact：
   - 更新 [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)。
   - 如果 parser 规则变化，更新 [artifact-parser-v2.spec.md](artifact-parser-v2.spec.md)。

5. 完成 PDF gap 或里程碑：
   - 更新 [b2-pdf-gap-todo.spec.md](b2-pdf-gap-todo.spec.md)。
   - 新增或更新 implementation report，保留真实测试命令、报告路径、conversation id 或失败原因。

6. 只写提案但不实现：
   - 文档顶部必须标记 `Proposed` 或 `Backlog`。
   - 不要把提案写成当前事实。

---

## 8. 答辩展示建议

如果评委关注 PDF 中 “AI 协作能力 30%”，B2 spec 可以这样展示：

- Spec 体系：本目录把 Agent runtime、Orchestrator、Preview、Memory、Testing 拆成可执行契约。
- Rules 体系：`AGENTS.md` / `CLAUDE.md` 定义目录所有权、API 契约、Adapter 契约和禁止事项。
- Skill 体系：`docs/ai-skills/b2-ai-collaboration/SKILL.md` 与 `docs/ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md` 固化了 AI 任务分发、复审、真实 E2E 修复闭环。
- Evidence 体系：`orchestrator/live-e2e-report.spec.md`、`docs/archive/b2-task-dispatch/` 与 `/tmp/agenthub_b2_p0_live_report.json` 证明真实协作和 E2E 跑通。
