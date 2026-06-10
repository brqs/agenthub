# Windows Desktop Client Implementation Plan

> Status: Draft implementation plan
> Last updated: 2026-06-09
> Scope: phased delivery plan for AgentHub Windows desktop client

## 1. Strategy

桌面客户端采用“先壳层连接，再本地服务管理，再安装器”的路线。

原因：

- 当前 Web 端已经承载主要产品体验；
- 后端 Docker stack 和 Agent runtime 已经存在；
- 直接做完整安装器会把 UI、runtime、DB、Docker、升级和权限问题同时引爆；
- Tauri 壳层可以先验证核心假设：同一套 React 是否能在 Windows 桌面中稳定使用。

## 2. Milestones

### P0: Documentation And Spike

目标：

- 明确架构、桥接边界、安全原则和测试计划；
- 验证 Tauri + Vite + React build 能跑起来；
- 不接入生产功能。

产出：

- `windows-desktop-client.spec.md`
- `windows-desktop-host-bridge.spec.md`
- `windows-desktop-implementation-plan.md`
- `windows-desktop-test-plan.md`
- 一个本地 spike 分支，可打开静态 Web dist。

Implementation note 2026-06-09:

- 已新增最小 Tauri v2 工程骨架：`frontend/src-tauri/`。
- 已新增开发命令：`pnpm desktop:dev`、`pnpm desktop:build`、`pnpm desktop:info`。
- P0 壳层只注册 `tauri::Builder::default()`，没有任何自定义 native command。
- P0 capability 只包含 `core:default`，没有 shell/fs/dialog/http/process/updater 插件权限。
- 当前 Windows 环境已通过 `winget install --id Rustlang.Rustup -e` 补齐 Rustup / stable MSVC toolchain；`rustc`、`cargo`、WebView2 和 MSVC 均已被 `pnpm desktop:info` 识别。
- 已从现有 PWA `public/icons/icon-512.png` 生成 Tauri 占位 icons，并显式配置 bundle icon 列表。
- `pnpm desktop:build` 已产出 Windows MSI 与 NSIS setup bundle。
- P0 不处理 backend CORS、本地 Docker stack 启动、Workspace 文件夹打开、通知、安装器和 runtime 可用性。

### P1: Shell Connects Existing Backend

目标：

- 桌面客户端加载现有 React UI；
- 用户手动启动后端后，桌面客户端正常登录、聊天、看 Workspace；
- 桌面客户端不管理 Docker。

前端任务：

- 增加 Tauri 工程骨架：
  - `frontend/src-tauri/tauri.conf.json`
  - `frontend/src-tauri/Cargo.toml`
  - `frontend/src-tauri/src/main.rs`
- 增加桌面检测 adapter：
  - `frontend/src/lib/desktopBridge.ts`
  - `frontend/src/hooks/useDesktopEnvironment.ts`
- 增加启动页：
  - backend health check；
  - backend URL 设置；
  - retry。
- 打包命令：
  - `pnpm desktop:dev`
  - `pnpm desktop:build`

B1/B2 任务：

- 保证 `GET /health` 或等价 health endpoint 足够轻量；
- health 里返回版本和基础依赖状态；
- 不为桌面单独开 API 分叉。

验收：

- 后端运行时，桌面客户端可完成登录、会话列表、发送消息、SSE、Workspace 展示。
- 后端未运行时，显示连接失败与重试，不白屏。

#### P1 Implementation Note

P1 在 P0 Tauri 壳层基础上补齐“连接现有后端”的最小闭环：

- React 入口通过 `AppRouter` 自动选择 Web `BrowserRouter` 或桌面 `HashRouter`；
- `desktopBridge` / `useDesktopEnvironment` 负责识别 Tauri、保存 `backendUrl`、执行 `/health` 探测；
- `DesktopBootstrapGate` 在桌面环境中先检查 `http://localhost:8000/health`，成功后才进入登录/聊天 UI；
- REST 与 SSE 共用 runtime API base URL，桌面启动页确认的地址会同时影响 axios 和 `fetchEventSource`；
- B1 `/health` 返回 `status/version/environment/dependencies`，默认 CORS 包含 `http://tauri.localhost`；
- P1 仍不启动 Docker、不读取本机文件、不调用 Claude/Codex/OpenCode/Opencode runtime。

