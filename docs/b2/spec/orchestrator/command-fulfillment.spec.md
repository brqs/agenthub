# Orchestrator Command Fulfillment Spec

> 状态：Backend MVP implemented
> 最后更新：2026-06-08
> 范围：Orchestrator-routed group task 的显式命令履约跟踪、平台动作闭环和最终回复不误报。

## 1. 目标

Orchestrator 不能只把 planner 生成的 task graph 跑完就宣布完成。用户请求里显式出现的要求，例如“生成文档”“交由两个智能体并行开发”“审阅”“网页预览”“浏览器验收”“部署”“Diff”，必须被单独跟踪。

该机制是通用履约层，不是前端演示模板。赛博朋克网站 prompt 只作为回归样例；其它文档、数据、工作流、代码修改和部署任务也应按同一规则提取和检查显式要求。

## 2. Fulfillment Item

每个 item 写入 `OrchestratorRunContext.fulfillment_items`，并通过 run detail event 暴露审计证据，不新增数据库表。

状态：

- `pending`：已识别要求，但尚未确认完成。
- `satisfied`：已有 task、artifact、tool 或 evaluation 证据满足要求。
- `failed`：任务阶段已结束且要求未满足，或平台 tool 明确失败。
- `skipped`：后续可扩展；当前 MVP 不主动生成。

当前 deterministic extractor 覆盖：

| item id | 触发词示例 | 满足证据 |
|---|---|---|
| `document` | 文档、方案、document、planning.md | 成功 attempt 生成 `.md/.doc/.docx` |
| `code_artifacts` | 代码、产物、网站、网页、HTML/CSS/JS | 成功 attempt 创建或修改代码/前端文件 |
| `multi_agent` | 两个智能体、多个 Agent、并行开发、分工协作 | plan 或成功 attempts 至少两个非 Orchestrator Agent |
| `review` | 审阅、评审、review | 独立 review task 成功，review Agent 不等于被 review 实现 Agent |
| `preview` | 预览、端口、preview、port | `start_workspace_preview` 成功 |
| `browser_verify` | 浏览器、质量验收、按钮、交互、移动端 | `verify_web_preview` passed |
| `deployment` | 部署、发布、上线、deploy | `create_deployment` 返回 published / running |
| `diff` | Diff、差异、变更摘要 | diff artifact 或足够 workspace changed evidence |
| `source_package` | 源码、打包、下载、source、zip | `package_workspace_source` 成功 |

## 3. Run Events

Orchestrator 使用现有 memory/run detail event：

```json
{
  "event_type": "command_fulfillment_status",
  "agent_id": "orchestrator",
  "payload": {
    "stage": "planned | tasks_finished | tool_result",
    "items": [
      {"id": "deployment", "label": "部署/发布", "status": "satisfied"}
    ]
  }
}
```

事件是审计证据，不是新的用户可见 ContentBlock。普通聊天仍通过 `process` block 和 final text 展示整理后的公开过程。

## 4. Planning Rules

- 多智能体触发词包括“两个智能体”“多个智能体”“双智能体”“交由两个智能体”“并行开发”“并行执行”“分工协作”等。
- 用户明确要求多个智能体时，如果 planner 输出只包含一个执行 Agent，后端会在不改 task 文案的前提下，把 implementation tasks 重平衡到至少两个可用 Agent。
- `codex-helper` 可以作为复杂任务的架构/方案首选，但不能吞掉用户明确要求的 Claude / OpenCode 并行执行。
- review task 必须避开自审；如果 planner 把 review 分给被 review 的实现 Agent，后端会改派给其它可用 Agent。
- 如果独立 review Agent 全部失败或不可用，但被 review 的前置任务已经留下可审阅产物，Orchestrator 可以执行 coordinator-level deterministic review fallback，生成 `review.md` 并在 run detail 标记 `fallback="orchestrator_review"`；这仍不允许实现 Agent 自审。
- 这些规则同样适用于非前端任务，不依赖任何固定主题或固定文件模板。

## 5. Platform Action Rules

- 用户要求“预览/端口”时，Orchestrator 必须调用 `start_workspace_preview`。
- 用户要求“浏览器验收/按钮/移动端/交互”时，必须调用 `verify_web_preview`。
- 用户要求“部署/发布/上线”时，必须在 preview/verify 后调用 `create_deployment`；`web_preview` URL 不等于完成部署。
- deployment health failed 时沿用现有 reflection/repair/redeploy 闭环；无法部署时 fulfillment item 保持 `failed` 或 `pending`，final text 不能写“已部署”。
- Source zip 与 container deployment 仍由对应显式请求触发；普通“部署静态站点”不隐式要求源码 zip 或容器部署。

