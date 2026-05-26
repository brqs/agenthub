# ADR-001 — Agent Runtime Pivot

**Status**: Accepted
**Date**: 2026-05-26
**Deciders**: F / B1 / B2
**Supersedes**: 隐含撤销 docs/development-plan.md v1.0 与 docs/team-division.md v1.0 中"Agent = LLM Provider 包装"的隐含定义。

---

## 1. Context

### 1.1 课题原文（PDF 关键句）

> 平台同时接入市面主流 Agent 平台（Claude Code、Codex、OpenCode 等），通过统一的适配器层屏蔽 API 差异，并支持用户自建 Agent。所有 Agent 产出（代码、网页、文档、PPT 等）支持实时预览、代码二次编辑和一键部署发布。
>
> —— `docs/AgentHub- 多Agent协作平台设计.pdf` §课题背景

PDF 中的 "Claude Code / Codex / OpenCode" **不是 LLM API**，而是**已具备 agent loop 能力的 agent runtime**：自带 tool calling、文件读写、bash 执行、MCP 接入。

### 1.2 当前实现已交付能力（不浪费的部分）

- ✅ IM 会话 / 消息持久化 / SSE 通道 / 认证 / Agent CRUD（B1）
- ✅ 前端 IM UI、富媒体 ContentBlock 渲染（文本/代码/Diff/WebPreview）、Zustand+TanStack Query 数据层（F）
- ✅ B2 已交付的 13 项 roadmap（[docs/b2/task-dispatch/B2-roadmap.md](../b2/task-dispatch/B2-roadmap.md)）：
  - BaseAgentAdapter / StreamChunk 协议（含 agent_switch、tool_* 已有占位扩展空间）
  - Claude / OpenAI / DeepSeek / Custom raw LLM 流式适配
  - StreamingArtifactParser（识别 code / diff / url）
  - Provider resilience（retry / timeout / 错误码统一）
  - Orchestrator 注入式调度 + block_index 重映射 + 失败降级 + fallback adapter

### 1.3 错配点

| PDF 要求 | 当前实现 | 错配 |
|---|---|---|
| 接入 Claude Code / Codex / OpenCode 等 **agent runtime** | 接的是 `anthropic` / `openai` SDK 的 **raw LLM API** | 🔴 完全错配 |
| 用户自建 Agent | `CustomAdapter` 仅是 system_prompt + LLM 单轮 | 🔴 不算 Agent |
| 产物：代码 / 网页 / 文档 / PPT 实时预览 + 二次编辑 + 一键部署 | 仅有渲染组件（DiffBlock / WebPreviewBlock），无 workspace、无可写文件、无部署 | 🟡 渲染层在，执行底座缺 |
| Tool calling / MCP / Memory / Context manager | 仅 [context_compression](../../backend/app/services/context_compression.py) + [conversation_memory](../../backend/app/models/conversation_memory.py) 雏形 | 🟡 部分可复用 |

### 1.4 触发事件

2026-05-26 用户在重新阅读 PDF 后澄清：
- 外部 Agent（Claude Code / Codex）→ 调用已有的 agent runtime SDK
- 自建 Agent → 团队自己实现完整 framework（loop + tool calling + MCP + context manager + memory manager）

---

## 2. Decision

### 2.1 Agent 层重新分为三层

