# B2-05 — Agent 配置校验与内置 Agent 配置对齐

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-05
任务名称：Agent 配置校验与内置 Agent 配置对齐

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目中 B2 方向的具体子任务。
Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现、测试和必要契约文档更新，不要做无关重构。

项目背景：
AgentHub 已完成：
- B2-01 StreamingArtifactParser
- B2-02 ClaudeAdapter
- B2-03 OpenAIAdapter
- B2-04 CustomAdapter 委托 Claude/OpenAI 上游 Provider

当前 Agent CRUD 已存在，但 `backend/app/api/v1/agents.py` 仍有 TODO：
`# TODO(B2): validate provider + model`

现在需要补齐 Agent 创建/更新时的配置校验，并让内置 seed agent 的 config 与这套规则保持一致。

当前问题：
1. `CreateAgentRequest.config` 当前几乎可以传任意 dict，无 provider/model/upstream 校验。
2. `UpdateAgentRequest.config` 当前会整体替换 `agent.config`，例如 PATCH `{"config": {"temperature": 0.5}}` 会丢失原有 `model`。
3. custom agent 依赖 `config.upstream_provider`，但 OpenAPI 和 API 文档没有显式说明。
4. 内置 custom agents 的 config 与最终校验规则需要对齐。

请先阅读：
1. AGENTS.md
2. docs/b2/spec/agent-config-validation.spec.md
3. docs/b2/task-dispatch/B2-roadmap.md
4. docs/b2/task-dispatch/B2-04-custom-adapter-delegation.md
5. backend/app/agents/base.py
6. backend/app/agents/adapters/claude.py
7. backend/app/agents/adapters/openai.py
8. backend/app/agents/adapters/custom.py
9. backend/app/agents/registry.py
10. backend/app/schemas/agent.py
11. backend/app/api/v1/agents.py
12. backend/app/models/agent.py
13. backend/app/seeds/seed_agents.py
14. shared/openapi.yaml
15. docs/api-spec.md

允许修改：
- backend/app/agents/config_validation.py
- backend/app/api/v1/agents.py
- backend/app/schemas/agent.py
- backend/app/seeds/seed_agents.py
- backend/tests/test_agent_config_validation.py
- shared/openapi.yaml
- docs/api-spec.md

