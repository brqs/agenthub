# AgentHub API 设计文档（API Specification）

> 配套文档：[development-plan.md](./development-plan.md) · [tech-architecture.md](./tech-architecture.md)
> 机器可读契约：[../shared/openapi.yaml](../shared/openapi.yaml)（唯一真相源）
> 文档版本：v1.1（Agent Runtime Pivot — 占位 / Sprint 5 Day 2 由 B1 落地）
> 最后更新：2026-05-26

> ⚠️ **2026-05-26 Agent Runtime Pivot 生效**：本文档（人类可读版）已在以下章节补充 pivot 新增能力的**占位说明**，但具体 schema / 字段定义将在 Sprint 5 Day 1-2 由 B1 完成（届时机器可读 [openapi.yaml](../shared/openapi.yaml) 与本文档将同步更新到 v1.1 正式版）。完整决策见 [docs/spec/agent-runtime-pivot.adr.md](spec/agent-runtime-pivot.adr.md)。
>
> v1.1 已落地章节：§5.6（SSE 新增 tool_call / tool_result 事件）/ §7.4（ToolCallBlock 加入 ContentBlock 联合）/ §11（Workspace & Artifact API，新增 3 端点）/ §8 错误码追加 6 个 / 附录 E 变更日志。
>
> v1.0 已有的认证、会话、消息、Agent CRUD、SSE 基础事件（start/block_*/delta/done/error/agent_switch）章节**全部保留并继续生效**，pivot 不破坏向后兼容。

---

## 目录

