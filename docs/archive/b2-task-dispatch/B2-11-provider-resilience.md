# B2-11 Provider retry / timeout / rate-limit 策略

任务编号：B2-11
任务名称：Provider retry / timeout / rate-limit 策略
负责人：B2
执行 AI：Claude Code
审阅 AI：Codex
依赖任务：B2-02 / B2-03 / B2-04 / B2-10

## 任务目标

在不修改 Agent 层公共契约的前提下，统一 Claude / OpenAI / DeepSeek / Custom 的上游错误处理策略：

- setup 阶段 transient error 可配置重试。
- rate limit 默认不重试，统一输出 `rate_limit`。
- request timeout 统一输出 `timeout`。
- connection error 统一输出 `connection_error`。
- 其他 SDK API error 统一输出 `upstream_error`。
- 内容已经开始输出后发生异常时，不重试，先 flush parser，再输出 error。

本任务重点是 Provider Adapter 的稳定性，不做 Orchestrator、registry、OpenAPI、前端或数据库改动。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/b2/spec/model-gateway.spec.md`
3. `backend/app/agents/base.py`
4. `backend/app/agents/types.py`
5. `backend/app/agents/artifact_parser.py`
6. `backend/app/agents/adapters/claude.py`
7. `backend/app/agents/adapters/openai.py`
8. `backend/app/agents/adapters/deepseek.py`
9. `backend/app/agents/adapters/custom.py`
10. 相关测试：
    - `backend/tests/test_claude_adapter.py`
    - `backend/tests/test_openai_adapter.py`
    - `backend/tests/test_deepseek_adapter.py`
    - `backend/tests/test_custom_adapter.py`

## 允许修改

- `backend/app/agents/adapters/claude.py`
- `backend/app/agents/adapters/openai.py`
- `backend/app/agents/adapters/deepseek.py`
- `backend/app/agents/adapters/custom.py`
- `backend/app/agents/adapters/resilience.py`（如需新增共享 helper，推荐放这里）
- `backend/tests/test_claude_adapter.py`
- `backend/tests/test_openai_adapter.py`
- `backend/tests/test_deepseek_adapter.py`
- `backend/tests/test_custom_adapter.py`
- `backend/tests/test_provider_resilience.py`（如需新增共享 helper 测试）
- `docs/ai-collaboration-log.md`

如发现文档和实现边界不一致，可最小更新：

- `docs/b2/spec/model-gateway.spec.md`
- `docs/b2/task-dispatch/B2-11-provider-resilience.md`

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/agents/orchestrator.py`
- `backend/app/agents/registry.py`
- `backend/app/api/**`
- `backend/app/schemas/**`
- `backend/app/models/**`
- `backend/app/seeds/**`
- `shared/openapi.yaml`
- `frontend/**`
- `.env`
- `backend/.env`

本任务不允许修改 `BaseAgentAdapter.stream()` 签名、`StreamChunk` schema、`ContentBlock` schema 或 OpenAPI。

## 实现要求

### 1. 抽出共享 resilience helper

建议新增：

```text
backend/app/agents/adapters/resilience.py
```

职责：

- 解析 resilience config：
  - `max_retries`
  - `retry_backoff_seconds`
  - `request_timeout_seconds`
  - `retry_on_rate_limit`
- 判断错误是否可重试。
- 生成标准 error `StreamChunk`。
- 提供安全的 retry/backoff 工具函数。

不要在 helper 中 import 数据库、registry、FastAPI 或具体业务 schema。

### 2. Retry 只能发生在内容输出前

Claude / OpenAI 的 retry 只允许覆盖“打开上游 stream”阶段：

- Claude：`client.messages.stream(...).__aenter__()` 或等价 setup 阶段。
- OpenAI / DeepSeek：`await client.chat.completions.create(..., stream=True)` 阶段。

一旦已经 yield 过任何 parser chunk，就不得 retry，避免重复输出 partial content。

### 3. 内容输出后异常必须 flush parser

如果 stream 迭代过程中发生异常：

1. 不重试。
2. 先调用 `parser.flush()`，yield flush 出来的 `block_end` / delta。
3. 再 yield `StreamChunk(event_type="error", error_code=...)`。