如果 `backend/app/agents/config_validation.py` 或 `backend/tests/test_agent_config_validation.py` 不存在，请新建。

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/artifact_parser.py
- backend/app/agents/adapters/claude.py
- backend/app/agents/adapters/openai.py
- backend/app/agents/adapters/custom.py
- backend/app/agents/orchestrator.py
- backend/app/models/**
- backend/app/services/**
- backend/app/api/v1/stream.py
- backend/app/api/v1/messages.py
- backend/app/api/v1/conversations.py
- backend/alembic/**
- docker-compose.yml
- AGENTS.md
- frontend/**

本任务允许更新 AgentConfig 相关 OpenAPI/API 文档，但不允许修改 BaseAgentAdapter.stream()、ContentBlock schema 或 SSE 事件契约。

契约变更说明：
本任务需要在 `shared/openapi.yaml` 的 `AgentConfig` 中显式补充可选字段 `upstream_provider`，并在 `docs/api-spec.md` 中说明 custom agent 的配置规则。
这是 Agent API 配置字段的文档化和校验补齐，不新增 API 路径，不改变 ContentBlock。
PR 描述中必须标注「契约变更：AgentConfig 增加 upstream_provider 说明」。

实现目标：
1. 建立 B2-owned 的 Agent config 校验工具。
2. 创建 Agent 时校验 provider、model、system_prompt、upstream_provider 和 numeric config。
3. 更新 Agent 时对 config 做局部合并，再校验合并后的完整 config。
4. 内置 `BUILTIN_AGENTS` 使用同一套规则校验，避免 seed 与运行时规则漂移。
5. OpenAPI/API 文档显式记录 custom agent 的 `upstream_provider`。
6. 增加单元测试覆盖核心配置边界。

核心行为：

1. 新增配置校验模块
   推荐新增：
   - backend/app/agents/config_validation.py

   建议包含：
   - SUPPORTED_PROVIDER_MODELS
   - SUPPORTED_UPSTREAM_PROVIDERS
   - AgentConfigValidationError
   - validate_agent_config(...)
   - merge_agent_config(...)

   MVP 阶段模型白名单至少包含当前代码和 seed 使用的模型：
   - claude: claude-sonnet-4-6
   - openai: gpt-4o

   不要动态访问真实 Claude/OpenAI API 获取模型列表。

2. 校验函数行为
   推荐函数签名：

   def validate_agent_config(
       *,
       provider: str,
       config: dict[str, Any],
       system_prompt: str | None,
   ) -> dict[str, Any]:
       ...

   要求：
   - 返回规范化后的 config 副本，不修改传入对象。
   - provider 必须是 claude/openai/custom。
   - config 必须是 dict/object。
   - model 必须是非空字符串。
   - model 必须属于有效 provider 支持的模型。
   - temperature 如果存在且非 None，必须是 0 到 2，temperature=0 必须合法。
   - max_tokens 如果存在且非 None，必须是 1 到 16384。
   - top_p 如果存在且非 None，必须是 0 到 1。
   - provider 为 claude/openai 时，不允许携带 upstream_provider。
   - provider 为 custom 时，必须有非空 system_prompt。
   - provider 为 custom 时，必须有 upstream_provider，且只能是 claude/openai。
   - custom 的 model 应按 upstream_provider 校验，例如 upstream_provider=openai 时 model 必须属于 openai 模型白名单。
   - upstream_provider 大小写不敏感，返回值中规范化为小写。

3. 错误类型
   建议定义：

   class AgentConfigValidationError(ValueError):
       def __init__(
           self,
           code: str,
           message: str,
           details: dict[str, Any] | None = None,
       ) -> None:
           ...

   API 层捕获后返回：
   - HTTP 422
   - detail={"error": {"code": exc.code, "message": exc.message, "details": exc.details}}

   推荐错误码：
   - INVALID_PROVIDER
   - INVALID_AGENT_CONFIG
   - INVALID_MODEL
   - INVALID_UPSTREAM_PROVIDER
   - MISSING_SYSTEM_PROMPT

4. create_agent 接入
   在 `backend/app/api/v1/agents.py` 的 `create_agent` 中：
   - 调用 validate_agent_config。
   - 将返回的 normalized_config 写入 Agent.config。
   - 不要直接写入未经校验的 payload.config。
   - 不要访问 LLM 上游 API。
   - 不要改变认证和 DB session 依赖。

5. update_agent 接入
   当前 `update_agent` 对 payload 字段直接 setattr。
   本任务需要专门处理 config：
   - 如果 payload.config 未提供，不改 agent.config。
   - 如果 payload.config 已提供，先与现有 agent.config 做浅合并：
     merged_config = {**agent.config, **payload.config}
   - 使用更新后的 effective system_prompt 做完整校验。
   - 校验通过后写入 merged_config。
   - 其他字段保持当前更新逻辑。

   注意：
   - PATCH `{"config": {"temperature": 0.5}}` 应保留已有 model/upstream_provider。
   - PATCH custom agent 的 system_prompt 为 None 或空字符串时，应被拒绝。
   - 仍然禁止修改内置 Agent。

6. schemas/agent.py 对齐
   `AgentConfig` 应显式包含：
   - model
   - temperature
   - max_tokens
   - top_p
   - upstream_provider

   `upstream_provider` 类型应限制为 claude/openai 或 None。
   保持 extra="allow"，便于后续 provider 扩展字段。

   可以补齐 UpdateAgentRequest 的基础 Field 约束：
   - name: 1-64
   - system_prompt: max_length=8192
   - capabilities: 最多 10 项

   不要引入会破坏现有 API 的大规模 schema 重构。

7. seed_agents.py 对齐
   - 所有内置 Agent 的 config 必须通过 validate_agent_config。
   - custom 内置 Agent 必须显式包含 upstream_provider。
   - 建议 custom 内置 Agent 也显式包含 temperature 和 max_tokens，避免默认值分散。
   - seed() 插入前可调用 validate_agent_config；校验失败应直接抛错，避免写入错误 seed。
   - 不要修改 Agent SQLAlchemy model 或 migration。

8. OpenAPI / API 文档同步
   在 `shared/openapi.yaml`：
   - AgentConfig.properties 增加 upstream_provider。
   - upstream_provider enum: [claude, openai]。
   - 可加 description 说明仅 custom agent 使用。

   在 `docs/api-spec.md`：
   - POST /api/v1/agents 示例中 custom config 增加 upstream_provider。
   - 字段约束中说明 custom 必须提供 system_prompt 和 config.upstream_provider。
   - PATCH 说明 config 是局部合并，不是整体替换。
   - 错误码列表补充 INVALID_UPSTREAM_PROVIDER、MISSING_SYSTEM_PROMPT、INVALID_AGENT_CONFIG。

实现约束：
- 不修改 BaseAgentAdapter.stream() 签名。
- 不修改 Adapter 流式逻辑。
- 不访问真实上游 LLM API。
- 不修改数据库模型和 migration。
- 不引入新的第三方依赖。
- 不修改 ContentBlock schema。
- 不修改前端代码。
- 保持 async route 逻辑，不使用同步阻塞 I/O。
- 不提交真实 API Key、token、.env 或本地 IDE 配置。

测试要求：
请新增 `backend/tests/test_agent_config_validation.py`，至少覆盖：

1. test_valid_claude_config
   - provider=claude
   - config={"model": "claude-sonnet-4-6", "temperature": 0.7, "max_tokens": 4096}
   - 校验通过。

2. test_valid_openai_config
   - provider=openai
   - config={"model": "gpt-4o", "temperature": 0.7, "max_tokens": 4096}
   - 校验通过。

3. test_custom_config_requires_system_prompt
   - provider=custom
   - system_prompt=None 或 ""
   - 抛 MISSING_SYSTEM_PROMPT。

4. test_custom_config_requires_upstream_provider
   - provider=custom
   - config 缺少 upstream_provider
   - 抛 INVALID_UPSTREAM_PROVIDER。

5. test_custom_config_accepts_claude_upstream
   - provider=custom
   - upstream_provider=claude
   - model=claude-sonnet-4-6
   - 校验通过。

6. test_custom_config_accepts_openai_upstream
   - provider=custom
   - upstream_provider=openai
   - model=gpt-4o
   - 校验通过。

7. test_custom_model_validated_against_upstream
   - provider=custom
   - upstream_provider=openai
   - model=claude-sonnet-4-6
   - 抛 INVALID_MODEL。

8. test_upstream_provider_case_insensitive_and_normalized
   - upstream_provider=OpenAI
   - 返回 config["upstream_provider"] == "openai"。

9. test_direct_provider_rejects_upstream_provider
   - provider=claude 或 openai
   - config 带 upstream_provider
   - 抛 INVALID_AGENT_CONFIG。

10. test_missing_model_rejected
    - model 缺失、None 或空字符串
    - 抛 INVALID_MODEL。

11. test_temperature_zero_is_allowed
    - temperature=0
    - 校验通过且返回值保留 0。

12. test_temperature_out_of_range_rejected
    - temperature=-0.1 或 2.1
    - 抛 INVALID_AGENT_CONFIG。

13. test_max_tokens_out_of_range_rejected
    - max_tokens=0 或 20000
    - 抛 INVALID_AGENT_CONFIG。

14. test_top_p_out_of_range_rejected
    - top_p=-0.1 或 1.1
    - 抛 INVALID_AGENT_CONFIG。

15. test_validation_does_not_mutate_input_config
    - 传入 config 后校验
    - 断言原 dict 未被修改。

16. test_merge_agent_config_preserves_existing_model
    - existing={"model": "claude-sonnet-4-6", "temperature": 0.7}
    - patch={"temperature": 0.5}
    - 断言合并后 model 保留、temperature 更新。

17. test_builtin_agents_pass_validation
    - 遍历 BUILTIN_AGENTS
    - 对每个 seed 调用 validate_agent_config
    - 全部通过。

如果为 API 层错误映射新增了小 helper，也请覆盖：
- AgentConfigValidationError 能映射出预期 code/message/details。

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_agent_config_validation.py
conda run -n LLMAgent python -m pytest
conda run -n LLMAgent ruff check app/agents/config_validation.py app/api/v1/agents.py app/schemas/agent.py app/seeds/seed_agents.py tests/test_agent_config_validation.py
conda run -n LLMAgent mypy app/agents/config_validation.py app/api/v1/agents.py app/schemas/agent.py app/seeds/seed_agents.py

如果已经激活 `LLMAgent` 环境，也可以执行对应的 python -m pytest / ruff / mypy 命令。

完成后交付说明必须包含：
1. 修改了哪些文件
2. Agent config 校验规则如何实现
3. create_agent 如何接入校验
4. update_agent 如何合并并校验 config
5. custom agent 的 upstream_provider/model/system_prompt 如何校验
6. seed 内置 Agent 如何对齐
7. OpenAPI/API 文档更新了什么
8. 运行了哪些验证命令
9. 测试是否通过
10. 是否存在未覆盖边界或后续风险

注意：
本任务完成后不要 commit，不要 push，不要创建 PR。
请先把 diff 和测试结果交给 Codex 做最终代码审阅。
```
