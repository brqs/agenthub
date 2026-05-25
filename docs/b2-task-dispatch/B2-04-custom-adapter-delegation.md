# B2-04 — 实现 CustomAdapter 委托上游 Provider

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-04
任务名称：实现 CustomAdapter 委托上游 Provider

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目中 B2 方向的具体子任务。
Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现和测试，不要做无关重构。

项目背景：
AgentHub 的 custom agent 不是新的 LLM Provider，而是“用户自定义 System Prompt + 上游 Provider”的包装层。
B2-02 已实现 ClaudeAdapter。
B2-03 已实现 OpenAIAdapter。
本任务要让 CustomAdapter 根据配置选择上游 Adapter，并把上游 StreamChunk 原样转发给 B1 SSE 层。

当前问题：
backend/app/agents/adapters/custom.py 仍是 stub，只返回固定文本。
它需要根据 `config["upstream_provider"]` 委托给 ClaudeAdapter 或 OpenAIAdapter，并注入 custom agent 的 system_prompt。

请先阅读：
1. AGENTS.md
2. docs/b2-task-dispatch/B2-roadmap.md
3. docs/b2-task-dispatch/B2-02-claude-adapter-streaming.md
4. docs/b2-task-dispatch/B2-03-openai-adapter-streaming.md
5. backend/app/agents/base.py
6. backend/app/agents/types.py
7. backend/app/agents/adapters/claude.py
8. backend/app/agents/adapters/openai.py
9. backend/app/agents/adapters/custom.py
10. backend/app/agents/registry.py
11. backend/app/seeds/seed_agents.py

允许修改：
- backend/app/agents/adapters/custom.py
- backend/tests/test_custom_adapter.py

如果 backend/tests/test_custom_adapter.py 不存在，请新建。

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/artifact_parser.py
- backend/app/agents/registry.py
- backend/app/agents/adapters/claude.py
- backend/app/agents/adapters/openai.py
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
实现 CustomAdapter，使它能够：
1. 从合并后的 config 中读取 `upstream_provider`。
2. `upstream_provider` 缺失、为空或 None 时默认使用 `claude`。
3. 支持 `claude` 和 `openai` 两个上游 Provider。
4. 根据上游 Provider 实例化 ClaudeAdapter 或 OpenAIAdapter。
5. 将 custom agent 的 system_prompt 注入上游 Adapter。
6. 将其余 config 传给上游 Adapter，但不要把 `upstream_provider` 继续传下去。
7. 原样转发上游 Adapter 产生的 StreamChunk。
8. 对不支持的 upstream_provider 输出标准 error StreamChunk。

核心行为：

1. 配置合并
   - 使用 self.merged_config(config) 合并 default_config 和本次调用 config。
   - per-call config 应覆盖 default_config。
   - 从合并后配置中取出 `upstream_provider`。
   - `upstream_provider` 应大小写不敏感，建议统一 `.lower()`。
   - 传给上游 Adapter 的 config 不应包含 `upstream_provider`。

2. 上游选择
   - upstream_provider == "claude" -> 委托 ClaudeAdapter。
   - upstream_provider == "openai" -> 委托 OpenAIAdapter。
   - upstream_provider 缺失 / "" / None -> 默认 "claude"。
   - 其他值 -> 不实例化上游 Adapter，直接 yield：
     - StreamChunk(event_type="start", agent_id=self.agent_id)
     - StreamChunk(event_type="error", agent_id=self.agent_id, error_code="unsupported_upstream_provider", error=<清晰错误信息>)

3. System Prompt 注入
   - 使用 self.effective_system_prompt(system_prompt) 得到最终 system prompt。
   - 如果调用方传入 system_prompt，调用方传入值优先。
   - 否则使用 CustomAdapter 初始化时的 self.system_prompt。
   - 将该最终 system prompt 传给上游 Adapter。
   - 不要把 system prompt 拼到用户 message content 里。

4. 上游 Adapter 实例化
   推荐模式：
   - upstream_adapter = adapter_cls(
       agent_id=self.agent_id,
       system_prompt=effective_system_prompt,
       default_config=upstream_config,
     )
   - 然后调用 upstream_adapter.stream(messages, system_prompt=effective_system_prompt, config=None)

   注意：
   - agent_id 应继续使用 custom agent 的 self.agent_id，这样 SSE 前端看到的仍是当前 custom agent。
   - 不要访问数据库。
   - 不要调用 registry.get_adapter()，避免 DB 依赖和 custom 递归。

