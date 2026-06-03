# Orchestrator Evaluation / Reflection Loop Spec

> 状态：Current contract / remaining backlog
> 最后更新：2026-06-03
> 范围：把现有网页 preview quality gate 抽象为通用“生成 -> 验证 -> 修复 -> 再验证”闭环。

---

## 1. 背景

当前 Orchestrator 已经具备两类质量闭环：

- 网页 / 前端任务命中 preview、部署、浏览器验收意图时，会调用平台 `start_workspace_preview`。
- 随后调用 `verify_web_preview` 做浏览器级质量门。
- 验证失败后最多调度 repair agent 修复 2 轮，并在修复后刷新 preview snapshot 或重新调用 deployment tool 再验证。
- `expected_output` 可以触发 artifact 存在性检查和 per-task fallback。
- artifact Evaluation / Reflection 已实现 MVP：`artifact_exists`、`document_quality`、`code_static_quality`、`workflow_validation`、workflow allowlist dry-run、`ppt_validation`、受控 `test_report_quality`、网页 `browser_preview_quality`、`deployment_health` 和可注入 `requirements_coverage`。2026-06-03 live E2E 已验证 workflow validation -> dry-run -> health passed、deployment failure -> reflection -> repair agent -> redeploy -> published，以及 document_quality failed -> reflection -> repair/fallback -> final passed。

剩余缺口是：`.pptx` 二进制深度解析、workflow 外部 step / 平台 tool step / 队列化长任务 runtime、生产 LLM-as-judge、更多语言/测试框架 runner、部署平台真实探活重试策略仍未覆盖。MVP 之前，部分 artifact 任务可能停在：

```text
生成文件 -> 只检查文件存在 -> 输出 summary
```

长期目标应是统一质量路径：

```text
生成 -> 验证 -> 反思/归因 -> 修复 -> 再验证 -> 交付
```

## 2. 目标

新增通用 Evaluation / Reflection Loop，使 Orchestrator 对可交付任务都能用统一协议表达质量状态。

目标：

1. 对每个可交付 `SubTask` 生成 evaluation plan。
2. 按 artifact kind 和任务类型选择 evaluator。
3. 将验证结果结构化记录到 run context 和 memory。
4. 失败时生成 reflection，明确 failure category、evidence 和 repair instruction。
5. 调度 repair agent 修改 workspace 或产出说明。
6. 对同一 evaluator 再验证，直到通过、达到轮数上限或遇到不可自动修复问题。
7. 保留现有网页 browser quality gate 行为，并以 `browser_preview_quality` evaluator 事件表达。

非目标：

- 不开放任意 shell 给 Orchestrator。
- 不要求所有任务都必须通过自动验证；无法自动验证时输出 `manual_review_required`。
- 不在本阶段自动 merge workspace conflict。
- 不暴露模型 hidden reasoning；reflection 必须是面向用户和系统的结构化诊断摘要。

## 3. Evaluation Plan

规划层在 `SubTask` 上方引入可选 evaluation plan。v1 可先不改 `SubTask` schema，而是在 execution 层从 `expected_output`、artifact manifest、用户请求和 agent 能力推断。

建议结构：

```json
{
  "task_id": "write-api-docs",
  "artifact_paths": ["api.md"],
  "artifact_kind": "document",
  "evaluators": [
    {"name": "artifact_exists", "required": true},
    {
      "name": "document_quality",
      "required": true,
      "criteria": ["has_title", "has_examples", "no_empty_sections"]
    },
    {
      "name": "requirements_coverage",
      "required": true,
      "criteria": ["mentions_auth", "mentions_error_codes"]
    }
  ],
  "max_repair_rounds": 2
}
```

Evaluator 选择优先级：

1. 用户显式要求的验证，例如“运行测试”“检查文档完整性”“验证 API”。
2. `expected_output` 中的 artifact path 和 kind。
3. workspace artifact manifest 推断。
4. Agent 类型和任务标题。
5. 默认 `artifact_exists` + `requirements_coverage`。

## 4. Evaluator 类型

v1 建议从低风险、无需任意 shell 的 evaluator 开始：

