# Windows Desktop Host Bridge Spec

> Status: Draft contract spec
> Last updated: 2026-06-09
> Scope: Tauri native bridge commands, permission boundary, host operations, and diagnostics

## 1. Summary

Windows 桌面客户端需要少量主机能力，但这些能力必须是受控桥接命令，而不是让 Web UI 获得本机完整权限。

Host Bridge 是 Tauri Rust 层暴露给 React 的白名单 API。它只做平台能力和本地服务管理，不承载 AgentHub 业务逻辑。

## 2. Design Principles

- **Allowlist first**：只有文档列出的 command 可以存在。
- **No arbitrary shell**：不提供 `runCommand(command: string)`。
- **Backend-owned runtime**：Claude / Codex / OpenCode / MCP 调度仍由 B1/B2 完成。
- **Explicit user action**：所有可能影响主机的操作来自用户点击。
- **Path capability**：文件操作必须绑定到后端确认过的 workspace、上传临时目录或下载目标。
- **Safe diagnostics**：日志可以看 tail，但必须清洗密钥、token、auth 路径和长 stderr。

## 3. Bridge Surface

### 3.1 Environment

```ts
type DesktopEnvironment = {
  platform: string;
  appVersion: string;
  appDataDir: string;
};
```

Commands:

- `desktop_get_environment(): DesktopEnvironment`
- `desktop_get_preferences(): DesktopPreferences`
- `desktop_set_preferences(patch: Partial<DesktopPreferences>): DesktopPreferences`

Preferences 可保存：

- `backendUrl`
- `autoStartLocalStack`
- `notificationsEnabled`
- `autoCheckUpdates`
- `lastUpdateCheckAt`
- `updateChannel`
- `language`
- `openWorkspaceBehavior`

Preferences 不保存：

- API Key；
- Claude / Codex / OpenCode 登录态；
- 任意 env；
- 用户文件内容。

### 3.2 Backend Health

```ts
type BackendHealth = {
  url: string;
  reachable: boolean;
  status: "ready" | "starting" | "unreachable" | "version_mismatch";
  version?: string;
  error?: string;
  checkedAt: string;
};
```

Commands:

- `desktop_check_backend_health(url?: string): BackendHealth`
- `desktop_wait_for_backend(url: string, timeoutMs: number): BackendHealth`

Rules:

- 只访问配置中的 AgentHub backend URL。
- 不扫描局域网。
- 不读取 backend 私有文件。

### 3.3 Local Stack Management

```ts
type LocalStackStatus = {
  projectRoot?: string;
  projectName?: string;
  profile?: "source" | "windows_image";
  docker: "ready" | "not_installed" | "not_running";
  composeAvailable: boolean;
  backendHealth: "ready" | "starting" | "unreachable";
  services: Array<{
    name: "postgres" | "redis" | "backend";
    status: "running" | "healthy" | "starting" | "stopped" | "error" | "unknown";
    detail?: string;
  }>;
};
```

Commands:

- `desktop_choose_project_root(): StackBinding | null`
- `desktop_get_stack_binding(): StackBinding`
- `desktop_check_local_stack(): LocalStackStatus`
- `desktop_start_local_stack(options?: { rebuild?: boolean }): StackOperation`
- `desktop_stop_local_stack(): StackOperation`
- `desktop_restart_backend(): StackOperation`

Rules:

- 只能在已识别的 AgentHub repo root 内执行受控脚本或固定 compose command。
- 项目目录必须包含 `docker-compose.yml`、`.env.example`、`backend/alembic.ini`、`shared/openapi.yaml`。
- 若检测到现有 `agenthub-backend`，其 Compose project 和 working directory 是权威绑定；目录冲突或原目录丢失时必须停止并解释，不得静默创建新 volumes。
- `rebuild=true` 必须二次确认，因为会拉镜像或重建容器。
- 不提供任意 service name 执行能力，第一版仅允许 `backend` restart。
- 不自动删除 volumes。
- 不执行 `docker compose down -v`。
- 同一时间只能执行一个 start/stop/restart。
- 长操作通过 Channel 返回 `checking`、`starting_services`、`migrating`、`seeding`、`waiting_health`、`ready/error`。

