# B2 Agent 集成目标框架与任务路线图

> 本文档用于统一 B2 后续开发方向。单个任务启动时，再基于本文档生成对应的详细 Claude Code 执行文档。

## 1. B2 总目标

B2 的目标不是单纯“调通一个 LLM API”，而是为 AgentHub 建立一层稳定的 Agent 集成能力：

- 屏蔽 Claude、OpenAI、自定义 Agent 等 Provider 差异。
- 通过 `BaseAgentAdapter` 向 B1 输出统一 `StreamChunk`。
- 支撑 SSE 流式输出、富媒体 ContentBlock、代码块解析和后续多 Agent 编排。
- 让新增 Provider 或新增 Agent 的成本稳定在小范围改动内。
- 保持 B2 不直接访问数据库，配置由 B1/service/registry 外层注入。

## 2. 设计边界

### B2 负责

- `backend/app/agents/**`
- `backend/app/agents/adapters/**`
- Agent 适配器、产物解析、Provider 错误映射、Orchestrator 编排逻辑
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
| B2-08 | Orchestrator Spec 与任务拆解 Prompt | P1 | 已完成 | `docs/spec/orchestrator.spec.md`, `docs/b2-task-dispatch/B2-08-orchestrator-spec.md` | B2-04 |
| B2-09 | Orchestrator 子 Agent 顺序调度与 block_index 重映射 | P1 | 已完成 | `backend/app/agents/orchestrator.py`, `backend/tests/test_orchestrator.py` | B2-08 / registry |
| B2-10 | Orchestrator 失败降级与部分成功输出 | P1 | 已拆解，待执行 | `backend/app/agents/orchestrator.py`, `backend/tests/test_orchestrator.py` | B2-09 |
| B2-11 | Provider retry/timeout/rate-limit 策略 | P1 | 待拆解 | `backend/app/agents/adapters/**` | B2-02 / B2-03 |
| B2-12 | Adapter E2E smoke tests 与可选真实 API slow tests | P1 | 待拆解 | `backend/tests/**` | B2-02 / B2-03 / B2-04 |
| B2-13 | B2 演示脚本、答辩材料和架构说明 | P2 | 待拆解 | `docs/**` | 主链路稳定后 |

## 5. 推荐执行顺序

### 当前最近三步

1. 执行 B2-10：在 B2-09 顺序调度基础上补齐 Orchestrator 失败降级与部分成功输出。
2. B2-10 完成后启动 B2-11：Provider retry / timeout / rate-limit 策略。
3. 主链路稳定后执行 B2-12：Adapter E2E smoke tests 与可选真实 API slow tests。

### 不建议提前做

- 不要在 B2-03 前实现 Orchestrator。Orchestrator 需要稳定的 Provider Adapter 作为底座。
- 不要在没有确认 ContentBlock/OpenAPI 影响前实现新的 block 类型。
- 不要把 B2-03、B2-04、B2-08 混在一个 PR。

## 6. 任务拆分原则

每个 B2 子任务应满足：

- 一个 PR 只解决一个明确目标。
- 文件范围尽量限制在 `backend/app/agents/**` 和对应测试。
- 涉及 B1/F/shared 契约时，先在任务文档中标注协作对象。
- 所有 Provider Adapter 测试默认使用 fake/mock client，不调用真实上游 API。
- 真实 API 测试只能作为 `slow` 或手动 smoke test，不进入默认测试链路。

## 7. B2-03 预期轮廓

目标：实现 `OpenAIAdapter` 真实流式接入。

预计允许修改：

- `backend/app/agents/adapters/openai.py`
- `backend/tests/test_openai_adapter.py`

关键要求：

- 使用 `openai.AsyncOpenAI`。
- 从 `settings.openai_api_key` 和 `settings.openai_base_url` 读取配置。
- 把 OpenAI streaming delta content 转给 `StreamingArtifactParser.feed()`。
- 输出 `start -> block_start/delta/block_end -> done` 或 `start -> error`。
- 缺少 API Key、rate limit、APIError 要映射为标准 `StreamChunk(error)`。

## 8. B2-04 预期轮廓

目标：实现 `CustomAdapter`，让用户自定义 Agent 复用 Claude/OpenAI 能力。

预计允许修改：

- `backend/app/agents/adapters/custom.py`
- `backend/tests/test_custom_adapter.py`

关键要求：

- 从 `config["upstream_provider"]` 决定委托给 Claude 还是 OpenAI。
- 将自定义 Agent 的 `system_prompt` 注入上游 Adapter。
- 不访问数据库，不直接读取 Agent 表。
- 不重复实现 Provider 流式逻辑。

