# B2 Agent Runtime Layer 目标框架与任务路线图

> 本文档用于统一 B2 后续开发方向。单个任务启动时，再基于本文档生成对应的详细 OpenCode 执行文档。

## 1. B2 总目标

B2 的目标不是单纯“调通一个 LLM API”，而是为 AgentHub 建立一层稳定的真实 Agent Runtime 编排能力：

- 屏蔽 Claude Code、Codex、OpenCode、自建 BuiltinAgent 等 runtime 差异。
- 通过 `BaseAgentAdapter v2` 向 B1 输出统一 `StreamChunk`。
- 支撑 SSE 流式输出、tool_call/tool_result、Workspace 产物和多 Agent 编排。
- 让新增 runtime 或新增内置 Agent 的成本稳定在小范围改动内。
- 保持 B2 不直接访问数据库，配置由 B1/service/registry 外层注入。

## 1.1 协作角色

- OpenCode：主要开发执行者，每个子任务新开一个对话窗口。
- Codex：总览、拆解、边界检查、最终代码复审。
- Claude Code：仅在 Codex 复审通过后处理 Git 状态整理、commit、push 和 PR，不参与开发实现。

## 2. 设计边界

### B2 负责

- `backend/app/agents/**`
- `backend/app/agents/external/**`
- `backend/app/agents/builtin/**`
- `backend/app/agents/model_gateway/**`
- Agent runtime 适配器、自建 Agent framework、ModelGateway、产物解析、Orchestrator 编排逻辑
- 与 Agent 行为强相关的测试
- B2 任务分发文档和协作日志

### B2 参与但需协同

- `backend/app/api/v1/agents.py`
- `backend/app/schemas/**`
- `shared/openapi.yaml`
- `backend/app/api/v1/stream.py`
- `backend/app/seeds/seed_agents.py`

这些文件涉及 B1/F 或共享契约，启动前必须明确 owner 和 PR 描述。

### B2 不负责

- 用户认证、会话 CRUD、消息 DB 持久化主流程
- 前端渲染组件
- Docker/PostgreSQL/Redis 基础设施
- OpenAPI 全局维护

## 3. 阶段目标

| 阶段 | 目标 | 关键验收 |
|------|------|----------|
| Phase 1 | 单 Provider 可用 | Claude 流式响应通过统一 `StreamChunk` 输出 |
| Phase 2 | 多 Provider 可替换 | Claude/OpenAI/Custom Adapter 都可通过 registry 调用 |
| Phase 3 | 富媒体输出增强 | text/code/diff/web_preview 等内容块可稳定生成 |
| Phase 4 | 多 Agent 编排 | Orchestrator 可拆解任务并调用子 Agent |
| Phase 5 | 稳定性与演示 | 错误、重试、日志、E2E smoke test 和演示链路齐全 |
| Phase 6 | Agent Runtime Pivot | Claude Code / Codex / OpenCode / BuiltinAgent 都通过统一 Adapter 接入 |

## 4. 任务路线图

