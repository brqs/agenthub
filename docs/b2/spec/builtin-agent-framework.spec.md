# Built-in Agent Framework Spec

> 团队自建 Agent 运行时框架。被 [agent-runtime-pivot.adr.md](../../spec/agent-runtime-pivot.adr.md) §2.6 引用。
> 与 [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md) 共同定义 Layer B。

---

## 1. 目标

让自建 Agent 具备**真 Agent 能力**：能写文件、跑命令、调用 MCP 工具、维护跨轮记忆。
**MVP 范围**（Sprint 5 内可交付），不追求功能完整。

### 组件总览

```
BuiltinAgentAdapter（实现 BaseAgentAdapter v2）
   │
   └── AgentLoop（§2）
         │
         ├── ContextManager（§4）── 复用 context_compression
         ├── MemoryManager（§4）── 复用 conversation_memory
         │
         ├── ModelGateway（§6）── 复用 B2-02~B2-12
         │     ├── ClaudeBackend
         │     ├── OpenAIBackend
         │     └── DeepSeekBackend
         │
         ├── ToolRegistry（§3）
         │     ├── read_file
         │     ├── write_file
         │     └── bash（白名单命令）
         │
         └── MCPClient（§5）── stdio transport
               └── 1 个 server: @modelcontextprotocol/server-filesystem
```

---

## 2. AgentLoop

### 2.1 伪代码

```python
# backend/app/agents/builtin/loop.py
async def run_agent_loop(
    messages: list[ChatMessage],
    tools: list[ToolSpec],
    workspace_path: Path,
    model_gateway: ModelGateway,
    config: dict,
    max_iterations: int = 10,
) -> AsyncIterator[StreamChunk]:
    yield StreamChunk(event_type="start", agent_id=agent_id)
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        # 1. 调模型（带 tool schemas）
        response_chunks: list[StreamChunk] = []
        tool_calls: list[ToolCall] = []
        async for chunk in model_gateway.stream(
            messages, tools=tools, config=config
        ):
            if chunk.event_type == "tool_call":
                tool_calls.append(parse_tool_call(chunk))
            yield chunk  # 透传文本流到上层
            response_chunks.append(chunk)

        # 2. 没有 tool_call → 结束
        if not tool_calls:
            yield StreamChunk(event_type="done", agent_id=agent_id)
            return

        # 3. 顺序执行工具（MVP 不并行）
        tool_results: list[ToolResult] = []
        for call in tool_calls:
            result = await execute_tool(call, workspace_path, tools)
            tool_results.append(result)
            yield StreamChunk(
                event_type="tool_result",
                call_id=call.id,
                tool_status=result.status,
                tool_output=truncate(result.output, max_len=2000),
                tool_output_truncated=len(result.output) > 2000,
            )

        # 4. 把 tool_results 喂回 messages 进入下一轮
        messages = append_tool_results(messages, tool_calls, tool_results)

    # 达到 max_iterations
    yield StreamChunk(
        event_type="error",
        error_code="loop_max_iterations",
        error=f"agent loop exceeded {max_iterations} iterations",
    )
```

### 2.2 终止条件

| 条件 | 行为 |
|---|---|
| 模型返回无 tool_call（纯文本回复） | yield `done` |
| 达到 `max_iterations`（默认 10，可配） | yield `error(loop_max_iterations)` |
| 模型 stream 抛异常 | yield `error(upstream_error)` 并终止 |
| 工具执行抛 `WorkspaceViolation` | yield `tool_result(error)` + `error(workspace_violation)` 并终止 |
| 工具执行抛其他异常 | yield `tool_result(error)`，继续循环（让模型自我修正） |

### 2.3 不做（明确边界）

- ❌ 并行 tool 调用（v1 仅顺序）
- ❌ 投机执行（speculative）
- ❌ Agent 调用子 Agent（仅 Orchestrator 才能调度多 Agent）
- ❌ 流式 tool result（tool 必须返回完整结果才 yield）

---

## 3. ToolRegistry — MVP 三件套

### 3.1 工具定义

```python
# backend/app/agents/builtin/tools/registry.py
TOOLS = {
    "read_file": ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file from the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to workspace root"},
            },
            "required": ["path"],
        },
    ),
    "write_file": ToolSpec(
        name="write_file",
        description="Write or overwrite a UTF-8 text file in the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    "bash": ToolSpec(
        name="bash",
        description="Run a whitelisted shell command in the workspace (timeout 30s).",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
        },
    ),
}
```

### 3.2 执行约束（与 [workspace-sandbox.spec.md](../../b1/spec/workspace-sandbox.spec.md) 一致）

| 工具 | 约束 |
|---|---|
| `read_file` | 路径必须解析后落在 workspace 内；最大读 1 MB；非 UTF-8 → `tool_status=error` |
| `write_file` | 路径必须在 workspace 内；不允许写 `.env` / `secrets/` / `.git/`；自动 `mkdir -p` 父目录；最大写 1 MB |
| `bash` | 命令首词必须在白名单：`ls`, `cat`, `mkdir`, `rm`, `mv`, `cp`, `node`, `python`, `pnpm`, `pip`, `cd`, `pwd`, `echo`, `grep`, `find`；超时 30s；cwd 强制为 workspace；不允许 `sudo` / 管道到 `/dev/*` |