```
┌─────────────────────────────────────────────────────────────┐
│  Layer A — ExternalAgentAdapter                             │
│    嵌入第三方 agent runtime SDK，复用其内置 loop/tool/MCP    │
│      ├── ClaudeCodeAdapter  → claude_agent_sdk              │
│      └── CodexAdapter       → openai-agents (Agents SDK)    │
│      （可选：OpenCodeAdapter → subprocess CLI）              │
├─────────────────────────────────────────────────────────────┤
│  Layer B — BuiltinAgent Framework（团队自建）                │
│    AgentLoop ─ ToolRegistry ─ MCPClient ─ MemoryManager ─   │
│                ContextManager ─ ModelGateway(↓)             │
├─────────────────────────────────────────────────────────────┤
│  Layer C — ModelGateway（现有 B2-01~B2-12 工作降级）          │
│    Claude / OpenAI / DeepSeek raw API + resilience          │
│    （仅供 Layer B 内部使用，不再作为顶层 Agent）             │
└─────────────────────────────────────────────────────────────┘
       │
       │ 三层都实现 BaseAgentAdapter v2 接口
       ▼
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator（保留现有框架，子 Agent 升级为真 Agent）       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 升级 `BaseAgentAdapter` 接口

详见 [agent-runtime-adapter.spec.md](../b2/spec/agent-runtime-adapter.spec.md)。要点：

- `stream()` 新增 `workspace_path: Path | None` 与 `tool_specs: list[ToolSpec] | None` 参数
- `StreamChunk` 新增事件类型：`tool_call`（含 tool_name / arguments / call_id）、`tool_result`（含 call_id / status / output / error）
- 新增错误码：`tool_call_failed`、`workspace_violation`、`mcp_server_down`

### 2.3 引入 Workspace（B1 提供）

详见 [workspace-sandbox.spec.md](../b1/spec/workspace-sandbox.spec.md)。要点：

- 每个 conversation 自动创建一个 sandbox 目录（宿主机 `/var/lib/agenthub/workspaces/<conversation_id>/`，容器内挂载）
- 所有 Agent 写操作必须在该目录下，禁止 `../` / 符号链接逃逸
- B1 新增 Artifact API：`GET /api/v1/workspaces/{conv_id}/files/{path}`（含 mime sniff）和 `GET /api/v1/workspaces/{conv_id}/tree`
- 安全：bash tool 限白名单命令；写文件不允许写到 `.env` / `secrets/`

### 2.4 Orchestrator 框架保留

[backend/app/agents/orchestrator.py](../../backend/app/agents/orchestrator.py) 的注入式调度、block_index 重映射、失败降级、fallback adapter **全部不动**。子 Agent 通过新 `BaseAgentAdapter v2` 接口自动升级为真 Agent。Orchestrator 的任务卡片在前端增加"工具调用计数"和"产物文件列表"摘要。

### 2.5 外部 Runtime 接入范围

- **Must**：Claude Agent SDK（`claude_agent_sdk`）+ Codex（`openai-agents` Agents SDK）
- **Could**：OpenCode（subprocess CLI，stdout 解析）—— 列为 Sprint 6 候选，不阻塞答辩
- **理由**：两个 Python SDK 嵌入成熟、流式协议稳定；OpenCode 通过 CLI 接入复杂度高且演示不稳

### 2.6 自建 Agent Framework MVP 范围

详见 [builtin-agent-framework.spec.md](../b2/spec/builtin-agent-framework.spec.md)。MVP 范围：

| 组件 | MVP 内容 | 不做（P2） |
|---|---|---|
| AgentLoop | `while not done: model_call → parse_tool_calls → execute → feed_results` | 并行 tool 调用 / 投机执行 |
| ToolRegistry | `read_file` / `write_file` / `bash`（三件套） | 网络访问 / 子 Agent 调用 / 任意 Python eval |
| MCPClient | 1 个 stdio MCP server（`@modelcontextprotocol/server-filesystem`） | HTTP transport / 多 server 路由 |
| MemoryManager | 复用 [conversation_memory](../../backend/app/models/conversation_memory.py)，仅 `pin` / `recall` | 向量检索 / 自动摘要 |
| ContextManager | 复用 [context_compression](../../backend/app/services/context_compression.py) | 重新设计 |
| ModelGateway | 复用 B2-02~B2-12 全部工作 | 不动 |

---

## 3. Consequences

### 3.1 正面

- 满足 PDF "Agent 平台接入" + "用户自建 Agent" + "产物预览" 三项要求
- 现有 B2-01~B2-13 工作 100% 复用（降级为 ModelGateway 底座），不浪费
- 现有 Orchestrator 框架 100% 复用，仅子 Agent 升级
- 前端 IM UI / SSE 通道 / 富媒体 ContentBlock / 认证 / 持久化全部不动
- 演示效果跃升：从"多 LLM 聊天" → "多 Agent 协同完成可交付产物"

### 3.2 负面

- `BaseAgentAdapter` 签名升级 → [CLAUDE.md](../../CLAUDE.md) §4.2 与 [AGENTS.md](../../AGENTS.md) §4.2 契约 2 必须同步升级，**这是契约破坏性变更**
- SSE 协议新增 `tool_call` / `tool_result` 事件 → 前端 SSE handler 与 ContentBlock 字典都要新增分支
- 新增依赖：`claude-agent-sdk`、`openai-agents`、`mcp`（Python SDK）—— 需要写入 [backend/pyproject.toml](../../backend/pyproject.toml)
- B1 工作量上涨：Workspace 模型 + Alembic + WorkspaceService + Artifact API + SSE 协议扩展
- F 工作量上涨：ToolCallBlock / ArtifactPreview / Monaco 编辑器 / Workspace 文件树

### 3.3 中性

- [backend/app/agents/adapters/custom.py](../../backend/app/agents/adapters/custom.py) 将被 BuiltinAgent 取代后删除
- [shared/openapi.yaml](../../shared/openapi.yaml) 和 [docs/api-spec.md](../api-spec.md) 在本 ADR 之后增量更新，**本 ADR 不修改契约文件**

---

## 4. Alternatives Considered

### 4.A 不 pivot，把现状包装为"轻量级 LLM 聚合器"
- 优点：8 天可控、无返工
- 缺点：偏离 PDF "Agent 平台接入" 要求，功能维度（25%）和创新维度（10%）大概率丢分
- **结论：拒绝**

### 4.B 全推倒重做
- 优点：架构最干净
- 缺点：8 天交付不可行，浪费 B2-01~13 工作
- **结论：拒绝**

### 4.C 只接外部 runtime，跳过自建 framework
- 优点：8 天压力小，演示有真 Agent
- 缺点：失去"代码理解度（15%）"和"创新与产品感（10%）"维度差异化——评委会问"自建 Agent 是怎么做的"
- **结论：拒绝**

### 4.D 本 ADR 选择：三层 Agent + 复用现有底座 + 中度文档修订
- **优点**：满足 PDF 全部要求；复用现有 70% 代码；8 天可控；答辩有自建 framework 的技术深度
- **缺点**：契约破坏性变更，需要全员同步
- **结论：采纳**

---

## 5. Migration Plan（高层）

详细 Sprint 见 [docs/development-plan.md §13](../development-plan.md) 和 [docs/team-division.md §7](../team-division.md)。

| Phase | Day | 主要交付 |
|---|---|---|
| Phase 1 | Day 1 | `BaseAgentAdapter v2` 接口 + Mock 实现；Workspace 模型 + Alembic |
| Phase 2 | Day 2-3 | ClaudeCodeAdapter 嵌入 Claude Agent SDK；端到端 demo（写 HTML → iframe 预览） |
| Phase 3 | Day 3-5 | BuiltinAgent Framework MVP：AgentLoop + ToolRegistry 三件套 + 1 个 MCP server |
| Phase 4 | Day 5-6 | CodexAdapter 嵌入 OpenAI Agents SDK；Orchestrator 接通真 Agent |
| Phase 5 | Day 7-8 | 全链路 smoke + Demo 视频 + 答辩讲稿 |

---

## 6. 现有代码复用映射

| 现有文件 | 新身份 | 改动 |
|---|---|---|
| [backend/app/agents/base.py](../../backend/app/agents/base.py) | `BaseAgentAdapter v2` | 升级签名（+ workspace_path、tool_specs），保留 stream() 形态 |
| [backend/app/agents/types.py](../../backend/app/agents/types.py) | `StreamChunk v2` | 新增 tool_call / tool_result 事件类型与字段 |
| [backend/app/agents/adapters/claude.py](../../backend/app/agents/adapters/claude.py) | `ModelGateway.ClaudeBackend` | 移到 `agents/model_gateway/`，BuiltinAgent 内部使用 |
| [backend/app/agents/adapters/openai.py](../../backend/app/agents/adapters/openai.py) | `ModelGateway.OpenAIBackend` | 同上 |
| [backend/app/agents/adapters/deepseek.py](../../backend/app/agents/adapters/deepseek.py) | `ModelGateway.DeepSeekBackend` | 同上 |
| [backend/app/agents/adapters/custom.py](../../backend/app/agents/adapters/custom.py) | **删除** | 被 BuiltinAgent 取代 |
| [backend/app/agents/adapters/resilience.py](../../backend/app/agents/adapters/resilience.py) | `model_gateway/resilience.py` | 原样保留 |
| [backend/app/agents/orchestrator.py](../../backend/app/agents/orchestrator.py) | `OrchestratorAgent`（不变） | 子 Agent 通过 v2 接口自动升级 |
| [backend/app/agents/artifact_parser.py](../../backend/app/agents/artifact_parser.py) | 保留 | BuiltinAgent 解析模型自然语言中的代码块 |
| [backend/app/services/context_builder.py](../../backend/app/services/context_builder.py) | `BuiltinAgent.ContextManager` 子组件 | 包装 |
| [backend/app/services/context_compression.py](../../backend/app/services/context_compression.py) | `BuiltinAgent.ContextManager` 子组件 | 包装 |
| [backend/app/models/conversation_memory.py](../../backend/app/models/conversation_memory.py) | `BuiltinAgent.MemoryManager` 数据层 | 不动 |
| [backend/app/agents/registry.py](../../backend/app/agents/registry.py) | `AgentRegistry v2` | 新增 ExternalAgent 注册分支 |
| **新建** `backend/app/agents/external/` | ExternalAgentAdapter 实现 | Claude Agent SDK / Codex |
| **新建** `backend/app/agents/builtin/` | BuiltinAgent Framework | loop / tools / mcp |
| **新建** `backend/app/workspaces/` | WorkspaceService（B1） | model + service + API |

---

## 7. 不在本 ADR 范围

- 不修改 [shared/openapi.yaml](../../shared/openapi.yaml) 与 [docs/api-spec.md](../api-spec.md)：Sprint 5 Day 1 由 B1 增量更新
- 不修改任何代码：Sprint 5 启动后由对应 owner 执行
- 不删除 [docs/b2/task-dispatch/](../b2/task-dispatch/) 历史记录：作为 Phase 1 ModelGateway 底座的开发记录保留
- 不实现 OpenCode 接入：列为 Sprint 6 候选
- 不实现一键部署：列为 P2，演示口述

---

## 8. References

- 课题 PDF：[docs/archive/AgentHub- 多Agent协作平台设计.pdf](<../archive/AgentHub- 多Agent协作平台设计.pdf>)
- 新 Adapter 接口规范：[docs/b2/spec/agent-runtime-adapter.spec.md](../b2/spec/agent-runtime-adapter.spec.md)
- 自建 Framework 规范：[docs/b2/spec/builtin-agent-framework.spec.md](../b2/spec/builtin-agent-framework.spec.md)
- Workspace 沙箱规范：[docs/b1/spec/workspace-sandbox.spec.md](../b1/spec/workspace-sandbox.spec.md)
- 现有 Orchestrator 规范：[docs/b2/spec/orchestrator.spec.md](../b2/spec/orchestrator.spec.md)
- 现有 Provider 弹性规范：[docs/b2/spec/provider-resilience.spec.md](../b2/spec/provider-resilience.spec.md)
- 总体协作宪法：[CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md)
