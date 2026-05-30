# Orchestrator Tool Calling Agent Spec

> 定义将 Orchestrator 从“程序化多 Agent 调度器 + LLM planner/replanner”升级为“具备原生 tool calling 的 autonomous manager agent”的技术设计。
>
> 状态：v1 implemented in current codebase
> 最后更新：2026-05-30

---

## 1. 背景

当前 Orchestrator 的核心动作不是 tool calling，而是后端代码控制的任务流：

```text
用户请求
-> platform fact / direct answer shortcut
-> planner 生成 SubTask
-> 后端按任务图调用 sub_adapter.stream()
-> 收集 TaskResult / TaskAttempt
-> ReAct replanner 输出严格 JSON action
-> Orchestrator structured memory 写入 run/task/attempt/event
-> 继续执行或结束
```

它已经能调度真实 `claude-code`、`codex-helper`、`opencode-helper`，但这种调度是后端程序调用 adapter，不是模型通过 `tool_call` 自主决定下一步。

更典型的 autonomous agent 应该是：

```text
模型观察上下文
-> tool_call(dispatch_agent)
-> 后端执行真实子 agent
-> tool_result(observation)
-> 模型继续 tool_call(read_artifact / validate_html / dispatch_agent)
-> 最终无 tool_call，输出总结
```

当前代码已经具备：

- `ModelGateway.stream(..., tools=list[ToolSpec])`。
- BuiltinAgent 的 `AgentLoop` model/tool 模式参考。
- Orchestrator 的 `_run_task()`、`TaskResult`、`TaskAttempt`、artifact path 存在性检查。
- Orchestrator structured memory writer，从 stream/service 层通过 `config["orchestrator_memory_writer"]` 注入。
- stream 层已在 Orchestrator 请求前注入 `Previous Orchestrator structured memory`。

本 spec 设计 Orchestrator 自己可调用的 tool 集合和 tool loop，同时复用现有 `ToolSpec`、`StreamChunk.tool_call/tool_result`、子 adapter、workspace guard、`_run_task()` 和结构化 memory。

---

## 2. 目标

让 Orchestrator 获得原生 tool calling 能力：

1. 模型可以通过 `dispatch_agent` 调用当前群聊内真实 agent。
2. 模型可以通过 workspace tools 检查产物，而不是只能派子 agent 检查。
3. 模型可以根据 tool result 动态决定下一步，而不是只输出 planner/replanner JSON。
4. tool result 自动进入本轮上下文，供后续模型回合使用。
5. 子 agent 的真实 SSE 输出仍然透传给用户，保持可观察性。
6. 不改 `BaseAgentAdapter`、`StreamChunk`、SSE wire contract。

v1 范围：

- `dispatch_agent`
- `inspect_workspace`
- `read_artifact`
- `validate_html`
- `ask_user`

非目标：

- 不让 Orchestrator 任意执行 shell。
- v1 不实现 `run_test` / 通用 bash；测试命令 runner 进入 v1.1 或后续版本。
- 不替换 Claude Code / Codex / OpenCode 的真实 runtime。
- 不实现并行 tool execution。
- 不暴露模型 hidden thought / chain of thought。
- 不新增前端交互协议；`ask_user` v1 只通过最终文本请求用户补充。

---

## 3. 执行模式

新增可选模式：

| 字段 | 类型 | 默认 | 说明 |
|---|---:|---:|---|
| `orchestrator_tool_calling_enabled` | bool | `false` | 是否启用 Orchestrator tool loop。 |
| `orchestrator_tool_trace_visible` | bool | `true` | 是否向用户显示 tool_call/tool_result。 |
| `orchestrator_tool_max_iterations` | int | `12` | tool loop 最大轮数，建议校验 `1..50`。 |
| `orchestrator_tool_result_max_chars` | int | `4000` | 单个 tool result 注入模型上下文的最大字符数。 |
| `orchestrator_tool_read_max_bytes` | int | `65536` | `read_artifact` 最大读取字节数。 |

入口顺序：

