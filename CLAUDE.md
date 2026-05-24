# AgentHub — AI 协作指南（CLAUDE.md）

> **本文件是项目的"AI 协作宪法"**。
> 所有 AI 助手（Claude Code / Cursor / Codex 等）在本仓库工作时，都应首先阅读此文件并严格遵守其中的约定。
> 团队成员对应规则的更新会在每日同步中通知所有人。

---

## 0. 阅读优先级

打开本仓库时，按以下顺序读取上下文：

1. **本文件**（`CLAUDE.md`）—— 项目宪法
2. **当前正在改动的目录**下的 `CLAUDE.md`（如果存在，覆盖部分全局规则）
3. **相关 Spec 文档**：`docs/spec/<module>.spec.md`
4. **API 契约**：`shared/openapi.yaml`
5. **架构文档**（按需）：`docs/tech-architecture.md`、`docs/api-spec.md`

---

## 1. 项目速览（30 秒读完）

**AgentHub** 是一个 IM 聊天式的多 Agent 协作平台。用户通过类似微信/飞书的对话界面，与多个 AI Agent（Claude / Codex / 自建）进行 1v1 单聊或群聊，由主 Agent（Orchestrator）协调任务分派，Agent 回复以富媒体卡片（代码块、Diff、网页预览）形式内联展示。

- **比赛项目**，3 人团队，14 天交付
- **核心交互**：IM 范式 + SSE 流式响应 + 多 Agent 编排
- **技术栈**：React + Vite（前端）、FastAPI + PostgreSQL（后端）、Claude/OpenAI SDK
- **架构核心**：Adapter 模式屏蔽 Provider 差异 + OpenAPI 契约驱动前后端

详细背景见 [docs/development-plan.md](docs/development-plan.md) 和 [docs/product-design.md](docs/product-design.md)。

---

## 2. 团队与目录所有权

```
团队（3 人）：
  F  → 前端开发        → frontend/**
  B1 → 后端核心平台    → backend/app/{core,models,services,api}/**
  B2 → Agent 集成      → backend/app/agents/**

共享文件（改前需通知所有人）：
  shared/openapi.yaml         (API 契约 ★ 最关键)
  backend/app/schemas/**      (Pydantic 模型)
  docker-compose.yml
  CLAUDE.md / docs/**
```

**铁律**：
- AI 在生成代码前，先确认当前文件归属哪个人/模块
- **不要跨边界改动**（例：B1 改 `agents/`、F 改 `backend/`）
- 跨边界改动时必须在 PR 描述中说明并 @ 对应 owner

完整所有权矩阵见 [docs/team-division.md § 2.3](docs/team-division.md)。

---

## 3. 技术栈速查

### 3.1 后端（Python 3.11）

```
FastAPI + Uvicorn       (Web 框架，async 原生)
SQLAlchemy 2.0 + Alembic (ORM + migration，async)
Pydantic v2             (数据校验)
asyncpg                 (PostgreSQL 异步驱动)
redis-py (asyncio)      (Redis 异步客户端)
python-jose             (JWT)
passlib[bcrypt]         (密码哈希)
sse-starlette           (SSE)
anthropic / openai      (LLM SDK)
pytest + pytest-asyncio (测试)
ruff + mypy             (lint + 类型检查)
```

**Python 风格**：
- 全栈 `async/await`，I/O 不允许同步阻塞
- 公开函数必须有完整 type hints
- 用 `from __future__ import annotations` + Python 3.11 联合类型语法（`X | Y` 而非 `Union[X, Y]`）
- 导入顺序：标准库 / 第三方 / 本地（ruff 自动排序）

### 3.2 前端（TypeScript 5+ / React 18）

```
React 18 + Vite + TypeScript
React Router v6
Tailwind CSS + shadcn/ui
Zustand                (UI 状态)
TanStack Query         (服务端数据缓存)
@microsoft/fetch-event-source (SSE，支持自定义 Header)
react-markdown + shiki (Markdown + 代码高亮)
react-diff-viewer-continued (Diff)
vitest + @testing-library
eslint + prettier
```

