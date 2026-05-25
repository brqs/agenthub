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

## 2026-05-25 — B2 拆解 B2-05 Agent 配置校验任务

### 任务
在 B2-04 CustomAdapter 合并后，启动 B2-05：补齐 Agent 创建/更新时的 provider、model、system_prompt、upstream_provider 和 numeric config 校验，并让内置 Agent seed 与运行时规则保持一致。

### 关键 Prompt
> 检查更新文档，现在开始b2-05

### AI 输出摘要
确认当前 `main` 已包含 B2-04 合并提交，新增 `docs/spec/agent-config-validation.spec.md` 和 `docs/b2-task-dispatch/B2-05-agent-config-validation.md`。同步更新 B2 任务索引与路线图，将 B2-04 标记为已完成，将 B2-05 标记为已拆解、待执行。

### 人工调整
B2-05 明确允许修改 `backend/app/api/v1/agents.py`、`backend/app/schemas/agent.py`、`backend/app/seeds/seed_agents.py`、`shared/openapi.yaml` 和 `docs/api-spec.md`；由于涉及 AgentConfig 契约说明，要求 PR 描述中标注契约变更，并说明不涉及 BaseAgentAdapter 或 ContentBlock。

### 经验
当 B2 任务从 Adapter 内部实现扩展到 Agent CRUD 和 OpenAPI 配置字段时，应先写 Spec 和任务文档，明确共享文件边界，再交给 Claude Code 执行，避免把配置校验、路由更新和契约文档拆散到多个不一致的 PR 中。

## 2026-05-25 — B2 拆解 B2-06 SSE error 状态持久化任务

### 任务
在 B2-05 合并后，启动 B2-06：补齐 SSE 层消费 Adapter error chunk 和 Adapter 异常时的消息状态持久化规则与回归测试。

### 关键 Prompt
> 现在开始b2-06

### AI 输出摘要
确认当前 `main` 已包含 B2-05 合并结果，工作区干净。读取 `backend/app/api/v1/stream.py` 后发现当前 SSE 层已有部分 error chunk 处理逻辑，因此 B2-06 被拆解为“补齐测试并修复未覆盖异常路径”，而不是重新实现 SSE。

新增 `docs/spec/stream-error-status.spec.md` 和 `docs/b2-task-dispatch/B2-06-stream-error-status.md`，同步更新 B2 任务索引与路线图，将 B2-05 标记为已完成，将 B2-06 标记为已拆解、待执行。

### 人工调整
B2-06 明确允许修改 `backend/app/api/v1/stream.py` 与 `backend/tests/test_b1_quality.py`；由于 `stream.py` 是 B1-owned 文件，任务文档标注为 B1/B2 协同任务。任务不允许修改 Adapter、BaseAgentAdapter、StreamChunk schema、OpenAPI 或 ContentBlock。

### 经验
跨边界任务启动前应先读现有实现和测试，避免把“已有部分修复”误判为“完全未实现”。B2-06 的关键不是大改 SSE，而是用回归测试锁住 error chunk、异常路径和 partial content 持久化行为。

## 2026-05-25 — B2 拆解 B2-07 ArtifactParser v2 富媒体识别增强任务

### 任务
在 B2-06 合并后，启动 B2-07：增强 `StreamingArtifactParser` 对 diff fence 和独立 URL 的识别，并让 SSE 持久化层保存既有 `diff` / `web_preview` ContentBlock。

### 关键 Prompt
> 现在开始进行b2-07的开发

### AI 输出摘要
确认 `ContentBlock` 和 `StreamChunk.block_type` 已经包含 `diff` 与 `web_preview`，因此 B2-07 不需要新增 schema 类型或修改 OpenAPI。新增 `docs/spec/artifact-parser-v2.spec.md` 和 `docs/b2-task-dispatch/B2-07-artifact-parser-v2.md`，将任务限定为 parser 增强、`_ContentAccumulator` 最小扩展和后端测试覆盖。

