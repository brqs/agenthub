## 2026-05-25 — B2 搭建后端云端联调环境

### 任务
搭建并记录 AgentHub 后端云端联调环境。

### 关键 Prompt
> 配置云服务器后端环境，验证 Docker Compose 服务，并沉淀后端 API、PostgreSQL、Redis 和部署注意事项，方便团队联调。

### AI 输出摘要
新增后端云端联调文档，记录公网后端 API 地址、服务状态、前端联调配置、Docker 代理说明、常用命令和安全边界。

### 人工调整
云服务器 IP 由人工提供：`111.229.151.159`。服务器 Docker daemon 代理配置位于仓库外，文档中明确标记为服务器系统级配置。

后续检查确认当前数据库仍为空库：`backend/alembic/versions/` 只有 `.gitkeep`，`alembic heads` 为空，数据库中不存在 `alembic_version` 表，也没有业务表。因此需要 B1 先补初始建表 migration，再执行 `alembic upgrade head` 和 `seed_agents`。

### 经验
云端运行状态要和 Git 仓库保持边界清晰：可复用的配置说明和源码修复应提交到仓库，但 `.env`、API Key、数据库密码和服务器 daemon 代理配置不能提交。

## 2026-05-25 — B2 明确 AI 分工协作模式

### 任务
明确后续 B2 工作中的 AI 协作分工：Codex 负责总览、协调、任务拆解和最终审阅，Claude Code 负责执行拆解后的具体子任务。

### 关键 Prompt
> 接下来，我想完成分工协作，codex负责总览大局，分工和协调工作，拆解的子任务我将交由claude code进行执行，代码最后的审阅由你最终负责，把这个分工记录到你的上下文中，不要遗忘

### AI 输出摘要
Codex 将在后续协作中作为项目级协调者：维护上下文、识别模块边界、拆解任务、检查契约影响、给出交付顺序，并在 Claude Code 完成具体实现后做最终代码审阅。

### 人工调整
B2 明确指定 Claude Code 作为具体子任务执行者，Codex 不默认抢占实现工作，除非用户明确要求。

### 经验
复杂协作应先固定 AI 角色边界：一个 AI 负责全局判断和审阅，另一个 AI 负责执行，可减少上下文混乱、重复修改和目录所有权冲突。

## 2026-05-25 — B2 固化 Claude Code 子任务分发模板

### 任务
将“Codex 分发给 Claude Code 的子任务必须完整详细”的要求沉淀为 B2 可复用文档模板。

### 关键 Prompt
> 这个要求需不需要同步进文档
> 好的，那你执行操作

### AI 输出摘要
新增 `docs/b2-ai-task-dispatch-template.md`，明确 B2、Codex、Claude Code 的协作角色，以及 Codex 分发子任务时必须包含的背景、文件范围、禁止事项、实现目标、测试要求、验证命令和交付说明。

### 人工调整
决定暂不修改 `AGENTS.md`，因为该约定属于 B2 当前阶段的协作流程，还不是全项目宪法级规则。

### 经验
任务分发模板应独立沉淀，避免把阶段性个人工作流过早写入全局规则；等团队验证稳定后，再考虑升级到 `AGENTS.md`。

## 2026-05-25 — B2 创建子任务分发目录

### 任务
为 B2 方向创建专门的子任务分发目录，并沉淀第一个 Claude Code 执行任务。

### 关键 Prompt
> 这个可以写进docs吗，创建一个子文件夹放任务分工的内容

### AI 输出摘要
新增 `docs/b2-task-dispatch/`，包含任务索引 `README.md` 和 `B2-01-streaming-artifact-parser.md`。B2-01 文档保存了交给 Claude Code 的完整任务命令，后续 B2-02、B2-03 可继续放在同一目录。

### 人工调整
任务文档作为阶段性执行记录放入 `docs/b2-task-dispatch/`，不升级为全局 `AGENTS.md` 规则。

### 经验
长期协作中，任务分发应有独立目录和编号，方便追踪 Claude Code 的执行范围、Codex 的审阅入口，以及后续答辩时展示 AI 协作过程。

## 2026-05-25 — B2 记录本地 Anaconda 开发环境

### 任务
记录 B2 本地 Python 开发环境，避免后续 Claude Code 重复创建或安装 Python 环境。

### 关键 Prompt
> 对了，我在本地开发使用的是anaconda的LLMAgent环境，请你也在文档中注明，以便之后的claude重复安装python环境

### AI 输出摘要
在 `docs/b2-task-dispatch/README.md` 和 `docs/b2-ai-task-dispatch-template.md` 中记录 B2 默认使用 Anaconda 环境 `LLMAgent`，并将 B2-01 的验证命令更新为 `conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py`。同时注明缺少项目依赖时应在现有 `LLMAgent` 环境内安装 `backend` 依赖，不要新建 Python 环境。

### 人工调整
该环境约定仅作为 B2 本地开发和 Claude Code 执行任务的说明，不改变 Docker Compose 或生产环境配置。

### 经验
AI 执行任务前应优先复用已有本地环境；环境名称和验证命令写入任务文档，可以减少重复安装和依赖版本漂移。

## 2026-05-25 — B2 新增 Git/PR Claude 协作角色

### 任务
新增一个专门负责 Git 和 PR 操作的 Claude 角色，并沉淀操作边界、流程和可直接发送的初始化指令。

### 关键 Prompt
> 我现在再创建一个claude，负责管理git和pr操作，请你同样的进行创建文档跟指令要求

### AI 输出摘要
新增 `docs/git-pr-ops/README.md`，记录 Git/PR Claude 的职责、禁止事项、标准流程、分支命名、commit 规范和 PR 模板。新增 `docs/git-pr-ops/claude-git-pr-instructions.md`，提供可直接发送给 Git/PR Claude 的初始化指令。同步更新 `docs/b2-task-dispatch/README.md`，将 Git/PR Claude 纳入 B2 协作方式。

### 人工调整
Git/PR Claude 只负责 Git 状态整理、commit、push 和 PR 准备，不替代 Claude Code 写业务代码，也不替代 Codex 做最终代码审阅。

### 经验
把代码执行、代码审阅、Git/PR 操作拆成不同 AI 角色，可以降低误提交、跨边界改动和未审阅代码进入 PR 的风险。