| 编号 | 任务 | 优先级 | 状态 | 主要文件 | 依赖 |
|------|------|--------|------|----------|------|
| B2-01 | StreamingArtifactParser 流式产物解析器 | P0 | 已完成 | `backend/app/agents/artifact_parser.py` | BaseAgentAdapter / StreamChunk |
| B2-02 | ClaudeAdapter 真实 Anthropic 流式接入 | P0 | 已完成 | `backend/app/agents/adapters/claude.py` | B2-01 |
| B2-03 | OpenAIAdapter 真实 OpenAI 流式接入 | P0 | 已完成 | `backend/app/agents/adapters/openai.py` | B2-01 / B2-02 模式 |
| B2-04 | CustomAdapter 委托上游 Provider | P0 | 已完成 | `backend/app/agents/adapters/custom.py` | B2-02 / B2-03 |
| B2-05 | Agent 配置校验与内置 Agent 配置对齐 | P0 | 已完成 | `backend/app/agents/config_validation.py`, `backend/app/api/v1/agents.py`, `backend/app/schemas/agent.py` | B2-02 / B2-03 / B1 协同 |
| B2-06 | SSE error 状态持久化协同修复 | P0 | 已完成 | `backend/app/api/v1/stream.py`, `backend/tests/test_b1_quality.py` | B2-02，需 B1 协作 |
| B2-07 | ArtifactParser v2：diff/url/web preview 识别 | P1 | 已完成 | `backend/app/agents/artifact_parser.py`, `backend/app/api/v1/stream.py` | B2-01 / B2-06，复用既有 ContentBlock |
| B2-08 | Orchestrator Spec 与任务拆解 Prompt | P1 | 已完成 | `docs/b2/spec/orchestrator.spec.md`, `docs/b2/task-dispatch/B2-08-orchestrator-spec.md` | B2-04 |
| B2-09 | Orchestrator 子 Agent 顺序调度与 block_index 重映射 | P1 | 已完成 | `backend/app/agents/orchestrator.py`, `backend/tests/test_orchestrator.py` | B2-08 / registry |
| B2-10 | Orchestrator 失败降级与部分成功输出 | P1 | 已完成 | `backend/app/agents/orchestrator.py`, `backend/tests/test_orchestrator.py` | B2-09 |
| B2-11 | Provider retry/timeout/rate-limit 策略 | P1 | 已完成，Codex 审阅通过 | `backend/app/agents/adapters/**`, `backend/tests/test_*adapter.py`, `docs/b2/spec/provider-resilience.spec.md` | B2-02 / B2-03 |
| B2-12 | Adapter E2E smoke tests 与可选真实 API slow tests | P1 | 已完成，Codex 审阅通过 | `backend/tests/**`, `backend/pyproject.toml`, `docs/b2/spec/adapter-smoke-tests.spec.md` | B2-02 / B2-03 / B2-04 / B2-11 |
| B2-13 | B2 演示脚本、答辩材料和架构说明 | P2 | 已完成 | `docs/b2/task-dispatch/B2-13-demo-and-architecture.md` | 主链路稳定后 |
| B2-14 | Agent Runtime Pivot 文档与任务重基线 | P0 | 已完成，Codex 复审通过 | `docs/b2/task-dispatch/**`, `docs/spec/agent-runtime-pivot.adr.md`, `docs/b2/spec/**` | B2-13 |
| B2-15 | ModelGateway 拆分与 raw LLM Adapter 降级 | P0 | 已完成，Codex 复审通过 | `backend/app/agents/model_gateway/**`, `backend/app/agents/adapters/**`, `backend/tests/**` | B2-14 / B2-11 / B2-12 |
| B2-16 | Claude Code ExternalAgentAdapter | P0 | 已完成，Codex 复审通过 | `backend/app/agents/external/claude_code.py`, `backend/tests/test_claude_code_external_adapter.py` | B2-15 |
| B2-17 | Codex ExternalAgentAdapter | P0 | 已完成，Codex 复审通过 | `backend/app/agents/external/codex.py`, `backend/tests/test_codex_external_adapter.py` | B2-16 |
| B2-18 | OpenCode ExternalAgentAdapter | P0 | 已完成，Codex 复审通过 | `backend/app/agents/external/opencode.py`, `backend/tests/test_opencode_external_adapter.py` | B2-16 / B2-17 |
| B2-19 | BuiltinAgent MVP | P0 | 已完成，Codex 复审通过 | `backend/app/agents/builtin/**`, `backend/tests/test_builtin_agent*.py` | B2-15 |
| B2-20 | 真实 Agent Demo Smoke 与 Registry 接线 | P0 | 已完成，Codex 复审通过 | `backend/app/agents/registry.py`, `backend/app/seeds/seed_agents.py`, `backend/tests/test_real_agent_demo_smoke.py` | B2-16 / B2-17 / B2-18 / B2-19 |

## 5. 推荐执行顺序

### 当前最近三步

1. Claude Code：按 Git/PR AI 角色处理 B2-20 的 Git 状态整理、commit、push 和 PR，不修改代码。
2. F / B1 协同：基于最新 `shared/openapi.yaml` 重新生成前端类型，并更新 Agent 创建表单对新 provider/config 的消费。
3. B2：如需真实 runtime 证明，手动 opt-in 跑 `AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1`；默认测试仍不得访问真实 runtime / 网络。