1. `platform_fact` shortcut 保持最高优先级。
2. `direct_answer` shortcut 保持不变。
3. 如果显式传入 `config.tasks`，继续走现有静态/ReAct task executor，保证测试和受控任务兼容。
4. 如果 `orchestrator_tool_calling_enabled=true`，进入 tool loop。
5. 否则才调用 `_resolve_tasks()`，走现有 planner / ReAct / static flow。

重要：tool loop 分支必须放在 `_resolve_tasks()` 之前。否则启用 tool calling 后仍会先触发 LLM planner，违背“模型通过 tools 自主决定下一步”的目标。

seed 默认建议先保持 `orchestrator_tool_calling_enabled=false`，等 smoke 通过后再在开发环境或特定 agent config 中开启。

---

## 4. Tool Loop

建议新增模块：

```text
backend/app/agents/orchestrator_tool_loop.py
backend/app/agents/orchestrator_tools.py
```

loop 形态复用 BuiltinAgent 的 model/tool 模式，但工具执行器是 Orchestrator 专属：

```text
OrchestratorAdapter.stream() 已经 yield start
current_messages = messages  # stream 层已注入 structured memory

for iteration in 1..max_iterations:
  model_gateway.stream(current_messages, tools=orchestrator_tools)
  collect tool_call chunks
  pass through visible assistant text
  if no tool_call:
    return final text/blocks to adapter

  for each tool_call sequentially:
    validate tool name and arguments
    yield normalized tool_call
    execute tool sequentially
    yield tool_result
    append tool result to current_messages

return final chunks to OrchestratorAdapter
OrchestratorAdapter.stream() 负责 yield done/error
```

tool loop helper 应该像 `run_react_loop()` 一样作为内部 generator：

```python
async def run_orchestrator_tool_loop(...) -> AsyncIterator[tuple[StreamChunk, int]]:
    ...
```

它不应再次发送 `start`，也不应绕过 `OrchestratorAdapter.stream()` 的最终 `done/error` 语义。

模型 backend：

- 默认使用 `planner_model_backend`。
- 缺省回退 `model_backend`。
- 再缺省回退 `claude`。
- 模型 config 复用 `orchestrator_llm_config`。

system prompt 约束：

- 只输出用户可见的简短进度或最终答案。
- 不输出 hidden reasoning。
- 需要执行时必须调用 tools。
- 不要模拟子 agent 结果。
- 不要调度群聊外 agent。
- 不要请求 preview/deploy/server 长驻命令。
- 最终回答必须基于 tool results。
- 当前 `messages` 里可能已经包含 `Previous Orchestrator structured memory`，模型应把它当作历史事实摘要，但最终判断仍以本轮 tool results 为准。
- `tool_specs` 入参继续透传给子 agent；Orchestrator 自身 tools 由 `orchestrator_tools.py` 内部定义，不从外部请求直接接受任意 tool schema。

---

## 5. Orchestrator Tool Set

### 5.1 `dispatch_agent`

调用当前群聊内真实子 agent。

Schema：

```json
{
  "name": "dispatch_agent",
  "description": "Dispatch a task to one available AgentHub group member and return its observed result.",
  "parameters": {
    "type": "object",
    "properties": {
      "task_id": {"type": "string"},
      "agent_id": {"type": "string"},
      "title": {"type": "string"},
      "instruction": {"type": "string"},
      "expected_output": {"type": "string"},
      "include_history": {"type": "boolean"}
    },
    "required": ["agent_id", "title", "instruction"]
  }
}
```

执行规则：

- `agent_id` 必须来自 `available_agents` 或 overridden `managed_agent_ids`。
- 禁止调度 `orchestrator` 自身。
- `task_id` 可选；缺省生成 `tool-<iteration>-<call_index>`。
- 内部转换为 `SubTask`，复用现有 `_run_task()`。
- tool loop 必须持有一个共享 `OrchestratorRunContext`；`dispatch_agent` 执行完成后从 `run_context.results[task_id]` 读取 `TaskResult` 生成 observation。
- 如果存在 `orchestrator_memory_writer`，`_run_task()` 会复用当前 `memory_run_id` 写入 task/attempt/result；tool loop 不应重复写同一个 dispatch result。
- 子 agent `start/done` 仍吞掉。
- 子 agent text block 继续透传。
- 子 agent `tool_call/tool_result` 继续透传，但 call id 必须加 dispatch 前缀，避免和 Orchestrator tool call 冲突。
- 执行结束后返回结构化 observation：