这可以避免前端和 B1 持久化层看到未闭合 block。

### 4. 错误码映射

必须统一输出以下错误码：

- `missing_api_key`
- `rate_limit`
- `timeout`
- `connection_error`
- `upstream_error`

允许使用 `metadata` 携带：

- `provider`
- `attempts`
- `retryable`

禁止携带 API key、JWT、完整请求体、用户隐私内容。

### 5. Provider 具体要求

#### ClaudeAdapter

- 保留现有 streaming artifact parser 行为。
- 保留 system message 合并逻辑。
- rate limit 默认不重试。
- setup 阶段 transient upstream error 按 `max_retries` 重试。
- timeout / connection error 映射为标准错误码。

#### OpenAIAdapter

- 保留 OpenAI-compatible 流式解析行为。
- DeepSeek 继续通过继承复用该实现。
- setup 阶段 transient upstream error 按 `max_retries` 重试。
- timeout / connection error 映射为标准错误码。

#### DeepSeekAdapter

- 不复制 OpenAIAdapter 逻辑。
- 只保留 provider/model/settings 属性。
- 新增测试确认 DeepSeek 继承 OpenAI resilience 行为。

#### CustomAdapter

- 不做二次 retry。
- 继续透明转发上游 Adapter 的 chunk。
- 不吞上游 error chunk。

## 测试要求

至少补充以下测试：

1. `test_openai_retries_setup_transient_error_then_succeeds`
   - 第一次 `create` 抛 transient API error。
   - 第二次返回正常 stream。
   - 断言最终没有 error，且内容只输出一次。

2. `test_openai_does_not_retry_rate_limit_by_default`
   - 抛 rate limit。
   - 断言只调用一次，输出 `rate_limit`。

3. `test_openai_timeout_maps_to_timeout_error`
   - setup 超时。
   - 断言输出 `timeout`。

4. `test_openai_connection_error_maps_to_connection_error`
   - setup 连接失败。
   - 断言输出 `connection_error`。

5. `test_openai_stream_error_after_content_flushes_then_errors`
   - stream 先输出 partial text，再抛异常。
   - 断言 parser flush 后 block 闭合。
   - 断言不重试。
   - 断言最后输出标准 error。

6. `test_claude_retries_setup_transient_error_then_succeeds`
   - Anthropic setup 阶段第一次失败、第二次成功。

7. `test_claude_rate_limit_does_not_retry_by_default`
   - rate limit 输出 `rate_limit`。

8. `test_deepseek_inherits_openai_resilience`
   - DeepSeekAdapter 使用 OpenAIAdapter resilience 路径。

9. `test_custom_adapter_does_not_double_retry`
   - 上游 fake adapter 输出 error chunk。
   - CustomAdapter 只转发，不重新 retry。

10. 如新增 `resilience.py`，添加 helper 单元测试：
    - 默认值。
    - 非法配置回退。
    - retry 上限 clamp。

已有 Claude/OpenAI/DeepSeek/Custom 测试必须继续通过。

## 验证命令

在 `backend` 目录运行：

```bash
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_claude_adapter.py tests/test_openai_adapter.py tests/test_deepseek_adapter.py tests/test_custom_adapter.py -q
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_provider_resilience.py -q
conda run --no-capture-output -n LLMAgent ruff check app/agents/adapters tests/test_claude_adapter.py tests/test_openai_adapter.py tests/test_deepseek_adapter.py tests/test_custom_adapter.py tests/test_provider_resilience.py
conda run --no-capture-output -n LLMAgent mypy app/agents/adapters
conda run --no-capture-output -n LLMAgent python -m pytest -q
```

如果没有新增 `tests/test_provider_resilience.py`，跳过对应单测命令，但必须说明原因。

在仓库根目录运行：

```bash
git diff --check
git status --short
```

## 完成后汇报

完成后请汇报：

1. 修改了哪些文件。
2. 新增了哪些 retry / timeout / error mapping 行为。
3. 哪些错误会重试，哪些不会重试。
4. 内容输出后异常如何处理。
5. 测试、ruff、mypy、全量 pytest 结果。
6. 是否修改了任何禁止文件。

不要 commit，不要 push，不要创建 PR。完成后交给 Codex 审阅。
