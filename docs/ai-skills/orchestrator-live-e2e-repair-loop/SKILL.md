---
name: orchestrator-live-e2e-repair-loop
description: Use when validating AgentHub Orchestrator real live E2E flows, 8082 preview/browser verification, DAG parallelism, workspace conflict detection, conversational custom agent creation, backend redeploy/seed checks, or any "test fails -> fix -> rerun until pass" loop.
---

# Orchestrator Live E2E Repair Loop Skill

> 类型：AI 协作 Skill / 测试修复闭环
> 适用范围：AgentHub Orchestrator、workspace artifact、preview/browser verify、B2 P0/P1 live E2E
> 最后更新：2026-06-01

---

## 1. 何时使用

当用户要求验证 Orchestrator 真实任务流转，或要求“失败就继续修、继续跑直到通过”时，使用本 Skill。

典型触发语句：

- “真实执行任务流转测试”
- “跑 live E2E”
- 进行E2E测试
- “测试不通过就继续修”
- “验证 8082 preview / browser verify”
- “验证 DAG 并行 / workspace conflict / create_custom_agent”
- “重新部署后端并 seed，再跑真实账号测试”

---

## 2. 核心目标

不是只跑一次测试，而是进入闭环：

```text
真实 E2E 失败
-> 保留现场
-> 分类失败层级
-> 定位代码或配置
-> 最小修复
-> 单测/回归测试
-> 重启后端 / seed
-> 重跑失败 case
-> 跑 preview/browser 回归
-> 全部通过后输出报告
```

除非遇到外部阻断项，例如云安全组未开放、第三方 Agent 服务不可用、账号失效，否则不把“失败”当作终点。

---

## 3. 环境事实

默认真实链路：

- 前端：`http://154.44.25.94:1573`
- 后端公网：`http://111.229.151.159:8000`
- Preview：`http://111.229.151.159:8082/index.html`
- 账号：`12345678 / 12345678`

默认群聊成员：

```text
orchestrator, claude-code, opencode-helper, codex-helper
```

后端部署提醒：

- 本阶段只部署后端，不部署前端。
- 每次 live E2E 前必须先执行“运行代码同步门禁”；不能直接复用修改代码前已经启动的旧后端进程。
- 当前后端部署在本机 `/home/ubuntu/agenthub/backend`。修改后端文件后，重启本机后端即可加载最新代码；如果以后后端迁移到其他服务器，必须先同步代码到目标服务器再重启。
- 新增或修改 Alembic migration 后必须先执行 `uv run alembic upgrade head`。
- 修改 seed 或 Orchestrator 默认配置后必须执行 `uv run python -m app.seeds.seed_agents`。
- 修改远端前端可见行为后，若验收目标包含浏览器 UI 展示，必须部署前端；只验证 API/SSE 数据时可以明确记录“前端未部署，本轮不验收远端 UI 渲染”。
- preview 端口由平台 preview service 管理，Agent runtime 不允许自行启动 `npm run dev`、`vite --host`、`python -m http.server` 等长驻服务。

---

## 4. Live E2E 前置门禁

每次首次执行 live E2E，以及每次修复代码后重跑失败 case 前，都必须先完成本节。不能因为上一次 E2E 跑通过就跳过。

### 4.1 判断变更范围

```bash
cd /home/ubuntu/agenthub
git status --short
git diff --name-only
git ls-files --others --exclude-standard
```

按文件范围执行同步动作：

| 变更范围 | E2E 前必须执行 |
|---|---|
| `backend/app/**`、`backend/scripts/**`、后端依赖或配置 | 相关测试后重启后端 |
| `backend/alembic/versions/**`、数据库模型 | `uv run alembic upgrade head`，再重启后端 |
| `seed_agents.py`、`ORCHESTRATOR_DEFAULTS`、内置 Agent config | 重启后端后重新执行 `uv run python -m app.seeds.seed_agents` |
| `frontend/**`、`shared/openapi.yaml` 且验收远端 UI | 重新构建并部署前端 |
| 仅 docs / tests | 不要求重启运行服务，但要明确记录 |

