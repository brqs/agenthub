# B2-10 Orchestrator 失败降级与部分成功输出

任务编号：B2-10
任务名称：Orchestrator 失败降级与部分成功输出
负责人：B2
执行 AI：Claude Code
审阅 AI：Codex
依赖任务：B2-09 Orchestrator 顺序调度与 block_index 重映射

## 任务目标

在 B2-09 的注入式顺序调度基础上，增强 Orchestrator 的失败降级能力：

- 单个子 Agent 失败时，不让整个 Orchestrator SSE 变成 `error`。
- 已经产生的 partial content 必须继续保留在流里。
- 失败任务应输出普通 text 失败说明块，并在 final summary 中标记为 `failed`。
- 后续不依赖失败任务的子任务应继续执行。
- 依赖失败任务的子任务应跳过，并在 final summary 中标记为 `skipped`。
- 所有子任务都失败时，Orchestrator 仍应输出 summary 并以 `done` 结束。
- 任务计划不可用时，仅在提供 fallback adapter 的情况下走单 Agent fallback；否则保留现有 clear `error` 行为。

本任务仍然不做真实 LLM 任务拆解、不接生产 registry、不改 OpenAPI、不改前端。

## 开始前必须确认

1. 先阅读 `AGENTS.md`。
2. 先阅读 `docs/spec/orchestrator.spec.md`，重点看 §8 和 §10.2。
3. 先阅读 `docs/b2-task-dispatch/B2-09-orchestrator-dispatch.md`。
4. 当前代码应已经包含 B2-09 的 `OrchestratorAdapter` 基础顺序调度实现。
5. 如果当前分支不是基于 B2-09 代码，请停止并回报，不要自行重写 Orchestrator。

## 允许修改

- `backend/app/agents/orchestrator.py`
- `backend/tests/test_orchestrator.py`
- `docs/ai-collaboration-log.md`

如实现过程中发现任务文档有明显歧义，可以最小更新：

- `docs/b2-task-dispatch/B2-10-orchestrator-fallback.md`

## 禁止修改

- `backend/app/agents/base.py`
- `backend/app/agents/types.py`
- `backend/app/agents/adapters/**`
- `backend/app/agents/registry.py`
- `backend/app/api/**`
- `backend/app/schemas/**`
- `backend/app/models/**`
- `backend/app/seeds/**`
- `shared/openapi.yaml`
- `frontend/**`
- `docker-compose.yml`
- `.env`
- `backend/.env`

本任务不允许修改 `BaseAgentAdapter.stream()` 签名、`StreamChunk` schema、`ContentBlock` schema 或 OpenAPI。

## 实现要求

### 1. 保持 B2-09 行为不退化

必须保留以下行为：

- Orchestrator 自己的 `start` 开头、`done` 结尾。
- 从 `config` / `default_config` 读取 `tasks`。
- 通过 `sub_adapters` 或 `adapter_factory` 获取子 Agent。
- 按 `priority` 升序顺序调度。
- 每个任务调用前发出 `agent_switch`。
- 子 Agent 的 `start` / `done` 不外发。
- 子 Agent 的 `block_start` / `delta` / `block_end` 必须重映射 `block_index`。
- 子 Agent 的 `error` chunk 不能直接外发，必须转换为普通 text 失败说明块。

### 2. 捕获子 Agent stream 异常

如果 `sub_adapter.stream(...)` 在迭代过程中抛出异常：

1. 不允许异常冒泡到 Orchestrator 外层。
2. 不允许 yield SSE `error`。
3. 已经 yield 出去的子 Agent partial content 保持不变。
4. 使用下一个可用 `block_index` 输出一个 text 失败说明块，例如：

```text
@agent-a failed: upstream connection lost
```

5. 当前任务状态标记为 `failed`。
6. 继续执行后续依赖已满足的任务。

注意：不要吞掉已有 partial block，也不要回滚已经 yield 的内容。

### 3. 捕获 adapter_factory / 子 Adapter 获取异常

如果 `adapter_factory(agent_id)` 抛异常，或返回非 `BaseAgentAdapter`：

1. 当前任务标记为 `failed`。
2. 输出普通 text 失败说明块。
3. 继续执行后续不依赖该任务的任务。

B2-09 已处理部分 `ValueError`，B2-10 需要覆盖更一般的异常路径。

### 4. 子 Agent error chunk 后继续后续任务

B2-09 已把子 Agent `error` chunk 转成 text failure block。

B2-10 必须明确保证：

- 该任务状态为 `failed`。
- Orchestrator 不外发 `error`。
- 后续不依赖该任务的任务继续执行。
- final summary 中准确显示失败和成功任务。

### 5. 依赖失败时跳过任务

如果某任务 `depends_on` 中任一任务状态不是 `succeeded`：

1. 不调用该任务的子 Adapter。
2. 不发出该任务的 `agent_switch`。
3. 将任务状态标记为 `skipped`。
4. 在 final summary 中体现：

