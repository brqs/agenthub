## 2026-05-26 — F 实现 Mock ToolCall 与 Workspace 产物预览

### 任务
在 Agent Runtime Pivot 后，为前端补齐 Mock 版 ToolCallBlock、ArtifactPreview 和 Workspace 文件树。

### 关键 Prompt
> 实现Mock 版 ToolCallBlock + ArtifactPreview + 文件树

### AI 输出摘要
前端新增 `ToolCallBlock` 渲染组件、Mock workspace 数据、Workspace 文件树和 ArtifactPreview；Mock SSE 现在会发出 `tool_call` / `tool_result` 事件，聊天 store 能按 `call_id` 配对更新工具调用状态。演示会话中可看到 `write_file` / `bash` 工具调用，右侧栏可浏览 `public/demo.html`、`src/RuntimeDemo.tsx` 和 `README.md`，并预览 HTML iframe 或文本代码内容。

### 人工调整
本次只做 Mock UI 和前端状态管线，不修改 `shared/openapi.yaml`，等待 B1 落地正式 ToolCallBlock schema 与 Workspace Artifact API 后再切换真实数据源。

### 经验
Pivot 后前端可以不等待真实 Agent runtime 完全接通，先用 Mock SSE 和本地 workspace 数据做出端到端产品感；只要事件字段和目标 OpenAPI 形态保持一致，后续替换为真实 API 的成本可控。

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
新增 `docs/b2/ai-task-dispatch-template.md`，明确 B2、Codex、Claude Code 的协作角色，以及 Codex 分发子任务时必须包含的背景、文件范围、禁止事项、实现目标、测试要求、验证命令和交付说明。

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
新增 `docs/b2/task-dispatch/`，包含任务索引 `README.md` 和 `B2-01-streaming-artifact-parser.md`。B2-01 文档保存了交给 Claude Code 的完整任务命令，后续 B2-02、B2-03 可继续放在同一目录。

### 人工调整
任务文档作为阶段性执行记录放入 `docs/b2/task-dispatch/`，不升级为全局 `AGENTS.md` 规则。

### 经验
长期协作中，任务分发应有独立目录和编号，方便追踪 Claude Code 的执行范围、Codex 的审阅入口，以及后续答辩时展示 AI 协作过程。

## 2026-05-25 — B2 记录本地 Anaconda 开发环境

### 任务
记录 B2 本地 Python 开发环境，避免后续 Claude Code 重复创建或安装 Python 环境。

### 关键 Prompt
> 对了，我在本地开发使用的是anaconda的LLMAgent环境，请你也在文档中注明，以便之后的claude重复安装python环境

### AI 输出摘要
在 `docs/b2/task-dispatch/README.md` 和 `docs/b2/ai-task-dispatch-template.md` 中记录 B2 默认使用 Anaconda 环境 `LLMAgent`，并将 B2-01 的验证命令更新为 `conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py`。同时注明缺少项目依赖时应在现有 `LLMAgent` 环境内安装 `backend` 依赖，不要新建 Python 环境。

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
新增 `docs/archive/git-pr-ops/README.md`，记录 Git/PR Claude 的职责、禁止事项、标准流程、分支命名、commit 规范和 PR 模板。新增 `docs/archive/git-pr-ops/claude-git-pr-instructions.md`，提供可直接发送给 Git/PR Claude 的初始化指令。同步更新 `docs/b2/task-dispatch/README.md`，将 Git/PR Claude 纳入 B2 协作方式。

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
新增 `docs/b2/task-dispatch/B2-02-claude-adapter-streaming.md`，记录交给 Claude Code 的完整任务命令。同步更新 `docs/b2/task-dispatch/README.md` 的任务索引，将 B2-02 标记为待执行。

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
新增 `docs/b2/task-dispatch/B2-roadmap.md`，定义 B2 总目标、设计边界、阶段目标、B2-01 到 B2-13 的任务路线图、近期执行顺序、PR 边界建议和 Codex 审阅重点。同步更新 `docs/b2/task-dispatch/README.md`，加入路线图入口，并将 B2-02 状态调整为“已审阅，待 Git/PR”。

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
确认当前分支为 `feat/B2-openai-adapter-streaming`，`origin/main` 已包含 B2-02 合并提交。检查本地 `openai` SDK 为 `2.31.0`，并基于当前 `openai.py` stub、`settings.openai_api_key/openai_base_url` 和 seed 默认模型 `gpt-4o` 创建 `docs/b2/task-dispatch/B2-03-openai-adapter-streaming.md`。