**TypeScript 风格**：
- 严禁 `any`，必要时用 `unknown` + 类型守卫
- API 相关类型一律从 `src/lib/types.ts`（由 OpenAPI 生成）导入，**不要手写重复**
- 组件用函数式 + Hooks，不用 class
- 文件命名：组件 `PascalCase.tsx`，hook/util `camelCase.ts`

---

## 4. 三大核心契约（绝对不能违反）

### 4.1 契约 1：OpenAPI Spec（前后端共享）

📍 `shared/openapi.yaml` —— **唯一真相源**

```
任何 API 变更必须遵循以下流程：
1. 先改 shared/openapi.yaml
2. 在 PR 描述中标注「契约变更」
3. F 运行 pnpm gen:types 重新生成 src/lib/types.ts
4. B1/B2 的 Pydantic Schema 与 OpenAPI 保持对齐
5. 合并后所有人 git pull 并重新生成类型
```

**AI 必须**：
- ✅ 改 API 前先读 `shared/openapi.yaml`
- ✅ 改完后同步更新 OpenAPI
- ❌ 不允许前端硬编码 API 路径字符串
- ❌ 不允许后端跳过 Pydantic 直接返回字典

### 4.2 契约 2：BaseAgentAdapter（B1 ↔ B2 解耦点）

📍 `backend/app/agents/base.py` —— B1 不感知具体 Provider 的唯一通道

```python
class BaseAgentAdapter(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        config: dict | None = None,
    ) -> AsyncIterator[StreamChunk]: ...
```

**AI 必须**：
- ✅ B1 代码通过 `agents.registry.get_adapter(agent_id)` 拿 Adapter，不直接 import 具体类
- ✅ B2 新增 Provider 时继承 `BaseAgentAdapter`，**不能改基类签名**
- ❌ B1 严禁直接 `import anthropic` / `import openai`
- ❌ B2 严禁在 Adapter 中访问数据库（如需配置由 Service 层注入）

### 4.3 契约 3：ContentBlock 联合类型（消息富媒体）

📍 `backend/app/schemas/message.py` + `frontend/src/lib/types.ts`

```python
ContentBlock = TextBlock | CodeBlock | DiffBlock | WebPreviewBlock | FileBlock
# 用 discriminator="type" 区分
```

**AI 必须**：
- ✅ 新增 Block 类型：先改 schemas → 同步 OpenAPI → F 加渲染组件
- ✅ 前端用 `BLOCK_COMPONENTS[block.type]` 字典分发渲染
- ❌ 严禁在某一处加新类型而不更新另两处

---

## 5. 项目目录约定

```
agenthub/
├── CLAUDE.md                         ← 本文件
├── docs/                             ← 全部文档（开发计划、架构、API、产品、Spec）
│   └── spec/                         ← 各模块 Spec（用于 AI 协作时喂上下文）
├── shared/
│   └── openapi.yaml                  ← API 契约 ★
├── .claude/
│   ├── skills/                       ← 项目专属 Skill
│   └── rules/                        ← 编码规则
├── backend/
│   └── app/
│       ├── core/        【B1】配置、DB、JWT、依赖注入
│       ├── models/      【B1】SQLAlchemy 模型
│       ├── schemas/     【共享】Pydantic Schema（B1+B2 协同）
│       ├── api/v1/      【B1】路由（除 agents.py 由 B2 主导）
│       ├── services/    【B1】业务逻辑
│       └── agents/      【B2】Adapter、Orchestrator、产物解析
└── frontend/
    └── src/
        ├── lib/         【F】API 客户端、类型、工具
        ├── stores/      【F】Zustand
        ├── hooks/       【F】业务 Hook
        ├── pages/       【F】页面
        └── components/  【F】组件
            ├── blocks/  ★ 富媒体消息块（每种 ContentBlock 一个组件）
            ├── chat/    聊天界面
            └── ...
```

