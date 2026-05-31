# AgentHub 技术架构文档（Tech Architecture）

> 配套文档：[development-plan.md](./development-plan.md) · [team-division.md](./team-division.md) · [api-spec.md](./api-spec.md)
> 文档版本：v1.1（Agent Runtime Pivot）
> 最后更新：2026-05-26

> ⚠️ **2026-05-26 Agent Runtime Pivot 生效**：Agent 层重新分为三层（External / Builtin Framework / ModelGateway 底座）；BaseAgentAdapter v2 接口升级；新增 Workspace 沙箱。决策依据见 [docs/spec/agent-runtime-pivot.adr.md](spec/agent-runtime-pivot.adr.md)。
>
> 本文档已就地同步的章节：§3（核心组件）/ §6（Adapter 与 Orchestrator）/ §13（ADR 索引）。其他章节（§1 总览、§2 分层、§4 数据流、§5 数据架构、§7 SSE、§8 安全、§9 前端、§10 部署、§11-12 性能与可观测、§14 演进）保留 v1.0 内容，待 pivot 后小幅同步，主要影响是 §4 数据流需要补 tool_call / tool_result 链路、§7 SSE 事件枚举需要扩展、§9 前端需要补 ToolCallBlock / ArtifactPreview。

---

## 目录

1. [架构总览](#1-架构总览)
2. [分层架构](#2-分层架构)
3. [核心组件设计](#3-核心组件设计)
4. [关键数据流](#4-关键数据流)
5. [数据架构](#5-数据架构)
6. [Adapter 与 Orchestrator 设计](#6-adapter-与-orchestrator-设计)
7. [流式通信架构（SSE）](#7-流式通信架构sse)
8. [安全架构](#8-安全架构)
9. [前端架构](#9-前端架构)
10. [部署架构](#10-部署架构)
11. [性能与扩展性](#11-性能与扩展性)
12. [可观测性](#12-可观测性)
13. [技术决策记录（ADR）](#13-技术决策记录adr)
14. [演进路线](#14-演进路线)

---

## 1. 架构总览

### 1.1 系统全景图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              客户端层（Clients）                              │
│  ┌─────────────────┐   ┌───────────────────┐   ┌─────────────────────────┐ │
│  │   Web Browser   │   │  Tauri Desktop    │   │  PWA / Mobile Web       │ │
│  │   (Chrome/Edge) │   │  (macOS/Win/Linux)│   │  (iOS/Android Safari)   │ │
│  └────────┬────────┘   └─────────┬─────────┘   └────────┬────────────────┘ │
│           │                      │                       │                  │
│           └──────────────────────┼───────────────────────┘                  │
│                                  │ HTTPS + SSE                              │
└──────────────────────────────────│──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                          反向代理（可选）                                       │
│                      Nginx / Caddy / Traefik                                  │
│            （TLS 终止 + 静态资源 + SSE 透传 → buffering off）                  │
└──────────────────────────────────│──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                     应用层（FastAPI + Uvicorn）                                │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                          API Gateway Layer                              ││
│  │  ┌──────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  ││
│  │  │ auth.py  │ │conversations │ │ messages.py  │ │ stream.py (SSE)  │  ││
│  │  └──────────┘ │     .py      │ └──────────────┘ └──────────────────┘  ││
│  │               └──────────────┘                                          ││
│  │                            ┌──────────────┐                             ││
│  │                            │  agents.py   │                             ││
│  │                            └──────────────┘                             ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐  │
│  │                        Service Layer                                  │  │
│  │  ┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │  │
│  │  │ conversation_service │ │ message_service  │ │ context_builder  │ │  │
│  │  └──────────────────────┘ └──────────────────┘ └──────────────────┘ │  │
│  └────────────────────────────────│────────────────────────────────────┘  │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐  │
│  │                       Domain Layer (Models)                           │  │
│  │  User ── Conversation ── Message ── Agent                            │  │
│  └────────────────────────────────│────────────────────────────────────┘  │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐  │
│  │                       Agent Integration Layer                          │  │
│  │  ┌──────────────────────┐  ┌────────────────────────────────────────┐│  │
│  │  │   Adapter Registry   │  │            Orchestrator                ││  │
│  │  └──────────┬───────────┘  └────────────────────────────────────────┘│  │
│  │             │                              │                          │  │
│  │  ┌──────────▼──────────────────────────────▼─────────────────────┐  │  │
│  │  │  ClaudeAdapter │ OpenAIAdapter │ CustomAdapter │ MockAdapter   │  │  │
│  │  └────────┬─────────────┬─────────────┬────────────────────────────┘  │  │
│  └───────────│─────────────│─────────────│─────────────────────────────┘  │
└─────────────│─────────────│─────────────│─────────────────────────────────┘
              │             │             │
       ┌──────▼──┐   ┌──────▼──┐   ┌──────▼────────┐
       │Anthropic│   │ OpenAI  │   │ (用户自建模型) │
       │   API   │   │   API   │   │                │
       └─────────┘   └─────────┘   └────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                          基础设施层（Infrastructure）                       │
│  ┌────────────────────┐  ┌─────────────────────┐  ┌────────────────────┐│
│  │  PostgreSQL 15     │  │  Redis 7            │  │  Object Storage    ││
│  │  (asyncpg driver)  │  │  (Pub/Sub + Cache)  │  │  (P2: 附件)         ││
│  └────────────────────┘  └─────────────────────┘  └────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 架构特征

| 特征 | 说明 |
|------|------|
| **分层清晰** | API / Service / Domain / Infrastructure 四层，单向依赖 |
| **异步优先** | 全栈 async/await，I/O 不阻塞 |
| **流式原生** | SSE 贯穿前后端，LLM 响应实时回传 |
| **Provider 解耦** | Adapter 模式屏蔽 Anthropic / OpenAI API 差异 |
| **契约驱动** | OpenAPI 作为前后端唯一真相源 |
| **状态外置** | 应用层无状态，可水平扩展（状态存 DB + Redis） |
| **跨平台前端** | React SPA 一份代码包装到 Web / Desktop / Mobile |

### 1.3 架构决策驱动因素

1. **比赛交付（短期约束）**：14 天内 3 人完成 MVP，必须低复杂度
2. **AI 协作（30% 权重）**：架构要利于 vibe coding —— 模块边界清晰、契约明确
3. **可演示性**：流式响应、富媒体预览必须流畅
4. **可扩展性预留**：架构应能容纳后续多用户、部署发布、多模态等功能

---

## 2. 分层架构

### 2.1 后端四层架构

```
┌─────────────────────────────────────────────────────────┐
│  API Layer  (app/api/v1/)                               │
│  - HTTP 路由、参数校验、响应序列化                          │
│  - 鉴权（FastAPI Depends）                                │
│  - 错误码映射                                              │
└────────────────────────────┬────────────────────────────┘
                             │ 调用
┌────────────────────────────▼────────────────────────────┐
│  Service Layer  (app/services/)                         │
│  - 业务逻辑编排                                            │
│  - 跨实体操作（事务边界）                                   │
│  - 调用 Agent 层（通过 Registry）                          │
└────────────────────────────┬────────────────────────────┘
                             │ 调用
┌────────────────────────────▼────────────────────────────┐
│  Domain Layer  (app/models/, app/schemas/)               │
│  - SQLAlchemy ORM 模型（持久化对象）                       │
│  - Pydantic Schema（DTO、传输对象）                        │
└────────────────────────────┬────────────────────────────┘
                             │ 持久化
┌────────────────────────────▼────────────────────────────┐
│  Infrastructure Layer  (app/core/)                       │
│  - 数据库连接池                                            │
│  - Redis 客户端                                            │
│  - JWT / 加密                                              │
│  - 配置加载                                                │
└─────────────────────────────────────────────────────────┘
```

### 2.2 依赖规则（重要）

```
API → Service → Domain → Infrastructure
                ▲
                │
              Agent
```

- 上层只依赖下层接口，**不允许反向依赖**
- Service 层调用 Agent 层时，通过 `agents.registry.get_adapter` 接口而非具体实现
- Agent 层**不直接访问 DB**，需要数据时由 Service 层传入

### 2.3 跨层数据流转

```python
# 示例：发送消息 → 触发 Agent

# 1. API 层
@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: UUID,
    payload: SendMessageRequest,  # Pydantic Schema
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 2. 调 Service
    result = await message_service.send(db, user, conv_id, payload)
    return SendMessageResponse.from_orm(result)  # DTO


# 3. Service 层
async def send(db, user, conv_id, payload) -> SendResult:
    # 校验权限
    conv = await db.get(Conversation, conv_id)
    if conv.user_id != user.id: raise PermissionDenied()
    
    # 持久化用户消息
    user_msg = Message(role="user", content=payload.content, ...)
    db.add(user_msg)
    
    # 创建 pending agent 消息
    agent_msg = Message(role="agent", agent_id=..., status="pending")
    db.add(agent_msg)
    
    await db.commit()
    return SendResult(user_msg=user_msg, agent_msg=agent_msg)


# 4. Agent 层（在 stream.py 中被调用）
adapter = registry.get_adapter(agent_msg.agent_id)
async for chunk in adapter.stream(...):
    yield chunk
```

---

## 3. 核心组件设计

### 3.1 组件清单（v1.1 — Agent Runtime Pivot）

| 组件 | 所属层 | 文件 | 职责 |
|------|--------|------|------|
| **AuthRouter** | API | `api/v1/auth.py` | 登录、注册、获取当前用户 |
| **ConversationRouter** | API | `api/v1/conversations.py` | 会话 CRUD |
| **MessageRouter** | API | `api/v1/messages.py` | 消息 CRUD、发送 |
| **StreamRouter** | API | `api/v1/stream.py` | **SSE 流式端点**（v1.1 扩展 tool_call / tool_result 事件） |
| **AgentRouter** | API | `api/v1/agents.py` | Agent CRUD |
| **WorkspaceRouter** ✨ | API | `api/v1/workspaces.py` | Workspace 文件树、文件读取、二次编辑回写（**pivot 新增**） |
| **ConversationService** | Service | `services/conversation_service.py` | 会话业务逻辑 |
| **MessageService** | Service | `services/message_service.py` | 消息业务逻辑、状态机 |
| **ContextBuilder** | Service | `services/context_builder.py` | 历史消息 → Agent 上下文 |
| **OrchestratorMemoryStore** ✨ | Service | `services/orchestrator_memory.py` | Orchestrator structured memory 读写、历史 run context 注入、debug 查询 |
| **WorkspaceService** ✨ | Service | `services/workspace_service.py` | Workspace CRUD + 路径校验（**pivot 新增**） |
| **BaseAgentAdapter v2** | Agent | `agents/base.py` | Adapter 抽象基类（含 workspace_path / tool_specs） |
| **AgentRegistry v2** | Agent | `agents/registry.py` | 注册 ExternalAgent / BuiltinAgent / Orchestrator |
| **Orchestrator** | Agent | `agents/orchestrator/adapter.py` | 任务拆解 + 分派（保留，子 Agent 升级为真 Agent） |
| **ArtifactParser** | Agent | `agents/artifact_parser.py` | 流式输出 → ContentBlock（保留） |
| **Layer A — ExternalAgentAdapter** ✨ | Agent | `agents/external/` | 嵌入 Claude Agent SDK / OpenAI Agents SDK / OpenCode CLI，复用其内置 loop/tool/MCP 或 CLI runtime（**pivot 新增**） |
| **Layer B — BuiltinAgentAdapter** ✨ | Agent | `agents/builtin/` | 自建 AgentLoop + ToolRegistry + MCPClient + Memory（**pivot 新增**） |
| **Layer C — ModelGateway** ✨ | Agent | `agents/model_gateway/` | 原 raw LLM Adapter 迁移而来（Claude/OpenAI/DeepSeek + resilience），仅 BuiltinAgent 内部使用 |
| **Security** | Infrastructure | `core/security.py` | JWT、密码哈希 |
| **Database** | Infrastructure | `core/database.py` | 连接池、会话工厂 |
| **PubSub** | Infrastructure | `core/pubsub.py` | Redis Pub/Sub 封装 |

> ✨ = pivot 新增 / 重新分层。完整迁移映射见 [agent-runtime-pivot.adr.md §6](spec/agent-runtime-pivot.adr.md)。

### 3.1.1 Orchestrator Structured Memory 表

2026-05-30 新增 Orchestrator 结构化编排记忆，migration：

```text
backend/alembic/versions/9a1b2c3d4e5f_add_orchestrator_memory.py
```

新增表：

| 表 | 用途 |
|---|---|
| `orchestrator_runs` | 一次 Orchestrator 编排 run，记录 conversation、触发消息、状态、用户请求、plan source、final summary。 |
| `orchestrator_tasks` | run 内 task graph，记录 task id、agent、依赖、priority、expected output、最终状态。 |
| `orchestrator_task_attempts` | 每个 task 的每次 attempt，记录实际执行 agent、状态、文本摘要、tool 摘要、artifact、missing artifact、error。 |
| `orchestrator_run_events` | 编排时间线事件，如 `planned`、`task_started`、`task_result`、`react_decision`、`finished`。 |

边界：

- Orchestrator adapter 仍不直接访问 DB。
- `stream.py` 创建 `OrchestratorMemoryStore`，通过 `config["orchestrator_memory_writer"]` 注入给 Orchestrator。
- 下一轮 Orchestrator 请求前，service 会把最近 terminal runs 格式化为 `Previous Orchestrator structured memory:` system message，并插入到最新 user request 之前。
- 该结构化 memory 不替代 `conversation_memories` 文本压缩表，两者并存。

### 3.2 组件交互（C4 Container 视图）

```
┌────────────────────────────────────────────────────────────────┐
│ Client (React SPA)                                              │
└─────────┬──────────────────────────────────────┬───────────────┘
          │ REST                                  │ SSE
          ▼                                       ▼
   ┌──────────────┐                       ┌──────────────┐
   │ AuthRouter   │                       │ StreamRouter │
   │ ConvRouter   │                       │              │
   │ MsgRouter    │                       │              │
   │ AgentRouter  │                       │              │
   └──────┬───────┘                       └──────┬───────┘
          │                                      │
          ▼                                      ▼
   ┌──────────────┐                       ┌──────────────────┐
   │ Services     │ ◀───────uses─────────│ ContextBuilder   │
   │ (Conv/Msg/   │                       └──────┬───────────┘
   │  Agent)      │                              │
   └──────┬───────┘                              ▼
          │                              ┌──────────────────┐
          │                              │ AdapterRegistry  │
          │                              └──────┬───────────┘
          ▼                                     │
   ┌──────────────┐                            ▼
   │ Models (SQL) │                     ┌────────────────────────────┐
   └──────┬───────┘                     │ Agent Runtime Layer (v1.1) │
          │                              │ ┌────────────────────────┐ │
          ▼                              │ │ ExternalAgentAdapter   │ │
   ┌──────────────┐                     │ │  ├ ClaudeCode (SDK)    │ │
   │ PostgreSQL   │                     │ │  └ Codex   (Agents SDK)│ │
   └──────────────┘                     │ ├────────────────────────┤ │
                                         │ │ BuiltinAgentAdapter    │ │
   ┌──────────────┐                     │ │  └ AgentLoop           │ │
   │ Workspace ✨ │ ◀── 读/写 ─────────│ │     ├ ToolRegistry     │ │
   │ /workspaces/ │                     │ │     ├ MCPClient        │ │
   │  <conv_id>/  │                     │ │     └ ModelGateway     │ │
   └──────────────┘                     │ │        (Claude/OpenAI/ │ │
                                         │ │         DeepSeek)      │ │
                                         │ ├────────────────────────┤ │
                                         │ │ Orchestrator (子 Agent │ │
                                         │ │  通过本接口拿 v2 Adapter)│
                                         │ └────────────────────────┘ │
                                         └──────┬─────────────────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │ External LLM /   │
                                       │ Agent runtime    │
                                       └──────────────────┘
```

---

## 4. 关键数据流

### 4.1 用户注册 / 登录

```
[Client]                  [AuthRouter]            [Service]             [DB]
   │                          │                       │                  │
   │── POST /auth/register ──▶│                       │                  │
   │                          │── hash_password() ───▶│                  │
   │                          │                       │── INSERT user ─▶│
   │                          │                       │◀── User ────────│
   │                          │── create_jwt() ───────│                  │
   │◀──── {access_token} ─────│                       │                  │
   │                          │                       │                  │
   │── POST /auth/login ─────▶│                       │                  │
   │                          │                       │── SELECT user ─▶│
   │                          │                       │◀── User ────────│
   │                          │── verify_password() ──│                  │
   │                          │── create_jwt() ───────│                  │
   │◀──── {access_token} ─────│                       │                  │
```

### 4.2 发送消息 + 流式回复（核心流程）

```
[Client]              [MsgRouter]          [MsgService]    [StreamRouter]   [Adapter]      [LLM API]
   │                      │                     │                 │             │              │
   │── POST messages ────▶│                     │                 │             │              │
   │                      │── send() ──────────▶│                 │             │              │
   │                      │                     │── INSERT user_msg(role=user) ─────────────▶ DB
   │                      │                     │── INSERT agent_msg(status=pending) ───────▶ DB
   │                      │◀── {ids} ──────────│                 │             │              │
   │◀──{user_id,agent_id}─│                     │                 │             │              │
   │                      │                     │                 │             │              │
   │── GET /messages/{id}/stream (SSE) ───────────────────────────▶│             │              │
   │                                                                │── build_context() ──▶ DB │
   │                                                                │◀── history ──             │
   │                                                                │── get_adapter() ──▶       │
   │                                                                │◀── ClaudeAdapter ─        │
   │                                                                │── stream(...) ──────────▶│
   │                                                                │                          │── API call ──▶
   │                                                                │                          │◀── stream ────
   │◀── event:start ────────────────────────────────────────────────│◀── StreamChunk ──        │
   │◀── event:block_start ─────────────────────────────────────────│◀── StreamChunk ──        │
   │◀── event:delta {text_delta: "你"} ─────────────────────────────│◀── StreamChunk ──        │
   │◀── event:delta {text_delta: "好"} ─────────────────────────────│◀── StreamChunk ──        │
   │   ...                                                          │                          │
   │◀── event:done ─────────────────────────────────────────────────│── UPDATE agent_msg ────▶ DB
   │                                                                  (content=full, status=done)
```

### 4.3 群聊 Orchestrator 流程

```
[Client] ──@Orchestrator "做一个Todo App" ──▶ [MsgService] ──▶ pending agent_msg(agent=orchestrator)
                                                                      │
                                                                      ▼
                                                              [StreamRouter]
                                                                      │
                                                            get_adapter("orchestrator")
                                                                      │
                                                                      ▼
                                                             [OrchestratorAdapter]
                                                                      │
                                                       ┌──────────────┼──────────────┐
                                                       │              │              │
                                                       ▼              ▼              ▼
                                              decompose tasks   call subtask 1   call subtask 2
                                              (function call)   (Claude write    (Codex write
                                                                 backend API)     frontend)
                                                       │              │              │
                                                       │              ▼              ▼
                                                       │       async for chunk:
                                                       │         yield chunk    yield chunk
                                                       │              │              │
                                                       └──────────────┴──────────────┘
                                                                      │
                                                                      ▼
                                                              [Client receives merged stream]
```

### 4.4 上下文组装（Context Builder）

```python
# pseudocode
def build_context(conversation_id, max_tokens=8000):
    messages = db.query(Message).filter(
        conversation_id=conversation_id
    ).order_by(created_at.asc()).all()
    
    result = []
    total = 0
    # 反向遍历，保留最近 N 条
    for msg in reversed(messages):
        text = blocks_to_plain_text(msg.content)
        # 简单按字符数估算 token（中文 ~1.5 chars/token，英文 ~4 chars/token）
        approx_tokens = len(text) / 3
        if total + approx_tokens > max_tokens and result:
            break
        result.insert(0, {
            "role": "assistant" if msg.role == "agent" else msg.role,
            "content": text,
        })
        total += approx_tokens
    
    # Pin 的消息强制保留（即使超长也单独压缩）
    pinned = [m for m in messages if m.is_pinned]
    if pinned and not any(p.id in [r.id for r in result] for p in pinned):
        result = compress_pinned(pinned) + result
    
    return result
```

---

## 5. 数据架构

### 5.1 数据库选型理由

| 候选 | 优势 | 劣势 | 决策 |
|------|------|------|------|
| PostgreSQL 15 | JSONB + 全文索引 + 强一致 + 生态成熟 | 学习曲线略高 | ✅ |
| MongoDB | Document 模型对消息友好 | 关系操作弱、事务弱 | ❌ |
| SQLite | 零运维 | 并发差、生产不可用 | ❌（仅用于测试） |

**结论**：PostgreSQL 用 JSONB 存富媒体消息块，关系部分（用户、会话）走标准范式。

### 5.2 ER 详图

```
┌─────────────────┐
│     users       │
├─────────────────┤
│ id (PK)         │
│ username (UQ)   │
│ password_hash   │
│ avatar_url      │
│ created_at      │
└────────┬────────┘
         │ 1:N
         │
         ▼
┌─────────────────────┐
│   conversations     │
├─────────────────────┤
│ id (PK)             │
│ user_id (FK)        │◀──── index
│ title               │
│ mode (single|group) │
│ agent_ids (JSONB)   │
│ is_pinned           │
│ is_archived         │
│ last_message_at     │◀──── index (DESC)
│ created_at          │
└──────────┬──────────┘
           │ 1:N
           │
           ▼
┌──────────────────────────┐         ┌─────────────────────┐
│       messages           │         │      agents         │
├──────────────────────────┤         ├─────────────────────┤
│ id (PK)                  │         │ id (PK)             │
│ conversation_id (FK,idx) │         │ user_id (FK, null)  │
│ role                     │         │ name                │
│ agent_id                 │─────────▶ provider            │
│ content (JSONB)          │         │ avatar_url          │
│ reply_to_id (FK self)    │         │ capabilities (JSONB)│
│ status                   │         │ system_prompt       │
│ is_pinned                │         │ config (JSONB)      │
│ created_at (idx)         │         │ is_builtin          │
└──────────────────────────┘         │ created_at          │
                                     └─────────────────────┘
```

### 5.3 DDL（建表语句简化版）

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY,
    username        VARCHAR(64) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    avatar_url      VARCHAR(512),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_username ON users(username);

CREATE TABLE conversations (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(255) NOT NULL,
    mode            VARCHAR(16) NOT NULL CHECK (mode IN ('single','group')),
    agent_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_pinned       BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_conv_user_last_msg ON conversations(user_id, last_message_at DESC);
CREATE INDEX idx_conv_user_flags ON conversations(user_id, is_pinned, is_archived);

CREATE TABLE messages (
    id              UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL CHECK (role IN ('user','agent','system')),
    agent_id        VARCHAR(64),
    content         JSONB NOT NULL DEFAULT '[]'::jsonb,
    reply_to_id     UUID REFERENCES messages(id) ON DELETE SET NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'done',
    is_pinned       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_msg_conv_time ON messages(conversation_id, created_at);

-- 全文搜索（可选）
ALTER TABLE messages ADD COLUMN search_vec tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content::text)) STORED;
CREATE INDEX idx_msg_search ON messages USING GIN(search_vec);

CREATE TABLE agents (
    id              UUID PRIMARY KEY,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(64) NOT NULL,
    provider        VARCHAR(32) NOT NULL,
    avatar_url      VARCHAR(512),
    capabilities    JSONB NOT NULL DEFAULT '[]'::jsonb,
    system_prompt   TEXT,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_builtin      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agents_user_builtin ON agents(user_id, is_builtin);
```

### 5.4 ContentBlock JSONB 示例

存储在 `messages.content` 字段：

```json
[
  {"type": "text", "text": "好的，下面是 Todo 组件代码："},
  {
    "type": "code",
    "language": "tsx",
    "code": "function Todo() {\n  return <div>...</div>\n}"
  },
  {
    "type": "diff",
    "filename": "src/App.tsx",
    "before": "function App() { return null }",
    "after": "function App() { return <Todo /> }"
  },
  {
    "type": "web_preview",
    "url": "https://example.com/preview/abc",
    "title": "Todo App Demo",
    "description": "Live preview"
  }
]
```

### 5.5 索引与性能考虑

| 查询 | 索引 | 复杂度 |
|------|------|--------|
| 用户登录（按 username） | `idx_users_username` | O(log N) |
| 用户的会话列表（按活跃度） | `idx_conv_user_last_msg` | O(log N + K) |
| 会话内消息历史（分页） | `idx_msg_conv_time` | O(log N + K) |
| 消息搜索（全文） | `idx_msg_search` (GIN) | O(K) |
| Agent 列表（按用户） | `idx_agents_user_builtin` | O(log N + K) |

### 5.6 数据保留与清理

| 数据 | 保留策略 |
|------|----------|
| 用户、会话、消息 | 用户主动删除前永久保留 |
| Pending 消息（异常终止） | 后台任务每小时清理 > 1 小时未完成的 |
| Redis 流式缓存 | TTL 5 分钟 |
| JWT | 无服务端存储，靠 `exp` 自然过期 |

---

## 6. Adapter 与 Orchestrator 设计

> ✏️ v1.1（pivot）重写：6.1 / 6.2 升级到 v2 签名；6.3 改为三层 Adapter 分类（External / Builtin / ModelGateway）；6.4 / 6.5 / 6.6 保留并补注 pivot 影响。**完整规范请直接读 [docs/b2/spec/agent-runtime-adapter.spec.md](b2/spec/agent-runtime-adapter.spec.md) 与 [docs/b2/spec/builtin-agent-framework.spec.md](b2/spec/builtin-agent-framework.spec.md)**——本节为架构层概述。

### 6.1 BaseAgentAdapter v2 抽象

**设计目标**：让 B1 完全不感知具体 Agent 类型（外部 runtime / 自建 framework / orchestrator），三类子 Adapter 通过同一接口注册到 AgentRegistry。

```python
# backend/app/agents/base.py（v2）
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from .types import ChatMessage, StreamChunk, ToolSpec


class BaseAgentAdapter(ABC):
    """v2 — Agent Runtime adapter contract."""

    provider: str = ""  # "claude_code" / "codex" / "opencode" / "builtin" / "mock"

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
        workspace_path: Path | None = None,        # ✨ v2 新增
        tool_specs: list[ToolSpec] | None = None,  # ✨ v2 新增
    ) -> AsyncIterator[StreamChunk]:
        """流式返回标准化 chunk（含 tool_call / tool_result）"""
        ...
```

**变更摘要 vs v1**：
- 新增 `workspace_path`：会话沙箱根目录（B1 由 WorkspaceService 创建并注入）
- 新增 `tool_specs`：BuiltinAgent 工具白名单；ExternalAdapter 可忽略
- 关键字参数强制 keyword-only（防止误传）

### 6.2 StreamChunk 协议（v1.1 扩展 tool_call / tool_result）

```python
# backend/app/agents/types.py（v1.1）
class StreamChunk(BaseModel):
    event_type: Literal[
        "start", "block_start", "delta", "block_end",
        "done", "error", "agent_switch", "heartbeat",
        "tool_call",      # ✨ v1.1 新增
        "tool_result",    # ✨ v1.1 新增
    ]
    # ── v1 字段保留 ──
    block_index: int | None = None
    block_type: Literal["text", "code", "diff", "web_preview", "tool_call"] | None = None  # +tool_call
    text_delta: str | None = None
    code_delta: str | None = None
    metadata: dict | None = None
    error: str | None = None
    error_code: str | None = None
    # ── v1.1 tool_call / tool_result ──
    call_id: str | None = None               # 一对 tool_call/tool_result 的关联 id
    tool_name: str | None = None             # tool_call
    tool_arguments: dict | None = None       # tool_call
    tool_status: Literal["ok", "error"] | None = None  # tool_result
    tool_output: str | None = None           # tool_result（已截断）
    tool_output_truncated: bool | None = None
```

**事件配对契约**：

```
tool_call { call_id: "c-001", tool_name: "write_file", tool_arguments: {...} }
   ⋮（同步执行）
tool_result { call_id: "c-001", tool_status: "ok", tool_output: "..." }
```

新增错误码：`tool_call_failed` / `tool_call_orphan` / `workspace_violation` / `mcp_server_down` / `external_runtime_error`。

### 6.3 三类 Adapter 子类（v1.1 新分类）

#### 6.3.A Layer A — ExternalAgentAdapter（嵌入第三方 agent runtime）

```python
# backend/app/agents/external/claude_code.py
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

class ClaudeCodeAdapter(BaseAgentAdapter):
    provider = "claude_code"

    async def stream(self, messages, *, workspace_path, tool_specs=None, **kw):
        yield StreamChunk(event_type="start", agent_id=self.agent_id)
        options = ClaudeAgentOptions(cwd=str(workspace_path), ...)
        async with ClaudeSDKClient(options=options) as client:
            await client.query(_messages_to_prompt(messages))
            async for sdk_event in client.receive_response():
                # 映射 SDK 原生事件 → StreamChunk（含 tool_use → tool_call 等）
                for chunk in map_claude_sdk_event(sdk_event):
                    yield chunk
        yield StreamChunk(event_type="done", agent_id=self.agent_id)
```

- 不自实现 loop / tool registry（由 SDK 提供）
- workspace_path 透传为 SDK 的 `cwd`
- 错误统一映射到标准 error_code

类似的还有 `backend/app/agents/external/codex.py`（基于 `openai-agents` SDK）和 `backend/app/agents/external/opencode.py`（基于 subprocess CLI / JSONL）。

#### 6.3.B Layer B — BuiltinAgentAdapter（团队自建 framework）

```python
# backend/app/agents/builtin/adapter.py
class BuiltinAgentAdapter(BaseAgentAdapter):
    provider = "builtin"

    async def stream(self, messages, *, workspace_path, tool_specs=None, **kw):
        # 1. 注入长期记忆
        recalled = await self.memory.recall(conv_id=...)
        # 2. 合并 tools（native + MCP）
        all_tools = (tool_specs or list(NATIVE_TOOLS.values())) \
                    + await self.mcp_client.list_tools()
        # 3. 启动 AgentLoop
        async for chunk in run_agent_loop(
            messages, all_tools, workspace_path,
            self.model_gateway, merged_config,
        ):
            yield chunk
```

完整 AgentLoop / ToolRegistry / MCPClient 设计见 [docs/b2/spec/builtin-agent-framework.spec.md](b2/spec/builtin-agent-framework.spec.md)。

#### 6.3.C Layer C — ModelGateway（v1 raw LLM Adapter 降级）

```python
# backend/app/agents/model_gateway/__init__.py
class ModelGateway:
    """Provider 无关的模型调用入口（含 tool calling 映射），仅供 BuiltinAgent 内部使用。"""

    BACKEND_MAP = {
        "claude":   ClaudeBackend,    # 原 agents/adapters/claude.py
        "openai":   OpenAIBackend,    # 原 agents/adapters/openai.py
        "deepseek": DeepSeekBackend,  # 原 agents/adapters/deepseek.py
    }

    async def stream(self, messages, tools, config) -> AsyncIterator[StreamChunk]: ...
```

- ❌ 不注册到顶层 AgentRegistry（不是顶层 Agent）
- ✅ retry / timeout / 错误码统一（复用 [docs/b2/spec/model-gateway.spec.md](b2/spec/model-gateway.spec.md)）
- ✅ 新增能力：把 Provider 原生 tool calling 协议（Anthropic `tool_use` / OpenAI `tool_calls`）映射为 `StreamChunk(tool_call)`

### 6.4 ClaudeBackend 实现示意（v1 ClaudeAdapter 迁移而来）

> 📍 v1.1 已迁移到 `backend/app/agents/model_gateway/claude.py`，作为 BuiltinAgent 的可选 LLM 后端。原 v1 代码（基于 `anthropic.AsyncAnthropic.messages.stream`）保留其骨架，**新增**对 Anthropic `tool_use` content block 的解析与 `StreamChunk(tool_call/tool_result)` 映射；retry / timeout / error_code 策略沿用 [model-gateway.spec.md](b2/spec/model-gateway.spec.md)。完整设计见 [builtin-agent-framework.spec.md §6](b2/spec/builtin-agent-framework.spec.md)。

```python
# backend/app/agents/model_gateway/claude.py（伪代码）
class ClaudeBackend:
    async def stream(self, messages, tools, config) -> AsyncIterator[StreamChunk]:
        async with self.client.messages.stream(
            model=config.get("model", "claude-sonnet-4-6"),
            tools=[_tool_spec_to_claude(t) for t in tools],  # ✨ v1.1
            messages=[m.model_dump() for m in messages],
        ) as stream:
            async for event in stream:
                # 把 content_block_start(type="tool_use") → StreamChunk(tool_call)
                # 把 content_block_delta(text) → StreamChunk(delta)
                for chunk in _map_anthropic_event(event):
                    yield chunk
```

### 6.5 StreamingArtifactParser 状态机

```python
# app/agents/artifact_parser.py
class StreamingArtifactParser:
    """
    流式解析 LLM 输出，识别代码围栏 ```lang...```，自动切换 ContentBlock
    
    状态机：
    [TEXT] --(detect "```lang\n")--> [CODE] --(detect "```")--> [TEXT]
    """
    
    def __init__(self):
        self.state = "TEXT"
        self.buffer = ""
        self.block_index = -1
        self.current_lang = None
        self._block_started = False
    
    def feed(self, text: str) -> list[StreamChunk]:
        chunks = []
        self.buffer += text
        
        while True:
            if self.state == "TEXT":
                # 找代码围栏起点
                fence_start = self.buffer.find("```")
                if fence_start == -1:
                    # 没有围栏，全部当文本输出（保留尾部少量 buffer 避免切到围栏中间）
                    if len(self.buffer) > 3:
                        if not self._block_started:
                            chunks.append(self._start_text_block())
                        chunks.append(StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            text_delta=self.buffer[:-3]
                        ))
                        self.buffer = self.buffer[-3:]
                    break
                else:
                    # 输出围栏前的文本
                    if fence_start > 0:
                        if not self._block_started:
                            chunks.append(self._start_text_block())
                        chunks.append(StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            text_delta=self.buffer[:fence_start]
                        ))
                    self.buffer = self.buffer[fence_start:]
                    
                    # 等待完整 "```lang\n"
                    newline = self.buffer.find("\n")
                    if newline == -1: break
                    
                    self.current_lang = self.buffer[3:newline].strip() or "text"
                    self.buffer = self.buffer[newline+1:]
                    
                    if self._block_started:
                        chunks.append(StreamChunk(event_type="block_end", block_index=self.block_index))
                    chunks.append(self._start_code_block(self.current_lang))
                    self.state = "CODE"
            
            elif self.state == "CODE":
                fence_end = self.buffer.find("```")
                if fence_end == -1:
                    if len(self.buffer) > 3:
                        chunks.append(StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            code_delta=self.buffer[:-3]
                        ))
                        self.buffer = self.buffer[-3:]
                    break
                else:
                    if fence_end > 0:
                        chunks.append(StreamChunk(
                            event_type="delta",
                            block_index=self.block_index,
                            code_delta=self.buffer[:fence_end]
                        ))
                    chunks.append(StreamChunk(event_type="block_end", block_index=self.block_index))
                    self.buffer = self.buffer[fence_end+3:]
                    self.state = "TEXT"
                    self._block_started = False
        
        return chunks
    
    def flush(self):
        chunks = []
        if self.buffer:
            event = "delta"
            field = "text_delta" if self.state == "TEXT" else "code_delta"
            chunks.append(StreamChunk(
                event_type=event,
                block_index=self.block_index,
                **{field: self.buffer}
            ))
            self.buffer = ""
        if self._block_started:
            chunks.append(StreamChunk(event_type="block_end", block_index=self.block_index))
        return chunks
    
    def _start_text_block(self):
        self.block_index += 1
        self._block_started = True
        return StreamChunk(event_type="block_start", block_index=self.block_index, block_type="text")
    
    def _start_code_block(self, lang):
        self.block_index += 1
        self._block_started = True
        return StreamChunk(
            event_type="block_start",
            block_index=self.block_index,
            block_type="code",
            metadata={"language": lang}
        )
```

### 6.6 Orchestrator 实现（v1.1 — 子 Agent 升级为真 Agent）

> v1.1 改动：Orchestrator 框架不变，但子 Adapter 通过 BaseAgentAdapter v2 接口拿到，因此现在可以是 ExternalAgentAdapter（Claude Code / Codex / OpenCode）或 BuiltinAgentAdapter；call_id 在跨子 Agent 时按 `task_id.<原 call_id>` 重映射，避免冲突。详见 [orchestrator/core.spec.md](b2/spec/orchestrator/core.spec.md) 与 [agent-runtime-adapter.spec.md §5.3](b2/spec/agent-runtime-adapter.spec.md)。

下面的 v1 代码示意保留以说明框架；实际生产代码见 [backend/app/agents/orchestrator/adapter.py](../backend/app/agents/orchestrator/adapter.py)。


```python
# app/agents/orchestrator.py
class OrchestratorAdapter(BaseAgentAdapter):
    provider = "builtin"
    
    DECOMPOSE_PROMPT = """
你是一个任务分派助手。给定用户的请求，把它拆解成多个子任务，每个子任务指派给一个最合适的 Agent。
可用 Agent 列表：
{agents}

输出格式（严格 JSON）：
{{
  "tasks": [
    {{"agent_id": "claude-code", "task": "..." }},
    ...
  ]
}}
"""
    
    async def stream(self, messages, system_prompt=None, config=None):
        # 1. 从 tasks 或 managed_agent_ids 得到任务计划
        tasks = self._derive_or_parse_tasks(messages, config)
        
        # 2. 输出"任务规划"卡片
        yield StreamChunk(event_type="start")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0,
                          text_delta=f"📋 拆解为 {len(tasks)} 个子任务：\n\n")
        for i, t in enumerate(tasks, 1):
            yield StreamChunk(event_type="delta", block_index=0,
                              text_delta=f"{i}. **@{t['agent_id']}** → {t['task']}\n")
        yield StreamChunk(event_type="block_end", block_index=0)
        
        # 3. 顺序调用子 Adapter
        block_offset = 1
        for task in tasks:
            yield StreamChunk(event_type="block_start", block_index=block_offset,
                              block_type="text")
            yield StreamChunk(event_type="delta", block_index=block_offset,
                              text_delta=f"\n---\n\n💬 **@{task['agent_id']}**\n\n")
            yield StreamChunk(event_type="block_end", block_index=block_offset)
            block_offset += 1
            
            try:
                sub_adapter = registry.get_adapter(task["agent_id"])
                sub_messages = messages + [ChatMessage(role="user", content=task["task"])]
                async for chunk in sub_adapter.stream(sub_messages):
                    if chunk.event_type in ("start", "done"):
                        continue  # 内部事件不外发
                    # 重映射 block_index
                    if chunk.block_index is not None:
                        chunk.block_index += block_offset
                    yield chunk
                block_offset += 10  # 预留空间
            except Exception as e:
                yield StreamChunk(event_type="block_start", block_index=block_offset,
                                  block_type="text")
                yield StreamChunk(event_type="delta", block_index=block_offset,
                                  text_delta=f"⚠️ @{task['agent_id']} 执行失败：{e}\n")
                yield StreamChunk(event_type="block_end", block_index=block_offset)
                block_offset += 1
        
        yield StreamChunk(event_type="done")
```

### 6.7 Adapter 扩展指南（v1.1 — 三类入口）

| 你想新增的是 | 入口 | 步骤摘要 | 详细模板 |
|---|---|---|---|
| 外部 Agent runtime（OpenCode、xxx CLI 等） | `agents/external/<runtime>.py` | 嵌入 SDK/CLI + 映射事件到 StreamChunk（含 tool_*） + 注册到 registry `PROVIDER_MAP` | [CLAUDE.md §7.6](../CLAUDE.md) |
| 自建 Agent 的工具 | `agents/builtin/tools/<tool>.py` | 实现 execute + 校验 + 注册 ToolSpec | [CLAUDE.md §7.7](../CLAUDE.md) |
| 自建 Agent 的 MCP server | `agents/builtin/mcp/` 配置 | 仅 stdio transport；前缀 `mcp_<server>__` | [CLAUDE.md §7.8](../CLAUDE.md) |
| ModelGateway 新 LLM provider | `agents/model_gateway/<provider>.py` | 实现 stream(messages, tools, config)；不要注册到顶层 AgentRegistry | [CLAUDE.md §7.2](../CLAUDE.md) |

> ❌ 不再在 `agents/adapters/` 下新增文件 —— pivot 后该目录将拆分到 `external/` / `builtin/` / `model_gateway/`。

---

## 7. 流式通信架构（SSE）

### 7.1 为什么选 SSE 而非 WebSocket

| 维度 | SSE | WebSocket |
|------|-----|-----------|
| 协议 | 标准 HTTP/1.1 + HTTP/2 | 升级协议（Upgrade: websocket） |
| 方向 | 单向（服务端→客户端） | 双向 |
| 鉴权 | 直接用 HTTP Header（JWT） | 需要在连接建立时单独处理 |
| 重连 | 浏览器原生支持 | 需要手动实现 |
| 代理/CDN | 通常友好（HTTP） | 需要特殊配置 |
| LLM 场景 | ✅ 完美匹配 | ❌ 过度设计 |
| 学习成本 | 低 | 中 |

**结论**：LLM 流式响应是单向场景，SSE 是行业标准（OpenAI / Anthropic / Google 都用 SSE）。

### 7.2 SSE 端点实现

```python
# app/api/v1/stream.py
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/messages/{message_id}/stream")
async def stream_message(
    message_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. 权限校验
    message = await message_service.get_for_user(db, user, message_id)
    if message.status not in ("pending", "streaming"):
        # 已完成的消息：直接返回完整内容（用于刷新场景）
        return EventSourceResponse(_replay_done_message(message))
    
    # 2. 标记为 streaming
    await message_service.mark_streaming(db, message_id)
    
    # 3. 组装上下文
    history = await context_builder.build(db, message.conversation_id)
    
    # 4. 拿 Adapter
    adapter = registry.get_adapter(message.agent_id, db=db)
    agent_config = await agent_service.get_config(db, message.agent_id)
    
    async def event_gen():
        accumulator = ContentAccumulator()
        try:
            async for chunk in adapter.stream(history, system_prompt=None, config=agent_config):
                # 客户端断开检测
                if await request.is_disconnected():
                    break
                accumulator.feed(chunk)
                yield chunk.to_sse_data()
            
            # 持久化最终内容
            await message_service.finalize(
                db, message_id,
                content=accumulator.to_blocks(),
                status="done"
            )
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            await message_service.mark_error(db, message_id, str(e))
    
    return EventSourceResponse(event_gen())
```

### 7.3 ContentAccumulator 设计

流式过程中实时累积内容到内存，结束时一次性写 DB：

```python
class ContentAccumulator:
    def __init__(self):
        self.blocks: list[dict] = []  # 当前已完成的块
        self.current: dict | None = None  # 正在构建的块
    
    def feed(self, chunk: StreamChunk):
        if chunk.event_type == "block_start":
            self.current = {
                "type": chunk.block_type,
                **(chunk.metadata or {}),
            }
            if chunk.block_type == "text":
                self.current["text"] = ""
            elif chunk.block_type == "code":
                self.current["code"] = ""
                self.current["language"] = chunk.metadata.get("language", "text")
        
        elif chunk.event_type == "delta" and self.current:
            if chunk.text_delta:
                self.current["text"] = self.current.get("text", "") + chunk.text_delta
            if chunk.code_delta:
                self.current["code"] = self.current.get("code", "") + chunk.code_delta
        
        elif chunk.event_type == "block_end" and self.current:
            self.blocks.append(self.current)
            self.current = None
    
    def to_blocks(self) -> list[dict]:
        if self.current:  # flush 未关闭的块
            self.blocks.append(self.current)
        return self.blocks
```

### 7.4 客户端 SSE 消费

```typescript
// frontend/src/hooks/useStream.ts
import { useEffect, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';

export function useMessageStream(messageId: string | null) {
  const [blocks, setBlocks] = useState<ContentBlock[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');
  
  useEffect(() => {
    if (!messageId) return;
    const ctrl = new AbortController();
    
    fetchEventSource(`/api/v1/messages/${messageId}/stream`, {
      headers: { Authorization: `Bearer ${getToken()}` },
      signal: ctrl.signal,
      onmessage(ev) {
        const data = JSON.parse(ev.data);
        switch (ev.event) {
          case 'start':
            setStatus('streaming');
            break;
          case 'block_start':
            setBlocks(prev => [...prev, initBlock(data)]);
            break;
          case 'delta':
            setBlocks(prev => applyDelta(prev, data));
            break;
          case 'block_end':
            break;
          case 'done':
            setStatus('done');
            ctrl.abort();
            break;
          case 'error':
            setStatus('error');
            ctrl.abort();
            break;
        }
      },
      onerror(err) {
        setStatus('error');
        throw err; // 阻止重连
      },
    });
    
    return () => ctrl.abort();
  }, [messageId]);
  
  return { blocks, status };
}
```

> **为什么用 `@microsoft/fetch-event-source` 而非原生 `EventSource`？**
> 原生 EventSource 不支持自定义 Header（JWT 无法传），且必须 GET。该库基于 fetch 实现，支持完整 HTTP 控制。

### 7.5 SSE 反向代理配置

**Nginx 配置（必须）**：

```nginx
location /api/v1/messages/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;          # ★ 关闭缓冲，立即转发
    proxy_cache off;              # ★ 关闭缓存
    proxy_read_timeout 24h;       # 长连接保活
    chunked_transfer_encoding on;
}
```

---

## 8. 安全架构

### 8.1 认证（Authentication）

**方案**：JWT Bearer Token

```
1. 注册：username + password → DB 存 bcrypt 哈希
2. 登录：校验密码 → 签发 JWT
3. 后续请求：Authorization: Bearer <jwt>
4. FastAPI 依赖 get_current_user 解析 JWT → 注入 User 对象
```

**Token 内容**：
```json
{
  "sub": "<user_uuid>",
  "exp": 1234567890,
  "iat": 1234567890
}
```

**安全要点**：
- JWT 密钥从环境变量读取，至少 32 字节随机串
- HS256 算法（对称）足够，单服务无需 RS256
- 过期时间：7 天（可配置）
- 不存 Refresh Token（MVP 简化），过期后重新登录

### 8.2 授权（Authorization）

**策略**：基于资源所有权（Owner-based）

```python
async def get_conversation_for_user(db, user, conv_id):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Not found")
    if conv.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    return conv
```

每个 Service 方法的第一步都是验证当前用户对资源有权限。

### 8.3 密码存储

**方案**：bcrypt（passlib）

```python
from passlib.context import CryptContext
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)
```

- bcrypt 自带 salt，无需手动管理
- cost factor 默认 12（耗时 ~250ms，可承受）

### 8.4 输入校验

**FastAPI + Pydantic v2**：
- 所有请求 body 用 Pydantic Schema 校验
- 路径参数 / Query 参数自动按类型转换
- 校验失败自动返回 422 + 详细错误

**额外校验**：
- 用户名：3-32 字符，字母数字下划线
- 密码：至少 8 字符
- 消息内容：单条 ≤ 32KB（防滥用）
- System Prompt：≤ 8KB

### 8.5 防 Prompt 注入

| 风险 | 应对 |
|------|------|
| 用户消息中包含"忽略之前指令" | LLM Provider 自带防护 + System Prompt 与用户消息严格分离 |
| 用户消息中包含特殊控制字符 | 不做特殊处理（信任 LLM） |
| 自定义 Agent 的 System Prompt 包含恶意指令 | 仅作用于自己，无影响 |

### 8.6 CORS 配置

```python
# app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # 配置具体域名，不要 *
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### 8.7 速率限制（可选）

```python
# 使用 slowapi（基于 starlette + limits）
from slowapi import Limiter
limiter = Limiter(key_func=lambda req: req.state.user.id)

@router.post("/messages", dependencies=[Depends(limiter.limit("60/minute"))])
async def send_message(...): ...
```

### 8.8 安全检查清单

- [ ] 不在日志中打印密码、JWT
- [ ] 数据库连接使用 asyncpg 参数化查询（默认防 SQL 注入）
- [ ] 所有上游 LLM API Key 仅在后端，不传到前端
- [ ] Docker 镜像不包含 `.env`
- [ ] 生产环境 `JWT_SECRET` ≠ 示例值
- [ ] HTTPS 启用（生产）

---

## 9. 前端架构

### 9.1 前端分层

```
┌──────────────────────────────────────────────────┐
│  Pages / Routes                                   │
│  (LoginPage, ChatPage, AgentsPage)               │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  Composite Components                             │
│  (ChatWindow, ConversationList, MessageList)     │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  Atomic Components                                │
│  (TextBlock, CodeBlock, AgentAvatar, Button)     │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  Hooks（业务逻辑）                                  │
│  (useConversations, useStream, useAgents)        │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  State (Zustand) + Server State (TanStack Query) │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  API Client / SSE Client                          │
└──────────────────────────────────────────────────┘
```

### 9.2 状态管理策略

| 数据 | 工具 | 理由 |
|------|------|------|
| JWT、用户信息 | Zustand + localStorage | 全局、持久化 |
| 服务端列表数据（会话、Agent） | TanStack Query | 自动缓存、重新验证、乐观更新 |
| UI 状态（当前选中会话、输入框文本） | Zustand | 全局但不持久化 |
| 流式消息 | useStream Hook 内部 useState | 局部状态，组件卸载即销毁 |
| 表单 | react-hook-form（可选） | 轻量 |

### 9.3 路由设计

```tsx
// router.tsx
<BrowserRouter>
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<AuthGuard><AppLayout /></AuthGuard>}>
      <Route path="/" element={<Navigate to="/chat" />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/chat/:conversationId" element={<ChatPage />} />
      <Route path="/agents" element={<AgentsPage />} />
      <Route path="/agents/new" element={<NewAgentPage />} />
    </Route>
  </Routes>
</BrowserRouter>
```

### 9.4 组件树（核心页面）

```
ChatPage
├── AppLayout
│   ├── Sidebar
│   │   ├── UserMenu
│   │   ├── SearchBar
│   │   ├── ConversationList
│   │   │   └── ConversationItem (× N)
│   │   └── NewConversationButton
│   │       └── NewConversationDialog (modal)
│   └── ChatWindow
│       ├── ChatHeader (会话标题 + Agent 头像)
│       ├── MessageList
│       │   └── MessageBubble (× N)
│       │       └── ContentRenderer
│       │           ├── TextBlock
│       │           ├── CodeBlock
│       │           ├── DiffBlock
│       │           ├── WebPreviewCard
│       │           └── FileAttachment
│       └── MessageInput
│           ├── AgentMentionPicker (群聊时)
│           └── SendButton
```

### 9.5 ContentRenderer 动态分发

```tsx
// components/chat/ContentRenderer.tsx
const BLOCK_COMPONENTS = {
  text: TextBlock,
  code: CodeBlock,
  diff: DiffBlock,
  web_preview: WebPreviewCard,
  file: FileAttachment,
} as const;

export function ContentRenderer({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <>
      {blocks.map((block, i) => {
        const Comp = BLOCK_COMPONENTS[block.type];
        if (!Comp) return <UnknownBlock key={i} block={block} />;
        return <Comp key={i} {...block} />;
      })}
    </>
  );
}
```

### 9.6 跨平台策略

| 目标平台 | 方案 | 改动量 |
|----------|------|--------|
| **Web** | Vite 直接 `pnpm build` 部署到 CDN | 0 |
| **桌面（macOS/Win/Linux）** | Tauri 包装 dist/ 目录 | 加 `src-tauri/` 配置（~50 行） |
| **移动（iOS/Android）** | Capacitor 包装 dist/ 目录 | 加 `capacitor.config.json` |
| **PWA** | Vite PWA 插件 | 加 `manifest.json` + Service Worker |

**核心**：所有平台共用一份 React 代码，因为 Tauri/Capacitor 都是 WebView 包装。

### 9.7 性能优化要点

- **虚拟列表**：消息超过 100 条时启用 `@tanstack/react-virtual`
- **代码懒加载**：路由级别 `React.lazy` + Suspense
- **shiki 按需加载语言**：只加载用户实际遇到的语言包
- **React.memo 包装 MessageBubble**：流式更新时只重渲染当前消息
- **图片懒加载**：`loading="lazy"`

---

## 10. 部署架构

### 10.1 本地开发

```
┌────────────────────────────────────────────────────┐
│  开发者机器                                          │
│                                                     │
│  ┌──────────────┐   ┌──────────────────────────┐  │
│  │ Vite Dev     │   │  docker-compose          │  │
│  │ Server :5173 │──▶│  ├ postgres :5432         │  │
│  └──────────────┘   │  ├ redis :6379            │  │
│                     │  └ backend :8000          │  │
│                     └──────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

`vite.config.ts` 配置代理：
```ts
server: {
  proxy: {
    '/api': 'http://localhost:8000',
  }
}
```

### 10.2 单机部署（演示）

```
┌─────────────────────────────────────────────────────┐
│  单机 Docker Host                                    │
│                                                      │
│  ┌─────────────┐   ┌──────────────┐                │
│  │  Caddy      │──▶│  backend     │                │
│  │  (TLS+静态) │   │  (FastAPI)   │                │
│  │  :80/:443   │   │  :8000        │                │
│  └─────────────┘   └──────┬───────┘                │
│         │                  │                        │
│         │ static dist/     ▼                        │
│         │            ┌──────────┐  ┌─────────┐    │
│         │            │ postgres │  │ redis   │    │
│         │            └──────────┘  └─────────┘    │
└─────────────────────────────────────────────────────┘
```

### 10.3 docker-compose.yml（核心）

```yaml
version: '3.9'
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: agenthub
      POSTGRES_USER: agenthub
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "agenthub"]
      interval: 5s
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://agenthub:${DB_PASSWORD}@postgres:5432/agenthub
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: ${JWT_SECRET}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    ports: ["8000:8000"]
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_started }
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

volumes:
  pgdata:
```

### 10.4 生产部署考虑（仅作架构预留，MVP 不实现）

- 多实例：FastAPI 后端可水平扩展（无状态），用 Nginx/Caddy LB
- SSE 多实例：需要 Redis Pub/Sub 在多实例间转发 stream 事件
- 数据库：管理服务（RDS / Cloud SQL）+ 读写分离
- 监控：Sentry（错误）+ Prometheus（指标）+ Grafana（可视化）

---

## 11. 性能与扩展性

### 11.1 性能基线（MVP 目标）

| 指标 | 目标 | 实际测试 |
|------|------|---------|
| API P95 响应（非 SSE） | < 200ms | 待测 |
| SSE 首字节延迟 | < 2s（受上游 LLM 影响） | 待测 |
| 前端首屏（本地） | < 2s | 待测 |
| 单会话 1000 条消息加载 | < 1s（分页 50 条/次） | 待测 |
| 数据库单表 100 万消息查询 | < 100ms（有索引） | 待测 |

### 11.2 扩展性预留

| 维度 | 当前 | 扩展路径 |
|------|------|---------|
| 用户并发 | 单实例 ~100 并发 | 加实例 + LB |
| 数据库 | 单 PG 实例 | 主从读写分离 → 分库分表（按 user_id） |
| SSE 连接数 | 单实例 ~10K（受 fd 限制） | 多实例 + Redis Pub/Sub |
| LLM 调用 | 直接调上游 | 加 Provider 内部 LB + 重试 + 熔断 |
| 文件附件 | 暂存本地 | 接 S3 / OSS |

### 11.3 瓶颈分析

| 潜在瓶颈 | 影响 | 缓解措施 |
|---------|------|---------|
| LLM API 速率限制 | 用户感知慢 | 多 Provider 切换 + 队列 + 用户友好提示 |
| 大会话上下文 | Token 超限 / 慢 | Context Builder 滑动窗口 + 摘要压缩 |
| 消息表数据膨胀 | 查询慢 | 分区表（按月）/ 归档 |
| SSE 长连接占用 | 内存 / 连接数 | 客户端断开检测 + 超时 |

---

## 12. 可观测性

### 12.1 日志

**后端**（structlog 结构化 JSON 日志）：

```python
import structlog
logger = structlog.get_logger()

logger.info("message_streamed",
            message_id=str(msg.id),
            agent_id=msg.agent_id,
            duration_ms=elapsed,
            tokens=token_count)
```

**关键日志事件**：
- 用户登录 / 注册
- 消息发送 / 完成 / 错误
- SSE 连接建立 / 断开
- LLM API 调用（含耗时、token）
- 错误（含堆栈）

### 12.2 指标（可选）

如有时间，接入 Prometheus 暴露：
- `http_requests_total{path, status}`
- `sse_active_connections`
- `llm_api_duration_seconds{provider, model}`
- `messages_created_total{role}`

### 12.3 错误追踪

- MVP：终端 + 日志文件
- 生产：Sentry SDK 自动捕获异常

---

## 13. 技术决策记录（ADR）

> ADR：Architecture Decision Record，重要技术选型的决策记录

### ★ ADR-007（v1.1）：Agent Runtime Pivot

- **状态**：Accepted（2026-05-26）
- **决策**：Agent 层重新分为三层（ExternalAgentAdapter / BuiltinAgent Framework / ModelGateway 底座）；BaseAgentAdapter v2 接口升级（新增 workspace_path / tool_specs）；StreamChunk 新增 tool_call / tool_result 事件；引入 Workspace 沙箱
- **理由**：PDF 课题要求接入 Claude Code / Codex / OpenCode 等真 agent runtime，并支持自建 Agent，而 v1 实现的是 raw LLM API 包装
- **影响**：扩大了 ADR-001（SSE）与 ADR-004（Adapter 协议翻译）的适用面；新增三份 spec 文档支撑
- **完整 ADR**：[docs/spec/agent-runtime-pivot.adr.md](spec/agent-runtime-pivot.adr.md)
- **配套规范**：[agent-runtime-adapter.spec.md](b2/spec/agent-runtime-adapter.spec.md) / [builtin-agent-framework.spec.md](b2/spec/builtin-agent-framework.spec.md) / [workspace-sandbox.spec.md](b1/spec/workspace-sandbox.spec.md)

> ADR-001 ~ ADR-006 为 v1.0 历史决策，仍然生效。

### ADR-001：选择 SSE 而非 WebSocket
- **背景**：需要把 LLM 流式响应推给前端
- **选项**：SSE / WebSocket / Long Polling
- **决策**：SSE
- **理由**：单向流场景、HTTP 标准、原生重连、生态一致
- **后果**：前端需用 `fetch-event-source` 支持自定义 Header

### ADR-002：选择 React + Vite 而非 Next.js
- **背景**：需要 IM 风格交互 + 三端部署
- **选项**：Next.js / React + Vite / Vue
- **决策**：React + Vite
- **理由**：SPA 简单、Tauri/Capacitor 包装直接、避免 SSR 复杂性
- **后果**：需自行配置静态资源、SEO 暂不考虑

### ADR-003：消息 content 用 JSONB 而非额外表
- **背景**：消息包含多种类型块（text/code/diff/preview）
- **选项**：JSONB 字段 / 多表关联（messages + content_blocks）
- **决策**：JSONB
- **理由**：MVP 阶段查询模式简单（按消息 ID 取全部块），JSONB 性能足够
- **后果**：未来若需按块类型聚合统计，需要再迁移

### ADR-004：Adapter 用"事件翻译"而非"完美抽象"
- **背景**：需要接入 Claude Code / Codex / OpenCode 等 agent runtime，同时保留 BuiltinAgent + ModelGateway。
- **选项**：完美抽象（所有 runtime 接口完全一致） / 事件翻译（统一 BaseAgentAdapter v2 + StreamChunk，差异在 adapter 内映射）
- **决策**：事件翻译
- **理由**：不同 runtime 的 tool/edit/bash/MCP 事件模型差异大，强行抽象会丢失能力；统一输出 `StreamChunk` 能稳定服务 B1/F。
- **后果**：每个 Adapter 内部实现差异较大，但对外事件契约一致。

### ADR-005：Orchestrator 先走结构化任务计划，真实 runtime 由 registry 注入
- **背景**：需要把用户请求拆成多个子任务分派，并能调度 ExternalAgentAdapter / BuiltinAgentAdapter。
- **选项**：纯 Prompt 输出 JSON / function calling / 显式 tasks 注入 / ReAct
- **决策**：MVP 支持显式 tasks / managed_agent_ids 生成任务计划，后续可用 BuiltinAgent + ModelGateway 增强拆解。
- **理由**：先保证 registry 接线、call_id 重映射和失败降级可测；避免早期绑定单一 Provider 的 function calling。
- **后果**：B2-20 已接通真实 runtime adapter factory；真实 LLM 任务拆解可作为后续增强。

### ADR-006：MVP 不引入 Refresh Token
- **背景**：JWT 安全 vs 易用性
- **决策**：单一长期 access_token（7 天）
- **理由**：MVP 简化，比赛场景无敏感生产数据
- **后果**：用户每周需重新登录一次

---

## 14. 演进路线

### Phase 1（当前 MVP，14 天）
- ✅ IM 核心体验
- ✅ Claude + OpenAI 适配
- ✅ Orchestrator 基础版
- ✅ 富媒体预览（Text/Code/Diff/WebPreview）

### Phase 2（P1，2-3 周）
- 🟡 部署发布（一键 Vercel/静态站点）
- 🟡 Tauri 桌面端打包
- 🟡 PWA / 移动端体验优化
- 🟡 Orchestrator 任务图可视化
- 🟡 内置 Skill 市场

### Phase 3（生产化，1-2 个月）
- 🟢 多用户协作（团队空间、共享会话）
- 🟢 第三方 OAuth 登录
- 🟢 用量计费 / 配额管理
- 🟢 完善监控告警
- 🟢 多模态（图片、语音输入）

### Phase 4（开放生态，长期）
- 🟢 第三方 Agent SDK
- 🟢 插件市场（用户上传自定义工具）
- 🟢 MCP（Model Context Protocol）适配
- 🟢 本地模型支持（Ollama）

---

## 附录 A：架构图工具说明

本文档所有架构图均用 ASCII 绘制，便于 Git diff 与 AI 协作。
正式答辩时可用以下工具重绘为图片：
- [Excalidraw](https://excalidraw.com) - 手绘风格
- [Mermaid](https://mermaid.live) - 文本驱动
- [draw.io](https://app.diagrams.net) - 通用流程图

## 附录 B：参考资料

### 框架文档
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Pydantic v2](https://docs.pydantic.dev/)
- [React 18](https://react.dev)
- [Vite](https://vite.dev)
- [TanStack Query](https://tanstack.com/query/latest)
- [Zustand](https://zustand-demo.pmnd.rs/)

### LLM SDK
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [OpenAI Python SDK](https://github.com/openai/openai-python)

### 流式与 SSE
- [SSE Starlette](https://github.com/sysid/sse-starlette)
- [@microsoft/fetch-event-source](https://github.com/Azure/fetch-event-source)

### 跨平台
- [Tauri](https://tauri.app)
- [Capacitor](https://capacitorjs.com)

### 设计参考
- [shadcn/ui](https://ui.shadcn.com)
- [Tailwind CSS](https://tailwindcss.com)