### P2: Managed Local Stack

目标：

- 桌面客户端可以启动现有本地 Docker stack；
- 启动慢、失败、端口冲突、Docker 未运行都有清晰引导。

前端任务：

- 桌面设置页增加本地服务状态；
- 启动页增加“一键启动本地 AgentHub”；
- 增加日志查看面板；
- 增加诊断导出入口。

Tauri 任务：

- 实现受控 commands：
  - `desktop_check_local_stack`
  - `desktop_start_local_stack`
  - `desktop_stop_local_stack`
  - `desktop_restart_backend`
  - `desktop_tail_service_logs`
  - `desktop_export_diagnostics`
- 命令只允许固定 compose project 和固定 service。

B1/B2 任务：

- 后端启动日志要能解释 migration、runtime health、workspace preview cleanup 等常见问题；
- runtime health 继续在后端里判断。

验收：

- Docker 已运行但 stack 未启动时，客户端能启动并进入 Web UI。
- Docker 未运行时，提示打开 Docker Desktop。
- 启动失败时可查看 backend log tail。

#### P2 Implementation Note

P2 已按“管理既有栈，不创造第二套数据栈”的原则落地：

- Tauri Rust 层拆分为 `environment`、`project`、`stack`、`logs`、`diagnostics`、`state` 和 `sanitizer` 模块。
- 自定义 capability 只向 `main` window 暴露文档列出的桌面命令；未启用 shell、fs、process 或 Docker 插件。
- Rust 只组装固定 `docker compose` 参数。前端不能传入命令、服务名、compose 文件或任意路径。
- 项目绑定优先读取现有 `agenthub-backend` 容器的 Compose labels；现有栈目录与新选择目录不一致时拒绝启动，避免项目目录改名后生成新的 volumes。
- 普通启动使用 `up -d --no-build --wait postgres redis backend`，随后执行 Alembic migration、内置 Agent seed 和 `/health` 轮询。
- 缺少 Backend image 时先返回 `backend_image_missing`；只有用户二次确认后才允许 `--build`。
- 停止只执行 `compose stop backend redis postgres`，重启只执行 `compose restart backend`。代码中没有 `down -v`、volume remove、prune 或数据库 reset 路径。
- 启动、停止、重启共享 operation mutex，并通过 Tauri Channel 返回阶段事件。
- 设置页提供本地服务状态、显式启动/停止/重启、日志查看、诊断导出和 opt-in 自动启动；远程 backend 模式隐藏本地控制。
- 诊断文件写入 Tauri app-data，只包含脱敏后的环境摘要、栈状态、审计记录和有限日志，不读取 `.env`、认证目录、聊天内容或 Workspace 文件。
- B1 lifespan 输出 `builtin_agents`、`workspace_cleanup`、`application ready` 和 shutdown 的结构化阶段日志。

### P3: Desktop Native Utilities

目标：

- 提供桌面场景真正有价值的少量原生能力。

功能：

- 打开当前 conversation Workspace 文件夹；
- 系统通知；
- 保存下载；
- 文件选择增强；
- 外部链接打开；
- 诊断包导出。

边界：

- 文件上传仍走 B1 upload API；
- Workspace tree/file 仍走 B1 API；
- 不引入任意文件读写 bridge。

验收：

- 用户可从右栏打开当前 Workspace 文件夹。
- 长任务完成后可收到通知并跳回 conversation。
- 下载源码包可通过系统保存对话框保存。

#### P3 Implementation Note

P3 已按“用户选择、会话约束、最小权限”落地：

- Tauri capability 只增加系统 open/save dialog，以及对系统对话框动态授权路径的 read/write/stat；没有静态全盘文件 scope。
- 桌面上传复用现有 B1 upload API。系统选择器只负责把用户明确选中的文件转换成 Web `File`。
- Workspace command 只接受 `conversationId`，Rust 校验项目绑定、canonical path、reparse point 和 `.agenthub/manifest.json` 后交给 Explorer。
- 源码包使用系统“另存为”；Web/PWA 继续使用浏览器下载。
- 诊断导出返回一次性 `fileToken`，保存命令不接受前端路径。
- 外部链接只允许 `http`、`https`、`mailto`。
- 系统通知默认关闭，只消费顶层消息的完成、失败或等待确认终态，且不包含聊天正文或 runtime stderr。
- Windows toast 点击在应用仍运行时聚焦并导航到 conversation；通知中心冷启动属于 P4。
- `DesktopEnvironmentProvider` 统一管理 P1/P2/P3 桌面状态。