同步更新 `docs/b2/task-dispatch/README.md` 任务索引，将 B2-03 标记为待执行；更新 `docs/b2/task-dispatch/B2-roadmap.md`，将 B2-03 状态调整为“已拆解，待执行”。

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
先将本地 `main` 快进同步到最新 `origin/main`，再创建 `feat/B2-custom-agent-adapter` 分支。基于当前 `custom.py` stub、已完成的 `ClaudeAdapter` / `OpenAIAdapter`、registry 和 seed custom agent 配置，新增 `docs/b2/task-dispatch/B2-04-custom-adapter-delegation.md`。

同步更新 `docs/b2/task-dispatch/README.md`，将 B2-03 标记为已完成并加入 B2-04；更新 `docs/b2/task-dispatch/B2-roadmap.md`，将 B2-04 标记为“已拆解，待执行”，并调整近期执行顺序。

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
确认当前 `main` 已包含 B2-04 合并提交，新增 `docs/b2/spec/agent-config-validation.spec.md` 和 `docs/b2/task-dispatch/B2-05-agent-config-validation.md`。同步更新 B2 任务索引与路线图，将 B2-04 标记为已完成，将 B2-05 标记为已拆解、待执行。

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

新增 `docs/b2/spec/stream-error-status.spec.md` 和 `docs/b2/task-dispatch/B2-06-stream-error-status.md`，同步更新 B2 任务索引与路线图，将 B2-05 标记为已完成，将 B2-06 标记为已拆解、待执行。

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
确认 `ContentBlock` 和 `StreamChunk.block_type` 已经包含 `diff` 与 `web_preview`，因此 B2-07 不需要新增 schema 类型或修改 OpenAPI。新增 `docs/b2/spec/artifact-parser-v2.spec.md` 和 `docs/b2/task-dispatch/B2-07-artifact-parser-v2.md`，将任务限定为 parser 增强、`_ContentAccumulator` 最小扩展和后端测试覆盖。

同步更新 `docs/b2/task-dispatch/README.md` 与 `docs/b2/task-dispatch/B2-roadmap.md`，将 B2-06 标记为已完成，将 B2-07 标记为已拆解、待执行，并增加建议分支 `feat/B2-artifact-parser-v2`。

### 人工调整
B2-07 明确不抓取网页标题、不做网络 I/O、不新增第三方依赖；独立 URL 只生成带 url 的 `web_preview` block。由于 `stream.py` 属于 B1-owned 文件，任务文档把 `_ContentAccumulator` 扩展标记为 B1/B2 协同边界，只允许做持久化所需的最小改动。

### 经验
当已有 schema 已覆盖目标 block 类型时，应优先复用现有契约，而不是为了 parser v2 新增字段。富媒体识别不仅要看 parser 输出，还必须检查 SSE 持久化层和前端流式消费能力，否则容易出现“流里有 block，但落库或渲染丢失”的断层。

## 2026-05-25 — B2 执行 B2-07 ArtifactParser v2 富媒体识别增强

### 任务
执行 B2-07：增强 `StreamingArtifactParser` 对 diff fence 和独立 URL 的识别，并让 SSE 持久化层保存既有 `diff` / `web_preview` ContentBlock。

### 关键 Prompt
> 请执行 B2-07。先阅读 docs/b2/spec/artifact-parser-v2.spec.md、docs/b2/task-dispatch/B2-07-artifact-parser-v2.md、AGENTS.md。严格按 B2-07 文档实现和测试。不要修改禁止范围内的文件，不要提交 commit，不要 push，不要创建 PR。

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
确认 B2-08 不应直接实现完整 Orchestrator，而是先创建面向 Claude Code 的任务文档：`docs/b2/task-dispatch/B2-08-orchestrator-spec.md`。该文档要求 Claude Code 创建 `docs/b2/spec/orchestrator.spec.md`，并定义 task decomposition、`agent_switch` 事件语义、子 Agent 顺序调度、`block_index` 重映射和失败降级边界。

同步更新 `docs/b2/task-dispatch/README.md` 与 `docs/b2/task-dispatch/B2-roadmap.md`，将 B2-08 标记为“已拆解，待执行”，并把 Orchestrator 后续实现拆成 B2-09 顺序调度与 B2-10 失败降级。

### 人工调整
Git/PR Claude 的指令保持简短：只需从最新 `main` 创建 `feat/B2-orchestrator-spec` 分支，不承载 B2-08 的长任务说明。B2-08 Claude Code 的完整执行命令沉淀在任务文档中，后续直接复制文档内容执行。

### 经验
长任务命令应进入 `docs/b2/task-dispatch/`，聊天窗口只保留入口命令和分支名。这样 Git/PR Claude 与实现 Claude 的职责不会混淆，也能减少重复粘贴导致的上下文偏差。

