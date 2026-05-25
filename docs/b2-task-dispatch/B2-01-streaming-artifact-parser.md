# B2-01 — 实现 StreamingArtifactParser 流式产物解析器

> 交给 Claude Code 执行的完整任务命令。

```text
任务编号：B2-01
任务名称：实现 StreamingArtifactParser 流式产物解析器

角色背景：
你现在作为 Claude Code，负责执行 AgentHub 项目中 B2 方向的具体子任务。
Codex 负责总览、任务拆解和最终审阅。你只需要完成本任务范围内的实现和测试，不要做无关重构。

项目背景：
AgentHub 是一个 IM 聊天式多 Agent 协作平台。后端 Agent 层通过 BaseAgentAdapter 输出统一的 StreamChunk，B1 的 SSE 端点会把 StreamChunk 转成前端可消费的 SSE event。

当前问题：
backend/app/agents/artifact_parser.py 中的 StreamingArtifactParser 仍是 TODO。它需要把 LLM 上游返回的普通文本流解析成 text/code 内容块对应的 StreamChunk 事件。

本任务不依赖数据库、不依赖 Redis、不依赖 OpenAI/Anthropic API Key，也不依赖 Alembic migration。请只实现 parser 和对应单元测试。

请先阅读：
1. AGENTS.md
2. docs/b2-ai-task-dispatch-template.md
3. backend/app/agents/types.py
4. backend/app/agents/base.py
5. backend/app/agents/artifact_parser.py
6. backend/app/agents/adapters/mock.py
7. backend/app/api/v1/stream.py

允许修改：
- backend/app/agents/artifact_parser.py
- backend/tests/test_artifact_parser.py

如果 backend/tests/test_artifact_parser.py 不存在，请新建。

禁止修改：
- backend/app/agents/base.py
- backend/app/agents/types.py
- backend/app/agents/registry.py
- backend/app/agents/adapters/**
- backend/app/api/v1/**
- backend/app/models/**
- backend/app/schemas/**
- shared/openapi.yaml
- docker-compose.yml
- AGENTS.md
- docs/**

实现目标：
实现 StreamingArtifactParser，使它可以接收 LLM 流式文本片段，并输出标准 StreamChunk 列表。它至少需要支持 Markdown fenced code block，把普通文本输出为 text block，把代码围栏内容输出为 code block。

核心 API：
- feed(text: str) -> list[StreamChunk]
- flush() -> list[StreamChunk]

必须保持这两个方法同步，不要改成 async。

核心行为：

1. 普通文本解析
   输入：
   hello world

   输出事件顺序：
   - block_start, block_index=0, block_type="text"
   - delta, block_index=0, text_delta="hello world"
   - flush() 时输出 block_end, block_index=0

2. 单个代码块解析
   输入：
   before
   ```python
   print(1)
   ```
   after

   输出应包含 3 个 block：
   - text block：包含 before
   - code block：metadata.language = "python"，code_delta 包含 print(1)
   - text block：包含 after

3. 语言标识规则
   - ```python -> metadata={"language": "python"}
   - ```tsx -> metadata={"language": "tsx"}
   - ```diff -> metadata={"language": "diff"}
   - ``` 后面没有语言 -> metadata={"language": "text"}
   - language 只取 fence 后第一段非空字符串，去掉首尾空白
   - diff 暂时仍作为 block_type="code"，不要新增 block_type

4. 跨 chunk 的代码围栏
   必须正确处理 fence 被拆开的情况，例如：

   feed("hello\n``")
   feed("`python\nprint(1)\n")
   feed("``")
   feed("`\nworld")
   flush()

   要求：
   - 不能丢字符
   - 不能把 ``` 泄漏到 text_delta 或 code_delta
   - block 顺序仍正确
   - code block 内容包含 print(1)
   - 最后的 text block 内容包含 world

5. 多个代码块
   输入中可以包含多个 fenced code block。
   block_index 必须从 0 开始递增，不能重复，不能跳号。

6. 未闭合代码块
   输入：
   ```python
   print(1)

   如果直到 flush() 都没有 closing fence，flush() 应正常输出当前 code block 的 block_end，不抛异常。

7. 空输入
   - feed("") 返回 []
   - 新 parser 直接 flush() 返回 []
   - 不要创建空 block

实现建议：
- 使用状态机实现，不要只靠一次性正则。
- 推荐状态至少包含 TEXT 和 CODE。
- 为了处理跨 chunk 的 ```，需要保留少量 pending buffer。
- 当前 block 打开时才允许输出 delta。
- 切换 block 类型时，必须先输出旧 block 的 block_end，再输出新 block 的 block_start。
- flush() 必须关闭当前打开的 block，并清空内部 buffer。
- 不要访问数据库。
- 不要引入新的第三方依赖。
- 不要修改 StreamChunk 或 BaseAgentAdapter。

测试要求：
请新增 backend/tests/test_artifact_parser.py，至少覆盖以下测试：

1. test_plain_text
   - feed("hello world")
   - flush()
   - 断言事件顺序是 block_start -> delta -> block_end
   - 断言 block_type 是 text
   - 断言 text_delta 是 hello world

2. test_single_code_block
   - 输入包含 before + python code fence + after
   - 断言共有 3 个 block_start
   - 断言第二个 block_start 是 code
   - 断言第二个 block metadata.language == "python"
   - 断言 code_delta 拼接后包含 print(1)
   - 断言 text_delta 拼接后包含 before 和 after

3. test_fence_split_across_chunks
   - 按多次 feed 拆开 opening fence 和 closing fence
   - 断言没有任何 text_delta/code_delta 包含 ```
   - 断言 code 内容正确
   - 断言最后 text 内容正确

4. test_multiple_code_blocks
   - 输入包含两个 fenced code block
   - 断言 block_index 为 0, 1, 2, 3, ... 递增
   - 断言两个 code block 的 language 分别正确

5. test_unclosed_code_block_flushes
   - 输入未闭合代码块
   - flush() 后最后有 block_end
   - 不抛异常
   - code_delta 包含代码内容

6. test_empty_feed_and_empty_flush
   - feed("") == []
   - 新 parser 直接 flush() == []

测试辅助：
可以在测试文件里写小 helper，把 chunks 按 event_type、block_index 聚合，方便断言文本和代码内容。

验证命令：
在 backend 目录执行：

conda run -n LLMAgent python -m pytest tests/test_artifact_parser.py

如果已经激活 `LLMAgent` 环境，也可以执行：

python -m pytest tests/test_artifact_parser.py

完成后交付说明必须包含：
1. 修改了哪些文件
2. StreamingArtifactParser 的状态机如何工作
3. 运行了哪些测试命令
4. 测试是否通过
5. 是否存在未覆盖边界或后续风险

注意：
本任务完成后不要继续实现 ClaudeAdapter、OpenAIAdapter、CustomAdapter 或 Orchestrator。那些是后续任务。
```