```json
{
  "task_id": "create-html",
  "agent_id": "opencode-helper",
  "state": "succeeded",
  "text_preview": "Created index.html.",
  "tool_summaries": ["write_file ok path=index.html"],
  "artifact_paths": ["index.html"],
  "missing_artifact_paths": [],
  "error": null
}
```

### 5.2 `inspect_workspace`

查看 workspace 文件树。

Schema：

```json
{
  "name": "inspect_workspace",
  "description": "List workspace files and directories with metadata.",
  "parameters": {
    "type": "object",
    "properties": {
      "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
      "path": {"type": "string"}
    }
  }
}
```

规则：

- `workspace_path` 缺失时返回 tool error，不 fallback 到宿主机路径。
- 只允许 workspace-relative path。
- 默认 `max_depth=4`。
- 不读取文件内容。
- 输出路径、类型、大小和修改时间。
- 跳过 `.git`、`.env`、`.ssh`、`secrets` 等敏感路径。

### 5.3 `read_artifact`

读取 workspace 内产物内容。

Schema：

```json
{
  "name": "read_artifact",
  "description": "Read a text artifact from the workspace.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string"},
      "max_bytes": {"type": "integer", "minimum": 1}
    },
    "required": ["path"]
  }
}
```

规则：

- `workspace_path` 缺失时返回 tool error。
- 路径必须在 workspace 内。
- 只读 UTF-8 文本。
- 默认最多读取 `orchestrator_tool_read_max_bytes`。
- 超出预算时返回截断内容和 `truncated=true`。
- 不读取敏感路径。

### 5.4 `validate_html`

对 HTML artifact 做轻量静态验证。

Schema：

```json
{
  "name": "validate_html",
  "description": "Validate that an HTML artifact contains expected static elements.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string"},
      "required_title": {"type": "string"},
      "require_input": {"type": "boolean"},
      "require_button": {"type": "boolean"},
      "require_script": {"type": "boolean"},
      "required_text": {
        "type": "array",
        "items": {"type": "string"}
      }
    },
    "required": ["path"]
  }
}
```

规则：

- `workspace_path` 缺失时返回 tool error。
- v1 只做静态验证，不启动浏览器。
- 检查 title、input、button、script 和 required text。
- 输出 `passed`、`checks`、`errors`。
- 动态点击验证不在 v1 内；如需真实浏览器行为，后续新增 `validate_browser_behavior`。

### 5.5 `run_test`（v1.1+，不在 v1 默认范围）

`run_test` 是后续增强，不进入第一版 Orchestrator tool calling v1。原因：

- 当前已有 external runtime 和 BuiltinAgent 能运行受限命令。
- Orchestrator 自身直接运行命令需要额外 permission manager、命令 allowlist、进程树清理和敏感信息 redaction。
- 先实现 `dispatch_agent`、workspace inspect/read、`validate_html` 可以验证 tool loop 主链路，风险更小。

执行受限测试命令。

Schema：

```json
{
  "name": "run_test",
  "description": "Run a safe test command in the workspace.",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {"type": "string"},
      "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120}
    },
    "required": ["command"]
  }
}
```

规则：

- 不是通用 bash。
- 命令必须匹配 allowlist，例如：
  - `pytest`
  - `python -m pytest`
  - `npm test`
  - `pnpm test`
  - `node <workspace-relative-js-file>`
- 禁止：
  - `npm run dev`
  - `pnpm dev`
  - `vite --host`
  - `python -m http.server`
  - 后台任务、管道到 shell、重定向到敏感路径、`sudo`、网络服务。
- cwd 固定 workspace。
- env 使用安全 allowlist，不透出 API key。
- stdout/stderr 截断到 tool result budget。

### 5.6 `ask_user`

请求用户补充信息。

Schema：

```json
{
  "name": "ask_user",
  "description": "Stop and ask the user for missing information.",
  "parameters": {
    "type": "object",
    "properties": {
      "question": {"type": "string"},
      "reason": {"type": "string"}
    },
    "required": ["question"]
  }
}
```

v1 规则：

