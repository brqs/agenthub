# B2 AI 子任务分发模板

> 适用范围：B2 Agent Runtime 工作中，Codex 将任务拆解后交给 OpenCode 执行的场景。

## 协作角色

- B2 负责人：决定 Agent 集成方向和任务优先级。
- OpenCode：负责执行 Codex 拆解后的具体子任务。
- Codex：负责总览大局、分工协调、任务拆解、边界和契约检查、最终代码复审。
- Claude Code：仅在 Codex 复审通过后负责 Git 状态整理、commit、push 和 PR 准备，不参与开发实现。

## 分发原则

每个交给 OpenCode 的子任务必须完整、明确、可验证。任务描述不能只写一句“实现某功能”，必须说明背景、边界、禁止事项、测试和交付要求。

拆解新任务前，先参考 `docs/b2/task-dispatch/B2-roadmap.md` 确认任务编号、优先级、依赖关系和 PR 边界；再为当前任务生成独立的详细执行文档。

## 环境约定

B2 本地开发默认使用 Anaconda 环境 `LLMAgent`。分发 Python 子任务时，验证命令应优先使用该环境，例如：

```bash
conda run -n LLMAgent python -m pytest <test-path>
```

如果缺少项目依赖，应在已有 `LLMAgent` 环境内执行 `python -m pip install -e ".[dev]"`，不要创建新的 Python 环境。

## 标准模板

```text
任务编号：B2-XX
任务名称：<一句话说明任务>
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）

背景：
<说明该任务在 AgentHub 架构中的位置、上游/下游依赖、为什么现在做>

请先阅读：
1. AGENTS.md
2. docs/b2/task-dispatch/B2-roadmap.md
3. <当前任务文档或相关代码文件>

文件范围：
允许修改：
- <path>

禁止修改：
- <path>

实现目标：
<描述最终要达到的行为，不只描述改哪个文件>

核心行为：
1. <行为 1>
2. <行为 2>
3. <行为 3>

实现约束：
- 不修改 BaseAgentAdapter.stream() 签名，除非团队确认。
- Adapter 内不访问数据库；配置由外层注入。
- 不引入无必要的新依赖。
- 不修改共享契约文件，除非任务明确要求。
- 保持 async/await 约定，避免同步阻塞 I/O。

测试要求：
1. <测试场景 1>
2. <测试场景 2>
3. <测试场景 3>

验证命令：
- conda run -n LLMAgent python -m pytest <test-path>

交付要求：
完成后请说明：
1. 修改了哪些文件
2. 核心实现思路
3. 运行了哪些测试，结果如何
4. 是否存在未覆盖的边界情况或后续风险
```

## 批量分配格式

当一个阶段允许多个 OpenCode 窗口并行执行时，先给出批次边界，再分别给每个窗口一段可直接粘贴的执行指令。

````text
<前置任务> 复审完成后，建议第 <N> 批并行开 <数量> 个 OpenCode：

- `B2-XX`：<任务短名>
- `B2-YY`：<任务短名>

`B2-ZZ` 等 <依赖任务> 完成并复审后再开；`B2-AA` 最后做。

**OpenCode 1：B2-XX**
```text
你现在作为 OpenCode，执行 AgentHub B2-XX：<任务名称>。

任务文档：
docs/b2/task-dispatch/B2-XX-<slug>.md

必须先读：
AGENTS.md
<相关 spec>
<相关任务文档>
<相关代码文件>

执行边界：
- 允许新增/修改 <path>
- 允许新增/修改 <test-path>
- 不要修改 <禁止修改的共享契约或接线文件>

目标：
<用 1-3 句话说明任务完成后的行为目标。>

完成后运行任务文档中的 pytest / ruff / mypy。不要 commit、push、PR。交付 diff 和测试结果给 Codex 复审。
```
````

批量分配时必须写清楚：

- 哪些任务可以并行，哪些任务必须等待。
- 每个 OpenCode 窗口只负责一个任务编号。
- 共享接线文件由哪个后置任务统一处理。
- 默认不允许 OpenCode commit、push 或创建 PR。

