# B2-07 ArtifactParser v2 富媒体识别增强

> 交给 Claude Code 执行的完整任务命令。

````text
任务编号：B2-07
任务名称：ArtifactParser v2 富媒体识别增强

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目 B2 Agent 集成方向的具体子任务。Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现和测试，不要做无关重构。

项目背景：
AgentHub 后端的 ClaudeAdapter / OpenAIAdapter 会把上游 LLM 文本 delta 交给 `StreamingArtifactParser`，再转成标准 `StreamChunk`，由 B1 SSE 层转发并持久化成 `Message.content`。

B2-01 已实现基础 parser：支持 text 和 fenced code block。
B2-06 已修复 SSE error 状态持久化。
当前 B2-07 要在不新增 schema 类型的前提下，让 parser 识别更多已有 ContentBlock：diff 和 web_preview。

请先阅读：
1. AGENTS.md
2. docs/spec/artifact-parser-v2.spec.md
3. docs/b2-task-dispatch/B2-roadmap.md
4. backend/app/agents/artifact_parser.py
5. backend/app/agents/types.py
6. backend/app/api/v1/stream.py
7. backend/app/schemas/message.py
8. backend/tests/test_artifact_parser.py
9. backend/tests/test_b1_quality.py

允许修改：
- backend/app/agents/artifact_parser.py
- backend/tests/test_artifact_parser.py
- backend/app/api/v1/stream.py
- backend/tests/test_b1_quality.py

如果确实更清晰，也可以新增：
- backend/tests/test_stream_content_blocks.py

允许同步更新：
- docs/ai-collaboration-log.md

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/adapters/**
- backend/app/schemas/**
- backend/app/models/**
- backend/app/api/v1/agents.py
- backend/app/api/v1/messages.py
- backend/app/api/v1/conversations.py
- shared/openapi.yaml
- frontend/**
- docker-compose.yml
- AGENTS.md
- .env / backend/.env

本任务不允许修改 OpenAPI、BaseAgentAdapter.stream() 签名、StreamChunk schema 或 ContentBlock schema。

实现目标：
1. `StreamingArtifactParser` 继续稳定支持 text/code。
2. fenced code language 为 `diff` / `patch` / `udiff` 时，输出 `block_type="diff"`。
3. 文本中独立成行的 http/https URL 输出 `block_type="web_preview"`。
4. 行内 URL 不拆分，继续作为 text。
5. `_ContentAccumulator` 能持久化 diff/web_preview block，避免 SSE 完成后丢失新 block。
6. 不引入网络请求，不抓取网页标题，不新增依赖。

核心行为：

1. Diff fence 识别
   输入示例：
   ```diff
   diff --git a/app.py b/app.py
   --- a/app.py
   +++ b/app.py
   @@
   -old
   +new
   ```

   parser 应输出：
   - block_start, block_type="diff", metadata 至少包含 filename 或可推断信息
   - delta 使用 text_delta 承载 raw diff 内容
   - block_end

   持久化后应得到合法 DiffBlock：
   - type="diff"
   - filename: 优先从 `+++ b/<file>` 或 `diff --git a/<file> b/<file>` 提取
   - before: 包含删除行和上下文行
   - after: 包含新增行和上下文行

2. 普通 code fence 保持不变
   - ```python / ```tsx / 未知语言仍输出 `block_type="code"`。
   - language metadata 保持现有规则：第一段 token。

3. Web preview 识别
   输入示例：
   `https://github.com/brqs/agenthub/pull/17`

   当 URL 独立成行时，parser 应输出：
   - block_start, block_type="web_preview", metadata={"url": "..."}
   - block_end

   注意：
   - 不要发起 HTTP 请求。
   - 不识别 `javascript:` / `file:` / `mailto:` 等非 http(s) scheme。
   - `请看 https://example.com` 这种行内 URL 保持 text。
   - URL 后常见标点如 `.`、`,`、`)` 是否剥离请保持保守，避免误删合法 URL 字符；测试中只要求干净独立 URL。

4. SSE 持久化层
   当前 `backend/app/api/v1/stream.py` 的 `_ContentAccumulator` 已处理 text/code。
   请最小扩展它：
   - diff：累计 raw diff，block_end 时解析为 `DiffBlock` 所需字段。
   - web_preview：从 metadata 持久化 url/title/description/thumbnail_url。
   - 不改变正常 text/code 行为。
   - 不改变 error 状态处理逻辑。

实现约束：
- 不修改 `StreamChunk` 字段；diff raw 内容使用现有 `text_delta`。
- 不修改 `ContentBlock` schema；复用已有 `DiffBlock` 和 `WebPreviewBlock`。
- 不修改 OpenAPI。
- 不修改前端 streaming store；如果前端 live rendering 需要专门处理 diff/web_preview，后续交给 F 任务。
- 不引入第三方依赖。
- 不让 parser 做网络 I/O。
- 不大改 adapter；Claude/OpenAI 继续只调用 parser。

测试要求：

在 `backend/tests/test_artifact_parser.py` 增加：
1. test_diff_fence_emits_diff_block
2. test_patch_fence_emits_diff_block
3. test_regular_code_fence_still_emits_code_block
4. test_standalone_url_emits_web_preview_block
5. test_inline_url_remains_text
6. test_url_split_across_chunks_is_stable
7. test_diff_fence_split_across_chunks_is_stable

在 `backend/tests/test_b1_quality.py` 或新建 `backend/tests/test_stream_content_blocks.py` 增加：
1. test_stream_persists_diff_block
   - monkeypatch `app.api.v1.stream.get_adapter`
   - fake adapter yield start / block_start diff / delta raw diff / block_end / done
   - 断言 DB 中 message.content[0].type == "diff"
   - 断言 filename/before/after 合法

2. test_stream_persists_web_preview_block
   - fake adapter yield start / block_start web_preview(metadata url) / block_end / done
   - 断言 DB 中 message.content[0].type == "web_preview"
   - 断言 url 正确

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py
conda run -n LLMAgent python -m pytest tests/test_b1_quality.py
conda run -n LLMAgent ruff check app/agents/artifact_parser.py app/api/v1/stream.py tests/test_artifact_parser.py tests/test_b1_quality.py

如果新增了 `tests/test_stream_content_blocks.py`，请把它加入 pytest/ruff 命令。

注意：
- 当前本地测试环境使用 Anaconda `LLMAgent`。
- `.env` 和 `backend/.env` 已用于本地/远程开发连接，但禁止提交。
- 测试可能连接远程开发 PostgreSQL；不要打印数据库密码或 API key。

完成后交付说明必须包含：
1. 修改了哪些文件
2. parser 如何识别 diff
3. parser 如何识别 web_preview
4. `_ContentAccumulator` 如何持久化 diff/web_preview
5. 是否修改任何共享契约，预期答案应为没有
6. 运行了哪些测试和 lint，结果如何
7. 未覆盖边界或后续需要 F/B1 协同的内容

本任务完成后不要 commit，不要 push，不要创建 PR。请先把 diff 和测试结果交给 Codex 做最终代码审阅。
````