## 9. B2-05 预期轮廓

目标：补齐 Agent 创建/更新时的配置校验，并让内置 Agent seed 与运行时规则一致。

预计允许修改：

- `backend/app/agents/config_validation.py`
- `backend/app/api/v1/agents.py`
- `backend/app/schemas/agent.py`
- `backend/app/seeds/seed_agents.py`
- `backend/tests/test_agent_config_validation.py`
- `shared/openapi.yaml`
- `docs/api-spec.md`

关键要求：

- `config.model` 必须属于 provider 或 custom upstream provider 支持的模型。
- custom agent 必须有非空 `system_prompt` 和合法 `config.upstream_provider`。
- `temperature=0` 必须保留为合法值，不能被默认值覆盖。
- PATCH `config` 必须是局部合并，不是整体替换。
- seed 中的内置 Agent 必须通过同一套校验规则。
- OpenAPI/API 文档需要显式记录 `upstream_provider`，PR 描述中标注契约变更。

## 10. B2-06 协同风险

B2-02 审阅时发现一个跨边界问题：

- Adapter 可以 yield `StreamChunk(event_type="error")`。
- B1 SSE 层必须识别 error chunk，否则可能仍把 message 状态持久化为 `done`。
- 当前 `stream.py` 已经包含部分 error chunk 处理逻辑，但仍需要补齐 Adapter error chunk 和 Adapter 中途抛异常时的回归测试，并确认 partial content 会被保存。

该问题需要 B1/B2 协同处理，不应由 B2 在 Provider Adapter PR 中擅自修改 `stream.py`。B2-06 已单独拆解为协同任务：

- 明确 error chunk 出现时如何终止 SSE。
- 明确 message.status 应为 `error`。
- 明确 error 前已产生的部分 blocks 应持久化。
- 明确 Adapter 抛异常时也应保存已累积内容并返回 `internal_error`。

## 11. 里程碑验收

### MVP 单聊链路

- `MockAdapter` 可用。
- `ClaudeAdapter` 可用。
- `OpenAIAdapter` 可用。
- `StreamingArtifactParser` 可把代码围栏输出为 code block。
- B1 SSE 端点可消费 B2 `StreamChunk`。

### 自定义 Agent 链路

- 用户创建 custom agent。
- custom agent 可选择 Claude/OpenAI 上游。
- system prompt 生效。
- 配置缺失时有清晰错误。

### Orchestrator 链路

- Orchestrator 能生成结构化任务列表。
- 能顺序调用子 Agent。
- 子 Agent 输出的 `block_index` 不冲突。
- 子 Agent 失败时主流程不中断。

## 12. PR 边界建议

| PR | 建议分支 | 内容 |
|----|----------|------|
| PR-B2-02 | `feat/B2-claude-adapter-streaming` | ClaudeAdapter + test + B2-02 docs |
| PR-B2-03 | `feat/B2-openai-adapter-streaming` | OpenAIAdapter + test |
| PR-B2-04 | `feat/B2-custom-agent-adapter` | CustomAdapter + test |
| PR-B2-05 | `feat/B2-agent-config-validation` | Agent config/model validation + AgentConfig OpenAPI 文档 |
| PR-B2-06 | `fix/B1-B2-stream-error-status` | SSE error 状态修复，需 B1/B2 协同 |
| PR-B2-07 | `feat/B2-artifact-parser-v2` | ArtifactParser v2：diff/web_preview 识别与持久化 |
| PR-B2-08 | `feat/B2-orchestrator-spec` | Orchestrator spec + task dispatch docs，不实现生产代码 |
| PR-B2-09 | `feat/B2-orchestrator-dispatch` | Orchestrator 顺序调度与 block_index 重映射 |
| PR-B2-10 | `feat/B2-orchestrator-fallback` | Orchestrator 失败降级与部分成功输出 |

## 13. Codex 审阅重点

后续每个 B2 PR，Codex 默认检查：

- 是否保持 `BaseAgentAdapter.stream()` 签名不变。
- Adapter 是否避免访问数据库。
- 是否把 provider 原生事件转换为标准 `StreamChunk`。
- 是否复用 `StreamingArtifactParser`，而不是复制解析逻辑。
- 是否对 API Key 缺失、rate limit、upstream error 有明确处理。
- 是否有 fake/mock client 单元测试。
- 是否跨越 B1/F/shared 边界且未说明。
