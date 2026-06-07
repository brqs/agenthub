# AgentHub 项目开发方案（Development Plan）

> 课题：AgentHub - 多 Agent 协作平台
> 文档版本：v1.1（Agent Runtime Pivot）
> 最后更新：2026-05-26

> ⚠️ **2026-05-26 Agent Runtime Pivot 生效**：PDF 课题要求接入"Claude Code / Codex / OpenCode 等 agent runtime + 用户自建 Agent"，与 v1.0 计划"raw LLM Adapter 包装"存在错配。Adapter 接口、StreamChunk 协议、Agent 层分类已升级；新增 Workspace 沙箱。完整决策见 [docs/spec/agent-runtime-pivot.adr.md](spec/agent-runtime-pivot.adr.md)。
>
> 本文档已就地同步的章节：§3 MoSCoW / §4.1 技术栈 / §5 系统架构（§5.2 数据流注解）/ §8 关键技术方案 / §13 里程碑。其他章节（§6 数据模型 / §7 API / §9-12 / §14-16）保持 v1.0；新增能力（Workspace 表 / Artifact API / SSE tool_* 事件 / ToolCallBlock）将在 Sprint 5 Day 1-2 由对应 owner 增量更新到 §6 / §7。

---

## 目录

1. [项目概述](#1-项目概述)
2. [目标与交付物](#2-目标与交付物)
3. [产品功能范围（MoSCoW）](#3-产品功能范围moscow)
4. [技术栈选型与理由](#4-技术栈选型与理由)
5. [系统架构设计](#5-系统架构设计)
6. [数据模型设计](#6-数据模型设计)
7. [API 设计](#7-api-设计)
8. [关键技术方案](#8-关键技术方案)
9. [项目目录结构](#9-项目目录结构)
10. [开发环境与工具链](#10-开发环境与工具链)
11. [开发流程规范](#11-开发流程规范)
12. [AI 协作规范（Vibe Coding）](#12-ai-协作规范vibe-coding)
13. [里程碑与时间线](#13-里程碑与时间线)
14. [风险与应对](#14-风险与应对)
15. [验收与测试方案](#15-验收与测试方案)
16. [答辩准备](#16-答辩准备)

---

## 1. 项目概述

### 1.1 项目定位

**AgentHub** 是一个**以 IM 聊天为核心交互范式**的多 Agent 协作平台。用户通过类似微信/飞书的对话界面，与不同的 AI Agent（Claude Code、Codex、OpenCode、自建 Agent 等）进行 1v1 单聊或多 Agent 群聊，由主 Agent（Orchestrator）自动协调分工，Agent 的回复以富媒体卡片（代码块、Diff、网页预览、文件附件）形式内联展示。

### 1.2 核心价值主张

| 维度 | 价值 |
|------|------|
| **交互直觉** | IM 范式人人熟悉，零学习成本即可与多个 AI 协作 |
| **多 Agent 协同** | Orchestrator 自动拆解任务，多 Agent 像群聊成员一样接力完成复杂工作 |
| **产物可视化** | 代码、网页、Diff 等产物内联预览，告别"复制粘贴看效果"的工作流 |
| **生态开放** | 统一 Adapter 屏蔽底层 API 差异，主流 Agent 即插即用 + 支持自建 |

### 1.3 团队配置

| 角色 | 人数 | 职责 |
|------|------|------|
| **F**（Frontend） | 1 | React SPA、IM 聊天界面、富媒体渲染、SSE 消费 |
| **B1**（Backend Core） | 1 | FastAPI 骨架、认证、会话/消息存储、SSE 端点、上下文组装 |
| **B2**（Agent Integration） | 1 | Adapter 抽象、Claude/OpenAI 适配器、Orchestrator、产物解析 |

---

## 2. 目标与交付物

### 2.1 比赛交付物

| 编号 | 交付物 | 备注 |
|------|--------|------|
| 1 | **产品设计文档** | `docs/product-design.md` —— 用户场景、功能流程、UI 草图 |
| 2 | **技术文档** | `docs/tech-architecture.md` + `docs/api-spec.md` —— 架构图、API、关键决策 |
| 3 | **可运行 Demo** | Docker Compose 一键启动，覆盖单聊 + 群聊 + 产物预览 |
| 4 | **AI 协作开发记录** | `docs/ai-collaboration-log.md` —— Spec/Skill/Rules 沉淀（30% 权重核心） |
| 5 | **3 分钟 Demo 视频** | 展示端到端核心流程，含群聊 Orchestrator 演示 |

### 2.2 评分权重对应策略

| 维度 | 权重 | 我们的策略 |
|------|------|-----------|
| **AI 协作能力** | 30% | 沉淀完整的 CLAUDE.md / Spec 文档 / Cursor Rules / 每模块开发前的 AI Prompt 记录 |
| **功能完整度** | 25% | P0 全部跑通：登录、单聊、群聊 Orchestrator、流式响应、产物预览 |
| **生成效果质量** | 20% | shadcn/ui 现代 UI、流畅动画、代码高亮、Diff 视图、骨架屏 Loading |
| **代码理解度** | 15% | 答辩前每人写一份"我负责模块的 5 分钟讲稿" |
| **创新与产品感** | 10% | Orchestrator 任务图可视化、内置 Skill 市场、Tauri 桌面端 |

---

## 3. 产品功能范围（MoSCoW）

> v1.1 已根据 [ADR-001 Agent Runtime Pivot](spec/agent-runtime-pivot.adr.md) 重新校准 P0。原 v1.0 中"接入 LLM Provider"已被"接入 Agent Runtime + 自建 Framework"取代。

### 3.1 Must Have（P0 —— 必须实现）

#### 平台基础（Sprint 1-4 已交付，pivot 后继续生效）
- ✅ JWT 用户认证（注册、登录）
- ✅ 会话管理：新建、列表、置顶、归档、删除
- ✅ 单聊模式：1v1 与单个 Agent 对话
- ✅ 群聊模式：@ 多 Agent，Orchestrator 协调
- ✅ 流式响应（SSE）：Agent 逐字回复
- ✅ 上下文连续：自动携带历史消息
- ✅ 富媒体消息：文本、代码块（高亮）
- ✅ Docker Compose 一键启动

#### Agent Runtime（v1.1 — pivot 后核心）
- 🆕 **外部 Agent Runtime 接入**：Claude Code（Claude Agent SDK 嵌入）+ Codex（OpenAI Agents SDK 嵌入）+ OpenCode（subprocess CLI 嵌入），通过统一 BaseAgentAdapter v2 屏蔽差异
- 🆕 **自建 Agent Framework MVP**：AgentLoop（model_call → tool_call → observe → loop）+ ToolRegistry 三件套（read_file / write_file / bash）+ 1 个 MCP server（filesystem，stdio）+ MemoryManager + ContextManager
- 🆕 **Workspace 沙箱**：每会话一个隔离目录，所有 Agent 在其中读写文件；路径校验拒绝越界
- 🆕 **产物实时预览**：HTML → iframe（带 CSP sandbox）、文本/代码 → 高亮渲染
- 🆕 **产物二次编辑**：Monaco 编辑器修改后回写 workspace 并自动续聊
- 🆕 Agent 注册表：顶层 provider 使用 `claude_code` / `codex` / `opencode` / `builtin` / `mock`，并保留 `orchestrator` 特例；用户可对话式创建自建 Agent（设定 System Prompt + 工具白名单）

### 3.2 Should Have（P1 —— 应该实现）

- 🟡 代码 Diff 视图、网页预览卡（已交付）
- 🟡 消息搜索、Pin 关键消息（已交付）
- 🟡 ToolCallBlock 折叠卡片（pivot 必须，归入 P0）
- 🟡 Orchestrator 任务卡升级（工具次数 + 产物文件列表）
- 🟡 复制代码、重新生成、引用消息（已交付）

### 3.3 Could Have（P2 —— 可以实现）

- 🟢 一键部署产物（静态站点） —— 演示时口述
- 🟢 MCP HTTP transport / 多 server 路由
- 🟢 BuiltinAgent 并行 tool 调用、向量记忆检索
- 🟢 Tauri 桌面端打包
- 🟢 PPT/文档产物预览
- 🟢 版本历史

### 3.4 Won't Have（暂不实现）

- ❌ 多用户协作、团队管理
- ❌ 移动端原生 App
- ❌ Agent 计费、配额管理
- ❌ Docker per-conversation 隔离（workspace 用宿主机目录 + 路径校验）
- ❌ Workspace 资源配额（CPU / 内存 / 字节）
- ❌ CI/CD 流水线

---

## 4. 技术栈选型与理由

### 4.1 总览

| 层级 | 选型 | 理由 |
|------|------|------|
| **前端框架** | React 18 + Vite + TypeScript | SPA 利于 IM 实时场景；Tauri/Capacitor 可包装实现三端 |
| **UI 组件库** | Tailwind CSS + shadcn/ui | 现代化、可定制性强、与 AI 协作友好（AI 熟悉 shadcn API） |
| **前端状态** | Zustand + TanStack Query | Zustand 管 UI 状态，TanStack Query 管服务端数据缓存与同步 |
| **路由** | React Router v6 | 业界标准，文档齐全 |
| **代码渲染** | react-markdown + shiki | Markdown + 高质量代码高亮 |
| **Diff 渲染** | react-diff-viewer-continued | 现代 Diff 视图组件 |
| **后端框架** | Python 3.11 + FastAPI + Uvicorn | 原生 async、自动 OpenAPI 文档、SSE 完善 |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic | 业界标准，async 支持完善 |
| **数据校验** | Pydantic v2 | FastAPI 内置，性能强 |
| **数据库** | PostgreSQL 15 | JSONB 存富媒体消息块、全文索引 |
| **缓存/Pub-Sub** | Redis 7 | SSE 多实例分发、会话上下文缓存 |
| **认证** | python-jose（JWT） + passlib（bcrypt） | 简单 JWT 即可，无需复杂 OAuth |
| **Agent Runtime（v1.1）** | `claude-agent-sdk` + `openai-agents` + `mcp`（Python SDK，stdio） | 嵌入第三方 agent runtime，复用其内置 loop / tool / MCP；自建 Agent 通过 mcp client 接入 stdio server |
| **Model Gateway（v1.1）** | `anthropic` + `openai`（仅 BuiltinAgent 内部） | 提供 tool calling 协议映射；不再作为顶层 Agent |
| **实时通信** | SSE (Server-Sent Events) — v1.1 扩展 tool_call / tool_result 事件 | LLM 流式响应标准方案，HTTP/2 友好，比 WebSocket 简单 |
| **包管理** | 后端：`uv` 或 `poetry` / 前端：`pnpm` | 性能与依赖管理最佳实践 |
| **代码质量** | 后端：`ruff` + `mypy` / 前端：`eslint` + `prettier` | 自动化代码风格统一 |
| **测试** | 后端：`pytest` + `httpx` / 前端：`vitest` + `@testing-library` | 业界标准 |
| **本地开发** | Docker Compose | 一键起 Postgres + Redis + 后端 |
| **API 契约** | OpenAPI 3.0 + `openapi-typescript` | 前后端共享契约，自动生成 TS 类型 |

### 4.2 关键决策记录

#### 为什么选 SSE 而非 WebSocket？
- LLM 流式响应是**单向**的（服务端 → 客户端）
- SSE 基于标准 HTTP，无需 sticky session、无 CDN 兼容问题
- 浏览器原生 `EventSource` API 自带重连
- Anthropic、OpenAI 官方流式 API 都用 SSE，生态一致
- WebSocket 适合**双向实时**场景（如多人协作编辑），本项目用不上

#### 为什么选 React + Vite 而非 Next.js？
- IM 应用核心是**长连接 + 实时状态**，SSR 价值低
- Vite 启动快、HMR 体验好，更适合 vibe coding 迭代
- 纯 SPA 易于用 Tauri/Capacitor 包装实现桌面端、移动端（**满足三端部署需求**）
- 不引入 Server Component / Server Action 的心智负担

#### 为什么选 FastAPI 而非 Django？
- 原生 async 支持，对 LLM 流式响应至关重要
- 自动生成 OpenAPI 文档，与前端 TS 类型生成无缝衔接
- 轻量、启动快，不需要 Django Admin 等重量级功能
- Pydantic v2 数据校验性能比 DRF Serializer 高一个数量级

#### 为什么用 PostgreSQL 而非 MongoDB？
- 富媒体消息块用 JSONB 存储，PG 的 JSONB 性能与 Mongo 相当
- 关系型场景（用户 → 会话 → 消息）天然适合 PG
- 全文搜索可直接用 PG 的 `tsvector`，无需额外引入 ES

---

## 5. 系统架构设计

### 5.1 整体架构图

> v1.1 关键变化：在 FastAPI 与外部 AI Provider 之间插入三层 Agent Runtime（External / Builtin / ModelGateway）；新增 Workspace 沙箱与 Artifact API；前端新增 ToolCallBlock + ArtifactPreview + Monaco 编辑器。完整架构请直接读 [docs/tech-architecture.md §3 / §6](tech-architecture.md)。

```
┌───────────────────────────────────────────────────────────────┐
│                         浏览器 / Tauri 桌面端                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              React 18 + Vite SPA (前端 F)                │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │ │
│  │  │ 会话列表  │  │ 聊天窗口  │  │ 富媒体消息块（+ToolCall│ │
│  │  │ Sidebar  │  │ ChatWin  │  │  +ArtifactPreview）   │ │ │
│  │  └──────────┘  └──────────┘  └──────────────────────┘ │ │
│  │       │             │                  │                │ │
│  │       └─ TanStack Query (REST) ─┐      │                │ │
│  │                                 ▼      ▼                │ │
│  └────────────────────────  EventSource (SSE) ─────────────┘ │
└──────────────────────────────────│────────────────────────────┘
                                   │  HTTPS
┌──────────────────────────────────▼────────────────────────────┐
│              FastAPI Backend (Uvicorn + Async)                 │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │   API Layer (B1)         │  │  Agent Layer (B2)        │ │
│  │  ┌────────────────────┐ │  │  ┌────────────────────┐  │ │
│  │  │ /auth (JWT)        │ │  │  │ Orchestrator       │  │ │
│  │  │ /conversations     │ │  │  │  ├─ Task Splitter  │  │ │
│  │  │ /messages          │ │  │  │  └─ Dispatcher     │  │ │
│  │  │ /stream (SSE)      │ │  │  │                    │  │ │
│  │  └────────────────────┘ │  │  │ Adapter Registry   │  │ │
│  │           │              │  │  │  ├─ ClaudeAdapter  │  │ │
│  │           ▼              │  │  │  ├─ OpenAIAdapter  │  │ │
│  │  ┌────────────────────┐ │  │  │  └─ CustomAdapter  │  │ │
│  │  │ Service Layer      │ │  │  │                    │  │ │
│  │  │  ├─ Conversation   │ │  │  │ Artifact Parser    │  │ │
│  │  │  ├─ Message        │◀┼──┼──┤ (识别 code/diff)   │  │ │
│  │  │  └─ ContextBuilder │ │  │  └────────────────────┘  │ │
│  │  └────────────────────┘ │  └─────────────│────────────┘ │
│  │           │              │                │               │
│  │           ▼              │                ▼               │
│  │  ┌────────────────────┐ │  ┌──────────────────────────┐ │
│  │  │ SQLAlchemy Models  │ │  │  External AI Providers   │ │
│  │  │  (User/Conv/Msg)   │ │  │  Anthropic | OpenAI      │ │
│  │  └────────┬───────────┘ │  └──────────────────────────┘ │
│  └───────────│──────────────┘                                │
└──────────────│───────────────────────────────────────────────┘
               │
       ┌───────▼──────┐         ┌─────────────────┐
       │ PostgreSQL   │         │  Redis          │
       │  (持久化)     │         │  (缓存/Pub-Sub) │
       └──────────────┘         └─────────────────┘
```

### 5.2 数据流：用户发送一条消息（v1.1 — 含 tool_call 链路）

```
1. F: 用户在 ChatWindow 输入文字 → POST /api/v1/conversations/{id}/messages
2. B1: messages.py 接收请求 → message_service 保存 user_message
3. B1: 创建 pending 状态的 agent_message → 返回 {user_msg_id, agent_msg_id}
4. F: 拿到 agent_msg_id → 立即发起 GET /api/v1/messages/{agent_msg_id}/stream (SSE)
5. B1: stream.py 路由
   ├─ context_builder 组装历史消息
   ├─ WorkspaceService.get_or_create(conv_id) → workspace_path   ✨ v1.1
   ├─ registry.get_adapter(agent_id) 获取 v2 Adapter（external / builtin / orchestrator）
   ├─ adapter.stream(messages, workspace_path=..., tool_specs=...) → AsyncIterator[StreamChunk]
   └─ 循环：
      ├─ 转换 StreamChunk → SSE event（含 tool_call / tool_result）   ✨ v1.1
      ├─ yield 给前端
      └─ _ContentAccumulator 累积：text/code 增量、tool_call+tool_result 配对成 ToolCallBlock   ✨ v1.1
6. F: useStream Hook 监听 EventSource
   ├─ 收到 delta → 增量更新 MessageList 中的对应消息
   ├─ 收到 block_start → 创建新的 ContentBlock
   ├─ 收到 tool_call → 创建 ToolCallBlock（pending 状态）   ✨ v1.1
   ├─ 收到 tool_result → 按 call_id 找到对应 ToolCallBlock 更新（ok/error）   ✨ v1.1
   └─ 收到 done → 关闭流，标记消息完成
7. B1: 流结束 → 更新 agent_message.status = "done"，content 持久化为 ContentBlock[]（含 ToolCallBlock）
8. F: 用户点击产物文件 → GET /api/v1/workspaces/{conv}/files/{path} → iframe / Monaco 编辑器   ✨ v1.1
```

### 5.3 群聊场景：Orchestrator 协调

```
1. F: 用户在群聊发送 "@Orchestrator 帮我做一个 Todo App"
2. B1: 同上保存 user_message，创建 agent_message（Orchestrator）
3. B2: OrchestratorAdapter.stream(...)
   ├─ Step 1: 基于 tasks 或 managed_agent_ids 生成任务计划 → 输出 [
   │     {agent_id: "claude-code", task: "写后端 API"},
   │     {agent_id: "codex-helper", task: "写前端组件"}
   │   ]
   ├─ Step 2: 用 yield 输出"任务规划"卡片到前端
   ├─ Step 3: 顺序调用每个子 Agent
   │   ├─ for subtask in tasks:
   │   │   ├─ yield 一个"开始 @claude-code" 的提示
   │   │   ├─ async for chunk in get_adapter(subtask.agent_id).stream(...):
   │   │   │   yield chunk
   │   │   └─ yield 一个"@claude 完成" 的提示
   └─ Step 4: 输出最终汇总
4. F: 整个流式过程中持续渲染，用户看到 Orchestrator → 子 Agent → 汇总 的完整过程
```

### 5.4 模块职责矩阵

| 模块 | 负责人 | 输入 | 输出 | 依赖 |
|------|--------|------|------|------|
| **REST API 路由层** | B1 | HTTP 请求 | JSON 响应 | Service |
| **SSE 流式路由** | B1 | HTTP GET | SSE event stream | ContextBuilder + Adapter Registry |
| **Service 业务层** | B1 | Pydantic Schema | DB 操作 | SQLAlchemy Models |
| **Context Builder** | B1 | conversation_id | `list[ChatMessage]` | DB |
| **BaseAgentAdapter** | B2 | `list[ChatMessage]` + config | `AsyncIterator[StreamChunk]` | 外部 AI API |
| **Adapter Registry** | B2 | agent_id | `BaseAgentAdapter` 实例 | DB（读 Agent 配置） |
| **Orchestrator** | B2 | 群聊上下文 | 任务分派 + 子 Adapter 调用 | Adapter Registry |
| **Artifact Parser** | B2 | LLM 文本输出 | `list[ContentBlock]` | 正则/状态机 |
| **前端 UI** | F | 用户操作 | API 调用 + SSE 订阅 | API Client + SSE Client |

---

## 6. 数据模型设计

### 6.1 实体关系图（ER）

```
┌──────────┐         ┌──────────────┐         ┌──────────┐
│   User   │ 1───∞ │ Conversation │ 1───∞ │ Message  │
│          │         │              │         │          │
│ id       │         │ id           │         │ id       │
│ username │         │ user_id (FK) │         │ conv_id  │
│ password │         │ title        │         │ role     │
│ avatar   │         │ mode         │         │ agent_id │
└──────────┘         │ agent_ids[]  │         │ content[]│ ← JSONB
                     │ is_pinned    │         │ status   │
                     │ is_archived  │         │ created  │
                     └──────────────┘         └──────────┘
                              │ ∞
                              │
                              │ refers to (logical)
                              ▼ ∞
                     ┌──────────────┐
                     │    Agent     │
                     │              │
                     │ id           │
                     │ user_id (FK) │ ← null 表示内置
                     │ name         │
                     │ provider     │
                     │ avatar       │
                     │ capabilities │
                     │ system_prompt│
                     │ config       │ ← JSONB
                     │ is_builtin   │
                     └──────────────┘
```

### 6.2 表结构详解

```python
# app/models/user.py
class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


# app/models/conversation.py
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16))  # "single" | "group"
    agent_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_pinned: Mapped[bool] = mapped_column(default=False)
    is_archived: Mapped[bool] = mapped_column(default=False)
    last_message_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation",
                                                     cascade="all, delete-orphan")


# app/models/message.py
class Message(Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "agent" | "system"
    agent_id: Mapped[str | None] = mapped_column(String(64))  # role=agent 时填
    content: Mapped[list[dict]] = mapped_column(JSONB, default=list)  # ContentBlock[]
    reply_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    status: Mapped[str] = mapped_column(String(16), default="done")
    # "pending" | "streaming" | "done" | "error"
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


# app/models/agent.py
class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))  # null = 内置
    name: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))  # "claude_code"|"codex"|"opencode"|"builtin"|"mock"; legacy raw provider only for migration
    avatar_url: Mapped[str] = mapped_column(String(512))
    capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_builtin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

### 6.3 ContentBlock 联合类型（消息富媒体核心）

```python
# app/schemas/message.py
from typing import Literal, Union, Annotated
from pydantic import BaseModel, Field

class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    language: str
    code: str

class DiffBlock(BaseModel):
    type: Literal["diff"] = "diff"
    filename: str
    before: str
    after: str

class WebPreviewBlock(BaseModel):
    type: Literal["web_preview"] = "web_preview"
    url: str
    title: str | None = None
    description: str | None = None

class FileBlock(BaseModel):
    type: Literal["file"] = "file"
    filename: str
    url: str
    size: int
    mime_type: str

ContentBlock = Annotated[
    Union[TextBlock, CodeBlock, DiffBlock, WebPreviewBlock, FileBlock],
    Field(discriminator="type"),
]
```

### 6.4 索引设计

| 表 | 索引 | 用途 |
|----|------|------|
| `users` | `username` UNIQUE | 登录查询 |
| `conversations` | `(user_id, last_message_at DESC)` | 会话列表按活跃排序 |
| `conversations` | `(user_id, is_pinned, is_archived)` | 过滤查询 |
| `messages` | `(conversation_id, created_at)` | 消息按时序查询 |
| `agents` | `(user_id, is_builtin)` | Agent 列表 |

### 6.5 Seed 数据（内置 Agent）

| ID | name | provider | 描述 |
|----|------|----------|------|
| `claude-code` | Claude Code | claude_code | 编码助手，擅长写/改代码 |
| `codex-helper` | Codex Helper | codex | Codex runtime，通用编码助手 |
| `opencode-helper` | OpenCode Helper | opencode | OpenCode runtime，CLI 型编码助手 |
| `orchestrator` | Orchestrator | builtin / orchestrator 特例 | 任务拆解+分派的主 Agent |

---

## 7. API 设计

### 7.1 RESTful 端点列表

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| **认证** | | | |
| POST | `/api/v1/auth/register` | ❌ | 注册（username + password） |
| POST | `/api/v1/auth/login` | ❌ | 登录，返回 `{access_token}` |
| GET | `/api/v1/auth/me` | ✅ | 获取当前用户信息 |
| **会话** | | | |
| GET | `/api/v1/conversations?archived=false&pinned=true` | ✅ | 列表（支持过滤、分页） |
| POST | `/api/v1/conversations` | ✅ | 新建（body: `{title, mode, agent_ids}`） |
| GET | `/api/v1/conversations/{id}` | ✅ | 详情 |
| PATCH | `/api/v1/conversations/{id}` | ✅ | 改标题/置顶/归档 |
| DELETE | `/api/v1/conversations/{id}` | ✅ | 删除 |
| **消息** | | | |
| GET | `/api/v1/conversations/{id}/messages?before=&limit=50` | ✅ | 历史消息（游标分页） |
| POST | `/api/v1/conversations/{id}/messages` | ✅ | 发送消息 |
| GET | `/api/v1/messages/{id}/stream` | ✅ | **SSE 流式订阅** |
| **Agent** | | | |
| GET | `/api/v1/agents?builtin=true` | ✅ | Agent 列表 |
| POST | `/api/v1/agents` | ✅ | 创建自定义 Agent |
| GET | `/api/v1/agents/{id}` | ✅ | 详情 |
| PATCH | `/api/v1/agents/{id}` | ✅ | 编辑（仅自建） |
| DELETE | `/api/v1/agents/{id}` | ✅ | 删除（仅自建） |

### 7.2 请求/响应示例

#### 发送消息

```http
POST /api/v1/conversations/{conv_id}/messages
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "content": [
    {"type": "text", "text": "用 React 写一个 Todo 组件"}
  ],
  "target_agent_id": "claude-code"  // 单聊时可省略
}
```

```json
{
  "user_message": {
    "id": "msg_a1b2c3",
    "role": "user",
    "content": [{"type": "text", "text": "..."}],
    "status": "done",
    "created_at": "2026-05-22T10:00:00Z"
  },
  "agent_message": {
    "id": "msg_d4e5f6",
    "role": "agent",
    "agent_id": "claude-code",
    "content": [],
    "status": "pending",
    "created_at": "2026-05-22T10:00:01Z"
  }
}
```

#### SSE 流式订阅

```http
GET /api/v1/messages/msg_d4e5f6/stream
Authorization: Bearer <jwt>
Accept: text/event-stream
```

```
event: start
data: {"message_id": "msg_d4e5f6", "agent_id": "claude-code"}

event: block_start
data: {"block_index": 0, "type": "text"}

event: delta
data: {"block_index": 0, "text_delta": "好的，"}

event: delta
data: {"block_index": 0, "text_delta": "下面是 Todo 组件代码："}

event: block_end
data: {"block_index": 0}

event: block_start
data: {"block_index": 1, "type": "code", "language": "tsx"}

event: delta
data: {"block_index": 1, "code_delta": "function Todo() {\n"}

event: delta
data: {"block_index": 1, "code_delta": "  return <div>...</div>\n}"}

event: block_end
data: {"block_index": 1}

event: done
data: {"message_id": "msg_d4e5f6"}
```

#### 错误事件

```
event: error
data: {"error": "rate_limit_exceeded", "message": "Anthropic API rate limit hit"}
```

### 7.3 错误响应规范

```json
{
  "error": {
    "code": "CONVERSATION_NOT_FOUND",
    "message": "Conversation msg_xxx does not exist or you don't have access",
    "details": {}
  }
}
```

| HTTP 状态 | 含义 |
|-----------|------|
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 已认证但无权访问 |
| 404 | 资源不存在 |
| 409 | 冲突（如用户名已存在） |
| 422 | Pydantic 校验失败 |
| 500 | 服务端内部错误 |
| 502 | 上游 AI API 失败 |

---

## 8. 关键技术方案

### 8.1 SSE 流式响应实现

#### 后端（FastAPI）
```python
# app/api/v1/stream.py
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

@router.get("/messages/{message_id}/stream")
async def stream_message(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async def event_generator():
        message = await message_service.get(db, message_id)
        # 1. 校验权限
        # 2. 组装上下文
        history = await context_builder.build(db, message.conversation_id)
        # 3. 拿到 Adapter
        adapter = registry.get_adapter(message.agent_id)
        # 4. 流式调用
        accumulator = ContentAccumulator()  # 用于累积写 DB
        async for chunk in adapter.stream(history, system_prompt, config):
            yield {"event": chunk.event_type, "data": chunk.to_json()}
            accumulator.feed(chunk)
        # 5. 持久化最终内容
        await message_service.finalize(db, message_id, accumulator.blocks)

    return EventSourceResponse(event_generator())
```

#### 前端（React Hook）
```typescript
// src/hooks/useStream.ts
export function useStream(messageId: string | null) {
  const [blocks, setBlocks] = useState<ContentBlock[]>([]);
  const [status, setStatus] = useState<'idle' | 'streaming' | 'done' | 'error'>('idle');

  useEffect(() => {
    if (!messageId) return;
    const es = new EventSource(`/api/v1/messages/${messageId}/stream`, {
      withCredentials: true,
    });

    es.addEventListener('start', () => setStatus('streaming'));
    es.addEventListener('block_start', (e) => {
      const data = JSON.parse(e.data);
      setBlocks(prev => [...prev, { type: data.type, ...initBlock(data) }]);
    });
    es.addEventListener('delta', (e) => {
      const data = JSON.parse(e.data);
      setBlocks(prev => applyDelta(prev, data));
    });
    es.addEventListener('done', () => { setStatus('done'); es.close(); });
    es.addEventListener('error', () => { setStatus('error'); es.close(); });

    return () => es.close();
  }, [messageId]);

  return { blocks, status };
}
```

### 8.2 Agent Adapter 抽象（v1.1 — BaseAgentAdapter v2）

> v1.1 升级：新增 `workspace_path` / `tool_specs` 参数；StreamChunk 新增 `tool_call` / `tool_result` 事件类型。完整规范见 [docs/b2/spec/agent-runtime-adapter.spec.md](b2/spec/agent-runtime-adapter.spec.md)；原 v1 签名（无 workspace / tool）已迁移到 ModelGateway 内部接口。

```python
# backend/app/agents/base.py（v2）
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from .types import ChatMessage, StreamChunk, ToolSpec

class BaseAgentAdapter(ABC):
    """v2 — 同时支持 External / Builtin / Orchestrator 三类子 Adapter。"""

    provider: str = ""  # "claude_code" / "codex" / "opencode" / "builtin" / "mock"

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
        workspace_path: Path | None = None,        # ✨ v2 新增
        tool_specs: list[ToolSpec] | None = None,  # ✨ v2 新增
    ) -> AsyncIterator[StreamChunk]: ...


# backend/app/agents/types.py（v1.1）
class StreamChunk(BaseModel):
    event_type: Literal[
        "start", "block_start", "delta", "block_end",
        "done", "error", "agent_switch", "heartbeat",
        "tool_call",      # ✨ v1.1
        "tool_result",    # ✨ v1.1
    ]
    # v1 字段保留 + v1.1 新增：call_id / tool_name / tool_arguments / tool_status / tool_output / tool_output_truncated
    ...
```

**三层子 Adapter**（详见 [tech-architecture.md §6.3](tech-architecture.md)）：

- **Layer A — ExternalAgentAdapter**（`agents/external/`）：嵌入 Claude Agent SDK / OpenAI Agents SDK / OpenCode CLI，复用其内置 loop/tool/MCP 或 CLI runtime
- **Layer B — BuiltinAgentAdapter**（`agents/builtin/`）：自建 AgentLoop + ToolRegistry + MCPClient + Memory（详见 §8.7-§8.10）
- **Layer C — ModelGateway**（`agents/model_gateway/`）：原 raw LLM Adapter 迁移而来，仅 BuiltinAgent 内部使用，**不注册为顶层 Agent**

### 8.3 Orchestrator 任务拆解

```python
# app/agents/orchestrator.py
class OrchestratorAdapter(BaseAgentAdapter):
    """主 Agent：负责拆解任务、分派给子 Agent"""

    async def stream(self, messages, system_prompt, config):
        # Step 1: 调 LLM 拆解任务
        yield StreamChunk(event_type="start")
        yield StreamChunk(event_type="block_start", block_index=0, block_type="text")
        yield StreamChunk(event_type="delta", block_index=0,
                          text_delta="正在分析任务...\n")

        tasks = await self._decompose(messages)
        # tasks = [{"agent_id": "claude-code", "task": "写后端"}, ...]
        
        yield StreamChunk(event_type="delta", block_index=0,
                          text_delta=f"任务拆解为 {len(tasks)} 步：\n")
        for i, t in enumerate(tasks):
            yield StreamChunk(event_type="delta", block_index=0,
                              text_delta=f"{i+1}. @{t['agent_id']}: {t['task']}\n")
        yield StreamChunk(event_type="block_end", block_index=0)

        # Step 2: 顺序调用子 Agent
        block_idx = 1
        for task in tasks:
            sub_adapter = registry.get_adapter(task["agent_id"])
            sub_messages = messages + [ChatMessage(role="user", content=task["task"])]
            async for chunk in sub_adapter.stream(sub_messages, ...):
                # 改写 block_index 避免冲突
                chunk.block_index = (chunk.block_index or 0) + block_idx
                yield chunk
            block_idx += 10  # 留出空间

        yield StreamChunk(event_type="done")

    async def _decompose(self, messages):
        # 用 Claude 调用结构化输出（function calling 或 JSON mode）
        ...
```

### 8.4 产物解析（Artifact Parser）

从 LLM 输出的 markdown 文本中识别代码块、Diff、URL：

```python
# app/agents/artifact_parser.py
CODE_FENCE_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
URL_RE = re.compile(r"https?://[^\s)]+")

def parse_to_blocks(text: str) -> list[ContentBlock]:
    """将 LLM 的 markdown 文本解析为 ContentBlock 列表"""
    blocks: list[ContentBlock] = []
    last_end = 0
    for m in CODE_FENCE_RE.finditer(text):
        if m.start() > last_end:
            blocks.append(TextBlock(text=text[last_end:m.start()]))
        blocks.append(CodeBlock(language=m.group(1) or "text", code=m.group(2)))
        last_end = m.end()
    if last_end < len(text):
        blocks.append(TextBlock(text=text[last_end:]))
    return blocks
```

> **MVP 简化**：流式过程中实时检测代码围栏 ``` 即可。复杂的 Diff、网页预览可由 Agent 通过 Tool Calling 主动产出结构化数据。

### 8.5 JWT 认证

```python
# app/core/security.py
from jose import jwt
from passlib.context import CryptContext

pwd_ctx = CryptContext(schemes=["bcrypt"])

def hash_password(p: str) -> str: return pwd_ctx.hash(p)
def verify_password(p: str, h: str) -> bool: return pwd_ctx.verify(p, h)

def create_access_token(user_id: UUID) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

# app/core/deps.py
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = UUID(payload["sub"])
    except (JWTError, ValueError):
        raise HTTPException(401, "Invalid token")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user
```

### 8.6 上下文组装（Context Builder）

> v1.1 注：现有 ContextBuilder + ContextCompression 在 BuiltinAgent 中作为 `ContextManager` 子组件复用，不重新实现。

```python
# app/services/context_builder.py
class ContextBuilder:
    MAX_TOKENS = 8000  # 简单按字数限制

    async def build(self, db, conversation_id: UUID) -> list[ChatMessage]:
        messages = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        result: list[ChatMessage] = []
        total_chars = 0
        # 反向遍历，优先保留最近的消息
        for m in reversed(list(messages.scalars())):
            text = self._blocks_to_text(m.content)
            if total_chars + len(text) > self.MAX_TOKENS * 4:
                break
            result.insert(0, ChatMessage(
                role="assistant" if m.role == "agent" else m.role,
                content=text,
            ))
            total_chars += len(text)
        return result
```

### 8.7 BuiltinAgent AgentLoop（v1.1 新增）

> 完整规范：[builtin-agent-framework.spec.md §2](b2/spec/builtin-agent-framework.spec.md)

```python
# backend/app/agents/builtin/loop.py（伪代码摘要）
async def run_agent_loop(messages, tools, workspace_path, model_gateway, config, max_iter=10):
    yield StreamChunk(event_type="start")
    for iteration in range(max_iter):
        tool_calls = []
        async for chunk in model_gateway.stream(messages, tools=tools, config=config):
            if chunk.event_type == "tool_call":
                tool_calls.append(parse_tool_call(chunk))
            yield chunk
        if not tool_calls:
            yield StreamChunk(event_type="done"); return
        for call in tool_calls:
            result = await execute_tool(call, workspace_path, tools)
            yield StreamChunk(event_type="tool_result", call_id=call.id, tool_status=result.status, ...)
        messages = append_tool_results(messages, tool_calls, results)
    yield StreamChunk(event_type="error", error_code="loop_max_iterations")
```

终止条件、错误处理矩阵详见 spec。MVP 不做并行 tool / 投机执行 / Agent 调用子 Agent。

### 8.8 ToolRegistry — MVP 三件套（v1.1 新增）

> 完整规范：[builtin-agent-framework.spec.md §3](b2/spec/builtin-agent-framework.spec.md)

| Tool | 约束 |
|---|---|
| `read_file` | 路径必须在 workspace 内；最大读 1 MB |
| `write_file` | 路径校验（§8.9）；禁止写 `.env`/`.git`/`secrets/`；最大 1 MB |
| `bash` | 命令首词必须在白名单（`ls cat mkdir rm mv cp node python pnpm pip cd pwd echo grep find`）；超时 30s；cwd 强制 workspace |

工具结果用统一 `ToolResult(call_id, status, output, error_code)`，由 AgentLoop 包装为 `StreamChunk(tool_result)`。

### 8.9 Workspace Sandbox（v1.1 新增）

> 完整规范：[workspace-sandbox.spec.md](b1/spec/workspace-sandbox.spec.md)

- 每会话一个目录：宿主机 `/var/lib/agenthub/workspaces/<conv_id>/`（容器内 `/workspaces`）
- 数据模型：`workspaces` 表（id / conversation_id unique / root_path / 时间戳），cascade 删除
- 路径校验函数（B1 提供）：`validate_write_path(workspace_root, user_path) -> Path`
- 拒绝：`../` / 符号链接 / `.env` / `.git` / `secrets/` / `.agenthub/`
- HTTP API：`GET /tree`、`GET /files/{path}`（含 mime sniff + iframe CSP）、`PUT /files/{path}`
- ❌ 不做：Docker per-conversation、网络/CPU 隔离（P2）

### 8.10 MCP Client（v1.1 新增）

> 完整规范：[builtin-agent-framework.spec.md §5](b2/spec/builtin-agent-framework.spec.md)

- 使用官方 `mcp` Python SDK
- 仅 **stdio** transport（HTTP 不做）
- MVP 启动 1 个 server：`@modelcontextprotocol/server-filesystem`
- 工具命名空间用前缀 `mcp_fs__` 避免与 native tool 冲突
- 错误：启动失败 → `error(mcp_server_down)`；运行崩溃 → `tool_result(error)` + 标记降级

---

## 9. 项目目录结构

```
agenthub/
├── README.md                         # 项目说明（一键启动指南）
├── CLAUDE.md                         # AI 协作规范（30% 权重核心）
├── docker-compose.yml                # 本地一键启动
├── .env.example                      # 环境变量模板
├── .gitignore
│
├── docs/                             # 所有文档
│   ├── product-design.md             # 产品设计文档
│   ├── development-plan.md           # 本文档
│   ├── team-division.md              # 三人分工方案
│   ├── tech-architecture.md          # 技术架构详解
│   ├── api-spec.md                   # API 文档（人类可读版）
│   ├── ai-collaboration-log.md       # AI 协作日志
│   ├── demo-script.md                # Demo 视频脚本
│   └── spec/                         # 模块 Spec（用于 AI 协作）
│       ├── auth.spec.md
│       ├── conversation.spec.md
│       ├── streaming.spec.md
│       └── orchestrator/
│           ├── README.md
│           └── core.spec.md
│
├── shared/                           # 前后端共享契约
│   ├── openapi.yaml                  # OpenAPI 规范（唯一真相源）
│   └── README.md
│
├── .claude/                          # Claude Code 协作规范
│   ├── skills/                       # 自定义 Skill
│   └── rules/                        # 编码规范文件
│
├── .cursor/                          # Cursor 协作规范
│   └── rules/
│
├── backend/                          # FastAPI 后端
│   ├── pyproject.toml
│   ├── README.md
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── versions/
│   │   └── seeds/                    # 内置 Agent 种子数据
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_conversations.py
│   │   └── test_adapters.py
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── core/                     # 【B1】
│       │   ├── config.py
│       │   ├── database.py
│       │   ├── security.py
│       │   ├── deps.py
│       │   └── pubsub.py
│       ├── models/                   # 【B1】
│       │   ├── user.py
│       │   ├── conversation.py
│       │   ├── message.py
│       │   └── agent.py
│       ├── schemas/                  # 【B1+B2】
│       │   ├── auth.py
│       │   ├── conversation.py
│       │   ├── message.py
│       │   └── agent.py
│       ├── api/                      # 【B1】
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── auth.py
│       │       ├── conversations.py
│       │       ├── messages.py
│       │       ├── agents.py
│       │       └── stream.py
│       ├── services/                 # 【B1】
│       │   ├── conversation_service.py
│       │   ├── message_service.py
│       │   └── context_builder.py
│       └── agents/                   # 【B2】
│           ├── __init__.py
│           ├── base.py               # BaseAgentAdapter
│           ├── types.py              # StreamChunk, ChatMessage
│           ├── registry.py           # Adapter 工厂
│           ├── orchestrator.py
│           ├── artifact_parser.py
│           ├── adapters/
│           │   └── mock.py           # Mock 用于联调；legacy raw adapter shim 暂存
│           ├── external/             # Claude Code / Codex / OpenCode runtime
│           ├── builtin/              # AgentLoop / ToolRegistry / MCP
│           └── model_gateway/        # raw Claude/OpenAI/DeepSeek，仅 BuiltinAgent 内部使用
│
└── frontend/                         # React + Vite 前端
    ├── package.json
    ├── pnpm-lock.yaml
    ├── README.md
    ├── Dockerfile
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── tsconfig.json
    ├── index.html
    ├── public/
    │   └── avatars/
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── router.tsx
        ├── lib/
        │   ├── api.ts
        │   ├── sse.ts
        │   ├── types.ts              # 从 openapi.yaml 生成
        │   ├── auth.ts               # token 存取
        │   └── utils.ts
        ├── stores/
        │   ├── authStore.ts
        │   ├── conversationStore.ts
        │   └── uiStore.ts
        ├── hooks/
        │   ├── useConversations.ts
        │   ├── useMessages.ts
        │   ├── useStream.ts
        │   └── useAgents.ts
        ├── pages/
        │   ├── LoginPage.tsx
        │   ├── ChatPage.tsx
        │   └── AgentsPage.tsx
        ├── components/
        │   ├── layout/
        │   │   ├── AppLayout.tsx
        │   │   └── Sidebar.tsx
        │   ├── conversation/
        │   │   ├── ConversationList.tsx
        │   │   ├── ConversationItem.tsx
        │   │   └── NewConversationDialog.tsx
        │   ├── chat/
        │   │   ├── ChatWindow.tsx
        │   │   ├── MessageList.tsx
        │   │   ├── MessageBubble.tsx
        │   │   ├── MessageInput.tsx
        │   │   └── AgentMentionPicker.tsx
        │   ├── blocks/                # 富媒体消息块
        │   │   ├── TextBlock.tsx
        │   │   ├── CodeBlock.tsx
        │   │   ├── DiffBlock.tsx
        │   │   ├── WebPreviewCard.tsx
        │   │   └── FileAttachment.tsx
        │   ├── agents/
        │   │   ├── AgentAvatar.tsx
        │   │   ├── AgentCard.tsx
        │   │   └── CustomAgentForm.tsx
        │   └── ui/                    # shadcn/ui 生成的组件
        ├── styles/
        │   └── globals.css
        └── tests/
```

---

## 10. 开发环境与工具链

### 10.1 本地启动步骤

```bash
# 1. 克隆仓库
git clone <repo-url> && cd agenthub

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env：填入 ANTHROPIC_API_KEY、OPENAI_API_KEY、JWT_SECRET

# 3. 启动后端（Postgres + Redis + Backend）
docker compose up -d

# 4. 运行数据库迁移
docker compose exec backend alembic upgrade head
docker compose exec backend python -m alembic.seeds.seed_agents

# 5. 启动前端（独立终端）
cd frontend
pnpm install
pnpm dev

# 6. 访问应用
open http://localhost:5173

# 7. 查看后端 API 文档
open http://localhost:8000/docs
```

### 10.2 推荐开发工具

| 工具 | 用途 |
|------|------|
| **VS Code / Cursor / Claude Code** | 主力编辑器（AI 协作） |
| **DBeaver / TablePlus** | 数据库可视化 |
| **Postman / Insomnia** | API 测试 |
| **Redis Insight** | Redis 可视化 |
| **Chrome DevTools** | 前端调试、SSE 流监控 |

### 10.3 环境变量清单（`.env.example`）

```bash
# 后端
DATABASE_URL=postgresql+asyncpg://agenthub:password@localhost:5432/agenthub
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change-me-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_DAYS=7

# AI Providers
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx

# 前端
VITE_API_BASE_URL=http://localhost:8000
```

---

## 11. 开发流程规范

### 11.1 Git 工作流（Trunk-Based + Feature Branch）

```
main
 ├── feat/F-chat-window        ← F 的功能分支
 ├── feat/B1-auth              ← B1 的功能分支
 └── feat/B2-claude-adapter    ← B2 的功能分支
```

**规则**：
- 主分支 `main` 始终可运行
- 每人在自己的 `feat/<owner>-<feature>` 分支上开发
- PR Review 至少 1 人 +1 才能合并
- 合并前必须本地跑通 `docker compose up` 端到端

### 11.2 Commit 规范（Conventional Commits）

```
<type>(<scope>): <subject>

[body]

[footer]
```

| type | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档 |
| refactor | 重构（非功能性改动） |
| test | 测试 |
| chore | 构建/工具 |

**示例**：
```
feat(B1/api): add SSE stream endpoint for messages

- Add /api/v1/messages/{id}/stream
- Integrate with B2's BaseAgentAdapter
- Persist accumulated content to DB on stream end
```

### 11.3 代码规范

#### 后端（Python）
- **格式化**：`ruff format`（替代 black）
- **检查**：`ruff check` + `mypy --strict`
- **命名**：函数/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE`
- **类型注解**：所有公开函数必须有完整类型注解
- **导入顺序**：标准库 → 第三方 → 本地（ruff 自动排序）
- **异步**：DB / HTTP 调用一律 async/await

#### 前端（TypeScript）
- **格式化**：`prettier`
- **检查**：`eslint`
- **命名**：组件 `PascalCase`，Hook `useXxx`，工具函数 `camelCase`
- **类型**：从 OpenAPI 生成的类型放在 `lib/types.ts`，不要手写重复类型
- **导入顺序**：React → 第三方 → 内部相对导入（eslint 自动排序）

### 11.4 PR 模板（`.github/PULL_REQUEST_TEMPLATE.md`）

```markdown
## 改动说明
<!-- 简述本 PR 做了什么 -->

## 关联模块
- [ ] F（前端）
- [ ] B1（核心后端）
- [ ] B2（Agent 集成）

## 测试方式
<!-- 列出本地验证步骤 -->

## API 契约变更
- [ ] 不涉及 API
- [ ] 已更新 `shared/openapi.yaml`
- [ ] 已通知前端重新生成类型

## 截图（如有 UI 改动）
```

### 11.5 API 契约管理流程（**关键**）

```
1. 任何 API 变更，先改 shared/openapi.yaml
2. 在 PR 描述中明确"契约变更"标签
3. 前端运行 pnpm run gen:types 重新生成 src/lib/types.ts
4. 后端的 Pydantic Schema 必须与 OpenAPI 对齐
5. 合并到 main 后，所有人 pull 并重新生成类型
```

---

## 12. AI 协作规范（Vibe Coding）

> **30% 权重核心维度**：这是评分占比最大的项，必须高度重视。

### 12.1 沉淀物清单

| 文件 | 用途 |
|------|------|
| `CLAUDE.md` | 项目总体 AI 协作指南（全员共用） |
| `.claude/skills/` | 项目专属 Skill（如"生成 SQLAlchemy 模型"、"生成 React 组件"） |
| `.claude/rules/` | 项目编码规则 |
| `.cursor/rules/*.mdc` | Cursor 项目规则 |
| `docs/spec/<module>.md` | 每个模块的 Spec（输入/输出/边界） |
| `docs/ai-collaboration-log.md` | AI 协作日志（记录关键 Prompt） |

### 12.2 CLAUDE.md 必须包含

```markdown
# AgentHub - AI 协作指南

## 项目概述
（一段话描述项目）

## 技术栈
（链接到 development-plan.md）

## 目录约定
- backend/app/core/ → B1 负责
- backend/app/agents/ → B2 负责
- frontend/src/ → F 负责

## 编码规范
（链接到 development-plan.md 第 11 节）

## API 契约修改流程
任何 API 变更必须先修改 shared/openapi.yaml

## 关键接口
- BaseAgentAdapter 位于 backend/app/agents/base.py
- ContentBlock 联合类型位于 backend/app/schemas/message.py

## 常见任务模板
（示例 Prompt）

## 不要做的事
- 不要绕过 BaseAgentAdapter 抽象直接调 Anthropic SDK
- 不要在前端硬编码 API 路径，使用生成的类型
- 不要写新文件前先查目录约定
```

### 12.3 模块 Spec 模板

每个模块开发前，先写 `docs/spec/<module>.spec.md`：

```markdown
# <模块名> Spec

## 目标
（一句话说明）

## 输入
- 数据类型
- 约束

## 输出
- 数据类型
- 约束

## 边界 / 错误处理
- 异常情况

## 性能要求

## 依赖
- 上游：xxx
- 下游：xxx

## 验收标准
- [ ] 用例 1
- [ ] 用例 2
```

### 12.4 AI 协作日志格式

```markdown
## 2026-05-22 — B1 实现 SSE 流式端点

### 任务
实现 GET /api/v1/messages/{id}/stream 流式端点

### 关键 Prompt
> 我需要在 FastAPI 中实现 SSE 端点。要求：
> 1. 使用 sse-starlette 库
> 2. 调用 backend/app/agents/registry.py 的 get_adapter
> 3. 流式累积 StreamChunk 到 DB
> 请参考 backend/app/agents/base.py 的 BaseAgentAdapter 接口

### AI 输出摘要
（生成了 stream.py 80 行，包含 event_generator 异步生成器）

### 人工调整
- 加了权限校验
- 修复了 chunk.block_index None 的情况

### 经验
- sse-starlette 的 EventSourceResponse 需要返回 dict 而非字符串
```

### 12.5 协作三原则

1. **契约先行**：API 变更先改 OpenAPI，再改实现
2. **接口先行**：B2 先交付 BaseAgentAdapter 抽象 + Mock 实现，B1 才能并行开发
3. **Mock 优先**：前端基于 OpenAPI 生成 Mock Server，不阻塞等后端

---

## 13. 里程碑与时间线

### 13.1 Sprint 计划（v1.1 — pivot 后版本）

| Sprint | 时间 | 目标 | 验收标准 |
|--------|------|------|----------|
| **Sprint 0** | Day 1-2 | 契约 + 脚手架 | `docker compose up` 启动成功，OpenAPI v0.1 完成 |
| **Sprint 1** | Day 3-5 | 单聊 MVP（raw LLM） | 登录 → 选 Agent → 发消息 → 看到流式回复 |
| **Sprint 2** | Day 6-8 | 富媒体 + Agent 管理 | 代码块高亮、Diff 视图、Agent CRUD |
| **Sprint 3** | Day 9-11 | 群聊 + Orchestrator | @ 多 Agent，Orchestrator 拆解、依次回复 |
| **Sprint 4** | Day 12-? | 打磨（含 demo polish v2、context compression）| Bug Fix、文档、Provider resilience、smoke tests |
| **Sprint 5（pivot）** ✨ | **2026-05-26 ~ 06-03（8 天）** | **Agent Runtime Pivot：External + Builtin + Workspace** | Day 3：Claude Code 真实写 HTML → iframe 预览；Day 5：BuiltinAgent MVP；Day 6：Codex / OpenCode + Orchestrator 接通真 Agent；Day 8：Demo 视频 + 答辩材料 |

### 13.1.1 Sprint 5 — Pivot 8 天详细计划

> 与 [team-division.md §7.1-PIVOT](team-division.md) / §7.2-PIVOT 同步保持一致。

| Day | F | B1 | B2 |
|---|---|---|---|
| **1** | 等待 schema | Workspace 模型 + Alembic + WorkspaceService 骨架 | BaseAgentAdapter v2 + StreamChunk v1.1 + ToolSpec + MockAdapter v2 |
| **2** | ToolCallBlock + ArtifactPreview iframe | Artifact API + OpenAPI 同步 + SSE 协议扩展 | ExternalAgentAdapter (Claude Agent SDK) + ModelGateway 迁移 |
| **3** | SSE handler tool_* 配对 + Workspace 文件树 | 联调 + bug fix | **里程碑：真 Agent 写 HTML → iframe 预览端到端** |
| **4** | Monaco 编辑器 + 二次编辑回写 | PUT 文件接口 + AgentRegistry v2 配合 | BuiltinAgent AgentLoop + ToolRegistry 三件套 |
| **5** | 错误态 / 空态 / 加载态 | 收尾 + 性能验证 | BuiltinAgent MemoryManager + MCP filesystem server |
| **6** | Orchestrator 任务卡升级 | — | ExternalAgentAdapter (Codex / OpenCode)；Orchestrator 接通真 Agent |
| **7** | Demo 视频脚本 + 关键交互预录制 | Bug fix + 文档同步 | 全链路 smoke + 失败降级回归 + 文档 |
| **8** | Demo 视频录制 + 答辩讲稿 | 答辩讲稿 | 答辩讲稿 + ADR 收尾 |

### 13.2 关键里程碑（v1.1）

```
Day 2:   ✅ 脚手架完成，前后端可独立启动            （已达成）
Day 5:   ✅ 里程碑 1 - 单聊 MVP 跑通               （已达成）
Day 8:   ✅ 里程碑 2 - 富媒体产物预览完整          （已达成）
Day 11:  ✅ 里程碑 3 - 群聊 Orchestrator 演示就绪 （已达成）

【pivot 触发于 2026-05-26（Day 5 of new Sprint）】

Sprint 5 Day 3:  ✨ 里程碑 4 - 第一个真 Agent 端到端 demo（Claude Code 写 HTML → iframe）
Sprint 5 Day 5:  ✨ 里程碑 5 - BuiltinAgent Framework MVP 跑通（loop + 3 tool + 1 MCP）
Sprint 5 Day 6:  ✨ 里程碑 6 - Codex 接入 + Orchestrator 接通真 Agent
Sprint 5 Day 8:  ✨ 里程碑 7 - 全部交付物完成，提交答辩
```

### 13.3 每日例会建议

- **早会**（15 分钟）：每人说昨天进度、今天计划、当前阻塞
- **晚同步**（异步消息）：在群里发 Daily Update，附 PR 链接
- **Sprint 5 额外**：每日 Demo 5 分钟（演示当天可见进展），保证视频素材逐日积累

---

## 14. 风险与应对

| 风险 | 等级 | 应对 |
|------|------|------|
| Anthropic / OpenAI API Key 不可用 | 🔴 高 | 提前申请、准备好 Mock Adapter，群聊场景可降级单 Agent |
| 团队成员 Python/React 不熟 | 🟡 中 | 提前 1-2 天熟悉文档、用 AI 协作快速上手 |
| OpenAPI 契约频繁变更 | 🟡 中 | 严格执行"契约先行"流程，每次变更走 PR Review |
| SSE 在某些代理 / Nginx 配置下断连 | 🟡 中 | 本地开发不用代理；前端 EventSource 自带重连 |
| Orchestrator 拆解任务的 Prompt 不稳定 | 🟡 中 | 用 function calling / JSON mode 强制结构化输出 |
| Demo 视频录制时遇到 Bug | 🟢 低 | Day 13 留一整天做"演示准备"，预录关键片段 |
| 三人代码冲突 | 🟢 低 | 严格按目录边界分工，避免同一文件多人改 |

---

## 15. 验收与测试方案

### 15.1 自动化测试

| 范围 | 工具 | 覆盖目标 |
|------|------|----------|
| 后端单元测试 | pytest + pytest-asyncio | Service 层、Context Builder、Adapter（用 Mock LLM） |
| 后端集成测试 | pytest + httpx + testcontainers | 完整 API 流程（含 SSE） |
| 前端单元测试 | vitest + @testing-library | 关键 Hook（useStream）、消息块组件 |
| E2E 测试（可选） | Playwright | 登录 → 发消息 → 收到回复 |

### 15.2 手动验收清单

#### 单聊场景
- [ ] 注册新用户成功
- [ ] 登录后跳转主页
- [ ] 看到内置 Agent 列表
- [ ] 新建会话，选 Claude
- [ ] 发送"用 React 写一个 Todo 组件"
- [ ] SSE 流式逐字出现
- [ ] 代码自动高亮（语言识别正确）
- [ ] 点击代码块复制按钮，剪贴板有内容
- [ ] 刷新页面后历史消息保留

#### 群聊场景
- [ ] 新建会话，选 Orchestrator + Claude + Codex
- [ ] @ Orchestrator 发送"设计一个 Todo API 并实现前端"
- [ ] 看到任务拆解卡片
- [ ] 看到 Claude / Codex 依次发言
- [ ] 最终汇总产物完整

#### 富媒体
- [ ] 代码块支持折叠/展开
- [ ] Diff 视图正确显示新增/删除
- [ ] 网页预览卡片可点击在新窗口打开

#### 边界情况
- [ ] 网络中断后 SSE 自动重连
- [ ] API Key 失效时显示友好错误
- [ ] 超长消息（> 4K 字符）正常处理
- [ ] 会话置顶/归档/搜索/删除

### 15.3 性能基线

| 指标 | 目标 |
|------|------|
| API 首字节延迟（除 SSE 外） | < 200ms |
| SSE 首个 token 延迟 | < 1.5s（取决于上游 LLM） |
| 前端首屏加载 | < 2s（本地） |
| 1000 条历史消息的会话打开时间 | < 1s（分页加载） |

---

## 16. 答辩准备

### 16.1 答辩前准备清单（每人）

- [ ] 准备 **5 分钟个人模块讲稿**：能讲清楚自己负责模块的"设计→实现→关键决策"
- [ ] 整理 **AI 协作记录**：至少 3 个有代表性的 Prompt + AI 输出 + 调整过程
- [ ] 跑通 **本地 Demo**：确保 Docker Compose 一键启动
- [ ] 备份 **离线 Demo 视频**：以防现场网络问题
- [ ] 准备 **3 个深度问题答案**（参见 16.3）

### 16.2 答辩流程（建议 15 分钟）

| 时间 | 内容 |
|------|------|
| 0-3 min | Demo 视频播放 |
| 3-5 min | F 讲产品体验 + 前端架构 |
| 5-7 min | B1 讲核心后端 + IM 模型 |
| 7-9 min | B2 讲 Agent 集成 + Orchestrator |
| 9-12 min | 全员答疑 |
| 12-15 min | 创新点演示（自建 Agent / 桌面端 / 任务图可视化） |

### 16.3 可能被问到的深度问题

| 问题 | 准备方向 |
|------|----------|
| 为什么用 SSE 而不是 WebSocket？ | 单向流场景、标准化、生态一致 |
| 多 Agent 同时回复时如何保证消息顺序？ | DB 时间戳 + Orchestrator 调度策略 |
| Adapter 抽象设计如何取舍？ | 协议翻译 vs 完美抽象的权衡 |
| 上下文超限怎么处理？ | 滑动窗口 / 摘要压缩 / 用户手动 Pin |
| 如何支持新接入一个 Agent 平台？ | 实现 BaseAgentAdapter + 注册到 registry，约 100 行代码 |
| 如何防止 Prompt 注入？ | 用户输入与 System Prompt 隔离 + Provider 自带防护 |
| AI 协作具体做了哪些规范？ | CLAUDE.md + Spec + Cursor Rules + 协作日志 |

---

## 附录 A：术语表

| 术语 | 说明 |
|------|------|
| **Agent** | AI 代理，可以理解为一个"聊天对象"，背后是 LLM + 配置（System Prompt、工具集等） |
| **Adapter** | 适配器，屏蔽不同 AI 平台 API 差异，提供统一接口 |
| **Orchestrator** | 主 Agent，负责拆解任务、协调子 Agent |
| **ContentBlock** | 消息内容块，支持文本、代码、Diff、网页预览等多种类型 |
| **SSE** | Server-Sent Events，HTTP 单向流式协议 |
| **Vibe Coding** | 与 AI 协作编程的方式，强调契约先行、Spec 沉淀 |

## 附录 B：参考资料

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SSE Starlette](https://github.com/sysid/sse-starlette)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Vite + React 模板](https://vite.dev/guide/)
- [shadcn/ui](https://ui.shadcn.com/)
- [Zustand](https://zustand-demo.pmnd.rs/)
- [TanStack Query](https://tanstack.com/query/latest)
- [OpenAPI Generator](https://github.com/openapi-ts/openapi-typescript)