### P4: Installer And Update Story

目标：

- 给非开发用户一个可分发的 Windows 安装路径。

需要设计：

- 安装包格式；
- WebView2 runtime 检测；
- Docker Desktop 依赖检测；
- 数据库/volumes 保留策略；
- 版本升级；
- 回滚；
- 崩溃日志；
- 企业环境代理设置。

本阶段不应阻塞 P1/P2。

#### P4 Implementation Note

P4 的发布与更新策略固定为：

- 首次安装使用 NSIS 主安装包 `AgentHub_Desktop_{version}_x64-setup.exe`；MSI 作为企业部署和测试辅助产物。
- 后续更新使用 Tauri updater，从 GitHub Releases 拉取 `latest.json` 和已签名更新包。
- updater 签名是强制项；`TAURI_SIGNING_PRIVATE_KEY` 和 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` 只存在 CI secret。
- `tauri.conf.json` 中保留一个不用于生产的开发 public key，release workflow 会用 `TAURI_UPDATER_PUBLIC_KEY` 覆盖。
- Windows 代码签名预留在 CI 层；没有证书时不阻塞 P4，但安装包会缺少发行商签名。
- 桌面客户端只更新自己，不升级 Docker Desktop、不重建 backend image、不删除或迁移 volumes。
- 回滚采用手动安装上一版本安装包；回滚不得触碰 Postgres、Redis、Workspace、uploads 或 runtime auth state。

已新增的 P4 能力：

- `tauri-plugin-updater`：检查、下载和安装 signed updater artifact；
- `tauri-plugin-deep-link`：支持 `agenthub://chat/{conversationId}` 和 `agenthub://notification/{notificationId}?conversationId={conversationId}`；
- `tauri-plugin-single-instance`：重复启动时聚焦已有窗口，并转发 deep link 参数；
- 前端设置页“版本与更新”：显示桌面版本、后端版本、更新状态、上次检查时间、自动检查开关、手动检查与安装入口；
- Rust crash/panic hook：把脱敏后的 panic 摘要写入 app-data，供诊断包读取；
- GitHub Actions release workflow：运行前端/Rust/后端 smoke tests，构建 NSIS/MSI，生成 `latest.json`、签名更新包、signature 和 `checksums.txt`。

P4 仍不做：

- 企业代理配置；
- 自建更新服务器；
- 离线完整企业包；
- 应用内一键回滚；
- 自动升级本地 Docker stack 或 backend image。

## 3. Suggested File Layout

```text
frontend/
  src-tauri/
    Cargo.toml
    tauri.conf.json
    src/
      main.rs
      commands/
        environment.rs
        backend.rs
        stack.rs
        workspace.rs
        diagnostics.rs
  src/
    lib/
      desktopBridge.ts
      desktopBridge.web.ts
      desktopBridge.tauri.ts
    hooks/
      useDesktopEnvironment.ts
      useBackendHealth.ts
    components/
      desktop/
        DesktopStartupScreen.tsx
        DesktopDiagnosticsPanel.tsx
      settings/
        DesktopSettingsPanel.tsx
```

## 4. Configuration

### 4.1 Build-time

| Name | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Remote or local backend URL |
| `VITE_DESKTOP_MODE` | Optional desktop feature gate |
| `TAURI_SIGNING_PRIVATE_KEY` | Release signing, only in CI secret |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Optional updater signing key password |
| `TAURI_UPDATER_PUBLIC_KEY` | Release public key written into generated Tauri config |

### 4.2 Runtime Preferences

| Preference | Default | Notes |
|---|---|---|
| `backendUrl` | `http://localhost:8000` | 用户可改为远程 |
| `autoStartLocalStack` | `false` | 第一次必须确认 |
| `notificationsEnabled` | `false` | 用户 opt-in |
| `autoCheckUpdates` | `true` | 失败不阻塞应用启动 |
| `updateChannel` | `stable` | P4 只支持稳定通道 |
| `language` | `zh-CN` | 与 Web 设置对齐 |
| `openWorkspaceBehavior` | explicit click | 点击 Workspace 文件夹按钮即表示本次授权 |

