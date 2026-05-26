# B2-12 Adapter E2E smoke tests 与可选真实 API slow tests

任务编号：B2-12
任务名称：Adapter E2E smoke tests 与可选真实 API slow tests
负责人：B2
执行 AI：Claude Code
审阅 AI：Codex
依赖任务：B2-02 / B2-03 / B2-04 / B2-11

## 任务目标

为 B2 Adapter 主链路补充 smoke tests，验证 Adapter 的标准 `stream()` 输出能被 B1 SSE 持久化逻辑消费：

- 默认 smoke tests 使用 fake/mock upstream，不访问真实网络。
- 覆盖 Claude / OpenAI / DeepSeek / Custom 的成功输出路径。
- 覆盖至少一个 error chunk 路径。
- 验证 chunk 可 `to_sse()`。
- 验证 chunk 可被 `_ContentAccumulator` 聚合成 ContentBlock。
- 增加可选真实 API slow tests，默认 skip，只在显式开启时运行。

本任务是测试稳定性任务，不新增 Provider 功能，不修改生产链路。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/b2/spec/adapter-smoke-tests.spec.md`
3. `docs/b2/spec/provider-resilience.spec.md`
4. `backend/app/agents/base.py`
5. `backend/app/agents/types.py`
6. `backend/app/api/v1/stream.py`
7. `backend/app/agents/adapters/claude.py`
8. `backend/app/agents/adapters/openai.py`
9. `backend/app/agents/adapters/deepseek.py`
10. `backend/app/agents/adapters/custom.py`
11. 现有 adapter 单元测试：
    - `backend/tests/test_claude_adapter.py`
    - `backend/tests/test_openai_adapter.py`
    - `backend/tests/test_deepseek_adapter.py`
    - `backend/tests/test_custom_adapter.py`

## 允许修改

- `backend/tests/test_adapter_smoke.py`
- `backend/tests/test_adapter_live_smoke.py`
- `backend/tests/conftest.py`（如确实需要共享 pytest helper）
- `backend/pyproject.toml`（只允许注册 pytest marker / 调整默认 addopts，不得改依赖）
- `docs/ai-collaboration-log.md`

如测试过程中发现现有 fake client 需要复用，也可以最小修改：

- `backend/tests/test_claude_adapter.py`
- `backend/tests/test_openai_adapter.py`
- `backend/tests/test_deepseek_adapter.py`
- `backend/tests/test_custom_adapter.py`

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/agents/adapters/**`
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

### 1. 新增默认 smoke test

新增：

```text
backend/tests/test_adapter_smoke.py
```

要求：

- 使用 fake upstream / monkeypatch，不访问真实网络。
- 默认 `pytest` 必须运行这些测试。
- 不依赖真实 API key。
- 不读取 `.env` 内容。

建议实现共享 helper：

- `collect_chunks(adapter, messages, config=None)`
- `assert_stream_contract(chunks)`
- `accumulate_content(chunks)`

`assert_stream_contract(chunks)` 至少断言：

- `chunks[0].event_type == "start"`
- 最后一个事件是 `done` 或 `error`
- `block_start` / `block_end` 成对匹配
- `delta.block_index` 对应已打开 block
- `chunk.to_sse()` 可正常执行
- 如果最后是 `done`，则不应出现 `error`
- 如果最后是 `done`，`done.total_blocks` 等于实际 block 数

### 2. 覆盖默认 fake smoke 场景

至少添加：

1. `test_claude_adapter_smoke_accumulates_text_block`
   - fake Anthropic text stream。
   - 断言 `_ContentAccumulator` 输出 text block。

2. `test_openai_adapter_smoke_accumulates_text_block`
   - fake OpenAI stream。
   - 包含一个空 delta，确认不会破坏输出。

3. `test_deepseek_adapter_smoke_uses_openai_compatible_path`
   - fake OpenAI-compatible stream。
   - 断言 DeepSeek 输出可被 accumulator 消费。

