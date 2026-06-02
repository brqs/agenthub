# AgentHub 前端文档索引

> 这里只放前端相关文档。前端 Spec 收在 [docs/frontend/spec/](spec/)。
> Owner：F。涉及契约（OpenAPI / ContentBlock）变更时同步 B1 / B2。
> 最后更新：2026-06-01

---

## 文档清单

| 文档 | 类型 | 用途 | 状态 |
|---|---|---|---|
| [development-plan.md](development-plan.md) | Plan | 前端整体开发计划：Discord 式四栏布局、阶段拆分 | 🟡 阶段 0–6 已完成，阶段 7 Demo 打磨进行中 |
| [api-adapter-plan.md](api-adapter-plan.md) | Plan | 真实 API 接入前的 Adapter 层准备 | 🟢 Step 1–4 已完成，Step 5 等后端 |
| [test-plan.md](test-plan.md) | Plan | 测试补齐计划 | 🟡 第一批 P0 完成（19 用例），后续批次待补 |
| [demo-polish-v2-plan.md](demo-polish-v2-plan.md) | Plan | Demo 二轮打磨（多 Agent 协作感、Pin、Archive、主题等） | 🔴 未开始 |
| [changelog.md](changelog.md) | Log | 前端更新流水账 + 顶部"当前状态"总览 | — |

---

## 相关 Spec

| Spec | 覆盖范围 |
|---|---|
| [chat-demo](spec/frontend-chat-demo.spec.md) | Mock 多 Agent 协作流 |
| [content-blocks](spec/frontend-content-blocks.spec.md) | 富媒体消息块 |
| [agent-management](spec/frontend-agent-management.spec.md) | Agent 管理页 |
| [demo-polish](spec/frontend-demo-polish.spec.md) | Demo 体验状态打磨 |
| [theme-auto-optimization](spec/frontend-theme-auto-optimization.spec.md) | 深色 / 浅色主题可读性优化 |
| [orchestrated-message-rendering](spec/orchestrated-message-rendering.spec.md) | 多 Agent 消息拆分渲染 |
| [mobile-development](spec/frontend-mobile-development.spec.md) | 移动 Web、PWA 与 Capacitor 分阶段适配 |
| [capacitor-shell](spec/frontend-capacitor-shell.spec.md) | Capacitor v8 iOS / Android 壳层、HTTPS 构建约束与原生桥接 |

---

## 项目级文档（前端读什么）

| 文档 | 何时读 |
|---|---|
| [../../CLAUDE.md](../../CLAUDE.md) | 项目宪法，每次开工先扫 |
| [../development-plan.md](../development-plan.md) | 看项目整体方向 / 时间线 |
| [../team-division.md](../team-division.md) | F 的任务清单 + 文件所有权矩阵 |
| [../api-spec.md](../api-spec.md) | 人类可读的 API 文档 |
| [../product-design.md](../product-design.md) | UI / 交互参考 |
| `../../shared/openapi.yaml` | API 契约真相源（线上后端 `/openapi.json` 现在也作为类型生成来源） |

---

## 入门动线（新到这个项目的同学）

1. 读 [../../CLAUDE.md](../../CLAUDE.md)（项目宪法）
2. 读本 README + [development-plan.md](development-plan.md)（前端落地方案）
3. 看 [changelog.md](changelog.md) 顶部"当前状态"了解到哪了
4. 看 [api-adapter-plan.md](api-adapter-plan.md) 理解 Mock / 真后端切换边界
5. 起前端：`cd frontend && pnpm dev`（详见 [frontend/README.md](../../frontend/README.md)）