### 3.3 工具结果格式

```python
@dataclass
class ToolResult:
    call_id: str
    status: Literal["ok", "error"]
    output: str          # 成功：文件内容 / stdout；失败：错误信息
    error_code: str | None = None
```

---

## 4. ContextManager / MemoryManager

### 4.1 ContextManager（复用现有）

- 直接复用 [backend/app/services/context_builder.py](../../../backend/app/services/context_builder.py) 与 [backend/app/services/context/compression.py](../../../backend/app/services/context/compression.py)
- BuiltinAgent 在 loop 开始前调一次：拿到压缩后的 `messages`
- **不重新设计**

### 4.2 MemoryManager（薄封装）

- 数据层复用 [backend/app/models/conversation_memory.py](../../../backend/app/models/conversation_memory.py)
- 提供两个接口：
  ```python
  async def pin(conv_id, content: str, tag: str | None = None) -> None
  async def recall(conv_id, limit: int = 10) -> list[MemoryItem]
  ```
- AgentLoop 在 system_prompt 前注入 `recall()` 结果作为"长期记忆"段
- `pin` 不暴露给 LLM 作为 tool（MVP），由用户在前端手动 pin（沿用现有产品逻辑）

### 4.3 不做

- ❌ 向量检索 / 嵌入
- ❌ 自动摘要生成
- ❌ 跨会话记忆共享

---

## 5. MCPClient — stdio transport

### 5.1 协议

- 使用官方 `mcp` Python SDK（`pip install mcp`）
- 仅实现 **stdio** transport
- 启动 server：spawn 子进程，stdin/stdout 双向 JSON-RPC
- 生命周期：BuiltinAgentAdapter 实例创建时启动，stream 结束或 GC 时关闭

### 5.2 MVP server 选型

| Server | 包名 | 提供工具 | 演示用途 |
|---|---|---|---|
| Filesystem | `@modelcontextprotocol/server-filesystem` | `list_directory` / `read_file` / `search_files` | 让自建 Agent 通过 MCP 而非 native tool 访问文件，演示 MCP 接入能力 |

### 5.3 工具合并策略

MCP server 暴露的工具与 native ToolRegistry 工具**合并到同一 `tools` 列表**传给模型。命名空间用前缀避免冲突：

- Native：`read_file`、`write_file`、`bash`
- MCP-fs：`mcp_fs__list_directory`、`mcp_fs__search_files`

模型收到统一的 tool schema 列表；AgentLoop 根据前缀路由到 Native 或 MCP 执行器。

### 5.4 错误处理

| 场景 | 行为 |
|---|---|
| MCP server 启动失败 | yield `error(mcp_server_down)`，loop 启动失败 |
| MCP server 运行中崩溃 | 拦截后 yield `tool_result(error, mcp_server_down)`，loop 继续（不再调用该 server 工具） |
| MCP 调用超时（15s） | yield `tool_result(error, tool_call_failed)` |

### 5.5 不做

- ❌ HTTP transport
- ❌ 多 server 路由（MVP 仅 1 个）
- ❌ 动态加载 MCP server（启动时静态配置）

---

## 6. ModelGateway（复用 B2-02~B2-12）

> ModelGateway 的 canonical spec 见 [model-gateway.spec.md](model-gateway.spec.md)。本节只保留 BuiltinAgent 视角下的接入说明。

### 6.1 结构

```
backend/app/agents/model_gateway/
   __init__.py        # 暴露 ModelGateway 类
   claude.py          # 从 agents/adapters/claude.py 迁移
   openai.py          # 从 agents/adapters/openai.py 迁移
   deepseek.py        # 从 agents/adapters/deepseek.py 迁移
   resilience.py      # 从 agents/adapters/resilience.py 迁移
```

### 6.2 接口

```python
class ModelGateway:
    """Provider 无关的模型调用入口，支持 tool calling。"""

    def __init__(self, backend: Literal["claude", "openai", "deepseek"], config: dict):
        ...

    async def stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        config: dict,
    ) -> AsyncIterator[StreamChunk]:
        """
        新增：tools 参数（v1 raw adapter 没有）。
        Backend 内部把 tools 转成 Provider 原生格式（Anthropic tools / OpenAI tools）。
        """
        ...
```

### 6.3 复用矩阵

| 现有能力 | 迁移后 |
|---|---|
| Stream chunk 标准化 | 不变 |
| Provider retry / timeout / 错误码 | 不变 |
| StreamingArtifactParser（识别 code/diff/url 自然语言输出） | 不变（用于模型自由文本输出） |
| Smoke tests | 迁移后路径更新，断言不变 |

### 6.4 新增能力

- Backend 必须支持 Provider 原生 tool calling 协议：
  - Claude → `tools=[...]` + `tool_use` content block
  - OpenAI → `tools=[...]` + `tool_calls` 字段
  - DeepSeek → 继承 OpenAI
- 把 Provider 原生 tool_use/tool_call 事件映射到 `StreamChunk.event_type = "tool_call"`

