# B2-13 B2 演示脚本、答辩材料和架构说明

任务编号：B2-13
任务名称：B2 演示脚本、答辩材料和架构说明
负责人：B2
执行 AI：Codex
审阅 AI：Codex
依赖任务：B2-01 至 B2-12

## 1. 任务定位

B2-13 是 B2 Agent 集成方向的收尾文档任务，不新增生产代码，不修改 OpenAPI / BaseAgentAdapter / StreamChunk / ContentBlock 契约。

本任务的目标是把 B2 已完成能力整理成可演示、可答辩、可交接的材料：

- 演示时按固定路径说明 B2 的价值与能力边界。
- 答辩时能解释 Adapter、ArtifactParser、Orchestrator、Provider resilience 的设计取舍。
- 交接时能让后续开发者知道 B2 目前完成了什么、如何验证、还有哪些边界不应误判。

## 2. B2 交付总览

| 编号 | 交付内容 | 当前状态 | 关键文件 |
|------|----------|----------|----------|
| B2-01 | StreamingArtifactParser 基础 text/code 解析 | 已完成 | `backend/app/agents/artifact_parser.py` |
| B2-02 | ClaudeAdapter Anthropic 流式接入 | 已完成 | `backend/app/agents/adapters/claude.py` |
| B2-03 | OpenAIAdapter OpenAI 流式接入 | 已完成 | `backend/app/agents/adapters/openai.py` |
| B2-04 | CustomAdapter 委托上游 Provider | 已完成 | `backend/app/agents/adapters/custom.py` |
| B2-05 | Agent 配置校验与内置配置对齐 | 已完成 | `backend/app/agents/config_validation.py` |
| B2-06 | SSE error 状态持久化协同修复 | 已完成 | `backend/app/api/v1/stream.py` |
| B2-07 | ArtifactParser v2：diff / web_preview | 已完成 | `backend/app/agents/artifact_parser.py` |
| B2-08 | Orchestrator Spec 与任务拆解 | 已完成 | `docs/spec/orchestrator.spec.md` |
| B2-09 | Orchestrator 顺序调度与 block_index 重映射 | 已完成 | `backend/app/agents/orchestrator.py` |
| B2-10 | Orchestrator 失败降级与部分成功输出 | 已完成 | `backend/app/agents/orchestrator.py` |
| B2-11 | Provider retry / timeout / rate-limit 策略 | 已完成 | `backend/app/agents/adapters/resilience.py` |
| B2-12 | Adapter smoke tests 与 live slow tests | 已完成 | `backend/tests/test_adapter_smoke.py` |
| B2-13 | 演示脚本、答辩材料、架构说明 | 已完成 | 本文档 |

## 3. B2 架构讲解

### 3.1 B2 在系统中的位置

B2 是 Agent 集成层，位于 B1 的 SSE / 消息持久化层之后，负责把不同 LLM Provider 和多 Agent 编排结果统一翻译成 `StreamChunk`。

```text
User / Frontend
  -> B1 API / SSE endpoint
  -> B1 registry.get_adapter(agent_id)
  -> B2 BaseAgentAdapter.stream(...)
  -> B2 Provider Adapter / Orchestrator
  -> StreamChunk(start/block_start/delta/block_end/done/error)
  -> B1 _ContentAccumulator
  -> Message.content JSONB
```

B2 的核心原则：

- B1 不直接依赖 Anthropic / OpenAI SDK。
- Provider 差异只留在各自 Adapter 内部。
- 对外统一输出 `StreamChunk`，由 B1 和前端按同一事件协议消费。
- Adapter 不访问数据库，Agent 配置由外层注入。

### 3.2 Adapter 模式

`BaseAgentAdapter` 是 B1 和 B2 的解耦点。所有 Provider 都实现同一个 `stream()` 方法：

```text
ChatMessage[] + system_prompt + config
  -> Provider 原生请求
  -> Provider 原生流事件
  -> StreamingArtifactParser
  -> 标准 StreamChunk
```

答辩重点：

- 这里不是追求“所有 Provider 完美抽象一致”，而是采用“协议翻译”。
- 对外协议稳定，内部允许 Provider-specific 处理，例如 Anthropic 的 `text_stream` 与 OpenAI 的 `choices[0].delta.content`。
- DeepSeek 复用 OpenAI-compatible Adapter 路径，降低重复实现。
- CustomAdapter 只做委托，不做二次 retry，避免重试策略叠加。

