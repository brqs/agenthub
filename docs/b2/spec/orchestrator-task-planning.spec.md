# Orchestrator Task Planning Spec

> 定义 Orchestrator 的任务规划、任务分配和 planner 降级规则。子任务执行流转、事件聚合和失败状态汇总见 [orchestrator.spec.md](orchestrator.spec.md)。
>
> 版本：v1.1
> 最后更新：2026-05-29

---

## 1. 范围

本文件只覆盖 Orchestrator 从用户请求到 `list[SubTask]` 的规划过程：

- direct answer 短路判定。
- 显式 `config.tasks` 解析。
- 直接多 Agent mention 路由。
- LLM planner 调用、输出解析和校验。
- preview/deploy/port 服务任务过滤。
- planner 失败后的 direct answer、template、fallback adapter、fatal error 降级顺序。

本文件不覆盖：

- 子 Agent stream 调度。
- `block_index` 和 `tool_call.call_id` 重映射。
- 子 Agent `heartbeat` / `error` 事件处理。
- execution summary 输出。
- workspace artifact 成功判定。

---

## 2. 输入来源

规划层读取：

| 输入 | 来源 | 说明 |
|---|---|---|
| `messages` | `BaseAgentAdapter.stream()` | 只把最新 user message 作为 active request。 |
| `system_prompt` | `BaseAgentAdapter.stream()` | 合并进 planner/direct answer system prompt。 |
| `config.tasks` | runtime config | 显式任务计划，优先级最高。 |
| `config.available_agents` | runtime config | planner 可用 Agent 描述，优先于 managed ids。 |
| `config.managed_agent_ids` | registry/default config | Orchestrator 管理的子 Agent 白名单。 |
| `config.default_sub_agents` | legacy config | `managed_agent_ids` 的兼容别名。 |
| `config.planner_gateway` | runtime config | 注入式 planner gateway。 |
| `config.orchestrator_llm_config` | runtime config | planner 模型参数。 |
| `config.answer_gateway` | runtime config | direct answer gateway。 |
| `config.fallback_adapter` | runtime config | 规划失败后的单 Agent fallback。 |
| `config.fallback_adapter_factory` | runtime config | 延迟创建 fallback adapter。 |

---

## 3. 总体解析顺序

Orchestrator 的任务解析顺序固定，前一个分支命中后不会继续尝试后续分支：

1. Direct answer 短路。
2. 显式 `config.tasks`。
3. 直接多 Agent mention 路由。
4. LLM planner。
5. Legacy template fallback。

规划失败后的降级顺序：

1. `planner_fallback_to_template is True` 时先回退 template。
2. planner 协议错误可按配置回退 direct answer。
3. 有 fallback adapter 时回退单 Agent fallback。
4. 都不可用时返回 Orchestrator fatal `error`。

---

## 4. Direct Answer 短路

在以下条件全部满足时，Orchestrator 不创建任务、不调用子 Agent runtime，只通过 `answer_gateway` 或 ModelGateway 直接回答：

- `config.tasks` 不存在。
- 最新用户消息没有显式提到任何 managed 子 Agent。
- 最新用户消息命中身份、模型、能力、职责等 meta question marker。
- 最新用户消息不命中生成、创建、实现、修复、部署、review、coordinate 等 task intent marker。

这个分支用于“你是谁”“你是什么模型”“你能做什么”等普通问答。

direct answer 使用：

- `answer_gateway` 优先。
- 否则创建 ModelGateway。
- backend 取 `answer_model_backend`，再取 `model_backend`，默认 `claude`。
- 模型参数来自 `orchestrator_answer_config`，并兼容顶层 `model`、`max_retries`、`request_timeout_seconds`。

---

## 5. 显式 `config.tasks`

如果 `config.tasks` 存在，Orchestrator 直接解析它：

1. `tasks` 必须是非空 list。
2. 每个 task 必须是 object，并满足 `SubTask` 字段校验。
3. `task_id` 必须唯一。
4. 解析后按 `priority` 升序排序。

显式任务不会再走 direct multi-agent routing、LLM planner 或 template fallback。

