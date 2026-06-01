# Workspace Artifact / Preview / Deployment Spec

> 状态：Artifact / Preview / Deployment v1 为 Current contract。
> 最后更新：2026-05-31

## 目标

统一定义 workspace 中 agent 产物的识别、记录、展示、预览和部署边界。该 Spec 合并原 artifact contract 与 preview/deploy 边界，作为 artifact / preview / deployment 的唯一事实来源。

核心原则：

- Agent runtime 只负责生成文件。
- 平台负责识别 artifact、维护 manifest、启动 preview / deployment、生成 URL。
- 端口、PID、URL、deployment record、生命周期不归 agent runtime 管。
- `web_preview.url` 必须来自平台 service，不能由 agent 编造。
- Deploy 不等同 preview：preview 是临时开发预览，deployment 是可追踪的发布记录。

## Artifact 定义

Artifact 是 workspace 中由 agent run 创建或修改、且对用户有交付意义的文件或文件集合。

| kind | 示例 | previewable |
|---|---|---|
| `html` | `snake.html` | true |
| `static_web` | `index.html` + `style.css` | true |
| `web_app` | `package.json` + `src/` | false，除非存在静态入口 |
| `code` | `app.py`, `main.tsx` | false |
| `document` | `README.md`, `report.md` | false |
| `asset` | `logo.png`, `style.css` | false |
| `archive` | `dist.zip` | false |

## Workspace Snapshot

每次 agent run 开始前记录 workspace snapshot，run 结束后对比：

- `created`
- `modified`
- `deleted`

默认忽略：

- `.agenthub/`
- `.git/`
- `node_modules/`
- `.venv/`
- `__pycache__/`
- runtime 临时输出文件

## Artifact Manifest

平台维护 `.agenthub/artifacts.json`，agent runtime 不允许写入 `.agenthub/`。

```json
{
  "version": 1,
  "artifacts": [
    {
      "id": "art_001",
      "run_message_id": "message-uuid",
      "path": "snake.html",
      "kind": "html",
      "status": "ready",
      "previewable": true,
      "entry_path": "snake.html",
      "created_at": "2026-05-29T12:00:00Z"
    }
  ]
}
```

## Artifact 识别规则

优先级：

1. Agent 最终文本明确提到的文件路径。
2. run snapshot 中新增或修改的可识别文件。
3. 标准入口：`index.html`、`snake.html`、`package.json`、`src/main.*`。
4. 文件扩展名和 MIME 推断。

HTML 规则：

- 单个 `.html` 文件直接作为 `entry_path`。
- 多个 `.html` 文件优先 `index.html`，其次最新修改文件。

JS web app 规则：

- 有 `package.json` 但无静态入口时，不执行 `npm install` / `npm run dev`。
- 记录为 `web_app`，`previewable=false`。

## Preview Session

平台层管理 preview session：

```python
class WorkspacePreviewSession(Base):
    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    entry_path: str
    port: int
    pid: int | None
    url: str
    status: Literal["starting", "running", "stopped", "error"]
    error: str | None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
```

约束：

- 一个 conversation 同时最多一个 active preview session。
- `entry_path` 必须通过 workspace path validation。
- `pid` 只能来自平台启动的进程，不能来自 agent runtime。

## Preview 配置

| 字段 | 默认值 | 说明 |
|---|---:|---|
| `PREVIEW_ENABLED` | `true` | 是否开启平台预览 |
| `PREVIEW_PORT_START` | `8082` | 端口池起始 |
| `PREVIEW_PORT_END` | `8182` | 端口池结束 |
| `PREVIEW_PUBLIC_BASE_URL` | null | 公网 base URL |
| `PREVIEW_IDLE_TTL_SECONDS` | `1800` | 闲置清理时间 |
| `PREVIEW_START_TIMEOUT_SECONDS` | `15` | 启动健康检查超时 |

8082 是平台端口池的一部分，不允许 agent runtime 直接监听。

## API