同步更新 `docs/b2-task-dispatch/README.md` 与 `docs/b2-task-dispatch/B2-roadmap.md`，将 B2-06 标记为已完成，将 B2-07 标记为已拆解、待执行，并增加建议分支 `feat/B2-artifact-parser-v2`。

### 人工调整
B2-07 明确不抓取网页标题、不做网络 I/O、不新增第三方依赖；独立 URL 只生成带 url 的 `web_preview` block。由于 `stream.py` 属于 B1-owned 文件，任务文档把 `_ContentAccumulator` 扩展标记为 B1/B2 协同边界，只允许做持久化所需的最小改动。

### 经验
当已有 schema 已覆盖目标 block 类型时，应优先复用现有契约，而不是为了 parser v2 新增字段。富媒体识别不仅要看 parser 输出，还必须检查 SSE 持久化层和前端流式消费能力，否则容易出现“流里有 block，但落库或渲染丢失”的断层。

## 2026-05-25 — B2 执行 B2-07 ArtifactParser v2 富媒体识别增强

### 任务
执行 B2-07：增强 `StreamingArtifactParser` 对 diff fence 和独立 URL 的识别，并让 SSE 持久化层保存既有 `diff` / `web_preview` ContentBlock。

### 关键 Prompt
> 请执行 B2-07。先阅读 docs/spec/artifact-parser-v2.spec.md、docs/b2-task-dispatch/B2-07-artifact-parser-v2.md、AGENTS.md。严格按 B2-07 文档实现和测试。不要修改禁止范围内的文件，不要提交 commit，不要 push，不要创建 PR。

### AI 输出摘要
1. 修改 `backend/app/agents/artifact_parser.py`：
   - 增加 `_is_standalone_url` 和 `_emit_text_buffer`，在 TEXT 状态下按行检测独立 URL 并拆分为 `web_preview` block。
   - CODE_LANG 中识别 `diff`/`patch`/`udiff` 语言，输出 `block_type="diff"`，delta 复用现有 `text_delta`。
   - 保持代码围栏跨 chunk 稳定性、未闭合 fence flush 收尾、行内 URL 保持 text 等既有行为。
2. 修改 `backend/app/api/v1/stream.py`：
   - `_ContentAccumulator` 扩展 `diff` 与 `web_preview` block 支持。
   - diff：累积 raw diff text，block_end 时通过 `_parse_diff` 提取 filename/before/after，降级为可读 diff block。
   - web_preview：透传 metadata url/title/description/thumbnail_url。
   - `to_list()` 统一调用 `_finalize_current()`，避免中断时保存非法 diff 格式。
3. 新增/修改测试：
   - `backend/tests/test_artifact_parser.py`：新增 7 个测试覆盖 diff fence、patch fence、code fence、独立 URL、行内 URL、URL 跨 chunk、diff fence 跨 chunk。
   - 新建 `backend/tests/test_stream_content_blocks.py`：新增 2 个集成测试覆盖 diff 和 web_preview 的 SSE 持久化。
4. 验证结果：pytest 全部通过（15 + 2 + 10 = 27 项），ruff 通过，无回归。

### 人工调整
无人工调整。Claude Code 完全按 B2-07 文档范围执行，未触碰禁止文件。

### 经验
- Parser 的 TEXT 状态引入“按行缓冲”后，需要小心处理无换行符的纯 URL 输入（如单个 URL 字符串），否则会被误判为普通 text。
- `_ContentAccumulator` 的 diff 解析放在 `block_end` 和 `to_list()` 中统一处理，可避免流中断时落库格式不合法。
- 跨 chunk URL 识别采取保守策略：不完整行保留在 buffer，宁可延迟识别也不提前拆错；flush 时最终兜底。

## 2026-05-25 — B2 拆解 B2-08 Orchestrator Spec 任务

### 任务
启动 B2-08：为后续多 Agent Orchestrator 实现先沉淀 Spec、任务拆解 Prompt、事件流规则和 PR 边界。