当前 `SubTask` 字段见 [orchestrator.spec.md §3](orchestrator.spec.md#3-子任务结构)。

`expected_output` 语义：

- 可继续作为人类可读的输出描述。
- 如果包含明确 workspace-relative path，如 `snake.html`、`src/App.tsx`，执行层可将其作为 artifact path 候选。
- `expected_output` 不应要求 runtime 启动 preview/deploy/server。
- planner 不需要保证 path 一定存在；存在性由 Orchestrator 执行层在任务结束后只读校验。

---

## 6. 直接多 Agent 路由

如果没有显式 `tasks`，Orchestrator 会检查最新用户消息是否显式提到了两个或更多 managed 子 Agent。

支持的内置别名包括：

| Agent | 别名示例 |
|---|---|
| `claude-code` | `@claude-code`, `claude code`, `claudecode` |
| `codex-helper` | `@codex-helper`, `codex helper`, `codex` |
| `opencode-helper` | `@opencode-helper`, `open code`, `opencode` |
| `web-designer` | `@web-designer`, `web designer` |

命中后会按 mention 在消息中的出现顺序创建一组 `direct-*` 任务：

- `title="Direct request"`。
- `include_history=False`。
- 如果用户消息中有引号内容，优先把引号内文本作为子 Agent 的 direct message。
- 子 Agent instruction 明确要求“只回答这条 direct request，不要联系、调用或模拟其他 agents/CLIs/APIs”。

这个分支用于“分别问 claude-code、codex-helper 你是什么模型”这类对比性直接问答。

---

## 7. LLM Planner

如果没有显式任务、没有直接多 Agent 路由，并且满足任一条件，则启用 LLM planner：

- `planner_gateway` 存在。
- `llm_planning is True`。
- `orchestrator_llm_config` 是 object。

planner 流程：

1. 可用 Agent id 优先来自 `available_agents`，否则来自 `managed_agent_ids/default_sub_agents`。
2. planner gateway 优先使用注入的 `planner_gateway`，否则创建 ModelGateway。
3. ModelGateway backend 取 `planner_model_backend`，再取 `model_backend`，默认 `claude`。
4. planner prompt 要求只使用白名单 agent id。
5. 有 tool support 时必须调用 `submit_task_plan`。
6. 没有 tool payload 时，从文本中解析 JSON。
7. planner 输出必须解析为 `{"tasks": [...]}` 或 tasks array。
8. Orchestrator 校验 `agent_id`、`depends_on` 和 task schema。
9. 纯 preview/deploy/port/server/service 任务会被过滤，除非该任务被其他任务依赖，或任务内容包含生成 artifact 的 marker。

`available_agents` 描述要求：

- 每个条目必须能明确映射到一个可调度 `agent_id`。
- 推荐包含：`id`、`name`、`capabilities`、`best_for`、`limitations`。
- planner prompt 应把这些描述传给模型，要求只选择白名单 id。
- 示例：

```json
{
  "id": "codex-helper",
  "name": "Codex Helper",
  "capabilities": ["coding", "sandbox"],
  "best_for": "code implementation and command-backed verification",
  "limitations": "must not start preview/deploy servers"
}
```

依赖规划要求：

- 如果后续任务需要消费前序任务结果，planner 必须填写 `depends_on`。
- 依赖只能引用同一计划内已存在的 `task_id`。
- 依赖不表达并发；当前 Orchestrator 仍严格顺序执行。
- 执行层会把依赖任务结果注入后续任务上下文，planner 不需要把前序结果复制进 instruction。

planner config：

- 默认 `temperature=0`。
- 默认 `max_tokens=2048`。
- 默认 `tool_choice={"type": "auto"}`。
- 兼容顶层 `model`、`max_retries`、`request_timeout_seconds`。

---

## 8. Preview / Deploy Guard

planner guard：

- 不得创建启动、部署、预览、管理长驻端口服务的子任务。
- 用户要求 port preview/deploy 时，只规划文件生成和内容验证。
- 平台 preview/deploy 由 AgentHub 平台层处理，不由 runtime agent 或 Orchestrator 启动。

过滤规则：

- 命中 `preview/deploy/port/server/service/808/预览/部署/端口/服务` 等 marker 的任务，会被识别为候选端口服务任务。
- 如果任务同时命中 `create/generate/write/implement/build/file/artifact/html/创建/生成/编写/实现/文件/产物` 等 artifact marker，则保留为文件生成任务。
- 如果该任务被其他任务依赖，也会保留，避免破坏 planner 输出的依赖图。
- 如果过滤后没有任何任务，保留原始任务列表，避免 planner 输出被全部清空。

---

## 9. Planner 失败处理

LLM planner 抛出 `ValueError` 后，Orchestrator 按以下顺序处理：

1. 如果 `planner_fallback_to_template is True`，回退到 template 任务。
2. 否则包装为 `PlannerResolutionError`。
3. 如果 `direct_answer_on_planner_failure is True` 且错误属于 planner 协议错误，则走 direct answer。
4. 如果配置了 fallback adapter，则走单 Agent fallback。
5. 否则发出 Orchestrator fatal `error`。

注意：本节只描述“规划失败”的 fallback。v1.2 的 per-task fallback 属于执行层能力，用于单个子任务 `failed` 或 `artifact_missing` 后的重试，见 [orchestrator.spec.md](orchestrator.spec.md)。

planner 协议错误包括：

- invalid JSON。
- 空 planner 输出。
- planner stream `error`。

---

## 10. Legacy Template Fallback

未启用 LLM planner 时，或 planner 配置允许 fallback 时，Orchestrator 使用 template 生成任务：

1. 如果用户显式提到两个或更多 managed 子 Agent，生成 direct tasks。
2. 否则取前 3 个 managed agents，生成：
   - `Analyze request`
   - `Produce solution`
   - `Review and refine`
3. 若没有可用 managed agents，返回 `missing_task_plan` fatal error 或触发 fallback adapter。

template fallback 是历史兼容路径，不应替代 LLM planner 的长期规划能力。

---

## 11. 验收标准

- 普通身份/模型/能力问答走 direct answer，不启动子 Agent runtime。
- 显式 `config.tasks` 优先于所有自动规划。
- 显式提到两个或更多 managed agents 时生成 direct tasks。
- direct tasks 使用 `include_history=False`。
- LLM planner 只允许输出白名单 agent id。
- planner 输出的依赖必须引用已存在 task id。
- planner 不规划 preview/deploy/server 长驻端口任务。
- planner 失败按 template、direct answer、fallback adapter、fatal error 的配置顺序降级。
- 没有 managed agents 且没有 fallback 时返回清晰 fatal error。
- planner 会在需要消费前序结果时填写 `depends_on`。
- `expected_output` 中的明确 artifact path 可被执行层用于 artifact 存在性校验。

---

## 12. 相关文件

| 文件 | 说明 |
|---|---|
| [orchestrator.py](../../../backend/app/agents/orchestrator.py) | 规划分支入口和 task parsing。 |
| [orchestrator_planner.py](../../../backend/app/agents/orchestrator_planner.py) | LLM planner helper。 |
| [orchestrator.spec.md](orchestrator.spec.md) | Orchestrator 主行为契约和执行流转。 |
| [model-gateway.spec.md](model-gateway.spec.md) | ModelGateway backend 与调用边界。 |
| [workspace-artifact-preview.spec.md](workspace-artifact-preview.spec.md) | preview/deploy 平台边界。 |
