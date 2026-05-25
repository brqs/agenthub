# Agent Config Validation Spec

## 目标

为 AgentHub 的 Agent 创建、更新和内置 seed 数据建立统一配置校验规则，避免无效模型、缺失 custom upstream、错误温度参数等问题进入数据库。

本 Spec 服务于 B2-05，重点约束 `provider`、`system_prompt` 和 `config` 三者之间的关系。

## 输入 / 输出

输入来源：

- `POST /api/v1/agents` 的 `CreateAgentRequest`
- `PATCH /api/v1/agents/{id}` 的 `UpdateAgentRequest`
- `backend/app/seeds/seed_agents.py` 中的 `BUILTIN_AGENTS`

核心输入字段：

- `provider`: `claude` / `openai` / `custom`
- `system_prompt`: custom agent 的行为提示词
- `config.model`: 上游模型名
- `config.temperature`: 采样温度，允许 `0`
- `config.max_tokens`: 最大输出 token 数
- `config.top_p`: nucleus sampling 参数
- `config.upstream_provider`: custom agent 的真实上游 Provider，取值 `claude` / `openai`

输出：

- 通过校验时返回规范化后的 `config` 副本。
- 校验失败时 API 返回统一 `422` 错误结构。

## 校验规则

### 通用规则

- `config` 必须是 object。
- `config.model` 在创建时必须是非空字符串。
- `config.temperature` 如果存在且非 `None`，必须在 `0 <= temperature <= 2`，且 `0` 必须保留为合法值。
- `config.max_tokens` 如果存在且非 `None`，必须在 `1 <= max_tokens <= 16384`。
- `config.top_p` 如果存在且非 `None`，必须在 `0 <= top_p <= 1`。
- 校验函数不能修改传入的原始 `config`。

### Provider 模型规则

MVP 阶段先维护项目内显式支持的模型白名单，不动态访问真实上游 API：

- `claude`: `claude-sonnet-4-6`
- `openai`: `gpt-4o`

后续新增模型时，只扩展白名单和 seed，不改 Adapter 基类契约。

### Custom Agent 规则

- `provider == "custom"` 时，`system_prompt` 必须是非空字符串。
- `config.upstream_provider` 必须是 `claude` 或 `openai`。
- `config.upstream_provider` 大小写不敏感，规范化为小写。
- `config.model` 必须属于 upstream provider 支持的模型。
- `config.upstream_provider` 只对 custom agent 有意义，普通 `claude` / `openai` agent 不应携带该字段。

## PATCH 合并规则

`PATCH /api/v1/agents/{id}` 中的 `config` 是局部更新，不是整体替换。

示例：

```json
{"config": {"temperature": 0.5}}
```

应当在后端合并为：

```python
merged_config = {**agent.config, **payload.config}
```

然后对合并后的配置做完整校验，避免把已有 `model` 或 `upstream_provider` 意外清空。

## 边界 / 错误处理

API 层应将配置校验错误映射为：

```json
{
  "error": {
    "code": "INVALID_MODEL",
    "message": "Unsupported model 'xxx' for provider 'claude'",
    "details": {
      "provider": "claude",
      "model": "xxx"
    }
  }
}
```

推荐错误码：

- `INVALID_PROVIDER`
- `INVALID_AGENT_CONFIG`
- `INVALID_MODEL`
- `INVALID_UPSTREAM_PROVIDER`
- `MISSING_SYSTEM_PROMPT`

## 依赖

- `backend/app/schemas/agent.py`
- `backend/app/api/v1/agents.py`
- `backend/app/seeds/seed_agents.py`
- `backend/app/agents/adapters/claude.py`
- `backend/app/agents/adapters/openai.py`
- `backend/app/agents/adapters/custom.py`
- `shared/openapi.yaml`
- `docs/api-spec.md`

## 验收标准

- 创建 Agent 时，无效 model / upstream_provider / numeric config 会返回 422。
- custom agent 缺少有效 system_prompt 会返回 422。
- 更新 Agent 时，`config` 局部合并，不覆盖已有完整配置。
- 内置 `BUILTIN_AGENTS` 全部通过同一套校验规则。
- OpenAPI 和 `docs/api-spec.md` 显式记录 `config.upstream_provider`。
- 不修改 `BaseAgentAdapter.stream()` 签名。
- 不修改数据库模型或 migration。