### 3.3 StreamingArtifactParser

ArtifactParser 的职责是把模型连续输出的文本流切成富媒体块：

- 普通文本 -> `text` block
- fenced code -> `code` block
- diff fence / diff 内容 -> `diff` block
- 独立 URL -> `web_preview` block

关键设计点：

- 使用状态机而不是一次性正则解析，因为 LLM 输出是分片流。
- 对尾部反引号做缓冲，避免 ``` 被拆在多个 delta 中时误判。
- `flush()` 必须关闭未结束 block，保证 B1 持久化层不会收到脏块。

### 3.4 Orchestrator

Orchestrator 的当前实现重点是可测试的顺序调度，而不是直接接真实 registry 或真实 LLM 任务拆解。

当前能力：

- 从 config 注入结构化任务计划。
- 按 priority 顺序调度子 Agent。
- 输出 `agent_switch` 事件。
- 对子 Agent 的 block index 进行全局重映射，避免多个子 Agent 块编号冲突。
- 子 Agent 失败时输出 failure text block，继续执行不依赖失败任务的后续任务。
- 任务计划不可用时可通过 fallback adapter 降级为单 Agent 回复。

答辩重点：

- 当前选择顺序调度，优先保证 SSE 输出顺序和持久化稳定。
- 并发调度不是不能做，而是要解决输出排序、取消、部分失败、前端展示一致性后再做。
- 生产 registry 接线属于 B1/B2 协同边界，不混入 Orchestrator 单元实现。

### 3.5 Provider resilience

B2-11 把 Provider 失败统一成可预期的错误协议。

标准错误码：

- `missing_api_key`
- `rate_limit`
- `timeout`
- `connection_error`
- `upstream_error`

关键规则：

- retry 只发生在打开上游 stream 之前。
- 一旦已经输出任何内容块，后续异常不得 retry，必须先 `parser.flush()` 再输出 error。
- rate limit 默认不 retry，避免继续压垮上游。
- error metadata 只携带 `provider`、`attempts`、`retryable`，不得泄露 API key、JWT、完整请求体或用户隐私内容。

## 4. 标准演示脚本

### 4.1 演示前检查

在 `backend` 目录运行：

```bash
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_provider_resilience.py tests/test_adapter_smoke.py -q
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_adapter_live_smoke.py -q
conda run --no-capture-output -n LLMAgent ruff check app/agents tests/test_provider_resilience.py tests/test_adapter_smoke.py tests/test_adapter_live_smoke.py
conda run --no-capture-output -n LLMAgent mypy app/agents/adapters tests/test_adapter_smoke.py tests/test_adapter_live_smoke.py
```

预期：

- fake smoke tests 通过。
- live smoke tests 默认 skip。
- ruff / mypy 通过。

真实 Provider smoke 仅在人工确认 API key 与网络可用时运行：

```powershell
$env:AGENTHUB_RUN_LIVE_PROVIDER_TESTS="1"
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_adapter_live_smoke.py -m slow -q
```

### 4.2 后端演示路径

1. 打开 API 文档和健康检查：
   - `http://111.229.151.159:8000/docs`
   - `http://111.229.151.159:8000/health`
2. 说明 B2 不直接暴露新的 HTTP 端点，B2 通过 B1 的 `/messages` 与 SSE stream 被调用。
3. 展示 Agent 列表和 Agent 配置：
   - Claude / OpenAI / DeepSeek / Custom provider。
   - Custom agent 通过 `upstream_provider` 委托真实上游。
4. 发起一条消息并观察 SSE：
   - 事件以 `start` 开始。
   - 内容以 `block_start` / `delta` / `block_end` 输出。
   - 成功以 `done` 结束。
   - 失败以 `error` 结束，B1 会保存 error 状态。
5. 展示富媒体输出：
   - 普通文本。
   - fenced code。
   - diff。
   - URL web preview。
6. 展示稳定性：
   - 缺少 API key 时输出 `missing_api_key`。
   - 上游连接失败时输出 `connection_error` 或 `upstream_error`。
   - 默认 smoke tests 不依赖真实网络。

