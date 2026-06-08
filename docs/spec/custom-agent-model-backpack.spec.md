# 自定义 Agent 模型背包规范

## Summary

模型背包让非技术用户用产品化语言配置自定义 Agent 的大模型：选择公司、输入 API Key、选择模型。后端负责把公司映射为具体 provider、协议、base URL 和调用客户端。

默认配置仍是 AgentHub 免费 DeepSeek：用户不填写 API Key 也可以创建并使用 `provider="builtin"` 的自定义 Agent。

## Public API

- `GET /api/v1/model-providers`
  - 返回 DeepSeek、OpenAI、Anthropic Claude、OpenAI 兼容接口。
  - 每项包含默认模型、推荐模型列表、协议类型和是否需要 `base_url`。

- `GET /api/v1/model-accounts`
  - 返回当前用户保存的模型账号。
  - 只返回 `api_key_preview`，不返回完整 API Key 或加密密文。

- `POST /api/v1/model-accounts`
  - 创建用户私有模型账号。
  - `openai_compatible` 必须填写 `base_url`。

- `PATCH /api/v1/model-accounts/{id}`
  - 修改显示名、模型、Base URL，或重新写入 API Key。

- `DELETE /api/v1/model-accounts/{id}`
  - 若有 Agent 正在引用该账号，返回 `409 MODEL_ACCOUNT_IN_USE`。

- `POST /api/v1/model-accounts/{id}/verify`
  - 轻量验证模型账号是否可用，写回 `ready` 或 `unavailable`。

## Agent Config Contract

Agent 配置只保存模型账号引用，不保存明文密钥：

```json
{
  "model_backend": "deepseek",
  "model_profile": {
    "source": "agenthub_default",
    "provider": "deepseek",
    "model": "deepseek-v4-flash"
  }
}
```

```json
{
  "model_backend": "openai",
  "model_profile": {
    "source": "user_account",
    "account_id": "00000000-0000-0000-0000-000000000000",
    "provider": "openai",
    "model": "gpt-5.4-mini"
  }
}
```

`Agent.config` 内禁止出现 `api_key`、`secret`、`access_token`、`authorization` 等内联凭据字段。

## Runtime

- AgentHub 免费 DeepSeek 继续使用后端全局环境配置。
- 用户模型账号以 `user_model_accounts` 存储，API Key 使用服务端密钥加密。
- `BuiltinAgentAdapter` 创建前由 registry 解析 `model_profile.account_id`，临时注入运行时密钥、base URL 和模型名。
- Claude Code / Codex / OpenCode 外部 runtime 不使用模型背包，继续走各自 CLI/SDK 认证契约。

## UX

- Agent Builder 默认选中“AgentHub 免费 DeepSeek”。
- 用户选择“使用我的 API”后，按“模型公司 -> API Key -> 模型”保存到背包。
- OpenAI 兼容接口才显示 Base URL。
- API Key 输入框是写入式，保存后只显示尾号 preview。
- Agent 详情页显示当前模型来源和模型名。
