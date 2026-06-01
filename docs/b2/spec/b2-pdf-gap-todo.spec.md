# B2 PDF Gap TODO

> 目的：根据课程 PDF《AgentHub - 多 Agent 协作平台设计》对照当前 B2 实现，列出尚未达标或只部分达标的 B2 TODO 清单。
>
> 状态：P0 implemented / P1+ backlog
> 最后更新：2026-05-31
>
> Spec 整理入口：完整状态分类、保留/精简/提案/历史边界见 [README.md](README.md)。

---

## 1. 当前结论

B2 当前已经具备 Agent Runtime Layer 的主体能力：

- `BaseAgentAdapter` / `StreamChunk` 统一协议。
- Claude Code / Codex / OpenCode external runtime 接入。
- Builtin Agent Framework + ModelGateway 底座。
- Orchestrator 任务拆解、群聊内子 Agent 调度、结果聚合。
- Artifact 追踪、平台 preview tool、8082 static preview、浏览器级质量验收与修复闭环。

与 PDF 要求相比，P0 核心缺口已经补齐并通过真实 E2E：

1. 并行 DAG 调度：已实现，默认开启。
2. Workspace snapshot / diff / conflict detection：已实现，冲突先记录和展示，不自动 merge。
3. 对话式自建 Agent：已实现 `create_custom_agent` 平台 tool，并支持加入当前群聊。

当前剩余缺口集中在：

1. 完整部署发布能力。
2. Workflow 产物支持。
3. Agent-to-Agent review thread。
4. 长期记忆与 Agent 能力画像。
5. 通用 Reflection / Evaluation 闭环。
6. 更丰富产物类型。

---

## 2. P0 已完成 - 核心多 Agent 达标项

本节只保留 PDF gap 对照结论。具体能力契约按架构归位：

- 并行 DAG 调度：见 [orchestrator/core.spec.md](orchestrator/core.spec.md) 与 [orchestrator/task-planning.spec.md](orchestrator/task-planning.spec.md)。
- Workspace 冲突处理：见 [orchestrator/workspace-conflict.spec.md](orchestrator/workspace-conflict.spec.md)。
- 对话式自建 Agent：见 [orchestrator/tool-calling.spec.md](orchestrator/tool-calling.spec.md) 与 [builtin-agent-framework.spec.md](builtin-agent-framework.spec.md)。
- 真实 E2E 证据：见 [orchestrator/live-e2e-report.spec.md](orchestrator/live-e2e-report.spec.md)。

### B2-GAP-01 并行 DAG 调度

PDF 对应要求：

- Orchestrator 支持并行调度。
- 多个 Agent 像群聊成员一样依次或协同产出。

当前状态：

- `SubTask.depends_on` 已存在。
- 静态任务执行器已支持 DAG ready queue。
- `llm_planning=true` 与 `orchestrator_parallel_enabled=true` 已作为 Orchestrator 默认配置。
- `orchestrator_parallel_max_concurrency=3` 已作为默认并发上限。
- 任务执行仍复用 `_run_task()`、fallback、artifact check 和 memory hooks。

已实现：

- 同一轮中并发执行所有依赖已满足的 runnable tasks。
- SSE 输出需要保持可读：并发内部可同时执行，但前端展示可按任务开始时间或完成时间串行落地。
- 增加配置：
  - `orchestrator_parallel_enabled`
  - `orchestrator_parallel_max_concurrency`
- 增加环境变量默认值覆盖：
  - `ORCHESTRATOR_LLM_PLANNING_DEFAULT`
  - `ORCHESTRATOR_PARALLEL_ENABLED_DEFAULT`
  - `ORCHESTRATOR_PARALLEL_MAX_CONCURRENCY_DEFAULT`

主要影响文件：

- `backend/app/agents/orchestrator/execution.py`
- `backend/app/agents/orchestrator/types.py`
- `backend/app/agents/config_fields.py`
- `backend/app/schemas/agent.py`
- `backend/app/core/config.py`
- `backend/tests/test_orchestrator.py`

验收结果：

- 两个互不依赖任务能并发调度。
- 有依赖任务等待依赖成功后执行。
- 前置失败时下游 task 标记 `skipped`。
- 真实 E2E Case 2 已通过，workspace 生成 `parallel-claude.md`、`parallel-opencode.md`、`review.md`。

### B2-GAP-02 Workspace 冲突处理

PDF 对应要求：

- Orchestrator 支持代码冲突处理。
- 多 Agent 共同产出代码时不能互相覆盖。

当前状态：

- Workspace 路径安全已经有。
- Artifact missing check 已经有。
- 已有 workspace snapshot、created / modified / deleted diff、同一 run 内冲突检测。
- 已记录 `workspace_snapshot`、`workspace_file_changes`、`workspace_conflict_detected` memory events。
- 冲突先在 summary 和 memory event 中展示，不自动 merge。

