# B2-20 真实 Agent Demo Smoke 与 Registry 接线

任务编号：B2-20
任务名称：真实 Agent Demo Smoke 与 Registry 接线
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-14 至 B2-19

## 任务目标

完成真实 Agent Runtime 的最终接线：registry、seed、orchestrator 子 Agent、demo smoke tests。

本任务结束后，顶层 Agent provider 语义必须从 raw LLM provider 切换为真实 runtime / builtin：

- `claude_code`
- `codex`
- `opencode`
- `builtin`
- `mock`

`claude` / `openai` / `deepseek` / `custom` 只能作为 ModelGateway 内部 backend 或临时兼容迁移项，不得作为最终内置 Agent 顶层 provider。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b2/spec/builtin-agent-framework.spec.md`
5. `docs/b1/spec/workspace-sandbox.spec.md`
6. `backend/app/agents/registry.py`
7. `backend/app/seeds/seed_agents.py`
8. `backend/app/agents/orchestrator.py`
9. B2-15 至 B2-19 的实现和测试

## 允许修改

- `backend/app/agents/registry.py`
- `backend/app/seeds/seed_agents.py`
- `backend/app/agents/config_validation.py`
- `backend/tests/test_agent_config_validation.py`
- `backend/tests/test_registry*.py`
- `backend/tests/test_real_agent_demo_smoke.py`
- `backend/tests/test_orchestrator.py`（仅补真实 runtime fake E2E，不重写 Orchestrator）
- `docs/ai-collaboration-log.md`
- 本任务文档（如需同步边界）

如确需同步配置 schema，可最小修改：

- `backend/app/schemas/agent.py`
- `shared/openapi.yaml`
- `docs/api-spec.md`

涉及 OpenAPI 时必须在交付说明中标注契约变更，并说明前端类型是否需要重新生成。

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/api/v1/stream.py`
- `backend/app/services/workspace_service.py`
- `backend/app/models/**`
- `frontend/**`
- `.env`
- `backend/.env`
- `docker-compose.yml`

本任务不允许改 BaseAgentAdapter、StreamChunk、ContentBlock 或 workspace 实现。

## 实现要求

### 1. Registry v2

`backend/app/agents/registry.py` 最终顶层 provider map 必须包含：

```python
PROVIDER_MAP = {
    "mock": MockAdapter,
    "claude_code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "opencode": OpenCodeAdapter,
    "builtin": BuiltinAgentAdapter,
}
```

可以保留 legacy provider 迁移兼容，但不得让内置 seed 继续使用 legacy provider。

### 2. 内置 Agent seed

`backend/app/seeds/seed_agents.py` 至少包含：

- `claude-code` -> provider `claude_code`
- `codex-helper` -> provider `codex`
- `opencode-helper` -> provider `opencode`
- `web-designer` -> provider `builtin`
- `orchestrator` -> provider `builtin` 或 registry 特例 Orchestrator

`orchestrator` 的默认 managed agents 必须包含真实 runtime：

```text
claude-code
codex-helper
opencode-helper
web-designer
```

### 3. 配置校验

更新 `validate_agent_config`：

- 支持新 provider：`claude_code`、`codex`、`opencode`、`builtin`、`mock`。
- legacy raw provider 只能作为 ModelGateway backend 出现在 builtin config 中，例如 `model_backend="claude"`。
- `opencode` config 必须允许 `command` / `args` / `timeout_seconds`。
- `builtin` config 必须允许 `model_backend`、`max_iterations`、`mcp_servers`。

### 4. Orchestrator 接线

保留现有 Orchestrator 顺序调度和失败降级逻辑，不重写。

需要验证：

- registry 能为 orchestrator 构造 `adapter_factory`。
- `adapter_factory("claude-code")` 返回 `ClaudeCodeAdapter`。
- `adapter_factory("codex-helper")` 返回 `CodexAdapter`。
- `adapter_factory("opencode-helper")` 返回 `OpenCodeAdapter`。
- `adapter_factory("web-designer")` 返回 `BuiltinAgentAdapter`。

