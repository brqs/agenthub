# B2-19 BuiltinAgent MVP

任务编号：B2-19
任务名称：BuiltinAgent MVP
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-14，B2-15，B1 Workspace / ToolCallBlock 基线

## 任务目标

新增自建 `BuiltinAgentAdapter`，实现 AgentHub 团队自己的最小 agent framework：AgentLoop、ToolRegistry、MCP stdio client、ModelGateway 调用，以及 `read_file/write_file/bash` 三类工具。

本任务的目标是让自建 Agent 具备真实执行能力，不是继续包装 raw LLM chat。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b2/spec/builtin-agent-framework.spec.md`
5. `docs/b1/spec/workspace-sandbox.spec.md`
6. `backend/app/agents/base.py`
7. `backend/app/agents/types.py`
8. `backend/app/agents/model_gateway/**`（B2-15 完成后）
9. `backend/app/services/workspace_service.py`（只读）

## 允许修改

- `backend/app/agents/builtin/**`
- `backend/tests/test_builtin_agent*.py`
- `backend/pyproject.toml`（仅在确需添加 `mcp` 依赖时）
- `docs/ai-collaboration-log.md`
- 本任务文档（如需同步边界）

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/agents/registry.py`（统一接线放 B2-20）
- `backend/app/api/**`
- `backend/app/services/workspace_service.py`
- `backend/app/schemas/**`
- `backend/app/models/**`
- `backend/app/seeds/**`
- `shared/openapi.yaml`
- `frontend/**`
- `.env`
- `backend/.env`

本任务不允许改 B1 workspace service；必须复用其路径校验语义或等价调用。

## 实现要求

### 1. 新增 builtin 包

新增建议结构：

```text
backend/app/agents/builtin/
  __init__.py
  adapter.py
  loop.py
  tools/
    __init__.py
    registry.py
    workspace_tools.py
    bash.py
  mcp/
    __init__.py
    client.py
```

### 2. BuiltinAgentAdapter

`BuiltinAgentAdapter` 必须继承 `BaseAgentAdapter`：

```python
class BuiltinAgentAdapter(BaseAgentAdapter):
    provider = "builtin"
```

行为：

- `workspace_path is None` 时 yield `workspace_violation` error。
- 合并 `default_config` 与 per-call `config`。
- 创建或注入 `ModelGateway`。
- 合并 native tools 与 MCP tools。
- 调用 AgentLoop 并透传标准 `StreamChunk`。

### 3. ToolRegistry

使用当前代码的 `ToolSpec.parameters` 字段定义工具 schema：

- `read_file(path: str)`
- `write_file(path: str, content: str)`
- `bash(command: str)`

工具执行要求：

- `read_file` 只能读 workspace 内 UTF-8 文本，超限或二进制返回 `tool_status="error"`。
- `write_file` 必须拒绝 `../`、绝对路径、`.env`、`.git`、`.ssh`、`secrets`、`.agenthub`。
- `bash` 必须 cwd 强制为 workspace，命令首词白名单，超时默认 30s。
- 禁止 `shell=True`。
- 禁止网络/eval 类工具。

### 4. AgentLoop

最小循环：

1. yield `start`。
2. 调 `ModelGateway.stream(messages, tools=tools, config=...)`。
3. 透传文本和 `tool_call` chunk。
4. 顺序执行工具，yield 对应 `tool_result`。
5. 将 tool result 追加回 messages 后进入下一轮。
6. 没有 tool_call 时 yield `done`。
7. 超过 `max_iterations` 时 yield `error(loop_max_iterations)`。

工具事件必须保持 call_id 配对。

### 5. MCP stdio client

实现 MVP：

- 仅支持 stdio transport。
- 支持 1 个静态配置 server。
- 工具命名前缀使用 `mcp_<server>__<tool>`。
- server 启动失败映射为 `mcp_server_down`。
- tool 调用超时映射为 `tool_call_failed`。

如果实际 MCP SDK 接入风险过高，可以先实现接口和 fake client，真实 SDK smoke 标为 opt-in，但任务交付必须说明缺口。

## 测试要求

至少覆盖：

- 单轮文本：无 tool_call 时正常 done。
- `write_file` 成功后 workspace 内文件存在。
- `read_file` 成功返回文件内容。
- `write_file("../x")` yield `tool_result(error)` + `error(workspace_violation)`。
- `bash("curl http://example.com")` 被白名单拒绝。
- bash timeout。
- `max_iterations` 触发 `loop_max_iterations`。
- MCP server down 映射为 `mcp_server_down`。

建议命令：

```bash
cd backend
python -m pytest tests/test_builtin_agent*.py -q
python -m ruff check app/agents/builtin tests/test_builtin_agent*.py
python -m mypy app/agents/builtin
```

## 交付说明

完成后交付说明必须包含：

1. BuiltinAgent 包结构。
2. AgentLoop 终止条件和 error 行为。
3. ToolRegistry 安全边界。
4. MCP MVP 完成程度和 opt-in 缺口。
5. 验证命令和结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和测试结果交给 Codex 复审。

## 执行结果

状态：已完成，Codex 复审通过。

实现摘要：

- 新增 `backend/app/agents/builtin/`，包含 `BuiltinAgentAdapter`、`AgentLoop`、native `ToolRegistry` 和 MCP stdio client。
- native tools 覆盖 `read_file` / `write_file` / `bash`，统一执行 workspace 内路径校验、写入禁区、命令白名单和超时控制；由于 MVP 没有系统级沙箱，`bash` 白名单移除 `python` / `node` / `pnpm` / `pip` 等可执行任意代码或安装依赖的命令。
- AgentLoop 透传模型文本与 `tool_call`，顺序执行工具并产出配对 `tool_result`，覆盖 `done`、`workspace_violation`、`loop_max_iterations`、`mcp_server_down`、`upstream_error` 等终止路径；在终止前会为已公开但未执行的 tool_call 补齐 error tool_result。
- MCP 当前为手写 stdio JSON-RPC client 和 fake/testable interface，没有接入官方 `mcp` Python SDK，也没有完整 initialize/session 流程；真实 SDK smoke 留给后续 opt-in 验证。
- 新增 `backend/tests/test_builtin_agent.py`，使用 fake ModelGateway 覆盖 B2-19 要求的默认测试路径，并额外锁定 bash 执行逃逸拒绝、已公开 tool_call 配对、MCP tool timeout、ModelGateway stream 异常映射。

验证结果：

- `python -m pytest "tests/test_builtin_agent.py" -q`：16 passed。
- `python -m ruff check "app/agents/builtin" "tests/test_builtin_agent.py"`：passed。
- `python -m mypy app/agents/builtin`：passed。
- 原始 PowerShell 命令 `python -m pytest tests/test_builtin_agent*.py tests/test_builtin_*.py -q` 未展开 glob，改用实际新增测试文件执行。

Codex 复审结果：

- 复审通过；BuiltinAgent MVP 实现与回修完成。
- 验证通过：`python -m pytest tests/test_builtin_agent.py -q` 16 passed，`ruff` passed，`mypy app/agents/builtin` success。
- 未修改禁改文件：`shared/openapi.yaml`、`backend/app/agents/base.py`、`backend/app/agents/types.py`、`backend/app/agents/registry.py`、`backend/app/seeds/seed_agents.py`、`frontend/**`。
- MCP 当前缺口已在任务文档和协作日志中披露：未使用官方 MCP SDK，真实 initialize/session 与 SDK smoke 留给后续 opt-in 验证。