### 关键 Prompt
> 现在开始进行b2-08的开发，分别给出git Claude和b2-08 claude 的命令

### AI 输出摘要
确认 B2-08 不应直接实现完整 Orchestrator，而是先创建面向 Claude Code 的任务文档：`docs/b2-task-dispatch/B2-08-orchestrator-spec.md`。该文档要求 Claude Code 创建 `docs/spec/orchestrator.spec.md`，并定义 task decomposition、`agent_switch` 事件语义、子 Agent 顺序调度、`block_index` 重映射和失败降级边界。

同步更新 `docs/b2-task-dispatch/README.md` 与 `docs/b2-task-dispatch/B2-roadmap.md`，将 B2-08 标记为“已拆解，待执行”，并把 Orchestrator 后续实现拆成 B2-09 顺序调度与 B2-10 失败降级。

### 人工调整
Git/PR Claude 的指令保持简短：只需从最新 `main` 创建 `feat/B2-orchestrator-spec` 分支，不承载 B2-08 的长任务说明。B2-08 Claude Code 的完整执行命令沉淀在任务文档中，后续直接复制文档内容执行。

### 经验
长任务命令应进入 `docs/b2-task-dispatch/`，聊天窗口只保留入口命令和分支名。这样 Git/PR Claude 与实现 Claude 的职责不会混淆，也能减少重复粘贴导致的上下文偏差。

## 2026-05-25 — B2 并行拆解 B2-09 Orchestrator 调度任务

### 任务
在 B2-08 Spec 任务启动后，并行准备 B2-09：Orchestrator 子 Agent 顺序调度与 `block_index` 重映射。

### 关键 Prompt
> 并行开始b2-09的工作内容

### AI 输出摘要
新增 `docs/b2-task-dispatch/B2-09-orchestrator-dispatch.md`，将 B2-09 定义为基于 B2-08 Spec 的实现任务：读取外层注入的 task plan 和子 Adapter，串行调用子 Agent，发出 `agent_switch`，转发子 Agent `StreamChunk` 并重映射 `block_index`，最后输出 summary 和 `done`。

同步更新 `docs/b2-task-dispatch/README.md` 与 `docs/b2-task-dispatch/B2-roadmap.md`：B2-07 标记为已完成，B2-09 标记为“已拆解，待 B2-08 Spec 完成后执行”。

### 人工调整
B2-09 允许提前准备任务文档，但实现必须等待 `docs/spec/orchestrator.spec.md` 存在并明确输入/输出规则。为了避免 Orchestrator 直接访问数据库，B2-09 文档要求使用外层注入的 `tasks` / `sub_adapters` / `adapter_factory`，不修改 registry、B1 SSE、seed、OpenAPI 或前端。

### 经验
并行推进依赖任务时，应把“文档拆解可并行”和“代码实现需等待上游契约”分开。B2-09 的核心不是抢先写调度代码，而是提前固定代码边界和测试标准，等 B2-08 Spec 落地后即可快速执行。

## 2026-05-25 — B2 执行 B2-08 Orchestrator Spec 与任务拆解 Prompt

### 任务
执行 B2-08：阅读 AGENTS.md、docs/b2-task-dispatch/B2-roadmap.md、docs/tech-architecture.md 和全部 agents 代码，然后新建 `docs/spec/orchestrator.spec.md` 并更新相关任务文档。

### 关键 Prompt
> 请执行 B2-08。先阅读 AGENTS.md，然后阅读 docs/b2-task-dispatch/B2-08-orchestrator-spec.md，并严格按该文档完成任务。不要 commit，不要 push，不要创建 PR，完成后交给 Codex 审阅。

