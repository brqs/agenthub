# B2-09 Orchestrator 顺序调度与 block_index 重映射

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-09
任务名称：Orchestrator 子 Agent 顺序调度与 block_index 重映射

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目 B2 Agent 集成方向的具体子任务。
Codex 负责总览、任务拆解、边界检查和最终代码审阅。
你只完成本任务范围内的 Orchestrator 顺序调度实现和测试，不要扩大到失败降级、并发调度、OpenAPI 或前端改动。

启动前置条件：
1. B2-08 必须已经产出 `docs/b2/spec/orchestrator.spec.md`。
2. 你必须先阅读 B2-08 Spec，并以它为准实现。
3. 如果 `docs/b2/spec/orchestrator.spec.md` 不存在，或其中的 Orchestrator 输入/输出规则不明确，请停止并回报，不要自行补写生产实现。
4. 如果你在 stacked branch 上工作，当前分支应基于 `feat/B2-orchestrator-spec`；如果 B2-08 已合并，则应基于最新 `main`。

项目背景：
现有 `backend/app/agents/orchestrator.py` 仍是 stub，只会输出固定文本。
B2-09 的目标是把它推进到“可用的基础编排器”：
- 根据已注入的任务计划顺序调用子 Agent。
- 在每个子 Agent 开始前发出 `agent_switch`。
- 转发子 Agent 的 `StreamChunk`。
- 重映射子 Agent 的 `block_index`，保证整个 Orchestrator 输出中 block_index 单调递增且不冲突。

本任务不负责：
- LLM function calling / JSON mode 真实任务拆解。
- 子 Agent 失败后继续执行后续任务的完整降级策略。
- 并发调度。
- 数据库查询或 registry DB 接线。
- OpenAPI / ContentBlock / StreamChunk schema 变更。

请先阅读：
1. AGENTS.md
2. docs/b2/spec/orchestrator.spec.md
3. docs/b2/task-dispatch/B2-roadmap.md
4. docs/b2/task-dispatch/B2-08-orchestrator-spec.md
5. docs/api-spec.md 中 Orchestrator SSE / agent_switch 示例
6. docs/tech-architecture.md 中 Orchestrator 章节
7. backend/app/agents/orchestrator.py
8. backend/app/agents/base.py
9. backend/app/agents/types.py
10. backend/app/agents/registry.py
11. backend/app/agents/adapters/mock.py

允许修改：
- backend/app/agents/orchestrator.py
- backend/tests/test_orchestrator.py
- docs/ai-collaboration-log.md

