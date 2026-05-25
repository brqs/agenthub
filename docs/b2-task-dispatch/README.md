# B2 子任务分发记录

本目录记录 B2 Agent 集成方向中，Codex 拆解后交给 Claude Code 执行的具体子任务。

## 协作方式

- Codex 负责总览、拆解、协调、边界检查和最终代码审阅。
- Claude Code 负责按任务文档执行具体实现和测试。
- Git/PR Claude 负责 Git 状态整理、commit、push 和 PR 准备。
- B2 负责人根据任务文档调度 Claude Code，并将执行结果交回 Codex 审阅。

Git/PR 操作规范见 [../git-pr-ops/README.md](../git-pr-ops/README.md)。

B2 总体目标框架和后续任务路线图见 [B2-roadmap.md](B2-roadmap.md)。

## 本地 Python 环境

B2 本地开发使用 Anaconda 环境 `LLMAgent`。Claude Code 执行 Python 任务前应优先复用该环境，不要重复创建或安装新的 Python 环境。

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
| B2-02 | 实现 ClaudeAdapter 真实 Anthropic 流式接入 | 已审阅，待 Git/PR | [B2-02-claude-adapter-streaming.md](B2-02-claude-adapter-streaming.md) |

## 模板

通用分发模板见 [../b2-ai-task-dispatch-template.md](../b2-ai-task-dispatch-template.md)。
