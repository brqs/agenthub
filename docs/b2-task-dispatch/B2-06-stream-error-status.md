# B2-06 — SSE error 状态持久化协同修复

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-06
任务名称：SSE error 状态持久化协同修复

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目中 B2/B1 协同方向的具体子任务。
Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现和测试，不要做无关重构。

项目背景：
AgentHub 后端中，B2 Adapter 通过 `BaseAgentAdapter.stream()` 输出标准 `StreamChunk`。
B1 SSE 层在 `backend/app/api/v1/stream.py` 中消费这些 chunk，转发给前端，并最终持久化 `Message.content` 与 `Message.status`。

B2-02 到 B2-05 已完成：
- ClaudeAdapter / OpenAIAdapter / CustomAdapter 都可能 yield `StreamChunk(event_type="error")`。
- `backend/app/api/v1/stream.py` 当前已经有部分 error chunk 处理逻辑。
- 现有测试只覆盖了正常流 done 和缺失 agent 导致 error，还没有覆盖 Adapter 主动 yield error chunk 或 Adapter 中途抛异常后的持久化行为。

当前任务不是重新设计 SSE，而是补齐并验证错误路径，确保错误不会被误持久化为 done，且错误前已经生成的内容不会丢失。

请先阅读：
1. AGENTS.md
2. docs/spec/stream-error-status.spec.md
3. docs/b2-task-dispatch/B2-roadmap.md
4. backend/app/api/v1/stream.py
5. backend/app/agents/types.py
6. backend/app/agents/base.py
7. backend/app/agents/adapters/mock.py
8. backend/app/models/message.py
9. backend/app/schemas/message.py
10. backend/tests/test_b1_quality.py

允许修改：
- backend/app/api/v1/stream.py
- backend/tests/test_b1_quality.py

如确实需要独立测试文件，也可以新增：
- backend/tests/test_stream_error_status.py

