# External Runtime Adapters Spec

## 2026-06-05 Update: Runtime Availability And Auth

An external runtime is runnable only when its actual execution path can be
probed successfully. Static configuration, installed packages, or auth files on
disk are candidates, not proof of availability.

For Claude Code, AgentHub supports provider credentials from backend
environment variables and shared auth state at `$AGENTHUB_CLAUDE_AUTH_DIR`.
Availability checks must use the same auth source as the adapter execution path:
copy shared Claude auth into an isolated runtime HOME, or run CLI smoke commands
with `HOME=$AGENTHUB_CLAUDE_AUTH_DIR`. A present `.claude.json` file or
`hasCompletedOnboarding=true` does not by itself prove that SDK/CLI execution is
authenticated.

Runtime probes may use a short TTL cache, but cache entries must become invalid
when relevant auth files or provider environment values change. Authentication
failures must be normalized into clear runtime errors and must not expose
contradictory SDK wrapper text such as `error result: success`.

## 目标

补齐 `claude-code`、`codex-helper`、`opencode-helper` 的 provider-specific 运行契约。通用 `BaseAgentAdapter` 只定义接口，本 Spec 定义每个 external runtime 如何启动、如何映射事件、如何清理、如何诊断。

适用范围：

- `backend/app/agents/external/claude_code.py`
- `backend/app/agents/external/codex.py`
- `backend/app/agents/external/opencode.py`
- `backend/app/agents/external/workspace_prompt.py`

## 共享规则

所有 external runtime adapter 必须遵守：

- `cwd` 固定为当前 conversation workspace。
- 最新用户消息是唯一 active request，历史消息只作上下文。
- 不启动、不建议、不输出 preview/deploy 长驻服务命令。
- 使用统一 runtime lifecycle，见 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。
- 支持 direct chat routing；普通问答不启动 SDK / CLI。
- 支持单聊 `requirement_alignment="strict"` pre-runtime gate：复杂任务先通过
  ModelGateway/API 生成结构化 `clarification` block，用户确认前不得启动 SDK / CLI、
  不读写 workspace、不得调用工具；用户明确确认后才将合并后的需求上下文交给 runtime。
- Orchestrator 分发的子任务必须跳过单聊需求对齐，避免执行阶段二次追问。
- stdout/stderr 只进入诊断日志，不直接暴露完整内容给最终用户。
- 日志必须 redacted，不记录 API key、完整 env、secrets、`.env` 内容。
- `cwd` 和 prompt guard 只是当前安全底座，不等价于 OS 级 sandbox；最小权限与 worker 隔离 backlog 见 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。

## 错误码

| error_code | 场景 |
|---|---|
| `external_runtime_error` | SDK/CLI 未分类异常 |
| `external_runtime_exit_error` | CLI 非 0 退出且无可用最终输出 |
| `external_runtime_not_found` | CLI/SDK 不存在或不可执行 |
| `workspace_violation` | runtime 尝试越界写入或访问受限路径 |

Timeout / cancellation lifecycle 错误码见 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。

## 事件映射

External runtime 原生事件必须映射为标准 `StreamChunk`：

| 原生事件 | StreamChunk |
|---|---|
| 文本增量 | `delta(text_delta=...)` |
| 文件编辑 / patch | `tool_call` + `tool_result` 或 `diff` block |
| shell / bash 调用 | `tool_call(tool_name="bash")` + `tool_result` |
| JSONL status / progress | 不进入最终 content；必要时 heartbeat metadata |
| runtime 完成 | `done` |
| runtime 失败 | `error` |

约束：

- `tool_use running/pending/started` 只能映射为 `tool_call`，不能提前生成成功 `tool_result`。
- 只有 completed/done/success/ok 才能映射为 `tool_result(status="ok")`。
- failed/error/cancelled 映射为 `tool_result(status="error")` 或 `error`。

## Claude Code Adapter

### 启动策略

