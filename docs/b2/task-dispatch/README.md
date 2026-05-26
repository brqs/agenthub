# B2 子任务分发记录

本目录记录 B2 Agent Runtime Layer 中，Codex 拆解后交给 OpenCode 执行的具体子任务。

B2-01 至 B2-13 是 Agent Runtime Pivot 前的历史任务，主要沉淀 raw LLM Provider Adapter、ArtifactParser、Provider resilience 和 Orchestrator 基线。B2-14 起进入真实 Agent Runtime 接入阶段，产品侧 runtime 范围固定包含 Claude Code / Codex / OpenCode，以及团队自建 BuiltinAgent。

## 协作方式

- Codex 负责总览、拆解、协调、边界检查和最终代码审阅。
- OpenCode 负责按任务文档执行具体实现和测试。
- Claude Code 只在 Codex 复审通过后负责 Git 状态整理、commit、push 和 PR 准备，不参与开发实现。
- B2 负责人每个子任务新开一个 OpenCode 对话窗口执行，并将执行结果交回 Codex 审阅。

Git/PR 操作规范见 [../../archive/git-pr-ops/README.md](../../archive/git-pr-ops/README.md)。

B2 总体目标框架和后续任务路线图见 [B2-roadmap.md](B2-roadmap.md)。

## 本地 Python 环境

B2 本地开发使用 Anaconda 环境 `LLMAgent`。OpenCode 执行 Python 任务前应优先复用该环境，不要重复创建或安装新的 Python 环境。

常用命令：

```bash
conda activate LLMAgent
python --version
python -m pytest tests/test_artifact_parser.py
```

如果执行更完整的后端测试时报 `ModuleNotFoundError`，应在已有 `LLMAgent` 环境中安装项目依赖，不要新建 Python 环境：

```bash
cd backend
python -m pip install -e ".[dev]"
```

也可以在不激活 shell 的情况下执行：

```bash
conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py
```

## 任务索引

| 编号 | 任务 | 状态 | 文档 |
|------|------|------|------|
| B2-01 | 实现 StreamingArtifactParser 流式产物解析器 | 已完成 | [B2-01-streaming-artifact-parser.md](B2-01-streaming-artifact-parser.md) |
| B2-02 | 实现 ClaudeAdapter 真实 Anthropic 流式接入 | 已完成 | [B2-02-claude-adapter-streaming.md](B2-02-claude-adapter-streaming.md) |
| B2-03 | 实现 OpenAIAdapter 真实 OpenAI 流式接入 | 已完成 | [B2-03-openai-adapter-streaming.md](B2-03-openai-adapter-streaming.md) |
| B2-04 | 实现 CustomAdapter 委托上游 Provider | 已完成 | [B2-04-custom-adapter-delegation.md](B2-04-custom-adapter-delegation.md) |
| B2-05 | Agent 配置校验与内置 Agent 配置对齐 | 已完成 | [B2-05-agent-config-validation.md](B2-05-agent-config-validation.md) |
| B2-06 | SSE error 状态持久化协同修复 | 已完成 | [B2-06-stream-error-status.md](B2-06-stream-error-status.md) |
| B2-07 | ArtifactParser v2 富媒体识别增强 | 已完成 | [B2-07-artifact-parser-v2.md](B2-07-artifact-parser-v2.md) |
| B2-08 | Orchestrator Spec 与任务拆解 Prompt | 已完成 | [B2-08-orchestrator-spec.md](B2-08-orchestrator-spec.md) |
| B2-09 | Orchestrator 子 Agent 顺序调度与 block_index 重映射 | 已完成 | [B2-09-orchestrator-dispatch.md](B2-09-orchestrator-dispatch.md) |
| B2-10 | Orchestrator 失败降级与部分成功输出 | 已完成 | [B2-10-orchestrator-fallback.md](B2-10-orchestrator-fallback.md) |
| B2-11 | Provider retry / timeout / rate-limit 策略 | 已完成，Codex 审阅通过 | [B2-11-provider-resilience.md](B2-11-provider-resilience.md) |
| B2-12 | Adapter E2E smoke tests 与可选真实 API slow tests | 已完成，Codex 审阅通过 | [B2-12-adapter-smoke-tests.md](B2-12-adapter-smoke-tests.md) |
| B2-13 | B2 演示脚本、答辩材料和架构说明 | 已完成 | [B2-13-demo-and-architecture.md](B2-13-demo-and-architecture.md) |
| B2-14 | Agent Runtime Pivot 文档与任务重基线 | 已完成，Codex 复审通过 | [B2-14-agent-runtime-rebaseline.md](B2-14-agent-runtime-rebaseline.md) |
| B2-15 | ModelGateway 拆分与 raw LLM Adapter 降级 | 已完成，Codex 复审通过 | [B2-15-model-gateway-split.md](B2-15-model-gateway-split.md) |
| B2-16 | Claude Code ExternalAgentAdapter | 已完成，Codex 复审通过 | [B2-16-claude-code-external-adapter.md](B2-16-claude-code-external-adapter.md) |
| B2-17 | Codex ExternalAgentAdapter | 已完成，Codex 复审通过 | [B2-17-codex-external-adapter.md](B2-17-codex-external-adapter.md) |
| B2-18 | OpenCode ExternalAgentAdapter | 已完成，Codex 复审通过 | [B2-18-opencode-external-adapter.md](B2-18-opencode-external-adapter.md) |
| B2-19 | BuiltinAgent MVP | 已完成，Codex 复审通过 | [B2-19-builtin-agent-mvp.md](B2-19-builtin-agent-mvp.md) |
| B2-20 | 真实 Agent Demo Smoke 与 Registry 接线 | 已完成，Codex 复审通过 | [B2-20-real-agent-demo-smoke.md](B2-20-real-agent-demo-smoke.md) |

## 模板

通用分发模板见 [../ai-task-dispatch-template.md](../ai-task-dispatch-template.md)。
Codex 复审模板见 [../codex-review-template.md](../codex-review-template.md)。
