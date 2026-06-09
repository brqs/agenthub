# AgentHub macOS 本地测试打包与迁移说明

> 用途：不上传 GitHub，只把当前 AgentHub 项目打包给一台 Mac 做本地测试。  
> 配套脚本：`scripts/start-agenthub-mac.command`

## 1. Mac 需要先安装什么

Mac 上需要：

- Docker Desktop for Mac
- Node.js 20+，推荐 22
- pnpm，或 Node 自带 Corepack

检查命令：

```bash
docker --version
docker compose version
node --version
corepack --version
```

如果没有 pnpm，脚本会尝试通过 Corepack 启用 pnpm。

## 2. 最小测试包应该包含什么

如果只是测试能不能跑起来，打包项目源码即可：

```text
agenthub-github/
  backend/
  frontend/
  shared/
  docs/
  workspaces/
  docker-compose.yml
  docker-compose.override.yml
  .env.example
  scripts/start-agenthub-mac.command
```

建议不要打包：

```text
.git/
frontend/node_modules/
backend/.pytest_cache/
.ruff_cache/
frontend/dist/
*.log
```

`.env` 可以带过去，但里面可能有真实 API key。只给可信测试机时才带。

## 3. 在 Mac 上启动

把项目解压到 Mac 后：

```bash
cd agenthub-github
chmod +x scripts/start-agenthub-mac.command
./scripts/start-agenthub-mac.command
```

第一次在 Mac 上运行时，通常需要重新 build backend 镜像：

```bash
./scripts/start-agenthub-mac.command --rebuild
```

脚本会做这些事：

1. 检查 Docker / Compose / curl。
2. 如果没有 `.env`，复制 `.env.example`。
3. 启动 `postgres`、`redis`、`backend`。
4. 执行 `alembic upgrade head`。
5. 执行 `python -m app.seeds.seed_agents`。
6. 等待 `http://localhost:8000/health`。
7. 安装前端依赖，如果 `frontend/node_modules` 不存在。
8. 后台启动 `VITE_DEV_PROXY_TARGET=http://localhost:8000 pnpm dev --host 0.0.0.0`。
9. 打开 `http://localhost:5173`。

只启动后端，不启动前端：

```bash
./scripts/start-agenthub-mac.command --skip-frontend
```

## 4. 空环境测试

如果你不需要旧聊天记录，直接启动即可。启动后访问：

```text
Frontend: http://localhost:5173
Backend docs: http://localhost:8000/docs
Health: http://localhost:8000/health
```

登录注册、创建会话、发送消息都走 Mac 本地的新数据库。

## 5. 搬迁旧数据到 Mac

如果希望 Mac 上看到旧聊天、旧 workspace、上传文件、runtime 登录态，需要额外迁移数据。

### 5.1 在原电脑导出数据库

在项目根目录执行：

```bash
mkdir -p mac-export
docker compose exec -T postgres pg_dump -U agenthub agenthub > mac-export/agenthub.sql
```

如果你的 `.env` 改过数据库用户名或库名，用实际值替换：

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > mac-export/agenthub.sql
```

### 5.2 导出 workspace

`workspaces/` 是项目根目录下的 bind mount，直接打包即可：

```bash
tar czf mac-export/workspaces.tgz workspaces
```

Windows PowerShell 如果没有 `tar` 问题，也可以直接压缩 `workspaces` 文件夹。

### 5.3 导出 uploads-data volume

上传文件在 Docker named volume `uploads-data` 里。用 backend 容器导出：

```bash
docker compose run --rm -v "$PWD/mac-export:/export" backend \
  sh -lc 'tar czf /export/uploads-data.tgz -C /app/data/uploads .'
```

如果当前没有上传文件，这一步可以跳过。

### 5.4 导出 Claude/OpenCode 登录态

Claude Code 登录态：

```bash
docker compose run --rm -v "$PWD/mac-export:/export" backend \
  sh -lc 'tar czf /export/claude-state.tgz -C "$AGENTHUB_CLAUDE_AUTH_DIR" .'
```

OpenCode 登录态：

```bash
docker compose run --rm -v "$PWD/mac-export:/export" backend \
  sh -lc 'tar czf /export/opencode-state.tgz -C "$AGENTHUB_OPENCODE_AUTH_DIR" .'
```

注意：登录态和 `.env` 一样敏感，只能给可信测试机。

### 5.5 把导出包复制到 Mac

最终复制：

```text
agenthub-github/
mac-export/
  agenthub.sql
  workspaces.tgz
  uploads-data.tgz
  claude-state.tgz
  opencode-state.tgz