## 2026-05-25 — B2 并行拆解 B2-09 Orchestrator 调度任务

### 任务
在 B2-08 Spec 任务启动后，并行准备 B2-09：Orchestrator 子 Agent 顺序调度与 `block_index` 重映射。

### 关键 Prompt
> 并行开始b2-09的工作内容

### AI 输出摘要
新增 `docs/b2/task-dispatch/B2-09-orchestrator-dispatch.md`，将 B2-09 定义为基于 B2-08 Spec 的实现任务：读取外层注入的 task plan 和子 Adapter，串行调用子 Agent，发出 `agent_switch`，转发子 Agent `StreamChunk` 并重映射 `block_index`，最后输出 summary 和 `done`。

同步更新 `docs/b2/task-dispatch/README.md` 与 `docs/b2/task-dispatch/B2-roadmap.md`：B2-07 标记为已完成，B2-09 标记为“已拆解，待 B2-08 Spec 完成后执行”。

### 人工调整
B2-09 允许提前准备任务文档，但实现必须等待 `docs/b2/spec/orchestrator.spec.md` 存在并明确输入/输出规则。为了避免 Orchestrator 直接访问数据库，B2-09 文档要求使用外层注入的 `tasks` / `sub_adapters` / `adapter_factory`，不修改 registry、B1 SSE、seed、OpenAPI 或前端。

### 经验
并行推进依赖任务时，应把“文档拆解可并行”和“代码实现需等待上游契约”分开。B2-09 的核心不是抢先写调度代码，而是提前固定代码边界和测试标准，等 B2-08 Spec 落地后即可快速执行。

## 2026-05-25 — B2 执行 B2-08 Orchestrator Spec 与任务拆解 Prompt

### 任务
执行 B2-08：阅读 AGENTS.md、docs/b2/task-dispatch/B2-roadmap.md、docs/tech-architecture.md 和全部 agents 代码，然后新建 `docs/b2/spec/orchestrator.spec.md` 并更新相关任务文档。

### 关键 Prompt
> 请执行 B2-08。先阅读 AGENTS.md，然后阅读 docs/b2/task-dispatch/B2-08-orchestrator-spec.md，并严格按该文档完成任务。不要 commit，不要 push，不要创建 PR，完成后交给 Codex 审阅。

### AI 输出摘要
1. 新建 `docs/b2/spec/orchestrator.spec.md`：
   - 定义 Orchestrator 输入（标准 `stream()` 签名 + 外层注入 `available_agents`）、输出（标准 `StreamChunk` 序列，不新增字段）。
   - 明确 Orchestrator 在 group chat 中的 6 项职责边界（任务拆解、子 Agent 选择、流式调度、block_index 重映射、失败降级、最终摘要）。
   - 定义 `SubTask` 结构化格式（`task_id`, `agent_id`, `title`, `instruction`, `depends_on`, `priority`, `expected_output`）。
   - 定义子 Agent 顺序调度规则：按 `priority` 排序，检查 `depends_on`，通过 config 注入的 `sub_adapters` / `adapter_factory` 获取子 Agent Adapter；registry 生产接线留给后续 B1/B2 协同任务。
   - 定义 `agent_switch` 事件语义：`from_agent="orchestrator"`, `to_agent`, `task`，切换前发出，不占用 `block_index`。
   - 定义 `block_index` 重映射算法：维护全局 `global_block_offset`，子 Agent `start`/`done` 被吞掉，其余 chunk 重映射后外发，确保全局单调递增。
   - 定义失败降级策略：单个子 Agent 失败不中断主流程，fallback 到文本说明块，最终 summary 列出 `SUCCEEDED`/`FAILED`/`SKIPPED`；任务拆解失败 fallback 到单 Agent 模式。
   - 明确不修改 `BaseAgentAdapter`、`StreamChunk`、`ContentBlock`、OpenAPI 的约束。
   - 制定 B2-09（顺序调度与 block_index 重映射，10 项验收标准）和 B2-10（失败降级与部分成功输出，7 项验收标准）的验收标准。
