# B2-08 Orchestrator Spec 与任务拆解 Prompt

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-08
任务名称：Orchestrator Spec 与任务拆解 Prompt

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目 B2 Agent 集成方向的具体子任务。
Codex 负责总览、任务拆解、边界检查和最终审阅。
你只完成本任务范围内的文档和设计沉淀，不要提前实现完整 Orchestrator。

项目背景：
AgentHub 当前已经完成 Claude/OpenAI/Custom Adapter、ArtifactParser v2 和 SSE error 状态处理。
下一阶段要进入多 Agent 编排。现有 `backend/app/agents/orchestrator.py` 仍是 stub。
B2-08 的目标不是直接写完整生产实现，而是先定义 Orchestrator 的行为契约、任务拆解格式、事件流规则、失败降级策略，并为 B2-09/B2-10 的实现提供明确执行边界。

请先阅读：
1. AGENTS.md
2. docs/b2-task-dispatch/B2-roadmap.md
3. docs/b2-ai-task-dispatch-template.md
4. docs/tech-architecture.md
5. backend/app/agents/orchestrator.py
6. backend/app/agents/base.py
7. backend/app/agents/types.py
8. backend/app/agents/registry.py
9. backend/app/agents/adapters/custom.py
10. backend/app/agents/adapters/claude.py
11. backend/app/agents/adapters/openai.py