已实现：

- 在每个 subtask 开始前记录 workspace snapshot。
- subtask 结束后计算 created / modified / deleted。
- 检测同一 run 内多个 Agent 修改同一文件的冲突。
- 对冲突文件生成 conflict report，列出冲突文件、涉及 task、涉及 agent。

本阶段边界：

- 不做自动 merge。
- 不做文件级锁。
- 不做 rollback。
- 后续 P1/P2 再接入 patch review / repair / merge 策略。

主要影响文件：

- `backend/app/agents/orchestrator/artifacts.py`
- `backend/app/agents/orchestrator/execution.py`
- `backend/app/agents/orchestrator/workspace_changes.py`
- `backend/app/agents/orchestrator/memory_hooks.py`
- `backend/app/services/orchestrator_memory.py`
- `backend/tests/test_orchestrator.py`

验收结果：

- A、B 两个 Agent 修改同一文件时能记录冲突。
- Orchestrator summary 中显示冲突文件、涉及 task、涉及 agent。
- 冲突不能被静默覆盖。
- 冲突处理过程有可追踪 event / memory 记录。
- 真实 E2E Case 3 已通过，`shared-conflict.md` 冲突被记录且 run 未崩溃。

### B2-GAP-03 对话式自建 Agent

PDF 对应要求：

- 支持用户自建 Agent。
- 创建方式是对话式创建，设定 System Prompt + 工具集。

当前状态：

- 后端已有 Agent CRUD。
- Builtin Agent Framework 已存在。
- Orchestrator 已支持聊天中通过正式平台 tool `create_custom_agent` 创建自建 Agent。
- 支持创建后加入当前 group conversation。
- 缺少必要字段时返回 `needs_user_input=true`，不创建半成品。

已实现：

- 新增 Orchestrator / Builtin tool：`create_custom_agent`。
- 支持从用户描述中提取：
  - name
  - provider
  - system_prompt
  - capabilities
  - tool whitelist
  - model/runtime config
- 对缺失字段调用 `ask_user`。
- 创建后返回 Agent 联系人信息，并允许立即拉入当前会话。
- 工具白名单必须走 config validation。

主要影响文件：

- `backend/app/agents/orchestrator/tools.py`
- `backend/app/agents/orchestrator/tool_loop.py`
- `backend/app/agents/orchestrator/adapter.py`
- `backend/app/services/orchestrator_platform_tools.py`
- `backend/app/agents/config_validation.py`
- `backend/tests/test_orchestrator_tool_calling.py`
- `backend/tests/test_agent_config_validation.py`

验收结果：

- 用户在聊天里说“创建一个文案 Agent，语气专业，能读写文件”，平台能生成自建 Agent。
- 缺少 provider/tool 权限时会追问，而不是创建半成品。
- 新 Agent 出现在 `/api/v1/agents`。
- 新 Agent 可在后续会话中被 Orchestrator 调度。
- 真实 E2E Case 4 已通过，`LiveCopywriter-{timestamp}` 创建成功并加入当前群聊。

### P0 验证记录

自动化验证：

```bash
cd backend
uv run pytest -q
# 440 passed, 7 skipped, 1 warning

uv run ruff check app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/browser_preview_verifier.py app/core/config.py app/schemas/agent.py app/api/v1/stream_orchestrator_context.py app/agents/registry.py
# passed

uv run mypy app/agents app/services/orchestrator_platform_tools.py app/services/orchestrator_memory.py app/services/browser_preview_verifier.py app/core/config.py app/schemas/agent.py
# passed
```

真实 E2E 验证：

- 报告：`/tmp/agenthub_b2_p0_live_report.json`
- 结果：`passed=true`
- Case 0：数据库内 Orchestrator config 已开启 `llm_planning=true`、`orchestrator_parallel_enabled=true`、`orchestrator_parallel_max_concurrency=3`。
- Case 1：8082 前端质量门通过，`start_workspace_preview` / `verify_web_preview` 为正式 tool 调用。
- Case 2：DAG 并行调度通过。
- Case 3：Workspace conflict 检测通过。
- Case 4：对话式自建 Agent 通过。

部署验证：

- 后端已从当前本地代码重启到 `0.0.0.0:8000`。
- 已重新执行 `uv run python -m app.seeds.seed_agents`。
- `http://127.0.0.1:8000/health` 与 `http://111.229.151.159:8000/health` 均返回正常。

---

## 3. P1 TODO - 影响产物交付完整度

### B2-GAP-04 Deployment / Release Tool（MVP 已实现，完整 P2 继续完善）

