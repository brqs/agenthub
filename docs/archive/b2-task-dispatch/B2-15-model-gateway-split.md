# B2-15 ModelGateway 拆分与 raw LLM Adapter 降级

任务编号：B2-15
任务名称：ModelGateway 拆分与 raw LLM Adapter 降级
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-14，B2-02 / B2-03 / B2-04 / B2-11 / B2-12

## 任务目标

把现有 Claude / OpenAI / DeepSeek / Custom raw LLM adapter 从顶层 Agent runtime 语义中降级为 BuiltinAgent 内部使用的 ModelGateway 底座。

本任务是结构迁移任务，不接入 Claude Code / Codex / OpenCode runtime，不修改 registry 最终 provider 语义；最终 registry cutover 放到 B2-20。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b2/spec/builtin-agent-framework.spec.md` §6
5. `backend/app/agents/base.py`
6. `backend/app/agents/types.py`
7. `backend/app/agents/adapters/claude.py`
8. `backend/app/agents/adapters/openai.py`
9. `backend/app/agents/adapters/deepseek.py`
10. `backend/app/agents/adapters/custom.py`
11. `backend/app/agents/adapters/resilience.py`
12. 现有 adapter 与 smoke tests

## 允许修改

- `backend/app/agents/model_gateway/**`
- `backend/app/agents/adapters/**`（仅兼容 shim 或 import 迁移）
- `backend/tests/test_*adapter.py`
- `backend/tests/test_provider_resilience.py`
- `backend/tests/test_adapter_smoke.py`
- `backend/tests/test_adapter_live_smoke.py`
- `docs/ai-collaboration-log.md`
- 本任务文档（如需同步边界）

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/agents/orchestrator.py`
- `backend/app/agents/registry.py`（最终 provider cutover 放 B2-20）
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

### 1. 新建 ModelGateway 包

新增结构：

```text
backend/app/agents/model_gateway/
  __init__.py
  gateway.py
  claude.py
  openai.py
  deepseek.py
  resilience.py
```

`gateway.py` 暴露 `ModelGateway`，最小接口：

```python
class ModelGateway:
    def __init__(self, backend: str, default_config: dict[str, Any] | None = None) -> None: ...

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]: ...
```

当前 `ToolSpec` 字段名是 `parameters`，不要写成旧 spec 字段名。

### 2. 迁移 raw backend 行为

- `claude.py` 复用现有 Anthropic streaming、artifact parser、resilience 行为。
- `openai.py` 复用现有 OpenAI-compatible streaming、artifact parser、resilience 行为。
- `deepseek.py` 继续复用 OpenAI-compatible 路径。
- `custom.py` 不迁入 ModelGateway；custom 顶层语义后续由 BuiltinAgent 取代。
- `resilience.py` 从旧 adapter 迁入或复用，错误码行为不变。

### 3. 保持分阶段兼容

B2-20 前，旧 `backend/app/agents/adapters/*.py` 可以保留兼容 shim，确保现有 registry 和测试仍能运行。

兼容 shim 的边界：

- 可以委托到 ModelGateway。
- 不新增新行为。
- 不把 ModelGateway backend 注册为最终顶层 provider。

### 4. 为 BuiltinAgent 预留 tool calling 入口

ModelGateway `stream(..., tools=...)` 必须接受 `tools` 参数。B2-15 可以先让 raw backend 忽略 `tools` 或只做空列表兼容，但接口必须为 B2-19 预留。

## 测试要求

至少覆盖：

- `ModelGateway("claude")` 文本流输出等价于旧 ClaudeAdapter。
- `ModelGateway("openai")` 文本流输出等价于旧 OpenAIAdapter。
- `ModelGateway("deepseek")` 使用 OpenAI-compatible backend。
- 缺少 API key / upstream error / timeout / rate limit 错误映射不退化。
- 旧 adapter shim 的现有测试仍通过。

建议命令：

```bash
cd backend
python -m pytest tests/test_claude_adapter.py tests/test_openai_adapter.py tests/test_deepseek_adapter.py tests/test_provider_resilience.py tests/test_adapter_smoke.py -q
python -m ruff check app/agents tests/test_claude_adapter.py tests/test_openai_adapter.py tests/test_deepseek_adapter.py tests/test_provider_resilience.py tests/test_adapter_smoke.py
python -m mypy app/agents
```

## 交付说明

完成后交付说明必须包含：

1. ModelGateway 新结构和旧 adapter shim 策略。
2. 哪些旧测试被保留并通过。
3. 是否存在暂时忽略 `tools` 的 backend，以及 B2-19 需要补齐的位置。
4. 验证命令和结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和测试结果交给 Codex 复审。