### 3.4 Logs

```ts
type ServiceLogTail = {
  service: string;
  lines: string[];
  truncated: boolean;
  sanitized: boolean;
};
```

Commands:

- `desktop_tail_service_logs(service: "backend" | "postgres" | "redis", lines?: number): ServiceLogTail`
- `desktop_export_diagnostics(): { fileToken: string; suggestedName: string }`
- `desktop_save_diagnostics(fileToken: string): SaveResult`

Rules:

- 默认最多 300 行。
- 导出诊断包前展示将包含哪些信息。
- 清洗规则至少覆盖：
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `DEEPSEEK_API_KEY`
  - `CLAUDE_*`
  - `OPENCODE_*`
  - bearer token
  - connection string password

### 3.5 Workspace Folder

Commands:

- `desktop_open_workspace_folder(conversationId: string): OpenResult`

Rules:

- React 只传 `conversationId`，不传任意本机路径。
- Tauri bridge 向 backend 请求或校验 workspace root。
- 最终路径必须在 configured workspace base 内。
- 不创建新 workspace；创建仍由 B1 `WorkspaceService` 完成。

### 3.6 File Picker And Downloads

Commands:

- 普通文件选择与下载保存通过 Tauri dialog + fs 动态 scope 完成，不暴露通用路径 command。
- 诊断保存只接受 `desktop_export_diagnostics` 返回的一次性 token。

Rules:

- 文件选择只返回浏览器可上传的 handle/token 或临时文件引用。
- 上传仍走现有 B1 upload API。
- 不因为选择 zip 自动解压到 Workspace。
- 保存下载文件时不覆盖已有文件，除非用户确认。

### 3.7 Notifications

Commands:

- `desktop_show_notification(input: DesktopNotification): void`
- event `desktop://notification-activated` 返回 notification/conversation ID。

Rules:

- 通知需要用户开启。
- 通知正文不展示敏感内容。
- 点击通知只导航到 conversation，不执行任务。
- P3 只保证应用运行期间的 Windows toast activation；冷启动激活留给 P4。

### 3.8 External URLs

Commands:

- `desktop_open_external_url(url: string): void`

Rules:

- 只允许 `http:`、`https:`、`mailto:`。
- `file:` URL 必须使用 workspace/open-folder command，不能直接打开。

### 3.9 Release, Update And Deep Links

Commands:

- `desktop_check_for_update(): DesktopUpdateCheckResult`
- `desktop_install_update(): DesktopUpdateInstallResult`
- `desktop_get_release_info(): DesktopReleaseInfo`
- `desktop_open_release_page(): OpenResult`
- `desktop_collect_crash_report(): CrashReport`

Protocols:

- `agenthub://chat/{conversationId}`
- `agenthub://notification/{notificationId}?conversationId={conversationId}`

Rules:

- updater 只能使用 Tauri signed artifact；禁止关闭签名校验。
- updater private key 只允许存在 CI secret；本地开发配置只能包含 public key。
- deep link 只接受 `agenthub:` scheme、UUID conversation ID 和受控 notification ID。
- deep link 不携带消息正文、文件路径、token、模型密钥或 runtime stderr。
- 重复启动只聚焦已有窗口并转发 deep link，不新开第二个独立实例。
- `desktop_open_release_page` 只打开固定 GitHub Releases 页面，不接受任意 URL。
- crash report 只返回脱敏后的 tail 内容；诊断包仍通过 P2/P3 的 token 保存流程导出。
- 安装器和 updater 只更新桌面客户端，不删除 Docker volumes、workspace、uploads 或 runtime auth state。

## 4. Disallowed Commands

禁止实现或暴露以下形态：

```ts
runShell(command: string): string
readFile(path: string): string
writeFile(path: string, content: string): void
readEnv(name?: string): Record<string, string>
copyClaudeAuth(): void
invokeRuntime(agentId: string, prompt: string): string
docker(command: string): string
```

