# Windows Desktop Client Test Plan

> Status: Draft test plan
> Last updated: 2026-06-09
> Scope: Windows desktop wrapper, host bridge, local stack management, and regression coverage

## 1. Test Philosophy

桌面客户端测试要验证两件事：

1. 它复用了现有 Web 产品面，没有引入第二套聊天/Agent/Workspace 行为。
2. 它开放的主机能力足够安全、可诊断、不会破坏用户本地数据。

因此测试分为：

- Web regression；
- Tauri bridge unit/integration；
- Windows manual smoke；
- Local stack failure matrix；
- Security boundary tests。

## 2. Automated Checks

### 2.0 P0 Environment Result

2026-06-09 P0 spike 环境检查：

- `node --version`：`v24.15.0`
- `pnpm desktop:info` 识别到 pnpm：`9.15.4`
- `WebView2`：`148.0.3967.96`
- `MSVC`：Visual Studio Community 2026
- `rustc --version`：`1.96.0`
- `cargo --version`：`1.96.0`
- `rustup --version`：`1.29.0`

结论：Windows P0 Tauri prerequisites 已补齐。Rust/Cargo 最初缺失，已通过 `winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements` 安装并在本轮 shell 中加入 `$HOME/.cargo/bin` 后完成验证。

2026-06-09 P0 spike 验证结果：

- `pnpm exec tsc -b`：通过。
- `pnpm build`：通过，保留既有 bundle size warning。
- `pnpm exec vitest run`：56 files / 249 tests 通过，保留既有 jsdom / React Router warning。
- `pnpm desktop:info`：通过，Tauri CLI 识别 WebView2、MSVC、Rustup、Rust toolchain、Vite/React。
- `cargo fmt --check --manifest-path src-tauri/Cargo.toml`：通过。
- `cargo test --manifest-path src-tauri/Cargo.toml`：通过，当前 0 Rust tests。
- `cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings`：通过。
- `pnpm desktop:build`：通过，生成 `agenthub-desktop.exe`、MSI 和 NSIS setup bundle。
- 桌面 exe smoke：通过，`agenthub-desktop.exe` 启动后窗口标题为 `AgentHub Desktop`，随后可正常关闭。
- 精准安全扫描 `rg "std::process|Command::|invoke_handler|plugin-shell|plugin-fs|docker|claude|codex|opencode" frontend/src-tauri`：无命中。
- `git diff --check`：通过，仅提示部分已有文件下次 Git touch 时 LF/CRLF 转换。

### 2.1 Frontend

每次桌面相关改动至少运行：

```bash
cd frontend
pnpm exec tsc -b
pnpm exec vitest run
pnpm build
```

如果新增 Tauri 工程：

```bash
cd frontend
pnpm desktop:dev
pnpm desktop:build
```

P0 允许在 Rust 缺失时将这两项记录为环境 blocker；`pnpm desktop:info` 仍应运行，用于确认 Tauri CLI 已安装并能给出诊断信息。

需要覆盖：

- desktop bridge web fallback；
- backend health startup state；
- desktop settings panel；
- non-desktop browser 不显示不可用控件；
- workspace open action 只在 desktop + local backend 模式可见。

P1 额外覆盖：

- `desktopBridge` 检测 Web/Tauri runtime、持久化 backend URL、解析 `/health` 成功和失败；
- `DesktopBootstrapGate` 在桌面环境中拦截 App，后端 ready 后再进入登录/聊天；
- REST `api` 与 SSE `subscribeMessageStream` 都使用同一个 runtime backend URL；
- 设置页显示中文“桌面客户端”诊断信息，但不显示 Docker 启动/停止控件。

P2 额外覆盖：

- 启动页在 localhost 模式显示本地栈状态和显式启动入口，远程 backend 模式隐藏本地控制；
- `autoStartLocalStack` 默认关闭，只有用户开启后才自动恢复；
- start/stop/restart 阶段通过 Channel 更新，不产生聊天消息；
- operation error 在状态刷新后仍保留，不被后续 health refetch 清空；
- 日志只允许 backend/postgres/redis，最多 300 行；
- 诊断导出只显示 app-data 文件路径。

P3 额外覆盖：

