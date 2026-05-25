# AgentHub 三人分工开发方案（Team Division Plan）

> 配套文档：[development-plan.md](./development-plan.md)
> 文档版本：v1.0
> 最后更新：2026-05-22

---

## 目录

1. [团队结构与角色](#1-团队结构与角色)
2. [协作原则与解耦设计](#2-协作原则与解耦设计)
3. [F（前端）详细任务清单](#3-f前端详细任务清单)
4. [B1（后端核心）详细任务清单](#4-b1后端核心详细任务清单)
5. [B2（Agent 集成）详细任务清单](#5-b2agent-集成详细任务清单)
6. [关键协作接口](#6-关键协作接口)
7. [Sprint × 角色 任务矩阵](#7-sprint--角色-任务矩阵)
8. [每日工作流](#8-每日工作流)
9. [依赖关系与关键路径](#9-依赖关系与关键路径)
10. [冲突预防机制](#10-冲突预防机制)
11. [个人答辩准备](#11-个人答辩准备)

---

## 1. 团队结构与角色

### 1.1 角色定位

| 代号 | 全称 | 主战场 | 核心产出 |
|------|------|--------|----------|
| **F** | Frontend Engineer | React SPA | 用户能看到的所有交互 |
| **B1** | Backend Core Engineer | FastAPI + DB | 数据持久化、认证、IM 协议、SSE 网关 |
| **B2** | Agent Integration Engineer | LLM Provider + 编排 | Adapter、Orchestrator、产物解析 |

### 1.2 工作量预估（按 14 天 Sprint 计）

| 角色 | P0 工作量 | P1 工作量 | P2 工作量 | 总工时（h） |
|------|-----------|-----------|-----------|-------------|
| **F** | ~50h | ~25h | ~15h | ~90h |
| **B1** | ~50h | ~25h | ~15h | ~90h |
| **B2** | ~50h | ~30h | ~10h | ~90h |

> 每人日均 ~6-7h，14 天约 90h，符合实际作息。

### 1.3 各角色技能要求

| 角色 | 必备技能 | 加分技能 |
|------|----------|----------|
| **F** | React、TypeScript、CSS、HTTP | Tailwind、shadcn、Zustand、SSE/EventSource |
| **B1** | Python、SQL、HTTP、async | FastAPI、SQLAlchemy 2.0、JWT、Redis |
| **B2** | Python、LLM API 使用 | Anthropic/OpenAI SDK、async generator、Prompt 工程 |

---

## 2. 协作原则与解耦设计

### 2.1 三大解耦点

```
                    ┌────────────────────────────┐
                    │   F（前端）                  │
                    └──────────┬─────────────────┘
                               │
                       【契约 1】OpenAPI Spec
                       shared/openapi.yaml
                               │
                    ┌──────────▼─────────────────┐
                    │   B1（核心后端）             │
                    └──────────┬─────────────────┘
                               │
                       【契约 2】BaseAgentAdapter
                       backend/app/agents/base.py
                               │
                    ┌──────────▼─────────────────┐
                    │   B2（Agent 集成）           │
                    └────────────────────────────┘
```

### 2.2 协作原则（必须严格执行）

1. **契约先行**
   - 任何 API 变更，必须先改 `shared/openapi.yaml`
   - F 用 `openapi-typescript` 生成 TS 类型，不手写
   - B1 用 FastAPI 路由的 Pydantic Schema 与 OpenAPI 对齐

2. **接口先行**
   - B2 必须在 Day 1-2 内交付 `BaseAgentAdapter` 抽象 + `MockAdapter` 实现
   - B1 不依赖 Claude/OpenAI 真实 API 即可开发完整功能

3. **Mock 优先**
   - F 用 MSW 或 `prism mock` 起 Mock Server，不阻塞等后端
   - 三人可以从 Day 3 开始完全并行

4. **目录边界清晰**
   - 每人只改自己负责的目录
   - 跨目录改动必须发起 PR，由对应 owner Review

5. **每日同步契约变更**
   - 早会时若有 OpenAPI 变更，全员在 5 分钟内 `git pull` + `pnpm run gen:types`

### 2.3 文件所有权矩阵

| 目录 / 文件 | F | B1 | B2 |
|------------|---|----|----|
| `frontend/**` | ✅ Owner | 👁 Read | 👁 Read |
| `backend/app/core/**` | 👁 Read | ✅ Owner | 👁 Read |
| `backend/app/models/**` | ❌ | ✅ Owner | 👁 Read |
| `backend/app/schemas/**` | 👁 Read | 🤝 Co-Own | 🤝 Co-Own |
| `backend/app/api/v1/auth.py` | 👁 Read | ✅ Owner | ❌ |
| `backend/app/api/v1/conversations.py` | 👁 Read | ✅ Owner | ❌ |
| `backend/app/api/v1/messages.py` | 👁 Read | ✅ Owner | ❌ |
| `backend/app/api/v1/stream.py` | 👁 Read | ✅ Owner | 👁 Read |
| `backend/app/api/v1/agents.py` | 👁 Read | 🤝 Co-Own | ✅ Owner |
| `backend/app/services/**` | ❌ | ✅ Owner | 👁 Read |
| `backend/app/agents/**` | ❌ | 👁 Read | ✅ Owner |
| `shared/openapi.yaml` | 🤝 Co-Own | ✅ Owner | 🤝 Co-Own |
| `docs/**` | 🤝 Co-Own | 🤝 Co-Own | 🤝 Co-Own |
| `CLAUDE.md` | 🤝 Co-Own | 🤝 Co-Own | 🤝 Co-Own |
| `docker-compose.yml` | 👁 Read | ✅ Owner | 👁 Read |

> ✅ Owner：主要负责 / 🤝 Co-Own：共同负责（需要协商） / 👁 Read：只读 / ❌：不应改动

---

## 3. F（前端）详细任务清单

### 3.1 职责范围

- 搭建 React + Vite 项目
- 实现 IM 风格聊天界面（侧边栏 + 主聊天区）
- 实现富媒体消息渲染（Text/Code/Diff/WebPreview）
- 实现 SSE 流式响应消费
- 实现登录、Agent 管理等辅助页面
- 录制 Demo 视频（团队协作）

### 3.2 技术栈速查

```
React 18 + Vite + TypeScript
├── 路由：React Router v6
├── 状态：Zustand（UI）+ TanStack Query（服务端数据）
├── UI：Tailwind CSS + shadcn/ui
├── 富文本：react-markdown + shiki
├── Diff：react-diff-viewer-continued
├── HTTP：axios + openapi-typescript（类型生成）
├── 实时：原生 EventSource
└── 测试：vitest + @testing-library
```

### 3.3 任务清单（按 Sprint 排序）

#### Sprint 0 — 脚手架（Day 1-2）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 用 Vite 创建 React + TS 项目 | `frontend/` | `pnpm dev` 启动成功 |
| 配置 Tailwind + shadcn/ui | `tailwind.config.ts`, `components/ui/` | shadcn 组件可用 |
| 安装核心依赖 | `package.json` | TanStack Query、Zustand、react-router、axios |
| 配置 ESLint + Prettier | `.eslintrc`, `.prettierrc` | 自动格式化生效 |
| 搭建路由骨架（登录、聊天、Agent） | `router.tsx` | 3 个空页面可访问 |
| 编写 API 客户端封装 | `src/lib/api.ts` | axios 实例 + JWT 拦截器 |
| 编写 OpenAPI 类型生成脚本 | `package.json` 中加 `gen:types` | 跑通生成 `src/lib/types.ts` |
| 搭建 MSW Mock Server | `src/mocks/handlers.ts` | 拦截 API 返回假数据 |
| 实现 authStore（JWT 持久化） | `stores/authStore.ts` | localStorage 存取 token |

**Day 2 验收**：本地可登录（mock）、可看到空白聊天页。

#### Sprint 1 — 单聊 MVP（Day 3-5）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 登录页（用户名 + 密码） | `pages/LoginPage.tsx` | 调用 `/auth/login` 成功跳转 |
| 注册页 | `pages/LoginPage.tsx`（同页切换） | 注册并自动登录 |
| 主布局（左侧栏 + 主区） | `layout/AppLayout.tsx`, `Sidebar.tsx` | 响应式布局 |
| 会话列表（最近、置顶分组） | `conversation/ConversationList.tsx` | TanStack Query 拉数据 |
| 新建会话弹窗（选 Agent） | `NewConversationDialog.tsx` | POST 创建后跳转 |
| 聊天窗口骨架 | `chat/ChatWindow.tsx` | 顶栏 + 消息列表 + 输入框 |
| 消息列表（虚拟滚动可选） | `chat/MessageList.tsx` | 自动滚到底部 |
| 消息气泡 | `chat/MessageBubble.tsx` | 用户/Agent 不同样式 |
| 文本消息块 | `blocks/TextBlock.tsx` | react-markdown 渲染 |
| 消息输入框（多行、Shift+Enter 换行） | `chat/MessageInput.tsx` | 发送回调 |
| **SSE 客户端封装** | `lib/sse.ts`, `hooks/useStream.ts` | EventSource + 事件分发 |
| 流式消息增量渲染 | `chat/MessageList.tsx` | 文字逐字出现 |
| 错误提示（Toast） | `components/ui/toast` | API 错误友好提示 |

**Day 5 验收（里程碑 1）**：登录 → 选 Claude → 发"写个 Todo" → 流式回复正常出现。

#### Sprint 2 — 富媒体 + Agent 管理（Day 6-8）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 代码消息块（shiki 高亮 + 复制按钮） | `blocks/CodeBlock.tsx` | 30+ 语言高亮、一键复制 |
| Diff 视图组件 | `blocks/DiffBlock.tsx` | 新增/删除/修改三色显示 |
| 网页预览卡片 | `blocks/WebPreviewCard.tsx` | iframe + 标题描述 |
| 文件附件组件 | `blocks/FileAttachment.tsx` | 点击下载 |
| Agent 列表页 | `pages/AgentsPage.tsx`, `agents/AgentCard.tsx` | 头像 + 能力标签 |
| 创建自定义 Agent 表单 | `agents/CustomAgentForm.tsx` | name + system_prompt + model |
| 会话置顶 / 归档 / 搜索 | `Sidebar.tsx`, `ConversationItem.tsx` | 右键菜单 + 搜索框 |
| 消息历史分页加载 | `hooks/useMessages.ts` | 向上滚动加载更多 |
| 重新生成按钮 | `chat/MessageBubble.tsx` | 重新发送上一条 |
| Pin 消息（标记为长期上下文） | API 调用 + UI | 已 Pin 消息有标识 |

**Day 8 验收（里程碑 2）**：Agent 回复的代码自动高亮，Diff 视图正确显示，可创建自定义 Agent。

#### Sprint 3 — 群聊 + Orchestrator（Day 9-11）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 群聊会话新建（多选 Agent） | `NewConversationDialog.tsx` | 支持选 2+ Agent |
| 群聊会话头部（多头像叠加） | `chat/ChatWindow.tsx` | 显示所有 Agent |
| **@ Agent 提及选择器** | `AgentMentionPicker.tsx` | 输入 `@` 弹出选择 |
| 群聊消息气泡（显示发言 Agent 头像） | `MessageBubble.tsx` | Agent 切换时清晰区分 |
| Orchestrator 任务卡片渲染 | `blocks/TaskCardBlock.tsx`（新） | 任务列表 + 状态 |
| 流式期间显示"正在调用 @xxx Agent" | `MessageList.tsx` | 类似群聊里"对方正在输入" |
| 复制完整对话为 Markdown | `chat/ChatWindow.tsx` | 一键导出 |

**Day 11 验收（里程碑 3）**：群聊 @Orchestrator + 任务 → 看到任务拆解 + 多 Agent 接力回复。

#### Sprint 4 — 打磨 + 交付（Day 12-14）

| 任务 | 验收 |
|------|------|
| UI 细节打磨（动画、过渡、Loading 骨架屏） | 流畅度提升 |
| Dark Mode 切换 | 全局主题切换正常 |
| 移动端响应式适配 | iPhone 尺寸下可用 |
| 性能优化（虚拟列表、图片懒加载） | 1000 条消息流畅 |
| **【P2】Tauri 桌面端打包** | macOS / Windows 可启动 |
| **【P2】PWA 配置** | 可"添加到主屏幕" |
| 录制 Demo 视频（团队） | 3 分钟覆盖核心流程 |
| 写前端 README + 部署说明 | 他人按文档可启动 |

### 3.4 F 的关键产出物

```
frontend/                              # 完整 React 项目
├── src/
│   ├── lib/                           # 工具层（10 文件）
│   ├── stores/                        # 3 个 Zustand store
│   ├── hooks/                         # 4 个业务 Hook
│   ├── pages/                         # 3 个页面
│   └── components/                    # ~25 个组件
└── tests/                             # 关键组件单测
```

### 3.5 F 的答辩重点

- **SSE 消费策略**：如何处理事件乱序、中断、重连？为什么用原生 EventSource？
- **流式渲染优化**：如何避免每个 delta 都触发整个列表重渲染？（讲 React Memo + 索引更新）
- **状态管理分层**：Zustand 管什么、TanStack Query 管什么？为什么这样分？
- **类型安全**：OpenAPI → TS 类型自动生成的工作流
- **三端跨平台**：Tauri 包装 SPA 的成本几乎为零

---

## 4. B1（后端核心）详细任务清单

### 4.1 职责范围

- FastAPI 项目骨架与基础设施（Docker、DB、Redis）
- 数据库 Schema 与 Alembic 迁移
- JWT 认证体系
- 会话 / 消息 / Agent CRUD API
- **SSE 流式端点**（核心，调用 B2 的 Adapter）
- 上下文组装（历史消息 → Adapter 输入）
- OpenAPI 规范主要维护者

### 4.2 技术栈速查

```
Python 3.11 + FastAPI + Uvicorn
├── ORM：SQLAlchemy 2.0 (async) + Alembic
├── 校验：Pydantic v2
├── 认证：python-jose（JWT）+ passlib (bcrypt)
├── SSE：sse-starlette
├── DB：PostgreSQL 15 + asyncpg
├── 缓存：Redis 7 (redis-py asyncio)
└── 测试：pytest + pytest-asyncio + httpx + testcontainers
```

### 4.3 任务清单（按 Sprint 排序）

#### Sprint 0 — 脚手架（Day 1-2）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 用 `uv init` 创建 backend 项目 | `pyproject.toml` | `uv run uvicorn ...` 启动 |
| 安装核心依赖 | `pyproject.toml` | fastapi、sqlalchemy、alembic、jose 等 |
| 配置 ruff + mypy | `pyproject.toml` | `ruff check` 通过 |
| `docker-compose.yml` 编写 | `docker-compose.yml` | postgres + redis + backend 启动 |
| `Dockerfile` 编写 | `backend/Dockerfile` | 镜像构建成功 |
| `.env.example` + Settings | `core/config.py` | pydantic-settings 读环境变量 |
| 数据库连接 + 依赖注入 | `core/database.py`, `core/deps.py` | `Depends(get_db)` 可用 |
| Alembic 初始化 | `alembic.ini`, `alembic/` | `alembic upgrade head` 成功 |
| **设计 OpenAPI v0.1** | `shared/openapi.yaml` | 所有端点定义完成 |
| SQLAlchemy 模型（User/Conv/Msg/Agent） | `models/*.py` | 第一次 migration 跑通 |
| Pydantic Schema | `schemas/*.py` | 与 OpenAPI 对齐 |
| FastAPI 入口 + CORS | `main.py` | `/docs` 可访问 |
| ContentBlock 联合类型 | `schemas/message.py` | discriminator 校验通过 |

**Day 2 验收**：`docker compose up` 启动后端，`/docs` 显示完整 API 列表。

#### Sprint 1 — 认证 + 会话/消息 CRUD（Day 3-5）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| JWT 工具（生成、校验、密码哈希） | `core/security.py` | 单测通过 |
| `get_current_user` 依赖 | `core/deps.py` | 401 错误正确返回 |
| `/auth/register`, `/auth/login`, `/auth/me` | `api/v1/auth.py` | Postman 测试通过 |
| Conversation CRUD | `api/v1/conversations.py`, `services/conversation_service.py` | 5 个端点齐全 |
| Message 历史 + 发送 | `api/v1/messages.py`, `services/message_service.py` | 分页正确 |
| 发送消息时创建 pending agent_message | `services/message_service.py` | 返回 user + agent 双 ID |
| **SSE 流式端点** | `api/v1/stream.py` | 调用 B2 MockAdapter 跑通 |
| Context Builder | `services/context_builder.py` | 按 token 限制裁剪 |
| 异常处理中间件 | `main.py` | 统一错误响应格式 |
| 跨域配置 | `main.py` | 前端可正常调用 |
| pytest 单元测试 | `tests/test_auth.py`, `test_conversations.py` | 覆盖率 > 60% |

**Day 5 验收（里程碑 1）**：完整流程跑通——前端登录、调用 API、收到 SSE 流。

#### Sprint 2 — 完善 + Agent CRUD 协作（Day 6-8）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 会话置顶 / 归档 / 改名 | `api/v1/conversations.py` PATCH | 字段独立更新 |
| 消息搜索（PG `tsvector` 或简单 `ILIKE`） | `api/v1/messages.py` | 关键词命中返回 |
| Pin 消息 API（消息表加 `is_pinned`） | DB 迁移 + API | 已 Pin 消息标识 |
| 消息状态机维护 | `services/message_service.py` | pending→streaming→done/error |
| Stream 端点持久化优化 | `api/v1/stream.py` | 失败时正确标记 error 状态 |
| 重新生成 API | `api/v1/messages.py` POST `/regenerate` | 删旧 agent 消息生成新的 |
| Agent CRUD（与 B2 协作） | `api/v1/agents.py` | B2 实现，B1 协助路由集成 |
| Alembic Seed Agent 数据脚本 | `alembic/seeds/seed_agents.py` | 启动时插入内置 Agent |

**Day 8 验收（里程碑 2）**：Agent 列表 / 创建 API 完整，会话管理功能齐全。

#### Sprint 3 — 群聊广播 + Orchestrator 集成（Day 9-11）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 群聊会话支持（多 agent_ids） | `services/conversation_service.py` | mode=group 字段处理 |
| 群聊消息路由（@ 提及解析） | `services/message_service.py` | 识别 `@agent_id` |
| Orchestrator 触发流程 | `api/v1/stream.py` | 群聊默认走 Orchestrator |
| **Redis Pub/Sub 多 SSE 订阅者支持** | `core/pubsub.py` | 同一会话多端流接收 |
| 流式端点性能优化 | `api/v1/stream.py` | 上游异常 → 友好 SSE error |
| 集成测试（含 SSE） | `tests/test_stream.py` | testcontainers 完整跑通 |

**Day 11 验收（里程碑 3）**：群聊场景后端跑通。

#### Sprint 4 — 打磨 + 文档（Day 12-14）

| 任务 | 验收 |
|------|------|
| 性能测试（100 并发） | locust 报告 |
| 错误日志结构化（structlog） | JSON 日志可解析 |
| API 文档（人类可读版） | `docs/api-spec.md` |
| 数据库 ER 图 | `docs/tech-architecture.md` |
| 答辩讲稿 | 自己负责模块讲透 |

### 4.4 B1 的关键产出物

```
backend/
├── app/
│   ├── core/                          # 6 文件
│   ├── models/                        # 4 模型
│   ├── schemas/                       # 4 schema
│   ├── api/v1/                        # 5 路由文件
│   └── services/                      # 3 service
├── alembic/                           # Migration + Seed
├── tests/                             # ~10 测试文件
└── pyproject.toml + Dockerfile
```

### 4.5 B1 的答辩重点

- **数据库设计取舍**：为什么 content 用 JSONB？性能 vs 结构化的权衡
- **SSE 端点实现**：如何把 async generator 转 SSE event？写库与流式的并发关系
- **JWT 中间件**：FastAPI 依赖注入如何优雅地做权限校验
- **Context Builder 策略**：超长上下文如何裁剪？为什么不直接发全量历史
- **B1 ↔ B2 解耦**：为什么 B1 完全不感知具体 LLM Provider？

---

## 5. B2（Agent 集成）详细任务清单

> B2 当前更细的执行路线图和任务编号以 [docs/b2-task-dispatch/B2-roadmap.md](b2-task-dispatch/B2-roadmap.md) 为准；本节保留团队级分工视角。

### 5.1 职责范围

- 设计并实现 `BaseAgentAdapter` 抽象接口
- 实现 Claude、OpenAI 适配器
- 实现自定义 Agent（基于 System Prompt 包装）
- **实现 Orchestrator 任务拆解与协调**
- 实现产物解析器（从 LLM 输出识别代码/Diff/URL）
- 内置 Agent Seed 数据
- Agent CRUD API（与 B1 协作）

### 5.2 技术栈速查

```
Python 3.11
├── Anthropic SDK: anthropic
├── OpenAI SDK: openai
├── 流式：async generator
├── 配置：从 DB 读取 Agent 配置
└── 测试：pytest + pytest-asyncio + 真实 LLM 调用（mark slow）
```

### 5.3 任务清单（按 Sprint 排序）

#### Sprint 0 — 设计核心抽象（Day 1-2）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| 设计 `BaseAgentAdapter` ABC | `agents/base.py` | B1 Review 通过 |
| 定义 `StreamChunk`、`ChatMessage` 类型 | `agents/types.py` | 覆盖所有事件类型 |
| 编写 MockAdapter（用于联调） | `agents/adapters/mock.py` | yield 模拟 token 流 |
| 设计 Adapter Registry | `agents/registry.py` | `get_adapter(agent_id)` 工作 |
| 与 B1 对齐 SSE 事件类型 | `shared/openapi.yaml` + `docs/spec/streaming.spec.md` | 文档化所有事件 |
| 阅读 Anthropic + OpenAI SDK 流式 API | 文档阅读笔记 | 输出 `docs/spec/llm-api-notes.md` |
| **设计 Orchestrator Spec** | `docs/spec/orchestrator.spec.md` | 决定任务拆解方式 |

**Day 2 验收**：B1 用 MockAdapter 即可跑通 SSE 端到端。

#### Sprint 1 — Claude + OpenAI 适配器（Day 3-5）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| Claude Adapter（流式） | `agents/adapters/claude.py` | 真实调用拿到流 |
| 解析 Claude 流事件 → StreamChunk | 同上 | content_block_delta 正确转换 |
| OpenAI Adapter（流式） | `agents/adapters/openai.py` | 真实调用拿到流 |
| 解析 OpenAI delta → StreamChunk | 同上 | choices[0].delta.content 流式 |
| Adapter Registry 注入 DB | `agents/registry.py` | 按 agent_id 从 DB 查 provider |
| 自定义 Agent Adapter（套 System Prompt） | `agents/adapters/custom.py` | 底层复用 Claude/OpenAI |
| 内置 Agent Seed 数据 | `alembic/seeds/seed_agents.py` | 4-5 个内置 Agent |
| 单元测试（用 Mock 上游） | `tests/test_adapters.py` | 流式事件断言 |

**Day 5 验收（里程碑 1）**：B1 的 SSE 端点用真实 Claude 跑通"Hello, write Python"。

#### Sprint 2 — 产物解析 + Agent CRUD（Day 6-8）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| **流式过程中实时识别代码围栏** | `agents/artifact_parser.py` | 检测到 ``` 时切换 block |
| URL 自动识别 → WebPreviewBlock | 同上 | 流末尾抓取 URL |
| Diff 块识别（特殊 fence ```diff） | 同上 | 识别 +/- 行 |
| Agent CRUD API（路由层与 B1 协作） | `api/v1/agents.py` | List/Create/Update/Delete |
| 自定义 Agent 创建支持 model 配置 | `agents/adapters/custom.py` | 用户可选 claude-3-5-sonnet 等 |
| 失败重试（指数退避，3 次） | `agents/registry.py` | rate limit 自动重试 |
| 错误降级（rate limit → 友好错误） | 同上 | SSE error event 输出 |

**Day 8 验收（里程碑 2）**：Agent 输出代码块 → 前端高亮显示，自定义 Agent 可用。

#### Sprint 3 — Orchestrator 实现（Day 9-11）

| 任务 | 关键文件 | 验收 |
|------|----------|------|
| **Orchestrator 任务拆解** | `agents/orchestrator.py` | 用 Claude function calling |
| 任务拆解输出 → 任务卡片 ContentBlock | 同上 | 前端可渲染任务列表 |
| 顺序调用子 Adapter | 同上 | 每个子 Agent 流式输出 |
| 子 Agent 输出聚合 | 同上 | 块索引管理避免冲突 |
| 异常降级（子 Agent 失败 → 主 Agent 兜底回复） | 同上 | 不会卡死 |
| Orchestrator 测试 | `tests/test_orchestrator.py` | 用 Mock 子 Adapter |
| **【P2】并行调用独立子任务** | 同上 | asyncio.gather + 顺序输出 |

**Day 11 验收（里程碑 3）**：群聊 @Orchestrator → 完整任务流程可演示。

#### Sprint 4 — 打磨 + 文档（Day 12-14）

| 任务 | 验收 |
|------|------|
| 性能优化（流式延迟） | 首 token < 2s |
| 添加更多内置 Agent（Writer、Translator） | 至少 5 个内置 |
| Adapter 设计文档 | `docs/tech-architecture.md` 含 |
| Orchestrator 任务图设计文档 | 同上 |
| AI 协作记录沉淀 | `docs/ai-collaboration-log.md` |
| 答辩讲稿 | 准备 5 分钟讲稿 |

### 5.4 B2 的关键产出物

```
backend/app/agents/
├── base.py                            # 核心抽象（~50 行）
├── types.py                           # 类型定义（~80 行）
├── registry.py                        # 工厂（~100 行）
├── orchestrator.py                    # 编排器（~200 行）
├── artifact_parser.py                 # 产物解析（~150 行）
└── adapters/
    ├── claude.py                      # ~150 行
    ├── openai.py                      # ~150 行
    ├── custom.py                      # ~100 行
    └── mock.py                        # ~50 行
```

### 5.5 B2 的答辩重点

- **Adapter 抽象设计**：为什么用"协议翻译"而非"完美抽象"？流式 chunk 标准化的取舍
- **Orchestrator 拆解策略**：用 function calling 强制结构化输出，为什么不用 ReAct？
- **流式产物解析**：状态机识别代码围栏的算法
- **新接入 Agent 的成本**：实现 BaseAgentAdapter → 注册到 registry → 约 100 行代码
- **错误处理**：上游 rate limit / token 超限 / 网络中断的降级策略

---

## 6. 关键协作接口

### 6.1 契约 1：OpenAPI Spec（F ↔ B1）

**文件**：`shared/openapi.yaml`
**所有权**：B1 主维护，F + B2 协同
**变更流程**：
1. 任何路由变更，先在此文件改 → 提 PR
2. 至少一人 Review
3. 合并后 F 跑 `pnpm gen:types`，B1 同步 Pydantic Schema

**示例片段**：
```yaml
paths:
  /api/v1/messages/{messageId}/stream:
    get:
      summary: SSE stream for agent response
      parameters:
        - name: messageId
          in: path
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200':
          description: SSE stream
          content:
            text/event-stream:
              schema:
                type: string
```

### 6.2 契约 2：BaseAgentAdapter（B1 ↔ B2）

**文件**：`backend/app/agents/base.py`
**所有权**：B2 主维护
**B1 视角**：
```python
# B1 在 stream.py 中调用
from app.agents.registry import get_adapter

adapter = get_adapter(agent_id)
async for chunk in adapter.stream(messages, system_prompt, config):
    yield {"event": chunk.event_type, "data": chunk.to_json()}
```

**B2 视角**：
```python
# B2 实现新 Adapter 时
class MyAdapter(BaseAgentAdapter):
    async def stream(self, messages, system_prompt, config):
        async for chunk in upstream_call(...):
            yield StreamChunk(event_type="delta", ...)
```

### 6.3 契约 3：Agent CRUD（B1 + B2 共同维护）

`api/v1/agents.py` 由 B2 主导编写，但需要：
- 用 B1 的 `get_db`、`get_current_user` 依赖
- 用 B1 的 `Agent` 模型
- B2 加自己的业务校验（如 provider 合法性、System Prompt 长度限制）

### 6.4 契约 4：ContentBlock 类型（全员共用）

**文件**：`backend/app/schemas/message.py` + `frontend/src/lib/types.ts`
**变更流程**：
1. 在 `schemas/message.py` 中改 Pydantic 模型
2. 同步更新 `shared/openapi.yaml` 中的 `components.schemas`
3. F 重新生成类型
4. F 在 `components/blocks/` 加新组件

---

## 7. Sprint × 角色 任务矩阵

| Sprint | F（前端） | B1（核心后端） | B2（Agent 集成） |
|--------|----------|----------------|------------------|
| **S0 Day 1-2** | Vite 脚手架、Tailwind、Router、API Client、Mock | FastAPI 脚手架、Docker、DB、Models、OpenAPI v0.1 | BaseAgentAdapter、MockAdapter、Registry 设计 |
| **S1 Day 3-5** | 登录、会话列表、聊天窗、文本块、SSE 消费 | 认证、CRUD、SSE 端点、Context Builder | Claude / OpenAI Adapter、内置 Seed |
| **S2 Day 6-8** | 代码块、Diff、网页预览、Agent 页面 | Pin / 搜索 / 重生成、Agent CRUD 路由 | 产物解析、自定义 Agent、Agent CRUD 业务 |
| **S3 Day 9-11** | @Mention、群聊 UI、任务卡片 | 群聊广播、Redis Pub/Sub、集成测试 | Orchestrator、错误降级 |
| **S4 Day 12-14** | UI 打磨、Demo 视频、可选 Tauri | 性能 / 日志 / API 文档 | 文档、AI 协作记录、扩展 Agent |

### 7.1 关键同步点（必须按时完成，否则阻塞他人）

| 时间 | 谁 | 交付物 | 阻塞谁 |
|------|----|--------|--------|
| **Day 1 EOD** | B2 | `BaseAgentAdapter` + `MockAdapter` 初稿 | B1 |
| **Day 2 EOD** | B1 | OpenAPI v0.1、所有 Pydantic Schema | F |
| **Day 2 EOD** | B1 | Docker Compose 跑通 | B2 |
| **Day 3 EOD** | F | OpenAPI → TS 类型生成跑通 | 自己 |
| **Day 4 EOD** | B1 | SSE 端点（用 MockAdapter）跑通 | F |
| **Day 4 EOD** | B2 | Claude Adapter 第一版可用 | B1 |
| **Day 5 EOD** | 全员 | 单聊 MVP 联调通过 | Sprint 1 收尾 |
| **Day 9 EOD** | B2 | Orchestrator 初版 | F |
| **Day 11 EOD** | 全员 | 群聊联调通过 | Sprint 3 收尾 |

---

## 8. 每日工作流

### 8.1 标准一天

```
09:00  早会（15 min）
       ├─ 每人 3 min：昨天/今天/阻塞
       └─ 同步 OpenAPI / Adapter 变更
09:15  开始编码
12:00  午饭
13:00  继续编码
16:00  PR 提交 / Review
18:00  晚同步（异步）
       └─ 群里发 Daily Update（含 PR 链接、Demo 截图）
```

### 8.2 PR 流程

```
1. feat/<owner>-<feature> 分支开发
2. 本地跑通 docker compose up，确认改动有效
3. 推到远程，提 PR
4. 至少 1 人 Review（关注：契约、命名、测试）
5. CI 通过（lint + test）
6. Squash & Merge 到 main
7. 其他人 git pull main，必要时重新生成类型
```

### 8.3 联调流程

```
当前端调通后端某 API 时：
1. F 在 Postman 中验证 API 行为符合 OpenAPI
2. 若不符合：在 PR 中提 issue，由 B1/B2 Fix
3. 若符合：F 在前端用真实 API 替代 Mock
4. 端到端验证（用户操作 → 数据库变化）
```

---

## 9. 依赖关系与关键路径

### 9.1 依赖图

```
                    ┌──────────────────┐
                    │  OpenAPI v0.1    │ ← B1 主，Day 2 EOD
                    └────────┬─────────┘
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌──────────────┐  ┌────────────┐
     │ F: API     │  │ B1: API 实现 │  │ B2: Adapter│
     │ Client + UI│  │ + CRUD       │  │ 实现       │
     └─────┬──────┘  └──────┬───────┘  └─────┬──────┘
           │                │                │
           │         ┌──────▼────────┐       │
           │         │ B1: SSE 端点  │◀──────┘
           │         │ (调用 Adapter)│
           │         └──────┬────────┘
           │                │
           ▼                ▼
     ┌─────────────────────────────┐
     │  F: SSE 消费 + 流式渲染     │
     └─────────────────────────────┘
                    │
                    ▼
            【里程碑 1】单聊 MVP
                    │
                    ▼
            ┌──────────────┐
            │ B2:          │
            │ Orchestrator │
            └───────┬──────┘
                    │
                    ▼
            【里程碑 3】群聊 Orchestrator
```

### 9.2 关键路径分析

**最长路径**（决定项目能否按时完成）：
```
OpenAPI v0.1 (D2)
  → Claude Adapter (D4)
  → SSE 端点联调 (D5)
  → Orchestrator (D11)
  → 全联调 (D12)
```

**关键风险**：B2 的 Orchestrator 是关键路径的关键节点，**必须在 Day 11 EOD 完成可演示状态**，否则群聊里程碑滞后。

### 9.3 并行机会

- **Day 3-5**：F 用 Mock 开发前端，B1 用 MockAdapter 开发 SSE，B2 开发真实 Adapter——**三人完全并行**
- **Day 6-8**：F 做富媒体组件，B1 做 Pin / 搜索，B2 做产物解析——**三人完全并行**
- **Day 9-11**：F 做群聊 UI，B1 做广播，B2 做 Orchestrator——**三人完全并行**

---

## 10. 冲突预防机制

### 10.1 文件级冲突预防

**铁律**：避免两人改同一个文件。

| 共享文件 | 协调策略 |
|----------|----------|
| `shared/openapi.yaml` | 改前在群里 @ 所有人，30 min 内合并 |
| `backend/app/schemas/*.py` | 由 B1 主导，B2 加块类型需提前协商 |
| `CLAUDE.md` / `docs/*.md` | 每人加自己负责模块的章节，避免同段落 |
| `backend/app/api/v1/agents.py` | B2 主导，B1 协助路由集成 |
| `docker-compose.yml` | B1 主导，其他人提 issue |

### 10.2 沟通规范

- **同步沟通**：早会、关键节点（合并大 PR 前）
- **异步沟通**：群内 Daily Update、PR Review、issue 评论
- **紧急沟通**：阻塞时直接私聊 + @ 群通知

### 10.3 知识共享

- **每 3 天一次 30 分钟分享**：每人讲一个自己模块的关键决策
- **CLAUDE.md 持续更新**：发现新的 AI 协作经验立即沉淀

---

## 11. 个人答辩准备

### 11.1 答辩材料清单（每人）

- [ ] 5 分钟个人讲稿（按"问题→设计→实现→效果"结构）
- [ ] 关键代码截图 3-5 张
- [ ] AI 协作 Prompt 记录 3 个（含初稿、调整后、最终代码）
- [ ] 自己模块的架构图（独立绘制，不要照搬团队图）
- [ ] 备答深度问题（每人准备 5 个，参见各角色"答辩重点"）

### 11.2 F 个人讲稿提纲（5 分钟）

```
1. (30s) 用户场景：用户打开 AgentHub，看到熟悉的 IM 界面
2. (60s) 前端架构：React + Vite + Zustand + TanStack Query 的分层
3. (90s) 核心难点 1：SSE 流式响应消费
   - 为什么用原生 EventSource？
   - 如何处理乱序、增量更新？
4. (90s) 核心难点 2：富媒体消息渲染
   - ContentBlock 联合类型设计
   - 代码块 + Diff + WebPreview 组件复用模式
5. (30s) 三端跨平台：Tauri 包装零成本
6. (30s) 闭环：流畅的 IM 体验如何超越普通 ChatGPT UI
```

### 11.3 B1 个人讲稿提纲（5 分钟）

```
1. (30s) 后端定位：IM 协议网关 + 数据持久化
2. (60s) 数据模型：四张表的设计，JSONB 存富媒体的考量
3. (90s) 核心难点 1：SSE 流式端点
   - 异步生成器与 DB 累积写入的并发
   - 错误时如何优雅终止
4. (90s) 核心难点 2：B1 ↔ B2 的解耦
   - BaseAgentAdapter 让 B1 完全不感知具体 Provider
   - Context Builder 单向数据流
5. (30s) 认证体系：JWT + FastAPI 依赖注入
6. (30s) 一句话总结：高内聚低耦合，团队并行
```

### 11.4 B2 个人讲稿提纲（5 分钟）

```
1. (30s) Agent 集成定位：屏蔽 LLM 差异 + 多 Agent 编排
2. (60s) Adapter 抽象设计：协议翻译模式
   - 为什么不做完美抽象？
3. (90s) 核心难点 1：Orchestrator 任务拆解
   - 用 Claude function calling 强制结构化输出
   - 子 Agent 依次调用 / 并行调用的取舍
4. (90s) 核心难点 2：流式产物解析
   - 实时识别代码围栏的状态机
   - 如何把 ``` 切换变成 ContentBlock 切换
5. (30s) 错误降级：rate limit / 网络中断的应对
6. (30s) 接入新 Agent 的成本：100 行代码即可
```

---

## 附录 A：每日检查清单

### A.1 每人每日 5 项检查

- [ ] 自己的代码本地跑通了吗？
- [ ] OpenAPI 有变更吗？通知了其他人吗？
- [ ] 今天的 PR 提了吗？
- [ ] 阻塞别人的事情解决了吗？
- [ ] AI 协作日志更新了吗？

### A.2 每个 Sprint 结束检查

- [ ] 里程碑达成了吗？
- [ ] 端到端 Demo 跑通了吗？
- [ ] 所有 P0 任务完成了吗？
- [ ] 文档同步更新了吗？
- [ ] 下个 Sprint 的依赖梳理清楚了吗？

---

## 附录 B：紧急情况处理

| 情况 | 应对 |
|------|------|
| 某人病假 | 优先保住 P0；其他两人按文件所有权矩阵接管关键文件 |
| API Key 失效 | 切换到另一个 Provider；用 MockAdapter 演示流程 |
| SSE 在演示环境断连 | 改用本地 Demo；预录视频备份 |
| 大 PR 冲突 | 先合并小 PR 释放冲突源；保留可工作的 main |
| Demo 视频翻车 | 先发文档版交付物；Day 14 重录 |

---

## 附录 C：协作工具推荐

| 工具 | 用途 |
|------|------|
| **GitHub** | 代码托管、PR Review |
| **GitHub Projects / Issues** | 任务跟踪 |
| **飞书 / Slack / 微信群** | 实时沟通 |
| **Notion / Lark Docs** | 共享文档（草稿） |
| **Postman / Insomnia 团队空间** | API 共享 |
| **Figma**（可选） | UI 设计稿 |

---

## 附录 D：文档清单（团队共同维护）

| 文档 | 路径 | 主负责人 | 协作者 |
|------|------|----------|--------|
| 产品设计文档 | `docs/product-design.md` | F | 全员 |
| 开发方案（本文档之前） | `docs/development-plan.md` | B1 | 全员 |
| **分工方案（本文档）** | `docs/team-division.md` | B1 | 全员 |
| 技术架构文档 | `docs/tech-architecture.md` | B2 | B1 |
| API 设计文档 | `docs/api-spec.md` | B1 | B2 |
| AI 协作日志 | `docs/ai-collaboration-log.md` | 全员 | — |
| Demo 视频脚本 | `docs/demo-script.md` | F | 全员 |
| 各模块 Spec | `docs/spec/*.spec.md` | 各模块 Owner | — |