- 不新增交互式 SSE event。
- tool result 以 JSON 字符串或 metadata 返回 `needs_user_input=true`。
- Orchestrator 下一轮模型调用应输出最终文本，请用户补充。
- loop 结束为正常 `done`，不是 error。

---

## 6. SSE 与消息持久化

Orchestrator tool loop 复用现有事件：

| 事件 | 行为 |
|---|---|
| `tool_call` | Orchestrator 模型发起工具调用时透传。 |
| `tool_result` | 工具执行结束后透传。 |
| `agent_switch` | `dispatch_agent` 执行前透传。 |
| 子 agent text blocks | 继续重映射 block index 后透传。 |
| 子 agent tool events | 继续透传并重写 call id。 |
| fatal loop error | 发 `error`。 |
| 正常结束 | 发 `done`。 |

call id 规则：

```text
orchestrator tool call: orch.<iteration>.<call_index>
child agent tool call: orch.<iteration>.<call_index>.child.<child_call_id>
```

如果模型提供 call id，仍需加 `orch.` 前缀，避免与子 agent 冲突。

`orchestrator_tool_trace_visible=false` 时：

- 可以隐藏 Orchestrator 自身的 `tool_call/tool_result`。
- `dispatch_agent` 子 agent 的用户可见输出仍保留。
- memory 和 model context 仍必须收到 tool result。

---

## 7. Context 与 Memory

tool loop 的上下文由三层组成：

1. `ContextBuilder` 提供的会话历史。
2. stream 层已注入的 `Previous Orchestrator structured memory` 跨轮结构化编排摘要。
3. 当前 tool loop 内累积的 tool results。

每个 tool result 都要追加到 `current_messages`，格式必须简短、事实化：

```text
Tool dispatch_agent (orch.1.1) ok:
task_id=create-html
agent_id=opencode-helper
state=succeeded
artifacts=index.html
text=Created index.html.
```

当前 Orchestrator Memory Store 已实现。tool loop 应按以下规则写入：

- 进入 tool loop 后、第一次模型调用前创建一个 run，`plan_source="tool_calling"`，初始 tasks 可以为空。
- `dispatch_agent` 对应 task/attempt/result 通过 `_run_task()` 写入 run memory。
- `inspect_workspace/read_artifact/validate_html/ask_user` 写入 `orchestrator_run_events`。
- `run_test` 在 v1.1+ 实现后也写入 `orchestrator_run_events`。
- final answer 写入 run final summary。
- tool loop fatal error 如果 run 已创建，应调用 `finish_run(status="error", final_summary=...)` 后再向 SSE 发 `error`。

如果 memory store 不存在：

- tool loop 仍可运行。
- 只依赖当前消息持久化和 `ConversationMemory` 文本压缩。

---

## 8. 权限与安全边界

Orchestrator tool calling 必须比 external runtime 更保守。

### 8.1 Agent 调度权限

- 只能调度当前 conversation group 里的 `available_agents`。
- 单聊没有 group members 时，才允许回退 seed/config 中的 `managed_agent_ids`。
- 禁止调度 `orchestrator`。
- 禁止模型通过参数覆盖 adapter config、CLI args、env、API key。

### 8.2 Workspace 权限

- 所有 file tools 都必须限制在 `workspace_path` 内。
- 禁止绝对路径、drive path、`..`、symlink escape。
- 禁止 `.git`、`.env`、`.ssh`、`secrets` 等路径。
- 读取大小和输出大小必须有预算。

### 8.3 Command 权限（v1.1+）

v1 不提供命令执行工具。本节只适用于后续 `run_test` 实现。

- `run_test` 是 allowlist command runner，不是 shell。
- 不通过 `shell=True` 执行。
- 不允许 preview/deploy/server/long-running 命令。
- 超时必须 kill process tree。
- stderr/stdout 必须 redaction。

### 8.4 Prompt 安全

system prompt 必须明确：

- tool results 是事实来源。
- 不得伪造子 agent 执行结果。
- 不得声称执行了未调用的 tool。
- 不得输出 secrets。
- 不得提供绕过 workspace 和 command policy 的建议。

---

## 9. 与现有 Orchestrator ReAct 的关系

