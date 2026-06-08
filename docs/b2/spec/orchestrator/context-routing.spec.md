# Orchestrator Context Routing Spec

> 状态：Backend hardening implemented + live E2E passed
> 最后更新：2026-06-08
> 范围：Orchestrator-routed group conversation 的追问识别、证据检索、bounded evidence pack 和继续/修复命令上下文注入。

## 1. 目标

Orchestrator 在多轮对话中应更像 OpenCode / Claude Code / Codex 这类 coding agent：最新用户消息是主指令，历史消息、run detail、workspace 文件、预览、验收和部署记录是按需检索的证据。

因此，下一轮用户问“生成了吗”“预览地址是什么”“验收通过了吗”“改了哪些文件”时，Orchestrator 不应重新规划任务，也不应把 planner 的 JSON 解析错误暴露给用户。它应直接读取最近运行和 workspace 证据，给出自然、准确、可核验的回答。

## 2. 路由分类

### 2.1 Evidence answer

命中状态或证据追问时，Orchestrator 在 planner 前直接回答，不创建子 Agent message，不重跑任务。

典型请求：

- `主题是赛博朋克风的网站生成了吗`
- `预览地址是什么`
- `部署了吗 / 发布了吗`
- `浏览器验收通过了吗`
- `改了哪些文件 / 文件在哪`

回答依据：

- 最近 Orchestrator run detail：task、attempt、artifact、evaluation、fulfillment event、final summary。
- Workspace tree：文件列表、大小、关键入口文件。
- Workspace preview session：port、entry path、status、URL。
- Workspace deployment records：kind、status、entry path、URL、download URL、health status。

### 2.2 Context action

命中继续、修复或修改命令时，Orchestrator 先检查 evidence。若证据显示没有缺失项，可以直接回答；若确实需要继续执行、修复或修改，则进入 planner / tool-loop / 子 Agent 调度，并必须携带上一轮有界证据包。

典型请求：

- `继续完成缺失的部署`
- `帮我修复按钮问题`
- `把网站主题改成蓝色`
- `补齐移动端适配`

子 Agent 收到的是“最新任务 + 相关历史证据 + 必要文件路径/片段”，不是完整聊天历史、完整 workspace 或 raw runtime transcript。

### 2.3 New task

无法归类为追问或继续/修复的任务请求，保持现有 task planner / legacy fallback / tool-loop 行为。

## 3. Evidence Pack

Evidence pack 是 Orchestrator 内部 system message，不是用户可见 ContentBlock。它只包含结构化事实和受限文件信息。

内容上限：

- 最近 run：默认 1 个完整 detail，最多保留少量 task / attempt / event 摘要。
- workspace tree：最多 50 个文件。
- 文件片段：只按需读取 `README.md`、用户点名文件、manifest / artifact 中的关键文件；单文件和总字节数都设上限，超限截断或跳过。

禁止进入 evidence pack 和用户可见回答：

- raw stderr、stack trace、CLI transcript。
- `call_`、workspace 绝对路径、auth 路径、provider debug prompt。
- `ReAct step`、`Observation:`、`Action:`、`Tools:`。

## 4. Planner Error Fallback

如果 planner 返回 invalid JSON 或其它 task plan 错误，而最新请求符合 evidence answer，则 Orchestrator 必须降级为 evidence answer，不能向用户输出 `invalid_task_plan`。

真正的新任务 planner 失败仍按现有 fallback / error 策略处理。

## 5. Summary Rules

Evidence answer 不声明无法证实的内容：

- 只有 run status、fulfillment、workspace 文件、preview / deployment / evaluation 证据支持时，才说“已生成 / 已部署 / 验收通过”。
- 缺少证据时说“我没有找到对应记录”，并列出已找到的最近文件或运行状态。
- 若发现 preview 运行但 deployment 不存在，应明确区分“预览可用”和“正式部署未完成”。

## 6. Verification

Backend targeted tests 应覆盖：

- `主题是赛博朋克风的网站生成了吗` 命中 evidence answer，不进入 planner。
- `预览地址是什么 / 浏览器验收通过了吗 / 改了哪些文件` 均从证据回答。
- `继续完成缺失的部署` 在已有部署证据时直接回答；缺失部署时进入调度，且 planner / 子 Agent message 包含 `Orchestrator evidence pack:`。
- planner invalid JSON + evidence follow-up 不暴露 `invalid_task_plan`。
- evidence answer / process block 均无 forbidden internal trace。

Live E2E scenario：

- `orchestrator_context_followup_repair`
- 先执行网站生成 / 预览 / 验收 / 部署任务。
- 连续追问：`主题是赛博朋克风的网站生成了吗`、`预览地址是什么`、`浏览器验收通过了吗`、`改了哪些文件`、`继续完成缺失的部署`。
- 验收所有追问不泄露 planner/debug/raw runtime；证据型追问不创建子 Agent message；回答能引用文件、preview URL、deployment URL 和 verify 状态。

2026-06-08 live E2E evidence：

```text
scenario: orchestrator_context_followup_repair
base_url: http://111.229.151.159:8000
conversation_id: 7488f39a-4eda-4f06-b21a-4540a35eb89a
user_message_id: 67698ae9-84aa-47ef-8898-d47c3c9e633d
agent_message_id: 75f4a83b-44f5-4b9d-9de1-a64e739dd055
run_id: 230826eb-7e99-4ae2-961a-31ffc6e3a84b
report: /tmp/agenthub_orchestrator_context_followup_report.json
sse: /tmp/agenthub_orchestrator_context_followup_sse.jsonl
browser_report: /tmp/agenthub_orchestrator_context_followup_browser.json
passed: true
preview_url: http://111.229.151.159:8082/index.html
static_release_url: http://111.229.151.159:8000/releases/Deo-L2-iNQbkHrJ7ZiktHJpfAsy02Sj6/index.html
context_followups_all_passed: true
```

本轮额外修复了 `GET /messages/{id}/stream` existing-session subscriber 持有
`SELECT ... FOR UPDATE` 行锁的问题：订阅已存在 stream session 时会先 rollback，再进入 SSE
订阅，避免 runner 在最终持久化 `messages.status="done"` 时被长期阻塞。
