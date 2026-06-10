# External Direct Chat Routing Spec

## 目标

为 `claude-code`、`codex-helper`、`opencode-helper` 增加统一的“仅对话 / 真实 runtime”路由规则：

- 仅普通问答、解释、讨论时，不启动第三方 SDK / CLI，不读写 workspace，不调用工具。
- 需要创建、修改、读取、分析项目文件，或执行测试、调试、生成 artifact 时，继续调用真实 external agent runtime。
- 复用 B2-01~B2-12 已建立的 raw LLM 流式对话能力，但不把 `claude` / `openai` / `deepseek` 恢复为顶层 Agent provider。

本 Spec 只覆盖 external runtime agents：

- `claude_code` / seed id `claude-code`
- `codex` / seed id `codex-helper`
- `opencode` / seed id `opencode-helper`

BuiltinAgent、Orchestrator、Workspace Preview / Deploy API 不在本轮范围。

## 校验结论

计划整体可行，但需要明确一个边界修正：

- “调用 B2-01~B2-12”应理解为调用当前 `ModelGateway`，而不是重新注册旧 raw LLM adapter 为顶层 provider。
- B1 SSE 层已经是 provider-agnostic，只依赖 `BaseAgentAdapter.stream()` 和 `StreamChunk`，因此路由应放在 external adapter 内部，B1 不需要新增 provider 分支。
- 当前 `registry` 的顶层 provider 仍应保持为 `claude_code` / `codex` / `opencode` / `builtin` / `mock`；`claude` / `deepseek` / `openai` 只作为 `ModelGateway` backend。
- 纯问答路径可以复用 `ModelGateway.stream()` 输出普通 `text` / `code` / `diff` / `web_preview` chunk，但必须跳过或重写内部 `start`，避免前端看到错误 agent id。
- 现有身份类问题本地短路继续保留，并且优先于模型分类器，避免身份问答也消耗模型调用。

## 路由原则

external adapter 收到最新用户消息后按以下顺序处理：

1. 发送当前 external agent 的 `start` chunk。
2. 执行本地 identity shortcut；命中则直接输出文本并 `done`。
3. 如果 `qa_short_circuit_enabled=false`，直接进入真实 runtime。
4. 调用 `ModelGateway` 做意图分类；分类调用不向 SSE 暴露任何 chunk。
5. 分类为 `direct_chat` 时，用 `ModelGateway.stream()` 生成最终回答。
6. 分类为 `runtime`、分类失败、JSON 解析失败、低置信度或模型调用错误时，进入真实 runtime。

默认 fallback 必须偏向 `runtime`，原因是错误地把任务型请求当成普通聊天会导致用户期望的文件/产物没有生成。

## direct_chat 与 runtime 判定

### direct_chat

适用于不需要访问当前 workspace，也不需要真实工具能力的请求：

- 通用问答、概念解释、架构讨论。
- 询问某段代码思路，但用户没有要求读取仓库文件。
- 要求给出短代码片段、伪代码、算法解释，但不要求写入文件。
- 对 AgentHub 产品行为、使用方式、限制进行说明。

示例：

- “解释一下贪吃蛇游戏怎么实现。”
- “React 中 useEffect 的依赖数组是什么意思？”
- “你觉得这个 timeout 机制应该怎么设计？”

### runtime

适用于需要真实 agent runtime 能力或 workspace 状态的请求：

- 创建、修改、删除、重命名、读取、搜索项目文件。
- 运行测试、构建、lint、调试命令。
- 生成 artifact，例如 `snake.html`、React 页面、脚本、补丁。
- 分析当前 repo、当前文件、报错日志、运行结果。
- 任何 preview / deploy 请求。当前 runtime 只能生成文件，不能启动长驻服务；预览/部署仍由平台层处理。

示例：

- “生成一个 `snake.html` 贪吃蛇小游戏。”
- “请检查当前项目为什么测试失败。”
- “把这个页面改成深色主题。”
- “创建小游戏并部署/预览到 8082。”

## 配置

三个 external provider 共享以下配置键：