- 默认 `runtime="sdk"`，使用 Claude Agent SDK。
- 显式 `runtime="cli"` 时启动 `claude` CLI，并必须走统一 `cli_runtime.py`。
- SDK runtime 中如果 SDK module 缺失，允许 CLI fallback；该 fallback 也必须走统一 `cli_runtime.py`。
- `cwd` 必须是 workspace。
- `workspace_prompt.workspace_guard_prompt()` 必须注入 system prompt。

### SDK 事件处理

- SDK async iterator 必须由 runtime budget 包裹。
- 等待下一条 SDK event 时仍要定期 yield heartbeat。
- 每个 SDK chunk 都刷新 activity。
- SDK stream 的 timeout / cancellation / cleanup 行为见 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。

### CLI fallback

- CLI fallback 不允许使用裸 `asyncio.create_subprocess_exec` 分散实现。
- 必须使用统一 CLI runner，以获得 stdout/stderr 并发读取、idle/hard timeout、process group cleanup。

### 输出过滤

Claude Code 的最终文本如果包含 preview/deploy 命令，应在 adapter 层后处理：

- 拦截 `http.server`、`npm run dev`、`pnpm dev`、`vite --host`、`next dev` 等命令文本。
- 替换为平台预览说明。
- 记录 redacted diagnostic log。

## Codex Adapter

### 启动策略

- 当前默认 CLI runtime。
- SDK runtime 可作为后续增强，但必须使用同一 runtime budget。
- CLI runtime 必须支持 `config.command`，默认 `codex`；配置值可为 string 或 argv list。
- AgentHub adapter 不提供硬编码默认模型。`config.model` 缺省或为空字符串时：
  - CLI runtime 不传 `-m`；
  - SDK/runtime 不传显式 `model` 参数；
  - run metadata 标记为 runtime default / 未显式指定。
- 只有用户或 Agent config 明确指定 `model` 时，adapter 才把该值传给 Codex CLI/SDK。
- CLI 必须使用 `-o` 输出文件捕获最终回答，避免 stdout/stderr 协议不稳定导致丢失内容。

### stdout/stderr

- stdout/stderr 并发读取。
- 任意 stdout/stderr 字节都刷新 activity。
- stdout/stderr 进入 bounded diagnostic buffer，默认最多保留尾部 16 KiB。
- 诊断日志需要 redaction。

### timeout 语义

- timeout 时如果 `-o` 输出文件非空，按成功返回 `done`。
- timeout 时输出文件为空，按 `runtime_idle_timeout` 或 `runtime_hard_timeout` 返回 error。
- 非 0 exit code 且输出文件非空，可按成功处理，但 metadata 记录 exit code。
- 非 0 exit code 且输出文件为空，返回 `external_runtime_exit_error` 并记录 redacted stdout/stderr 摘要。

## OpenCode Adapter

### 启动策略

- 通过 CLI JSONL 模式运行。
- `command` / `args` 来自 config，但必须通过 config validation。
- `cwd` 固定 workspace。
- AgentHub adapter 不提供硬编码默认模型。`config.model` 缺省或为空字符串时，不传
  `--model`，由 OpenCode runtime 使用其本地默认模型配置。只有配置明确指定 `model` 时，
  adapter 才传 `--model <value>`。

### JSONL 处理

- 每条合法 JSONL event 刷新 activity。
- 等待 stdout line 期间按 heartbeat interval 唤醒。
- JSON parse 失败不应立刻终止；应记录诊断并继续读取，除非连续失败超过阈值。
- stderr 字节刷新 activity，并进入 bounded diagnostic buffer。
- adapter 必须捕获 stdout JSON 中的 `sessionID`。
- 对 OpenCode 1.16.x 兼容：当进程 `return_code=0` 且 stdout JSON 没有 assistant
  text/tool 输出时，允许按 `sessionID` 从 OpenCode SQLite store 补读 assistant text。
  该补读只允许读取 `message.data.role == "assistant"` 且
  `part.data.type == "text"` 的内容。
- DB 补读不得读取 reasoning、user prompt、auth/account 文件或其他非 assistant text 记录；
  DB 不可读、非 SQLite、无 session 或无 assistant text 时，才返回清洗后的 empty-output /
  runtime error。

### 进程清理