- 桌面文件选择只读取系统对话框返回的动态 scope，取消选择不产生上传；
- 选择文件超过 100 MB 时在读取内容前拒绝；
- 桌面附件上传携带 `clientPlatform=desktop`，Web/移动端行为不变；
- Workspace 打开只接收 conversation UUID，并验证项目绑定、manifest、canonical path 和 reparse point；
- 源码 ZIP 与诊断文件通过系统“另存为”保存；
- 外链拒绝 `file:`、`javascript:`、`data:` 和带用户名密码的 URL；
- 通知默认关闭、前台同会话抑制、终态去重、clarification waiting 映射为等待确认；
- 点击通知只聚焦并导航，不产生消息或 Agent 操作。

P4 额外覆盖：

- 设置页“版本与更新”展示桌面版本、后端版本、上次检查时间、自动检查开关和稳定通道。
- 自动检查更新默认开启，但 404、无网络、签名错误或 GitHub 不可达都不能阻塞应用启动。
- 手动检查更新覆盖：无更新、有更新、下载失败、安装完成等待重启。
- `agenthub://chat/{conversationId}` 只接受 UUID 并跳转对应 conversation。
- `agenthub://notification/{notificationId}?conversationId={conversationId}` 可在应用运行或冷启动后回到 conversation。
- single-instance 重复启动只聚焦已有窗口并转发 deep link，不创建第二套前端状态。
- crash/panic log 脱敏、限长、可被诊断收集读取。
- Release workflow 产出 NSIS、MSI、signed updater package、signature、`latest.json` 和 `checksums.txt`。
- Release artifacts 不包含 `.env`、auth state、workspace、uploads、数据库 dump、诊断包或本地构建缓存。

### 2.2 Tauri Rust

建议：

```bash
cd frontend/src-tauri
cargo test
cargo fmt --check
cargo clippy -- -D warnings
```

覆盖：

- command 参数校验；
- path boundary；
- log sanitization；
- compose command builder；
- backend health parsing；
- error code mapping。

### 2.3 Backend Regression

桌面客户端不应破坏后端契约。至少运行：

```bash
ruff check app tests
pytest -q tests/test_workspace_api.py tests/test_stream_tool_calls.py tests/test_model_accounts_api.py
```

如果改 health endpoint 或 workspace path：

```bash
pytest -q tests/test_workspace_service.py tests/test_b1_quality.py
```

## 3. Manual Smoke Matrix

### 3.1 Backend Already Running

前置：

- Docker stack 已运行；
- backend health ready；
- Postgres 中有历史会话。

步骤：

1. 打开桌面客户端。
2. 确认无需手动输入 URL 即进入应用。
3. 检查会话列表不是空白。
4. 打开旧会话。
5. 发送普通消息。
6. 发送 Orchestrator 任务。
7. 切换会话再切回。
8. 打开 Workspace。

预期：

- 行为与 Web 端一致；
- SSE 不因为窗口/会话切换中断；
- Workspace 不出现上一会话残影；
- Agent runtime 由后端选择。

P1 自动化/半自动 smoke：

1. `docker compose up -d postgres redis backend`；
2. 轮询 `http://localhost:8000/health`，直到 `status=ok`；
3. `cd frontend && pnpm desktop:build`；
4. 启动 `src-tauri/target/release/agenthub-desktop.exe`；
5. 确认窗口非白屏，桌面启动页通过后可进入 `/login`。

### 3.2 Backend Not Running

前置：

- Docker Desktop 运行；
- AgentHub compose stack 停止。

步骤：

1. 打开桌面客户端。
2. 观察启动页。
3. 点击启动本地服务。
4. 等待 health ready。

预期：

- 不白屏；
- 显示启动阶段；
- 成功后进入应用；
- 不重建镜像，除非用户选择 rebuild；
- 不删除 volume。

P1 边界：此阶段只显示连接失败和重试，不提供“一键启动本地服务”。一键启动、日志 tail 和 Docker 诊断属于 P2。

### 3.3 Docker Desktop Not Running

步骤：

1. 退出 Docker Desktop。
2. 打开桌面客户端。
3. 点击启动本地服务。

预期：

- 显示 `需要先启动 Docker Desktop`；
- 提供重试；
- 不陷入无限 spinner；
- 日志面板不会显示空白。

### 3.4 Port Conflict