| Evaluator | 适用对象 | 验证方式 |
|---|---|---|
| `artifact_exists` | 所有 workspace artifact | 只读检查路径存在、普通文件/目录状态 |
| `requirements_coverage` | 所有任务 | LLM-as-judge 或规则检查用户需求是否被覆盖 |
| `document_quality` | Markdown / text 文档 | 标题、结构、空段落、placeholder、过短内容 |
| `code_static_quality` | 代码文件 | AST/解析器、语言已知格式检查；不执行任意命令 |
| `test_report_quality` | 测试报告 / allowlist runner | 读取报告摘要，或运行受控 `python_compile_artifacts` |
| `deployment_health` | deployment record | 使用平台 deployment tool / health check 结果；失败时生成 reflection 并可触发 repair/redeploy |
| `browser_preview_quality` | HTML / static web | 复用现有 `verify_web_preview` |
| `workflow_validation` | JSON/YAML workflow | 校验 version/name/nodes/edges、节点唯一性、edge 引用 |
| `ppt_validation` | PPT outline / markdown / `.pptx` | 校验标题、slides 和每页内容；`.pptx` 做 OpenXML 文本层轻量解析 |
| `image_validation` | PNG/JPEG/GIF/WebP/SVG | 校验文件非空、文件头/尺寸或 SVG XML 可解析 |
| `archive_validation` | zip/tar/tgz/tar.gz | 校验 archive 非空、无 path traversal、大小和文件数受限 |
| `manual_review_required` | 无法自动验证的产物 | 输出待人工确认项，不阻断非关键交付 |

受控 `run_test` evaluator 必须通过平台 allowlist runner，不允许模型自由拼 shell。当前 MVP 仅启用 `python_compile_artifacts` alias，默认关闭。

## 5. Result Schema

每次 evaluation 产生结构化结果：

```json
{
  "evaluation_id": "eval-write-api-docs-1",
  "task_id": "write-api-docs",
  "attempt_index": 1,
  "status": "failed",
  "passed": false,
  "evaluator": "document_quality",
  "severity": "major",
  "issues": [
    {
      "code": "missing_examples",
      "message": "API document has endpoint descriptions but no request/response examples.",
      "evidence": "api.md",
      "repair_hint": "Add one request and response example for each endpoint."
    }
  ],
  "checked_artifacts": ["api.md"],
  "raw_output_truncated": false
}
```

状态建议：

- `passed`
- `failed`
- `skipped`
- `manual_review_required`
- `blocked`

Evaluation 结果会按 `checked_artifacts` 同步到 workspace artifact manifest：

- 任一相关 evaluator failed -> `evaluation_status="failed"`。
- 出现 `manual_review_required` evaluator -> `evaluation_status="manual_review_required"`。
- 相关 required evaluator 均 passed -> `evaluation_status="passed"`。
- 仅 skipped 或无 evaluator -> `evaluation_status="unknown"`。

manifest 更新失败不改变用户消息状态；平台记录 `artifact_manifest_update_failed` memory event
或 warning，不能把平台写入问题伪装成 artifact evaluator 失败。

## 6. Reflection

Reflection 是失败后的结构化归因，不是隐藏思维链。

```json
{
  "task_id": "write-api-docs",
  "repair_round": 1,
  "failure_category": "incomplete_requirements",
  "summary": "The document exists but misses examples required by the user request.",
  "evidence": ["document_quality:missing_examples"],
  "repair_instruction": "Update api.md. Add request/response examples for each endpoint. Keep existing sections."
}
```

Reflection 规则：

- 只基于 evaluator output、task result、artifact metadata 和用户请求。
- 不输出 hidden chain of thought。
- 必须包含可执行 repair instruction。
- 对不可自动修复问题标记 `blocked` 或 `manual_review_required`，不要空转重试。

## 7. Loop

通用执行流：

```text
run_task
-> collect artifact paths and task result
-> build evaluation plan
-> run evaluators
-> if all required evaluators pass: task succeeded
-> if evaluator failed and repair rounds remain:
     build reflection
     dispatch repair task
     rerun same required evaluators
-> if repair exhausted: task evaluation_failed
-> summary includes evaluation status and issues
```

与现有状态的关系：

- `artifact_missing` 仍是最早失败类型，可视作 `artifact_exists` evaluator failed。
- 网页 `run_quality_gate` 可迁移为 `browser_preview_quality` evaluator。
- deployment 失败可迁移为 `deployment_health` evaluator failed。
- workspace conflict 保持独立检测，但可以生成 `manual_review_required` evaluation。

建议新增 task state：

```text
evaluation_failed
manual_review_required
blocked
```

