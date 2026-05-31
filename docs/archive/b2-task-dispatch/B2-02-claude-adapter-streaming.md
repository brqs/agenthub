# B2-02 — 实现 ClaudeAdapter 真实 Anthropic 流式接入

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-02
任务名称：实现 ClaudeAdapter 真实 Anthropic 流式接入

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目中 B2 方向的具体子任务。
Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现和测试，不要做无关重构。

项目背景：
AgentHub 后端 Agent 层通过 BaseAgentAdapter 输出统一 StreamChunk。
B1 的 SSE 端点只消费 StreamChunk，不直接感知 Anthropic/OpenAI 等具体 Provider。
B2-01 已实现 StreamingArtifactParser，可把 LLM 文本流中的 Markdown fenced code block 拆成 text/code block。

当前问题：
backend/app/agents/adapters/claude.py 仍是 stub，无法真实调用 Anthropic Claude，也没有接入 StreamingArtifactParser。
本任务要把 Claude 上游流式文本转换为 AgentHub 标准 StreamChunk，并复用 B2-01 parser。

请先阅读：
1. AGENTS.md
2. docs/b2/ai-task-dispatch-template.md
3. docs/b2/task-dispatch/B2-01-streaming-artifact-parser.md
4. backend/app/agents/base.py
5. backend/app/agents/types.py
6. backend/app/agents/artifact_parser.py
7. backend/app/agents/adapters/claude.py
8. backend/app/agents/adapters/mock.py
9. backend/app/core/config.py
10. backend/app/api/v1/stream.py

允许修改：
- backend/app/agents/adapters/claude.py
- backend/tests/test_claude_adapter.py