---

## 7. BuiltinAgentAdapter 入口

```python
# backend/app/agents/builtin/adapter.py
class BuiltinAgentAdapter(BaseAgentAdapter):
    provider = "builtin"

    def __init__(
        self,
        agent_id: str,
        system_prompt: str | None = None,
        default_config: dict | None = None,
    ):
        super().__init__(agent_id, system_prompt, default_config)
        backend = default_config.get("model_backend", "claude")
        self.model_gateway = ModelGateway(backend, default_config)
        self.memory = MemoryManager()
        self.mcp_client = MCPClient.from_config(default_config.get("mcp_servers", []))

    async def stream(
        self,
        messages,
        *,
        system_prompt=None,
        config=None,
        workspace_path=None,
        tool_specs=None,
    ):
        # 1. 注入 long-term memory
        recalled = await self.memory.recall(conv_id=...)
        full_system = build_system_prompt(self.system_prompt, recalled)

        # 2. 合并 tools（native + MCP）；传入 tool_specs 时对两类工具统一过滤
        all_tools = await self._available_tools(tool_specs)

        # 3. 启动 AgentLoop
        async for chunk in run_agent_loop(
            messages, all_tools, workspace_path,
            self.model_gateway, merged_config,
        ):
            yield chunk
```

当前权限边界：

- Adapter 入口支持通过 `tool_specs` 对 native tools 和 MCP tools 做统一过滤。
- `Agent.config.allowed_tools` 已作为持久化最大权限集合接入运行时；有该字段时，传入的 `tool_specs` 只能进一步收窄，不能放大。
- 对话式 `create_custom_agent` 创建用户自建 builtin Agent 时默认写入 `allowed_tools=[]`，表示最小权限；当前只允许显式授权
  `allowed_tools=["read_file"]`。
- 用户自建 builtin Agent 是 read-only review/reader 能力：不得暴露 `write_file`、`bash` 或 MCP 工具。写文件、命令执行和 MCP
  工具仍只属于内置/历史 trusted BuiltinAgent 路径或后续单独权限设计。
- 当配置恰好为 `allowed_tools=["read_file"]` 且用户明确要求读取 workspace 文件时，Adapter 可以走确定性 read route：
  执行 `read_file` 并返回可见文本，不依赖上游模型完成工具选择。
- 已有未配置 `allowed_tools` 的历史/内置 Builtin Agent 保持旧行为：未显式传入 `tool_specs` 时会获得全部 native tools 和 MCP tools。
- 当前 MVP 覆盖 builtin native/MCP tools；external runtime 的 CLI/SDK 权限映射仍属于后续 hardening。

2026-06-03 / 2026-06-11 live E2E 已验证：

- 真实聊天创建 builtin 自建 Agent 时，显式 `allowed_tools=["read_file"]` 持久化到
  `Agent.config.allowed_tools`。
- 该 Agent 后续会话可使用 `read_file` 读取 workspace 文件。
- 未授权的 `write_file` / `bash` 不会进入模型 tool list，任务不能通过未授权 tool 完成。
- `custom_agent_reader_review_repair` 场景中，自建只读 Review Agent 不写 workspace，只输出审阅意见；后续修复由内置可写 Agent 完成。

证据：`/tmp/agenthub_custom_agent_tools_report.json`、`/tmp/agenthub_custom_agent_reader_review_repair_report.json`，均
`passed=true`。

---

## 8. 验收用例（8 个）

| # | 用例 | 验证 |
|---|---|---|
| 1 | 单轮文本（模型未调用工具） | yield `start → block_start → delta* → block_end → done`，无 tool_call |
| 2 | 单轮调用 `write_file` | yield 序列含 `tool_call(write_file) → tool_result(ok)`，workspace 真有该文件 |
| 3 | 多轮工具：read_file → 修改 → write_file | iteration ≥ 2，messages 累积正确 |
| 4 | `bash` 调用非白名单命令（如 `curl`） | yield `tool_result(error)`，loop 继续，模型可重试 |
| 5 | `write_file` 写到 `../etc/passwd` | yield `tool_result(error)` + `error(workspace_violation)`，loop 终止 |
| 6 | 达到 `max_iterations` | yield `error(loop_max_iterations)` |
| 7 | MCP filesystem server 启动失败 | yield `error(mcp_server_down)`，BuiltinAgentAdapter 启动失败 |
| 8 | 模型选 `mcp_fs__list_directory` | 调用路由到 MCPClient 而非 native，前端看到 tool_call 卡片 |

---

## 9. 不在本 Spec 范围

- Tool 的具体安全实现细节 → 见 [workspace-sandbox.spec.md](../../b1/spec/workspace-sandbox.spec.md)
- BaseAgentAdapter / StreamChunk 协议本身 → 见 [agent-runtime-adapter.spec.md](agent-runtime-adapter.spec.md)
- External Agent SDK 嵌入细节 → 由 B2 在 Sprint 5 Day 2 / Day 6 撰写 task 文档
- 前端 ToolCallBlock UI → 由 F 在 Sprint 5 Day 2 决定
