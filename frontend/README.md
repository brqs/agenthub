# AgentHub Frontend

React + Vite + TypeScript + Tailwind + shadcn/ui.

## 启动

```bash
cd frontend
pnpm install
pnpm dev      # → http://localhost:5173
```

默认走 Mock 模式，**无需后端**即可演示。要接真后端：

```bash
cp .env.example .env.local
# .env.local 中设置 VITE_USE_MOCK_API=false（VITE_API_BASE_URL 留空走 Vite 代理）
pnpm dev
```

或本地启后端：`docker compose up -d`，然后在 `.env.local` 把 `VITE_DEV_PROXY_TARGET` 改成 `http://localhost:8000`。

## 从 OpenAPI 生成 TS 类型

```bash
pnpm gen:types
```

会从 `../shared/openapi.yaml` 覆盖 `src/lib/types.gen.ts`（生成代码，不要手改）。`src/lib/types.ts` 是手维护的友好别名层，导入这一个即可。**契约变更后必须重跑**。

## 测试 / Lint / 类型检查

```bash
pnpm test
pnpm lint
pnpm tsc --noEmit
```

## macOS 桌面壳（Tauri）

桌面端复用同一份 React/Vite 产物，Tauri 只负责窗口、bundle 和系统外链打开。

```bash
# 开发模式：需要本机安装 Rust 工具链
VITE_API_BASE_URL=http://127.0.0.1:8000 \
VITE_ALLOW_INSECURE_DESKTOP_API=true \
pnpm tauri:dev

# 打包模式：生产必须使用 HTTPS 后端
VITE_API_BASE_URL=https://api.example.com pnpm tauri:build
```

如果本机没有 `rustc` / `cargo`，请先安装 Rust 后再运行 `tauri:dev` 或 `tauri:build`。详细方案见 [../docs/frontend/spec/frontend-macos-tauri-shell.spec.md](../docs/frontend/spec/frontend-macos-tauri-shell.spec.md)。

## 目录约定

```
src/
├── lib/
│   ├── api.ts          axios 实例 + JWT 拦截器
│   ├── env.ts          集中读 VITE_USE_MOCK_API / VITE_API_BASE_URL
│   ├── adapters/       REST 端点的 typed 包装（auth / conversations / messages / agents）
│   ├── sse.ts          SSE 订阅（Mock/Real 分支）
│   ├── types.ts        友好别名（手维护）
│   ├── types.gen.ts    由 openapi-typescript 自动生成（不要手改）
│   └── mockData.ts     Mock 模式的会话/消息/Agent 种子
├── stores/        Zustand 全局状态（auth/chat/agent）
├── hooks/         业务 Hook（Mock/API 双模式分支）
├── pages/         LoginPage / ChatPage / AgentsPage
├── components/
│   ├── layout/    AppLayout / ModuleRail / AuthGuard
│   ├── chat/      聊天界面
│   ├── blocks/    富媒体消息块（每种 ContentBlock 一个组件）
│   ├── agents/    Agent UI
│   └── conversation/  会话列表
└── styles/        全局 CSS
```

更多设计细节见 [../docs/frontend/](../docs/frontend/)。

## 跨平台预留

- **Tauri 桌面**：`src-tauri/` 包装 `dist/`
- **Capacitor 移动**：`pnpm capacitor init`，包装 `dist/`
- **PWA**：用 `vite-plugin-pwa`
