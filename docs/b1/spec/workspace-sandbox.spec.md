# Workspace Sandbox Spec

> 每会话一个 sandbox 目录的隔离规范。被 [agent-runtime-pivot.adr.md](../../spec/agent-runtime-pivot.adr.md) §2.3 引用。
> 由 B1 实现，被 BuiltinAgent 与 ExternalAgent 共同遵守。

---

## 1. 目标

为每个 conversation 提供一个**隔离的文件系统沙箱**：

- Agent 在此目录内自由读写、跑命令
- 越界写操作（包括 `../` / 符号链接逃逸）必须被拒绝
- 前端能浏览目录树、预览文件、二次编辑文件
- 删除会话时自动清理

**MVP 不做**：Docker per-conversation、网络隔离、cgroup 资源限制（列为 P2）。

---

## 2. 数据模型

```python
# backend/app/models/workspace.py
class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    root_path: Mapped[str] = mapped_column(String(512))  # 绝对路径
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    last_accessed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

### 关系

- 1 Conversation : 1 Workspace（unique 约束）
- Conversation 删除 → Workspace 行删除 + 物理目录清理（service 层 cascade）

### Alembic migration

- 新增 `workspaces` 表
- 不需要回填（pivot 前的旧会话没有 workspace，懒创建）

---

## 3. 目录布局

### 3.1 基目录

```
宿主机：/var/lib/agenthub/workspaces/
容器内：/workspaces/   （docker-compose 卷挂载）
```

具体路径由 [backend/app/core/config.py](../../../backend/app/core/config.py) 的 `WORKSPACE_BASE_DIR` 控制（默认 `/workspaces`）。

### 3.2 每会话目录

```
/workspaces/<conversation_id>/
   ├── .agenthub/          ← 内部元数据，禁止 Agent 写
   │     └── manifest.json
   ├── README.md           ← 自动创建，含 conversation_id
   └── ...                 ← Agent 产物
```

`<conversation_id>` 使用完整 UUID，避免冲突。

### 3.3 生命周期

| 事件 | 行为 |
|---|---|
| Conversation 创建 | **不**立即创建 workspace（懒创建） |
| Agent 第一次需要 workspace_path | WorkspaceService 创建目录 + DB 行 + README |
| Conversation 删除 | 删除 workspaces 行 + `shutil.rmtree(root_path)`，并清理 preview / release / source zip / deployment 资源 |
| Preview 闲置超过 TTL | Janitor 停止 preview session 并清理隔离快照 |
| Source zip 过期 | Janitor 删除过期 zip 和孤儿目录 |

---

## 4. 路径校验规则（核心安全边界）

### 4.1 写操作校验

任何 Agent 调用 `write_file` / `bash`（写入相关）/ MCP 写操作前，必须执行：

```python
def validate_write_path(workspace_root: Path, user_path: str) -> Path:
    """
    返回安全的绝对路径；任何越界都抛 WorkspaceViolation。
    """
    candidate = (workspace_root / user_path).resolve()
    # 1. 必须落在 workspace_root 之内
    try:
        candidate.relative_to(workspace_root.resolve())
    except ValueError:
        raise WorkspaceViolation(f"path escapes workspace: {user_path}")
    # 2. 禁止 .agenthub/ 内部元数据
    if ".agenthub" in candidate.parts:
        raise WorkspaceViolation("cannot write to .agenthub/")
    # 3. 禁止 .git / .env / secrets
    forbidden = {".git", ".env", "secrets", ".ssh"}
    if any(p in forbidden for p in candidate.parts):
        raise WorkspaceViolation(f"forbidden path component: {user_path}")
    # 4. 禁止穿越符号链接（resolve 已展开，再次校验）
    if candidate.is_symlink():
        raise WorkspaceViolation("symlinks not allowed")
    return candidate
```

### 4.2 读操作校验

读取相对宽松，但仍需：

- 路径必须在 workspace 内
- 禁止读 `.agenthub/`（防止 Agent 通过元数据自举）
- 最大读 1 MB

### 4.3 Bash 命令校验

- 仅允许命令首词在白名单（见 [builtin-agent-framework.spec.md](../../b2/spec/builtin-agent-framework.spec.md) §3.2）
- `cwd` 强制为 workspace 根
- 不传 host 环境变量（白名单 `PATH` / `LANG` / `HOME`）
- 超时 30s（`asyncio.wait_for`）

---

## 5. WorkspaceService API

```python
# backend/app/services/workspace_service.py
class WorkspaceService:
    async def get_or_create(self, db, conversation_id: UUID) -> Workspace: ...
    async def delete(self, db, conversation_id: UUID) -> None: ...
    async def list_tree(
        self, workspace: Workspace, max_depth: int = 5
    ) -> TreeNode: ...
    async def read_file(
        self, workspace: Workspace, rel_path: str
    ) -> tuple[bytes, str]: ...  # (content, mime_type)
    async def write_file(
        self, workspace: Workspace, rel_path: str, content: bytes
    ) -> None: ...