5. StreamChunk 转发
   - 对支持的上游 Provider，CustomAdapter 不应自己再 yield start/done。
   - 直接 async for chunk in upstream_adapter.stream(...): yield chunk。
   - 不要修改 block_index。
   - 不要重新解析 text/code。
   - 不要吞掉上游 error chunk。

实现约束：
- 不修改 BaseAgentAdapter.stream() 签名。
- Adapter 内不访问数据库。
- 不引入新的第三方依赖。
- 不修改共享契约文件。
- 保持 async/await，不使用同步阻塞 I/O。
- 不要实现 ClaudeAdapter、OpenAIAdapter 或 Orchestrator。
- 不要提交真实 API Key、token、.env 或本地 IDE 配置。
- 测试必须使用 fake/mock upstream adapter，不调用真实 Claude/OpenAI API。

测试要求：
请新增 backend/tests/test_custom_adapter.py，至少覆盖：

1. test_defaults_to_claude
   - CustomAdapter default_config 不含 upstream_provider。
   - monkeypatch 上游 adapter map，让 "claude" 指向 FakeUpstreamAdapter。
   - 断言委托给 claude。

2. test_delegates_to_openai
   - config={"upstream_provider": "openai"}。
   - 断言委托给 openai。

3. test_per_call_config_overrides_default_config
   - default_config={"upstream_provider": "claude"}。
   - stream(..., config={"upstream_provider": "openai"})。
   - 断言最终委托 openai。

4. test_upstream_provider_is_not_forwarded
   - config 包含 upstream_provider、model、temperature、max_tokens。
   - 断言传给 FakeUpstreamAdapter 的 default_config 或 stream config 不包含 upstream_provider。
   - 断言 model/temperature/max_tokens 保留。

5. test_system_prompt_injected
   - CustomAdapter(system_prompt="custom prompt")。
   - 断言 FakeUpstreamAdapter 收到 system_prompt。

6. test_system_prompt_override_wins
   - CustomAdapter(system_prompt="default prompt")。
   - stream(..., system_prompt="override prompt")。
   - 断言上游收到 override prompt，不是 default prompt。

7. test_messages_are_forwarded_unchanged
   - 传入 user/assistant messages。
   - 断言上游收到同一个 messages 列表内容。

8. test_chunks_are_forwarded_unchanged
   - FakeUpstreamAdapter 产生 start/block_start/delta/block_end/done。
   - 断言 CustomAdapter 输出事件顺序和字段一致。

9. test_upstream_error_chunk_is_forwarded
   - FakeUpstreamAdapter 产生 start/error。
   - 断言 CustomAdapter 不吞 error。

10. test_unsupported_upstream_provider_yields_error
    - config={"upstream_provider": "bad-provider"}。
    - 断言输出 start 后 error。
    - 断言 error_code == "unsupported_upstream_provider"。
    - 断言没有实例化任何上游 Fake Adapter。

11. test_upstream_provider_case_insensitive
    - config={"upstream_provider": "OpenAI"}。
    - 断言委托 openai。

测试实现建议：
- 不要依赖真实 Claude/OpenAI 服务。
- 可以在 custom.py 中定义模块级 UPSTREAM_ADAPTERS 映射，并在测试中 monkeypatch。
- FakeUpstreamAdapter 可以继承 BaseAgentAdapter，也可以只实现兼容构造参数和 stream 方法。
- FakeUpstreamAdapter 应记录：
  - agent_id
  - system_prompt
  - default_config
  - stream 调用收到的 messages/system_prompt/config
  - 是否被实例化
- 测试中可写 helper 收集 async generator 输出：
  async def collect(adapter.stream(...)) -> list[StreamChunk]

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_custom_adapter.py
conda run -n LLMAgent python -m pytest tests/test_claude_adapter.py tests/test_openai_adapter.py tests/test_custom_adapter.py
conda run -n LLMAgent python -m pytest
conda run -n LLMAgent ruff check app/agents/adapters/custom.py tests/test_custom_adapter.py
conda run -n LLMAgent mypy app/agents/adapters/custom.py

如果已经激活 `LLMAgent` 环境，也可以执行对应的 python -m pytest / ruff / mypy 命令。

完成后交付说明必须包含：
1. 修改了哪些文件
2. CustomAdapter 如何选择上游 Provider
3. system_prompt 如何注入上游 Adapter
4. config 如何过滤 upstream_provider 并继续传递模型参数
5. StreamChunk 如何转发
6. 错误码如何映射
7. 运行了哪些验证命令
8. 测试是否通过
9. 是否存在未覆盖边界或后续风险

注意：
本任务完成后不要 commit，不要 push，不要创建 PR。
请先把 diff 和测试结果交给 Codex 做最终代码审阅。
```
