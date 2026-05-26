# B2-14 Agent Runtime Pivot 文档与任务重基线

任务编号：B2-14
任务名称：Agent Runtime Pivot 文档与任务重基线
负责人：B2
执行 AI：OpenCode
复审 AI：Codex
Git/PR AI：Claude Code（仅 commit / push / PR，不改代码）
依赖任务：B2-01 至 B2-13，ADR-001

## 任务目标

把 B2 后续开发从 “raw LLM Provider Adapter” 重基线为 “真实 Agent Runtime 接入 + 自建 Agent Framework”。

本任务只做文档和任务分发基线，不实现 runtime 代码。完成后，B2-15 至 B2-20 可以分别交给新的 OpenCode 对话窗口执行。

必须明确：

- 产品 runtime 范围包含 `Claude Code`、`Codex`、`OpenCode`，三者都是 Must。
- OpenCode 不再按旧 ADR 中的候选项处理。
- 开发协作角色固定为：OpenCode 主要开发，Codex 复审，Claude Code 只负责 Git/PR 操作。
- 旧 B2-01 至 B2-13 保留为历史记录，其 raw LLM adapter 工作会在后续降级为 ModelGateway 底座。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/spec/agent-runtime-pivot.adr.md`
3. `docs/b2/spec/agent-runtime-adapter.spec.md`
4. `docs/b2/spec/builtin-agent-framework.spec.md`
5. `docs/b1/spec/workspace-sandbox.spec.md`
6. `docs/b2/task-dispatch/README.md`
7. `docs/b2/task-dispatch/B2-roadmap.md`

## 允许修改

- `docs/b2/task-dispatch/README.md`
- `docs/b2/task-dispatch/B2-roadmap.md`
- `docs/b2/task-dispatch/B2-14-agent-runtime-rebaseline.md`
- `docs/b2/task-dispatch/B2-15-model-gateway-split.md`
- `docs/b2/task-dispatch/B2-16-claude-code-external-adapter.md`
- `docs/b2/task-dispatch/B2-17-codex-external-adapter.md`
- `docs/b2/task-dispatch/B2-18-opencode-external-adapter.md`
- `docs/b2/task-dispatch/B2-19-builtin-agent-mvp.md`
- `docs/b2/task-dispatch/B2-20-real-agent-demo-smoke.md`
- `docs/spec/agent-runtime-pivot.adr.md`
- `docs/b2/spec/agent-runtime-adapter.spec.md`
- `docs/b2/spec/builtin-agent-framework.spec.md`
- `AGENTS.md` / `CLAUDE.md`（仅同步 OpenCode runtime 口径）
- `docs/ai-collaboration-log.md`

## 禁止修改

- `backend/app/**`
- `frontend/**`
- `shared/openapi.yaml`
- `backend/pyproject.toml`
- `.env`
- `backend/.env`
- `docker-compose.yml`

本任务不允许修改 `BaseAgentAdapter.stream()` 签名、`StreamChunk` schema、`ContentBlock` schema 或 OpenAPI。

## 实现要求

### 1. 更新协作角色口径

`docs/b2/task-dispatch/README.md` 必须写清：

- Codex 负责总览、拆解、边界检查和最终代码审阅。
- OpenCode 负责按任务文档执行具体实现和测试。
- Claude Code 仅在 Codex 复审通过后做 Git 状态整理、commit、push 和 PR 准备。
- B2 负责人每个子任务新开一个 OpenCode 对话窗口执行。

旧任务文档 B2-01 至 B2-13 不需要逐个重写，但 README 要标记它们为 pivot 前历史任务。

### 2. 新增 B2-14 至 B2-20 任务索引

README 与 roadmap 必须同时列出新任务：

- B2-14 文档与规格重基线
- B2-15 ModelGateway 拆分
- B2-16 Claude Code ExternalAdapter
- B2-17 Codex ExternalAdapter
- B2-18 OpenCode ExternalAdapter
- B2-19 BuiltinAgent MVP
- B2-20 真实 Agent demo smoke 与 registry 接线

默认状态写为 “待执行”，不要标记已完成。

### 3. 修正 ADR/spec 中的 OpenCode 优先级

`docs/spec/agent-runtime-pivot.adr.md` 中：

- Layer A 必须包含 `OpenCodeAdapter`。
- `Must` runtime 必须包含 Claude Code、Codex、OpenCode。
- 删除或改写 OpenCode 仍是候选项、暂不实现、或不阻塞答辩的旧表述。

### 4. 修正 ToolSpec 文档字段

当前代码中的 `ToolSpec` 字段是：

```python
name: str
description: str | None = None
parameters: dict[str, Any] = Field(default_factory=dict)
```

因此 `agent-runtime-adapter.spec.md` 和 `builtin-agent-framework.spec.md` 里不能继续使用旧字段名。任务文档也必须使用 `parameters`。

### 5. 保留代码契约边界

本任务只同步文档。不要为了让文档“更完整”而改：

- `BaseAgentAdapter`
- `StreamChunk`
- `ToolSpec`
- `ContentBlock`
- OpenAPI
- registry
- seed

这些由后续任务分别处理。

## 验证要求

在仓库根目录运行：

```bash
rg -n "Claude Code 执行|Sprint 6 候选|不实现 OpenCode|parameters_schema" docs/spec docs/b2/spec AGENTS.md CLAUDE.md docs/b2/task-dispatch/README.md docs/b2/task-dispatch/B2-roadmap.md
rg -n "执行 AI：OpenCode|复审 AI：Codex|Git/PR AI：Claude Code" docs/b2/task-dispatch
git diff -- docs/b2/task-dispatch docs/spec docs/b2/spec AGENTS.md CLAUDE.md docs/ai-collaboration-log.md
```

第一个命令不应在新任务文档或已同步 spec 中出现旧口径；旧 B2-01 至 B2-13 历史文档可保留旧执行 AI 文案。

## 交付说明

完成后交付说明必须包含：

1. 新增了哪些 B2-14 至 B2-20 任务文档。
2. README / roadmap 如何标记 pivot 前历史任务与 pivot 后待执行任务。
3. ADR/spec 中 OpenCode 和 ToolSpec 口径同步结果。
4. 执行过的验证命令及结果。

不要 commit，不要 push，不要创建 PR。完成后把 diff 和验证结果交给 Codex 复审。