### 4.2 同步本机后端运行实例

当前后端运行在本机，所以“部署后端”等价于：确认旧进程、应用 migration、重启实际运行方式、按需 seed、检查本机与公网 health。

详细命令遵循：

```text
docs/ai-skills/backend-deploy/SKILL.md
```

至少保留：

- 重启前后端 PID。
- `alembic current` 输出。
- 是否执行 seed。
- 本机和公网 `/health` 响应。
- 对本轮关键能力的 API 断言，例如 `/api/v1/agents` 配置或 OpenAPI 新路由。

`/health` 返回正常只能证明服务存活，不能单独证明运行实例已经加载本轮代码。必须结合进程重启证据和关键 API 断言。

### 4.3 通过门禁后再运行 live E2E

顺序固定为：

```text
检查 diff
-> 相关单测
-> migration（如需要）
-> 重启后端
-> seed（如需要）
-> health + 关键 API 断言
-> live E2E
```

---

## 5. 标准 Case

### Case 0 - Config

验证 `/api/v1/agents` 中 Orchestrator config：

```json
{
  "llm_planning": true,
  "orchestrator_parallel_enabled": true,
  "orchestrator_parallel_max_concurrency": 3
}
```

失败优先检查：

- env 默认值。
- `ORCHESTRATOR_DEFAULTS`。
- `seed_agents` 是否覆盖数据库旧配置。

### Case 1 - 8082 Quality Gate

任务：

```text
@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、按钮交互和移动端适配的前端开发演示，主题使用“太空任务控制台”，部署在端口8082，并完成浏览器级质量验收
```

验收：

- workspace 有 `index.html`、`styles.css`、`app.js`。
- `start_workspace_preview` 是正式 tool 调用。
- `verify_web_preview` 是正式 tool 调用。
- `http://111.229.151.159:8082/index.html` 返回 200。
- 桌面/移动端截图存在且非空。
- 无 JS error、console error、同源资源 404。
- report `passed=true`。

失败定位顺序：

1. preview tool。
2. browser verifier。
3. workspace 产物。
4. SSE/tool result。
5. 8082 端口占用或公网访问。

### Case 2 - DAG Parallel

任务：

```text
@orchestrator 请使用并行 DAG 调度完成一个协作写作任务：让 claude-code 生成 workspace 文件 parallel-claude.md，内容为“信息架构方案”；让 opencode-helper 同时生成 workspace 文件 parallel-opencode.md，内容为“视觉交互方案”；这两个任务互不依赖。等两个文件都完成后，再让 codex-helper 汇总生成 review.md，说明两个方案如何组合。请在最终总结里说明哪些任务是并行执行的。
```

验收：

- workspace 有 `parallel-claude.md`、`parallel-opencode.md`、`review.md`。
- 两个独立任务没有被依赖关系互相阻塞。
- `review.md` 在两个前置产物后生成。
- summary 无 `artifact_missing` 或 pending 任务。

失败优先检查：

- DAG 任务依赖解析。
- ready queue。
- 并发上限。
- flush 输出顺序。
- task 状态流转。
- AsyncSession 并发写入。

### Case 3 - Workspace Conflict

任务：

```text
@orchestrator 请测试 workspace 冲突处理：先创建 shared-conflict.md，然后安排 claude-code 和 opencode-helper 在同一个 run 内分别修改 shared-conflict.md 的内容，claude-code 写入“设计视角”，opencode-helper 写入“实现视角”。不要要求它们手动合并，最后请在总结中明确列出是否检测到 workspace conflict、冲突文件路径、涉及 task 和涉及 agent。
```

验收：

- workspace 有 `shared-conflict.md`。
- memory event 或 summary 中出现冲突记录。
- summary 列出冲突文件、涉及 task、涉及 agent。
- 冲突不导致 run 崩溃。
- 本阶段不要求自动 merge。

失败优先检查：