### 5. Demo smoke

新增 fake runtime E2E smoke，覆盖：

1. 用户发起 “生成一个 hello.html”。
2. Orchestrator 调用至少一个真实 runtime adapter fake。
3. fake adapter yield `tool_call(write_file)` / `tool_result(ok)`。
4. workspace 中能看到 `hello.html`。
5. Workspace API 可读取该文件。
6. SSE body 中有 `tool_call` / `tool_result`。
7. message content 中持久化 `ToolCallBlock`。

真实 runtime smoke 必须 opt-in：

```bash
AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1 python -m pytest tests/test_real_agent_demo_smoke.py -m slow -q
```

可用 `AGENTHUB_LIVE_RUNTIME_PROVIDERS=claude_code,codex,opencode` 选择要跑的真实 runtime；未设置时默认尝试三类 provider，OpenCode CLI 未安装时仅跳过对应 provider。

默认测试不得访问真实 Claude Code / Codex / OpenCode runtime。

## 测试要求

建议命令：

```bash
cd backend
python -m pytest tests/test_registry*.py tests/test_agent_config_validation.py tests/test_real_agent_demo_smoke.py tests/test_orchestrator.py -q
python -m ruff check app/agents app/seeds tests/test_registry*.py tests/test_real_agent_demo_smoke.py
python -m mypy app/agents app/seeds
```

如果全量后端测试可承受，额外运行：

```bash
python -m pytest -q
```

## 交付说明

完成后交付说明必须包含：

1. 最终顶层 provider map。
2. seed agent 列表和 provider。
3. legacy raw provider 的兼容/移除策略。
4. Orchestrator adapter_factory 验证结果。
5. fake demo smoke 覆盖路径。
6. 是否发生 OpenAPI/schema 变更。
7. 验证命令和结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和测试结果交给 Codex 复审。Codex 复审通过后，Claude Code 才能处理 Git/PR。

## 执行结果

状态：已完成，Codex 复审通过。

- Registry 顶层 `PROVIDER_MAP` 已切换为 `mock` / `claude_code` / `codex` / `opencode` / `builtin`。
- Seed 已切换为真实 runtime / builtin provider，并设置 orchestrator 默认 managed agents：`claude-code`、`codex-helper`、`opencode-helper`、`web-designer`。
- `validate_agent_config` 支持 B2-20 新 provider；legacy raw provider 不再可作为新顶层 Agent provider，只在 registry 迁移兼容路径映射到 `builtin` ModelGateway backend。
- 补充 registry / Orchestrator adapter_factory / fake real-agent demo smoke 测试；真实 runtime smoke 默认 skip，仅 `AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1` 时 opt-in，并可用 `AGENTHUB_LIVE_RUNTIME_PROVIDERS` 选择 provider。
- 同步了 `backend/app/schemas/agent.py`、`shared/openapi.yaml` 和 `docs/api-spec.md` 的 provider/config schema，前端类型需要重新生成。
- 回修检查中修复 fake smoke 固定 `orchestrator` id 导致的主键冲突，测试只创建和清理 `demo-smoke-*` Agent，不删除 seed `orchestrator`。
- 本机验证：B2-20 指定测试 50 passed / 3 skipped；ruff passed；mypy passed。`AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1` + `AGENTHUB_LIVE_RUNTIME_PROVIDERS=opencode` 验证 opt-in 路径 1 passed / 2 skipped / 1 deselected。

## Codex 复审结论

结论：通过。

- 未发现阻塞性问题。
- 上一轮两条 findings 已回修：fake smoke 不再固定插入/删除 seed `orchestrator`；live smoke 不再无条件占位 skip。
- 复审未执行 `AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1` 的真实 runtime 路径，避免实际调用本机 runtime / 网络；当前 live smoke 主要证明 opt-in 后会进入 provider 参数化 adapter 调用路径，不严格证明真实 runtime 成功产出。
