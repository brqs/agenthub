# External Runtime Lifecycle Spec

## 目标

统一 external runtime 的运行生命周期：预算、心跳、取消、进程清理、SDK stream 清理、诊断日志和错误码。适用对象：

- `claude-code`
- `codex-helper`
- `opencode-helper`

本 Spec 是 runtime lifecycle 的唯一事实来源。Provider-specific 启动和事件映射见 [external-runtime-adapters.spec.md](external-runtime-adapters.spec.md)。

## 运行预算

所有 external runtime 使用同一组配置：

| 键 | 类型 | 范围 | 默认值 | 说明 |
|---|---:|---:|---:|---|
| `max_runtime_seconds` | float | `1..3600` | `600` | 绝对最长运行时间 |
| `idle_timeout_seconds` | float | `1..3600` | `180`，Codex `240` | 无活动多久视为卡死 |
| `heartbeat_interval_seconds` | float | `1..3600` | `15` | 等待期间 heartbeat 间隔 |
| `timeout_seconds` | float | `1..3600` | `120` | 兼容旧字段，映射到 `max_runtime_seconds` |

优先级：

- `max_runtime_seconds` 优先于 `timeout_seconds`。
- `idle_timeout_seconds <= max_runtime_seconds` 必须由 config validation 保证。

## 活动信号

以下事件会刷新 `last_activity_at`：

- SDK stream event。
- CLI stdout/stderr 字节。
- OpenCode JSONL event。
- tool event。
- Codex `-o` 输出文件 mtime/size 变化。
- 子进程正常退出。

单纯等待不算活动。

## Heartbeat

等待 SDK/CLI 下一条事件期间，adapter 必须按间隔输出：

```python
StreamChunk(
    event_type="heartbeat",
    metadata={
        "elapsed_seconds": ...,
        "idle_seconds": ...,
        "max_runtime_seconds": ...,
        "idle_timeout_seconds": ...,
    },
)
```

约束：

- heartbeat 通过 SSE 透传。
- heartbeat 不进入 `message.content`。
- heartbeat 不代表任务成功，也不应被 Orchestrator 计作 artifact 产出。

## Timeout 语义

| error_code | 触发 |
|---|---|
| `runtime_idle_timeout` | 无活动持续超过 `idle_timeout_seconds` |
| `runtime_hard_timeout` | 总运行时间超过 `max_runtime_seconds` |

timeout 时必须先清理 runtime，再返回 error chunk。Codex 特例：

- 如果 timeout 时 `-o` 输出文件非空，可以按成功返回 `done`。
- 如果输出文件为空，返回对应 timeout error。

## CLI 生命周期

统一 CLI runner 必须：

1. 使用 workspace 作为 `cwd`。
2. 创建进程组。
3. 并发读取 stdout/stderr。
4. 用 bounded buffer 保存尾部诊断输出。
5. 在等待输出、等待进程退出、等待文件变化期间检查 budget。
6. timeout/cancel/error 时 terminate process group。
7. grace period 后仍未退出则 kill process group。
8. drain stdout/stderr reader tasks。
9. 清理临时输出文件。

不得在各 adapter 中分散实现裸 `asyncio.wait_for(process.communicate())`。

## SDK 生命周期

SDK runtime 不得使用会永久阻塞 heartbeat 的裸 `async for`。

推荐模式：

- 对 `iterator.__anext__()` 创建 task。
- `asyncio.wait()` 同时等待 next event、heartbeat deadline、runtime deadline、cancel signal。
- 取消时 cancel pending next task。
- 如果 SDK 提供 close/cancel API，必须调用。
- cleanup 必须幂等。

## Cancellation

取消来源：

| 来源 | 行为 |
|---|---|
| 客户端断开 SSE | 停止读取 adapter stream，关闭 async iterator，清理 runtime |
| 服务端 shutdown | 取消当前 run，清理 runtime |
| runtime timeout | 清理 runtime，返回 timeout error |
| adapter 主动失败 | 清理 runtime，返回 error |

当前不新增数据库 message status。MVP 状态规则：

- 正常完成：`done`
- error / timeout / cancel：`error`
- client disconnect error_code：`runtime_cancelled`

标准 cancellation chunk：

```python
StreamChunk(
    event_type="error",
    error_code="runtime_cancelled",
    error="Agent runtime was cancelled because the client disconnected.",
    metadata={"reason": "client_disconnected"},
)
```

如果 SSE 已断开，该 chunk 只用于落库和日志。

## B1 SSE 责任

`_event_generator` 应：

- 使用 `contextlib.aclosing()` 或等价机制关闭 adapter async iterator。
- 检测到 `request.is_disconnected()` 后停止继续消费 chunk。
- partial content 可以保留。
- message status 标记为 `error`。
- DB commit 需要避免被 cancel scope 中断后留下 `streaming`。

## Orchestrator 责任

- 子 agent heartbeat 可以透传。
- 子 agent timeout/error 按 Orchestrator fallback 处理。
- 全局 cancellation 时停止后续子任务。
- cancellation 不应写入成功 summary。

## 诊断与脱敏

必须记录但不得泄露：

- provider、agent_id、conversation_id、message_id。
- exit code。
- timeout 类型。
- stdout/stderr 尾部摘要。
- 最后活动时间。

必须脱敏：

- API key。
- Bearer token。
- Authorization header。
- 完整 env。
- `.env`、`secrets/`、`.ssh/` 内容。

## 测试计划

- 静默子进程触发 idle timeout。
- 持续 stderr 输出不触发 idle timeout，但受 hard timeout 限制。
- SDK 等待期间持续 heartbeat。
- client disconnect 后 message 最终不是永久 `streaming`。
- timeout/cancel 后无残留子进程。
- Codex timeout 且输出文件非空时成功。
- heartbeat 不进入 `message.content`。
- diagnostics redaction 覆盖 token/API key。

## 验收标准

- 三个 external runtimes 使用同一 lifecycle 机制。
- 复杂任务不会被旧 120 秒硬超时误杀。
- 卡死任务会被 idle timeout 终止。
- SSE 断开不会留下长期运行的 SDK/CLI。
- 所有 timeout/cancel/error 都有可诊断但脱敏的日志。