### AI 输出摘要
1. 新建 `docs/spec/orchestrator.spec.md`：
   - 定义 Orchestrator 输入（标准 `stream()` 签名 + 外层注入 `available_agents`）、输出（标准 `StreamChunk` 序列，不新增字段）。
   - 明确 Orchestrator 在 group chat 中的 6 项职责边界（任务拆解、子 Agent 选择、流式调度、block_index 重映射、失败降级、最终摘要）。
   - 定义 `SubTask` 结构化格式（`task_id`, `agent_id`, `title`, `instruction`, `depends_on`, `priority`, `expected_output`）。
   - 定义子 Agent 顺序调度规则：按 `priority` 排序，检查 `depends_on`，通过 config 注入的 `sub_adapters` / `adapter_factory` 获取子 Agent Adapter；registry 生产接线留给后续 B1/B2 协同任务。
   - 定义 `agent_switch` 事件语义：`from_agent="orchestrator"`, `to_agent`, `task`，切换前发出，不占用 `block_index`。
   - 定义 `block_index` 重映射算法：维护全局 `global_block_offset`，子 Agent `start`/`done` 被吞掉，其余 chunk 重映射后外发，确保全局单调递增。
   - 定义失败降级策略：单个子 Agent 失败不中断主流程，fallback 到文本说明块，最终 summary 列出 `SUCCEEDED`/`FAILED`/`SKIPPED`；任务拆解失败 fallback 到单 Agent 模式。
   - 明确不修改 `BaseAgentAdapter`、`StreamChunk`、`ContentBlock`、OpenAPI 的约束。
   - 制定 B2-09（顺序调度与 block_index 重映射，10 项验收标准）和 B2-10（失败降级与部分成功输出，7 项验收标准）的验收标准。
2. 更新 `docs/b2-task-dispatch/B2-08-orchestrator-spec.md`：追加执行结果摘要。
3. 更新 `docs/b2-task-dispatch/README.md`：将 B2-08 状态从“已拆解，待执行”改为“进行中”。
4. 更新 `docs/b2-task-dispatch/B2-roadmap.md`：将 B2-08 状态改为“进行中”。
5. 未修改任何 `.py` / `.ts` / `.yaml` 代码文件。

### 人工调整
无人工调整。Claude Code 完全按 B2-08 文档范围执行，未触碰禁止文件，未修改代码。

### 经验
- Orchestrator Spec 应先于代码实现，因为涉及多个子 Agent 的流式聚合、block_index 重映射和失败降级，需要在前端 SSE 消费层、后端 SSE 持久化层和 Adapter 层之间对齐语义。
- `agent_switch` 和 `from_agent`/`to_agent`/`task` 字段在 `types.py` 中已预先定义，Spec 无需新增 schema 字段，只需明确语义即可。
- 将 B2-08/B2-09/B2-10 拆成三个独立 PR（spec → 调度 → 降级），可避免一个 PR 同时改动文档和核心编排逻辑，降低审阅复杂度。

## 2026-05-25 — B2 执行 B2-09 Orchestrator 顺序调度

### 任务
实现 B2-09：在不修改共享契约和生产 registry 接线的前提下，让 Orchestrator 通过 config 注入的任务计划和子 Adapter 顺序调度子 Agent，并重映射 `block_index`。

### 关键 Prompt
> 请执行 B2-09。先阅读 AGENTS.md，然后阅读 docs/spec/orchestrator.spec.md 和 docs/b2-task-dispatch/B2-09-orchestrator-dispatch.md。严格按文档实现：只做注入式顺序调度；通过 config 注入的 tasks 和 sub_adapters / adapter_factory 获取子 Agent；不做真实 LLM 任务拆解；不做 registry DB 生产接线；不修改 OpenAPI / BaseAgentAdapter / StreamChunk / ContentBlock；不修改 frontend；不 commit，不 push，不创建 PR。完成后运行文档要求的 pytest / ruff / mypy，并把结果交给 Codex 审阅。

