# B2-16 Claude Code ExternalAgentAdapter

任务编号：B2-16
任务名称：Claude Code ExternalAgentAdapter
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-14，B2-15，B1 Workspace / ToolCallBlock 基线

## 任务目标

新增 `ClaudeCodeAdapter`，把 Claude Code agent runtime 接入 AgentHub 的 `BaseAgentAdapter v2`。

本任务接的是 Claude Code runtime / Claude Agent SDK，不是 `anthropic` raw LLM API。现有 raw Claude 逻辑只属于 ModelGateway，不得复用为 ExternalAgentAdapter。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b1/spec/workspace-sandbox.spec.md`
5. `backend/app/agents/base.py`
6. `backend/app/agents/types.py`
7. `backend/app/api/v1/stream.py`（只读，理解 tool_call 持久化）
8. `backend/app/services/workspace_service.py`（只读，理解 workspace 边界）
9. B2-15 的 ModelGateway 结果

## 允许修改

- `backend/app/agents/external/**`
- `backend/tests/test_claude_code_external_adapter.py`
- `backend/pyproject.toml`（仅在确需添加 `claude-agent-sdk` 依赖时）
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

本任务不允许修改公共契约或 B1 workspace 实现。

## 实现要求

### 1. 新增 external 包与 Adapter

新增：

```text
backend/app/agents/external/
  __init__.py
  claude_code.py
```

`ClaudeCodeAdapter` 必须继承 `BaseAgentAdapter`：

```python
class ClaudeCodeAdapter(BaseAgentAdapter):
    provider = "claude_code"
```

### 2. workspace_path 必须透传为 cwd

调用 SDK 时必须把 `workspace_path` 作为工作目录传入。若 `workspace_path is None` 且 SDK 需要 cwd：

- yield `start`
- yield `error(error_code="workspace_violation", error="workspace_path is required")`
- return

不要让 SDK 默认在仓库根目录或用户 HOME 目录执行。

### 3. SDK 事件映射到 StreamChunk

至少支持以下标准输出：

- runtime start -> `StreamChunk(event_type="start", agent_id=self.agent_id)`
- 文本 delta -> `block_start(text)` / `delta(text_delta=...)` / `block_end`
- SDK tool start -> `tool_call`，带 `call_id`、`tool_name`、`tool_arguments`
- SDK tool finish -> `tool_result`，带同一 `call_id`、`tool_status`、`tool_output`
- runtime done -> `done(total_blocks=...)`
- runtime exception -> `error(error_code="external_runtime_error")`

工具事件必须成对。不要吞掉 call_id。

### 4. 不自实现工具执行

ExternalAdapter 只能映射 Claude Code runtime 事件，不允许在本任务中实现自己的 `read_file/write_file/bash` loop。工具执行由第三方 runtime 提供。

### 5. SDK 缺失和 API key 缺失

如果测试环境没有安装 SDK，单测应通过 monkeypatch fake SDK 覆盖路径。生产运行时 SDK import 失败必须映射为：

```text
error_code="external_runtime_error"
```

如果 SDK 明确返回认证缺失，映射为：

```text
error_code="missing_api_key"
```

## 测试要求

使用 fake SDK，不访问真实网络。

至少覆盖：

- 文本流：`start -> block_start -> delta -> block_end -> done`
- tool 调用：`tool_call` 与 `tool_result` call_id 配对
- `workspace_path` 传给 SDK cwd
- SDK 抛异常映射为 `external_runtime_error`
- `workspace_path=None` 时不在仓库根目录执行

建议命令：

```bash
cd backend
python -m pytest tests/test_claude_code_external_adapter.py -q
python -m ruff check app/agents/external tests/test_claude_code_external_adapter.py
python -m mypy app/agents/external
```

真实 runtime smoke 只能 opt-in：

```bash
AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1 python -m pytest tests/test_claude_code_external_adapter.py -m slow -q
```

缺少 SDK、CLI 或凭据时必须 skip。

## 交付说明

完成后交付说明必须包含：

1. Claude Code SDK 事件到 `StreamChunk` 的映射说明。
2. workspace cwd 透传验证。
3. fake SDK 测试覆盖点。
4. 是否添加了依赖，以及添加原因。
5. 验证命令和结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和测试结果交给 Codex 复审。