P2 可以在 Rust 内部调用固定 Docker argv，但禁止把 Docker 命令、service、compose 参数或 shell 字符串作为前端输入。

如果未来确实需要某一类能力，必须拆成一个受控 command，并补充：

- 参数 schema；
- 路径边界；
- 用户确认；
- 日志清洗；
- 后端权限对齐；
- 测试用例。

## 5. Frontend Adapter

React 层不直接依赖 `window.__TAURI__`，而是通过一个小适配器：

```ts
export type DesktopBridge = {
  isDesktop: boolean;
  getEnvironment(): Promise<DesktopEnvironment>;
  checkBackendHealth(url?: string): Promise<BackendHealth>;
  startLocalStack(options?: { rebuild?: boolean }): Promise<StackOperation>;
  openWorkspaceFolder(conversationId: string): Promise<OpenResult>;
  selectFiles(options: DesktopFilePickerOptions): Promise<DesktopSelectedFiles>;
};
```

Web/PWA 下 adapter 返回 `isDesktop=false`，调用桌面专属能力时给出可理解错误，不让业务组件崩溃。

建议文件：

- `frontend/src/lib/desktopBridge.ts`
- `frontend/src/hooks/useDesktopEnvironment.ts`
- `frontend/src/components/settings/DesktopSettingsPanel.tsx`

## 6. Permission And Confirmation Matrix

| Action | Confirmation | Audit | Notes |
|---|---:|---:|---|
| Check backend health | No | No | 只访问配置 URL |
| Start local stack | Yes | Yes | 可记住偏好，但第一次必须确认 |
| Stop local stack | Yes | Yes | 不删除 volumes |
| Restart backend | Yes | Yes | 仅 backend |
| Tail logs | No | No | 固定服务、最多 300 行、清洗敏感信息 |
| Export diagnostics | Click action | Yes | 只写入 app-data |
| Open workspace folder | Click action | Yes | conversation-scoped |
| Select files | OS picker | Yes | 上传前仍由用户发送 |
| Save downloads | OS picker | Yes | 不静默覆盖 |
| Show notification | Setting opt-in | No | 不含敏感内容 |
| Check/install update | Click or opt-in auto check | Yes | updater signed artifact only |
| Open deep link | OS protocol activation | No | UUID allowlist, navigation only |
| Collect crash report | Click action | Yes | 脱敏 tail，不含聊天正文 |

## 7. Error Semantics

Bridge error 必须结构化：

```ts
type DesktopBridgeError = {
  code:
    | "desktop_not_available"
    | "backend_unreachable"
    | "docker_not_running"
    | "compose_not_available"
    | "project_root_not_found"
    | "project_binding_conflict"
    | "existing_stack_project_missing"
    | "backend_image_missing"
    | "desktop_operation_busy"
    | "port_conflict"
    | "operation_denied"
    | "path_not_allowed"
    | "service_start_failed"
    | "timeout"
    | "unknown";
  message: string;
  detail?: string;
};
```

UI 文案要求：

- 先说用户可做什么；
- 再展示技术细节；
- 不把 stderr 原样塞进主界面；
- 不把 bridge failure 渲染成 agent message error。

## 8. Audit Log

建议本地记录：

- timestamp；
- action；
- sanitized parameters；
- result；
- duration；
- app version。

不记录：

- API key；
- full env；
- selected file content；
- model prompt；
- message content；
- auth json。

## 9. Acceptance Criteria

- Web 模式下不会加载 Tauri-only code path。
- Desktop 模式下每个 command 都有参数校验和错误码。
- 没有任意 shell command bridge。
- Capability 仅允许 `main` window 的本地应用内容调用，不配置 remote URL capability。
- 打开 Workspace 只能打开当前 conversation 的 workspace。
- React 不向 Workspace 或 diagnostics command 传入本机路径。
- 系统选择器产生的文件 scope 不持久化。
- 本地 stack start/restart/stop 均不会删除用户数据 volumes。
- 日志导出经过敏感信息清洗。
- 所有 bridge failure 都是局部 UI 状态，不污染聊天消息生命周期。
