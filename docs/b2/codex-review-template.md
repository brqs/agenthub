# B2 Codex 复审模板

> 适用范围：B2 Agent Runtime 子任务完成后，Codex 对 OpenCode 实现结果进行代码复审、边界复核和验证记录的场景。

## 使用方式

每次复审前，先把 `<B2-XX>`、`<任务名称>`、任务文档、实现目录、测试文件和高风险关键词替换为当前任务的实际值。

复审默认以问题为先：先列 Findings，再列阻塞问题、结论和测试证据。不要在复审中改代码；如果发现问题，输出明确文件路径、行号和修复方向，交回实现窗口处理。

## 通用复审指令

````text
你现在作为 Codex，复审 AgentHub <B2-XX>：<任务名称>。

请先阅读：
1. AGENTS.md
2. docs/b2/task-dispatch/<B2-XX-task-doc>.md
3. <相关 spec 文档 1>
4. <相关 spec 文档 2>
5. backend/app/agents/base.py
6. backend/app/agents/types.py
7. <本任务涉及的实现目录>
8. <相关测试文件>

重点检查：
- <核心验收点 1>。
- <核心验收点 2>。
- <核心验收点 3>。
- 是否遵守 AGENTS.md 的 owner 边界与任务范围。
- 是否没有修改 BaseAgentAdapter、StreamChunk、OpenAPI、frontend，除非任务文档明确要求。
- 是否没有修改 registry.py / seed_agents.py；如果是 runtime 接线或 cutover，确认是否属于当前任务范围。
- 是否没有把 ModelGateway backend 注册成顶层 Agent。
- workspace_path / tool_specs / ToolSpec.parameters / call_id 等共享契约是否按 spec 使用。
- 错误码、resilience 行为、stream parser flush / done 逻辑是否没有退化。
- 测试是否使用 fake/mock，不访问真实网络、真实 SDK、真实 CLI，除非 smoke 明确 opt-in。
- 新增测试和旧测试是否覆盖关键路径、错误路径、边界条件。

建议执行：
```bash
git status --short
git diff -- <实现目录> <测试文件> docs/ai-collaboration-log.md docs/b2/task-dispatch/<B2-XX-task-doc>.md

cd backend
python -m pytest <相关测试文件> -q
python -m ruff check <实现目录> <相关测试文件>
python -m mypy <实现目录>

rg -n "<高风险关键词1>|<高风险关键词2>|<高风险关键词3>" <实现目录> <相关测试文件>
```

复审输出格式：
- Findings：按严重程度列问题，带文件路径和行号；没有问题则写「未发现阻塞性问题」。
- Open Questions：仅列阻塞性不确定点；没有则写「无」。
- Verdict：通过 / 需修改。
- Test Evidence：列出实际运行命令和结果。
````

## 字段替换建议

- `<任务名称>`：使用任务文档标题，例如 `ModelGateway 拆分与 raw LLM Adapter 降级`。
- `<相关 spec 文档>`：只放当前任务真正相关的 spec，避免复审范围漂移。
- `<实现目录>`：放允许本任务修改的代码目录，例如 `backend/app/agents/external`。
- `<测试文件>`：放本任务新增或应保持通过的测试文件。
- `<高风险关键词>`：放本任务最容易违规的调用或旧路径，例如 `shell=True|os.environ|OpenAIAdapter|registry`。

## 常见高风险检查项

ModelGateway 任务：
- raw Claude / OpenAI / DeepSeek 是否降级为 `backend/app/agents/model_gateway/**` backend。
- 旧 adapter 是否只是兼容 shim，不继续扩展顶层 provider 语义。
- `stream(..., tools=...)` 是否接受 tools 参数，并使用当前 `ToolSpec.parameters` 字段。
- resilience、错误码、parser flush 和旧 adapter 关闭语义是否没有退化。

ExternalAgentAdapter 任务：
- adapter `provider` 是否等于任务指定的 runtime id。
- 是否继承 `BaseAgentAdapter`，且没有修改基类签名。
- `workspace_path` 是否作为 runtime cwd；`workspace_path=None` 时是否安全失败或使用任务允许的安全默认值。
- SDK / subprocess / JSONL 事件是否映射为标准 `StreamChunk`。
- `tool_call` / `tool_result` 是否保持 `call_id` 配对。
- 是否没有自实现第三方 runtime 已经提供的 tool loop。
- SDK 缺失、认证缺失、runtime 异常、timeout、JSON parse error 是否映射为标准错误码。

BuiltinAgent 任务：
- 是否通过 ModelGateway backend 调 raw LLM，而不是直接注册 raw provider。
- ToolRegistry 是否使用 `ToolSpec.parameters`，工具入参与输出是否可追踪。
- 文件读写和命令执行是否走 workspace sandbox 边界校验。
- MCP 仅使用 stdio transport，启动失败和运行崩溃是否映射为标准错误码。
- Agent loop 是否限制迭代次数，并保证工具异常不会破坏流式 done / error 语义。

Registry / smoke cutover 任务：
- 是否只在 cutover 任务中修改 `registry.py` / `seed_agents.py`。
- registry 是否注册 ExternalAgent / BuiltinAgent，不把 ModelGateway backend 暴露为顶层 Agent。
- smoke 是否默认 fake 或 opt-in，真实 CLI / SDK / 网络测试不进入默认测试。