4. `test_custom_adapter_smoke_forwards_upstream_blocks`
   - fake upstream adapter 输出 text block。
   - CustomAdapter 透明转发。

5. `test_adapter_error_smoke_has_no_dirty_content`
   - 选择一个 adapter 的 missing API key 或 fake upstream error。
   - 断言输出 `start` + `error`。
   - 断言 accumulator 结果为空或没有未闭合脏 block。

### 3. 新增可选真实 API slow tests

新增：

```text
backend/tests/test_adapter_live_smoke.py
```

要求：

- 文件内测试必须 `pytestmark = pytest.mark.slow` 或每个测试使用 `@pytest.mark.slow`。
- 默认 skip，只有 `AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1` 时才运行。
- 每个 Provider 单独检查对应 API key，缺失时 skip。
- prompt 必须极短，例如 `"Reply with exactly one short sentence."`
- `max_tokens` 必须较小，例如 64。
- 不断言具体回复内容，只断言：
  - 有 `start`
  - 最终 `done`
  - 至少一个 text/code block 有内容
  - stream contract 成立
  - accumulator 能消费

可覆盖：

- Claude live smoke
- OpenAI live smoke
- DeepSeek live smoke

如果 B2-11 尚未合并，B2-12 可以先完成 fake smoke；live smoke 的错误码细节以当前 adapter 行为为准，不要为 live tests 修改 adapter。

### 4. 注册 slow marker

在 `backend/pyproject.toml` 注册：

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests that call live external providers or are too slow for default runs",
]
```

不要让默认 `python -m pytest` 自动跑真实 API。

### 5. 安全要求

- 不提交 `.env` / `backend/.env`。
- 不提交任何 API key。
- 不打印完整环境变量。
- 不在失败信息中暴露 Authorization header。
- 不把真实 API 响应全文写入 docs。

## 验证命令

在 `backend` 目录运行默认测试：

```bash
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_adapter_smoke.py -q
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_adapter_live_smoke.py -q
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_claude_adapter.py tests/test_openai_adapter.py tests/test_deepseek_adapter.py tests/test_custom_adapter.py -q
conda run --no-capture-output -n LLMAgent ruff check tests/test_adapter_smoke.py tests/test_adapter_live_smoke.py
conda run --no-capture-output -n LLMAgent mypy tests/test_adapter_smoke.py tests/test_adapter_live_smoke.py
conda run --no-capture-output -n LLMAgent python -m pytest -q
```

说明：

- `tests/test_adapter_live_smoke.py -q` 在未设置 `AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1` 时应全部 skip。
- 如果未新增 live smoke 文件，必须说明原因；推荐新增并默认 skip。

手动真实 API smoke：

PowerShell：

```powershell
$env:AGENTHUB_RUN_LIVE_PROVIDER_TESTS="1"
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_adapter_live_smoke.py -m slow -q
```

Bash：

```bash
AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1 conda run --no-capture-output -n LLMAgent python -m pytest tests/test_adapter_live_smoke.py -m slow -q
```

在仓库根目录运行：

```bash
git diff --check
git status --short
```

## 完成后汇报

完成后请汇报：

1. 修改了哪些文件。
2. 默认 smoke 覆盖了哪些 Adapter。
3. live smoke 是否新增，默认是否 skip。
4. slow marker 是否已注册。
5. 是否访问了真实 API；如访问，只汇报 provider 和通过/失败，不粘贴完整响应。
6. 测试、ruff、mypy、全量 pytest 结果。
7. 是否修改了任何禁止文件。

## 完成状态

- [x] fake smoke tests 实现（`backend/tests/test_adapter_smoke.py`）
- [x] live smoke tests 实现（`backend/tests/test_adapter_live_smoke.py`）
- [x] slow marker 注册（`backend/pyproject.toml`）
- [x] 全量 pytest / ruff 通过
- [x] 使用真实 B1 `_ContentAccumulator` 消费验证
- [x] **已完成，Codex 审阅通过**

不要 commit，不要 push，不要创建 PR。完成后交给 Codex 审阅。
