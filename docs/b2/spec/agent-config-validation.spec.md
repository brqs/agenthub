# Agent Config Validation Spec

## 目标

为 AgentHub 的 Agent 创建、更新和内置 seed 数据建立统一配置校验规则，避免旧 raw LLM provider、无效 runtime 配置或错误 BuiltinAgent backend 进入数据库。

本 Spec 最初服务于 B2-05；B2-20 后已随 Agent Runtime Pivot 更新。当前顶层 Agent provider 是真实 runtime / builtin：

- `claude_code`
- `codex`
- `opencode`
- `builtin`
- `mock`

旧 `claude` / `openai` / `deepseek` / `custom` 不再允许作为新建 Agent 的顶层 provider；它们只允许作为 ModelGateway backend 或历史数据迁移兼容项。

## 输入 / 输出

输入来源：

- `POST /api/v1/agents` 的 `CreateAgentRequest`
- `PATCH /api/v1/agents/{id}` 的 `UpdateAgentRequest`
- `backend/app/seeds/seed_agents.py` 中的 `BUILTIN_AGENTS`

核心输入字段：

- `provider`: `claude_code` / `codex` / `opencode` / `builtin` / `mock`
- `system_prompt`: Agent 行为提示词，可由 runtime / builtin 使用
- `config.model_backend`: BuiltinAgent 内部 ModelGateway backend，取值 `claude` / `deepseek` / `openai`
- `config.context_max_tokens`: 通用 agent 会话上下文预算，默认 `64000`，范围 `1..200000`
- `config.orchestrator_context_max_tokens`: Orchestrator 主流程上下文预算，默认 `64000`，范围 `1..200000`
- `config.orchestrator_subagent_context_max_tokens`: Orchestrator 分发给子 Agent 的上下文预算，默认 `64000`，范围 `1..200000`
- `config.planner_context_max_tokens`: Orchestrator Planner 单次 LLM 输入上下文预算，默认 `128000`，范围 `1..1000000`
- `config.max_iterations`: BuiltinAgent loop 最大迭代次数
- `config.mcp_servers`: BuiltinAgent MCP stdio server 配置数组
- `config.runtime` / `config.command` / `config.args` / `config.timeout_seconds`: external runtime 配置

输出：

- 通过校验时返回规范化后的 `config` 副本。
- 校验失败时 API 返回统一 `422` 错误结构。

## 校验规则

### 通用规则

- `config` 必须是 object。
- 校验函数不能修改传入的原始 `config`。
- 新建 Agent 只允许 `claude_code` / `codex` / `opencode` / `builtin`。
- `mock` 仅用于内置或测试路径，不作为普通用户新建 provider。
- `context_max_tokens`、`orchestrator_context_max_tokens`、
  `orchestrator_subagent_context_max_tokens` 如果存在，必须是整数且满足
  `1..200000`。
- `planner_context_max_tokens` 如果存在，必须是整数且满足 `1..1000000`。

### External Runtime 规则

- `claude_code` / `codex` / `opencode` 允许透传 runtime 专属配置。
- `timeout_seconds` 如果存在，必须在 `1 <= timeout_seconds <= 3600`。
- `claude_code.runtime` 如果存在，必须是 `sdk` 或 `cli`。
- `claude_code.command` 如果存在，必须是字符串或字符串数组；仅 `runtime=cli` 或 SDK 缺失 fallback CLI 时使用。
- `codex.runtime` 如果存在，必须是 `cli` 或 `sdk`。
- `codex.command` 如果存在，必须是字符串或字符串数组；默认 `codex`。
- `codex.sandbox_mode` 如果存在，必须是 `read-only` / `workspace-write` / `danger-full-access`。
- `opencode.command` 如果存在，必须是字符串或字符串数组。
- `opencode.args` 如果存在，必须是字符串数组。

### BuiltinAgent and server wrapper rules

- 当前内置 Agent 白名单来自 `seed_agents.BUILTIN_AGENTS`，只包含 `orchestrator`、`claude-code`、`codex-helper`、`opencode-helper`。
- Seed cleanup must delete stale `is_builtin=True` rows whose ids are no longer in `BUILTIN_AGENTS`; it must not delete `is_builtin=False` user-created Agents except through an explicit one-time migration.
- `model_backend` defaults to `claude`.
- `model_backend` must be one of `claude`, `deepseek`, or `openai`.
- `max_iterations` must be an integer in `1..50` when present.
- `react_decision_max_tokens` must be an integer in `1..4096` when present.
- `task_result_context_max_chars`, `task_result_item_max_chars`, `orchestrator_memory_context_max_chars`, `orchestrator_tool_max_tokens`, and `orchestrator_tool_result_max_chars` must stay within their documented bounded ranges when present.
- `orchestrator_tool_read_max_bytes` and `orchestrator_evaluation_read_max_bytes` must be integers in `1..1048576` when present.
- `mcp_servers` must be an object array when present.
- Internal `builtin` provider remains available for Orchestrator / BuiltinAgent runtime and for restricted user-created read-only Agents.
- User-created `provider="builtin"` Agents must be normalized to `custom_agent_mode="server_agent_wrapper"` with `base_agent_id=null`.
- User-created builtin Agents may only expose `allowed_tools=[]` or `allowed_tools=["read_file"]`; `write_file`, `bash`, MCP tools, command/runtime/env/api key fields, and SDK options must be rejected.
- The default external-runtime user custom Agent path is `server_agent_wrapper` around a base Agent:
  - `custom_agent_mode` must be `server_agent_wrapper`.
  - `base_agent_id` must be `claude-code`, `codex-helper`, or `opencode-helper`.
  - Top-level `provider` must match the base Agent: `claude-code -> claude_code`, `codex-helper -> codex`, `opencode-helper -> opencode`.
  - `wrapper_profile` must be an object and may store `role`, `purpose`, `planning_profile`, `planning_strengths`, `planning_weaknesses`, `preferred_task_types`, `capabilities`, `output_style`, and `boundaries`.
