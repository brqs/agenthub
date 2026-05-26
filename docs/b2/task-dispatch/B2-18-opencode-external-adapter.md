# B2-18 OpenCode ExternalAgentAdapter

任务编号：B2-18
任务名称：OpenCode ExternalAgentAdapter
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-14，B2-15，B2-16，B2-17

## 任务目标

新增 `OpenCodeAdapter`，通过 subprocess CLI 把 OpenCode 作为真实 agent runtime 接入 `BaseAgentAdapter v2`。

OpenCode 是本轮产品 runtime Must，不得降级为旧 ADR 中的候选项或答辩后再接。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b1/spec/workspace-sandbox.spec.md`
5. `backend/app/agents/base.py`
6. `backend/app/agents/types.py`
7. `backend/app/agents/external/claude_code.py`
8. `backend/app/agents/external/codex.py`

## 允许修改

- `backend/app/agents/external/**`
- `backend/tests/test_opencode_external_adapter.py`
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

### 1. 新增 OpenCodeAdapter

新增：

```text
backend/app/agents/external/opencode.py
```

Adapter 定义：

```python
class OpenCodeAdapter(BaseAgentAdapter):
    provider = "opencode"
```

### 2. subprocess CLI 配置

从 merged config 读取：

- `command`：OpenCode CLI 命令列表或字符串，默认不硬编码绝对路径。
- `args`：额外参数列表。
- `timeout_seconds`：默认 120。
- `jsonl`：是否期待 stdout JSONL，默认 true。

推荐内部统一为 `list[str]`，使用 `asyncio.create_subprocess_exec`，不要用 shell=True。

### 3. cwd 与环境变量

- `cwd` 必须是 `workspace_path`。
- `workspace_path is None` 时 yield `workspace_violation` error。
- 子进程 env 只传必要白名单，不得透传完整宿主环境。
- 不在日志输出 API key、JWT 或 `.env` 内容。

### 4. stdout JSONL 映射

测试用 fake subprocess 输出 JSONL。Adapter 支持以下最小事件：

```json
{"type":"text_delta","text":"hello"}
{"type":"tool_call","call_id":"c-1","tool_name":"write_file","arguments":{"path":"index.html"}}
{"type":"tool_result","call_id":"c-1","status":"ok","output":"wrote index.html"}
{"type":"done"}
{"type":"error","error_code":"external_runtime_error","error":"..."}
```

映射到标准 `StreamChunk`。未知事件不得崩溃，映射为 `external_runtime_error` 或忽略时必须有测试说明。

### 5. stderr / exit code

- 非零退出码且未输出 error event：yield `error_code="external_runtime_error"`。
- timeout：kill 子进程，yield `error_code="timeout"`。
- JSON 解析失败：yield `error_code="external_runtime_error"`，错误信息不包含完整敏感 stdout。

## 测试要求

使用 fake subprocess，不调用真实 OpenCode CLI。

至少覆盖：

- JSONL 文本流正常完成。
- tool_call/tool_result 配对。
- `workspace_path` 作为 cwd。
- 非零 exit code 映射为 `external_runtime_error`。
- timeout 会终止子进程并 yield `timeout`。
- JSON 解析失败不会泄露完整输出。

建议命令：

```bash
cd backend
python -m pytest tests/test_opencode_external_adapter.py -q
python -m ruff check app/agents/external tests/test_opencode_external_adapter.py
python -m mypy app/agents/external
```

真实 CLI smoke 只能 opt-in：

```bash
AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1 python -m pytest tests/test_opencode_external_adapter.py -m slow -q
```

缺少 OpenCode CLI 或凭据时必须 skip。

## 交付说明

完成后交付说明必须包含：

1. OpenCode CLI config 格式。
2. JSONL runtime event 到 `StreamChunk` 的映射表。
3. subprocess cwd/env/timeout 安全处理。
4. fake subprocess 测试覆盖点。
5. 验证命令和结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和测试结果交给 Codex 复审。