| 字段 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `qa_short_circuit_enabled` | bool | `true` | 是否启用纯问答短路 |
| `qa_model_backend` | enum | `deepseek` | direct chat 使用的 `ModelGateway` backend，取值 `claude` / `deepseek` / `openai` |
| `qa_model` | string \| null | null | direct chat 的具体模型名；为空则使用 backend 默认模型 |
| `qa_classifier_model` | string \| null | null | 分类器模型名；为空则复用 `qa_model` 或 backend 默认模型 |
| `qa_max_tokens` | int | `8192` | direct chat 最大输出 token |
| `qa_classifier_max_tokens` | int | `128` | 分类器最大输出 token |
| `qa_temperature` | float | `0.2` | direct chat 温度 |
| `qa_request_timeout_seconds` | float | `20` | 分类和 direct chat 的单次模型调用超时 |
| `qa_stream_idle_timeout_seconds` | float | `10` | direct chat 流式等待下一条 chunk 的 idle timeout |
| `qa_stream_max_runtime_seconds` | float | `45` | direct chat 单次流式回答 hard timeout |
| `qa_stream_heartbeat_seconds` | float | `5` | direct chat 等待 chunk 期间的 heartbeat 间隔 |

Seed 默认值：

| Agent | 默认配置补充 |
|---|---|
| `claude-code` | `qa_short_circuit_enabled=true`, `qa_model_backend=deepseek`, `qa_max_tokens=8192`, `context_max_tokens=64000`, `qa_request_timeout_seconds=20` |
| `codex-helper` | `qa_short_circuit_enabled=true`, `qa_model_backend=deepseek`, `qa_max_tokens=8192`, `context_max_tokens=64000`, `qa_request_timeout_seconds=20` |
| `opencode-helper` | `qa_short_circuit_enabled=true`, `qa_model_backend=deepseek`, `qa_max_tokens=8192`, `context_max_tokens=64000`, `qa_request_timeout_seconds=20` |

Orchestrator 托管的 `conversation` / `dialogue_turn` 子任务会在调用子 Agent 时覆盖为更宽松的
direct-chat 流式预算：idle 至少 45 秒、hard runtime 至少 120 秒、heartbeat 10 秒。该覆盖不改变
普通 Agent 私聊，也不改变真实 CLI/SDK runtime budget。

## 配置校验

`backend/app/agents/config_validation.py` 应在 external runtime 共享校验中增加：

- `qa_short_circuit_enabled` 必须是 bool。
- `qa_model_backend` 必须是 `claude` / `deepseek` / `openai`。
- `qa_model`、`qa_classifier_model` 如果存在，必须是非空 string。
- `qa_max_tokens` 范围 `1..32000`。
- `qa_classifier_max_tokens` 范围 `1..1024`。
- `qa_temperature` 范围 `0..2`。
- `qa_request_timeout_seconds` 范围 `1..120`。
- `qa_stream_idle_timeout_seconds`、`qa_stream_max_runtime_seconds`、`qa_stream_heartbeat_seconds` 范围 `1..3600`。

校验失败继续返回现有 `INVALID_AGENT_CONFIG` / `INVALID_MODEL_BACKEND` 错误结构。

## 分类器契约

分类器使用 `ModelGateway` 的非工具调用模式，输入只包含：

- external agent 的 system prompt 摘要。
- 最新用户消息。
- 必要的短历史上下文。

分类器输出必须是严格 JSON：

```json
{
  "route": "direct_chat",
  "confidence": 0.92,
  "reason": "general architecture discussion, no workspace access required"
}
```

字段规则：

- `route`: `direct_chat` 或 `runtime`。
- `confidence`: `0..1` number。
- `reason`: 短文本，仅用于 debug 日志，不进入最终 message content。

推荐低置信度阈值为 `0.65`。低于阈值时按 `runtime` 处理。分类器如果输出非 JSON、多余 Markdown、未知 route、空内容或 error chunk，也按 `runtime` 处理。

分类器 prompt 必须强调：

- 只判断最新用户消息。
- 历史消息只作为上下文，不代表当前任务仍需继续。
- 如果请求需要 workspace、文件、命令、工具、artifact、preview/deploy，则返回 `runtime`。
- 不要回答用户问题，只输出 JSON。

## direct_chat 输出契约

direct chat helper 使用 `ModelGateway.stream()` 生成最终回答，并映射为当前 external agent 的输出：

- 不启动 Claude SDK、Codex CLI / SDK、OpenCode CLI。
- 不调用 builtin tools，不读写 workspace。
- 不产生 `tool_call` / `tool_result`。
- 不持久化分类器 reason。
- 不把 heartbeat 写入 `message.content`。
- `agent_id` 必须是当前 external agent id，而不是 `model-gateway-*`。
- 如果 `ModelGateway` 已产生 `start` chunk，adapter 应跳过内部 `start`，因为 external adapter 已经发过自己的 `start`。
- 如果 direct chat 期间模型报错，返回标准 `error` chunk；不要 fallback 到 runtime 重试同一个回答，以免一次普通问答意外触发文件操作。

建议 helper 位于：

```text
backend/app/agents/external/direct_chat.py
```

建议公共接口：