如需兼容前端，短期可以在 summary 中展示这些状态，并把顶层 SSE 仍保持 `done`。

## 8. Tool / Service 边界

Evaluator 必须通过平台受控 service 或 tool 执行。

允许：

- 只读 workspace inspection。
- 读取明确 artifact 文件，遵守大小限制和敏感路径过滤。
- 调用现有 platform tools：`verify_web_preview`、`get_deployment_status` 等。
- 调用 ModelGateway 做受控 LLM evaluation。

不允许：

- Orchestrator 自由执行 shell。
- 子 agent 自行启动 preview / deploy / server。
- evaluator 读取 `.env`、`.ssh`、`secrets`、`.agenthub`。
- repair agent 修改 `.agenthub/` manifest。

## 9. Memory 与 Summary

Orchestrator structured memory 建议新增 event：

```text
evaluation_started
evaluation_result
reflection_created
repair_dispatched
evaluation_finished
```

最终 summary 应展示：

- 每个任务的生成状态。
- 每个 required evaluator 的 pass/fail/manual 状态。
- 自动修复轮数。
- 仍需人工确认的问题。

示例：

```text
Evaluation summary:
- write-api-docs: passed after 1 repair
  - artifact_exists: passed
  - document_quality: passed
  - requirements_coverage: passed
- shared-conflict.md: manual_review_required because workspace conflict was detected
```

## 10. 分阶段落地

### Phase 1 - Spec 与最小通用 evaluator

- 新增 evaluator 数据结构和内部 runner。
- 将 artifact existence check 迁移为 `artifact_exists` evaluator。
- 增加 `requirements_coverage` 的 LLM-as-judge MVP。
- summary 展示 evaluation 状态。

### Phase 2 - Artifact evaluator 覆盖

- 增加 `document_quality`、`code_static_quality`、`workflow_validation`、`ppt_validation`、`test_report_quality`。
- 为文档 / 代码 / 后端服务任务生成默认 evaluation plan。
- evaluation 失败后调度 repair agent 并再验证。

### Phase 3 - 网页 quality gate 收敛

- 把现有 `run_quality_gate` 包装为 `browser_preview_quality` evaluator。
- 保持 `start_workspace_preview` / `verify_web_preview` tool event 兼容。
- 复用同一 reflection / repair / retry 机制。

### Phase 4 - 受控测试 runner

- MVP 支持 allowlist `python_compile_artifacts` runner，默认关闭。
- 后续支持 repo 已知命令，例如 `pnpm test -- --run`、`uv run pytest`，但必须由平台配置允许。
- 保存测试 report artifact，用 `test_report_quality` 判断结果。

## 11. 验收标准

- 文档任务能在文件存在后继续做内容完整性 evaluation。
- Evaluation 失败会生成 reflection，并调度 repair agent。
- Repair 后会重新运行同一组 required evaluators。
- 达到最大修复轮数后不会无限循环，summary 明确失败原因。
- 网页 preview quality gate 行为保持兼容。
- 所有 evaluator 都遵守 workspace path guard 和敏感路径过滤。
- 真实 E2E 至少覆盖：
  - Markdown 文档缺章节 -> repair -> pass：已由 `p1_evaluation_repair` 公网 E2E 覆盖，report `/tmp/agenthub_p1_evaluation_repair_report.json`，conversation `5186e757-6a7c-4d0f-8643-c9b3defbc181`。
  - 代码产物存在但语法不合法 -> repair -> pass 或 `evaluation_failed`。
  - 网页 preview 原有 Case 1 仍通过。

## 12. 相关文件

| 文件 | 说明 |
|---|---|
| [core.spec.md](core.spec.md) | 当前 Orchestrator task state、fallback、summary 主契约 |
| [tool-calling.spec.md](tool-calling.spec.md) | Orchestrator platform tools 和 workspace tools |
| [workspace-conflict.spec.md](workspace-conflict.spec.md) | conflict detection 可映射为 manual review evaluator |
| [../workspace-artifact-preview.spec.md](../workspace-artifact-preview.spec.md) | artifact kind、preview、deployment 边界 |
| [../b2-pdf-gap-todo.spec.md](../b2-pdf-gap-todo.spec.md) | PDF 对照 backlog |
| [../../../ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md](../../../ai-skills/orchestrator-live-e2e-repair-loop/SKILL.md) | 当前真实 E2E 修复闭环 skill |