当前 ReAct 是 task-graph ReAct：

```text
execute SubTask
-> observation
-> replanner JSON add/update/skip/finish
```

Tool Calling Orchestrator 是 tool-loop ReAct：

```text
model tool_call
-> execute tool
-> tool_result
-> model next action
```

两者关系：

- v1 并存，不互相删除。
- `orchestrator_tool_calling_enabled=true` 时，普通任务优先进入 tool loop。
- 显式 `config.tasks` 继续走现有 executor。
- tool loop 内部的 `dispatch_agent` 复用 `_run_task()` 和 `TaskResult`，避免重复实现子 agent 流转。
- 现有 ReAct 可以作为稳定 fallback。

长期方向：

- tool loop 稳定后，可将 `orchestrator_react.py` 的 JSON replanner 能力收敛到 tool loop。
- task graph 仍可作为 memory/summary 视图存在，而不是执行入口。

---

## 10. 实现入口建议

建议新增：

- `backend/app/agents/orchestrator_tool_loop.py`
- `backend/app/agents/orchestrator_tools.py`
- `backend/tests/test_orchestrator_tool_calling.py`

建议修改：

- `backend/app/agents/orchestrator.py`
  - 增加 tool calling 分支。
  - 分支位置在 platform fact / direct answer / explicit `config.tasks` 之后、`_resolve_tasks()` 之前。
  - 将 `_run_task()`、block remap、summary/format callbacks 传给 tool loop。
- `backend/app/agents/config_validation.py`
  - 校验新增 config 字段。
- `backend/app/schemas/agent.py`
  - 增加新增 config 字段。
- `shared/openapi.yaml`
  - 同步 config 字段。
- `backend/app/seeds/seed_agents.py`
  - 先保留默认关闭，或仅 dev seed 开启。

实现顺序：

1. 定义 tool specs 和参数校验。
2. 实现 workspace `inspect_workspace`、`read_artifact`、`validate_html`、`ask_user`。
3. 实现 `dispatch_agent`，复用 `_run_task()`。
4. 实现 Orchestrator tool loop。
5. 接入 `OrchestratorAdapter.stream()`。
6. 接入 memory writer events。
7. 补 config/schema/openapi/seed。
8. 补测试和真实 agent smoke。

`run_test` 单独作为 v1.1+ 任务，不阻塞 v1 tool loop 合并。

---

## 11. 测试计划

### 11.1 单元测试

- 模型输出 `dispatch_agent` 后，真实 sub adapter 被调用。
- `dispatch_agent` 只能选择 available agents，群聊外 agent 被拒绝。
- `dispatch_agent` 子 stream 的 text/tool events 被正确 remap。
- `read_artifact` 拒绝 workspace 外路径和敏感路径。
- `inspect_workspace` 不输出敏感文件。
- `validate_html` 能识别 title/input/button/script。
- `ask_user` 产生 `needs_user_input` tool result，并让最终回答请求用户补充。
- `orchestrator_tool_trace_visible=false` 时隐藏 Orchestrator 自身 tool cards，但保留子 agent 输出。
- tool loop 超过 `orchestrator_tool_max_iterations` 后返回 `loop_max_iterations`。
- memory writer 存在时，tool loop 创建 `plan_source="tool_calling"` run。
- `dispatch_agent` task/attempt/result 写入 memory，workspace/read/validate/ask_user 写入 event。

### 11.2 Stream/API 测试

- group conversation 中启用 tool calling 后，Orchestrator 使用 `dispatch_agent` 调用当前群聊 agent。
- SSE 中出现标准 `tool_call/tool_result/agent_switch`。
- message content 持久化后 tool blocks 配对完整，无 orphan tool call。
- 不调度 `web-designer` 等群外 agent。
- direct answer/platform fact 仍然短路，不进入 tool loop。

### 11.3 真实 Agent Smoke

建议任务：

```text
@orchestrator 请用 tool calling 编排当前群聊完成：
1. 派一个 agent 创建 tool-loop-smoke.html。
2. 读取该文件。
3. 验证 HTML 包含 title、input、button、script。
4. 如果验证失败，派另一个 agent 修复。
5. 最终总结实际调用了哪些 tool、哪个 agent 生成了文件、验证结果是什么。
```

