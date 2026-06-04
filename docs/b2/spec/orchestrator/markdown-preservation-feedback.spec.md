# Orchestrator Markdown Preservation Feedback Spec

> Owner: B2
> Related: [message-attribution.spec.md](message-attribution.spec.md), [core.spec.md](core.spec.md), [../../../b1/spec/message-content-block-attribution.spec.md](../../../b1/spec/message-content-block-attribution.spec.md)
> Reporter: F
> Status: Backend action required
> Last updated: 2026-06-04

## 1. 结论

当前聊天中仍然出现 Markdown 渲染异常，根因不是前端 Markdown renderer，而是 B2 Orchestrator 在输出 ReAct trace / observation 时，把子 Agent 的原始 Markdown 再次拼接成一个单行文本块。

前端已经可以正常渲染子 Agent 原始 text block。异常只出现在 Orchestrator 额外生成的这类 block：

```text
ReAct step 1
Observation: - create-coder-demo @claude-code succeeded Text: I'll create all three files in the `coder-demo/` directory.已创建 **coder-demo** 项目，包含以下三个文件： ### 文件结构 ``` coder-demo/ ├── index.html — 主页面（在线代码编辑器界面） ├── styles.css — 深色主题样式 └── app.js — 交互逻辑 ``` ### 功能说明 | 功能 | 描述 | |------|------| ...
Action: finish: ...
```

这段内容把 Markdown 标题、代码块、表格、列表都压到同一行，导致前端只能按普通段落和 inline code 渲染。

## 2. 复现样本

后端消息响应中同一条 `agent` message 内同时存在两类 text block。

### 2.1 子 Agent 原始输出正常

```json
{
  "type": "text",
  "agent_id": "claude-code",
  "text": "已创建 **coder-demo** 项目，包含以下三个文件：\n\n### 文件结构\n\n```\ncoder-demo/\n├── index.html   — 主页面（在线代码编辑器界面）\n├── styles.css   — 深色主题样式\n└── app.js       — 交互逻辑\n```\n\n### 功能说明\n\n| 功能 | 描述 |\n|------|------|\n| **代码编辑区**（左侧） | 带行号的文本编辑器，默认显示 JavaScript 示例代码，支持 Tab 缩进 |\n..."
}
```

该 block 的换行、标题、代码块、表格都是合法 Markdown，前端可以正确渲染。

### 2.2 Orchestrator ReAct observation 异常

```json
{
  "type": "text",
  "agent_id": "orchestrator",
  "text": "ReAct step 1\nObservation: - create-coder-demo @claude-code succeeded Text: I'll create all three files in the `coder-demo/` directory.已创建 **coder-demo** 项目，包含以下三个文件： ### 文件结构 ``` coder-demo/ ├── index.html — 主页面（在线代码编辑器界面） ├── styles.css — 深色主题样式 └── app.js — 交互逻辑 ``` ### 功能说明 | 功能 | 描述 | |------|------| ..."
}
```

该 block 已经丢失 Markdown block 语义：

- `### 文件结构` 不在行首。
- fenced code block 的 ``` 不在独立行。
- GFM table 行都被挤在同一行。
- `|------|------|` 不再是表格分隔行。
- `-` / numbered list 没有稳定行首。

前端无法可靠、无副作用地从这种单行文本恢复原始 Markdown，尤其是代码块和表格。

## 3. 影响

用户可见问题：

- Orchestrator 消息中出现一大段拥挤文本。
- 标题、表格、代码块、列表都不能按 Markdown 显示。
- inline code 被大量高亮，视觉噪声很大。
- 子 Agent 原始输出已经展示过一次，Orchestrator observation 又重复展示一遍，信息重复且更难读。

产品层面：

- 多 Agent 协作结果看起来像渲染 bug。
- 会削弱 `block.agent_id` 分段展示的效果。
- 前端只能做启发式容错，无法保证所有 Markdown 样本都修复。

## 4. 责任边界

### B2 需要修改

B2 负责 Orchestrator ReAct trace、task result context、summary 文本生成，因此需要保证输出给聊天流的 text block 是 Markdown-safe 的。

重点路径：

- `backend/app/agents/orchestrator/react.py`
  - `_react_observation_text(...)`
  - `_react_trace_text(...)`
- `backend/app/agents/orchestrator/summary.py`
  - `format_task_result_context(...)`
  - `truncate_preserving_edges(...)`
- 可能相关：
  - `backend/app/services/orchestrator_memory.py`
  - `OrchestratorTaskAttempt.text_preview` 生成/截断逻辑

### B1 通常不需要修改

当前样本说明 B1 已经能持久化子 Agent 原始 text block 中的 `\n\n`、代码块和表格。B1 只有在发现 stream accumulator 持久化时主动替换换行为空格时才需要参与。

### F 已做但不能根治

前端已做过扁平 Markdown 的有限容错，但它只能处理简单标题/列表。对于 fenced code block、GFM table、路径树、被截断文本，前端不能可靠恢复原始结构。

## 5. 后端修复方案

### 5.1 首选方案：不要把完整子 Agent Markdown 放进 ReAct observation 聊天块

ReAct observation 是 Orchestrator 内部决策轨迹，不应该把子 Agent 最终 Markdown 全量复制给用户。

建议：

```text
ReAct step 1
Observation:
- task: create-coder-demo
- agent: @claude-code
- status: succeeded
- artifacts: coder-demo/index.html, coder-demo/styles.css, coder-demo/app.js
- text_preview: 已创建 coder-demo 项目，包含 3 个文件。
Action: finish
```

要求：

- `text_preview` 是纯文本摘要，不包含 Markdown 表格、代码块、完整正文。
- 子 Agent 原文只通过它自己的 `agent_id="claude-code"` text block 展示。
- Orchestrator summary 只列结构化状态、artifact、evaluation，不重复整段子 Agent 正文。

### 5.2 如果必须展示 observation，必须保留 Markdown block 边界

如果产品仍需要展示 ReAct trace，则 observation 必须是 Markdown-safe：

```markdown
ReAct step 1