允许同步更新：
- docs/ai-collaboration-log.md

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/adapters/**
- backend/app/api/v1/agents.py
- backend/app/api/v1/messages.py
- backend/app/api/v1/conversations.py
- backend/app/models/**
- backend/app/schemas/**
- shared/openapi.yaml
- frontend/**
- docker-compose.yml
- AGENTS.md

本任务不应修改 OpenAPI、BaseAgentAdapter.stream() 签名、StreamChunk schema 或 ContentBlock schema。

实现目标：
1. 明确并测试 Adapter yield `error` chunk 时，SSE 层会把 message.status 持久化为 `error`。
2. 明确并测试 Adapter 抛异常时，SSE 层会返回 `internal_error`，并把 message.status 持久化为 `error`。
3. 错误发生前已经累积出的 text/code block 必须保存到 message.content。
4. 正常流仍保持 `done`，既有成功路径不回归。
5. 不改变 Adapter 内部错误映射和流式解析逻辑。

核心行为：

1. Adapter error chunk
   当 `adapter.stream()` yield `StreamChunk(event_type="error", ...)`：
   - 先把该 error chunk `yield chunk.to_sse()` 给前端。
   - 将 `message.content = accumulator.to_list()`。
   - 将 `message.status = "error"`。
   - commit 后 return，停止继续消费 adapter。

2. Adapter 中途抛异常
   当 adapter 在已经 yield 部分 block 后抛出异常：
   - 捕获异常。
   - 将 `message.content = accumulator.to_list()`，保留已生成内容。
   - 将 `message.status = "error"`。
   - commit。
   - yield `StreamChunk(event_type="error", error_code="internal_error", error=str(e)).to_sse()`。

   注意：
   - 当前 `stream.py` 的 generic exception 分支可能只设置 status，不保存 accumulated content；请确认并修复。
   - 不要让异常逃逸成 HTTP 500。

3. AgentNotFoundError
   当 `get_adapter()` 抛 `AgentNotFoundError`：
   - status 必须是 `error`。
   - SSE error_code 必须是 `agent_not_found`。
   - content 可为空列表。
   - 保持既有行为，不要改成 HTTP 404。

4. missing agent_id
   当 agent message 没有 `agent_id`：
   - status 必须是 `error`。
   - SSE error_code 必须是 `missing_agent`。
   - content 可为空列表。

5. 客户端断开
   如果 `request.is_disconnected()` 返回 true：
   - 停止消费 adapter。
   - status 应为 `error`。
   - content 保存断开前已累积内容。
   - 本任务可以不新增断开连接集成测试，除非容易稳定模拟。

实现约束：
- 不修改 `BaseAgentAdapter.stream()` 签名。
- 不修改 `StreamChunk` 字段。
- 不修改 Adapter。
- 不修改数据库模型和 migration。
- 不引入第三方依赖。
- 不修改 OpenAPI。
- 只做最小必要改动，不重构整个 SSE 端点。

测试要求：
请在 `backend/tests/test_b1_quality.py` 或新建 `backend/tests/test_stream_error_status.py` 中覆盖：

1. test_stream_success_marks_agent_message_done
   - 保持既有成功路径。
   - 断言 SSE 包含 `event: done`。
   - 断言 message.status == "done"。
   - 断言 message.content 被持久化。

2. test_stream_missing_agent_marks_agent_message_error
   - 保持或补齐既有缺失 agent 测试。
   - 断言 SSE 包含 `event: error`。
   - 断言 message.status == "error"。

3. test_stream_adapter_error_chunk_marks_message_error
   - monkeypatch `app.api.v1.stream.get_adapter`，返回 fake adapter。
   - fake adapter 依次 yield：
     - start
     - block_start text
     - delta text_delta="partial"
     - error error_code="rate_limit"
   - 请求 SSE endpoint。
   - 断言响应 body 包含 `event: error` 和 `rate_limit`。
   - 断言 message.status == "error"。
   - 断言 message.content 至少包含 text block，内容包含 "partial"。

4. test_stream_adapter_exception_marks_message_error_and_preserves_partial_content
   - monkeypatch `app.api.v1.stream.get_adapter`，返回 fake adapter。
   - fake adapter yield start / block_start / delta 后 raise RuntimeError("boom")。
   - 请求 SSE endpoint。
   - 断言响应 body 包含 `event: error` 和 `internal_error`。
   - 断言 message.status == "error"。
   - 断言 message.content 保留异常前的 partial text。

测试实现建议：
- 复用 `test_b1_quality.py` 中已有 `_register`、`_insert_agent`、`_create_conversation`、`_send_message` helper。
- fake adapter 只需要实现 async `stream(self, messages)`，不需要继承真实 Adapter。
- monkeypatch 的目标应是 `app.api.v1.stream.get_adapter`，因为 `stream.py` 已经导入了该函数。
- 测试不要调用真实 Claude/OpenAI API。

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_b1_quality.py
conda run -n LLMAgent python -m pytest
conda run -n LLMAgent ruff check app/api/v1/stream.py tests/test_b1_quality.py
conda run -n LLMAgent mypy app/api/v1/stream.py

如果已经激活 `LLMAgent` 环境，也可以执行对应的 python -m pytest / ruff / mypy 命令。

注意：
`mypy app/api/v1/stream.py` 可能会被项目既有 B1 类型问题带失败。若失败，请区分是否为本任务新增问题，并在交付说明中如实说明。

完成后交付说明必须包含：
1. 修改了哪些文件
2. Adapter error chunk 如何处理
3. Adapter 抛异常时如何处理
4. partial content 是否会保存
5. message.status 如何变化
6. 运行了哪些验证命令
7. 测试是否通过
8. 是否存在未覆盖边界或后续风险

本任务完成后不要 commit，不要 push，不要创建 PR。
请先把 diff 和测试结果交给 Codex 做最终代码审阅。
```