建议 B1 暴露：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/workspaces/{conversation_id}/artifacts` | 列出 artifact |
| `GET` | `/api/v1/workspaces/{conversation_id}/artifacts/{artifact_id}` | 查看 artifact metadata |
| `POST` | `/api/v1/workspaces/{conversation_id}/preview` | 启动或复用 preview |
| `GET` | `/api/v1/workspaces/{conversation_id}/preview` | 查询 preview 状态 |
| `DELETE` | `/api/v1/workspaces/{conversation_id}/preview` | 停止 preview |
| `POST` | `/api/v1/workspaces/{conversation_id}/deployments` | 创建一次部署 / 打包 |
| `GET` | `/api/v1/workspaces/{conversation_id}/deployments` | 列出部署历史 |
| `GET` | `/api/v1/workspaces/{conversation_id}/deployments/{deployment_id}` | 查询部署状态 |
| `DELETE` | `/api/v1/workspaces/{conversation_id}/deployments/{deployment_id}` | 停止可停止部署 |
| `GET` | `/api/v1/workspaces/{conversation_id}/deployments/{deployment_id}/download` | 下载源码包 |

`POST preview` body：

```json
{
  "entry_path": "snake.html",
  "mode": "static"
}
```

MVP 只要求 `mode="static"`。

## Agent 请求预览

当用户消息明确包含部署/端口/preview 意图时，SSE 流结束前由平台层执行自动 preview：

1. agent / Orchestrator 仍只负责生成和验证 workspace artifact。
2. `stream_preview.py` 在生成完成后查找 `index.html` 或其他 `.html/.htm` 入口。
3. 平台插入 `tool_call(name="start_workspace_preview")` 与对应 `tool_result`。
4. `WorkspacePreviewService` 校验 workspace path、按用户明确端口作为首选分配端口并启动静态 preview。
5. 成功后追加平台来源的 `web_preview` block。

该 tool 是平台受控 tool，不是 runtime agent shell 命令；`pid` 只能来自平台 service。

## URL 与 StreamChunk

平台返回：

```json
{
  "status": "running",
  "entry_path": "snake.html",
  "port": 8082,
  "url": "http://111.229.151.159:8082/snake.html"
}
```

当前端或平台确认 preview 可用后，可以追加：

```python
StreamChunk(
    event_type="block_start",
    block_type="web_preview",
    metadata={
        "url": preview_url,
        "title": entry_path,
        "description": "AgentHub Workspace Preview",
    },
)
```

约束：

- `web_preview.url` 必须来自平台 Preview service。
- Artifact manifest 不进入 `message.content`。
- 如果 preview 尚未实现或启动失败，final summary 只能说明平台预览处理状态，不能提供 terminal 命令。

## Deployment v1

> 当前状态：MVP 已实现。静态发布与 Preview 生命周期解耦、不可变 release snapshot、稳定 release route、真实 stop 和 container 安全底座见 [deployment-release-hardening.execution.spec.md](deployment-release-hardening.execution.spec.md)。

Deploy 不等同 preview：

- `preview`：临时开发预览，端口池管理，适合浏览器验收。
- `deployment`：一次可追踪发布记录，有状态、URL、日志、失败原因和历史。
- `source_export`：源码 zip 打包下载，不等同部署。
- `container_deploy`：本阶段只返回 `not_supported`，不执行 Docker。

v1 平台记录一次 deployment：

```python
class WorkspaceDeployment(Base):
    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    kind: Literal["static_site", "source_zip", "container"]
    artifact_path: str
    status: Literal[
        "queued",
        "publishing",
        "published",
        "failed",
        "stopped",
        "not_supported",
    ]
    url: str | None
    download_url: str | None
    error: str | None
    logs: list[str]
    created_at: datetime
    updated_at: datetime
