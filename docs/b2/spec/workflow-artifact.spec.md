# Workflow Artifact Spec

> Owner: B2
> Status: Current contract / Runtime dry-run MVP
> Related: [artifact-parser-v2.spec.md](artifact-parser-v2.spec.md), [orchestrator/evaluation-reflection.spec.md](orchestrator/evaluation-reflection.spec.md)

## 1. 目标

Workflow 作为正式聊天产物进入 ContentBlock / SSE / 前端预览链路，而不是只作为 `workflow_validation` evaluator 的隐式 JSON/YAML 文件。

MVP 覆盖：

- `workflow` ContentBlock schema。
- Streaming parser 识别 `workflow` / `workflow-json` / `workflow-yaml` fenced block。
- SSE accumulator 持久化 workflow block，并可将符合 workflow schema 的 `json` / `yaml` code block 升级为 workflow block。
- 前端用 workflow card 展示名称、节点、边、validation / runtime / dry-run / health 状态。
- evaluator 继续负责 workspace 文件级 `workflow_validation`。
- 本地无副作用 dry-run runner、run history 和 health API。
- Orchestrator 在 workflow validation passed 后自动执行 dry-run。

MVP 不覆盖：

- shell、HTTP、部署、workspace 写入或外部 Agent 调用类 step。
- 队列化长任务 runtime。
- 生产级外部 workflow worker。

## 2. WorkflowBlock

字段：

```json
{
  "type": "workflow",
  "agent_id": "codex-helper",
  "last_run_id": "132b73b3-6916-4ef0-a121-02b586f6011a",
  "name": "Launch Flow",
  "path": "workflow.yaml",
  "format": "yaml",
  "definition": {
    "version": "1",
    "name": "Launch Flow",
    "nodes": [{ "id": "start", "type": "trigger" }],
    "edges": []
  },
  "nodes": [{ "id": "start", "type": "trigger" }],
  "edges": [],
  "validation_status": "passed",
  "runtime_status": "ready",
  "dry_run_status": "passed",
  "health_status": "passed",
  "validation_errors": []
}
```

状态约定：

- `validation_status`: `passed | failed | unknown`
- `runtime_status`: `ready | invalid | not_supported`
- `dry_run_status`: `passed | failed | not_supported`
- `health_status`: `passed | failed | unknown`

当前 runtime / dry-run MVP 使用本地 allowlist runner：schema valid 且 supported dry-run 通过时 `runtime_status="ready"`、`dry_run_status="passed"`、`health_status="passed"`；schema 或 dry-run 失败时对应状态为 `invalid/failed/failed`。

## 3. Parser / Persistence

直接识别：

- <code>```workflow</code> 默认按 YAML。
- <code>```workflow-yaml</code> / <code>```workflow-yml</code> 按 YAML。
- <code>```workflow-json</code> 按 JSON。

落库升级：

- 普通 `json` / `yaml` code block 若解析后包含 `version/name/nodes/edges` 之一，会升级为 workflow block。
- 非 workflow JSON/YAML 保持 code block。
- workflow block 解析失败时持久化为 `validation_status="failed"`，不标记为 ready。

## 4. Validation

MVP validator 要求：

- 顶层是 object。
- 包含 `version`、`name`、`nodes`、`edges`。
- `nodes` 是非空 list。
- 每个 node 有唯一 string `id` 和 string `type`。
- `edges` 是 list。
- 每个 edge 的 `source` / `target` 指向存在的 node id。

## 5. 前端预览

前端 WorkflowBlock card 展示：

- 名称、path、节点数、边数。
- validation / runtime / dry-run / health 状态。
- 节点列表和边列表。
- 原始 JSON/YAML 定义预览。

## 6. Runtime / Dry-run

本地 runner 只允许无副作用节点：

- `trigger`
- `task` with `config.action="set_context"`
- `assert` with `config.equals`
- `end`

Runner 行为：

- 按 DAG topological order 执行。
- 检测 cycle、unsupported node type/action。
- `set_context` 将 `config.values` 合并到 dry-run context。
- `assert.equals` 按 dot-path 校验 context。
- 上游失败后下游节点标记 `skipped`。
- 单次 run 记录 node results、context、status 和 error。
- 限制 `max_nodes=50`、`max_edges=100`。

API：

```text
POST /api/v1/workspaces/{conversation_id}/workflow-runs
GET  /api/v1/workspaces/{conversation_id}/workflow-runs?path=workflow.yaml
GET  /api/v1/workspaces/{conversation_id}/workflow-runs/{run_id}
GET  /api/v1/workspaces/{conversation_id}/workflow-health?path=workflow.yaml
```

Orchestrator：

- `workflow_validation` passed 后自动 dry-run。
- dry-run result 进入 evaluation summary / memory event。
- persisted workflow block 会按 `path` 回填 latest run 的 `last_run_id`、`dry_run_status` 和 `health_status`。

## 7. 验收

- workflow fenced block 产生 `block_type="workflow"`。
- SSE accumulator 持久化合法 WorkflowBlock。
- 普通 JSON/YAML workflow code block 可升级为 workflow block。
- 普通 JSON code block 不被误升级。
- 前端 ContentRenderer 能展示 workflow card。
- OpenAPI 暴露 `WorkflowBlock`。
- Live E2E `p1_workflow_runtime` passed：
  - report: `/tmp/agenthub_p1_workflow_runtime_report.json`
  - sse: `/tmp/agenthub_p1_workflow_runtime_sse.jsonl`
  - conversation_id: `12ac1864-0158-48ca-a9f3-6640da9ab6ab`
  - passed: true