- snapshot 采集。
- diff 计算。
- attempt file changes。
- conflict 去重。
- summary 暴露。
- memory event 记录。

### Case 4 - Conversational Custom Agent

任务：

```text
@orchestrator 请创建一个新的自建 Agent，名字为 LiveCopywriter-{timestamp}，provider 使用 builtin，system_prompt 为“你是一个中文产品文案 Agent，只输出简短、清晰、有行动感的产品文案”，capabilities 设置为 copywriting、review，并把它加入当前群聊。创建完成后，请让它为“太空任务控制台”写一句中文 slogan。
```

验收：

- SSE 或最终消息中出现 `create_custom_agent` 正式 tool 调用。
- `/api/v1/agents` 能查到 `LiveCopywriter-{timestamp}`。
- 当前 conversation 的 `agent_ids` 包含新 Agent id。
- tool result 返回 id、name、provider、capabilities。
- 新 Agent 能被 Orchestrator 后续调度，或至少出现在群聊成员里。

失败优先检查：

- tool spec。
- tool loop 路由。
- platform executor。
- agent config validation。
- conversation membership 写入。

---

## 6. 失败现场必须保留

每次失败都保留：

- conversation id。
- user message id。
- agent message id。
- SSE jsonl。
- report json。
- browser report。
- 后端日志片段。
- workspace tree 快照。
- 入口 HTML 路径与 preview URL。

标准输出路径：

- `/tmp/agenthub_orchestrator_quality_report.json`
- `/tmp/agenthub_orchestrator_quality_sse.jsonl`
- `/tmp/agenthub_orchestrator_quality_browser.json`
- `/tmp/agenthub_b2_p0_live_report.json`

旧 8082 smoke 输出路径：

- `/tmp/agenthub_orchestrator_8082_sse.jsonl`
- `/tmp/agenthub_orchestrator_8082_report.json`

---

## 7. 失败分类

按以下层级定位：

1. 配置 / seed。
2. API。
3. SSE。
4. Orchestrator planner。
5. tool loop。
6. workspace artifact。
7. preview service。
8. browser verifier。
9. Agent runtime。
10. 外部基础设施。

外部阻断才停止闭环，例如：

- 公网 8082 被云安全组拒绝。
- 第三方 Agent 服务不可达。
- 账号登录失败。
- 服务器权限不足，无法重启后端。

---

## 8. 修复规则

- 优先最小改动，不重构无关模块。
- 修复后补或更新自动化测试。
- 修复后重跑 live E2E 前，重新执行“运行代码同步门禁”。
- 修改 seed 或 Orchestrator 默认配置后必须重新 seed。
- 修改后端代码后必须重启本机后端。
- 新增或修改 migration 后必须执行 `uv run alembic upgrade head`。
- 先重跑失败 case，再跑 Case 1 preview/browser 回归。
- 所有 case 通过后再跑全量测试、ruff、mypy。

后端部署入口：

```bash
sed -n '1,240p' /home/ubuntu/agenthub/docs/ai-skills/backend-deploy/SKILL.md
```

不要在本 Skill 维护另一套简化重启命令，避免遗漏旧进程停止、migration 或条件式 seed。

---

## 9. 结果沉淀位置

这类计划不应全部堆进单个 spec。建议分层沉淀：

| 内容 | 推荐位置 |
|---|---|
| 通用失败修复闭环 | 本 Skill |
| 当前能力契约 | `docs/b2/spec/orchestrator/core.spec.md`、`orchestrator/tool-calling.spec.md`、`workspace-artifact-preview.spec.md` |
| Orchestrator 真实结果 | `docs/b2/spec/orchestrator/live-e2e-report.spec.md` |
| 后续缺口 | `docs/b2/spec/b2-pdf-gap-todo.spec.md` |
| 可重复执行脚本说明 | `backend/scripts/orchestrator_live_e2e.py` 和相关 report 文档 |
| AI 协作过程证据 | `docs/ai-collaboration-log.md` |
