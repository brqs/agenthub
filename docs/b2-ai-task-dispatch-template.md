# B2 AI 子任务分发模板

> 适用范围：B2 Agent 集成工作中，Codex 将任务拆解后交给 Claude Code 执行的场景。

## 协作角色

- B2 负责人：决定 Agent 集成方向和任务优先级。
- Codex：负责总览大局、分工协调、任务拆解、边界和契约检查、最终代码审阅。
- Claude Code：负责执行 Codex 拆解后的具体子任务。

## 分发原则

每个交给 Claude Code 的子任务必须完整、明确、可验证。任务描述不能只写一句“实现某功能”，必须说明背景、边界、禁止事项、测试和交付要求。

## 环境约定

B2 本地开发默认使用 Anaconda 环境 `LLMAgent`。分发 Python 子任务时，验证命令应优先使用该环境，例如：

```bash
conda run -n LLMAgent python -m pytest <test-path>
```

如果缺少项目依赖，应在已有 `LLMAgent` 环境内执行 `python -m pip install -e ".[dev]"`，不要创建新的 Python 环境。

## 标准模板

```text
任务编号：B2-XX
任务名称：<一句话说明任务>

背景：
<说明该任务在 AgentHub 架构中的位置、上游/下游依赖、为什么现在做>

请先阅读：
1. AGENTS.md
2. <相关文档或代码文件>

文件范围：
允许修改：
- <path>

禁止修改：
- <path>

实现目标：
<描述最终要达到的行为，不只描述改哪个文件>

核心行为：
1. <行为 1>
2. <行为 2>
3. <行为 3>

实现约束：
- 不修改 BaseAgentAdapter.stream() 签名，除非团队确认。
- Adapter 内不访问数据库；配置由外层注入。
- 不引入无必要的新依赖。
- 不修改共享契约文件，除非任务明确要求。
- 保持 async/await 约定，避免同步阻塞 I/O。

测试要求：
1. <测试场景 1>
2. <测试场景 2>
3. <测试场景 3>

验证命令：
- conda run -n LLMAgent python -m pytest <test-path>

交付要求：
完成后请说明：
1. 修改了哪些文件
2. 核心实现思路
3. 运行了哪些测试，结果如何
4. 是否存在未覆盖的边界情况或后续风险
```

## 审阅入口

Claude Code 完成子任务后，B2 将 diff、关键文件或测试结果交给 Codex。Codex 默认按代码审阅模式检查：

- 是否违反目录所有权和模块边界
- 是否违反 OpenAPI、BaseAgentAdapter、ContentBlock 契约
- 是否存在行为 bug、异常路径或流式事件顺序问题
- 测试是否覆盖关键路径
- 是否引入无关重构或不必要依赖
