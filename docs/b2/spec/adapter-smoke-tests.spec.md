# Adapter Smoke Tests Spec

> 定义 B2 Adapter E2E smoke tests 与可选真实 API slow tests 的边界。
> 本 Spec 服务于 B2-12，不修改 Adapter 公共契约、不提交任何 API key。

## 目标

B2-12 的目标是给 Agent Adapter 主链路补一层“比单元测试更接近真实消费方式”的 smoke tests：

- 用 fake/mock upstream 验证 Claude / OpenAI / DeepSeek / Custom Adapter 的端到端 `stream()` 输出契约。
- 验证输出事件序列能被 B1 `_ContentAccumulator` 正确消费并形成 ContentBlock。
- 验证 error chunk 不破坏内容累积和事件生命周期。
- 提供可选真实 API slow tests，用于人工 smoke，不进入默认 CI / 默认 pytest。

## 非目标

- 不扩大 Provider Adapter 功能。
- 不在默认测试中访问真实 Anthropic / OpenAI / DeepSeek API。
- 不读取、打印或提交 `.env`、API key、token。
- 不修改 OpenAPI、BaseAgentAdapter、StreamChunk、ContentBlock、registry、API 路由或前端。
- 不测试完整前端 UI。

## 测试分层

### 默认 smoke tests

默认 smoke tests 必须：

- 使用 fake client / fake stream / monkeypatch。
- 不依赖真实网络。
- 不依赖 `.env` 中的真实 API key。
- 默认 `pytest` 必须运行并通过。
- 覆盖 adapter 输出能被 `_ContentAccumulator` 消费。

建议文件：

```text
backend/tests/test_adapter_smoke.py
```

### 可选真实 API slow tests

真实 API slow tests 必须：

- 使用 `@pytest.mark.slow`。
- 默认 skip。
- 只有显式设置 `AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1` 时才运行。
- 每个 Provider 还必须检查对应 API key 是否存在：
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `DEEPSEEK_API_KEY`
- 请求 prompt 必须极短，`max_tokens` 必须较小。
- 不断言具体模型内容，只断言事件协议和至少一个非空 text/code 内容。

建议文件：

```text
backend/tests/test_adapter_live_smoke.py
```

## Pytest Marker

如果新增 slow tests，必须在 `backend/pyproject.toml` 注册 marker：

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests that call live external providers or are too slow for default runs",
]
```

默认测试命令仍是：

```bash
python -m pytest
```

手动真实 API smoke 命令是：

```bash
AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1 python -m pytest tests/test_adapter_live_smoke.py -m slow -q
```

Windows PowerShell 可使用：

```powershell
$env:AGENTHUB_RUN_LIVE_PROVIDER_TESTS="1"; python -m pytest tests/test_adapter_live_smoke.py -m slow -q
```

## 事件协议断言

Smoke tests 至少要提供共享断言 helper：

- 第一个事件是 `start`。
- 最终事件是 `done` 或 `error`。
- 如果最终是 `done`，不应出现 `error`。
- 所有 `block_start` / `block_end` 成对匹配。
- 每个 `delta` 的 `block_index` 必须对应已打开 block。
- `done.total_blocks` 应等于输出的 block 数。
- 所有 chunk 都能调用 `to_sse()` 并返回 `{event, data}`。
- `_ContentAccumulator.feed(chunk)` 不抛异常，并能产出符合预期的 block 列表。

## 默认 smoke 覆盖范围

### ClaudeAdapter

- fake Anthropic stream 输出普通文本。
- 经 `ClaudeAdapter.stream()` 产生标准 chunk。
- `_ContentAccumulator` 可聚合出 text block。

### OpenAIAdapter

- fake OpenAI stream 输出普通文本和空 delta。
- 经 `OpenAIAdapter.stream()` 产生标准 chunk。
- `_ContentAccumulator` 可聚合出 text block。

### DeepSeekAdapter

- 使用 OpenAI-compatible fake stream。
- 验证 DeepSeek 继承 OpenAIAdapter 的 smoke 行为。

### CustomAdapter

- fake upstream adapter 输出 text block。
- `CustomAdapter` 透明转发。
- `_ContentAccumulator` 可聚合出 text block。

### Error Smoke

至少覆盖一个 adapter error chunk：

- 缺 API key 或 fake upstream error。
- 输出 `start` 后输出 `error`。
- `_ContentAccumulator` 不应产生脏 block。

## 可选真实 API 覆盖范围

真实 API slow tests 可覆盖：

- Claude：短 prompt，期望至少一个 text block。
- OpenAI：短 prompt，期望至少一个 text block。
- DeepSeek：短 prompt，期望至少一个 text block。

如果某个 key 缺失，对应测试必须 skip，不得 fail。

## 安全要求

- 不打印 API key。
- 不打印完整环境变量。
- 不把 `.env` 或 `backend/.env` 加入 git。
- 测试失败信息中不得包含 Authorization header。
- 真实 API prompt 不包含敏感数据。

## 验收标准

- 默认 `pytest` 不访问真实网络。
- 新增 smoke tests 能验证 adapter chunk 序列、SSE 序列化和 B1 accumulator 消费。
- slow tests 默认 skip，手动开启时才访问真实 API。
- `backend/pyproject.toml` 注册 `slow` marker，避免 pytest unknown marker warning。
- 所有现有 adapter 单元测试继续通过。
- ruff / mypy / 全量 pytest 通过。
