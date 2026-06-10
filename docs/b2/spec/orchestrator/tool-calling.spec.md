# Orchestrator Tool Calling Agent Spec

> 定义将 Orchestrator 从“程序化多 Agent 调度器 + LLM planner/replanner”升级为“具备原生 tool calling 的 autonomous manager agent”的技术设计。
>
> 状态：v1 implemented / platform tools extended / allowed_tools live E2E passed
> 最后更新：2026-06-03

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

v1 已实现范围：

- `dispatch_agent`
- `inspect_workspace`
- `read_artifact`
- `validate_html`
- `ask_user`
- `start_workspace_preview`
- `verify_web_preview`
- `create_custom_agent`
- `create_deployment`
- `get_deployment_status`
- `package_workspace_source`

非目标：

- 不让 Orchestrator 任意执行 shell。
- v1 不实现 `run_test` / 通用 bash；测试命令 runner 进入 v1.1 或后续版本。
- v1 不让 Orchestrator 或子 agent 执行任意裸 shell 部署命令；Netlify、Vercel、SSH、Docker/Podman、`npm run dev`、`vite --host`、`python -m http.server` 等能力必须收敛到平台受控 tool / deployment worker。
- 不替换 Claude Code / Codex / OpenCode 的真实 runtime。
- 不实现并行 tool execution；默认 DAG 并行属于 [core.spec.md](core.spec.md) 的静态任务执行器能力，不通过本 tool loop 承载。
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
| `orchestrator_tool_max_tokens` | int | `8192` | tool loop 单次模型输出 token 预算，建议校验 `1..32000`。 |
| `orchestrator_tool_result_max_chars` | int | `12000` | 单个 tool result 注入模型上下文的最大字符数。 |
| `orchestrator_tool_read_max_bytes` | int | `262144` | `read_artifact` 最大读取字节数。 |

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

当前实现模块：