如果 backend/tests/test_claude_adapter.py 不存在，请新建。

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/artifact_parser.py
- backend/app/agents/registry.py
- backend/app/agents/adapters/openai.py
- backend/app/agents/adapters/custom.py
- backend/app/agents/orchestrator.py
- backend/app/api/v1/**
- backend/app/models/**
- backend/app/schemas/**
- shared/openapi.yaml
- docker-compose.yml
- AGENTS.md
- frontend/**

本任务不应修改 OpenAPI、BaseAgentAdapter.stream() 签名或 ContentBlock schema。

实现目标：
实现 ClaudeAdapter，使它能够：
1. 使用 anthropic.AsyncAnthropic 创建异步客户端。
2. 调用 Anthropic Messages API 的流式接口。
3. 将上游 text delta 交给 StreamingArtifactParser.feed()。
4. 将 parser 输出的 StreamChunk 原样 yield 给 B1 SSE 层。
5. 流结束时调用 parser.flush() 并 yield done。
6. 对缺少 API Key、RateLimitError、APIError 输出标准 error StreamChunk。

核心行为：

1. 正常流式输出顺序
   - 首先 yield StreamChunk(event_type="start", agent_id=self.agent_id)
   - 上游每次返回文本片段时：
     - 调用 parser.feed(text)
     - 逐个 yield parser 返回的 block_start/delta/block_end
   - 上游结束后：
     - 调用 parser.flush()
     - 逐个 yield flush 返回的剩余 block
     - 最后 yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=<实际 block 数>)

2. 配置合并
   - 使用 self.merged_config(config) 合并默认配置和本次调用配置。
   - model 从合并后的 config["model"] 获取。
   - temperature 从 config["temperature"] 获取，默认 0.7。
   - max_tokens 从 config["max_tokens"] 获取，默认 4096。
   - system prompt 使用 self.effective_system_prompt(system_prompt)。
   - 如果 ChatMessage 中包含 role="system"，不要放入 Anthropic messages，应合并到 system prompt 文本中。

3. Anthropic 客户端
   - 从 app.core.config.settings.anthropic_api_key 读取 API Key。
   - 如果 settings.anthropic_base_url 非空，创建客户端时传入 base_url。
   - 不要在代码中写死任何 API Key。
   - 不要读取 .env 文件内容。
   - 建议增加私有方法 _create_client()，方便单元测试 monkeypatch。

4. Anthropic messages 转换
   - 输入是 list[ChatMessage]。
   - Anthropic messages 只能包含 role="user" 或 role="assistant"。
   - 每条消息转换为 {"role": <role>, "content": <content>}。
   - 跳过空 content。
   - 保持原始顺序。
   - 不要把 role="system" 放进 messages。

5. 产物解析
   - 必须使用 StreamingArtifactParser。
   - 不要在 ClaudeAdapter 中重新实现 fenced code block 解析。
   - parser 产生的 code block metadata.language 应继续传给 StreamChunk。
   - fence 被拆分到多个上游 text delta 时，也应依赖 parser 正确处理。

6. 错误处理
   - 如果缺少 settings.anthropic_api_key：
     - yield start
     - yield StreamChunk(event_type="error", agent_id=self.agent_id, error_code="missing_api_key", error=<清晰错误信息>)
     - 不要创建真实客户端，不要发起网络请求。
   - anthropic.RateLimitError：
     - yield StreamChunk(event_type="error", agent_id=self.agent_id, error_code="rate_limit", error=str(exc))
   - anthropic.APIError：
     - yield StreamChunk(event_type="error", agent_id=self.agent_id, error_code="upstream_error", error=str(exc))
   - 不要用裸 except 吞掉所有异常；非 Anthropic 预期异常可以继续抛出，让 B1 SSE 层统一处理 internal_error。

实现约束：
- 不修改 BaseAgentAdapter.stream() 签名。
- Adapter 内不访问数据库。
- 不引入新的第三方依赖。
- 不修改共享契约文件。
- 保持 async/await，不使用同步阻塞 I/O。
- 不要实现 OpenAIAdapter、CustomAdapter 或 Orchestrator。
- 不要提交真实 API Key、token、.env 或本地 IDE 配置。
- 不要为了测试去调用真实 Anthropic API；测试必须使用 fake/mock client。

测试要求：
请新增 backend/tests/test_claude_adapter.py，至少覆盖：

1. test_stream_plain_text
   - fake Anthropic stream 返回若干 text delta。
   - 断言事件顺序包含 start、block_start、delta、block_end、done。
   - 断言 text_delta 拼接后等于预期文本。
   - 不发生真实网络请求。

2. test_stream_code_block_uses_artifact_parser
   - fake 上游返回包含 ```python fenced code block 的文本。
   - 断言输出包含 code block。
   - 断言 code block metadata.language == "python"。
   - 断言 code_delta 包含代码内容。

3. test_stream_split_fence_across_deltas
   - fake 上游分片返回 opening fence 和 closing fence，例如 "``" + "`python\n"。
   - 断言没有任何 text_delta/code_delta 泄漏 ```。
   - 断言 block 类型和内容正确。

4. test_missing_api_key_yields_error
   - monkeypatch settings.anthropic_api_key 为空。
   - 断言输出 start 后有 error。
   - 断言 error_code == "missing_api_key"。
   - 断言没有创建真实客户端。

5. test_rate_limit_yields_error
   - fake client 在流式调用时抛 anthropic.RateLimitError，或用 monkeypatch 模拟同类异常路径。
   - 断言 error_code == "rate_limit"。

6. test_api_error_yields_upstream_error
   - fake client 在流式调用时抛 anthropic.APIError，或用 monkeypatch 模拟同类异常路径。
   - 断言 error_code == "upstream_error"。

7. test_system_messages_are_merged_into_system_prompt
   - 输入 messages 中包含 role="system"。
   - 断言传给 Anthropic 的 messages 不包含 system role。
   - 断言 system prompt 包含 system message 内容。

测试实现建议：
- 不要依赖真实 anthropic 服务。
- 可以为 ClaudeAdapter._create_client() monkeypatch 一个 fake client。
- fake client 只需要模拟当前实现实际使用到的方法和 async context manager。
- 测试中可写 helper 收集 async generator 输出：
  async def collect(adapter.stream(...)) -> list[StreamChunk]
- 如 anthropic 异常类构造复杂，可优先 monkeypatch adapter 内部捕获路径所需的异常类，或用 pytest 明确构造最小可用异常对象。

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_claude_adapter.py
conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py tests/test_claude_adapter.py
conda run -n LLMAgent ruff check app/agents/adapters/claude.py tests/test_claude_adapter.py
conda run -n LLMAgent mypy app/agents/adapters/claude.py

如果已经激活 `LLMAgent` 环境，也可以执行对应的 python -m pytest / ruff / mypy 命令。

完成后交付说明必须包含：
1. 修改了哪些文件
2. ClaudeAdapter 如何创建 Anthropic client
3. ChatMessage 如何转换为 Anthropic messages/system prompt
4. StreamingArtifactParser 如何接入流式 delta
5. 错误码如何映射
6. 运行了哪些验证命令
7. 测试是否通过
8. 是否存在未覆盖边界或后续风险

注意：
本任务完成后不要 commit，不要 push，不要创建 PR。
请先把 diff 和测试结果交给 Codex 做最终代码审阅。
```
