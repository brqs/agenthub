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

## 2026-05-25 — B2 拆解 B2-02 ClaudeAdapter 流式接入任务

### 任务
在 B2-01 完成 StreamingArtifactParser 后，拆解下一项 B2 开发任务：实现 ClaudeAdapter 真实 Anthropic 流式接入。

### 关键 Prompt
> b2-02的任务更新至docs文档

### AI 输出摘要
新增 `docs/b2-task-dispatch/B2-02-claude-adapter-streaming.md`，记录交给 Claude Code 的完整任务命令。同步更新 `docs/b2-task-dispatch/README.md` 的任务索引，将 B2-02 标记为待执行。

### 人工调整
B2-02 明确只允许修改 `backend/app/agents/adapters/claude.py` 和 `backend/tests/test_claude_adapter.py`，禁止修改 OpenAPI、BaseAgentAdapter、ContentBlock schema、OpenAIAdapter、CustomAdapter 和 Orchestrator。

### 经验
B2-01 产物解析器完成后，应先接入一个真实 Provider Adapter，验证 B1 SSE 层消费 StreamChunk 的主链路；OpenAIAdapter、CustomAdapter 和 Orchestrator 可作为后续独立任务继续拆分。

## 2026-05-25 — B2 建立 Agent 集成总体路线图

### 任务
在 B2-01 和 B2-02 推进后，补充一个更大的目标框架，统一后续 B2-03、B2-04、Orchestrator 和稳定性任务的拆分方向。

### 关键 Prompt
> 对了，我突然想起来还是得有个大的框架比较好，请你现在先生成一个目标整体框架，包含b2-01，b2-02,b2-03....等等你制定的任务和计划，

### AI 输出摘要
新增 `docs/b2-task-dispatch/B2-roadmap.md`，定义 B2 总目标、设计边界、阶段目标、B2-01 到 B2-13 的任务路线图、近期执行顺序、PR 边界建议和 Codex 审阅重点。同步更新 `docs/b2-task-dispatch/README.md`，加入路线图入口，并将 B2-02 状态调整为“已审阅，待 Git/PR”。

### 人工调整
路线图只作为目标框架，不提前为所有未来任务生成完整 Claude Code 执行命令。每个任务启动时仍需基于当时代码状态单独生成详细任务文档。

### 经验
在连续拆分子任务前，应先建立中长期路线图，避免后续 PR 之间目标重叠，也方便判断哪些任务需要 B1/F 协同、哪些可以由 B2 独立推进。

## 2026-05-25 — B2 拆解 B2-03 OpenAIAdapter 流式接入任务

### 任务
在 B2-02 ClaudeAdapter 合并后，启动 B2-03：实现 OpenAIAdapter 真实 OpenAI 流式接入。

### 关键 Prompt
> 接下来开始b2-03

### AI 输出摘要
确认当前分支为 `feat/B2-openai-adapter-streaming`，`origin/main` 已包含 B2-02 合并提交。检查本地 `openai` SDK 为 `2.31.0`，并基于当前 `openai.py` stub、`settings.openai_api_key/openai_base_url` 和 seed 默认模型 `gpt-4o` 创建 `docs/b2-task-dispatch/B2-03-openai-adapter-streaming.md`。

同步更新 `docs/b2-task-dispatch/README.md` 任务索引，将 B2-03 标记为待执行；更新 `docs/b2-task-dispatch/B2-roadmap.md`，将 B2-03 状态调整为“已拆解，待执行”。

### 人工调整
B2-03 明确只允许修改 `backend/app/agents/adapters/openai.py` 和 `backend/tests/test_openai_adapter.py`，禁止修改 OpenAPI、BaseAgentAdapter、ContentBlock schema、ClaudeAdapter、CustomAdapter 和 Orchestrator。

### 经验
OpenAIAdapter 应复用 B2-02 的 Adapter 模式：Provider client 创建、消息转换、delta 解析、StreamingArtifactParser 接入和错误映射保持一致；差异只应集中在 OpenAI SDK 的流式事件读取方式。

## 2026-05-25 — B2 拆解 B2-04 CustomAdapter 委托任务

### 任务
在 B2-02 ClaudeAdapter 和 B2-03 OpenAIAdapter 完成后，启动 B2-04：实现 CustomAdapter 根据配置委托上游 Provider。

### 关键 Prompt
> 好的，那就开始b2-04

### AI 输出摘要
先将本地 `main` 快进同步到最新 `origin/main`，再创建 `feat/B2-custom-agent-adapter` 分支。基于当前 `custom.py` stub、已完成的 `ClaudeAdapter` / `OpenAIAdapter`、registry 和 seed custom agent 配置，新增 `docs/b2-task-dispatch/B2-04-custom-adapter-delegation.md`。

同步更新 `docs/b2-task-dispatch/README.md`，将 B2-03 标记为已完成并加入 B2-04；更新 `docs/b2-task-dispatch/B2-roadmap.md`，将 B2-04 标记为“已拆解，待执行”，并调整近期执行顺序。

### 人工调整
B2-04 明确只允许修改 `backend/app/agents/adapters/custom.py` 和 `backend/tests/test_custom_adapter.py`。任务要求 CustomAdapter 不访问数据库、不调用 registry、不重复实现 Claude/OpenAI 流式逻辑，只负责选择上游 Adapter、注入 system prompt、过滤 `upstream_provider` 并转发 StreamChunk。

### 经验
CustomAdapter 应保持为轻量委托层：Provider 细节继续由 ClaudeAdapter/OpenAIAdapter 处理，CustomAdapter 只处理 custom agent 的配置解释和 system prompt 注入，避免形成第三套流式解析逻辑。
