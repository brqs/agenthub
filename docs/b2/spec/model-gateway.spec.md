# ModelGateway Spec

## 目标

定义 B2 raw LLM backend 的统一入口。B2-20 之后，`claude` / `openai` / `deepseek` 不再是顶层 Agent provider，只能作为 `ModelGateway` backend 被以下组件内部使用：

- BuiltinAgent
- Orchestrator planner / answer synthesis
- External direct chat routing
- legacy raw provider shim

## Backend

支持 backend：

| backend | 实现 |
|---|---|
| `claude` | `backend/app/agents/model_gateway/claude.py` |
| `openai` | `backend/app/agents/model_gateway/openai.py` |
| `deepseek` | `backend/app/agents/model_gateway/deepseek.py` |

顶层 `Agent.provider` 不允许使用这些值。

## 接口

```python
class ModelGateway:
    def __init__(
        self,
        backend: str,
        default_config: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None: ...

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]: ...
```

## StreamChunk 行为

ModelGateway backend 输出标准 `StreamChunk`：

- `start`
- `block_start`
- `delta`
- `block_end`
- `tool_call`
- `tool_result`
- `done`
- `error`

调用方可以选择跳过或重写 `start.agent_id`。例如 external direct chat 已经由 external adapter 发出 `start`，因此必须跳过内部 ModelGateway `start`。

## Tool Calling

BuiltinAgent 使用 `tools` 参数：

- Claude backend 将 `ToolSpec` 转为 Anthropic tools。
- OpenAI backend 将 `ToolSpec` 转为 OpenAI tools。
- DeepSeek 继承 OpenAI-compatible 行为。

Provider 原生 tool event 必须映射为：

- `tool_call`
- `tool_result`

## Resilience

ModelGateway resilience 适用于打开上游 stream 阶段，且只在尚未输出内容前重试。

配置：

| 字段 | 默认值 | 说明 |
|---|---:|---|
| `max_retries` | `1` | 失败后最多重试次数；总尝试次数为 `max_retries + 1` |
| `retry_backoff_seconds` | `0.25` | 重试退避基准 |
| `request_timeout_seconds` | `30.0` | 打开上游 stream 的超时时间 |
| `retry_on_rate_limit` | `false` | 是否对 rate limit 重试 |

错误码：

| error_code | 场景 |
|---|---|
| `missing_api_key` | 对应 provider API key 缺失 |
| `rate_limit` | 上游限流 |
| `timeout` | 打开上游 stream 超时 |
| `connection_error` | 网络连接失败 |
| `upstream_error` | SDK APIError 或其他上游异常 |

规则：

- missing API key 不重试。
- rate limit 默认不重试。
- connection error / timeout / transient upstream error 可重试。
- 一旦已经输出 `block_start` / `delta` / `block_end`，后续异常不重试，只 flush parser 并输出 error。
- metadata 不得包含 API key、JWT、完整请求体或用户隐私内容。

## ArtifactParser

ModelGateway 自由文本输出继续复用 `StreamingArtifactParser`：

- fenced code block → `code` block。
- unified diff → `diff` block。
- 独立 URL 行 → `web_preview` block。

平台 workspace preview URL 语义见 [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md)。ArtifactParser 只负责文本解析，不负责启动 preview。

## 使用方约束

### BuiltinAgent

- 使用 ModelGateway 进行 model call。
- 传入 tools。
- 根据 tool_call 执行本地工具 loop。

### External direct chat

- 使用 ModelGateway 做分类和最终纯问答。
- 不传 tools。
- 分类器输出不进入 SSE。
- direct chat error 不 fallback 到 external runtime。

### Orchestrator

- 使用 ModelGateway 做任务规划和最终答案综合。
- 不把 raw LLM backend 暴露给用户作为 agent。

## 测试计划

- 三个 backend 都能输出标准 text chunk 序列。
- 缺 API key 返回 `missing_api_key`。
- setup 阶段 timeout 返回 `timeout`。
- setup 阶段 transient error 按配置重试。
- 内容输出后异常不重试。
- ToolSpec 能映射为 provider 原生 tool schema。
- external direct chat 能跳过 ModelGateway 内部 `start`。

## 验收标准

- raw LLM provider 不再作为顶层 Agent provider。
- BuiltinAgent / Orchestrator / direct chat 共享同一 ModelGateway。
- retry / timeout / 错误码行为在 Claude/OpenAI/DeepSeek 间一致。
