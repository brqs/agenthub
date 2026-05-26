# Agent Runtime Adapter Spec（v2）

> 本 Spec 定义 pivot 后的 `BaseAgentAdapter` 接口与 `StreamChunk` 协议扩展。
> 被 [agent-runtime-pivot.adr.md](../../spec/agent-runtime-pivot.adr.md) §2.2 引用。
> 替代 CLAUDE.md / AGENTS.md §4.2 中的契约 2 旧签名。

---

## 1. 目标

让 B1（SSE / 持久化）以统一接口调用三类完全不同的 Agent：

- **ExternalAgentAdapter**：嵌入 Claude Agent SDK / OpenAI Agents SDK 等第三方 agent runtime
- **BuiltinAgentAdapter**：调用自建 [builtin-agent-framework](../../b2/spec/builtin-agent-framework.spec.md)
- **OrchestratorAdapter**：保留现有注入式调度，子 Agent 通过本接口拿到

所有 Adapter 共享：
- 同一份 `BaseAgentAdapter` 抽象
- 同一份 `StreamChunk` 流式事件协议（扩展 tool_call / tool_result）
- 同一份 Workspace 隔离约束（见 [workspace-sandbox.spec.md](../../b1/spec/workspace-sandbox.spec.md)）

---

## 2. 新 `BaseAgentAdapter` 接口签名

```python
# backend/app/agents/base.py（v2）
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.agents.types import ChatMessage, StreamChunk, ToolSpec


class BaseAgentAdapter(ABC):
    """v2 — Agent Runtime adapter contract."""

    provider: str = ""  # 子类必须设置

    def __init__(
        self,
        agent_id: str,
        system_prompt: str | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,
        tool_specs: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Args:
            messages: ContextBuilder 已组装好的对话历史
            system_prompt: 覆盖 self.system_prompt
            config: 覆盖 self.default_config（per-call）
            workspace_path: 当前会话的 sandbox 根目录（B1 传入；可能为 None 表示无文件能力）
            tool_specs: 本次调用允许使用的工具白名单（ExternalAdapter 可能忽略，使用其内置工具）

        Yields:
            StreamChunk：start / block_* / delta / tool_call / tool_result /
                         agent_switch / done / error / heartbeat
        """
        raise NotImplementedError
```

### 变更摘要（vs v1）

| 项 | v1 | v2 | 说明 |
|---|---|---|---|
| 参数 `workspace_path` | — | `Path \| None` | 新增；B1 创建会话时分配 |
| 参数 `tool_specs` | — | `list[ToolSpec] \| None` | 新增；BuiltinAgent 用 |
| 关键字参数 | 位置参数 | `*` 后强制 keyword-only | 防止误传 |
| 返回 | `AsyncIterator[StreamChunk]` | 同上 | 不变 |

> v1 调用方（[backend/app/api/v1/stream.py](../../../backend/app/api/v1/stream.py)）需要补充 workspace_path 与 tool_specs；不传时旧行为保留。

---

## 3. `StreamChunk` 协议扩展

```python
# backend/app/agents/types.py（v2）
StreamEventType = Literal[
    # v1（保留）
    "start", "block_start", "delta", "block_end",
    "done", "error", "agent_switch", "heartbeat",
    # v2 新增
    "tool_call",     # Agent 决定调用工具
    "tool_result",   # 工具执行结果回传
]

BlockType = Literal[
    "text", "code", "diff", "web_preview",
    "tool_call",     # 前端渲染为"工具调用卡片"
]


class StreamChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: StreamEventType
    # ── v1 字段（保留）──
    block_index: int | None = None
    block_type: BlockType | None = None
    text_delta: str | None = None
    code_delta: str | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    from_agent: str | None = None
    to_agent: str | None = None
    task: str | None = None
    message_id: str | None = None
    agent_id: str | None = None
    total_blocks: int | None = None
    # ── v2 新增 ──
    call_id: str | None = None             # 一对 tool_call/tool_result 的关联 id
    tool_name: str | None = None           # tool_call
    tool_arguments: dict[str, Any] | None = None  # tool_call
    tool_status: Literal["ok", "error"] | None = None  # tool_result
    tool_output: str | None = None         # tool_result（已截断）
    tool_output_truncated: bool | None = None
```

### 事件配对契约

```
tool_call { call_id: "c-001", tool_name: "write_file", tool_arguments: {...} }
   ⋮（同步执行；可能耗时）
tool_result { call_id: "c-001", tool_status: "ok", tool_output: "..." }
```

- `call_id` 全局唯一（建议 ULID 或 `c-<n>`）
- `tool_call` 后必须有匹配的 `tool_result`（成功或失败），否则视为 `error_code=tool_call_orphan`
- ExternalAdapter 把第三方 SDK 的 tool event 映射到此协议；映射规则各 Adapter 自己实现

---

## 4. `ToolSpec` 定义

```python
# backend/app/agents/types.py
class ToolSpec(BaseModel):
    """单个工具的 JSON Schema 描述，传给 LLM 决定是否调用。"""

    name: str
    description: str
    parameters_schema: dict[str, Any]   # JSON Schema draft-2020-12
    requires_workspace: bool = True
```

ToolSpec 仅供 BuiltinAgent 使用；ExternalAdapter 一般忽略此参数（其内置工具由 SDK 管理）。

---

## 5. 三类子 Adapter 的约束

### 5.1 ExternalAgentAdapter

