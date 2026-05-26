# Frontend Agent Management Spec

## 目标

完成桌面 Demo 中的 Agent 管理页，让用户可以浏览内置 Agent、自建 Mock Agent、查看详情并创建新的 Demo Agent。

## 输入 / 输出

输入：

- Mock Agent 列表。
- 用户在搜索框输入 Agent 名称、Provider 或能力标签。
- 用户通过创建表单输入名称、Provider、模型、能力标签和 System Prompt。

输出：

- Agent 管理页按“我的 Agent / 内置 Agent”分组展示。
- 右侧详情栏展示 Agent 能力、运行配置、接入状态和 System Prompt。
- 新建 Agent 会写入前端 Mock store，并立即出现在“我的 Agent”分组中。

## 边界 / 错误处理

- 当前阶段不修改 `shared/openapi.yaml`。
- 当前创建流程仅为 Mock，不持久化到后端。
- Agent 名称为空时不创建。
- 创建 Agent 的 id 由前端基于名称生成，重复时自动加后缀。

## 性能要求

- 搜索与分组使用本地状态和 memo，保证 Demo 列表即时响应。
- 详情栏固定在右侧，避免切换 Agent 时主列表明显跳动。

## 依赖

- `frontend/src/stores/agentStore.ts`
- `frontend/src/hooks/useAgents.ts`
- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/components/agents/AgentCard.tsx`
- `frontend/src/components/agents/AgentCreateDialog.tsx`
- `frontend/src/components/agents/AgentDetailPanel.tsx`

## 验收标准

- 可以从模块栏进入 Agent 管理页。
- 可以搜索 Agent，并看到空状态。
- 可以创建一个自建 Agent。
- 创建后 Agent 出现在“我的 Agent”分组，并自动进入详情态。
- `tsc`、`eslint`、`vite build` 通过。