```

所有方法内部调用 §4 的校验函数。

---

## 6. HTTP API（B1 暴露）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/workspaces/{conv_id}/tree` | 返回目录树 JSON |
| GET | `/api/v1/workspaces/{conv_id}/files/{path:path}` | 返回文件内容（含 mime sniff） |
| PUT | `/api/v1/workspaces/{conv_id}/files/{path:path}` | 前端二次编辑回写 |
| POST | `/api/v1/workspaces/{conv_id}/preview` | 启动或复用平台静态预览 |
| GET | `/api/v1/workspaces/{conv_id}/preview` | 查询 preview 状态 |
| DELETE | `/api/v1/workspaces/{conv_id}/preview` | 停止 preview |
| POST | `/api/v1/workspaces/{conv_id}/preview/verify` | 浏览器级验证 preview |
| POST | `/api/v1/workspaces/{conv_id}/deployments` | 创建 static site / source zip / container deployment |
| GET | `/api/v1/workspaces/{conv_id}/deployments` | 列出部署历史 |
| GET | `/api/v1/workspaces/{conv_id}/deployments/{deployment_id}` | 查询部署状态 |
| DELETE | `/api/v1/workspaces/{conv_id}/deployments/{deployment_id}` | 停止部署或删除源码包 |
| GET | `/api/v1/workspaces/{conv_id}/deployments/{deployment_id}/download` | 下载 source zip |

### 鉴权

- 全部 `Depends(get_current_user)` + 校验 conversation 归属当前用户
- 路径参数 `{path}` 必须走 §4 校验

### MIME sniff

- `.html` / `.htm` → `text/html`（前端用于 iframe 预览）
- `.css` / `.js` / `.mjs` / `.json` / `.md` / `.txt` → 对应 text/* 或 application/*
- 图片 → 直接二进制返回
- 其他 → `application/octet-stream`，前端提供下载

### iframe 预览注意

- 返回 `text/html` 时设置 CSP：`default-src 'self' 'unsafe-inline'; sandbox`
- 设置 `X-Frame-Options: SAMEORIGIN`
- 不允许跨域跳转

### Preview / Deployment 注意

- Preview 和 deployment URL 必须由平台服务生成，Agent runtime 不得编造 URL。
- Agent runtime 不直接启动 `python -m http.server`、`npm run dev`、`vite` 或 `node server.js`。
- Preview 服务隔离快照目录，不直接公开原始 workspace。
- Static release 是不可变快照，停止后 release token 立即失效。
- Source zip 必须排除 `.agenthub`、`.git`、`.env*`、`.ssh`、`secrets`、`node_modules`、虚拟环境和缓存目录。
- Container deployment 必须经过平台 worker 和 policy 校验；worker 关闭时只能返回受控失败或 `not_supported`，不能降级为 Agent 直接执行 Docker。

---

## 7. OpenAPI 同步

Workspace、Preview、Deployment 端点均已同步到 [shared/openapi.yaml](../../../shared/openapi.yaml)。
本 Spec 说明 B1 安全边界；机器可读契约以 `shared/openapi.yaml` 为准。

---

## 8. 验收用例

| # | 用例 | 验证 |
|---|---|---|
| 1 | Agent 第一次调 `write_file("App.tsx", ...)` | Workspace 自动创建；文件落在 `/workspaces/<conv>/App.tsx`；DB 有对应行 |
| 2 | Agent 调 `write_file("../etc/passwd", ...)` | 抛 WorkspaceViolation；返回 `tool_result(error, workspace_violation)` |
| 3 | Agent 调 `bash("curl http://evil.com")` | 拒绝（curl 不在白名单）；`tool_result(error)` |
| 4 | 前端 GET `/api/v1/workspaces/.../files/App.tsx` | 200 + text/plain 内容 |
| 5 | 前端 POST `/preview` | 返回平台生成 URL；预览服务读取隔离快照 |
| 6 | 前端 POST `/deployments` `kind=static_site` | 返回 deployment record 和不可变 release URL |
| 7 | 前端 POST `/deployments` `kind=source_zip` | 返回 download URL；源码包排除敏感路径 |
| 8 | 删除 conversation | workspace 行删除；物理目录、preview、release、zip 和 deployment 资源被清理 |

---

## 9. 不在本 Spec 范围

- Docker per-conversation 隔离（P2）
- 网络/CPU/内存资源限制（P2）
- 多副本/多机部署时的 workspace 路径协议（MVP 假设单机）
- Workspace 配额（每用户/每会话最大字节数）（P2，默认无限）
- 前端文件树、preview、deployment UI（由 F 负责）