- 必须把第三方 SDK 的流事件**完整映射**到本协议（含 tool_call / tool_result）
- 必须把 `workspace_path` 作为第三方 SDK 的工作目录（如 Claude Agent SDK 的 `cwd` 或 `setting_sources`）
- **不允许**自己实现 tool execution loop（loop 由第三方 SDK 提供）
- 错误必须映射到标准 error_code（见 §6）

### 5.2 BuiltinAgentAdapter

- 必须实现完整 AgentLoop（见 [builtin-agent-framework.spec.md](../../b2/spec/builtin-agent-framework.spec.md)）
- 必须只调用 `tool_specs` 列出的工具
- 必须把每次 tool 执行的 `call_id` 持续到 `tool_result`
- ModelGateway 内部使用，不暴露 raw LLM 流

### 5.3 OrchestratorAdapter（保留）

- 不变：仍通过注入的 sub-adapters 调度（[orchestrator.spec.md](orchestrator.spec.md)）
- 子 Adapter 现在可能是 External / Builtin，行为对 Orchestrator 透明
- block_index 重映射规则不变，但现在还要重映射 `call_id`（加 sub-task 前缀，如 `t1.c-001`）

---

## 6. 错误码扩展

在现有 `missing_api_key` / `rate_limit` / `timeout` / `connection_error` / `upstream_error`（[provider-resilience.spec.md](provider-resilience.spec.md)）之外新增：

| error_code | 触发场景 | Adapter 类型 |
|---|---|---|
| `tool_call_failed` | 工具调用执行出错（脚本异常、文件不存在等） | Builtin |
| `tool_call_orphan` | tool_call 没有对应 tool_result | Builtin（防御性） |
| `workspace_violation` | 写操作越界 / 路径包含 `..` / 符号链接逃逸 | Builtin / External |
| `mcp_server_down` | MCP server 启动失败或断开 | Builtin |
| `external_runtime_error` | 第三方 SDK 抛出未分类异常 | External |

错误处理原则与现有一致：内容输出前可重试；内容输出后只能 flush 当前 parser 并 yield error。

---

## 7. 兼容性与迁移

### 7.1 调用方（B1）迁移

`backend/app/api/v1/stream.py` 在拿到 Adapter 后改为：

```python
async for chunk in adapter.stream(
    messages,
    workspace_path=workspace.root_path if workspace else None,
    tool_specs=allowed_tools_for(message.agent_id),
):
    ...
```

- 不传 `workspace_path` / `tool_specs` 时，旧 Adapter 行为退化为 v1 等价
- ModelGateway backends（原 Claude/OpenAI/DeepSeek adapter）在 v2 中**仅作为 BuiltinAgent 的依赖**，不再独立注册到顶层 registry

### 7.2 持久化（B1）

`messages.content`（JSONB）新增两种 ContentBlock：

```jsonc
{ "type": "tool_call", "call_id": "c-001", "tool_name": "write_file",
  "arguments": {"path": "App.tsx", "content_preview": "..."} }
{ "type": "tool_result", "call_id": "c-001", "status": "ok",
  "output_preview": "...", "truncated": false }
```

- 前端 [components/blocks/](../../../frontend/src/components/blocks/) 新增 `ToolCallBlock.tsx`（折叠展示工具名、参数 preview、结果）
- 累积器 `_ContentAccumulator`（[backend/app/api/v1/stream.py](../../../backend/app/api/v1/stream.py)）需要处理这两种新事件

### 7.3 OpenAPI

- `shared/openapi.yaml` 的 SSE 事件枚举新增两项
- `ContentBlock` 联合类型新增两个分支
- 由 B1 在 Sprint 5 Day 1 完成；**本 Spec 不直接修改 OpenAPI**

---

## 8. 验收用例（5 个标准用例）

| # | 用例 | 验证 |
|---|---|---|
| 1 | 旧 v1 Adapter 不传 workspace_path / tool_specs 仍可工作 | 现有 `test_claude_adapter.py` 全部通过 |
| 2 | BuiltinAgentAdapter 调用 `write_file` 工具 | yield 顺序：`start → tool_call(c-1) → tool_result(c-1, ok) → block_start(text) → delta → block_end → done` |
| 3 | BuiltinAgentAdapter 调用越界路径 | 工具内部抛 PermissionError → yield `tool_result(c-1, error)` + `error(code=workspace_violation)` |
| 4 | ExternalAgentAdapter (Claude Agent SDK) 调 SDK 内置 Edit tool | SDK 事件正确映射为 tool_call/tool_result；前端能看到"修改了 App.tsx"卡片 |
| 5 | OrchestratorAdapter 调用两个 Builtin 子 Agent，各自有 tool_call | call_id 被重映射为 `t1.c-001` / `t2.c-001`，无冲突 |

---

## 9. 不在本 Spec 范围

- 不定义具体 tool 的 JSON Schema（见 [builtin-agent-framework.spec.md](../../b2/spec/builtin-agent-framework.spec.md) §3）
- 不定义 Workspace 路径校验细节（见 [workspace-sandbox.spec.md](../../b1/spec/workspace-sandbox.spec.md)）
- 不定义 MCP server 启动/连接管理（见 [builtin-agent-framework.spec.md](../../b2/spec/builtin-agent-framework.spec.md) §5）
- 不定义前端 ToolCallBlock 视觉设计（F 在 Sprint 5 Day 2 决定）