**新建文件前**：先看上面的目录约定，把文件放对位置。

---

## 6. 编码规范

### 6.1 通用

- **小函数**：单个函数 ≤ 50 行，单文件 ≤ 500 行
- **早返回**：减少嵌套
- **明确命名**：变量名能自解释，不写注释解释 *做什么*；只在 *为什么* 不明显时写注释
- **不写过度防御代码**：内部信任，只在系统边界（用户输入、外部 API）校验
- **不要为"未来可能用到"加抽象**：YAGNI

### 6.2 后端（Python）

```python
# ✅ 好
async def get_conversation(db: AsyncSession, user: User, conv_id: UUID) -> Conversation:
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    if conv.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    return conv

# ❌ 不好（同步调用、缺类型、过度防御）
def get_conversation(db, user, conv_id):
    try:
        conv = db.query(Conversation).filter(...).first()
        if conv is None:
            return None
        if conv.user_id != user.id:
            return None
        return conv
    except Exception as e:
        logging.error(e)
        return None
```

### 6.3 前端（TypeScript / React）

```typescript
// ✅ 好
export function MessageBubble({ message }: { message: Message }) {
  return (
    <div className="rounded-md bg-secondary p-4">
      {message.content.map((block, i) => (
        <ContentRenderer key={i} block={block} />
      ))}
    </div>
  );
}

// ❌ 不好（用 any、内联类型、缺 key）
export function MessageBubble(props: any) {
  return (
    <div>
      {props.message.content.map((block: any) => <div>{block.text}</div>)}
    </div>
  );
}
```

### 6.4 测试

- **后端**：用 `pytest-asyncio`，集成测试用 `httpx.AsyncClient`
- **前端**：关键 Hook 和组件用 `vitest` + `@testing-library`
- **不必追求 100% 覆盖**，覆盖核心路径即可

---

## 7. 常见任务模板

> 复用这些 Prompt 与 AI 协作时能省 50% 沟通成本。

### 7.1 添加新 API 端点

```
任务：添加 <端点描述> 端点。

要求：
1. 先在 shared/openapi.yaml 中定义此端点（path、method、params、request body、responses）
2. 在 backend/app/schemas/<resource>.py 中定义 Pydantic Schema
3. 在 backend/app/services/<resource>_service.py 中实现业务逻辑
4. 在 backend/app/api/v1/<resource>.py 中实现路由层
5. 添加单元测试到 backend/tests/test_<resource>.py
6. 验证：
   - mypy 通过
   - pytest 通过
   - /docs Swagger UI 中可见
   - curl 测试通过
```

### 7.2 添加新 Agent Adapter

```
任务：添加 <Provider> 的 Adapter。

参考：
- 接口定义：backend/app/agents/base.py
- 已有示例：backend/app/agents/adapters/claude.py

要求：
1. 在 backend/app/agents/adapters/ 下创建 <provider>.py
2. 继承 BaseAgentAdapter，实现 _create_client 和 stream
3. 把 LLM 原生流事件转换为标准 StreamChunk
4. 在 backend/app/agents/registry.py 的 PROVIDER_MAP 中注册
5. 添加单元测试（用 Mock 上游响应）
6. 在 alembic/seeds/seed_agents.py 中添加 Seed 数据（可选）
7. 验证：
   - 单元测试通过
   - 端到端：通过 SSE 端点能拿到流式响应
```

### 7.3 添加新 ContentBlock 类型

```
任务：添加 <BlockType>（如 ChartBlock）。

要求：
1. 在 backend/app/schemas/message.py 中添加新 Block 类（继承 BaseModel）
2. 把它加入 ContentBlock 联合类型
3. 在 shared/openapi.yaml 的 components.schemas 中添加同名定义
4. 在 frontend/src/lib/types.ts 中重新生成类型（pnpm gen:types）
5. 在 frontend/src/components/blocks/ 下创建 <BlockType>.tsx 组件
6. 在 BLOCK_COMPONENTS 字典中注册
7. 验证：
   - 后端能序列化新 Block
   - 前端能正确渲染
```