### 4.3 讲解节奏

5 分钟版本：

```text
0:00-0:30  B2 定位：把不同 LLM Provider 统一成 AgentHub 的流式协议。
0:30-1:20  Adapter：Claude / OpenAI / DeepSeek / Custom 的接入方式。
1:20-2:10  ArtifactParser：流式识别 text/code/diff/web_preview。
2:10-3:10  Orchestrator：子 Agent 顺序调度、block_index 重映射、失败降级。
3:10-4:00  Resilience：retry、timeout、rate-limit 和错误码统一。
4:00-4:40  Smoke tests：fake tests 默认稳定，live tests 手动开启。
4:40-5:00  总结：B2 稳定输出 StreamChunk，让 B1/F 不感知 Provider 差异。
```

## 5. 答辩提纲

### 5.1 一句话总结

B2 的价值是把不稳定、差异大的 LLM Provider 和多 Agent 编排，收敛成 AgentHub 内部稳定的流式事件协议。

### 5.2 关键问题与回答

**为什么不用一个巨大的 Provider 抽象覆盖所有模型能力？**

因为不同 Provider 在 streaming、tool use、错误类型和兼容参数上差异很大。B2 只统一 B1/F 必须依赖的最低协议：`ChatMessage` 输入和 `StreamChunk` 输出。Provider-specific 能力保留在 config 和 Adapter 内部，避免抽象过早僵化。

**为什么 retry 只发生在内容输出前？**

因为一旦已经输出 `block_start` 或 `delta`，重试会造成重复内容、重复 block 或持久化污染。B2 的策略是：输出前可以 retry；输出后只能 flush 当前 parser，再用 error chunk 明确终止。

**为什么 Orchestrator 当前选择顺序调度？**

比赛 MVP 更需要稳定、可解释、可持久化的流式输出。顺序调度能保证前端展示和 B1 持久化顺序一致。并发调度可以作为后续增强，但需要额外解决排序、取消、部分失败和超时合并。

**B2 如何保证前端不用关心 Provider 差异？**

前端只消费 B1 SSE 输出的标准事件。Claude / OpenAI / DeepSeek 的原生事件结构、错误类和 SDK 差异都在 Adapter 内部被翻译成 `StreamChunk`。

**真实 API 不稳定时如何演示？**

默认演示可以依赖 fake smoke tests 和前端 mock demo。真实 Provider smoke tests 默认 skip，只在明确设置 `AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1` 且 API key 存在时运行。现场若上游失败，B2 会输出标准 error chunk，前端可展示错误并 retry。

## 6. 当前边界与后续建议

已完成：

- Provider Adapter 主路径。
- 流式富媒体解析。
- Custom agent 委托。
- Orchestrator 注入式调度与失败降级。
- Provider resilience。
- fake smoke tests 和可选 live slow tests。

当前边界：

- Orchestrator 生产 registry 接线仍属于 B1/B2 协同边界。
- Orchestrator 真实 LLM task decomposition 未在 B2-09/B2-10 中接入生产链路。
- live smoke tests 依赖真实网络、API key 和上游额度，不进入默认测试。
- `agent_switch` 与前端任务卡展示若扩展为正式产品能力，需要同步 OpenAPI / ContentBlock 契约。

后续建议：

1. 单独拆一个 B1/B2 协同任务，把 Orchestrator 接入真实 registry 和群聊创建流程。
2. 将当前注入式 Orchestrator 测试保留为核心回归测试，避免生产接线破坏调度语义。
3. 如果要做并发子任务调度，先写 spec，明确输出排序、取消和失败合并策略。
4. 将 live smoke tests 放入手动发布前检查，不放入默认 CI。

## 7. 提交与 PR 建议

建议分支：

```text
docs/B2-final-demo-materials
```

建议 commit：

```text
docs(B2): add final demo and architecture materials
```

建议 PR 标题：

```text
docs(B2): add final demo and architecture materials
```

PR 描述重点：

- B2-13 为文档收尾任务。
- 不修改生产代码。
- 不修改 OpenAPI / BaseAgentAdapter / StreamChunk / ContentBlock。
- 新增 B2 演示脚本、答辩提纲、架构说明和验证命令。