1. [基础约定](#1-基础约定)
2. [认证（Authentication）](#2-认证authentication)
3. [会话（Conversations）](#3-会话conversations)
4. [消息（Messages）](#4-消息messages)
5. [SSE 流式响应（Stream）](#5-sse-流式响应stream)
6. [Agent](#6-agent)
7. [数据模型（Schemas）](#7-数据模型schemas)
8. [错误码规范](#8-错误码规范)
9. [限流与配额](#9-限流与配额)
10. [完整调用示例（端到端）](#10-完整调用示例端到端)
11. [Workspace & Artifact API（v1.1 — Pivot 已落地）](#11-workspace--artifact-apiv11--pivot-已落地)

---

## 1. 基础约定

### 1.1 基础信息

| 项 | 值 |
|----|----|
| **Base URL（开发）** | `http://localhost:8000` |
| **Base URL（生产）** | `https://api.agenthub.example.com`（占位） |
| **API 前缀** | `/api/v1` |
| **协议** | HTTPS（生产）/ HTTP（本地） |
| **数据格式** | JSON（除 SSE 端点外） |
| **字符编码** | UTF-8 |
| **时间格式** | ISO 8601（UTC，如 `2026-05-22T10:00:00Z`） |
| **ID 格式** | UUID v4（如 `550e8400-e29b-41d4-a716-446655440000`） |

### 1.2 认证方式

所有受保护端点需在 Header 中携带 JWT：

```http
Authorization: Bearer <access_token>
```

未携带或无效 Token 返回 `401 Unauthorized`。

### 1.3 请求头规范

| Header | 必填 | 说明 |
|--------|------|------|
| `Content-Type` | POST/PATCH 时必填 | `application/json` |
| `Authorization` | 受保护端点必填 | `Bearer <jwt>` |
| `Accept` | 可选 | 默认 `application/json`；SSE 端点为 `text/event-stream` |
| `X-Request-ID` | 可选 | 客户端可自定义追踪 ID（服务端会回传） |

### 1.4 通用响应结构

#### 成功响应

```json
{
  "id": "...",
  "field1": "...",
  "field2": "..."
}
```

成功响应直接返回资源对象或资源列表，**不额外包裹 `data` 字段**。

#### 错误响应

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Conversation not found",
    "details": {
      "resource_type": "Conversation",
      "resource_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  }
}
```

#### 列表响应（游标分页）

```json
{
  "items": [...],
  "next_cursor": "eyJpZCI6IjEyMyJ9",
  "has_more": true
}
```

### 1.5 分页约定

- **游标分页**（推荐）：用于消息列表，按 `created_at` 倒序
  - Query: `?cursor=<opaque>&limit=50`
  - Response 包含 `next_cursor`、`has_more`
- **偏移分页**：用于会话列表、Agent 列表
  - Query: `?page=1&page_size=20`
  - Response 包含 `total`、`page`、`page_size`

### 1.6 HTTP 状态码

| 状态码 | 含义 | 触发场景 |
|--------|------|---------|
| 200 OK | 成功 | GET、PATCH 成功 |
| 201 Created | 创建成功 | POST 创建资源 |
| 204 No Content | 成功无返回体 | DELETE 成功 |
| 400 Bad Request | 请求格式错误 | JSON 解析失败、参数缺失 |
| 401 Unauthorized | 未认证 | 无 Token 或 Token 失效 |
| 403 Forbidden | 已认证但无权限 | 访问他人资源 |
| 404 Not Found | 资源不存在 | 找不到指定 ID |
| 409 Conflict | 资源冲突 | 用户名已被占用 |
| 422 Unprocessable Entity | 校验失败 | Pydantic 校验失败 |
| 429 Too Many Requests | 速率限制 | 触发限流 |
| 500 Internal Server Error | 服务端错误 | 未捕获异常 |
| 502 Bad Gateway | 上游错误 | LLM API 不可达 |
| 503 Service Unavailable | 服务不可用 | 数据库连接失败 |

---

## 2. 认证（Authentication）

### 2.1 POST `/api/v1/auth/register` — 注册

**鉴权**：❌ 无需

**请求**：
```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "username": "alice",
  "password": "P@ssw0rd!"
}
```

**请求字段**：
| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `username` | string | ✅ | 3-32 字符，字母/数字/下划线 |
| `password` | string | ✅ | 至少 8 字符 |

**响应 201**：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 604800,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "alice",
    "avatar_url": null,
    "created_at": "2026-05-22T10:00:00Z"
  }
}
```

**错误**：
- `409 USERNAME_TAKEN` —— 用户名已存在
- `422 INVALID_PASSWORD` —— 密码不符合规范

---

### 2.2 POST `/api/v1/auth/login` — 登录

**鉴权**：❌ 无需

**请求**：
```http
POST /api/v1/auth/login HTTP/1.1
Content-Type: application/json

{
  "username": "alice",
  "password": "P@ssw0rd!"
}
```

**响应 200**：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 604800,
  "user": {
    "id": "550e8400-...",
    "username": "alice",
    "avatar_url": null,
    "created_at": "2026-05-22T10:00:00Z"
  }
}
```

**错误**：
- `401 INVALID_CREDENTIALS` —— 用户名或密码错误

---

### 2.3 GET `/api/v1/auth/me` — 获取当前用户

**鉴权**：✅

**请求**：
```http
GET /api/v1/auth/me HTTP/1.1
Authorization: Bearer eyJhbGc...
```

**响应 200**：
```json
{
  "id": "550e8400-...",
  "username": "alice",
  "avatar_url": null,
  "created_at": "2026-05-22T10:00:00Z"
}
```

---

## 3. 会话（Conversations）

### 3.1 GET `/api/v1/conversations` — 会话列表

**鉴权**：✅

**Query 参数**：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `archived` | bool | false | 是否包含归档会话 |
| `pinned_only` | bool | false | 仅显示置顶 |
| `search` | string | - | 标题模糊搜索 |
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页数量（最大 100） |

**响应 200**：
```json
{
  "items": [
    {
      "id": "550e8400-...",
      "title": "React Todo 组件",
      "mode": "single",
      "agent_ids": ["claude-code"],
      "is_pinned": true,
      "is_archived": false,
      "last_message_at": "2026-05-22T10:30:00Z",
      "last_message_preview": "好的，下面是 Todo 组件代码...",
      "created_at": "2026-05-22T09:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

**排序**：置顶 → 按 `last_message_at` 倒序

---

### 3.2 POST `/api/v1/conversations` — 新建会话

**鉴权**：✅

**请求**：
```json
{
  "title": "React Todo 组件",
  "mode": "single",
  "agent_ids": ["claude-code"]
}
```

**请求字段**：
| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `title` | string | ✅ | 1-255 字符 |
| `mode` | enum | ✅ | `single` 或 `group` |
| `agent_ids` | string[] | ✅ | single 必须 1 个，group 至少 2 个 |

**响应 201**：
```json
{
  "id": "550e8400-...",
  "title": "React Todo 组件",
  "mode": "single",
  "agent_ids": ["claude-code"],
  "is_pinned": false,
  "is_archived": false,
  "last_message_at": "2026-05-22T11:00:00Z",
  "created_at": "2026-05-22T11:00:00Z"
}
```

**错误**：
- `422 INVALID_MODE` —— `mode` 非法
- `404 AGENT_NOT_FOUND` —— `agent_ids` 中含不存在的 Agent

---

### 3.3 GET `/api/v1/conversations/{id}` — 会话详情

**鉴权**：✅

**响应 200**：（同 3.2 响应）

**错误**：
- `404 CONVERSATION_NOT_FOUND`
- `403 FORBIDDEN`（不是自己的会话）

---

### 3.4 PATCH `/api/v1/conversations/{id}` — 修改会话

**鉴权**：✅

**请求**（任意字段可选）：
```json
{
  "title": "新标题",
  "is_pinned": true,
  "is_archived": false
}
```

**响应 200**：（同 3.2）

---

### 3.5 DELETE `/api/v1/conversations/{id}` — 删除会话

**鉴权**：✅

**响应**：`204 No Content`

> 删除会级联删除该会话下所有消息（DB `ON DELETE CASCADE`）

---

### 3.6 GET `/api/v1/conversations/{id}/memory` — 会话压缩记忆调试

**鉴权**：✅

**说明**：仅开发环境可用，用于 B1 验证 Context Builder 的滚动摘要。

**响应 200**：
```json
{
  "conversation_id": "uuid",
  "summary_text": "【会话历史摘要】...",
  "summarized_until_message_id": "uuid",
  "source_message_count": 32,
  "source_token_estimate": 12000,
  "summary_token_estimate": 900,
  "algorithm_version": "rules-v1",
  "created_at": "2026-05-25T12:00:00Z",
  "updated_at": "2026-05-25T12:00:00Z"
}
```

**错误**：
- `404 MEMORY_NOT_FOUND` —— 当前会话尚未触发压缩摘要
- `404 NOT_FOUND` —— 非开发环境隐藏该调试端点

---

### 3.7 GET/PATCH `/api/v1/context-compression/config` — 上下文压缩配置

**鉴权**：✅

**说明**：上下文压缩使用独立的模型配置覆盖层，和普通聊天 Agent 的 provider/model 分开。管理员只需要填写 `provider`、`model`、`api_key` 和 `base_url`，后端内部自动处理 OpenAI-compatible、Anthropic/Claude、DeepSeek 等不同 API 格式。

**默认配置**：
```env
CONTEXT_COMPRESSION_MODE=hybrid
CONTEXT_COMPRESSION_PROVIDER=deepseek
CONTEXT_COMPRESSION_MODEL=deepseek-v4-flash
CONTEXT_COMPRESSION_API_KEY=sk-...
CONTEXT_COMPRESSION_BASE_URL=https://api.deepseek.com
```

说明：上下文压缩使用独立的 `CONTEXT_COMPRESSION_API_KEY`，不会自动复用聊天 Agent 的 provider key。未配置时会自动回退到 rules-v2，保证聊天不中断。

**GET 响应 200**：
```json
{
  "mode": "hybrid",
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "summary_max_tokens": 1200,
  "recent_raw_keep": 12,
  "api_key_configured": true,
  "api_key_source": "context_compression_api_key",
  "api_key_preview": "sk-***f0cb",
  "base_url": "https://api.deepseek.com",
  "supported_models": ["deepseek-v4-flash", "deepseek-v4-pro"]
}
```

**PATCH 请求**（仅开发环境可用，运行时临时生效）：
```json
{
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "api_key": "sk-xxx",
  "base_url": "https://api.deepseek.com",
  "summary_max_tokens": 1600,
  "recent_raw_keep": 12
}
```

**支持的 provider**：

| provider | 内部处理 |
|----------|----------|
| `deepseek` | OpenAI-compatible，默认 base_url `https://api.deepseek.com` |
| `openai` | OpenAI Chat Completions，base_url 可为空 |
| `openai_compatible` | 任意 OpenAI-compatible 服务，必须填 base_url |
| `anthropic` / `claude` | Anthropic Messages API |

**POST `/api/v1/context-compression/config/test`**：

用于测试当前或提交的压缩模型配置是否能连通。

```json
{
  "provider": "openai_compatible",
  "model": "custom-summary-model",
  "api_key": "sk-xxx",
  "base_url": "https://example.com/v1"
}
```

响应：

```json
{
  "ok": true,
  "provider": "openai_compatible",
  "model": "custom-summary-model"
}
```

**错误**：
- `422 UNSUPPORTED_COMPRESSION_PROVIDER` —— 压缩服务提供者不支持
- `422 UNSUPPORTED_COMPRESSION_MODEL` —— 压缩模型不在当前 provider 白名单内
- `422 MISSING_COMPRESSION_BASE_URL` —— `openai_compatible` 未填写 base_url
- `404 NOT_FOUND` —— 非开发环境隐藏 PATCH 调试能力

---

## 4. 消息（Messages）

### 4.1 GET `/api/v1/conversations/{id}/messages` — 历史消息

**鉴权**：✅

**Query 参数**：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `cursor` | string | - | 游标（首次请求不传） |
| `limit` | int | 50 | 每页数量（最大 100） |
| `direction` | enum | `before` | `before`（往历史方向）/ `after`（往新方向） |

**响应 200**：
```json
{
  "items": [
    {
      "id": "msg_a1...",
      "conversation_id": "550e8400-...",
      "role": "user",
      "agent_id": null,
      "content": [
        {"type": "text", "text": "用 React 写一个 Todo 组件"}
      ],
      "reply_to_id": null,
      "status": "done",
      "is_pinned": false,
      "created_at": "2026-05-22T10:00:00Z"
    },
    {
      "id": "msg_b2...",
      "conversation_id": "550e8400-...",
      "role": "agent",
      "agent_id": "claude-code",
      "content": [
        {"type": "text", "text": "好的，下面是代码："},
        {
          "type": "code",
          "language": "tsx",
          "code": "function Todo() { return <div /> }"
        }
      ],
      "reply_to_id": "msg_a1...",
      "status": "done",
      "is_pinned": false,
      "created_at": "2026-05-22T10:00:05Z"
    }
  ],
  "next_cursor": "eyJpZCI6Im1zZ19hMSJ9",
  "has_more": true
}
```

**排序**：按 `created_at` 升序（即历史 → 最新）

---

### 4.2 POST `/api/v1/conversations/{id}/messages` — 发送消息

**鉴权**：✅

**请求**：
```json
{
  "content": [
    {"type": "text", "text": "用 React 写一个 Todo 组件"}
  ],
  "target_agent_id": "claude-code"
}
```

**请求字段**：
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | ContentBlock[] | ✅ | 消息内容块数组 |
| `target_agent_id` | string | ⭕ | 指定目标 Agent；single 模式可省略 |

**说明**：
- 单聊模式：`target_agent_id` 自动用会话的唯一 Agent
- 群聊模式：必须指定 `target_agent_id`（通常是 Orchestrator）

**响应 201**：
```json
{
  "user_message": {
    "id": "msg_user_xxx",
    "conversation_id": "550e8400-...",
    "role": "user",
    "agent_id": null,
    "content": [{"type": "text", "text": "用 React 写一个 Todo 组件"}],
    "status": "done",
    "created_at": "2026-05-22T11:00:00Z"
  },
  "agent_message": {
    "id": "msg_agent_yyy",
    "conversation_id": "550e8400-...",
    "role": "agent",
    "agent_id": "claude-code",
    "content": [],
    "status": "pending",
    "created_at": "2026-05-22T11:00:01Z"
  }
}
```

**前端流程**：
1. 拿到 `agent_message.id`
2. 立即发起 GET `/messages/{agent_message.id}/stream` 订阅流

**错误**：
- `404 AGENT_NOT_FOUND` —— target_agent_id 不在会话中
- `422 EMPTY_CONTENT` —— content 为空数组
- `422 CONTENT_TOO_LARGE` —— 总内容超过 32KB

---

### 4.3 POST `/api/v1/messages/{id}/regenerate` — 重新生成

**鉴权**：✅

**说明**：删除指定的 agent 消息，并基于上一条 user 消息重新发起生成。

**响应 201**：（返回新的 agent_message，结构同 4.2 的 `agent_message`）

**错误**：
- `400 NOT_AGENT_MESSAGE` —— 不是 agent 消息无法重生成
- `404 MESSAGE_NOT_FOUND`

---

### 4.4 PATCH `/api/v1/messages/{id}` — 修改消息

**鉴权**：✅

**说明**：仅支持修改 `is_pinned` 字段（Pin/Unpin 消息）。

**请求**：
```json
{
  "is_pinned": true
}
```

**响应 200**：返回更新后的消息对象。

---

### 4.5 DELETE `/api/v1/messages/{id}` — 删除消息

**鉴权**：✅

**响应**：`204 No Content`

> 仅允许删除自己发的 user 消息和自己会话中的 agent 消息

---

### 4.6 GET `/api/v1/messages/search` — 搜索消息

**鉴权**：✅

**Query**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | ✅ | 搜索关键词 |
| `conversation_id` | uuid | - | 限定某会话 |
| `limit` | int | 20 | 最多 50 |

**响应 200**：
```json
{
  "items": [
    {
      "message": { /* Message 对象 */ },
      "conversation": {
        "id": "...",
        "title": "..."
      },
      "highlight": "...好的，下面是 <em>Todo</em> 组件代码..."
    }
  ],
  "total": 5
}
```

---

## 5. SSE 流式响应（Stream）

### 5.1 GET `/api/v1/messages/{id}/stream` — 订阅 Agent 流式响应

**鉴权**：✅ Header 中带 JWT（用 `fetch-event-source` 库）

**请求**：
```http
GET /api/v1/messages/msg_agent_yyy/stream HTTP/1.1
Authorization: Bearer eyJhbGc...
Accept: text/event-stream
```

**响应 Header**：
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

**响应体**：标准 SSE 流（见 5.2-5.3）

**注意事项**：
- 客户端不能用原生 `EventSource`（无法传 JWT Header），需用 `@microsoft/fetch-event-source`
- 服务端用 `sse-starlette` 的 `EventSourceResponse`
- 反向代理必须关闭 buffering（Nginx: `proxy_buffering off`）

---

### 5.2 SSE 事件类型完整规范

#### Event: `start`
**说明**：流开始，含元信息

```
event: start
data: {"message_id":"msg_agent_yyy","agent_id":"claude-code","timestamp":"2026-05-22T11:00:02Z"}
```

#### Event: `block_start`
**说明**：开始一个新的内容块

```
event: block_start
data: {"block_index":0,"block_type":"text"}
```

代码块带语言元数据：
```
event: block_start
data: {"block_index":1,"block_type":"code","metadata":{"language":"tsx"}}
```

#### Event: `delta`
**说明**：内容增量

文本：
```
event: delta
data: {"block_index":0,"text_delta":"好的，"}
```

代码：
```
event: delta
data: {"block_index":1,"code_delta":"function Todo() {\n"}
```

#### Event: `block_end`
**说明**：当前块结束

```
event: block_end
data: {"block_index":0}
```

#### Event: `done`
**说明**：整个流结束

```
event: done
data: {"message_id":"msg_agent_yyy","total_blocks":2,"finished_at":"2026-05-22T11:00:08Z"}
```

#### Event: `error`
**说明**：流式过程中发生错误

```
event: error
data: {"error_code":"rate_limit_exceeded","message":"Anthropic API rate limit hit, please retry later"}
```

错误码见 [8. 错误码规范](#8-错误码规范)。

#### Event: `agent_switch`（仅 Orchestrator 群聊使用）
**说明**：Orchestrator 切换到下一个子 Agent

```
event: agent_switch
data: {"from_agent":"orchestrator","to_agent":"claude-code","task":"写后端 API"}
```

#### Event: `heartbeat`
**说明**：心跳，防止连接超时（可选，每 30s 发一次）

```
event: heartbeat
data: {}
```

---

### 5.3 完整 SSE 流示例

```
event: start
data: {"message_id":"msg_agent_yyy","agent_id":"claude-code"}

event: block_start
data: {"block_index":0,"block_type":"text"}

event: delta
data: {"block_index":0,"text_delta":"好的"}

event: delta
data: {"block_index":0,"text_delta":"，下面是 "}

event: delta
data: {"block_index":0,"text_delta":"Todo 组件代码："}

event: block_end
data: {"block_index":0}

event: block_start
data: {"block_index":1,"block_type":"code","metadata":{"language":"tsx"}}

event: delta
data: {"block_index":1,"code_delta":"function Todo() {\n"}

event: delta
data: {"block_index":1,"code_delta":"  return <div>Todo</div>\n"}

event: delta
data: {"block_index":1,"code_delta":"}"}

event: block_end
data: {"block_index":1}

event: done
data: {"message_id":"msg_agent_yyy","total_blocks":2}

```

---

### 5.4 Orchestrator SSE 流示例（群聊）

```
event: start
data: {"message_id":"msg_orc_zzz","agent_id":"orchestrator"}

event: block_start
data: {"block_index":0,"block_type":"text"}

event: delta
data: {"block_index":0,"text_delta":"📋 拆解为 2 个子任务：\n\n1. @claude-code → 写 Todo 后端 API\n2. @codex-helper → 写 Todo 前端组件"}

event: block_end
data: {"block_index":0}

event: agent_switch
data: {"from_agent":"orchestrator","to_agent":"claude-code","task":"写 Todo 后端 API"}

event: block_start
data: {"block_index":1,"block_type":"code","metadata":{"language":"python"}}

event: delta
data: {"block_index":1,"code_delta":"@app.get('/todos')\nasync def list_todos(): ..."}

event: block_end
data: {"block_index":1}

event: agent_switch
data: {"from_agent":"claude-code","to_agent":"codex-helper","task":"写 Todo 前端组件"}

event: block_start
data: {"block_index":2,"block_type":"code","metadata":{"language":"tsx"}}

event: delta
data: {"block_index":2,"code_delta":"function TodoList() { ... }"}

event: block_end
data: {"block_index":2}

event: done
data: {"message_id":"msg_orc_zzz","total_blocks":3}

```

---

### 5.5 SSE 客户端最佳实践

**前端代码示例**（使用 `@microsoft/fetch-event-source`）：

```typescript
import { fetchEventSource } from '@microsoft/fetch-event-source';

const ctrl = new AbortController();

await fetchEventSource('/api/v1/messages/' + messageId + '/stream', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Accept': 'text/event-stream',
  },
  signal: ctrl.signal,
  
  async onopen(response) {
    if (response.ok) return;
    if (response.status === 401) throw new FatalError('Unauthorized');
    throw new RetriableError();
  },
  
  onmessage(ev) {
    const data = JSON.parse(ev.data);
    switch (ev.event) {
      case 'start':       /* 标记 streaming */ break;
      case 'block_start': /* 创建新 block */ break;
      case 'delta':       /* 应用增量 */ break;
      case 'block_end':   /* 关闭 block */ break;
      case 'done':        ctrl.abort(); break;
      case 'error':       handleError(data); ctrl.abort(); break;
      case 'agent_switch':/* 显示切换提示 */ break;
    }
  },
  
  onerror(err) {
    if (err instanceof FatalError) throw err;
    // 其他错误自动重试
  },
});
```

### 5.6 v1.1 已落地：新增 `tool_call` / `tool_result` 事件（Pivot）

> Sprint 5 Day 2 由 B1 落地 SSE 网关与持久化；B2 负责 Adapter / BuiltinAgent 产生标准 tool 事件。正式 schema 见 [openapi.yaml](../shared/openapi.yaml) 与 [agent-runtime-adapter.spec.md §3](b2/spec/agent-runtime-adapter.spec.md)。

新增 2 个 SSE 事件类型，与 v1.0 `start / block_* / delta / done / error / agent_switch` 并列：

| 事件 | 含义 | 主要字段 |
|---|---|---|
| `tool_call` | Agent 决定调用一个工具 | `call_id` / `tool_name` / `tool_arguments` |
| `tool_result` | 工具执行完成回传结果 | `call_id` / `tool_status` ("ok"\|"error") / `tool_output` / `tool_output_truncated` |

**配对契约**：每个 `tool_call` 必有匹配的 `tool_result`（按 `call_id` 关联）；否则 yield `error(code=tool_call_orphan)`。

**示例片段**：

```
event: tool_call
data: {"call_id":"c-001","tool_name":"write_file",
       "tool_arguments":{"path":"App.tsx","content":"export function App()..."}}

event: tool_result
data: {"call_id":"c-001","tool_status":"ok","tool_output":"wrote 312 bytes"}
```

**新增错误码**（在 §8 错误码规范中追加）：`tool_call_failed` / `tool_call_orphan` / `workspace_violation` / `mcp_server_down` / `external_runtime_error` / `loop_max_iterations`。

**持久化**：B1 `_ContentAccumulator` 把一对 `tool_call` + `tool_result` 配对为单个 `ToolCallBlock`（见 §7.8）写入 `messages.content`。
`tool_output` 和超长工具参数只保留预览，默认最多约 2 KB，避免把大文件内容直接写进消息 JSON。

---

## 6. Agent

### 6.1 GET `/api/v1/agents` — Agent 列表

**鉴权**：✅

**Query**：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `builtin` | bool | - | 仅内置 / 仅自建 / 都返回 |
| `provider` | string | - | 按 Provider 过滤 |

Provider values: `claude` / `deepseek` / `openai` / `custom`.

**响应 200**：
```json
{
  "items": [
    {
      "id": "claude-code",
      "name": "Claude Code",
      "provider": "claude",
      "avatar_url": "/avatars/claude.png",
      "capabilities": ["coding", "writing"],
      "system_prompt": null,
      "config": {"model": "claude-sonnet-4-6"},
      "is_builtin": true,
      "created_at": "2026-05-22T00:00:00Z"
    },
    {
      "id": "codex-helper",
      "name": "Codex Helper",
      "provider": "openai",
      "avatar_url": "/avatars/openai.png",
      "capabilities": ["coding"],
      "system_prompt": null,
      "config": {"model": "gpt-4o"},
      "is_builtin": true,
      "created_at": "2026-05-22T00:00:00Z"
    },
    {
      "id": "deepseek-assistant",
      "name": "DeepSeek Assistant",
      "provider": "deepseek",
      "avatar_url": "/avatars/deepseek.png",
      "capabilities": ["chat", "analysis", "coding"],
      "system_prompt": null,
      "config": {"model": "deepseek-v4-flash"},
      "is_builtin": true,
      "created_at": "2026-05-22T00:00:00Z"
    },
    {
      "id": "orchestrator",
      "name": "Orchestrator",
      "provider": "custom",
      "avatar_url": "/avatars/orchestrator.png",
      "capabilities": ["task_decomposition", "coordination"],
      "system_prompt": "你是任务协调专家...",
      "config": {"model": "claude-sonnet-4-6", "upstream_provider": "claude"},
      "is_builtin": true,
      "created_at": "2026-05-22T00:00:00Z"
    }
  ],
  "total": 4
}
```

---

### 6.2 POST `/api/v1/agents` — 创建自定义 Agent

**鉴权**：✅

**请求**：
```json
{
  "name": "文案专家",
  "provider": "custom",
  "avatar_url": "/avatars/custom-1.png",
  "capabilities": ["writing", "copywriting"],
  "system_prompt": "你是一位专业的文案撰稿人，擅长营销文案、社交媒体内容创作...",
  "config": {
    "model": "claude-sonnet-4-6",
    "temperature": 0.7,
    "max_tokens": 4096,
    "upstream_provider": "claude"
  }
}
```

**字段约束**：
| 字段 | 约束 |
|------|------|
| `name` | 1-64 字符 |
| `provider` | `claude` / `deepseek` / `openai` / `custom` |
| `capabilities` | 字符串数组，最多 10 项 |
| `system_prompt` | 最长 8KB |
| `config.model` | 必须是 Provider 支持的模型 |
| `config.temperature` | 0.0 - 2.0 |
| `config.max_tokens` | 1 - 16384 |
| `config.upstream_provider` | 仅 `custom` agent 必填，取值 `claude` / `deepseek` / `openai` |

**Custom Agent 额外规则**：
- `provider` 为 `custom` 时，`system_prompt` 必须为非空字符串。
- `provider` 为 `custom` 时，`config.upstream_provider` 必填，且只能是 `claude`、`deepseek` 或 `openai`。
- `config.model` 必须属于 `upstream_provider` 支持的模型（例如 `upstream_provider=deepseek` 时只能用 `deepseek-v4-flash` / `deepseek-v4-pro`）。
- `provider` 为 `claude` / `deepseek` / `openai` 时，不允许携带 `config.upstream_provider`。

**响应 201**：（同 6.1 列表项）

**错误**：
- `422 INVALID_PROVIDER`
- `422 INVALID_MODEL`
- `422 INVALID_AGENT_CONFIG`
- `422 INVALID_UPSTREAM_PROVIDER`
- `422 MISSING_SYSTEM_PROMPT`
- `422 SYSTEM_PROMPT_TOO_LARGE`

---

### 6.3 GET `/api/v1/agents/{id}` — Agent 详情

**鉴权**：✅

**响应 200**：（同 6.1 列表项）

---

### 6.4 PATCH `/api/v1/agents/{id}` — 修改 Agent

**鉴权**：✅

**说明**：仅可修改用户自建的 Agent（`is_builtin=false`）。

**请求**：（任意字段可选）
```json
{
  "name": "新名字",
  "system_prompt": "新的 prompt",
  "config": {"temperature": 0.5}
}
```

**Config 局部合并**：
`PATCH` 中的 `config` 会与现有配置做浅合并，不是整体替换。例如：
```json
{"config": {"temperature": 0.5}}
```
会保留已有 `model` 和 `upstream_provider`，仅更新 `temperature`。

**响应 200**：（同 6.3）

**错误**：
- `403 CANNOT_MODIFY_BUILTIN` —— 内置 Agent 不可修改
- `422 INVALID_AGENT_CONFIG` —— 合并后的配置校验失败
- `422 MISSING_SYSTEM_PROMPT` —— custom agent 的 system_prompt 被清空或置空

---

### 6.5 DELETE `/api/v1/agents/{id}` — 删除 Agent

**鉴权**：✅

**响应**：`204 No Content`

**错误**：
- `403 CANNOT_DELETE_BUILTIN`
- `409 AGENT_IN_USE` —— Agent 正被会话使用（可选限制，MVP 可允许删除并孤儿化引用）

---

## 7. 数据模型（Schemas）

### 7.1 User

```typescript
interface User {
  id: string;              // UUID
  username: string;
  avatar_url: string | null;
  created_at: string;      // ISO 8601
}
```

### 7.2 Conversation

```typescript
interface Conversation {
  id: string;
  title: string;
  mode: "single" | "group";
  agent_ids: string[];
  is_pinned: boolean;
  is_archived: boolean;
  last_message_at: string;
  last_message_preview?: string;  // 列表 API 才有
  created_at: string;
}
```

### 7.3 Message

```typescript
interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "agent" | "system";
  agent_id: string | null;
  content: ContentBlock[];
  reply_to_id: string | null;
  status: "pending" | "streaming" | "done" | "error";
  is_pinned: boolean;
  created_at: string;
}
```

### 7.4 ContentBlock（联合类型）

```typescript
type ContentBlock =
  | TextBlock
  | CodeBlock
  | DiffBlock
  | WebPreviewBlock
  | FileBlock
  | ToolCallBlock;        // ✨ v1.1 新增（pivot）

interface TextBlock {
  type: "text";
  text: string;
}

interface CodeBlock {
  type: "code";
  language: string;       // "python" | "tsx" | ...
  code: string;
}

interface DiffBlock {
  type: "diff";
  filename: string;
  before: string;
  after: string;
}

interface WebPreviewBlock {
  type: "web_preview";
  url: string;
  title?: string;
  description?: string;
  thumbnail_url?: string;
}

interface FileBlock {
  type: "file";
  filename: string;
  url: string;
  size: number;           // bytes
  mime_type: string;
}

// ✨ v1.1 新增（pivot）— 由 SSE tool_call + tool_result 配对持久化而来
// 完整规范：docs/b2/spec/agent-runtime-adapter.spec.md §3 / §7.2
interface ToolCallBlock {
  type: "tool_call";
  call_id: string;                                // 唯一 id，如 "c-001" 或 "t1.c-001"（orchestrator 子任务重映射后）
  tool_name: string;                              // 如 "write_file" / "bash" / "mcp_fs__list_directory"
  arguments: Record<string, unknown>;             // tool 参数（write_file 的 content 可能 preview 截断）
  status: "pending" | "ok" | "error";             // pending 仅在流式过程出现
  output_preview?: string;                        // tool 返回的输出（已截断，最大 ~2 KB）
  output_truncated?: boolean;                     // true 表示原始输出更长，需要访问 workspace 看完整文件
  error_code?: string;                            // status=error 时填，如 "workspace_violation" / "tool_call_failed"
}
```

### 7.5 Agent

```typescript
interface Agent {
  id: string;
  name: string;
  provider: "claude" | "deepseek" | "openai" | "custom";
  avatar_url: string;
  capabilities: string[];
  system_prompt: string | null;
  config: AgentConfig;
  is_builtin: boolean;
  created_at: string;
}

interface AgentConfig {
  model: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  [key: string]: any;
}
```

### 7.6 StreamEvent

```typescript
type StreamEvent =
  | { event: "start"; data: { message_id: string; agent_id: string } }
  | { event: "block_start"; data: { block_index: number; block_type: string; metadata?: object } }
  | { event: "delta"; data: { block_index: number; text_delta?: string; code_delta?: string } }
  | { event: "block_end"; data: { block_index: number } }
  | { event: "done"; data: { message_id: string; total_blocks: number } }
  | { event: "error"; data: { error_code: string; message: string } }
  | { event: "agent_switch"; data: { from_agent: string; to_agent: string; task: string } }
  | { event: "heartbeat"; data: {} };
```

### 7.7 Pagination

```typescript
// Offset-based
interface OffsetPaginationResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// Cursor-based
interface CursorPaginationResponse<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}
```

### 7.8 ErrorResponse

```typescript
interface ErrorResponse {
  error: {
    code: string;          // 大写蛇形，如 RESOURCE_NOT_FOUND
    message: string;       // 人类可读
    details?: object;      // 可选附加信息
  };
}
```

---

## 8. 错误码规范

### 8.1 错误码命名规则

- 全大写、下划线分隔（`SCREAMING_SNAKE_CASE`）
- 形式：`<RESOURCE>_<REASON>` 或 `<ACTION>_<REASON>`

### 8.2 完整错误码表

#### 通用错误（400/422）
| Code | HTTP | 含义 |
|------|------|------|
| `BAD_REQUEST` | 400 | 请求格式错误 |
| `VALIDATION_ERROR` | 422 | Pydantic 校验失败 |
| `MISSING_FIELD` | 422 | 缺少必填字段 |
| `INVALID_FIELD_VALUE` | 422 | 字段值不合法 |

#### 认证错误（401/403）
| Code | HTTP | 含义 |
|------|------|------|
| `UNAUTHORIZED` | 401 | 未携带 Token |
| `INVALID_TOKEN` | 401 | Token 无效 |
| `TOKEN_EXPIRED` | 401 | Token 已过期 |
| `INVALID_CREDENTIALS` | 401 | 用户名或密码错 |
| `FORBIDDEN` | 403 | 无权限访问 |

#### 资源错误（404/409）
| Code | HTTP | 含义 |
|------|------|------|
| `RESOURCE_NOT_FOUND` | 404 | 通用资源不存在 |
| `USER_NOT_FOUND` | 404 | 用户不存在 |
| `CONVERSATION_NOT_FOUND` | 404 | 会话不存在 |
| `MESSAGE_NOT_FOUND` | 404 | 消息不存在 |
| `AGENT_NOT_FOUND` | 404 | Agent 不存在 |
| `USERNAME_TAKEN` | 409 | 用户名已被占用 |
| `AGENT_IN_USE` | 409 | Agent 被会话引用 |

#### 业务错误（400/422）
| Code | HTTP | 含义 |
|------|------|------|
| `INVALID_PASSWORD` | 422 | 密码不符合规范 |
| `INVALID_MODE` | 422 | 会话 mode 非法 |
| `EMPTY_CONTENT` | 422 | 消息内容为空 |
| `CONTENT_TOO_LARGE` | 422 | 消息内容超过上限 |
| `INVALID_PROVIDER` | 422 | provider 非法 |
| `INVALID_MODEL` | 422 | model 非法 |
| `INVALID_AGENT_CONFIG` | 422 | Agent 配置非法（如数值越界、携带了不该有的字段） |
| `INVALID_UPSTREAM_PROVIDER` | 422 | upstream_provider 非法或缺失 |
| `MISSING_SYSTEM_PROMPT` | 422 | custom agent 缺少 system_prompt |
| `SYSTEM_PROMPT_TOO_LARGE` | 422 | System Prompt 超长 |
| `CANNOT_MODIFY_BUILTIN` | 403 | 内置资源不可改 |
| `CANNOT_DELETE_BUILTIN` | 403 | 内置资源不可删 |
| `NOT_AGENT_MESSAGE` | 400 | 不是 agent 消息 |

#### 限流（429）
| Code | HTTP | 含义 |
|------|------|------|
| `RATE_LIMIT_EXCEEDED` | 429 | 请求过于频繁 |

#### 服务端错误（5xx）
| Code | HTTP | 含义 |
|------|------|------|
| `INTERNAL_ERROR` | 500 | 服务端未捕获异常 |
| `UPSTREAM_ERROR` | 502 | 上游 LLM API 错误 |
| `UPSTREAM_RATE_LIMIT` | 502 | 上游限流 |
| `UPSTREAM_TIMEOUT` | 502 | 上游超时 |
| `SERVICE_UNAVAILABLE` | 503 | DB / Redis 不可用 |

#### SSE 流内错误（在 event:error 中）
| Code | 含义 |
|------|------|
| `stream_aborted` | 客户端主动断开 |
| `rate_limit_exceeded` | 上游限流 |
| `context_length_exceeded` | 上下文超过模型最大长度 |
| `api_error` | 上游 API 错误 |
| `internal_error` | 服务端内部错误 |

---

## 9. 限流与配额

### 9.1 MVP 阶段限流策略

| 端点 | 限制 |
|------|------|
| `POST /auth/register` | 5 次 / IP / 小时 |
| `POST /auth/login` | 10 次 / IP / 5 分钟 |
| `POST /messages` | 60 次 / 用户 / 分钟 |
| 其他读端点 | 100 次 / 用户 / 分钟 |

### 9.2 限流响应

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests, please retry after 60 seconds",
    "details": {
      "retry_after_seconds": 60,
      "limit": "60/minute"
    }
  }
}
```

### 9.3 上游 LLM 配额管理（MVP 简化）

- 不实现用户级配额
- 上游 429 时通过 SSE error event 透传，前端显示"暂时无法响应，请稍后再试"

---

## 10. 完整调用示例（端到端）

### 10.1 注册 → 登录 → 创建会话 → 发消息 → 收到流式回复

#### Step 1: 注册

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"P@ssw0rd!"}'
```

响应：
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 604800,
  "user": {"id":"u1","username":"alice","avatar_url":null,"created_at":"..."}
}
```

#### Step 2: 列出可用 Agent

```bash
TOKEN="eyJhbGc..."
curl http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer $TOKEN"
```

#### Step 3: 创建单聊会话

```bash
curl -X POST http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "我的第一个会话",
    "mode": "single",
    "agent_ids": ["claude-code"]
  }'
```

响应：
```json
{"id":"c1","title":"我的第一个会话","mode":"single","agent_ids":["claude-code"],...}
```

#### Step 4: 发送消息

```bash
curl -X POST http://localhost:8000/api/v1/conversations/c1/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": [{"type":"text","text":"Hello, write a Python hello world"}]
  }'
```

响应：
```json
{
  "user_message": {"id":"m1","status":"done",...},
  "agent_message": {"id":"m2","status":"pending",...}
}
```

#### Step 5: 订阅 SSE 流

```bash
curl -N http://localhost:8000/api/v1/messages/m2/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"
```

输出：
```
event: start
data: {"message_id":"m2","agent_id":"claude-code"}

event: block_start
data: {"block_index":0,"block_type":"text"}

event: delta
data: {"block_index":0,"text_delta":"Sure! "}

event: delta
data: {"block_index":0,"text_delta":"Here is your hello world:\n"}

event: block_end
data: {"block_index":0}

event: block_start
data: {"block_index":1,"block_type":"code","metadata":{"language":"python"}}

event: delta
data: {"block_index":1,"code_delta":"print('Hello, world!')"}

event: block_end
data: {"block_index":1}

event: done
data: {"message_id":"m2","total_blocks":2}
```

#### Step 6: 获取完整历史

```bash
curl http://localhost:8000/api/v1/conversations/c1/messages \
  -H "Authorization: Bearer $TOKEN"
```

响应：
```json
{
  "items": [
    {"id":"m1","role":"user","content":[{"type":"text","text":"Hello, write a Python hello world"}],...},
    {"id":"m2","role":"agent","agent_id":"claude-code","content":[
      {"type":"text","text":"Sure! Here is your hello world:\n"},
      {"type":"code","language":"python","code":"print('Hello, world!')"}
    ],"status":"done",...}
  ],
  "next_cursor": null,
  "has_more": false
}
```

### 10.2 群聊 Orchestrator 调用示例

#### 创建群聊

```bash
curl -X POST http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Todo App 协作",
    "mode": "group",
    "agent_ids": ["orchestrator", "claude-code", "codex-helper"]
  }'
```

#### 发送 @Orchestrator 消息

```bash
curl -X POST http://localhost:8000/api/v1/conversations/c2/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": [{"type":"text","text":"@orchestrator 帮我设计一个 Todo App，包含后端 API 和前端组件"}],
    "target_agent_id": "orchestrator"
  }'
```

#### 订阅 SSE 流（含 agent_switch 事件）

输出参见 [5.4 Orchestrator SSE 流示例](#54-orchestrator-sse-流示例群聊)。

---

## 11. Workspace & Artifact API（v1.1 — Pivot 已落地）

> Sprint 5 Day 2 由 B1 落地。完整安全边界与路径校验规则见 [docs/b1/spec/workspace-sandbox.spec.md](b1/spec/workspace-sandbox.spec.md)，机器可读契约见 [shared/openapi.yaml](../shared/openapi.yaml)。
>
> 设计目标：每个 conversation 对应一个隔离 sandbox 目录，所有 Agent（External / Builtin）在其中读写文件；前端通过 3 个端点浏览、预览、二次编辑产物。

### 11.1 资源关系

```
Conversation (1) ─── (1) Workspace ─── (n) Files
                          │
                          └── root_path = /workspaces/<conversation_id>/
```

- **懒创建**：Conversation 创建时**不**立即建 workspace；Agent 第一次需要 `workspace_path` 时由 WorkspaceService 创建
- **生命周期**：Conversation 删除 → workspace 行 cascade + 物理目录 rmtree

### 11.2 GET `/api/v1/workspaces/{conv_id}/tree` — 文件树

**鉴权**：✅ + 校验 conversation 归属当前用户

**Query**：
- `max_depth?` — 默认 5，范围 0-20

**响应 200**：

```json
{
  "root": "/workspaces/uuid",
  "tree": {
    "type": "directory",
    "name": "uuid",
    "path": "",
    "children": [
      {
        "type": "directory",
        "name": "src",
        "path": "src",
        "children": [
          {"type": "file", "name": "App.tsx", "path": "src/App.tsx", "size": 312, "mime_type": "text/plain"},
          {"type": "file", "name": "index.css", "path": "src/index.css", "size": 80, "mime_type": "text/css"}
        ]
      },
      {"type": "file", "name": "README.md", "path": "README.md", "size": 120, "mime_type": "text/markdown"}
    ]
  }
}
```

### 11.3 GET `/api/v1/workspaces/{conv_id}/files/{path}` — 读文件

**鉴权**：✅ + 路径校验（[workspace-sandbox.spec.md §4](b1/spec/workspace-sandbox.spec.md)）

**响应 200**（按 mime 分类）：
- `text/html` → 含 `Content-Security-Policy: default-src 'self' 'unsafe-inline'; sandbox` + `X-Frame-Options: SAMEORIGIN`（前端可直接 iframe 预览）
- `text/*` / `application/json` → 文本内容
- 图片 → 直接二进制
- 其他 → `application/octet-stream`（前端提供下载）

**错误**：
- 404 — 文件不存在
- 403 — 路径越界 / 试图读 `.agenthub/`（返回 `workspace_violation` 错误码）
- 413 — 文件超过 `WORKSPACE_MAX_READ_BYTES`

### 11.4 PUT `/api/v1/workspaces/{conv_id}/files/{path}` — 写文件（前端二次编辑回写）

**鉴权**：✅ + 路径校验 + 禁止写 `.env` / `.git/` / `secrets/` / `.agenthub/`

**请求**：原始文件内容（`Content-Type` 必须是 `text/*` 或 `application/octet-stream`）

**响应 204**

**错误**：
- 403 — 路径越界 / 试图写 `.agenthub/`、`.env`、`.git/`、`.ssh/`、`secrets/`
- 413 — 请求体超过 `WORKSPACE_MAX_READ_BYTES`

**典型用例**：用户在 Monaco 编辑器改了 `App.tsx` → PUT 回写 → 前端自动在对话中发送一条系统消息 "我把 App.tsx 改成了这样，请基于此继续" → Agent 接续

### 11.5 安全边界（强制）

| 操作 | 校验 | 拒绝时返回 |
|---|---|---|
| 任意路径 | 必须落在 `workspace_root` 之内（resolve 后再 `relative_to` 校验） | 403 `workspace_violation` |
| 任意路径 | 不允许穿越符号链接 | 403 `workspace_violation` |
| 任意路径 | 禁止读写 `.agenthub/` / `.git/` | 403 `workspace_violation` |
| 写操作 | 禁止写 `.env` / `secrets/` / `.ssh/` | 403 `workspace_violation` |
| 读操作 | 最大 1 MB | 413 |
| 写操作 | 最大 1 MB | 413 |

❌ **不做**（MVP）：Docker per-conversation 隔离、网络/CPU 限制、Workspace 字节配额。

---

## 附录 A：OpenAPI 规范同步

本文档为人类可读版，机器可读版位于 `shared/openapi.yaml`。

**变更流程**：
1. 修改 `shared/openapi.yaml`
2. 同步修改本文档对应章节
3. 前端运行 `pnpm gen:types` 重新生成 TS 类型
4. 后端 Pydantic Schema 与 OpenAPI 保持一致（FastAPI 自动校验）

## 附录 B：FastAPI 自动文档

启动后端后访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## 附录 C：Postman Collection

> 待补充：导出 Postman Collection JSON 文件，放在 `docs/postman/agenthub.postman_collection.json`

## 附录 D：API 版本策略

- 当前版本：`v1`
- 破坏性变更：升级到 `v2`，`v1` 保留 6 个月
- 非破坏性变更（新增字段、新增端点）：直接在 `v1` 添加
- 弃用字段：响应中添加 `X-Deprecated-Field` 头标识

## 附录 E：变更日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-22 | v1.0 | 初始版本 |
| 2026-05-26 | v1.1（占位） | Agent Runtime Pivot：新增 §5.6 SSE `tool_call` / `tool_result` 事件、§7.4 `ToolCallBlock` 联合类型分支、§11 Workspace & Artifact API（3 端点）；新增错误码 `tool_call_failed` / `tool_call_orphan` / `workspace_violation` / `mcp_server_down` / `external_runtime_error` / `loop_max_iterations`。正式 schema 由 B1 在 Sprint 5 Day 1-2 同步到 `shared/openapi.yaml` 与本文档。决策见 [ADR-001](spec/agent-runtime-pivot.adr.md)。|
| 2026-05-26 | v1.1（B1-PIVOT-3） | Workspace & Artifact API 已落地：`GET /workspaces/{conv_id}/tree`、`GET /workspaces/{conv_id}/files/{path}`、`PUT /workspaces/{conv_id}/files/{path}`；同步 `WorkspaceTreeNode` / `WorkspaceTreeResponse` 到 `shared/openapi.yaml`。|
| 2026-05-26 | v1.1（B1-PIVOT-4/5） | SSE `tool_call` / `tool_result` 已落地：B1 stream 网关注入 `workspace_path`，配对持久化为 `ToolCallBlock`，并同步 `shared/openapi.yaml`。|