### 7.4 添加新 React 页面

```
任务：添加 <PageName>。

要求：
1. 在 frontend/src/pages/ 下创建 <PageName>.tsx
2. 在 frontend/src/router.tsx 中注册路由
3. 如需新 API 调用：在 frontend/src/hooks/ 下加 use<Resource>.ts
4. 用 TanStack Query 管理服务端数据，Zustand 管 UI 状态
5. 用 shadcn/ui 组件，禁止重新发明轮子
6. 验证：
   - 路由可访问
   - 无 console.error
   - 移动端响应式
```

### 7.5 修复 Bug

```
任务：修复 Bug <描述>。

要求：
1. 先理解根因，而非贴补丁
2. 加测试复现 Bug
3. 修复
4. 测试通过
5. 思考：这类 Bug 还有其他地方会出现吗？

不允许：
- 用 try/except 吞掉异常
- 不写测试就关闭 Issue
- 修复一处但放过相同模式的其他位置
```

---

## 8. 反模式（绝对不要做）

### ❌ 不要

1. **不要绕过 BaseAgentAdapter 直接调 Anthropic SDK**
   - 正确：B1 → registry.get_adapter() → Adapter → SDK
   - 错误：B1 直接 `from anthropic import ...`

2. **不要在前端硬编码 API 路径字符串**
   - 正确：从生成的 types 或 API 客户端调用
   - 错误：`fetch('/api/v1/conversations')` 散落各处

3. **不要写不带类型注解的 Python 函数**

4. **不要用 `any` 逃避 TypeScript 类型检查**

5. **不要在 service 层之外直接操作数据库**（路由层只调 service）

6. **不要在 Adapter 层访问数据库**（需要的配置由调用方传入）

7. **不要在没有 Spec 的情况下开始写新模块**
   - 先在 `docs/spec/<module>.spec.md` 写 Spec → 喂给 AI → 再写代码

8. **不要在 main 分支直接 commit**（必须走 PR）

9. **不要 commit 含 API Key / 密码的代码**（用 `.env`）

10. **不要为了 commit 通过而 `--no-verify`**（修复 hook 报错，不绕过）

11. **不要写没有人会读的 long comment**（除非说明非显然的 *为什么*）

12. **不要在生产代码中留 `console.log` / `print`**（用 logger）

---

## 9. AI 协作沉淀（30% 评分核心）

### 9.1 每次重要任务后要做的事

在 `docs/ai-collaboration-log.md` 追加记录：

```markdown
## YYYY-MM-DD — <谁> 实现 <什么>

### 任务
<一句话描述>

### 关键 Prompt
> <粘贴你给 AI 的核心提示>

### AI 输出摘要
<几行总结>

### 人工调整
<列出关键修改>

### 经验
<这次学到的，下次可以复用的>
```

### 9.2 模块 Spec 沉淀

每开始一个新模块前，先在 `docs/spec/<module>.spec.md` 中写：

```markdown
# <module> Spec

## 目标
## 输入 / 输出
## 边界 / 错误处理
## 性能要求
## 依赖
## 验收标准
```

Spec 越具体，AI 生成的代码越精准。

### 9.3 Skill 和 Rules

- **Skill**（`.claude/skills/<name>.md`）：可重用的复杂任务模板
- **Rules**（`.claude/rules/<name>.md`）：项目专属编码规则（细则）

每发现一个值得复用的 Prompt 模式，就沉淀为 Skill 或 Rules。

---

## 10. Git 工作流

### 10.1 分支命名

```
feat/<owner>-<feature>      新功能
fix/<owner>-<bug>           修复
docs/<owner>-<topic>        文档
refactor/<owner>-<area>     重构
chore/<owner>-<task>        构建/工具
```