### AI 输出摘要
1. 更新 `backend/app/agents/orchestrator.py`：
   - 从 `config` / `default_config` 读取 `tasks`。
   - 支持通过注入的 `sub_adapters` 或 `adapter_factory` 获取子 Agent Adapter。
   - 按 `priority` 升序串行调度任务，并在每个子 Agent 前发出 `agent_switch`。
   - 子 Agent `start` / `done` 不外发，`block_start` / `delta` / `block_end` 通过本地映射表重写 `block_index`。
   - 子 Agent `error` chunk 被转换为普通 text 失败说明块，不直接外发 `error`。
   - 输出 planning text block、每个 Agent 的 header text block、summary text block 和最终 `done`。
2. 新增 `backend/tests/test_orchestrator.py`：
   - 覆盖单/多任务顺序、`agent_switch`、`block_index` 无冲突、metadata/delta 保留、`adapter_factory` 注入、缺少任务计划或 Adapter 注入时的 clear error、子 Agent error chunk 拦截。
3. 未修改 `BaseAgentAdapter`、`StreamChunk`、`ContentBlock`、OpenAPI、registry、backend API、frontend 或生产 seed。

### 人工调整
首轮 ruff 指出 import 排序、`StrEnum` 和循环变量命名问题；后续为保持小函数约束抽出 `_run_task`，并按 mypy 结果修正返回类型注解。未做 commit、push 或 PR。

### 经验
- B2-09 的核心边界是“注入式可测调度”，不要为了演示提前接生产 registry 或真实 LLM 任务拆解。
- block index 重映射使用“原始 index → 全局 index”的 per-subtask 映射表，比固定 offset 更稳，可处理子 Agent 原始 index 不连续的情况。
- 子 Agent 的 `error` chunk 不能透传，否则上层 SSE 可能把整个 Orchestrator message 标记为 error；当前仅做 error chunk 拦截，Adapter 抛异常、复杂失败降级和部分成功策略留给 B2-10。

## 2026-05-25 — B2 拆解 B2-10 Orchestrator 失败降级任务

### 任务
启动 B2-10：在 B2-09 注入式顺序调度基础上，补齐 Orchestrator 的失败降级、部分成功输出、依赖跳过和 fallback adapter 测试路径。

### 关键 Prompt
> 请执行 B2-10。先阅读 AGENTS.md，然后阅读 docs/spec/orchestrator.spec.md 和 docs/b2-task-dispatch/B2-10-orchestrator-fallback.md。严格按文档实现：只增强 Orchestrator 失败降级；捕获子 Agent stream 异常、adapter_factory 异常和 error chunk；失败任务输出普通 text block；后续不依赖失败任务的任务继续执行；依赖失败任务的任务标记 skipped；所有任务失败也必须 summary + done；任务计划非法时仅在提供 fallback adapter 的情况下走单 Agent fallback。不要实现真实 LLM 任务拆解，不接 registry/seed，不改 OpenAPI / BaseAgentAdapter / StreamChunk / ContentBlock，不改 frontend，不 commit，不 push，不创建 PR。完成后运行 pytest / ruff / mypy / 全量 pytest，并交给 Codex 审阅。

### AI 输出摘要
1. 新增 `docs/b2-task-dispatch/B2-10-orchestrator-fallback.md`：
   - 明确 B2-10 只处理 Orchestrator 失败降级，不做 retry、timeout、并发调度或生产 registry 接线。
   - 规定子 Agent `stream()` 抛异常时保留 partial content，并追加 text failure block。
   - 规定 `adapter_factory` 异常、子 Agent `error` chunk、依赖失败跳过和全失败仍 `done` 的行为。
   - 为任务计划不可用场景定义测试用 fallback adapter 注入方式。
   - 给出 6 类必须覆盖的单元测试和验证命令。
2. 更新 `docs/b2-task-dispatch/README.md` 和 `docs/b2-task-dispatch/B2-roadmap.md`：
   - 将 B2-08 / B2-09 标记为已完成。
   - 将 B2-10 标记为“已拆解，待执行”。
   - 将当前推荐执行顺序推进到 B2-10 / B2-11 / B2-12。

