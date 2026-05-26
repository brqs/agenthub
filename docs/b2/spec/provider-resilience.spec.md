# Provider Resilience Spec

> 定义 B2 Provider Adapter 的 retry、timeout 和错误映射策略。
> 本 Spec 服务于 B2-11，不修改 `BaseAgentAdapter`、`StreamChunk`、OpenAPI 或前端契约。
> B2-20 之后，本 Spec 仅适用于 `agents/model_gateway/**` 与 legacy raw adapter shim；`claude` / `openai` / `deepseek` / `custom` 不再是顶层 AgentRegistry provider。

## 目标

让 legacy Claude / OpenAI / DeepSeek / Custom 适配器或 ModelGateway backend 在上游不稳定时输出一致、可预测的 `StreamChunk`：

- 缺少 API key 时立即输出 `missing_api_key`。
- rate limit 统一输出 `rate_limit`，默认不重试。
- 连接失败统一输出 `connection_error`。
- 请求打开阶段超时统一输出 `timeout`。
- 其他上游 SDK 错误统一输出 `upstream_error`。
- retry 仅发生在尚未产生任何内容块之前，避免重复输出 partial content。
- 一旦已经输出任何 `block_start` / `delta` / `block_end`，后续异常不得重试，只能关闭当前 parser 输出并 yield `error`。

## 非目标

- 不实现全链路队列重试。
- 不实现并发请求或 fallback provider。
- 不修改数据库、registry、seed、OpenAPI、schema 或前端。
- 不新增 `StreamChunk` 字段。
- 不在 `CustomAdapter` 中额外包一层 retry；Custom 只委托上游 Adapter，避免双重重试。

## 配置

Provider Adapter 通过 `config` / `default_config` 读取以下可选字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_retries` | int | 1 | 失败后最多重试次数；总尝试次数为 `max_retries + 1` |
| `retry_backoff_seconds` | float | 0.25 | 重试退避基准；测试中可设为 0 |
| `request_timeout_seconds` | float | 30.0 | 打开上游 stream 的超时时间，不限制整个流式生成总时长 |
| `retry_on_rate_limit` | bool | false | 默认 false，避免打爆上游；如显式 true，可对 rate limit 进行同样重试 |

配置边界：

- `max_retries` 小于 0 时按 0 处理，大于 3 时按 3 处理。
- `retry_backoff_seconds` 小于 0 时按 0 处理。
- `request_timeout_seconds` 小于等于 0 时按默认值处理。
- 非法类型不得导致未捕获异常，应回退默认值。

## Retry 规则

### 可重试场景

默认可重试：

- connection error
- timeout
- transient upstream API error

默认不重试：

- missing API key
- unsupported upstream provider
- rate limit（除非 `retry_on_rate_limit=true`）
- 已经输出任意内容块后的异常

### 内容输出后的异常

当 Adapter 已经 yield 过 `block_start` / `delta` / `block_end` 后，后续异常必须：

1. 不重试。
2. 调用 `StreamingArtifactParser.flush()` 输出剩余 close chunk，尽量保证 block 闭合。
3. yield 标准 `StreamChunk(event_type="error", error_code=...)`。

## 错误码

| 错误码 | 含义 |
|--------|------|
| `missing_api_key` | 对应 provider 的 API key 缺失 |
| `rate_limit` | 上游限流 |
| `timeout` | 打开上游 stream 超时 |
| `connection_error` | 网络连接失败、DNS、连接重置等 |
| `upstream_error` | SDK APIError 或其他上游异常 |

错误 chunk 可使用现有 `metadata` 字段携带调试信息：

```python
StreamChunk(
    event_type="error",
    agent_id=self.agent_id,
    error_code="timeout",
    error="OpenAI request timed out",
    metadata={
        "provider": "openai",
        "attempts": 2,
        "retryable": True,
    },
)
```

不得在 `metadata` 中输出 API key、JWT、完整请求体或用户隐私内容。

## Provider 对齐

### ClaudeAdapter

- 捕获 Anthropic SDK 的 rate limit、API error、connection / timeout 类异常。
- 打开 `client.messages.stream(...)` 阶段可以重试。
- `stream.text_stream` 已经输出内容后，不重试。

### OpenAIAdapter

- 捕获 OpenAI SDK 的 rate limit、API error、connection / timeout 类异常。
- `client.chat.completions.create(..., stream=True)` 阶段可以重试。
- 迭代 stream 已经输出内容后，不重试。

### DeepSeekAdapter

- 继续继承 OpenAIAdapter 的 resilience 行为。
- 错误 metadata 中 provider 应是 `deepseek`。

### CustomAdapter

- 不新增 retry。
- 继续透明转发上游 Adapter 的 chunk。
- 不吞掉上游 error chunk。

## 验收标准

- Claude/OpenAI 对 setup 阶段 transient upstream error 会按配置重试，成功后只输出一次正常内容流。
- Claude/OpenAI 对 rate limit 默认不重试，直接输出 `rate_limit`。
- Claude/OpenAI 对 request timeout 输出 `timeout`。
- Claude/OpenAI 对 connection error 输出 `connection_error`。
- 内容已经开始输出后发生异常时，不重试，先 flush parser，再输出 error。
- DeepSeek 继承 OpenAIAdapter resilience 行为。
- CustomAdapter 不进行二次 retry，只转发上游输出。
- 所有测试、ruff、mypy 通过。