2. 更新 `docs/b2/task-dispatch/B2-08-orchestrator-spec.md`：追加执行结果摘要。
3. 更新 `docs/b2/task-dispatch/README.md`：将 B2-08 状态从“已拆解，待执行”改为“进行中”。
4. 更新 `docs/b2/task-dispatch/B2-roadmap.md`：将 B2-08 状态改为“进行中”。
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
> 请执行 B2-09。先阅读 AGENTS.md，然后阅读 docs/b2/spec/orchestrator.spec.md 和 docs/b2/task-dispatch/B2-09-orchestrator-dispatch.md。严格按文档实现：只做注入式顺序调度；通过 config 注入的 tasks 和 sub_adapters / adapter_factory 获取子 Agent；不做真实 LLM 任务拆解；不做 registry DB 生产接线；不修改 OpenAPI / BaseAgentAdapter / StreamChunk / ContentBlock；不修改 frontend；不 commit，不 push，不创建 PR。完成后运行文档要求的 pytest / ruff / mypy，并把结果交给 Codex 审阅。

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
> 请执行 B2-10。先阅读 AGENTS.md，然后阅读 docs/b2/spec/orchestrator.spec.md 和 docs/b2/task-dispatch/B2-10-orchestrator-fallback.md。严格按文档实现：只增强 Orchestrator 失败降级；捕获子 Agent stream 异常、adapter_factory 异常和 error chunk；失败任务输出普通 text block；后续不依赖失败任务的任务继续执行；依赖失败任务的任务标记 skipped；所有任务失败也必须 summary + done；任务计划非法时仅在提供 fallback adapter 的情况下走单 Agent fallback。不要实现真实 LLM 任务拆解，不接 registry/seed，不改 OpenAPI / BaseAgentAdapter / StreamChunk / ContentBlock，不改 frontend，不 commit，不 push，不创建 PR。完成后运行 pytest / ruff / mypy / 全量 pytest，并交给 Codex 审阅。

### AI 输出摘要
1. 新增 `docs/b2/task-dispatch/B2-10-orchestrator-fallback.md`：
   - 明确 B2-10 只处理 Orchestrator 失败降级，不做 retry、timeout、并发调度或生产 registry 接线。
   - 规定子 Agent `stream()` 抛异常时保留 partial content，并追加 text failure block。
   - 规定 `adapter_factory` 异常、子 Agent `error` chunk、依赖失败跳过和全失败仍 `done` 的行为。
   - 为任务计划不可用场景定义测试用 fallback adapter 注入方式。
   - 给出 6 类必须覆盖的单元测试和验证命令。
2. 更新 `docs/b2/task-dispatch/README.md` 和 `docs/b2/task-dispatch/B2-roadmap.md`：
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
> 请执行 B2-11。先阅读 AGENTS.md，然后阅读 docs/b2/spec/provider-resilience.spec.md 和 docs/b2/task-dispatch/B2-11-provider-resilience.md。严格按文档实现：只修改 Provider Adapter 及其测试；setup 阶段 transient error 可配置重试；rate limit 默认不重试；timeout / connection / upstream error 输出标准 StreamChunk(error)；内容已经开始输出后不得重试，必须先 flush parser 再输出 error；DeepSeek 继承 OpenAI resilience；Custom 不做二次 retry，只转发上游 chunk。不要修改 BaseAgentAdapter / StreamChunk / OpenAPI / registry / API / frontend / .env。不要 commit，不要 push，不要创建 PR。完成后运行文档要求的 pytest / ruff / mypy / 全量 pytest，并交给 Codex 审阅。

### AI 输出摘要
1. 新增 `docs/b2/spec/provider-resilience.spec.md`：
   - 定义 retry 只发生在内容输出前。
   - 定义 `missing_api_key`、`rate_limit`、`timeout`、`connection_error`、`upstream_error` 五类标准错误码。
   - 定义 `max_retries`、`retry_backoff_seconds`、`request_timeout_seconds`、`retry_on_rate_limit` 配置。
   - 明确 DeepSeek 继承 OpenAI 行为，Custom 不做二次 retry。
2. 新增 `docs/b2/task-dispatch/B2-11-provider-resilience.md`：
   - 给出允许 / 禁止修改文件范围。
   - 建议新增 `backend/app/agents/adapters/resilience.py` 作为共享 helper。
   - 明确 Claude / OpenAI / DeepSeek / Custom 的具体实现要求。
   - 给出 10 类必须覆盖的测试和验证命令。
3. 更新 `docs/b2/task-dispatch/README.md` 与 `docs/b2/task-dispatch/B2-roadmap.md`：
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
> 请执行 B2-12。先阅读 AGENTS.md，然后阅读 docs/b2/spec/adapter-smoke-tests.spec.md 和 docs/b2/task-dispatch/B2-12-adapter-smoke-tests.md。严格按文档实现：默认 smoke tests 必须使用 fake/mock upstream，不访问真实网络；验证 Adapter stream chunk 序列、to_sse()、block_start/block_end 成对、done.total_blocks 和 B1 _ContentAccumulator 消费；新增可选真实 API slow tests 时必须默认 skip，仅在 AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1 且对应 API key 存在时运行；注册 pytest slow marker；不要修改 Adapter 生产代码、BaseAgentAdapter、StreamChunk、OpenAPI、registry、API、frontend 或 .env。不要 commit，不要 push，不要创建 PR。完成后运行文档要求的 pytest / ruff / mypy / 全量 pytest，并交给 Codex 审阅。