### 人工调整
当前工作区从 `feat/B2-orchestrator-dispatch` 切出 `feat/B2-orchestrator-fallback`，以避免 B2-10 文档和后续代码混入 B2-09 PR。

### 经验
- Orchestrator 的失败降级要区分“任务级失败”和“编排器 fatal error”：前者应转成普通文本并继续，后者才 yield `error`。
- B2-10 仍不应该接真实 registry 或 LLM task decomposition；fallback adapter 先通过 config 注入形成可测闭环。

## 2026-05-25 — B2 拆解 B2-11 Provider resilience 任务

### 任务
启动 B2-11：为 Claude / OpenAI / DeepSeek / Custom Adapter 统一 retry、timeout、rate-limit 和上游错误映射策略。

### 关键 Prompt
> 请执行 B2-11。先阅读 AGENTS.md，然后阅读 docs/spec/provider-resilience.spec.md 和 docs/b2-task-dispatch/B2-11-provider-resilience.md。严格按文档实现：只修改 Provider Adapter 及其测试；setup 阶段 transient error 可配置重试；rate limit 默认不重试；timeout / connection / upstream error 输出标准 StreamChunk(error)；内容已经开始输出后不得重试，必须先 flush parser 再输出 error；DeepSeek 继承 OpenAI resilience；Custom 不做二次 retry，只转发上游 chunk。不要修改 BaseAgentAdapter / StreamChunk / OpenAPI / registry / API / frontend / .env。不要 commit，不要 push，不要创建 PR。完成后运行文档要求的 pytest / ruff / mypy / 全量 pytest，并交给 Codex 审阅。

### AI 输出摘要
1. 新增 `docs/spec/provider-resilience.spec.md`：
   - 定义 retry 只发生在内容输出前。
   - 定义 `missing_api_key`、`rate_limit`、`timeout`、`connection_error`、`upstream_error` 五类标准错误码。
   - 定义 `max_retries`、`retry_backoff_seconds`、`request_timeout_seconds`、`retry_on_rate_limit` 配置。
   - 明确 DeepSeek 继承 OpenAI 行为，Custom 不做二次 retry。
2. 新增 `docs/b2-task-dispatch/B2-11-provider-resilience.md`：
   - 给出允许 / 禁止修改文件范围。
   - 建议新增 `backend/app/agents/adapters/resilience.py` 作为共享 helper。
   - 明确 Claude / OpenAI / DeepSeek / Custom 的具体实现要求。
   - 给出 10 类必须覆盖的测试和验证命令。
3. 更新 `docs/b2-task-dispatch/README.md` 与 `docs/b2-task-dispatch/B2-roadmap.md`：
   - 将 B2-11 标记为“已拆解，待执行”。

### 人工调整
当前工作区从 `feat/B2-orchestrator-fallback` 切出 `feat/B2-provider-resilience`，避免 B2-11 与 B2-10 混在同一分支。

### 经验
- Provider retry 必须以“是否已经输出内容”为边界，否则会造成重复 token、重复 block 或持久化污染。
- rate limit 默认不重试更安全；需要重试时必须显式配置，避免对上游造成进一步压力。

## 2026-05-25 — B2 拆解 B2-12 Adapter smoke tests 任务

### 任务
并行准备 B2-12：为 Claude / OpenAI / DeepSeek / Custom Adapter 增加默认 fake smoke tests 和可选真实 API slow tests。

### 关键 Prompt
> 请执行 B2-12。先阅读 AGENTS.md，然后阅读 docs/spec/adapter-smoke-tests.spec.md 和 docs/b2-task-dispatch/B2-12-adapter-smoke-tests.md。严格按文档实现：默认 smoke tests 必须使用 fake/mock upstream，不访问真实网络；验证 Adapter stream chunk 序列、to_sse()、block_start/block_end 成对、done.total_blocks 和 B1 _ContentAccumulator 消费；新增可选真实 API slow tests 时必须默认 skip，仅在 AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1 且对应 API key 存在时运行；注册 pytest slow marker；不要修改 Adapter 生产代码、BaseAgentAdapter、StreamChunk、OpenAPI、registry、API、frontend 或 .env。不要 commit，不要 push，不要创建 PR。完成后运行文档要求的 pytest / ruff / mypy / 全量 pytest，并交给 Codex 审阅。

