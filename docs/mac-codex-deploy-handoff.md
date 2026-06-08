# AgentHub Mac Codex 本地部署交接文档

> 这份文档是给 Mac 电脑上的 Codex 使用的。  
> 目标：不依赖 GitHub，把另一台电脑导出的 AgentHub 源码、后端 Docker 镜像、数据库、workspace、uploads 和 runtime 登录态恢复到 Mac，并启动一个可测试的本地 AgentHub。

## 0. 你拿到的包应该长什么样

导出包目录通常叫：

```text
mac-codex-package/
  MAC_CODEX_READ_THIS.md
  package-manifest.json
  agenthub-source.tgz
  agenthub-backend-linux-amd64.tar
  agenthub.sql
  workspaces.tgz
  uploads-data.tgz
  claude-state.tgz
  opencode-state.tgz
  .env                  # 只有导出时显式选择 IncludeEnv 才会存在
  ENV_NOT_INCLUDED.txt  # 如果没有导出 .env，会有这个提示文件
```

有些文件可能不存在：

- 没有旧聊天：可能没有 `agenthub.sql`。
- 没有上传文件：可能没有 `uploads-data.tgz`。
- 没有 runtime 登录态：可能没有 `claude-state.tgz` / `opencode-state.tgz`。
- 没有导出 `.env`：需要手动配置 API key。

## 1. Mac 前置要求

先确认 Mac 上有：

```bash
docker --version
docker compose version
node --version
corepack --version
```

如果 Docker 没运行，先启动 Docker Desktop。

如果没有 pnpm，后续脚本会尝试用 Corepack 启用。

## 2. 解出源码

如果包里有 `agenthub-source.tgz`，在包的同级目录执行：

```bash
tar xzf mac-codex-package/agenthub-source.tgz
cd agenthub-github
```

如果用户已经手动复制了完整 `agenthub-github/` 项目目录，则直接：

```bash
cd agenthub-github
```

给脚本执行权限：

```bash
chmod +x scripts/start-agenthub-mac.command
chmod +x scripts/import-agenthub-mac-codex-package.sh
```

## 3. 一键导入并部署

推荐第一次导入时使用：

```bash
./scripts/import-agenthub-mac-codex-package.sh ../mac-codex-package --reset-volumes --restore-db
```

这个命令会：

1. 如果包里有 `.env`，复制到项目根。
2. 如果没有 `.env`，复制 `.env.example`。
3. `--reset-volumes` 会清空 Mac 上旧的 AgentHub Docker volumes。
4. 如果有 `agenthub-backend-linux-amd64.tar`，执行 `docker load`。
5. 使用 `docker-compose.mac-image.yml` 让 backend 直接用导入镜像。
6. 恢复 `workspaces.tgz`。
7. 启动 Postgres、Redis、Backend。
8. 恢复 uploads、Claude state、OpenCode state。
9. `--restore-db` 会导入 `agenthub.sql`。
10. 执行 `alembic upgrade head`。
11. 执行 `python -m app.seeds.seed_agents`。
12. 启动前端 dev server。
13. 打开 `http://localhost:5173`。

如果不想清空 Mac 上已有测试数据：

```bash
./scripts/import-agenthub-mac-codex-package.sh ../mac-codex-package --restore-db
```

如果只想启动后端，不启动前端：

```bash
./scripts/import-agenthub-mac-codex-package.sh ../mac-codex-package --reset-volumes --restore-db --skip-frontend
```

## 4. Apple Silicon 注意事项

导出的后端镜像通常是：

```text
linux/amd64
```

Intel Mac 可以直接运行。

Apple Silicon Mac 通常也可以通过 Docker Desktop 的 amd64 emulation 运行，但会慢一些。如果导入镜像启动失败、非常慢，或运行时出现架构问题，改用 Mac 本机重建：

```bash
./scripts/import-agenthub-mac-codex-package.sh ../mac-codex-package --reset-volumes --restore-db --rebuild
```

`--rebuild` 会忽略导入的 backend image tar，直接在 Mac 上 build backend 镜像。

## 5. 验证部署是否成功

服务地址：