## 5. Backend Coordination

桌面客户端不应该要求 B1/B2 新增大量桌面专属 API。

需要确认的契约：

- health endpoint 返回稳定状态；
- workspace API 可根据 conversation id 返回 root display info；
- deployment/download API 支持桌面保存；
- runtime health error 可读；
- existing batch starter 与 Tauri stack manager 使用同一套 compose project，不互相冲突。

## 6. Runtime Coordination

当前 Agent runtime 的关系：

| Runtime | 桌面客户端如何使用 |
|---|---|
| Builtin Agent | 通过 B1/B2 正常调用 |
| DeepSeek/OpenAI/Anthropic ModelGateway | 通过模型背包和后端环境调用 |
| Claude Code SDK/CLI | 通过 B2 adapter 调用，桌面壳不直接调用 |
| OpenCode CLI | 通过 B2 adapter 调用，桌面壳不直接调用 |
| Codex CLI | 通过 B2 adapter 调用，桌面壳不直接调用 |
| MCP | Agent config + B2 runtime health，桌面壳不直接启动用户 MCP |

## 7. UX Details

### 7.1 Startup Screen

推荐状态顺序：

1. 检查后端；
2. 若失败，检查是否桌面环境；
3. 若桌面环境，显示启动本地服务；
4. 启动后轮询 health；
5. 成功后进入 React App；
6. 失败时展示日志和修复建议。

### 7.2 Settings

桌面设置必须用中文默认文案，面向非工程用户：

- `本地服务`
- `后端地址`
- `启动 Docker 服务`
- `查看后端日志`
- `导出诊断包`
- `打开 Workspace 文件夹`

高级技术细节折叠。

### 7.3 Failure Copy

推荐错误文案：

- Docker 未运行：`需要先启动 Docker Desktop，AgentHub 的本地后端运行在 Docker 中。`
- Backend unreachable：`还没有连接到 AgentHub 后端。你可以重试，或启动本地服务。`
- Port conflict：`本地端口被占用，后端无法启动。请查看日志确认占用来源。`
- Runtime unavailable：`后端已启动，但部分 Agent 运行时不可用。你仍可使用可用 Agent。`

## 8. Migration And Rollback

桌面客户端必须避免数据破坏：

- 不自动执行 destructive migration；
- 不删除 Postgres volume；
- 不删除 Redis volume；
- 不删除 workspace volume；
- 不删除 Claude/OpenCode/Codex state volume；
- 升级前提示当前版本和目标版本。

如果桌面客户端不可用，用户仍可：

- 使用批处理脚本启动 Web；
- 打开 `http://localhost:5173`；
- 直接访问 `http://localhost:8000/docs` 做后端诊断。

## 9. Implementation Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Docker Desktop 启动慢 | 用户以为卡死 | 启动页显示阶段和日志 |
| 端口冲突 | 后端不可达 | health + log tail + 文案 |
| WebView2 版本差异 | UI 异常 | Windows smoke matrix |
| Bridge 权限过宽 | 安全风险 | allowlist + no arbitrary shell |
| 壳层调用 runtime | 状态不一致 | 明确禁止，runtime only via B1/B2 |
| 本地/远程 backend 混淆 | Workspace 打开错误 | backend URL mode 标识 |

## 10. Definition Of Done

P1 done:

- Tauri dev/build 可运行；
- 桌面壳连接现有 backend；
- 基础 Web 功能一致；
- 后端未启动有清晰状态。

P2 done:

- 可一键启动本地 Docker stack；
- 可查看日志；
- 失败可诊断；
- 不删除数据；
- 能识别并保护已有 Compose project/volumes；
- 远程 backend 模式不暴露本地栈控制。

P3 done:

- Workspace 文件夹打开；
- 通知；
- 文件选择/保存增强；
- 诊断包。
- 原生能力均由 capability、动态文件 scope 或 conversation-scoped command 限制。

## 11. Handoff Checklist

给后续 Agent 接手时必须确认：

- 当前分支；
- 是否已有 `src-tauri`；
- 是否决定 Tauri 版本；
- 是否已有 backend health endpoint；
- 当前 Docker compose project name；
- Windows 机器是否安装 WebView2 和 Docker Desktop；
- 是否连接本地 backend 还是远程 backend；
- 是否允许 desktop manager 启动 Docker stack。