### AI 输出摘要
1. 新增 `docs/spec/adapter-smoke-tests.spec.md`：
   - 定义默认 fake smoke tests 与可选真实 API slow tests 的边界。
   - 明确默认测试不得访问真实 Provider。
   - 明确 `slow` marker、`AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1` 和 provider API key 检查。
   - 定义 stream contract、SSE 序列化和 `_ContentAccumulator` 消费断言。
2. 新增 `docs/b2-task-dispatch/B2-12-adapter-smoke-tests.md`：
   - 指定允许修改测试文件和 `backend/pyproject.toml` 的 marker 配置。
   - 禁止修改 Adapter 生产代码和共享契约。
   - 给出 Claude / OpenAI / DeepSeek / Custom 默认 smoke 场景和 live smoke 场景。
   - 给出验证命令和完成后汇报要求。
3. 更新 `docs/b2-task-dispatch/README.md` 与 `docs/b2-task-dispatch/B2-roadmap.md`：
   - 将 B2-12 标记为“已拆解，待执行”。

### 人工调整
当前工作区仍在 `feat/B2-provider-resilience`，且已有 B2-11 文档改动。B2-12 先作为并行任务文档沉淀；Git/PR 时需要确保 B2-11 与 B2-12 的提交边界清晰。

### 经验
- 真实 API smoke tests 必须默认 skip，否则会让 CI 和本地默认测试依赖外部网络、费用和 API key。
- Adapter smoke tests 的核心不是断言模型回复内容，而是断言标准事件协议能被 SSE 和持久化层稳定消费。

## 2026-05-25 — B2 完成 B2-10 Orchestrator 失败降级回修

### 任务
完成 B2-10 实现后的审阅回修：收窄 fallback 触发范围、补充 fallback 说明文本块、校验 `task_id` 唯一性，并同步 Orchestrator 线完成状态。

### 关键 Prompt
> B2-10 当前仍有 3 个非阻塞问题尚未回修：orchestrator.py fallback 触发范围仍偏宽、fallback 缺少“正在 fallback”的说明 text block、仍未校验 task_id 唯一性。请你进行回修。

### AI 输出摘要
1. `backend/app/agents/orchestrator.py`：
   - fallback 仅在任务计划缺失或格式非法时触发。
   - 合法任务但缺少 `sub_adapters` / `adapter_factory` 时保持 `missing_sub_adapters` fatal error。
   - fallback 流程先输出 `Task plan unavailable; falling back to @<agent>.` 文本块。
   - 重复 `task_id` 被拒绝为 `invalid_task_plan`。
2. `backend/tests/test_orchestrator.py`：
   - 补充合法任务缺少 adapter source 不 fallback 的回归测试。
   - 补充重复 `task_id` 回归测试。
   - 保留 fallback 输出、异常降级、依赖跳过、全部失败仍 `done` 等覆盖。
3. `docs/b2-task-dispatch/README.md` 和 `docs/b2-task-dispatch/B2-roadmap.md`：
   - 将 B2-10 状态同步为“已完成”。
   - 将下一步推进到 B2-11 / B2-12 / B2-13。

### 人工调整
Codex 审阅时未发现阻塞性代码问题，只指出 B2-10 文档状态和协作日志未同步。本次仅补齐文档状态与日志，不修改共享契约、不改 frontend、不接 registry/seed。

### 经验
- Orchestrator fallback 应只代表“任务计划不可用”的降级路径，不能掩盖合法计划下的 adapter 注入缺失。
- B2 文档状态要随实现与审阅同步更新，否则任务索引会误导后续调度。