### AI 输出摘要
1. 新增 `docs/b2/spec/adapter-smoke-tests.spec.md`：
   - 定义默认 fake smoke tests 与可选真实 API slow tests 的边界。
   - 明确默认测试不得访问真实 Provider。
   - 明确 `slow` marker、`AGENTHUB_RUN_LIVE_PROVIDER_TESTS=1` 和 provider API key 检查。
   - 定义 stream contract、SSE 序列化和 `_ContentAccumulator` 消费断言。
2. 新增 `docs/b2/task-dispatch/B2-12-adapter-smoke-tests.md`：
   - 指定允许修改测试文件和 `backend/pyproject.toml` 的 marker 配置。
   - 禁止修改 Adapter 生产代码和共享契约。
   - 给出 Claude / OpenAI / DeepSeek / Custom 默认 smoke 场景和 live smoke 场景。
   - 给出验证命令和完成后汇报要求。
3. 更新 `docs/b2/task-dispatch/README.md` 与 `docs/b2/task-dispatch/B2-roadmap.md`：
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
3. `docs/b2/task-dispatch/README.md` 和 `docs/b2/task-dispatch/B2-roadmap.md`：
   - 将 B2-10 状态同步为“已完成”。
   - 将下一步推进到 B2-11 / B2-12 / B2-13。

### 人工调整
Codex 审阅时未发现阻塞性代码问题，只指出 B2-10 文档状态和协作日志未同步。本次仅补齐文档状态与日志，不修改共享契约、不改 frontend、不接 registry/seed。

### 经验
- Orchestrator fallback 应只代表“任务计划不可用”的降级路径，不能掩盖合法计划下的 adapter 注入缺失。
- B2 文档状态要随实现与审阅同步更新，否则任务索引会误导后续调度。

## 2026-05-25 — B2 完成 B2-13 演示与答辩材料

### 任务
直接由 Codex 完成 B2-13：整理 B2 演示脚本、答辩材料、架构说明和验证命令，不再分发给 Claude Code。

### 关键 Prompt
> b2-13 的工作由你直接完成吧，就不进行任务的分发了

### AI 输出摘要
1. 新增 `docs/b2/task-dispatch/B2-13-demo-and-architecture.md`：
   - 总结 B2-01 到 B2-12 的交付内容。
   - 梳理 Adapter、ArtifactParser、Orchestrator、Provider resilience 的架构讲解。
   - 提供演示前检查命令、后端演示路径和 5 分钟讲解节奏。
   - 提供答辩常见问题、当前边界与后续建议。
2. 更新 `docs/b2/task-dispatch/README.md`：
   - 将 B2-12 标记为“已完成，Codex 审阅通过”。
   - 新增 B2-13 索引并标记为“已完成”。
3. 更新 `docs/b2/task-dispatch/B2-roadmap.md`：
   - 将 B2-13 状态标记为“已完成”。
   - 更新当前下一步为提交 B2-13 文档 PR 和演示前验证。
   - 补充 B2-11/12 与 B2-13 的 PR 边界建议。

### 人工调整
本次 B2-13 为纯文档收尾，不修改生产代码、不修改 OpenAPI、不修改 `BaseAgentAdapter` / `StreamChunk` / `ContentBlock` 契约。

### 经验
- 收尾文档应把“已完成能力”和“当前边界”同等明确地写出来，避免演示或答辩时把注入式 Orchestrator 测试路径误说成完整生产接线。
- B2 的答辩重点不是逐个 Provider SDK 细节，而是说明如何把 Provider 差异、流式富媒体解析和多 Agent 编排统一成稳定的 `StreamChunk` 协议。

## 2026-05-26 — Codex 整理 docs 文档目录

### 任务
按角色和时效整理 `docs/`：将 B1、B2、前端相关文档归入对应目录，将过时或阶段性资料放入归档目录。

### 关键 Prompt
> 整理一下docs目录下的文档将过时的文档放入归档文件夹，相关文档放入b1 b2文件夹 前端文件夹

### AI 输出摘要
1. 新增文档入口：
   - `docs/README.md`
   - `docs/b1/README.md`
   - `docs/b2/README.md`
   - `docs/archive/README.md`
