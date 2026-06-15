# Agent Architecture Patterns Spec

> 目的：把主流 Agent 架构模式映射到 AgentHub B2 Orchestrator，避免把“LLM-first”误解为“LLM 任意执行”。
>
> 状态：Architecture reference / proposed evolution map
> 最后更新：2026-06-15

---

## 1. 推荐架构原则

AgentHub 推荐采用生产级 agent 架构：**LLM decision + deterministic executor + guardrails + observability**。

这意味着：

- LLM 负责理解意图、规划 task graph、选择下一步、提出 repair/review/fallback 建议。
- 后端负责状态机、DAG 并发、群聊 Agent 白名单、权限、重试上限、工具执行、敏感信息过滤和 run detail 观测。
- 子 Agent runtime 负责真实执行；Orchestrator 不伪造子 Agent 结果。
- `llm_control_points` 记录模型参与的安全摘要，但不保存完整 prompt、token、stderr、env 或密钥。

参考的主流模式：

- Anthropic Building Effective Agents：prompt chaining、routing、parallelization、orchestrator-workers、evaluator-optimizer。
  https://www.anthropic.com/research/building-effective-agents
- LangGraph：graph state machine、durable execution、streaming、human-in-the-loop。
  https://docs.langchain.com/oss/python/langgraph/overview
- OpenAI Agents SDK：agents、handoffs、guardrails、tracing。
  https://developers.openai.com/api/docs/guides/agents

---

## 2. 模式映射

| 模式 | 主流含义 | AgentHub 映射 | 状态 |
|---|---|---|---|
| Workflow / Graph State Machine | 预定义节点、边、状态和可控跳转 | 静态 DAG executor 按 `depends_on`、priority、concurrency 执行 | Implemented |
| Agent Loop | 模型观察状态并决定下一步 action/tool | Orchestrator tool loop 与 ReAct replanner | Partially implemented |
| Planner / Executor | 先规划，再由执行器完成任务 | LLM Planner 生成 `SubTask` graph，executor 调度子 Agent | Implemented |
| Orchestrator-Workers | 中央协调者分派给多个 worker | Orchestrator 调度 Claude/Codex/OpenCode/自建 Agent | Implemented |
| Parallelization | 可并行子任务同时执行 | DAG ready batch 并行执行，受 max concurrency 限制 | Implemented |
| Evaluator-Optimizer | 生成、评估、修复、再验证 | Evaluation / Reflection、review thread、quality repair loop | Partially implemented |
| Handoff | Agent 间交接和审阅 | review/handoff metadata、timeline、handoff hint | Implemented MVP |
| Tool Calling | 模型通过工具调用推进任务 | Orchestrator tool loop，平台 preview/browser/deploy tools | Partially implemented / optional |
| Guardrails | 模型输出必须经过策略和边界校验 | 群聊白名单、tool allowlist、secret filtering、fallback limits | Implemented |
| Tracing / Observability | 可诊断但不暴露 hidden reasoning | process block、memory events、`llm_control_points`、run detail | Implemented MVP |

---

## 3. 当前 AgentHub 结构

当前复杂任务默认主链是：

```text
User request
-> clarification / direct / platform fact gates
-> LLM Planner creates initial task graph
-> backend validates and normalizes the graph
-> static DAG executor runs ready batches
-> sub Agent runtimes execute tasks
-> deterministic evaluation / review / repair hooks
-> response polish or deterministic final summary
```

当前已实现能力：

- LLM Planner：`Implemented`。负责初始 task graph、Agent 分工、依赖和产物要求。
- 静态 DAG 并行 executor：`Implemented`。负责可靠并发、依赖推进和 task state。
- ReAct replanner：`Partially implemented`。已可基于 observation 决策，但默认不会覆盖多任务并行 DAG 主链的每个 batch。
- Dialogue controller：`Implemented`。纯对话/辩论场景可由 LLM 控制续轮和 judgement。
- Tool loop：`Partially implemented / optional`。进入该分支后由模型选择工具，但默认不是主执行路径。
- Response polish：`Implemented with fallback`。基于结构化事实润色最终回答。
- Fallback/retry：`Implemented deterministic`。候选、次数、cooldown 和群聊边界由后端规则控制。

---

## 4. 目标演进

目标不是删除静态 DAG executor，而是在它的安全边界内增加更强的 LLM 动态决策：

```text
Initial Planner
-> DAG Executor Batch
-> Batch-level Re-planner
-> continue / add repair / add review / skip / finish
-> Evaluator / Browser / Deployment evidence
-> Re-planner
-> Final Summary
```

建议状态划分：

- Parallel batch 后进入 Re-planner：`Proposed`。
- LLM 在安全白名单内建议 fallback/repair Agent：`Proposed`。
- Evaluator-Optimizer repair loop 统一由 Re-planner 决策：`Proposed`。
- 完整 autonomous tool-loop orchestrator：`Future / optional`。

---

## 5. 设计边界

- LLM 不直接执行 shell、读写 DB、绕过 workspace guard 或调用群聊外 Agent。
- Re-planner 输出只能是建议，必须经过后端校验、白名单过滤、cycle 防护和重试上限。
- Tool loop 是可选能力；即使启用，平台 tool 的实际执行仍由后端 service 完成。
- Fallback 不应完全交给模型自由选择；模型只能在当前群聊可运行 Agent 集合内建议。
- E2E 验收必须证明模型参与关键控制点，而不是只证明最终文件存在。