PDF 对应要求：

- 聊天中直接发送“部署”指令，Agent 返回部署状态卡片。
- 一键生成预览 URL / 静态站点部署 / 容器化部署 / 源码打包下载。

当前状态：

- 已实现平台 static preview 和可追踪 `WorkspaceDeployment` record。
- Orchestrator 有正式 `create_deployment`、`get_deployment_status`、`package_workspace_source` tool。
- 已实现 `deployment_status` 消息块、前端卡片、静态站点发布和源码 zip 下载。
- 容器化部署返回 `not_supported`，不执行 Docker 或 shell。
- 当前静态发布仍复用 Preview 生命周期；尚未形成不可变 release snapshot。
- 当前停止 static deployment 只更新 record，没有真正停止独立发布 runtime。
- 远端前端尚未重新发布状态卡 UI。
- 真正容器化发布仍未实现。

后续完善计划：

- 见 [deployment-release-hardening.execution.spec.md](deployment-release-hardening.execution.spec.md)。
- 先完成静态发布与 Preview 解耦、snapshot、真实 stop、资源清理和前端发布准备。
- Container 先补安全底座和默认关闭的 feature flag；真实 E2E 等用户后续明确命令再执行。

实现内容：

- 新增正式平台 deployment tools：
  - `create_deployment`
  - `get_deployment_status`
  - `package_workspace_source`
- 新增部署记录模型：
  - deployment id
  - conversation id
  - workspace id
  - artifact path
  - deployment kind：`static_site | source_zip | container`
  - status
  - public url
  - download url
  - logs
  - error
  - created / updated timestamps
- 新增 `deployment_status` 消息块 / 前端卡片。
- MVP 先支持 `static_site` deployment + `source_zip` download。
- 容器化部署本阶段返回 `not_supported`，不执行 Docker 或 shell。

建议影响文件：

- `backend/app/agents/orchestrator/tools.py`
- `backend/app/services/orchestrator_platform_tools.py`
- `backend/app/services/workspace_preview.py`
- `backend/app/api/v1/workspaces.py`
- `backend/app/models/workspace.py`
- `backend/app/schemas/workspace.py`
- `backend/tests/test_workspace_api.py`
- `backend/tests/test_orchestrator_tool_calling.py`
- `frontend/src/components/blocks/ContentRenderer.tsx`
- `frontend/src/components/blocks/DeploymentStatusBlock.tsx`

验收标准：

- 用户说“部署这个网页”，Orchestrator 明确调用 `create_deployment(kind="static_site")`。
- 返回部署状态和 URL，不由 Agent 编造 URL。
- 部署失败有状态、错误原因和日志。
- 源码打包下载接口可用。
- 用户说“容器化部署”时返回 `not_supported` 状态卡，不执行 Docker。
- 用户只说“预览”时仍走 `start_workspace_preview`，不混淆 preview 与 deployment。

### B2-GAP-05 Workflow 产物支持

PDF 对应要求：

- 通过对话式交互创建网页、Workflow 等产物。

当前状态：

- 当前产物链路主要覆盖代码、HTML、Diff、网页预览。
- 没有 workflow schema、runner、validator 或 preview。

待办：

- 定义 Workflow artifact schema，例如：
  - nodes
  - edges
  - inputs
  - outputs
  - trigger
  - steps
- 新增 artifact kind：`workflow`。
- Orchestrator 能识别“帮我做一个工作流/流程”的任务意图。
- Builtin Agent 可生成 workflow JSON。
- 平台提供 workflow validator。
- 前端展示可先用 JSON / mermaid / 简单 DAG metadata。

建议影响文件：

- `backend/app/agents/artifact_parser.py`
- `backend/app/agents/orchestrator/task_planning.py`
- `backend/app/agents/orchestrator/artifacts.py`
- `backend/app/schemas/message.py`
- `backend/app/schemas/workspace.py`
- `backend/tests/test_artifact_parser.py`
- `backend/tests/test_orchestrator_planning.py`

验收标准：

- 用户请求 workflow 时，workspace 生成结构化 workflow 文件。
- workflow 文件通过平台 validator。
- Orchestrator summary 能列出 workflow artifact。
- 非法 workflow 不被标记为 ready。

### B2-GAP-06 Agent-to-Agent Review Thread

PDF 对应要求：

- 多 Agent 群聊协作，而不只是主 Agent 串行转述。

当前状态：

- 子 Agent 之间主要通过 Orchestrator 汇总上下文接力。
- 没有直接互评、质疑、确认或 handoff thread。

待办：

- 新增 review task 类型：
  - implementation task
  - review task
  - repair task