```text
Frontend: http://localhost:5173
Backend docs: http://localhost:8000/docs
Health: http://localhost:8000/health
```

检查容器：

```bash
docker compose ps
```

检查后端健康：

```bash
curl -fsS http://localhost:8000/health
```

检查数据库中是否有旧会话：

```bash
docker compose exec postgres psql -U agenthub -d agenthub -c "select count(*) from conversations;"
docker compose exec postgres psql -U agenthub -d agenthub -c "select count(*) from messages;"
```

检查 workspace：

```bash
ls -la workspaces
docker compose exec backend ls -la /workspaces
```

## 6. 验证 External Runtime

OpenCode：

```bash
docker compose exec backend opencode --version
docker compose exec backend opencode auth list
```

Claude SDK：

```bash
docker compose exec backend python -c "import claude_agent_sdk; print('sdk ok')"
```

Claude CLI：

```bash
docker compose exec backend sh -lc 'HOME=$AGENTHUB_CLAUDE_AUTH_DIR claude -p "只回复 OK" --output-format text'
```

如果 `.env` 没有被导出，或者 runtime state 没恢复，Claude/OpenCode 可能不可用。这不代表项目没部署成功，只代表执行型 Agent 缺少认证。

## 7. 如果前端连到了错误后端

前端必须连本地 backend。脚本会使用：

```bash
VITE_DEV_PROXY_TARGET=http://localhost:8000 pnpm dev --host 0.0.0.0
```

如果手动启动前端，也必须这样启动：

```bash
cd frontend
VITE_DEV_PROXY_TARGET=http://localhost:8000 pnpm dev --host 0.0.0.0
```

否则 Vite 默认代理可能指向远端 demo 后端，导致看不到本地恢复的数据。

## 8. 常见失败与处理

### 8.1 Docker image load 后还是 build

确认运行的是导入脚本，不是普通 starter：

```bash
./scripts/import-agenthub-mac-codex-package.sh ../mac-codex-package --restore-db
```

导入镜像时会使用：

```bash
docker compose -f docker-compose.yml -f docker-compose.mac-image.yml up -d --no-build postgres redis backend
```

### 8.2 旧聊天没出现

检查是否传了 `--restore-db`：

```bash
./scripts/import-agenthub-mac-codex-package.sh ../mac-codex-package --reset-volumes --restore-db
```

再检查：

```bash
docker compose exec postgres psql -U agenthub -d agenthub -c "select count(*) from conversations;"
```

### 8.3 Workspace 不对

确认 `workspaces.tgz` 已恢复：

```bash
ls -la workspaces
docker compose exec backend ls -la /workspaces
```

### 8.4 上传文件下载失败

确认 `uploads-data.tgz` 存在，并已恢复到 `/app/data/uploads`：

```bash
docker compose exec backend ls -la /app/data/uploads
```

### 8.5 Claude/OpenCode 不可用

如果包里没有 `.env`，需要手动填写 provider key：

```bash
cp .env.example .env
open .env
```

至少配置需要的 key，例如：

```text
ANTHROPIC_API_KEY=...
DEEPSEEK_API_KEY=...
OPENAI_API_KEY=...
```

然后：

```bash
docker compose restart backend
```

## 9. 给 Mac Codex 的执行目标

请按顺序完成：

1. 解压 `agenthub-source.tgz` 到 `agenthub-github/`。
2. 进入项目目录。
3. 给脚本加执行权限。
4. 执行导入脚本。
5. 确认 backend health 通过。
6. 确认 frontend 打开。
7. 如果导出了数据库，确认旧会话数量不为 0。
8. 如果导出了 workspace，确认右侧 workspace 能显示旧目录。
9. 如果导出了 runtime state，执行 Claude/OpenCode smoke。
10. 如果 amd64 镜像在 Apple Silicon 上不可用，使用 `--rebuild` 重来。

成功标准：

- `http://localhost:5173` 可以打开。
- 可以注册/登录。
- 可以看到恢复的旧会话，或者能创建新会话。
- 后端 `/health` 正常。
- `docker compose ps` 中 postgres、redis、backend 都是 running/healthy。
