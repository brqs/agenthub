---
name: b2-ai-collaboration
description: Use when planning or reviewing AgentHub B2 Agent Runtime work with AI collaborators, including task dispatch to OpenCode/Claude Code, Codex review prompts, ownership boundaries, validation commands, and collaboration evidence updates.
---

# B2 AI Collaboration Skill

## When To Use

Use this skill when the user asks to:

- 拆解 B2 Agent Runtime / Orchestrator / adapter / preview 任务。
- 给 OpenCode、Claude Code 或 Codex 生成可执行任务指令。
- 做 B2 代码复审、边界检查或测试证据整理。
- 更新 B2 协作日志、任务证据或答辩材料。

## Role Split

- B2 owner：决定优先级、验收口径和最终取舍。
- Codex：总览、拆解、协调、边界检查、最终复审。
- OpenCode：按任务文档执行具体实现和测试。
- Claude Code：可执行代码任务；若作为 Git/PR 角色，只负责 status、commit、push 任务分支、创建 PR，不改业务代码，也不执行合并。

## Task Dispatch Template

给执行 Agent 的任务必须完整、可验证，至少包含：

```text
任务编号：
任务名称：
执行 AI：
复审 AI：

背景：

必须先读：
- AGENTS.md
- docs/b2/spec/README.md
- <相关 spec>
- <相关代码/测试>

允许修改：
- <path>

禁止修改：
- <path>

实现目标：

核心行为：
1.
2.
3.

测试要求：
1.
2.
3.

建议验证：
cd backend
uv run pytest <tests> -q
uv run ruff check <paths>
uv run mypy <paths>

交付要求：
- 不 commit / push / PR，除非明确指定。
- 如明确要求推送，必须创建 PR 并返回链接；不得直接 push 到 main，不得执行 merge 或 auto-merge。
- 汇报修改文件、核心思路、测试结果、未覆盖风险。
```

## Batch Dispatch Rules

并行开多个执行窗口时：

- 每个窗口只负责一个任务编号。
- 明确哪些任务可并行、哪些必须等待前置任务。
- 共享接线文件由后置任务统一处理。
- 同一共享契约变更必须指定唯一 owner。

## Codex Review Template

复审时先读：

1. `AGENTS.md`
2. `docs/b2/spec/README.md`
3. 当前任务相关 spec
4. 任务涉及的实现文件
5. 任务涉及的测试文件

重点检查：

- 是否违反目录 owner、任务边界或共享契约。
- 是否擅自修改 `BaseAgentAdapter`、`StreamChunk`、OpenAPI、frontend、registry、seed。
- Orchestrator 规划/prompt/调度改动是否遵守 [docs/b2/spec/orchestrator/clarification-gate.spec.md](../../b2/spec/orchestrator/clarification-gate.spec.md)：代码产物请求进入 planner/子 Agent 调度前，应先判断是否需要一问一答式需求澄清。
- `workspace_path`、`tool_specs`、`ToolSpec.parameters`、`call_id` 是否符合 contract。
- external runtime 的 timeout、process cleanup、SDK/subprocess error 是否映射为标准 error。
- tool_call/tool_result 是否保持 call_id 配对。
- 文件读写和命令执行是否受 workspace sandbox 约束。
- 测试是否使用 fake/mock；真实 runtime smoke 必须 opt-in。

复审输出格式：

```text
Findings:
- 按严重程度列问题，带文件路径和行号。无问题则写“未发现阻塞性问题”。

Open Questions:
- 只列阻塞性不确定点。无则写“无”。

Verdict:
- 通过 / 需修改。

Test Evidence:
- 列出实际运行命令和结果。
```

## Evidence Updates

B2 协作过程需要保留可评分证据：

- 当前契约：更新 `docs/b2/spec/*.spec.md`。
- 可复用流程：更新本 skill 或其他 `docs/ai-skills/*/SKILL.md`。
- 真实执行结果：写入 implementation report 或 live E2E report。
- 协作过程：追加 `docs/ai-collaboration-log.md`。
- 任务单只保留当前必要 spec / skill；过时历史任务单不再保留为 B2 当前入口。