验收：

- 至少一次 `dispatch_agent` 调用真实 `opencode-helper` / `codex-helper` / `claude-code`。
- 至少一次 `read_artifact` 或 `validate_html` 由 Orchestrator 自己执行。
- 最终 summary 基于 tool results，不伪造未执行结果。
- workspace 中真实存在 `tool-loop-smoke.html`。

### 11.4 回归

```bash
uv run python -m pytest tests/test_orchestrator.py tests/test_orchestrator_tool_calling.py tests/test_stream_tool_calls.py -q
uv run python -m pytest tests/test_agent_config_validation.py tests/test_registry.py -q
uv run python -m ruff check app tests
uv run python -m mypy app/agents app/schemas/agent.py
```

`run_test` v1.1+ 回归需追加：

- 允许 test command，拒绝 preview/dev/server command。
- 超时会清理进程。
- stdout/stderr redaction 和截断生效。

---

## 12. 与其他 Spec 的关系

- [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md) 定义通用 model/tool loop 参考。
- [orchestrator.spec.md](orchestrator.spec.md) 定义当前程序化任务调度契约。
- [orchestrator-react-dynamic-task-graph.spec.md](orchestrator-react-dynamic-task-graph.spec.md) 定义 task graph ReAct。
- [orchestrator-memory-context-management.spec.md](orchestrator-memory-context-management.spec.md) 定义结构化 run memory。
- 本文档定义 Orchestrator 原生 tool calling 执行模型。

实现后，Orchestrator 将从：

```text
LLM produces plan/replan JSON
backend code executes tasks
```

升级为：

```text
LLM calls tools
backend executes tools safely
tool results drive next model action
```

---

## 13. v1 实现记录

已落地：

- 新增 `backend/app/agents/orchestrator_tools.py`
  - 定义 `dispatch_agent`、`inspect_workspace`、`read_artifact`、`validate_html`、`ask_user`。
  - workspace 工具限制在 `workspace_path` 内，拒绝绝对路径、`..`、drive path、敏感路径。
  - `validate_html` v1 只做静态检查，不启动浏览器。
- 新增 `backend/app/agents/orchestrator_tool_loop.py`
  - 使用 `ModelGateway.stream(..., tools=...)` 驱动 Orchestrator 自身 tool loop。
  - 支持多轮 tool result 注入当前模型上下文。
  - 支持 `orchestrator_tool_trace_visible=false` 隐藏 Orchestrator 自身 tool card。
  - tool loop 超限返回 `loop_max_iterations`。
- 更新 `backend/app/agents/orchestrator.py`
  - 入口顺序为 platform fact -> direct answer -> explicit `config.tasks` -> tool loop -> existing planner/ReAct/static。
  - `dispatch_agent` 复用 `_run_task()`，子 agent 输出继续透传，子 tool call id 前缀为 `orch.<iteration>.<call>.child.*`。
  - `dispatch_agent` 只允许当前 `available_agents` / overridden `managed_agent_ids` 内的 agent。
- 更新 config/schema/openapi/seed：
  - `orchestrator_tool_calling_enabled`
  - `orchestrator_tool_trace_visible`
  - `orchestrator_tool_max_iterations`
  - `orchestrator_tool_result_max_chars`
  - `orchestrator_tool_read_max_bytes`
  - seed 默认仍关闭 `orchestrator_tool_calling_enabled=false`。
- 新增 `backend/tests/test_orchestrator_tool_calling.py`
  - 覆盖 dispatch + validate flow、群外 agent 拒绝、隐藏 trace、workspace escape、max iterations。

已验证：

```bash
cd backend
uv run python -m pytest tests/test_orchestrator_tool_calling.py tests/test_orchestrator.py tests/test_agent_config_validation.py -q
# 113 passed

uv run python -m ruff check app tests/test_orchestrator_tool_calling.py tests/test_agent_config_validation.py
# passed

uv run python -m mypy app/agents app/schemas/agent.py
# passed
```

尚未落地：

- `run_test` / 通用命令执行工具仍保留在 v1.1+。
- 浏览器级点击验证仍保留为后续 `validate_browser_behavior`。