```text
- skipped: @agent-b - Frontend UI
```

本任务不强制为 skipped 任务额外输出正文块，summary 中体现即可。

### 6. 所有任务失败也必须 done

只要 Orchestrator 自身能解析任务计划并开始调度，即使所有子任务都失败，也应：

- 输出每个任务的失败说明块。
- 输出 final summary。
- 最后 yield `done`。
- 不 yield `error`。

`error` 只保留给 Orchestrator 自身 fatal error，例如缺少任务计划且没有 fallback adapter。

### 7. 任务计划不可用时的 fallback adapter

B2-10 不实现真实 LLM 任务拆解，但需要为“任务拆解失败 fallback 到单 Agent 模式”预留可测路径。

建议通过 `config` 注入以下测试专用字段：

```python
config = {
    "tasks": "invalid task plan",
    "fallback_agent_id": "claude-code",
    "fallback_adapter": fake_adapter,
}
```

或：

```python
config = {
    "tasks": "invalid task plan",
    "fallback_agent_id": "claude-code",
    "fallback_adapter_factory": factory,
}
```

行为要求：

1. 当 `tasks` 缺失或格式非法，且提供了 fallback adapter 时，不 yield fatal `error`。
2. 输出一个 text block 说明正在 fallback。
3. 可选发出 `agent_switch(from_agent="orchestrator", to_agent=fallback_agent_id, task="fallback")`。
4. 使用原始 `messages` 调用 fallback adapter。
5. 转发并重映射 fallback adapter 的 block 输出。
6. fallback adapter 的 `start` / `done` 不外发。
7. 最终输出 summary 并 yield `done`。

如果没有 fallback adapter，则保持 B2-09 的 clear error 行为，例如：

- `missing_task_plan`
- `invalid_task_plan`
- `missing_sub_adapters`

### 8. 不做的内容

本任务不要实现：

- 真实 LLM function calling / tool use 任务拆解。
- registry / seed 生产接线。
- retry / timeout / rate-limit 策略。
- 并发调度。
- 前端渲染改动。
- OpenAPI 或 schema 改动。

retry / timeout / rate-limit 留给 B2-11。

## 测试要求

在 `backend/tests/test_orchestrator.py` 中补充或调整测试，至少覆盖：

1. `test_orchestrator_continues_after_subagent_stream_exception`
   - 第一个 fake adapter 先 yield partial block，再抛异常。
   - 第二个 fake adapter 正常执行。
   - 断言 partial content 存在。
   - 断言 failure text block 存在。
   - 断言第二个任务输出存在。
   - 断言最终是 `done`，不是 `error`。

2. `test_orchestrator_continues_after_subagent_error_chunk`
   - 第一个 fake adapter yield `error` chunk。
   - 第二个 fake adapter 正常执行。
   - 断言没有外发 `error`。
   - 断言 summary 同时包含 `failed` 和 `succeeded`。

3. `test_orchestrator_skips_tasks_with_failed_dependencies`
   - task-b depends_on task-a。
   - task-a 失败。
   - 断言 task-b 没有 `agent_switch`。
   - 断言 task-b adapter 没有被调用。
   - 断言 summary 包含 `skipped`。

4. `test_orchestrator_all_tasks_fail_still_done`
   - 多个任务都失败。
   - 断言没有外发 `error`。
   - 断言最终 `done`。
   - 断言 summary 列出所有 failed。

5. `test_orchestrator_adapter_factory_exception_is_task_failure`
   - `adapter_factory` 对某个 agent 抛异常。
   - 断言该任务失败说明块存在。
   - 断言后续任务继续执行。

6. `test_orchestrator_fallback_adapter_handles_invalid_task_plan`
   - `tasks` 为非法格式。
   - 注入 fallback adapter。
   - 断言没有 fatal `error`。
   - 断言 fallback adapter 输出被转发。
   - 断言最终 `done`。

已有 B2-09 测试必须继续通过。

## 验证命令

在 `backend` 目录运行：

```bash
conda run --no-capture-output -n LLMAgent python -m pytest tests/test_orchestrator.py -q
conda run --no-capture-output -n LLMAgent ruff check app/agents/orchestrator.py tests/test_orchestrator.py
conda run --no-capture-output -n LLMAgent mypy app/agents/orchestrator.py
conda run --no-capture-output -n LLMAgent python -m pytest -q
```

在仓库根目录运行：

```bash
git diff --check
git status --short
```

## 完成后汇报

完成后请汇报：

1. 修改了哪些文件。
2. 新增了哪些失败降级行为。
3. 哪些失败场景会继续后续任务。
4. 哪些 fatal error 仍会 yield `error`。
5. 测试、ruff、mypy、全量 pytest 结果。
6. 是否修改了任何禁止文件。

不要 commit，不要 push，不要创建 PR。完成后交给 Codex 审阅。