## OpenCode 执行指令模板

用于给单个 OpenCode 新窗口下发实现任务。

````text
你现在作为 OpenCode，执行 AgentHub <任务编号>：<任务名称>。

任务文档：
docs/b2/task-dispatch/<任务文档>.md

必须先读：
1. AGENTS.md
2. <当前任务文档>
3. <相关 spec>
4. <相关代码文件>
5. <相关测试文件或相邻测试>

执行边界：
- 允许新增/修改 <path>
- 允许新增/修改 <test-path>
- 如确需依赖，可最小修改 <dependency-file>
- 不要修改 <forbidden-path>
- 不要修改 <shared-contract-path>

目标：
<说明要实现的业务/架构能力。>

重点要求：
- <关键行为 1>
- <关键行为 2>
- <关键行为 3>
- <安全/沙箱/契约要求>
- <哪些接线留给后续任务>

测试要求：
- <测试场景 1>
- <测试场景 2>
- <测试场景 3>

建议执行：
```bash
cd backend
python -m pytest <test-path> -q
python -m ruff check <code-path> <test-path>
python -m mypy <code-path>
```

交付要求：
- 不 commit
- 不 push
- 不创建 PR
- 提交 diff 摘要、测试结果、已知风险给 Codex 复审
- 如更新任务状态，同步 docs/b2/task-dispatch/README.md、docs/b2/task-dispatch/B2-roadmap.md、docs/ai-collaboration-log.md
````

## Codex 复审指令模板

用于 OpenCode 完成后，新开 Codex 窗口做代码复审。

````text
你现在作为 Codex，复审 AgentHub <任务编号>：<任务名称>。

请先阅读：
1. AGENTS.md
2. docs/b2/task-dispatch/<任务文档>.md
3. <相关 spec>
4. <相关边界 spec>
5. <关键代码文件>
6. <新增实现目录>
7. <新增/修改测试文件>

重点检查：
- <provider / class / public API 是否符合任务要求>
- 是否遵守 BaseAgentAdapter / StreamChunk / ContentBlock / OpenAPI 契约。
- 是否没有越权修改 registry.py / seed_agents.py / frontend / B1 文件。
- 是否正确处理 workspace_path、cwd、路径越界和敏感文件。
- 是否正确映射 start / text_delta / tool_call / tool_result / done / error。
- tool_call / tool_result 是否保持 call_id 配对。
- 外部 runtime / subprocess / SDK / MCP 异常是否映射为标准 error_code。
- timeout 是否会清理子进程或终止等待。
- 测试是否使用 fake SDK / fake subprocess / fake ModelGateway，不默认访问真实网络。
- 真实 runtime smoke 是否 opt-in，不进入默认测试。

建议执行：
```bash
git status --short
git diff -- <code-path> <test-path> docs/ai-collaboration-log.md docs/b2/task-dispatch/<任务文档>.md
git diff --name-only -- shared/openapi.yaml backend/app/agents/base.py backend/app/agents/types.py backend/app/agents/registry.py backend/app/seeds/seed_agents.py frontend

cd backend
python -m pytest <test-path> -q
python -m ruff check <code-path> <test-path>
python -m mypy <code-path>

rg -n "<risk-pattern-1>|<risk-pattern-2>|<risk-pattern-3>" <code-path> <test-path>
```

复审输出格式：

Findings：按严重程度列问题，带文件路径和行号。
Open Questions：仅列阻塞性不确定点。
Verdict：通过 / 需修改。
Test Evidence：列出实际运行命令和结果。
````

## 审阅入口

OpenCode 完成子任务后，B2 将 diff、关键文件或测试结果交给 Codex。Codex 默认按代码审阅模式检查：

- 是否违反目录所有权和模块边界
- 是否违反 OpenAPI、BaseAgentAdapter、ContentBlock 契约
- 是否存在行为 bug、异常路径或流式事件顺序问题
- 测试是否覆盖关键路径
- 是否引入无关重构或不必要依赖