2. 调整文档目录：
   - B1 文档移动到 `docs/b1/`，Workspace spec 移动到 `docs/b1/spec/`。
   - B2 文档移动到 `docs/b2/`，任务分发记录移动到 `docs/b2/task-dispatch/`，B2 spec 移动到 `docs/b2/spec/`。
   - 前端 spec 移动到 `docs/frontend/spec/`。
   - 原始课题 PDF 与 Git/PR Claude 阶段性资料移动到 `docs/archive/`。
3. 同步修复 AGENTS / CLAUDE / 全局文档 / 子目录文档中的相对链接，并用脚本检查 Markdown 文件链接可解析。

### 人工调整
本次只做文档组织与链接修复，不修改生产代码、不修改 OpenAPI 契约、不改变各模块实现边界。

### 经验
- 文档移动后要立刻跑相对链接检查，尤其是从 `docs/b2/spec/` 回指 `backend/`、`frontend/`、`shared/` 的路径层级容易漏。
- `docs/spec/` 只保留跨团队 ADR，模块内 spec 放回 owner 目录，后续检索会更直接。

## 2026-05-26 — Codex 拆解 B2-14 至 B2-20 真实 Agent Runtime 任务

### 任务
按 Agent Runtime Pivot 重新拆分 B2 后续任务，明确 OpenCode 开发、Codex 复审、Claude Code 仅处理 Git/PR，并把 OpenCode 纳入产品侧必接 runtime。

### 关键 Prompt
> PLEASE IMPLEMENT THIS PLAN: B2-14~B2-20 真实 Agent Runtime 接入计划

### AI 输出摘要
1. 新增 B2-14 至 B2-20 任务文档：
   - 文档与规格重基线
   - ModelGateway 拆分
   - Claude Code / Codex / OpenCode ExternalAdapter
   - BuiltinAgent MVP
   - 真实 Agent demo smoke 与 registry 接线
2. 更新 `docs/b2/task-dispatch/README.md` 和 `B2-roadmap.md`：
   - B2-01 至 B2-13 标记为 pivot 前历史任务。
   - B2-14 至 B2-20 标记为待执行。
   - 协作角色统一为 OpenCode 执行、Codex 复审、Claude Code 仅 Git/PR。
3. 同步 ADR/spec：
   - OpenCode 从候选项调整为 Must runtime。
   - ToolSpec 文档字段与当前代码的 `parameters` 对齐。

### 人工调整
本次只做文档和规格口径同步，不修改后端 runtime 代码、不修改 OpenAPI、不修改 `BaseAgentAdapter` / `StreamChunk` / `ContentBlock` 契约。

### 经验
- pivot 后的任务文档必须同时写清产品 runtime 范围和开发协作角色，否则 OpenCode 容易被误判为可选项或被 Claude Code 执行模式覆盖。
- 分阶段接入真实 runtime 时，先把 ModelGateway、ExternalAdapter、BuiltinAgent、registry cutover 拆开，能降低每个 OpenCode 对话窗口的决策负担。

## 2026-05-26 — OpenCode 执行 B2-15 ModelGateway 拆分

### 任务
将 Claude / OpenAI / DeepSeek raw LLM 能力迁移为 BuiltinAgent 内部 ModelGateway backend，并保留旧 adapter 兼容 shim。

### 关键 Prompt
> 执行 AgentHub B2-15：ModelGateway 拆分与 raw LLM Adapter 降级。只允许新增/修改 `backend/app/agents/model_gateway/**`，最小修改 `backend/app/agents/adapters/**` 做兼容 shim，并运行任务文档中的 pytest / ruff / mypy。

### AI 输出摘要
新增 `backend/app/agents/model_gateway/`，包含 `ModelGateway`、Claude/OpenAI/DeepSeek backend 和 resilience helper。旧 Claude/OpenAI/DeepSeek adapter 改为兼容 shim，继续满足 BaseAgentAdapter v2 和现有 registry 调用路径。

### 人工调整
无人工代码调整。执行中发现 shim 包装 async generator 时需要显式关闭内层流，已用 `aclosing()` 保持旧 Claude stream 关闭语义。

### 经验
迁移底层 provider 逻辑时，兼容 shim 不只要透传数据，还要保留 async generator 的关闭/清理语义；否则中途 `aclose()` 的 resilience 测试会退化。

## 2026-05-26 — OpenCode 执行 B2-19 BuiltinAgent MVP

### 任务
新增自建 BuiltinAgent MVP，实现 AgentLoop、ToolRegistry、MCP stdio client、ModelGateway 调用和 workspace 工具安全边界。