- timeout/cancel/error 时 kill 整个 process group。
- 子进程退出后必须 drain stdout/stderr reader，避免资源泄漏。

## 配置

Adapter-specific 配置继续保留：

| Provider | 字段 |
|---|---|
| `claude_code` | `runtime` (`sdk` / `cli`), `sdk_options`, `command` |
| `codex` | `runtime` (`cli` / `sdk`), `sandbox_mode`, `command` |
| `opencode` | `command`, `args` |

共享配置：

- runtime lifecycle 字段见 [external-runtime-lifecycle.spec.md](external-runtime-lifecycle.spec.md)。
- direct chat 字段见 `external-direct-chat-routing.spec.md`。
- 单聊需求对齐字段：
  - `requirement_alignment_model_backend`：可选 ModelGateway backend；优先于
    `qa_model_backend` / `model_backend`。
  - `requirement_alignment_llm_enabled`：为 `false` 时只使用确定性 fallback 问题。
  - `auto_clarification_max_questions`：默认最多 3 轮，每轮只问 1 个最高价值问题。
- external direct-chat 流式预算字段：
  - `qa_stream_idle_timeout_seconds`：等待下一条 direct-chat chunk 的 idle timeout。
  - `qa_stream_max_runtime_seconds`：direct-chat 单次回答 hard timeout。
  - `qa_stream_heartbeat_seconds`：等待 direct-chat chunk 期间的 heartbeat 间隔。
  这些字段只作用于 `maybe_stream_direct_chat()` / ModelGateway direct-chat path，不改变
  Claude Code / Codex / OpenCode 真实 CLI/SDK runtime budget。
- `codex.sandbox_mode="danger-full-access"` 不能作为长期 seed 默认值；后续应收紧为 `workspace-write`，更高权限仅允许显式配置并记录审计。

## 2026-06-10 Direct-Chat Dialogue Timeout Hardening

纯对话 / 辩论 / 接力群聊仍优先使用 direct-chat，不默认启动真实 CLI/SDK runtime。
Orchestrator 托管的 `conversation` / `dialogue_turn` 子任务会在调用子 Agent 时注入更宽松的
direct-chat 流式预算：

- `qa_stream_idle_timeout_seconds >= 45`
- `qa_stream_max_runtime_seconds >= 120`
- `qa_stream_heartbeat_seconds = 10`

普通私聊 Agent、短问答和代码 / 文件 / 部署任务不使用该 Orchestrator override。若 direct-chat
仍超时，用户可见错误必须是清洗后的本轮响应超时说明，不能暴露 `direct_chat_timeout`、
`idle_timeout_seconds`、raw stderr 或本地路径。

## 测试计划

- Claude SDK 等待期间持续 heartbeat。
- Claude CLI fallback 由统一 CLI runner cleanup。
- Claude 输出 preview 命令时被 adapter 后处理拦截。
- Codex stderr 活动刷新 idle deadline。
- Codex 缺省 `config.model` 时不向 CLI/SDK 传模型参数；显式配置模型时才传递。
- Codex timeout 且 `-o` 文件非空时成功。
- Codex exit code 1 且无输出时返回完整 redacted 摘要。
- OpenCode 缺省 `config.model` 时 `_model_args()` 为空；显式配置模型时才传
  `--model <value>`。
- OpenCode JSONL running 不提前生成成功 `tool_result`。
- OpenCode stdout 缺少 assistant text 但包含 `sessionID` 且 DB 有 assistant text part
  时，adapter 输出正常 text block；DB 中 reasoning/user text 不得输出。
- OpenCode timeout/cancel 后无残留进程。

## 验收标准

- 三个 external adapters 都不含裸 subprocess timeout 逻辑。
- 三个 external adapters 都能透传 heartbeat。
- 三个 external adapters 都能在 cancel/timeout 时清理资源。
- 三个 external adapters 都不会启动或建议 preview/deploy server。
- smoke 中 `claude-code`、`codex-helper`、`opencode-helper` 对同一 artifact 任务行为一致：生成文件、结束 SSE、不监听 8082。