允许修改：
- docs/spec/orchestrator.spec.md
- docs/b2-task-dispatch/B2-08-orchestrator-spec.md
- docs/b2-task-dispatch/README.md
- docs/b2-task-dispatch/B2-roadmap.md
- docs/ai-collaboration-log.md

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/adapters/**
- backend/app/agents/orchestrator.py
- backend/app/schemas/**
- shared/openapi.yaml
- frontend/**
- docker-compose.yml
- .env
- backend/.env

本任务不允许修改 OpenAPI、BaseAgentAdapter.stream() 签名、StreamChunk schema 或 ContentBlock schema。

交付目标：
1. 新建 `docs/spec/orchestrator.spec.md`
   必须包含：
   - 目标
   - 输入 / 输出
   - Orchestrator 在 group chat 中的职责
   - task decomposition 的结构化格式
   - 子 Agent 调度顺序
   - `agent_switch` 事件语义
   - `block_index` 重映射规则
   - 子 Agent 失败时的降级策略
   - 不修改 BaseAgentAdapter / StreamChunk / ContentBlock 的约束
   - B2-09 / B2-10 的验收标准

2. 更新或完善 `docs/b2-task-dispatch/B2-08-orchestrator-spec.md`
   保持它作为本任务的 Claude Code 执行文档。
   如果你认为当前命令不够完整，可以补充细节，但不要改变任务边界。

3. 更新 `docs/b2-task-dispatch/README.md`
   - 在任务索引中加入 B2-08
   - B2-08 状态标记为“已拆解，待执行”或“进行中”

4. 更新 `docs/b2-task-dispatch/B2-roadmap.md`
   - 将 B2-08 状态从“待拆解”更新为“已拆解，待执行”
   - 明确 B2-08 只做 Spec / Prompt，不实现完整 Orchestrator
   - 保持 B2-09 / B2-10 作为后续实现任务
   - 如有必要，将 PR 边界拆成：
     - B2-08：Orchestrator spec/docs
     - B2-09：Orchestrator 顺序调度与 block_index 重映射
     - B2-10：失败降级与部分成功输出

5. 更新 `docs/ai-collaboration-log.md`
   追加一条 B2-08 启动记录，说明：
   - Codex 拆解任务和边界
   - Claude Code 执行文档与 Spec
   - Codex 最终审阅
   - Git/PR Claude 只负责分支、commit、push、PR

Orchestrator Spec 关键设计要求：
1. 输入
   - `messages: list[ChatMessage]`
   - `system_prompt: str | None`
   - `config: dict[str, Any] | None`
   - group chat 中可用的 agent 列表应由外层注入，不允许 Orchestrator 直接访问数据库。

2. 输出
   - 必须沿用 `StreamChunk`
   - 正常事件序列应包含：
     - `start`
     - task planning text block
     - 若干 `agent_switch`
     - 子 Agent 的 block_start/delta/block_end
     - final summary text block
     - `done`
   - 不新增 StreamChunk 字段。

3. 任务拆解格式
   Spec 中需要定义一个稳定的内部结构，例如：
   - task_id
   - agent_id
   - title
   - instruction
   - depends_on
   - priority
   - expected_output

4. 子 Agent 调度
   - B2-09 先实现顺序调度，不做并发。
   - 每个子 Agent 调用必须通过 registry / adapter 抽象，不直接 import 具体 Provider SDK。
   - 子 Agent 的 `block_index` 必须重映射，避免多个子 Agent 输出互相冲突。

5. `agent_switch`
   - 切换到某个子 Agent 前发出 `StreamChunk(event_type="agent_switch")`
   - 需要说明 from_agent / to_agent / task 字段的语义。

6. 失败降级
   - 单个子 Agent 失败时，不应直接中断整个 Orchestrator。
   - B2-10 负责实现“记录失败、继续后续任务、最终 summary 说明部分失败”的策略。
   - Spec 中先定义规则和验收标准。

7. 边界
   - 不做数据库访问。
   - 不改 OpenAPI。
   - 不新增 ContentBlock 类型。
   - 不改 BaseAgentAdapter。
   - 不引入新的第三方依赖。
   - 不实现并发调度。

验证命令：
在仓库根目录运行：
git diff --check
git status --short

如果你没有修改 Python 代码，不需要运行 pytest。
如果你意外修改了 Python 代码，请停止并说明原因，不要继续扩大范围。

## 执行结果（Claude Code 完成后填写）

### 修改的文件

1. 新建 `docs/spec/orchestrator.spec.md`
2. 更新 `docs/b2-task-dispatch/B2-08-orchestrator-spec.md`（本文件）
3. 更新 `docs/b2-task-dispatch/README.md`
4. 更新 `docs/b2-task-dispatch/B2-roadmap.md`
5. 更新 `docs/ai-collaboration-log.md`

### `orchestrator.spec.md` 核心设计点

- **输入**：`messages`, `system_prompt`, `config` + 外层注入的 `available_agents` 和 `orchestrator_llm_config`；Orchestrator 不直接访问数据库。
- **输出**：标准 `StreamChunk` 序列，不新增字段；事件顺序为 `start → task planning → agent_switch → 子 Agent chunks → summary → done`。
- **任务拆解格式**：定义 `SubTask` 结构（`task_id`, `agent_id`, `title`, `instruction`, `depends_on`, `priority`, `expected_output`），通过 LLM function calling / tool use 生成。
- **顺序调度**：B2-09 按 `priority` 排序、检查 `depends_on` 依赖、顺序调用子 Agent；通过 config 注入的 `sub_adapters` / `adapter_factory` 获取子 Agent Adapter；registry 生产接线留给后续 B1/B2 协同任务。
- **`agent_switch` 语义**：切换前发出，包含 `from_agent="orchestrator"`, `to_agent`, `task`；客户端可据此展示 Agent 工作状态。
- **`block_index` 重映射**：维护全局 `global_block_offset`，子 Agent 的 `start`/`done` 被吞掉，其余 chunk 的 `block_index` 加上偏移量后外发，确保全局单调递增。
- **失败降级**：B2-10 实现单个子 Agent 失败不中断主流程，fallback 到文本说明块，最终 summary 列出 `SUCCEEDED`/`FAILED`/`SKIPPED` 状态；即使部分失败也 yield `done`。
- **契约约束**：不修改 `BaseAgentAdapter.stream()` 签名、不新增 `StreamChunk` 字段、不新增 `ContentBlock` 类型、不改 OpenAPI。

### B2-09 / B2-10 衔接

- **B2-09**：基于本 Spec 的 §5（调度顺序）、§6（agent_switch）、§7（block_index 重映射）和 §10.1（验收标准），实现 `OrchestratorAdapter.stream()` 的核心顺序调度逻辑。
- **B2-10**：基于本 Spec 的 §8（失败降级）和 §10.2（验收标准），增强异常处理、部分成功输出和 final summary。
- PR 边界：
  - PR-B2-08：`feat/B2-orchestrator-spec` — Spec + 文档更新（不实现代码）
  - PR-B2-09：`feat/B2-orchestrator-dispatch` — 顺序调度与 block_index 重映射
  - PR-B2-10：`feat/B2-orchestrator-fallback` — 失败降级与部分成功输出

### 是否修改代码文件

否。本任务未修改任何 `.py`、`.ts`、`.yaml` 等代码文件，只新建/更新了 `docs/**` 下的 Markdown 文档。

### 验证命令结果

```bash
git diff --check
# 无尾随空白冲突
git status --short
# 只显示 docs/** 下的新增/修改文件
```

---

**本任务完成后不要 commit，不要 push，不要创建 PR。**
**请先把结果交给 Codex 进行最终审阅。**
```