### 不建议提前做

- 不要把 raw LLM backend 注册为最终顶层 Agent provider。
- 不要在 ExternalAdapter 中自实现 tool loop；ExternalAdapter 只映射第三方 runtime 事件。
- 不要为了 B2-15 至 B2-20 修改 `BaseAgentAdapter`、`StreamChunk`、`ContentBlock` 或 OpenAPI，除非任务文档显式授权。

## 6. 任务拆分原则

每个 B2 子任务应满足：

- 一个 PR 只解决一个明确目标。
- 文件范围尽量限制在 `backend/app/agents/**` 和对应测试。
- 涉及 B1/F/shared 契约时，先在任务文档中标注协作对象。
- 所有 runtime 测试默认使用 fake/mock SDK、fake subprocess 或 fake runtime，不调用真实上游。
- 真实 runtime 测试只能作为 `slow` 或手动 smoke test，不进入默认测试链路。
- 真实 runtime smoke 统一使用 `AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1` opt-in。

## 7. PR 边界建议

| PR | 建议分支 | 内容 |
|----|----------|------|
| PR-B2-14 | `docs/B2-agent-runtime-rebaseline` | 任务分发文档、ADR/spec 口径同步 |
| PR-B2-15 | `feat/B2-model-gateway-split` | raw LLM adapter 降级为 ModelGateway |
| PR-B2-16 | `feat/B2-claude-code-runtime` | Claude Code ExternalAgentAdapter |
| PR-B2-17 | `feat/B2-codex-runtime` | Codex ExternalAgentAdapter |
| PR-B2-18 | `feat/B2-opencode-runtime` | OpenCode ExternalAgentAdapter |
| PR-B2-19 | `feat/B2-builtin-agent-mvp` | BuiltinAgent loop / tools / MCP MVP |
| PR-B2-20 | `feat/B2-real-agent-demo-smoke` | registry / seed / orchestrator / demo smoke 接线 |

Claude Code 只在 Codex 审阅通过后处理 Git/PR，不负责实现这些 PR 内容。

## 8. 里程碑验收

### ModelGateway 底座

- raw Claude / OpenAI / DeepSeek 能作为 BuiltinAgent 内部 backend 使用。
- 旧 adapter 测试在兼容 shim 下不退化。
- ModelGateway 不注册为最终顶层 Agent provider。

### External Runtime 链路

- `ClaudeCodeAdapter`、`CodexAdapter`、`OpenCodeAdapter` 都实现 `BaseAgentAdapter v2`。
- 三者都把 `workspace_path` 作为 runtime cwd。
- 三者都能把 runtime tool event 映射为 `tool_call/tool_result`。
- 默认测试使用 fake SDK / fake subprocess；真实 runtime smoke opt-in。

### BuiltinAgent 链路

- BuiltinAgent 能通过 ModelGateway 获取模型输出。
- `read_file/write_file/bash` 三件套遵守 workspace sandbox。
- MCP stdio client 至少有 fake/server-down 测试覆盖。

### Demo 链路

- registry 顶层 provider 使用 `claude_code/codex/opencode/builtin/mock`。
- seed 中至少包含 `claude-code`、`codex-helper`、`opencode-helper`、`web-designer`、`orchestrator`。
- Orchestrator 能调度真实 runtime adapter fake。
- demo smoke 能证明 Agent 写文件后 Workspace API 可见，SSE 中有 ToolCallBlock 事件。

## 9. Codex 审阅重点

后续每个 B2 PR，Codex 默认检查：

- 是否保持 `BaseAgentAdapter.stream()`、`StreamChunk`、`ContentBlock`、OpenAPI 不变，除非任务明确授权。
- Adapter 是否避免访问数据库。
- ExternalAdapter 是否只映射第三方 runtime 事件，没有自实现 tool loop。
- BuiltinAgent 是否只通过 workspace sandbox 执行读写和命令。
- ModelGateway backend 是否没有注册为最终顶层 Agent。
- `tool_call/tool_result` 是否 call_id 配对，错误路径是否闭合。
- 是否有 fake/mock 单元测试，真实 runtime smoke 是否 opt-in。
- 是否跨越 B1/F/shared 边界且未说明。
