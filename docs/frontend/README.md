# AgentHub 前端文档索引

> 这里只放前端相关文档。前端 Spec 收在 [docs/frontend/spec/](spec/)。
> Owner：F。涉及契约（OpenAPI / ContentBlock）变更时同步 B1 / B2。
> 最后更新：2026-06-03

---

## 文档清单

| 文档 | 类型 | 用途 | 状态 |
|---|---|---|---|
| [development-plan.md](development-plan.md) | Plan | 前端整体开发计划：Discord 式四栏布局、阶段拆分 | 🟡 阶段 0–6 已完成，阶段 7 Demo 打磨进行中 |
| [api-adapter-plan.md](api-adapter-plan.md) | Plan | 真实 API 接入前的 Adapter 层准备 | 🟢 Step 1–4 已完成，Step 5 等后端 |
| [test-plan.md](test-plan.md) | Plan | 测试补齐计划 | 🟡 第一批 P0 完成（19 用例），后续批次待补 |
| [demo-polish-v2-plan.md](demo-polish-v2-plan.md) | Plan | Demo 二轮打磨（多 Agent 协作感、Pin、Archive、主题等） | 🔴 未开始 |
| [deployment-release-handoff.md](deployment-release-handoff.md) | Handoff | Deployment / Release 状态卡、metadata 和远端发布交接 | 🟢 后端 E2E 已过，前端增强可选 |
| [agent-review-thread-handoff.md](agent-review-thread-handoff.md) | Handoff | Agent-to-Agent review / handoff / repair timeline 前端产品化交接 | 🟢 后端 E2E 已过，前端待产品化 |
| [rich-artifact-preview-handoff.md](rich-artifact-preview-handoff.md) | Handoff | Rich artifact card、manifest API、evaluation status 前端产品化交接 | 🟢 后端 E2E 已过，前端待产品化 |
| [changelog.md](changelog.md) | Log | 前端更新流水账 + 顶部"当前状态"总览 | — |
| [../spec/next-major-modules.spec.md](../spec/next-major-modules.spec.md) | Spec | 下一阶段三大前端模块：停止当前回复、跨端附件上传、无代码自定义 Agent 向导 | 🟡 Draft |

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
| [deployment-release-handoff](spec/deployment-release-handoff.spec.md) | Deployment / Release 状态卡与可选 metadata 展示 |
| [mobile-development](spec/frontend-mobile-development.spec.md) | 移动 Web、PWA 与 Capacitor 分阶段适配 |
| [capacitor-shell](spec/frontend-capacitor-shell.spec.md) | Capacitor v8 iOS / Android 壳层、HTTPS 构建约束与原生桥接 |
| [macos-tauri-shell](spec/frontend-macos-tauri-shell.spec.md) | macOS Tauri 桌面套壳、打包签名、Shell 适配与验收 |
| [file-upload](spec/frontend-file-upload.spec.md) | Web / iOS / Android 文件上传、附件队列、AttachmentBlock 和 Workspace 导入 UX |
| [windows-desktop-client](spec/windows-desktop-client.spec.md) | Windows 桌面客户端网页套壳、运行环境复用和总体架构 |
| [windows-desktop-host-bridge](spec/windows-desktop-host-bridge.spec.md) | Tauri 原生桥接命令、安全边界、主机能力白名单 |
| [windows-desktop-implementation-plan](spec/windows-desktop-implementation-plan.md) | Windows 桌面客户端分阶段实施路线 |
| [windows-desktop-test-plan](spec/windows-desktop-test-plan.md) | Windows 桌面客户端测试、验收和安全回归计划 |

## 相关 Skill

| Skill | 何时使用 |
|---|---|
| [foreground-contrast-audit](../ai-skills/foreground-contrast-audit/SKILL.md) | 修改前景色、文本 token、深浅色主题可读性或逐组件对比度验收时使用 |

## 下一阶段前端职责

- 打断对话：当前会话 streaming 时将发送按钮切换为 stop，展示 `interrupted` 终态，不把用户打断渲染成错误/重试。
- 文件上传：实现桌面拖拽/粘贴/文件选择、移动端选择器、上传队列、附件预览、Workspace 显式导入确认。
- 深度自定义 Agent：提供面向非代码用户的向导式创建体验，隐藏 JSON/YAML 细节，把角色、功能、知识、skills、MCP、权限和测试发布组织成可理解步骤。

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
## 2026-06-07 Conversation Interrupt UI Contract

- The current conversation input switches from Send to Stop while there is an active stream.
- Stop calls `POST /api/v1/messages/{msg_id}/interrupt` exactly once per click and shows a disabled stopping state while the request is in flight.
- The textarea remains editable during streaming. With text, Enter submits a queued next turn; with no text, the primary control remains Stop.
- Hydrated or streamed `interrupted` messages clear local active stream state, render a neutral `已打断` label, preserve partial content, and never show retry/error styling.
- Background streams in other conversations continue unless their own message is explicitly interrupted.

## 2026-06-07 Queued Next Turn UI Contract

- While the current conversation is streaming, typing text changes the primary action to "send to queue" instead of Stop.
- Stop remains available as a separate control while there is queued text, and remains the primary control when the input is empty.
- Queued user bubbles render with a neutral `排队中` state and small edit/delete controls.
- Terminal stream events with `queued_next` replace the queued user bubble with the dispatched user message, append the next pending agent message, and start streaming it.
- A queued message is the next turn, not an instruction injected into the active agent's current reasoning.
- Queues are conversation-scoped; queueing in one conversation must not disturb active streams in another conversation.

## 2026-06-08 需求对齐 UI Contract

- The input toolbar exposes a `需求对齐` switch. It defaults to off and is remembered per conversation in local UI storage.
- Normal send, queued send, and stop-and-run draft submit carry the current `requirement_alignment` turn option.
- When the switch is off, the frontend must not imply that Orchestrator will ask clarification questions.
- Queued user bubbles show a small `需求对齐` label only when their persisted `turn_options.requirement_alignment` is `strict`.
- Editing a queued message lets the user change the same turn option before dispatch.
- Clarification cards with `mode=requirement_alignment` render as `Orchestrator 需求对齐`; answer chips only fill the input and never auto-submit.

## 2026-06-07 Conversation Control Plane UI Contract

- While streaming with text in the input, the primary action remains "send to queue".
- A secondary active-turn menu exposes explicit controls: guide current reply, side question, and stop current reply then run this draft.
- Guidance creates a visible `turn_control` card with states such as waiting for safe point, applied, expired, or failed. It is not shown as an error/retry state.
- Side chat is rendered as compact visible status Q&A and must not look like a new main task response.
- Queued user bubbles expose edit/delete plus advanced actions: convert to guidance and stop current reply then run this queued message.
- Frontend state must treat `turn_control` SSE events as status updates for an existing control block. Refresh/hydrate should recover the same state from persisted message content.
- None of these controls should affect active streams in other conversations.
