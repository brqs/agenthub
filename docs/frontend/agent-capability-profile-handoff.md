# Agent Capability Profile v1 前端交接说明

> 用途：同步 B2 Agent Capability Profile v1 的只读 API 契约与后续前端工作边界。
>
> 状态：后端 API、OpenAPI 与公网 E2E 已通过，前端可以开始消费。

## 当前后端能力

- 新增只读 API：`GET /api/v1/conversations/{conversation_id}/agent-capability-profile`。
- API 仅返回当前用户拥有的当前 conversation 画像，不跨用户、不跨 workspace。
- response item 包含成功/失败、缺产物、evaluation failure、平均 attempts、artifact kinds、review outcomes、repair success、近期失败原因和 confidence。
- `shared/openapi.yaml` 已补齐路由、`AgentCapabilityProfileOut` 和 `AgentCapabilityProfileItemOut`。
- 公网 API/SSE E2E 已通过：
  - report：`/tmp/agenthub_p1_agent_capability_profile_report.json`
  - conversation：`8dd905aa-e51a-4f68-b869-2cc4c6278a3d`
  - report `passed=true`

## 本轮前端边界

- 本轮不修改前端 UI，也不新增画像展示入口。
- 后端契约已稳定到可消费状态；前端可开始重新生成类型并实现只读展示。
- 前端后续接入前需运行：

```bash
cd frontend
pnpm gen:types
```

- 类型重新生成后，建议在 conversation/run detail 的 debug 或诊断视图中先做只读展示，再决定是否产品化为 Agent 选择依据视图。
- v1 数据是当前 conversation 的近期经验摘要，不应展示为跨项目、跨用户的永久能力评级。

## 后续验收建议

- API 空画像时正常展示空态。
- 多 Agent 时能区分近期 success/failure、artifact kind、review/repair 表现。
- UI 文案明确画像是近期、conversation-scoped 的软参考。
- 不提供 mutation、手动改分或硬编码调度控制。