## 6. Final Response Rules

Response presentation 会读取 fulfillment 状态：

- 全部显式要求满足时，可以自然说明已完成。
- 任一显式要求 `pending/failed/skipped` 时，最终回复必须进入 partial / needs-attention 语气。
- Orchestrator 的最终可见 text 必须在 task execution、browser quality gate、preview/verify/deployment tool 全部结束后生成；不能先输出“尚未完成部署/验收”，再在同一条消息后半段展示成功的 preview/deployment block。
- 用户可见文案不得包含 raw stderr、stack trace、call id、planner/debug prompt、`ReAct step`、`Observation:`、`Action:`、`Tools:` 或长 tool output。

## 7. Current Verification

Backend targeted tests 覆盖：

- 中文“交由两个智能体并行开发”触发 task rebalance。
- planner 自审 review 改派给独立 Agent。
- “网站 + 预览/按钮/移动端 + 部署在端口8082”触发 `start_workspace_preview -> verify_web_preview -> create_deployment`，并记录 fulfillment event。
- pending deployment fulfillment 会让 final visible summary partial，不误报全量完成。
- live E2E registry 新增 `command_fulfillment_cyberpunk_group_deploy`，默认报告：
  - `/tmp/agenthub_command_fulfillment_report.json`
  - `/tmp/agenthub_command_fulfillment_sse.jsonl`
  - `/tmp/agenthub_command_fulfillment_browser.json`

2026-06-08 repair hardening 补充：

- `message_error.error` 也纳入 visible sanitizer / live E2E forbidden term 检查，避免前端直接渲染 raw Codex/OpenCode runtime transcript。
- sanitizer 覆盖 Codex/OpenCode CLI 原始输出中的 workspace path、`OpenAI Codex`、`workdir:`、`approval:`、`sandbox:`、`UnknownError`、`external_runtime_error` 等内部痕迹；run detail 仍保留审计证据。
- `command_fulfillment_cyberpunk_group_deploy` hard checks 新增：
  - `message_error_no_forbidden_terms`
  - `command_final_text_no_contradictory_completion`
  - `container_deployment_smoke_request_created`
- 容器化部署 smoke 使用同一个 workspace deployment API 发起 `kind="container"` 请求；生产默认关闭容器 worker 时应得到可解释的 `not_supported`，而不是前端按钮静默不可点击。

2026-06-08 公网 repair loop 通过：

- conversation：`9fd3cd30-6b65-45a4-8833-dcadffd78f64`
- report：`/tmp/agenthub_command_fulfillment_report.json`
- SSE：`/tmp/agenthub_command_fulfillment_sse.jsonl`
- browser：`/tmp/agenthub_command_fulfillment_browser.json`
- `passed=true`
- workspace：`planning.md`、`index.html`、`styles.css`、`app.js`、`diff.md`、`review.md`
- preview：`http://111.229.151.159:8082/index.html`
- static release：`http://111.229.151.159:8000/releases/j1k19e_7KaHDGrY-dF9s2blPdUIYVucC/index.html`
- `message_error_no_forbidden_terms=true`
- container smoke：HTTP `201`，status `not_supported`，符合生产默认关闭容器 worker 的安全策略。

2026-06-07 公网 E2E `command_fulfillment_cyberpunk_group_deploy` 已通过：

- conversation：`25ff9e75-7776-46b2-8549-babb78555177`
- report：`/tmp/agenthub_command_fulfillment_report.json`
- SSE：`/tmp/agenthub_command_fulfillment_sse.jsonl`
- browser：`/tmp/agenthub_command_fulfillment_browser.json`
- `passed=true`
- workspace：`planning.md`、`design-doc.md`、`index.html`、`styles.css`、`app.js`、`diff.md`、`review.md`
- preview：`http://111.229.151.159:8082/index.html`
- static release：`http://111.229.151.159:8000/releases/vw1Obog5VUQ1cY4lCNzBaevfgnDc1Epy/index.html`

公网 E2E evidence 详见 [live-e2e-report.spec.md](live-e2e-report.spec.md)。