Observation:

- task: create-coder-demo
- agent: @claude-code
- status: succeeded

Child text:

> 已创建 coder-demo 项目，包含以下三个文件：
> 
> ### 文件结构
> 
> ...

Action:

finish: 已成功创建 coder-demo 演示页面。
```

但不推荐完整引用子 Agent Markdown，因为：

- 会重复展示。
- 嵌套 code fence 和 table 很容易再次破坏。
- 聊天流阅读成本高。

### 5.3 `text_preview` 生成规则

`TaskAttempt.text_preview` / observation preview 应满足：

- 用于摘要时：转纯文本，移除 Markdown block 语法。
- 保留可读空格，但不要保留完整表格、代码块。
- 截断前先压缩为自然语言摘要，而不是简单把原文换行替换为空格。
- 不要把多个子 Agent text block 直接拼成一行。

建议实现 helper：

```python
def markdown_to_observation_preview(text: str, max_chars: int) -> str:
    """Return a user-safe plain-text preview for Orchestrator ReAct observation."""
```

规则建议：

- 删除 fenced code block 内容或替换为 `[code block omitted]`。
- GFM table 只保留表头或转为 `功能: 描述; ...` 的短句。
- Markdown heading 转为普通短句。
- 连续空白压缩为一个空格。
- 最大长度控制在 240 到 400 字符。

### 5.4 `_react_trace_text` 格式要求

当前：

```python
lines = [
    f"ReAct step {iteration}",
    f"Observation: {observation}",
    f"Action: {action_summary}",
]
```

建议改为：

```python
lines = [
    f"ReAct step {iteration}",
    "",
    "Observation:",
    observation,
    "",
    "Action:",
    action_summary,
]
```

并保证 `observation` 本身不是完整子 Agent Markdown，而是结构化短摘要。

### 5.5 生产 UI 建议隐藏 ReAct trace

如果 ReAct trace 主要用于调试，建议后端增加配置：

```python
emit_react_trace_to_chat: bool = False
```

生产聊天流默认不输出 `ReAct step ... Observation ...`。调试模式可进入 run detail / memory detail，而不是直接污染用户主聊天流。

## 6. 验收标准

### 6.1 API 响应验收

使用相同请求：

```text
给我创建一个coder
```

期望：

1. 子 Agent 原始 text block 保持完整 Markdown：
   - `### 文件结构`
   - fenced code block 独立成行
   - GFM table 分隔行独立成行

2. Orchestrator text block 不再包含完整子 Agent Markdown 单行拷贝。

3. 如果仍输出 `ReAct step`：
   - `Observation:` 后是结构化短摘要。
   - 不包含 `### 文件结构 ``` coder-demo/ ... | 功能 | 描述 | |------|` 这种单行混合内容。

4. `Execution summary` 只展示：
   - task 状态
   - agent
   - artifacts
   - evaluation
   - review / conflict / error metadata

### 6.2 自动测试建议

新增 B2 测试：

- `backend/tests/test_orchestrator_react.py`
- 或对应 Orchestrator summary / execution 测试

测试样例：

```python
child_text = """已创建 **coder-demo** 项目，包含以下三个文件：

### 文件结构

```
coder-demo/
├── index.html
└── app.js
```

| 功能 | 描述 |
|------|------|
| 运行按钮 | 执行代码 |
"""
```

断言：

```python
assert "### 文件结构 ``` coder-demo/" not in orchestrator_trace
assert "| 功能 | 描述 | |------|------|" not in orchestrator_trace
assert "coder-demo/index.html" in execution_summary
```

如果选择保留 Markdown：

```python
assert "\n\n### 文件结构\n\n" in child_block_text
assert "\n|------|------|\n" in child_block_text
```

### 6.3 前端验收

后端修复后，前端无需依赖扁平 Markdown 修复器也应满足：

- Orchestrator 主消息不再出现一大段单行 Markdown。
- 子 Agent 输出仍按 block.agent_id 分段展示。
- Markdown 标题、代码块、表格正常渲染。

## 7. 不建议的修复

不要只做：

- 让前端继续用正则猜测恢复所有 Markdown。
- 在 B1 持久化层把所有 text 再跑 Markdown formatter。
- 在 Orchestrator summary 中继续拼完整子 Agent 正文，只是简单加几个换行。
- 用 HTML 字符串替代 Markdown。

这些都会扩大问题面，且无法稳定处理代码块、表格、路径树和截断文本。