例：`feat/B1-sse-endpoint`、`feat/F-message-bubble`

### 10.2 Commit 规范（Conventional Commits）

```
<type>(<scope>): <subject>

[body]
```

例：
```
feat(B1/api): add SSE stream endpoint for messages

- Integrate with BaseAgentAdapter
- Persist accumulated content to DB on stream end
```

### 10.3 PR 必检项

- [ ] 不引入新的目录边界违规
- [ ] OpenAPI 变更已同步
- [ ] 类型检查通过（mypy / tsc）
- [ ] 测试通过
- [ ] 至少 1 人 Review
- [ ] 本地 `docker compose up` 端到端验证

---

## 11. 性能与安全红线

### 11.1 性能

- **API 非 SSE 端点 P95 < 200ms**
- **SSE 首字节 < 2s**（受上游 LLM 限制）
- **DB 查询必须走索引**（执行计划 Seq Scan = 报警）
- **不要在循环里发 DB 查询**（用 `selectinload` / batch）

### 11.2 安全

- ✅ 所有受保护端点都用 `Depends(get_current_user)`
- ✅ 所有 SQL 都通过 SQLAlchemy 参数化（无字符串拼接）
- ✅ 用户输入不直接拼到 System Prompt
- ✅ `.env` 在 `.gitignore`
- ❌ 不在日志输出密码 / JWT / API Key
- ❌ 不在前端引用 LLM Provider API Key

---

## 12. 快速命令速查

### 后端

```bash
# 启动开发环境
docker compose up -d

# 数据库迁移
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "msg"

# 运行测试
cd backend && uv run pytest

# 类型检查 + Lint
cd backend && uv run ruff check && uv run mypy app
```

### 前端

```bash
# 启动
cd frontend && pnpm dev

# 生成 API 类型（每次 openapi.yaml 变更后必跑）
cd frontend && pnpm gen:types

# 类型检查 + Lint
cd frontend && pnpm tsc --noEmit && pnpm lint

# 测试
cd frontend && pnpm test
```

### 工具

```bash
# 查看后端 API 文档
open http://localhost:8000/docs

# 查看前端
open http://localhost:5173
```

---

## 13. 紧急联系与升级路径

如 AI 在以下情况无法独立判断，必须停下并向人类求助：

1. **跨边界改动**（涉及非自己负责的模块）
2. **契约变更**（修改 OpenAPI / BaseAgentAdapter / ContentBlock）
3. **需要 destructive 操作**（删表、删分支、`git reset --hard`）
4. **涉及 API Key / 密钥**
5. **不确定的产品决策**（"应该这样还是那样"）

> 求助方式：在生成代码前明确询问。**宁可多问，不要错改。**

---

## 14. 参考文档索引

| 文档 | 何时读 |
|------|--------|
| [docs/development-plan.md](docs/development-plan.md) | 想全面了解项目 |
| [docs/team-division.md](docs/team-division.md) | 想知道谁负责什么 |
| [docs/tech-architecture.md](docs/tech-architecture.md) | 写代码前看相关章节 |
| [docs/api-spec.md](docs/api-spec.md) | 调 API 或加 API |
| [docs/product-design.md](docs/product-design.md) | 做 UI / 交互 |
| `docs/spec/<module>.spec.md` | 开始具体模块前 |
| `shared/openapi.yaml` | 写任何前后端代码前 |

---

## 15. 元规则（关于本文件）

- 本文件 ≤ 500 行（当前未超），保证每次 AI 读取都加载得动
- 详细内容放到 `docs/` 下并在此引用，不要复制粘贴
- 任何团队成员发现遗漏或冲突，立即提 PR 更新
- 每个 Sprint 结束 Review 一次本文件，删除过时内容
- 更新本文件等同于"立法"，需要团队 3 人一致同意

---

**版本**：v1.0
**最后更新**：2026-05-22
**维护者**：AgentHub 团队
