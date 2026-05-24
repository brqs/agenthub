# AgentHub Frontend

React + Vite + TypeScript + Tailwind + shadcn/ui.

## 启动

```bash
cd frontend
pnpm install
pnpm dev      # → http://localhost:5173
```

需先启动后端（`docker compose up -d`）。

## 从 OpenAPI 生成 TS 类型

```bash
pnpm gen:types
```

会覆盖 `src/lib/types.ts`。**任何 API 契约变更后必须重跑**。

## 测试 / Lint / 类型检查

```bash
pnpm test
pnpm lint
pnpm tsc --noEmit
```

## 目录约定

```
src/
├── lib/           API 客户端、SSE 客户端、生成的类型
├── stores/        Zustand 全局状态
├── hooks/         业务 Hook（useStream 等）
├── pages/         页面组件
├── components/
│   ├── layout/    AppLayout、Sidebar、AuthGuard
│   ├── chat/      聊天界面
│   ├── blocks/    富媒体消息块（每种 ContentBlock 一个组件）
│   ├── agents/    Agent UI
│   ├── conversation/  会话列表
│   └── ui/        shadcn/ui 生成的组件
└── styles/        全局 CSS
```

## 跨平台预留

- **Tauri 桌面**：`pnpm tauri init`，包装 `dist/`
- **Capacitor 移动**：`pnpm capacitor init`，包装 `dist/`
- **PWA**：用 `vite-plugin-pwa`
