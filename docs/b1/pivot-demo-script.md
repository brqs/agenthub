# B1 Pivot Demo Script

## 1. B1 负责什么

B1 负责 AgentHub 的后端底座：认证、会话、消息、SSE 网关、数据库持久化，以及这次 Pivot 新增的 Workspace 沙箱和 Artifact API。

一句话概括：B2 的 Agent 负责“思考和执行”，F 负责“展示和交互”，B1 负责让这些执行结果安全、稳定、可追踪地落到后端。

## 2. 为什么需要 Workspace 沙箱

真实 Agent 不只是聊天，它会写代码、生成网页、修改文件。

如果后端直接让 Agent 写任意系统路径，会有两个风险：

- 安全风险：Agent 可能写到 `.env`、`.ssh`、系统目录或其他用户文件。
- 协作风险：前端不知道产物在哪里，也无法稳定预览和二次编辑。

所以 B1 为每个 conversation 创建一个独立目录：

```text
/workspaces/<conversation_id>/
```

Agent 只能在这个目录里读写文件。所有路径都会经过校验，禁止绝对路径、`../`、`.env`、`.git`、`.ssh`、`secrets` 和符号链接逃逸。

## 3. SSE tool 事件如何工作

Agent 执行工具时，Adapter 会输出标准流式事件：

```text
tool_call   -> Agent 准备调用工具，例如 write_file("hello.html")
tool_result -> 工具执行结果，例如 wrote hello.html
```

B1 的 SSE 网关会做两件事：

- 实时把事件转发给前端，前端可以显示工具调用卡片。
- 把 `tool_call + tool_result` 配对，写进数据库的 `messages.content`，形成一个 `ToolCallBlock`。

这样刷新页面后，用户依然能看到 Agent 曾经调用过什么工具、成功还是失败、输出了什么摘要。

## 4. Artifact API 如何支持预览和编辑

Agent 写入 workspace 后，前端通过 B1 的三个接口消费产物：

```text
GET /api/v1/workspaces/{conversation_id}/tree
GET /api/v1/workspaces/{conversation_id}/files/{path}
PUT /api/v1/workspaces/{conversation_id}/files/{path}
```

其中 HTML 文件会带安全响应头：

```text
Content-Security-Policy: default-src 'self' 'unsafe-inline'; sandbox
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
```

这让前端可以用 iframe 预览 HTML，同时减少脚本和跨域风险。

## 5. P3 Demo 讲法：Agent 生成产物

可以这样演示：

1. 用户向 Agent 发送“生成一个 hello 页面”。
2. 后端开始 SSE stream。
3. Fake/真实 Agent 收到 `workspace_path`，在 workspace 写入 `hello.html`。
4. SSE 输出 `tool_call(write_file)` 和 `tool_result(ok)`。
5. B1 把工具调用持久化成 `ToolCallBlock`。
6. 前端或 curl 调用 tree API，看到 `hello.html`。
7. 调 file API，拿到 HTML 内容和安全响应头。

这证明 B1 已经支持“真实 Agent 生成产物 -> 后端安全落盘 -> 前端可预览”的核心链路。

## 6. P4 Demo 讲法：前端二次编辑回写

P4 要证明前端编辑后的文件，下一轮 Agent 也能继续基于它工作。

可以这样演示：

1. Agent 先生成或 workspace 中已有 `src/App.tsx`。
2. 前端用 Monaco 打开这个文件。
3. 用户修改代码并保存。
4. 前端调用：

```text
PUT /api/v1/workspaces/{conversation_id}/files/src/App.tsx
```

5. 前端再发送一条普通聊天消息，例如“我已经改了 App.tsx，请继续优化”。
6. B1 stream 层再次调用 Adapter，并传入同一个 `workspace_path`。
7. Fake/真实 Agent 读取 `src/App.tsx`，能看到用户刚刚保存的新内容。

这里的关键点是：B1 不需要新增专门的“编辑完成”接口。保存文件用 Artifact API，继续协作用普通消息触发。

## 7. AgentRegistry v2 协作边界

B1 不关心 Agent 是 builtin、external 还是 orchestrator。

B1 只要求 B2 返回的 adapter 支持统一的 v2 stream 契约：

```python
adapter.stream(
    messages,
    workspace_path=workspace_path,
    tool_specs=tool_specs,
)
```

这样 B2 后续接入 Claude Code、Codex、BuiltinAgent 或 Orchestrator 时，B1 不需要写 provider 分支。

## 8. 边界说明

B1 不负责：

- 真正实现 Claude Code / Codex / BuiltinAgent。
- 真正执行 `read_file` / `write_file` / `bash` 工具。
- 前端 ToolCallBlock、ArtifactPreview、Monaco Editor 的 UI。

B1 负责保证：

- workspace 安全边界可靠。
- Artifact API 可被前端稳定调用。
- 前端编辑后的文件能安全写回。
- SSE tool 事件能实时转发。
- 工具调用结果能正确持久化。
- 出错时消息状态、错误码和数据库内容一致。