```python
async def maybe_stream_direct_chat(
    *,
    agent_id: str,
    provider: str,
    messages: list[ChatMessage],
    system_prompt: str | None,
    config: dict[str, Any],
) -> DirectChatDecision:
    ...
```

其中 `DirectChatDecision` 表达三种结果：

- `route="direct_chat"`：返回可迭代的 `StreamChunk` 流。
- `route="runtime"`：adapter 继续原真实 runtime 路径。
- `route="disabled"`：配置关闭，adapter 继续原真实 runtime 路径。

## Adapter 集成点

三个 external adapter 的集成点保持一致：

1. `stream()` 开始后仍先 yield `StreamChunk(event_type="start", agent_id=self.agent_id)`。
2. 保留 `direct_identity_response()` 本地短路。
3. identity 未命中后，调用 direct chat helper。
4. direct chat 命中时，转发 helper 输出并结束本次 stream。
5. 未命中时，进入现有 SDK / CLI runtime 路径。

具体文件：

- `backend/app/agents/external/claude_code.py`
- `backend/app/agents/external/codex.py`
- `backend/app/agents/external/opencode.py`
- `backend/app/agents/external/workspace_prompt.py`

## B1 / SSE 行为

B1 不新增 API，也不新增 provider 分支：

- `POST /messages` 仍创建 pending agent message。
- `GET /messages/{id}/stream` 仍通过 `get_adapter()` 获取当前 external adapter。
- SSE 事件仍是标准 `StreamChunk.to_sse()`。
- `_ContentAccumulator` 继续只持久化 block/tool 内容；分类器中间结果不进入 accumulator。
- direct chat 的最终消息状态仍由 B1 根据 chunk 流结束情况标记为 `done` 或 `error`。
- `CONVERSATION_BUSY` 行为不变。

## 日志与诊断

建议记录结构化 debug 日志，但必须脱敏：

- `conversation_id`、`message_id`、`agent_id`。
- `route`、`confidence`、`reason`。
- classifier error code / parse error 类型。
- 进入 runtime 的 fallback 原因。

不得记录 API key、完整环境变量、完整 workspace 文件内容。

## 测试计划

### Helper 单测

- 分类为 `direct_chat` 时，返回 direct chat 流。
- 分类为 `runtime` 时，不调用最终回答模型。
- 分类器输出无效 JSON 时 fallback 到 runtime。
- 分类器 error chunk 时 fallback 到 runtime。
- 低置信度时 fallback 到 runtime。
- direct chat 模型 error 时输出 error，不进入 runtime。

### Adapter 单测

- `claude-code` 普通问答不启动 SDK / CLI fallback。
- `codex-helper` 普通问答不启动 `codex` 子进程。
- `opencode-helper` 普通问答不启动 `opencode` 子进程。
- 身份问题仍由本地 shortcut 回答，不调用分类器。
- “生成 `snake.html`” 等 artifact 请求仍进入 runtime。

### API / SSE 测试

- direct chat 产生标准 `start -> block_start -> delta -> block_end -> done`。
- direct chat 的 `message.content` 只包含最终回答，不包含分类 JSON。
- runtime 请求路径的 tool_call / heartbeat / timeout 行为不变。
- 客户端断开 SSE 后消息状态仍按现有逻辑处理。
- `CONVERSATION_BUSY` 行为不变。

### Smoke

- 对 `claude-code`、`codex-helper`、`opencode-helper` 分别发送“解释贪吃蛇游戏怎么实现”，确认无 SDK / CLI 子进程启动。
- 对三者分别发送“生成一个 `snake.html` 贪吃蛇小游戏”，确认进入真实 runtime 并生成文件。
- 对“生成小游戏并预览到 8082”，确认进入 runtime 生成文件，但 agent runtime 不启动也不建议长驻 preview/deploy server。

## 验收标准

- 三个 external agents 对普通问答都能直接完成，且不创建、读取、修改 workspace 文件。
- 三个 external agents 对任务型请求仍调用真实 runtime。
- 顶层 provider 列表不新增 `claude` / `deepseek` / `openai`。
- B1 SSE / OpenAPI 无需新增接口。
- direct chat 不破坏 runtime budget、heartbeat、preview/deploy guard、conversation busy 现有行为。
- 所有新增配置可被 seed 和 API 校验覆盖。

## 非目标

- 不实现平台 Preview / Deploy API。
- 不改变 BuiltinAgent 的工具调用语义。
- 不改变 Orchestrator 的 planner / 子任务调度逻辑。
- 不引入后台任务系统或取消 API。
- 不要求 external runtime 共享 direct chat 会话缓存；上下文仍由 B1 `ContextBuilder` 传入。