- Orchestrator 在关键产物生成后自动安排另一个 Agent review。
- review agent 必须引用具体 artifact/diff。
- review 失败时生成 repair task。
- 记录 handoff reason 和 review outcome。

建议影响文件：

- `backend/app/agents/orchestrator/task_planning.py`
- `backend/app/agents/orchestrator/execution.py`
- `backend/app/agents/orchestrator/quality.py`
- `backend/app/agents/orchestrator/summary.py`
- `backend/app/models/orchestrator_memory.py`
- `backend/tests/test_orchestrator.py`
- `backend/tests/test_orchestrator_quality_gate.py`

验收标准：

- 构建任务后至少一个群聊内其他 Agent 能执行 review。
- review 明确指出通过/失败/需修复。
- 修复任务只使用当前群聊成员。
- 最终 summary 展示 review 结论。

---

## 4. P2 TODO - 提升真实多 Agent 系统成熟度

### B2-GAP-07 长期记忆与 Agent 能力画像

当前状态：

- 有 `orchestrator_runs` / `tasks` / `attempts` / `events`。
- 更像 run log，不是长期经验系统。

待办：

- 从历史 run 中聚合 agent success rate、timeout rate、artifact missing rate。
- 形成 Agent capability profile。
- Planner 调度时参考能力画像。
- 记录用户偏好，例如常用主题、代码风格、部署偏好。

验收标准：

- 同类失败多次后，Orchestrator 会降低该 Agent 优先级。
- 调度理由中能说明选择某 Agent 的历史依据。

### B2-GAP-08 Reflection / Evaluation 闭环通用化

当前状态：

- 前端 preview 任务已有 quality gate。
- 其他任务没有统一 evaluation/reflection。

待办：

- 抽象通用 evaluation stage：
  - artifact exists
  - schema valid
  - tests pass
  - browser verify
  - review passed
- 每类任务有自己的 evaluator。
- 失败后统一生成 repair task。

验收标准：

- 非网页任务也能进入“生成 -> 验证 -> 修复 -> 再验证”闭环。
- 最终交付必须带 evaluation summary。

### B2-GAP-09 更丰富产物类型

当前状态：

- 代码、HTML、Diff 较强。
- 文档、PPT、图片、附件、版本历史能力弱。

待办：

- 补充 artifact kind：
  - markdown document
  - pdf/document
  - ppt
  - image
  - archive
- 扩展 artifact manifest。
- 支持文件附件 block 与下载链接。

验收标准：

- Agent 生成 README / report 时能被识别为 document artifact。
- 打包下载时能包含所有相关产物。

---

## 5. 建议执行顺序

建议按照以下顺序推进：

1. B2-GAP-04 Deployment hardening
   MVP 已补齐演示缺口；下一步按 [deployment-release-hardening.execution.spec.md](deployment-release-hardening.execution.spec.md) 将静态发布与 Preview 解耦，并补 container 安全底座。

2. B2-GAP-05 Workflow 产物支持  
   补课题背景中“Workflow 等产物”的覆盖面。

3. B2-GAP-06 Agent-to-Agent Review Thread  
   让协作从“Orchestrator 转派”更接近真实多 Agent 讨论。

4. B2-GAP-07 长期记忆与 Agent 能力画像  
   让 planner 从固定规则升级为带历史依据的 agent 选择。

5. B2-GAP-08 Reflection / Evaluation 闭环通用化  
   将当前网页质量门抽象到更多产物类型。

6. B2-GAP-09 更丰富产物类型  
   作为答辩加分项和长期演进。

---

## 6. Demo 验收矩阵

| 场景 | 当前能否演示 | 完成 TODO 后的目标 |
|---|---:|---|
| 群聊 @orchestrator 做前端页面 | 可以 | 保持稳定 |
| 自动生成 workspace 代码产物 | 可以 | 保持稳定 |
| 8082 静态预览 | 可以 | Preview 保持临时验收职责，Static release 使用独立生命周期 |
| 浏览器质量验收 | 可以 | 通用 evaluation framework |
| 并行调用多个 Agent | 可以 | 继续补并行可观测性和更复杂依赖图 |
| 多 Agent 修改同一文件冲突检测 | 可以 | 冲突报告 + 修复/合并策略 |
| 聊天中创建自建 Agent | 可以 | 补前端联系人管理和更多工具白名单 UI |
| 生成 Workflow 产物 | 不可以 | workflow schema + validator |
| 部署状态卡片 | 仓库内已实现，远端前端待发布 | 发布前端构建，并补状态刷新、停止入口和部署历史 |
| 源码打包下载 | 可以 | 补限额、digest、过期清理和更多安全测试 |
| 容器化部署 | 仅 `not_supported` 占位 | 补 rootless runtime、policy、Worker、限额与清理后再开放 |