```text
backend/app/agents/orchestrator/tool_loop.py
backend/app/agents/orchestrator/tools.py
backend/app/services/orchestrator_platform_tools.py
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
- `tool_specs` 入参继续透传给子 agent；Orchestrator 自身 tools 由 `orchestrator/tools.py` 内部定义，不从外部请求直接接受任意 tool schema。

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
- `validate_html` 本身不做动态点击；真实浏览器行为由平台 `verify_web_preview` 覆盖。

### 5.5 `start_workspace_preview`

通过平台 preview service 启动 workspace 静态预览。Orchestrator 只发起请求，实际端口、进程和生命周期由平台管理。

Schema：

```json
{
  "name": "start_workspace_preview",
  "description": "Start or reuse a platform-managed static preview for the current workspace.",
  "parameters": {
    "type": "object",
    "properties": {
      "entry_path": {"type": "string"},
      "requested_port": {"type": "integer"},
      "mode": {"type": "string", "enum": ["static"]}
    }
  }
}
```

规则：

- 仅支持 `mode="static"`。
- `entry_path` 必须是 workspace-relative HTML 文件。
- 指定 `requested_port=8082` 时必须使用 8082；端口不可用时返回失败，不静默 fallback。
- 禁止 agent runtime 通过 `npm run dev`、`vite --host`、`python -m http.server` 等命令自行启动服务。
- 返回 preview URL、port、entry path、session 状态。
- `web_preview` / preview URL 只代表临时工作区预览，不等于 release/deployment。用户明确要求“部署/发布/上线”时，Orchestrator 仍必须后续调用 `create_deployment`。

### 5.6 `verify_web_preview`

使用平台 Playwright verifier 对已启动 preview 做浏览器级质量验收。

Schema：

```json
{
  "name": "verify_web_preview",
  "description": "Verify a platform preview with Chromium desktop and mobile checks.",
  "parameters": {
    "type": "object",
    "properties": {
      "url": {"type": "string"},
      "required_text": {
        "type": "array",
        "items": {"type": "string"}
      },
      "click_selector": {"type": "string"}
    }
  }
}
```

规则：

- 检查桌面端和移动端。
- 捕获 `pageerror`、`console.error`、同源资源加载失败。
- 保存验证 JSON 和截图到 `/tmp/agenthub_browser_verify/{conversation_id}/`。
- 至少一次按钮点击后不得新增 JS error。
- 返回 `passed`、检查项、错误列表、截图路径。
- 用户明确要求部署静态前端时，Orchestrator 的平台闭环顺序是 `start_workspace_preview -> verify_web_preview -> create_deployment`；浏览器验收失败时应先 repair，再重新 preview/verify/deploy。

### 5.7 `create_custom_agent`

在聊天中创建自建 Agent，并可加入当前 group conversation。

Schema：

```json
{
  "name": "create_custom_agent",
  "description": "Create a custom AgentHub agent for the current user and optionally add it to the current group conversation.",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "provider": {"type": "string", "enum": ["builtin", "claude_code", "codex", "opencode"]},
      "system_prompt": {"type": "string"},
      "capabilities": {
        "type": "array",
        "items": {"type": "string"}
      },
      "config": {"type": "object"},
      "allowed_tools": {
        "type": "array",
        "items": {"type": "string"}
      },
      "add_to_conversation": {"type": "boolean"}
    },
    "required": ["name", "provider", "system_prompt"]
  }
}
```

规则：

- 使用当前用户身份创建 Agent。
- 复用 `validate_agent_config`。
- 缺少必要字段时返回 `needs_user_input=true`，不创建半成品。
- `add_to_conversation=true` 时，将新 Agent id 加入当前 group conversation 的 `agent_ids`。
- 返回 id、name、provider、capabilities、allowed_tools。
- `provider="builtin"` 且未提供 `allowed_tools` 时，默认写入 `allowed_tools=[]`，表示最小权限。
- `allowed_tools` 支持 builtin native tools：`read_file`、`write_file`、`bash`。
- MCP 工具名使用 `mcp_<server_name>__<tool_name>`，其中 `server_name` 必须存在于同一 config 的 `mcp_servers`。

当前边界：

- 显式 `allowed_tools` MVP 已实现，覆盖 builtin native/MCP tools。
- 已有未配置 `allowed_tools` 的历史/内置 Builtin Agent 保持旧行为：未显式传入 `tool_specs` 时仍可获得全部 native tools 和 MCP tools。
- 外部 runtime 的 CLI/SDK 权限白名单仍属于后续 hardening，不由本字段控制。

后续 contract：

- 前端 UI 提供工具选择器，复用 Agent CRUD 与聊天创建的同一份工具权限 schema。
- 继续扩展 external runtime 的 provider-specific 权限映射。

平台执行：

- executor 位于 `backend/app/services/orchestrator_platform_tools.py`。
- tool spec 位于 `backend/app/agents/orchestrator/tools.py`。
- tool loop 路由位于 `backend/app/agents/orchestrator/tool_loop.py`。
- 即使未启用完整 autonomous tool loop，Orchestrator 也可以在明确自建 Agent 意图下发出正式 `create_custom_agent` tool_call/tool_result，保证聊天流可观察。

验收：

- `/api/v1/agents` 能查到新 Agent。
- 当前 group conversation 的 `agent_ids` 包含新 Agent id。
- 缺少 `name/provider/system_prompt` 时返回 `needs_user_input=true`，且数据库中不产生半成品。
- 非法 provider 或非法 config 返回 tool error。
- 增加 `allowed_tools` 后，非法工具名必须返回 tool error，未授权工具不得进入 Builtin Agent loop。

### 5.8 `create_deployment`

创建一次平台受控 deployment。用于用户明确说“部署 / 发布 / 上线”。

Schema：

```json
{
  "name": "create_deployment",
  "description": "Create a platform-managed workspace deployment or source export.",
  "parameters": {
    "type": "object",
    "properties": {
      "kind": {
        "type": "string",
        "enum": ["static_site", "source_zip", "container"]
      },
      "entry_path": {"type": "string"},
      "requested_port": {"type": "integer"}
    },
    "required": ["kind"]
  }
}
```

规则：

- `static_site` 必须指定 workspace-relative HTML `entry_path`。
- `source_zip` 不要求 `entry_path`，由平台打包当前 workspace。
- `container` 当前默认按
  [native-deployment.execution.spec.md](native-deployment.execution.spec.md)
  通过 `ContainerDeployWorker` 执行真实 build/run；管理员关闭 worker 时返回
  `not_supported`。
- 返回 deployment id、kind、status、url/download_url、error、logs preview。
- 成功或失败都应产生 `deployment_status` 消息块，方便前端展示状态卡片。
- 用户只看到 preview URL 不能算部署完成；只有 `create_deployment` 返回 published/running，或 deployment health 通过后，command fulfillment 才能把 `deployment` item 标记为 satisfied。
- 当 `deployment_health` 判断发布失败且状态不是 `not_supported` 时，Orchestrator 会生成结构化
  reflection，调用 repair agent 修复 workspace，然后重新调用同一个 deployment tool；这条闭环不新增
  REST endpoint，也不允许 Agent 手动运行 Docker / dev server。
- `static_site` 由平台创建不可变 snapshot，并通过稳定 Token URL 发布；不复用 Preview 端口或生命周期。
- `requested_port` 仅为兼容字段，Static Release 会忽略并记录日志。
- 后端部署基础能力见 [deployment-release-backend.execution.spec.md](../deployment-release-backend.execution.spec.md)。
- 原生部署重构计划见
  [native-deployment.execution.spec.md](native-deployment.execution.spec.md)。

### 5.9 `get_deployment_status`

查询 deployment 状态。

Schema：

```json
{
  "name": "get_deployment_status",
  "description": "Read the current status of a platform-managed deployment.",
  "parameters": {
    "type": "object",
    "properties": {
      "deployment_id": {"type": "string"}
    },
    "required": ["deployment_id"]
  }
}
```

规则：

- 只能查询当前 conversation 下的 deployment。
- 返回状态、URL、下载 URL、错误和日志摘要。
- 不读取部署产物文件内容。

### 5.10 `package_workspace_source`

打包当前 workspace 源码供下载。语义上等价于 `create_deployment(kind="source_zip")`，但作为独立 tool 可以更好匹配“下载源码 / 打包源码”意图。

Schema：

```json
{
  "name": "package_workspace_source",
  "description": "Package the current workspace into a downloadable source archive.",
  "parameters": {
    "type": "object",
    "properties": {
      "format": {"type": "string", "enum": ["zip"]}
    }
  }
}
```

规则：

- v1 只支持 `zip`。
- 排除 `.agenthub/`、`.git/`、`node_modules/`、`.venv/`、`__pycache__/`。
- 禁止打包 `.env`、`.ssh`、`secrets/`。
- 返回 export id、download URL、文件大小、文件数、摘要、过期时间和状态。

### 5.11 `run_test`（v1.1+，不在 v1 默认范围）

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

### 5.9 `ask_user`

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

- tool loop 稳定后，可将 `orchestrator/react.py` 的 JSON replanner 能力收敛到 tool loop。
- task graph 仍可作为 memory/summary 视图存在，而不是执行入口。

---

## 10. 实现入口建议

当前实现入口：

- `backend/app/agents/orchestrator/tool_loop.py`
- `backend/app/agents/orchestrator/tools.py`
- `backend/app/services/orchestrator_platform_tools.py`
- `backend/tests/test_orchestrator_tool_calling.py`

当前已修改：

- `backend/app/agents/orchestrator/adapter.py`
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
  - 内置 Orchestrator 默认启用 LLM planning、DAG 并行和正式 tool loop。

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
- 不调度当前群聊外的 agent。
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

- [../builtin-agent-framework.spec.md](../builtin-agent-framework.spec.md) 定义通用 model/tool loop 参考。
- [core.spec.md](core.spec.md) 定义当前程序化任务调度契约。
- [memory-context.spec.md](memory-context.spec.md) 定义结构化 run memory。
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

- 新增 `backend/app/agents/orchestrator/tools.py`
  - 定义 `dispatch_agent`、`inspect_workspace`、`read_artifact`、`validate_html`、`ask_user`。
  - 后续扩展 `start_workspace_preview`、`verify_web_preview`、`create_custom_agent`。
  - workspace 工具限制在 `workspace_path` 内，拒绝绝对路径、`..`、drive path、敏感路径。
  - `validate_html` v1 只做静态检查，不启动浏览器。
- 新增 `backend/app/agents/orchestrator/tool_loop.py`
  - 使用 `ModelGateway.stream(..., tools=...)` 驱动 Orchestrator 自身 tool loop。
  - 支持多轮 tool result 注入当前模型上下文。
  - 支持 `orchestrator_tool_trace_visible=false` 隐藏 Orchestrator 自身 tool card。
  - tool loop 超限返回 `loop_max_iterations`。
- 新增 `backend/app/services/orchestrator_platform_tools.py`
  - 执行平台级 tool：preview、browser verify、自建 Agent。
  - 平台 tool 可以访问 db、conversation、workspace、preview service。
- 更新 `backend/app/agents/orchestrator/adapter.py`
  - 入口顺序为 platform fact -> direct answer -> explicit `config.tasks` -> tool loop -> existing planner/ReAct/static。
  - `dispatch_agent` 复用 `_run_task()`，子 agent 输出继续透传，子 tool call id 前缀为 `orch.<iteration>.<call>.child.*`。
  - `dispatch_agent` 只允许当前 `available_agents` / overridden `managed_agent_ids` 内的 agent。
  - 对聊天中的自建 Agent 意图，即使未开启完整 tool loop，也可通过正式 `create_custom_agent` tool_call/tool_result 执行平台创建。
- 更新 config/schema/openapi/seed：
  - `orchestrator_tool_calling_enabled`
  - `orchestrator_tool_trace_visible`
  - `orchestrator_tool_max_iterations`
  - `orchestrator_tool_max_tokens`
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
- 浏览器级点击验证已由平台 `verify_web_preview` 覆盖；通用 `validate_browser_behavior` 可作为后续跨产物/跨页面增强。

## 14. Platform Tool Extension 验证记录

已通过真实 E2E：

- `start_workspace_preview` 作为正式 Orchestrator tool 调用，启动 `8082` static preview。
- `verify_web_preview` 作为正式 Orchestrator tool 调用，生成桌面/移动端截图和浏览器校验 JSON。
- `create_custom_agent` 作为正式 platform tool 调用，创建 `LiveCopywriter-{timestamp}` 并加入当前群聊。
- `create_custom_agent.allowed_tools` 作为正式 schema 字段通过 live E2E：创建 builtin
  `LiveReader-{timestamp}` 时 `allowed_tools=["read_file"]` 持久化，后续运行可读文件，未授权
  `write_file` / `bash` 不进入模型 tool list。
- `create_deployment(container)` 失败后通过 `deployment_health` reflection 调度 repair agent，
  repair 后第二次调用 deployment tool 并最终 `published=true`。

报告：

- `/tmp/agenthub_b2_p0_live_report.json`
- `/tmp/agenthub_orchestrator_quality_report.json`
- `/tmp/agenthub_orchestrator_quality_browser.json`
- `/tmp/agenthub_deployment_repair_flow_report.json`
- `/tmp/agenthub_custom_agent_tools_report.json`

详细验收记录见 [live-e2e-report.spec.md](live-e2e-report.spec.md)。