前置：

- 占用 backend 或 Postgres 端口。

预期：

- 启动失败可诊断；
- 显示端口冲突或 compose 错误摘要；
- 可查看 log tail；
- 不显示为聊天消息失败。

### 3.5 Remote Backend

步骤：

1. 设置 backend URL 为远程 AgentHub。
2. 登录并打开会话。

预期：

- 本地 stack controls 变为不可用或隐藏；
- 打开本地 Workspace 文件夹不可用；
- 聊天、SSE、Agent、模型背包仍可用；
- 文案明确当前连接的是远程服务。

### 3.6 P3 Native Utilities

1. 安装 MSI/NSIS 后启动客户端并启用系统通知。
2. 在 Workspace 右栏点击文件夹图标，确认 Explorer 打开当前 conversation 目录。
3. 选择图片和 ZIP，确认附件队列和上传进度正常。
4. 下载 source ZIP，选择目标目录并验证压缩包可读。
5. 导出诊断并点击“另存为”，确认前端未显示 app-data 完整路径。
6. 在另一个会话运行任务，确认 done/error/等待确认通知；点击后跳回正确 conversation。
7. 关闭通知后重复任务，确认不再发送 toast。

Windows toast 的点击验收使用已安装包；`tauri dev` 不作为应用身份和通知中心冷启动的验收依据。

### 3.7 P4 Installer And Updater

步骤：

1. 通过 GitHub Actions 手动触发或 `desktop-v*` tag 构建 release。
2. 确认 workflow 运行前端、Rust、后端 smoke tests。
3. 下载 `AgentHub_Desktop_{version}_x64-setup.exe` 并安装。
4. 验证开始菜单、桌面快捷方式和 WebView2 启动体验。
5. 发布测试 GitHub Release，验证客户端检查到新版本、下载、安装、重启。
6. 更新后检查历史会话、workspace、uploads 和 runtime volumes 保持不变。
7. 关闭应用后从浏览器打开 `agenthub://chat/{conversationId}`，验证冷启动和聚焦跳转。
8. 关闭应用后点击 Windows 通知中心中的任务通知，验证冷启动回到对应 conversation。
9. 手动安装上一版本，验证回滚不删除本地数据。

预期：

- updater 签名校验失败时拒绝安装并显示中文诊断。
- GitHub Releases 不可达时应用照常进入登录/聊天。
- 卸载或回滚不触碰 Docker volumes、Postgres/Redis、workspaces、uploads 或 runtime auth state。

## 4. Host Bridge Security Tests

P0 静态安全检查：

```bash
rg "shell|fs|Command|docker|claude|codex|opencode" frontend/src-tauri
```

预期只有文档性描述或无结果；不得出现自定义 command、runtime 调用或 Docker 调用。

P3 精准检查允许受控 native command 和 dialog/fs 插件，但必须确认：

```bash
rg "shell|process:|fs:allow-(read-dir|remove|rename)|Command::new" frontend/src-tauri
rg "desktop_open_workspace_folder|desktop_save_diagnostics|desktop_open_external_url" frontend/src-tauri
```

预期：没有通用 shell/process 权限、没有静态全盘目录 scope、没有接受任意路径的 command。

### 4.1 Path Boundary

必须拒绝：

- `C:\Users\<user>\.ssh`
- `C:\Windows\System32`
- `..\..\outside`
- UNC path；
- symlink escape。

允许：

- 后端确认的当前 conversation workspace；
- 用户通过系统保存对话框选择的下载路径；
- 文件选择器返回的上传文件。

### 4.2 Command Boundary

必须不存在：

- 任意 shell command；
- 前端可控的任意 Docker command、service name 或 compose 参数；
- 任意 env dump；
- runtime direct invoke。

允许：

- Rust 内部固定的 `docker compose up/stop/restart/exec/ps/logs/images` argv；
- 仅针对验证通过的 AgentHub project root 和 backend/postgres/redis；
- 无 `down -v`、prune、volume remove、数据库 reset。

测试方式：

- 静态搜索 bridge command；
- Rust unit test；
- 前端类型只暴露 allowlist API。

### 4.3 Log Sanitization

准备日志样本：

```text
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
postgres://agenthub:password@postgres:5432/agenthub
Authorization: Bearer abc.def
```

