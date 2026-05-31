# B2-03 — 实现 OpenAIAdapter 真实 OpenAI 流式接入

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-03
任务名称：实现 OpenAIAdapter 真实 OpenAI 流式接入

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目中 B2 方向的具体子任务。
Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现和测试，不要做无关重构。

项目背景：
AgentHub 后端 Agent 层通过 BaseAgentAdapter 输出统一 StreamChunk。
B1 的 SSE 端点只消费 StreamChunk，不直接感知 Anthropic/OpenAI 等具体 Provider。
B2-01 已实现 StreamingArtifactParser。
B2-02 已实现 ClaudeAdapter，并形成了 Provider Adapter 的参考实现和测试结构。

当前问题：
backend/app/agents/adapters/openai.py 仍是 stub，无法真实调用 OpenAI，也没有接入 StreamingArtifactParser。
本任务要把 OpenAI Chat Completions 上游流式文本转换为 AgentHub 标准 StreamChunk，并复用 B2-01 parser。

本地环境参考：
- Python 环境：Anaconda `LLMAgent`
- 本地已检查 openai SDK：`openai 2.31.0`
- 当前项目 seed 中 OpenAI 内置 Agent 默认模型为 `gpt-4o`

请先阅读：
1. AGENTS.md
2. docs/b2/task-dispatch/B2-roadmap.md
3. docs/b2/task-dispatch/B2-01-streaming-artifact-parser.md
4. docs/b2/task-dispatch/B2-02-claude-adapter-streaming.md
5. backend/app/agents/base.py
6. backend/app/agents/types.py
7. backend/app/agents/artifact_parser.py
8. backend/app/agents/adapters/claude.py
9. backend/app/agents/adapters/openai.py
10. backend/app/core/config.py
11. backend/app/api/v1/stream.py

允许修改：
- backend/app/agents/adapters/openai.py
- backend/tests/test_openai_adapter.py

