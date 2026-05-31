# Workspace Conflict Detection Spec

> 状态：Current contract
> 最后更新：2026-05-31

---

## 1. 目标

Workspace conflict detection 用于解决多 Agent 在同一个 Orchestrator run 内共同修改 workspace 时的可追踪性问题。

当前版本只负责：

1. 记录 task attempt 前后的 workspace snapshot。
2. 计算每个 attempt 的 `created`、`modified`、`deleted`。
3. 检测同一 run 内多个 task 修改同一路径。
4. 在 summary 和 structured memory event 中展示冲突。

当前版本不负责：

- 自动 merge。
- 文件级 lock。
- rollback。
- patch review。
- 冲突后的自动修复派工。

这些能力属于后续 Agent-to-Agent review / merge workflow。

---

## 2. Snapshot

每个 task attempt 开始前和结束后采集 workspace snapshot。

snapshot item 包含：

- workspace-relative `path`
- `size`
- `mtime`
- `sha256`

忽略路径：

- `.agenthub/`
- `.git/`
- `node_modules/`
- `.venv/`
- `__pycache__/`
- runtime 临时输出目录

实现入口：

- `backend/app/agents/orchestrator/workspace_changes.py`
- `backend/app/agents/orchestrator/execution.py`

---

## 3. File Changes

attempt 结束后基于 before / after snapshot 计算：

```json
{
  "created": ["new-file.md"],
  "modified": ["shared.md"],
  "deleted": ["old-file.md"]
}
```

归因规则：

- 如果 task 有明确 artifact paths，则优先只把这些路径归因到该 task。
- 这样可以避免并行 batch 中一个 task 的 after snapshot 看见另一个 task 创建的文件，从而误报 file change / conflict。
- 没有明确 artifact paths 时，使用完整 snapshot diff。

---

## 4. Conflict Detection

同一 Orchestrator run 内，如果多个 task 的 file changes 命中同一 path，则记录 conflict。

conflict payload 至少包含：

- `path`
- 涉及 task id
- 涉及 agent id
- 涉及 change type

summary 展示格式：

```text
Workspace conflicts

- shared-conflict.md
  tasks: conflict-design, conflict-implementation
  agents: claude-code, opencode-helper
```

structured memory event：

- `workspace_snapshot`
- `workspace_file_changes`
- `workspace_conflict_detected`

---

## 5. Orchestrator 集成

Orchestrator 执行层在每个 `_run_task()` attempt 前后记录 snapshot，并在 run 结束前刷新 conflict。

相关契约：

- [core.spec.md](core.spec.md)：任务执行流、summary、验收标准。
- [memory-context.spec.md](memory-context.spec.md)：memory event 持久化。
- [live-e2e-report.spec.md](live-e2e-report.spec.md)：真实 E2E Case 3 验收结果。

主要代码：

- `backend/app/agents/orchestrator/workspace_changes.py`
- `backend/app/agents/orchestrator/execution.py`
- `backend/app/agents/orchestrator/summary.py`
- `backend/app/agents/orchestrator/memory_hooks.py`
- `backend/app/services/orchestrator_memory.py`

---

## 6. 验收标准

- 两个 task 修改同一文件时，summary 必须展示 conflict。
- conflict 记录必须包含文件路径、涉及 task、涉及 agent。
- conflict 不应让 run 崩溃。
- 并行 batch 中其他 task 创建的明确 artifact 不应被误归因。
- memory event 中能追踪 snapshot、file changes 和 conflict。
