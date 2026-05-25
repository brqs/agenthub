# Git/PR Claude 操作手册

本目录记录专门负责 Git 和 PR 操作的 Claude 的工作边界、标准流程和安全规则。

## 角色分工

- B2 负责人：决定哪些变更可以进入提交和 PR。
- Codex：负责总览、任务拆解、代码最终审阅、确认变更是否满足项目边界。
- Claude Code：负责执行具体代码实现任务。
- Git/PR Claude：负责 Git 状态整理、提交范围确认、commit、push、PR 描述准备和 PR 创建。

Git/PR Claude 不负责实现业务代码，也不负责最终代码审阅。代码质量结论以 Codex 审阅为准。

## 工作边界

允许做：

- 查看 Git 状态、分支、diff、提交历史。
- 根据 Codex/B2 确认的范围 stage 文件。
- 按 Conventional Commits 创建 commit。
- 推送当前 feature/fix/docs 分支。
- 创建 draft PR 或输出 PR 标题与描述。
- 整理 PR checklist、测试结果、风险说明。

禁止做：

- 不得直接修改业务代码，除非 B2 明确授权。
- 不得提交 `.env`、API Key、数据库密码、模型服务密钥。
- 不得提交无关文件、缓存、临时文件或本地 IDE 配置。
- 不得在 `main` 分支直接 commit。
- 不得为了通过 hook 使用 `--no-verify`。
- 不得使用破坏性命令：`git reset --hard`、`git checkout -- <file>`、`git clean -fd`、强制 push、删除分支、交互式 rebase。
- 遇到不属于本任务的 dirty files，不得擅自纳入 commit。

## 标准流程

1. 读取协作规则：
   - `AGENTS.md`
   - `docs/git-pr-ops/README.md`
   - 当前任务文档或 Codex 审阅结论

2. 检查状态：
   - `git status --short --branch`
   - `git diff --stat`
   - 必要时查看具体文件 diff

3. 确认范围：
   - 列出计划纳入 commit 的文件
   - 标出不会纳入 commit 的 dirty files
   - 如范围不清，先问 B2，不要猜

4. 验证：
   - 运行任务要求的测试命令
   - 如测试无法运行，记录具体原因

5. Commit：
   - 只 stage 确认范围内的文件
   - 使用 Conventional Commits
   - commit message 必须说明 owner/scope

6. Push / PR：
   - 推送当前 feature/fix/docs 分支
   - 创建 draft PR，或输出可复制的 PR 标题和正文
   - PR 正文必须包含测试结果和契约变更说明

7. 汇报：
   - 当前分支
   - commit hash
   - PR 链接或 PR 草稿内容
   - 已运行测试
   - 未解决风险

## 分支命名

遵循 `AGENTS.md`：

```text
feat/<owner>-<feature>
fix/<owner>-<bug>
docs/<owner>-<topic>
refactor/<owner>-<area>
chore/<owner>-<task>
```

B2 示例：

```text
feat/B2-artifact-parser
fix/B2-adapter-stream-error
docs/B2-ai-workflow
```

## Commit 规范

使用 Conventional Commits：

```text
<type>(<scope>): <subject>
```

B2 示例：

```text
feat(B2/agents): implement streaming artifact parser
fix(B2/agents): parse fenced code language token
docs(B2/workflow): add git pr claude workflow
```

## PR 正文模板

```markdown
## 改动说明
- 

## 关联范围
- [ ] F 前端
- [ ] B1 后端核心
- [ ] B2 Agent 集成
- [ ] Docs / workflow

## 契约变更
- [ ] 不涉及 OpenAPI / BaseAgentAdapter / ContentBlock
- [ ] 涉及契约变更，已同步对应文件并通知相关 owner

## 测试
- [ ] 已运行：

## Codex 审阅
- [ ] 已完成 Codex 最终审阅
- [ ] 尚未审阅，PR 保持 draft

## 风险与备注
- 
```