- Product-facing no-code settings may be stored in `builder_profile`, `permissions`, and `memory_policy` when supported by the builder flow.
- `builder_profile` must be an object. `role`, `purpose`, `tone`, and `output_style` are strings; `goals`, `do_not_do`, and `starters` are string arrays; `clarification_policy` is `ask_first`, `balanced`, or `decide_with_defaults`.
- `permissions` must be an object. `workspace_read` and `workspace_write` are booleans; `run_commands` is `never`, `ask`, or `auto_low_risk`; `network` is `never`, `ask`, or `allowlisted`; `deploy` and `external_accounts` are `never` or `ask`.
- `memory_policy` is `none`, `conversation`, `project`, or `user`. MVP stores all four values but only `none` and `conversation` have runtime behavior.
- Wrapper Agent config must not contain `api_key`, `model_profile`, `command`, `args`, `sandbox_mode`, runtime auth, or other bottom-layer fields; those values must come from the base Agent safe defaults.
- Skills are injected through Agent asset APIs. Knowledge, model backpack, and raw MCP JSON are not part of the current server-wrapper custom Agent main path.
- `allowed_tools` remains the final runtime permission boundary. For user-created builtin Agents, UI permissions may only map into `read_file` until a separate write/command permission design is approved.

### Legacy raw provider 规则

- `claude` / `openai` / `deepseek` / `custom` 不能作为新建 Agent 顶层 provider。
- registry 可为历史 DB 数据保留迁移 shim，把 legacy provider 映射为 `BuiltinAgentAdapter` + `model_backend`。
- seed agent 不得继续使用 legacy provider。

## PATCH 合并规则

`PATCH /api/v1/agents/{id}` 中的 `config` 是局部更新，不是整体替换。

示例：

```json
{"config": {"max_iterations": 5}}
```

应当在后端合并为：

```python
merged_config = {**agent.config, **payload.config}
```

然后对合并后的配置做完整校验，避免把已有 `model_backend` 或 `mcp_servers` 意外清空。

## 边界 / 错误处理

API 层应将配置校验错误映射为：

```json
{
  "error": {
    "code": "INVALID_MODEL_BACKEND",
    "message": "Unsupported model_backend 'custom'",
    "details": {
      "model_backend": "custom"
    }
  }
}
```

推荐错误码：

- `INVALID_PROVIDER`
- `INVALID_AGENT_CONFIG`
- `INVALID_MODEL_BACKEND`
- `SYSTEM_PROMPT_TOO_LARGE`

旧 `INVALID_MODEL` / `INVALID_UPSTREAM_PROVIDER` / `MISSING_SYSTEM_PROMPT` 只属于 pivot 前 raw provider / custom agent 路径，不应出现在新建 runtime Agent 的默认校验路径中。

## 依赖

- `backend/app/schemas/agent.py`
- `backend/app/api/v1/agents.py`
- `backend/app/seeds/seed_agents.py`
- `backend/app/agents/config_validation.py`
- `backend/app/agents/registry.py`
- `shared/openapi.yaml`
- `docs/api-spec.md`

## 验收标准

- 创建 Agent 时，legacy raw provider 会返回 `422 INVALID_PROVIDER`。
- `opencode` 的 `command` / `args` / `timeout_seconds` 校验覆盖成功和失败路径。
- `builtin` 的 `model_backend` / `max_iterations` / `mcp_servers` 校验覆盖成功和失败路径。
- 用户自建 `provider="builtin"` 只允许 `allowed_tools=[]` 或 `["read_file"]`；`write_file` / `bash` / MCP 工具和 runtime secret fields 会被拒绝。
- 更新 Agent 时，`config` 局部合并，不覆盖已有完整配置。
- 内置 `BUILTIN_AGENTS` 全部通过同一套校验规则。
- OpenAPI 和 `docs/api-spec.md` 显式记录新 provider 与 `AgentConfig` 字段。
- 不修改 `BaseAgentAdapter.stream()` 签名。
- 不修改数据库模型或 migration。