如 B2-08 Spec 明确要求同步说明，也允许最小更新：
- docs/b2/task-dispatch/B2-roadmap.md

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/adapters/**
- backend/app/agents/registry.py
- backend/app/api/**
- backend/app/schemas/**
- backend/app/models/**
- backend/app/seeds/**
- shared/openapi.yaml
- frontend/**
- docker-compose.yml
- .env
- backend/.env

本任务不允许修改 BaseAgentAdapter.stream() 签名、StreamChunk schema、ContentBlock schema 或 OpenAPI。

实现目标：
1. 保持 `OrchestratorAdapter` 继承 `BaseAgentAdapter`。
2. 保持 `stream()` 签名不变。
3. 从 `config` 或 `self.default_config` 中读取 B2-08 Spec 定义的任务计划。
4. 从外层注入的 adapter factory / sub_adapters 中获取子 Agent adapter。
5. 不直接访问数据库。
6. 不直接 import 具体 Provider SDK。
7. 按任务顺序串行调用子 Agent。
8. 每个子 Agent 调用前 yield `agent_switch`。
9. 转发子 Agent 的 `block_start` / `delta` / `block_end` 事件，并重映射 `block_index`。
10. Orchestrator 自己的 planning block 从 `block_index=0` 开始。
11. 子 Agent 输出从下一个可用 block_index 开始，多个子 Agent 之间不能冲突。
12. 最后输出一个 summary text block，然后 yield `done`。

建议的配置注入形态：
以 B2-08 Spec 为准。若 Spec 尚未定义更具体方案，可使用仅测试可用的内部形态：

```python
config = {
    "tasks": [
        {
            "task_id": "task-1",
            "agent_id": "agent-a",
            "title": "Backend API",
            "instruction": "Implement API",
        },
        {
            "task_id": "task-2",
            "agent_id": "agent-b",
            "title": "Frontend UI",
            "instruction": "Implement UI",
        },
    ],
    "sub_adapters": {
        "agent-a": fake_adapter_a,
        "agent-b": fake_adapter_b,
    },
}
```

注意：
- `sub_adapters` 只用于当前 B2-09 的单元测试和内部注入，不写入数据库。
- 不要为了生产接线修改 B1 SSE、registry 或 seed。
- 如果 B2-08 Spec 指定了 `adapter_factory`，则优先按 Spec 实现。

事件流要求：
正常路径至少应满足：
1. `start`
2. planning `block_start(text)` / `delta` / `block_end`
3. `agent_switch(from_agent="orchestrator", to_agent=<agent_id>, task=<task title or instruction>)`
4. 子 Agent block 事件，block_index 已重映射
5. 下一个 `agent_switch`
6. 下一个子 Agent block 事件，block_index 不冲突
7. summary `block_start(text)` / `delta` / `block_end`
8. `done(total_blocks=<实际 block 数>)`

block_index 重映射规则：
1. Orchestrator planning block 固定占用 index 0。
2. 子 Agent 的所有 block_index 必须映射到全局 index。
3. 同一个子 Agent 内，相同原始 block_index 必须映射到同一个全局 block_index。
4. 不同子 Agent 的 block_index 即使原始值相同，也必须映射到不同全局 block_index。
5. `delta` / `block_end` 的 index 必须和对应 `block_start` 保持一致。
6. `start` / `done` / `agent_switch` / `error` 等无 block_index 事件不参与映射。

测试要求：
新增 `backend/tests/test_orchestrator.py`，至少覆盖：

1. `test_orchestrator_emits_planning_agent_switch_subagent_and_summary`
   - 使用两个 fake sub adapters。
   - 断言事件顺序包含 planning block、两次 agent_switch、两个子 Agent 输出、summary、done。

2. `test_orchestrator_remaps_block_indices_without_collisions`
   - 两个 fake sub adapters 都输出原始 block_index=0。
   - 断言最终输出中的 block_start index 不重复。
   - 断言 delta/block_end 使用重映射后的 index。

3. `test_orchestrator_preserves_subagent_metadata_and_delta_fields`
   - 子 Agent 输出 code block / text block。
   - 断言 block_type、metadata、text_delta、code_delta 被保留。

4. `test_orchestrator_does_not_require_database`
   - 不创建 DB session。
   - 只用 fake adapters 和 config 注入即可运行。

5. `test_orchestrator_requires_task_plan_or_emits_clear_error`
   - 缺少 tasks 或 sub_adapters 时，不抛出未处理异常。
   - 可以 yield 标准 `StreamChunk(event_type="error", error_code=...)`。
   - 不要求实现 B2-10 的“部分成功后继续”策略。

实现约束：
- 不要修改其他 Adapter。
- 不要复制 Claude/OpenAI/Custom 的 provider 流式逻辑。
- 不要在 Orchestrator 中访问数据库。
- 不要在 Orchestrator 中读取 `.env`。
- 不要引入新依赖。
- 不要新增 ContentBlock 类型。
- 不要新增 StreamChunk 字段。
- 不要实现并发调度。
- 不要实现复杂 retry/timeout 策略，该内容属于 B2-10/B2-11。

验证命令：
在 `backend` 目录运行：

conda run --no-capture-output -n LLMAgent python -m pytest tests/test_orchestrator.py -q
conda run --no-capture-output -n LLMAgent ruff check app/agents/orchestrator.py tests/test_orchestrator.py
conda run --no-capture-output -n LLMAgent mypy app/agents/orchestrator.py

如果你修改了 roadmap 或协作日志，也在仓库根目录运行：

git diff --check
git status --short

完成后请汇报：
1. 修改了哪些文件
2. Orchestrator 如何读取任务计划和子 Adapter
3. `agent_switch` 的输出时机
4. `block_index` 重映射规则如何实现
5. 哪些失败场景留给 B2-10
6. 是否修改了任何共享契约，预期答案应为“没有”
7. 运行了哪些测试、ruff、mypy，结果如何
8. git status --short

本任务完成后不要 commit，不要 push，不要创建 PR。
请先把 diff 和验证结果交给 Codex 进行最终审阅。
```