```

### Deployment Kinds

| kind | 行为 | v1 状态 |
|---|---|---|
| `static_site` | 校验 workspace HTML 入口，创建 deployment record，复用平台静态服务返回 URL | Implemented |
| `source_zip` | 打包 workspace 源码，返回下载 URL | Implemented |
| `container` | 返回 `not_supported` 状态卡，说明容器化部署未开放 | Implemented placeholder |

`POST deployments` body：

```json
{
  "kind": "static_site",
  "entry_path": "index.html",
  "requested_port": 8082
}
```

`source_zip` 必须排除 `.agenthub/`、`.git/`、`node_modules/`、`.venv/`、`__pycache__/`，且禁止打包 `.env`、`.ssh`、`secrets/`。

本轮不允许 agent runtime 执行 Netlify、Vercel、SSH、Docker、`npm run dev`、`vite --host`、`python -m http.server` 等部署或长驻服务命令。

## Deployment Status Block

聊天流中应新增部署状态卡片：

```ts
type DeploymentStatusBlock = {
  type: "deployment_status";
  deployment_id: string;
  kind: "static_site" | "source_zip" | "container";
  status: "queued" | "publishing" | "published" | "failed" | "stopped" | "not_supported";
  title?: string;
  url?: string;
  download_url?: string;
  error?: string;
  logs_preview?: string;
};
```

卡片职责：

- `published`：展示访问 URL、复制和打开入口。
- `source_zip`：展示源码下载入口。
- `failed`：展示错误原因和日志摘要。
- `not_supported`：展示容器化部署未开放说明。
- `stopped`：展示已停止状态。

## 生命周期

| 事件 | 行为 |
|---|---|
| agent run 开始 | 记录 workspace snapshot |
| agent run 结束 | diff snapshot，更新 artifact manifest |
| 用户启动 preview | 分配端口，启动平台静态 server |
| 用户重复启动 preview | 复用或重启当前 conversation session |
| 用户发送部署/发布/上线 | 创建 deployment record，执行平台受控部署 |
| 用户请求源码打包下载 | 创建 source zip export，返回下载 URL |
| 用户请求容器化部署 | 创建 `not_supported` 状态记录，不执行 Docker |
| SSE 断开 | 不影响已启动 preview；preview 由 TTL 管理 |
| Conversation 删除 | 当前停止 preview 并删除 DB record；release snapshot、source zip 和稳定 route token 的完整清理由 hardening 补齐 |
| Workspace 删除 | 停止 preview |

## Orchestrator 集成

Orchestrator 只做 workspace artifact 的只读存在性检查，不直接接管 preview / deployment 生命周期。平台 preview / deployment API 仍是唯一能启动、复用、停止 service 或失效 release route，并生成 URL 的组件。

Orchestrator 对 `requires_artifact=true` 或 `expected_output` 明确包含 artifact path 的子任务必须检查 artifact：

- expected artifact 存在：任务 `succeeded`。
- 子 agent `done` 但没有 artifact：任务 `artifact_missing`。
- `artifact_missing` 可触发 fallback agent。
- 不读取 `.env`、`.ssh`、`secrets/`、`.agenthub/`，不执行 shell，不监听端口。

Deployment tools：

- 用户只说“预览”时，Orchestrator 使用 `start_workspace_preview`。
- 用户说“部署 / 发布 / 上线”时，Orchestrator 使用 `create_deployment(kind="static_site")`。
- 用户说“源码打包 / 下载源码”时，Orchestrator 使用 `package_workspace_source`。
- 用户说“容器化部署”时，Orchestrator 使用 `create_deployment(kind="container")`，返回 `not_supported`。

## 安全规则

- `entry_path` 必须在 workspace 内。
- 禁止预览 `.env`、`.ssh`、`secrets/`、`.agenthub/`。
- Preview 静态 server 只能暴露当前 workspace；hardening 后正式 static release 只能暴露不可变 snapshot。
- 默认禁止目录列表。
- HTML 预览必须设置 sandbox / CSP。
- 平台 preview 进程不接收 provider API key。
- Deployment / source export 不打包或暴露敏感目录。
- Container deployment 在未实现隔离前只能返回 `not_supported`。

## 测试计划

- `snake.html` 新增后被识别为 previewable `html` artifact。
- `index.html` + `style.css` 被识别为同一 static web artifact。
- `package.json` 无静态入口时不自动启动 dev server。
- Agent 请求“预览到 8082”时只生成文件，不监听端口。
- 平台 preview API 为 artifact 返回 URL。
- 删除 conversation 后 preview PID 被清理。
- Orchestrator 能把 `done` 但无文件判为 `artifact_missing`。
- `static_site` deployment 返回 deployment status 和 URL。
- `source_zip` 可下载且不包含敏感目录。
- `container` 请求返回 `not_supported` 且不执行 Docker。

## 验收标准

- 用户能通过 workspace/artifact API 找到 agent 产物。
- 可静态预览 artifact 由平台 preview service 提供 URL。
- 8082 只由平台 service 管理。
- Agent runtime 不通过启动服务来证明 artifact 可用。
- 聊天中“部署”指令返回 `deployment_status` 卡片。
- 一键静态发布和源码打包下载由平台 tool 完成。