```

## 6. 在 Mac 上恢复旧数据

先启动一次环境：

```bash
cd agenthub-github
chmod +x scripts/start-agenthub-mac.command
./scripts/start-agenthub-mac.command --rebuild --skip-frontend
```

### 6.1 恢复数据库

如果 Mac 上是全新数据库：

```bash
cat mac-export/agenthub.sql | docker compose exec -T postgres psql -U agenthub -d agenthub
```

如果已经有测试数据，建议先清空 volume 后再恢复：

```bash
docker compose down -v
./scripts/start-agenthub-mac.command --skip-frontend
cat mac-export/agenthub.sql | docker compose exec -T postgres psql -U agenthub -d agenthub
```

恢复后再执行迁移，确保 schema 跟当前代码一致：

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m app.seeds.seed_agents
```

### 6.2 恢复 workspace

```bash
rm -rf workspaces
tar xzf mac-export/workspaces.tgz
```

如果压缩包里不是 `workspaces/` 顶层目录，就手动把内容放到项目根的 `workspaces/`。

### 6.3 恢复上传文件 volume

```bash
docker compose run --rm -v "$PWD/mac-export:/export" backend \
  sh -lc 'mkdir -p /app/data/uploads && tar xzf /export/uploads-data.tgz -C /app/data/uploads'
```

### 6.4 恢复 Claude/OpenCode 登录态

Claude Code：

```bash
docker compose run --rm -v "$PWD/mac-export:/export" backend \
  sh -lc 'mkdir -p "$AGENTHUB_CLAUDE_AUTH_DIR" && tar xzf /export/claude-state.tgz -C "$AGENTHUB_CLAUDE_AUTH_DIR"'
```

OpenCode：

```bash
docker compose run --rm -v "$PWD/mac-export:/export" backend \
  sh -lc 'mkdir -p "$AGENTHUB_OPENCODE_AUTH_DIR" && tar xzf /export/opencode-state.tgz -C "$AGENTHUB_OPENCODE_AUTH_DIR"'
```

## 7. Runtime 验证

OpenCode：

```bash
docker compose exec backend opencode --version
docker compose exec backend opencode auth list
```

Claude Code SDK / CLI：

```bash
docker compose exec backend python -c "import claude_agent_sdk; print('sdk ok')"
docker compose exec backend sh -lc 'HOME=$AGENTHUB_CLAUDE_AUTH_DIR claude -p "只回复 OK" --output-format text'
```

如果不迁移登录态，也可以只在 Mac 的 `.env` 里配置 provider key，例如：

```text
ANTHROPIC_API_KEY=...
DEEPSEEK_API_KEY=...
OPENAI_API_KEY=...
```

然后重启 backend：

```bash
docker compose restart backend
```

## 8. 常见问题

### 8.1 Docker build 很慢或失败

backend 镜像会安装 Node.js、Claude Code CLI、OpenCode CLI、Playwright Chromium。第一次 build 慢是正常的。

如果网络访问 Docker registry 或 npm 失败，先检查 Docker Desktop 代理，再在 `.env` 里配置：

```text
HTTP_PROXY=
HTTPS_PROXY=
ALL_PROXY=
```

然后：

```bash
./scripts/start-agenthub-mac.command --rebuild
```

### 8.2 看不到旧聊天记录

通常是没有恢复数据库，或者恢复到了不同的 `POSTGRES_DB`。

检查：

```bash
docker compose exec postgres psql -U agenthub -d agenthub -c "select count(*) from conversations;"
docker compose exec postgres psql -U agenthub -d agenthub -c "select count(*) from messages;"
```

### 8.3 Workspace 空了

通常是没有复制 `workspaces/`，或者数据库里的 conversation id 对应目录不在 `workspaces/` 下。

检查：

```bash
ls -la workspaces
docker compose exec backend ls -la /workspaces
```

### 8.4 前端没有启动

看日志：

```bash
cat .agenthub-mac-frontend.log
```

手动启动：

```bash
cd frontend
pnpm install
VITE_DEV_PROXY_TARGET=http://localhost:8000 pnpm dev --host 0.0.0.0
```

### 8.5 端口冲突

常用端口：

```text
5173 frontend
8000 backend
5432 postgres
6379 redis
8081-8085 container deployment
8082-8182 preview
```

如果 5173 被占用，脚本会跳过前端启动。你可以手动换端口：

```bash
cd frontend
pnpm dev --host 0.0.0.0 --port 5174
```

## 9. 停止和清理

停止后端栈：

```bash
docker compose down
```

停止前端：

```bash
if [ -f .agenthub-mac-frontend.pid ]; then
  kill "$(cat .agenthub-mac-frontend.pid)" || true
  rm .agenthub-mac-frontend.pid
fi
```

删除所有 Docker 数据，谨慎使用：

```bash
docker compose down -v
```

这会删除 Postgres、uploads、Claude/OpenCode 登录态 volume。