预期：

- UI 和诊断包均显示 redacted；
- 不保留原文。

## 5. Data Safety Tests

必须验证：

- `stop local stack` 不删除 Postgres volume；
- `restart backend` 不删除 workspace；
- `desktop export diagnostics` 不打包 `.env`、auth volume、uploads 原始文件；
- 版本升级不重置 DB；
- 连接远程 backend 不修改本地 Docker stack。

## 6. Agent Runtime Tests

桌面客户端不直接测试 runtime 内部实现，但必须验证调度路径：

### 6.1 Builtin Agent

- 自定义 builtin Agent 使用默认 DeepSeek；
- 桌面发送消息；
- 后端返回 stream。

### 6.2 Claude Code

- 如果后端 runtime health ready，Orchestrator 可调度当前群聊内 Claude Code；
- 如果 unavailable，UI 显示后端错误，不由桌面壳尝试修复或直接调用 CLI。

### 6.3 OpenCode / Codex

- 同上；
- runtime 缺失错误由 B2 归一化；
- 桌面壳不读取 CLI 路径作为可用性事实。

## 7. Workspace Tests

### 7.1 Open Folder

步骤：

1. 打开某 conversation 的 Workspace。
2. 点击“在文件资源管理器中打开”。

预期：

- 打开该 conversation workspace；
- 切换 conversation 后再次打开是新 workspace；
- 不允许传入旧路径。

### 7.2 Running Task

步骤：

1. Orchestrator 调度 Agent 写文件。
2. 运行中保持右栏 Workspace 打开。
3. 等待完成或失败。

预期：

- 运行中保留最后可信 tree；
- 后台刷新失败不整块闪红；
- 完成后 tree 更新。

## 8. Notification Tests

覆盖：

- 通知关闭时不弹；
- 打开后任务完成弹通知；
- 失败任务弹通知；
- 点击通知回到对应 conversation；
- 通知内容不含敏感错误全文。

## 9. Accessibility And UX

检查：

- Windows 缩放 125% / 150%；
- Ctrl + mouse wheel 页面缩放不震颤；
- 高对比度模式；
- 键盘可操作；
- 设置页文字默认中文；
- 错误文案不要求用户理解 Docker 内部细节。

## 10. Release Checklist

发布桌面包前确认：

- `pnpm build` 通过；
- `pnpm desktop:build` 通过；
- `cargo test` 通过；
- Web regression tests 通过；
- Rust bridge tests 通过；
- Windows manual smoke 通过；
- 没有把 `.env`、auth state、workspaces、uploads、数据库 dump 打进包；
- installer 不删除现有 Docker volumes；
- README 有启动、排障、卸载说明。

## 11. P2 Verification Record

2026-06-09 本机验证结果：

- `pnpm exec vitest run`：60 files / 261 tests 通过。
- `pnpm exec tsc -b`、`pnpm build`：通过；保留既有 bundle size warning。
- `cargo fmt --check`、`cargo test`：通过，9 个 Rust 单测覆盖项目标记、profile/lifecycle argv、Compose JSON、停止态、偏好、脱敏和诊断路径。
- `cargo clippy -- -D warnings`：通过。
- `uv run ruff check app tests`：通过。
- 独立测试数据库运行 `tests/test_health.py tests/test_model_accounts_api.py`：10 tests 通过。
- `pnpm desktop:info`：识别 WebView2、MSVC、Rust 1.96、Cargo 1.96、Tauri 2.11。
- `pnpm desktop:build`：通过，生成 release exe、MSI 和 NSIS bundle。
- release exe smoke：进程成功创建标题为 `AgentHub Desktop` 的主窗口并可正常关闭。
- Web smoke：登录页非白屏，无横向溢出。
- 真实 Docker stop/start/restart、migration、seed、health 全部通过。
- 数据安全核对：操作前后 AgentHub 6 个 named volumes 名称完全一致；`users=7189`、`conversations=594`、`messages=5136`、`workspaces=292` 均未变化。
- 发现并修复旧开发库漂移：`user_model_accounts` 已被旧测试 `create_all()` 创建，但 Alembic 版本仍在上一 revision。迁移现在会验证已有表结构、补缺失索引并安全推进版本；独立临时数据库已复现验证。