如果 backend/tests/test_openai_adapter.py 不存在，请新建。

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/artifact_parser.py
- backend/app/agents/registry.py
- backend/app/agents/adapters/claude.py
- backend/app/agents/adapters/custom.py
- backend/app/agents/orchestrator.py
- backend/app/api/v1/**
- backend/app/models/**
- backend/app/schemas/**
- shared/openapi.yaml
- docker-compose.yml
- AGENTS.md
- frontend/**
- docs/**

本任务不应修改 OpenAPI、BaseAgentAdapter.stream() 签名或 ContentBlock schema。

实现目标：
实现 OpenAIAdapter，使它能够：
1. 使用 openai.AsyncOpenAI 创建异步客户端。
2. 调用 OpenAI Chat Completions 的 stream=True 流式接口。
3. 从 choices[0].delta.content 读取文本增量。
4. 将上游 text delta 交给 StreamingArtifactParser.feed()。
5. 将 parser 输出的 StreamChunk 原样 yield 给 B1 SSE 层。
6. 流结束时调用 parser.flush() 并 yield done。
7. 对缺少 API Key、RateLimitError、APIError 输出标准 error StreamChunk。

核心行为：

1. 正常流式输出顺序
   - 首先 yield StreamChunk(event_type="start", agent_id=self.agent_id)
   - 上游每次返回文本片段时：
     - 读取 chunk.choices[0].delta.content
     - content 为空或 None 时跳过
     - 调用 parser.feed(content)
     - 逐个 yield parser 返回的 block_start/delta/block_end
   - 上游结束后：
     - 调用 parser.flush()
     - 逐个 yield flush 返回的剩余 block
     - 最后 yield StreamChunk(event_type="done", agent_id=self.agent_id, total_blocks=<实际 block 数>)

2. 配置合并
   - 使用 self.merged_config(config) 合并默认配置和本次调用配置。
   - model 从合并后的 config["model"] 获取；为空或缺失时默认 `gpt-4o`。
   - temperature 从 config["temperature"] 获取；缺失或为 None 时默认 0.7。
   - max_tokens 从 config["max_tokens"] 获取；缺失或为 None 时默认 4096。
   - temperature=0 是合法值，不能被错误替换成 0.7。
   - system prompt 使用 self.effective_system_prompt(system_prompt)。

3. OpenAI 客户端
   - 从 app.core.config.settings.openai_api_key 读取 API Key。
   - 如果 settings.openai_base_url 非空，创建客户端时传入 base_url。
   - 不要在代码中写死任何 API Key。
   - 不要读取 .env 文件内容。
   - 建议增加私有方法 _create_client()，方便单元测试 monkeypatch。

4. ChatMessage 转换
   - 输入是 list[ChatMessage]。
   - OpenAI Chat Completions messages 支持 system/user/assistant。
   - 将 effective system prompt 和输入 messages 中的 role="system" 内容合并为一个 system message，放在 messages 最前面。
   - 后续只追加 role="user" 或 role="assistant" 且 content 非空的消息。
   - 保持 user/assistant 原始顺序。
   - 每条消息格式为 {"role": <role>, "content": <content>}。

5. 产物解析
   - 必须使用 StreamingArtifactParser。
   - 不要在 OpenAIAdapter 中重新实现 fenced code block 解析。
   - parser 产生的 code block metadata.language 应继续传给 StreamChunk。
   - fence 被拆分到多个 OpenAI delta 时，也应依赖 parser 正确处理。

6. 错误处理
   - 如果缺少 settings.openai_api_key：
     - yield start
     - yield StreamChunk(event_type="error", agent_id=self.agent_id, error_code="missing_api_key", error=<清晰错误信息>)
     - 不要创建真实客户端，不要发起网络请求。
   - openai.RateLimitError：
     - yield StreamChunk(event_type="error", agent_id=self.agent_id, error_code="rate_limit", error=str(exc))
   - openai.APIError：
     - yield StreamChunk(event_type="error", agent_id=self.agent_id, error_code="upstream_error", error=str(exc))
   - 不要用裸 except 吞掉所有异常；非 OpenAI 预期异常可以继续抛出，让 B1 SSE 层统一处理 internal_error。

实现约束：
- 不修改 BaseAgentAdapter.stream() 签名。
- Adapter 内不访问数据库。
- 不引入新的第三方依赖。
- 不修改共享契约文件。
- 保持 async/await，不使用同步阻塞 I/O。
- 不要实现 ClaudeAdapter、CustomAdapter 或 Orchestrator。
- 不要提交真实 API Key、token、.env 或本地 IDE 配置。
- 不要为了测试去调用真实 OpenAI API；测试必须使用 fake/mock client。

测试要求：
请新增 backend/tests/test_openai_adapter.py，至少覆盖：

1. test_stream_plain_text
   - fake OpenAI stream 返回若干 choices[0].delta.content。
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

4. test_skips_empty_delta_content
   - fake stream 中包含 delta.content 为 None 或空字符串的 chunk。
   - 断言不会产生空 delta，也不会破坏最终输出。

5. test_missing_api_key_yields_error
   - monkeypatch settings.openai_api_key 为空。
   - 断言输出 start 后有 error。
   - 断言 error_code == "missing_api_key"。
   - 断言没有创建真实客户端。

6. test_rate_limit_yields_error
   - fake client 在流式调用时抛 openai.RateLimitError，或用 monkeypatch 模拟同类异常路径。
   - 断言 error_code == "rate_limit"。

7. test_api_error_yields_upstream_error
   - fake client 在流式调用时抛 openai.APIError，或用 monkeypatch 模拟同类异常路径。
   - 断言 error_code == "upstream_error"。

8. test_system_messages_are_merged_into_system_prompt
   - 输入 messages 中包含 role="system"。
   - 同时传入 system_prompt。
   - 断言传给 OpenAI 的 messages 第一条是 system。
   - 断言 system content 包含 system_prompt 和输入 system message 内容。
   - 断言后续 user/assistant 顺序保持。

9. test_empty_config_uses_defaults
   - config={}。
   - 断言传给 fake client 的 model == "gpt-4o"。
   - 断言 temperature == 0.7。
   - 断言 max_tokens == 4096。

10. test_temperature_none_fallback
    - config={"temperature": None}。
    - 断言 temperature == 0.7。

11. test_temperature_zero_preserved
    - config={"temperature": 0}。
    - 断言 temperature == 0。

12. test_max_tokens_none_fallback
    - config={"max_tokens": None}。
    - 断言 max_tokens == 4096。

测试实现建议：
- 不要依赖真实 OpenAI 服务。
- 可以为 OpenAIAdapter._create_client() monkeypatch 一个 fake client。
- fake client 只需要模拟当前实现实际使用到的方法：
  - client.chat.completions.create(..., stream=True)
  - 返回一个 async iterator
- fake stream chunk 可以用简单对象模拟：
  - choices[0].delta.content
- 测试中可写 helper 收集 async generator 输出：
  async def collect(adapter.stream(...)) -> list[StreamChunk]
- 如 OpenAI 异常类构造复杂，可优先 monkeypatch adapter 内部捕获路径所需的异常类，或用 pytest 明确构造最小可用异常对象。

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_openai_adapter.py
conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py tests/test_claude_adapter.py tests/test_openai_adapter.py
conda run -n LLMAgent ruff check app/agents/adapters/openai.py tests/test_openai_adapter.py
conda run -n LLMAgent mypy app/agents/adapters/openai.py

如果已经激活 `LLMAgent` 环境，也可以执行对应的 python -m pytest / ruff / mypy 命令。

完成后交付说明必须包含：
1. 修改了哪些文件
2. OpenAIAdapter 如何创建 OpenAI client
3. ChatMessage 如何转换为 OpenAI messages/system prompt
4. StreamingArtifactParser 如何接入 OpenAI delta
5. 错误码如何映射
6. 运行了哪些验证命令
7. 测试是否通过
8. 是否存在未覆盖边界或后续风险

注意：
本任务完成后不要 commit，不要 push，不要创建 PR。
请先把 diff 和测试结果交给 Codex 做最终代码审阅。
```