### 关键 Prompt
> 请执行 B2-19：Builtin Agent MVP。新增 backend/app/agents/builtin/**，实现 AgentLoop、ToolRegistry、MCP stdio client、ModelGateway 调用、read_file/write_file/bash 三类工具、StreamChunk 映射和错误路径测试；不修改 BaseAgentAdapter、StreamChunk、OpenAPI、frontend、registry.py 或 seed_agents.py。

### AI 输出摘要
新增 `backend/app/agents/builtin/` 包：`BuiltinAgentAdapter` 合并配置和工具，`AgentLoop` 处理模型流、工具调用、tool_result 配对和终止条件，native tools 负责 workspace 内读写和 bash 白名单/路径边界执行，MCP client 提供手写 stdio JSON-RPC MVP。新增 `backend/tests/test_builtin_agent.py` 覆盖单轮文本、文件读写、越界、bash 拒绝/路径逃逸/超时、max_iterations、MCP server down、call_id 配对、fake ModelGateway 调用路径，以及复审指出的 bash 执行逃逸、orphan tool_call、MCP timeout 和 upstream error 映射。

### 人工调整
验证时发现 PowerShell 不展开 pytest glob，改用实际新增测试文件路径执行。一次尝试用 `rg --files` 自动发现测试时本机 shell 未安装 `rg`，导致 pytest 无参数启动全量测试并超时；该问题不影响 B2-19 指定测试文件结果。复审后明确 MCP 当前未使用官方 SDK，真实 initialize/session 和 SDK smoke 留给后续 opt-in 验证。

### 经验
BuiltinAgent 的测试应默认注入 fake ModelGateway，避免依赖真实 Provider tool calling。工具异常要区分 `workspace_violation` 和普通 `tool_call_failed`，前者必须终止 loop，但终止前也必须为所有已经公开的 tool_call 补齐 tool_result。没有真实系统沙箱时，bash 白名单必须保守，不能允许 `python` / `node` 这类可写出 workspace 的解释器。

## 2026-05-26 — Codex 沉淀 B2 复审模板

### 任务
将 B2-15 至 B2-18 复审提示抽象为可复用的 Codex 复审文档模板。

### 关键 Prompt
> 请仿照 B2-15 至 B2-18 的 Codex 复审格式，做一个复审模板，并写入成文档。

### AI 输出摘要
新增 `docs/b2/codex-review-template.md`，提供通用复审指令、字段替换建议，以及 ModelGateway、ExternalAgentAdapter、BuiltinAgent、Registry cutover 的高风险检查项。

### 人工调整
同步更新 `docs/b2/task-dispatch/README.md` 的模板索引，方便后续 B2 复审入口检索。

### 经验
复审模板应独立沉淀为文档，避免散落在单次对话里；通用模板只保留稳定边界，任务特有检查点由每次复审替换补齐。

## 2026-05-26 — Codex 同步 B2-14 至 B2-18 复审状态

### 任务
根据当前 B2-14 至 B2-18 的 Codex 复审结论，同步任务索引、路线图和下一步执行顺序。

### 关键 Prompt
> 请你查看和同步其他修改，尤其是文档的修改是否同步

### AI 输出摘要
1. 检查 `docs/b2/task-dispatch/README.md` 和 `docs/b2/task-dispatch/B2-roadmap.md` 后发现 B2-14 至 B2-18 仍标记为“待执行”。
2. 将 B2-14、B2-15、B2-16、B2-17、B2-18 统一同步为“已完成，Codex 复审通过”。
3. 将 roadmap 当前最近步骤推进为：先复审 B2-19，再启动 B2-20 registry / seed / orchestrator / demo smoke 接线。

### 人工调整
本次只修正文档状态和协作日志，不修改后端实现代码、不修改 OpenAPI、不修改 `BaseAgentAdapter` / `StreamChunk` / `ContentBlock`，也不接 registry 或 seed。

### 经验
B2 并行执行后，README 与 roadmap 的状态表必须在每轮 Codex 复审通过后一起更新；否则后续会误判 B2-14 至 B2-18 仍可被重复分发。

## 2026-05-27 — Codex 同步 B2-19 复审通过状态

### 任务
根据 B2-19 Codex 复审结论，同步 BuiltinAgent MVP 的任务状态和下一步路线。

### 关键 Prompt
> 收到，B2-19 复审通过。

### AI 输出摘要
1. 将 `docs/b2/task-dispatch/README.md`、`docs/b2/task-dispatch/B2-roadmap.md` 和 `docs/b2/task-dispatch/B2-19-builtin-agent-mvp.md` 中的 B2-19 状态同步为“已完成，Codex 复审通过”。
2. 将 roadmap 当前最近步骤推进到 B2-20：registry、seed、orchestrator 和 demo smoke 接线。
3. 记录复审验证摘要：`pytest` 16 passed，`ruff` passed，`mypy app/agents/builtin` success；未修改禁改文件。

### 人工调整
本次只做文档状态同步，不修改后端实现代码、不修改 OpenAPI、不修改 `BaseAgentAdapter` / `StreamChunk` / `ContentBlock`，也不提前接 registry 或 seed。

### 经验
B2-19 复审通过后，B2-20 才可以开始最终顶层 provider、seed agent 和 orchestrator 接线；在此之前 ExternalAdapter 和 BuiltinAgent 的实现应保持独立可测。

## 2026-05-27 — OpenCode 执行 B2-20 真实 Agent Demo Smoke 与 Registry 接线

### 任务
完成真实 Agent Runtime 最终接线：registry、seed、orchestrator adapter_factory、配置校验与 fake demo smoke。

### 关键 Prompt
> 你现在作为 OpenCode，执行 AgentHub B2-20：真实 Agent Demo Smoke 与 Registry 接线。完成真实 Agent Runtime 最终接线：registry、seed、orchestrator 子 Agent adapter_factory、fake demo smoke。

### AI 输出摘要
1. `backend/app/agents/registry.py` 顶层 `PROVIDER_MAP` 切换为 `mock` / `claude_code` / `codex` / `opencode` / `builtin`，并保留 legacy raw provider 到 `builtin` ModelGateway 的临时迁移兼容。
2. `backend/app/seeds/seed_agents.py` 内置 Agent 切换为 `claude-code`、`codex-helper`、`opencode-helper`、`web-designer`、`orchestrator` 等 runtime/builtin provider，orchestrator 默认 managed agents 覆盖四个子 Agent。
3. `backend/app/agents/config_validation.py` 支持新 provider 与 `opencode` / `builtin` 配置字段；schema / OpenAPI / API 文档同步更新。
4. 补充 registry、orchestrator tool event 透传和 fake real-agent demo smoke 测试；live runtime smoke 默认 skip，需 `AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1` opt-in，可用 `AGENTHUB_LIVE_RUNTIME_PROVIDERS` 选择 provider。

### 人工调整
回修检查发现 fake smoke 固定插入/删除 seed `orchestrator` 有主键冲突和污染本地 DB 风险，已改为唯一 `demo-smoke-*` Agent，并只清理测试 Agent。live smoke 也从占位 skip 改为 provider 参数化真实 adapter 调用路径；本机 B2-20 指定测试 50 passed / 3 skipped，ruff 与 mypy 通过。

### 经验
Registry provider cutover 不能只改 seed；需要同步 Pydantic schema、OpenAPI、API 文档和 config validation。Orchestrator 聚合真实 Agent runtime 时必须透传 `tool_call` / `tool_result`，否则 B1 SSE 层无法持久化 ToolCallBlock。

## 2026-05-27 — Codex 复审通过 B2-20 真实 Agent Demo Smoke

### 任务
根据 B2-20 Codex 复审结论，同步真实 Agent runtime registry/seed/orchestrator 接线任务状态。

### 关键 Prompt
> Findings: 未发现阻塞性问题。上一轮两条 findings 已回修：fake smoke 不再固定插入/删除 seed `orchestrator`，live smoke 也不再是无条件占位 skip。Verdict: 通过。

### AI 输出摘要
1. 将 `docs/b2/task-dispatch/README.md`、`docs/b2/task-dispatch/B2-roadmap.md` 和 `docs/b2/task-dispatch/B2-20-real-agent-demo-smoke.md` 中的 B2-20 状态同步为“已完成，Codex 复审通过”。
2. 记录复审边界：未执行 `AGENTHUB_RUN_LIVE_RUNTIME_TESTS=1` 的真实 runtime 路径；当前 live smoke 证明 opt-in 后会进入 provider 参数化 adapter 调用路径，不严格证明真实 runtime 成功产出。
3. 将 roadmap 下一步推进到 Claude Code 处理 Git/PR，以及前端基于最新 OpenAPI 重新生成类型并更新 Agent 创建表单。

### 人工调整
本次只做文档状态同步，不修改后端实现代码、不修改 OpenAPI、不修改 `BaseAgentAdapter` / `StreamChunk` / `ContentBlock`，也不修改前端实现。

### 经验
B2-20 复审通过后，B2-14 至 B2-20 的真实 Agent Runtime 接入线可以进入 Git/PR 阶段；但 OpenAPI/schema 已变更，前端生成类型与 Agent 创建 UI 必须作为后续协同项跟进。
