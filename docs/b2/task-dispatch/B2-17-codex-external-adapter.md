# B2-17 Codex ExternalAgentAdapter

任务编号：B2-17
任务名称：Codex ExternalAgentAdapter
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-14，B2-15，B2-16

## 任务目标

新增 `CodexAdapter`，把 Codex / OpenAI Agents SDK 作为真实 agent runtime 接入 `BaseAgentAdapter v2`。

本任务不是 `OpenAIAdapter` raw chat completions 的重命名。raw OpenAI 只能作为 ModelGateway backend，Codex ExternalAdapter 必须使用 agent runtime 语义。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b1/spec/workspace-sandbox.spec.md`
5. `backend/app/agents/base.py`
6. `backend/app/agents/types.py`
7. `backend/app/agents/external/claude_code.py`（B2-16 完成后）
8. `backend/app/api/v1/stream.py`（只读）

## 允许修改

- `backend/app/agents/external/**`
- `backend/tests/test_codex_external_adapter.py`
- `backend/pyproject.toml`（仅在确需添加 `openai-agents` 依赖时）
- `docs/ai-collaboration-log.md`
- 本任务文档（如需同步边界）

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/agents/registry.py`（统一接线放 B2-20）
- `backend/app/agents/model_gateway/**`
- `backend/app/api/**`
- `backend/app/services/workspace_service.py`
- `backend/app/schemas/**`
- `backend/app/models/**`
- `backend/app/seeds/**`
- `shared/openapi.yaml`
- `frontend/**`
- `.env`
- `backend/.env`

## 实现要求

### 1. 新增 CodexAdapter

新增或扩展：

```text
backend/app/agents/external/
  codex.py
```

Adapter 定义：

```python
class CodexAdapter(BaseAgentAdapter):
    provider = "codex"
```

### 2. 统一 ExternalAdapter 行为

尽量复用 B2-16 中已经抽出的 event mapping helper；如果没有 helper，可在本任务抽出到 `backend/app/agents/external/events.py`，但不要抽象过度。

必须保持：

- `workspace_path` 作为 runtime cwd。
- `tool_specs` 可忽略，但参数必须保留。
- runtime tool event 映射为 `tool_call/tool_result`。
- runtime 异常映射为 `external_runtime_error`。

### 3. 不复用 raw OpenAIAdapter

禁止直接 import 或委托：

- `backend/app/agents/adapters/openai.py`
- `backend/app/agents/model_gateway/openai.py`

可以复用小型纯函数 helper，例如错误消息清洗，但不能把 raw LLM streaming 当成 Codex runtime。

### 4. 配置约定

Adapter 从 `default_config` / per-call `config` 读取：

- `model`：Codex runtime 默认模型
- `runtime_options`：透传给 SDK 的安全选项
- `timeout_seconds`：runtime 调用超时

不要在 Adapter 中读取数据库。API key 仍由 SDK 或 settings 注入，不能写入日志。

## 测试要求

使用 fake OpenAI Agents SDK，不访问真实网络。

至少覆盖：

- 文本流正常完成。
- tool_call/tool_result 配对。
- `workspace_path` 传给 runtime cwd。
- SDK 认证错误映射为 `missing_api_key`。
- SDK 其他异常映射为 `external_runtime_error`。
- 不 import raw OpenAIAdapter。

建议命令：

```bash
cd backend
python -m pytest tests/test_codex_external_adapter.py -q
python -m ruff check app/agents/external tests/test_codex_external_adapter.py
python -m mypy app/agents/external
```

真实 runtime smoke 只能 opt-in：

```bash
AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1 python -m pytest tests/test_codex_external_adapter.py -m slow -q
```

缺少 SDK、CLI 或凭据时必须 skip。

## 交付说明

完成后交付说明必须包含：

1. Codex runtime 与 raw OpenAI ModelGateway 的边界。
2. SDK fake 测试如何覆盖文本、tool 和错误路径。
3. workspace cwd 透传验证。
4. 验证命令和结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和测试结果交给 Codex 复审。
