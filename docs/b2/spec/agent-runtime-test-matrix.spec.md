# Agent Runtime Test Matrix Spec

## 目标

统一 B2 测试矩阵，替代 legacy-only adapter smoke 文档，并把分散在各 runtime spec 中的测试要求收敛到一个入口。

## 测试分层

| 层级 | 默认 CI | 说明 |
|---|---|---|
| Unit | yes | adapter helper、parser、budget、config validation |
| Integration | yes | fake SDK/CLI、B1 accumulator、registry |
| API/SSE | yes | pending/streaming/done/error、heartbeat、disconnect |
| Slow live smoke | no | 真实 Claude/Codex/OpenCode/ModelGateway，手动开启 |
| Remote smoke | no | 部署环境端到端验证 |

## 默认测试要求

默认 `pytest` 必须：

- 不访问真实网络。
- 不依赖真实 API key。
- 不启动长驻 preview/deploy server。
- 不监听 8082。
- 不打印 secret/env。

## 共享 StreamChunk 断言

所有 adapter smoke 必须断言：

- 第一个对外事件是 `start`。
- 最终事件是 `done` 或 `error`。
- 如果最终是 `done`，不应出现 `error`。
- `block_start` / `block_end` 成对匹配。
- `delta.block_index` 指向已打开 block。
- `done.total_blocks` 等于输出 block 数。
- 所有 chunk 都能 `to_sse()`。
- B1 `_ContentAccumulator.feed(chunk)` 不抛异常。
- `heartbeat` 不进入最终 `message.content`。

## ModelGateway

覆盖：

- Claude/OpenAI/DeepSeek fake stream 输出普通文本。
- setup timeout / connection error / rate limit / missing key。
- 内容输出后异常不重试。
- ToolSpec 映射。
- direct chat 跳过内部 `start`。

## External Runtime

覆盖：

- Claude SDK 等待期间 heartbeat。
- Claude CLI fallback 使用统一 lifecycle cleanup。
- Codex stdout/stderr 刷新 activity。
- Codex `-o` 输出文件非空时 timeout 仍可成功。
- OpenCode JSONL running 不提前生成成功 `tool_result`。
- timeout/cancel 后无残留子进程。
- preview/deploy 命令被过滤或替换。

## Direct Chat Routing

覆盖：

- 普通问答不启动 SDK/CLI。
- 身份问题走本地 shortcut，不调用分类器。
- artifact 请求进入 runtime。
- 分类器 invalid JSON / low confidence fallback runtime。
- direct chat 模型 error 不 fallback runtime。

## Workspace Artifact / Preview

覆盖：

- `snake.html` 被识别为 previewable artifact。
- artifact manifest 不进入 message content。
- preview API 分配平台端口。
- agent runtime 不监听 8082。
- 删除 conversation 清理 preview session。

## Orchestrator

覆盖：

- planner 不规划 preview/deploy server。
- 子 agent heartbeat 透传。
- 子 agent error 转 summary，不让主流程卡住。
- `artifact_missing` 触发 fallback。
- fallback 成功后 summary 包含 artifact 路径。
- 所有 attempts 失败时 Orchestrator `done` 并说明失败。

## Slow Live Smoke

必须使用 marker：

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests that call live external providers or are too slow for default runs",
]
```

手动开启：

```bash
AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1 python -m pytest -m slow -q
```

要求：

- key 缺失时 skip，不 fail。
- prompt 极短。
- max tokens 较小。
- 不断言具体模型文案，只断言协议和 artifact 是否存在。

## Remote Smoke

部署环境至少覆盖：

- `claude-code` 生成 `snake.html` 并 `done`。
- `codex-helper` 生成 `snake.html` 并 `done`。
- `opencode-helper` 生成 `snake.html` 并 `done`。
- 三者都不启动或建议 preview/deploy server。
- 8082 无 agent runtime 监听。
- 平台 preview service 可以单独管理 8082。
- Orchestrator 子 agent 失败后 summary `done`，artifact fallback 生效。

## 验收标准

- 默认 CI 覆盖协议和资源清理，不访问真实 provider。
- slow smoke 可手动验证真实 runtime。
- remote smoke 能覆盖“生成 artifact + 平台 preview 边界”。
- 测试矩阵不再以 legacy raw adapter 为主视角。
