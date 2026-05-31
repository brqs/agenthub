---
name: git-commit-pr
description: Use when preparing AgentHub Git commits, reviewing staged changes, creating a safe feature/fix/docs branch, pushing a branch, or drafting a Pull Request while preserving unrelated user changes.
---

# Git Commit And PR Skill

## When To Use

Use this skill when the user asks to:

- 检查当前 Git 修改。
- 创建提交、推送分支或准备 PR。
- 整理 PR 描述、测试证据和变更摘要。
- 处理多人协作下的本地未提交修改。

## Branch Rules

| Branch | Purpose |
|--------|---------|
| `main` | 生产分支，只通过 PR 合并，禁止直接提交和 force push |
| `feat/*` | 新功能 |
| `fix/*` | bug 修复 |
| `docs/*` | 文档更新 |
| `refactor/*` | 重构 |

## Safety Rules

- 永远先运行 `git status --short` 和 `git diff --stat`。
- 不使用 `git add -A` 或 `git add .` 作为默认操作；只暂存本次任务相关文件。
- 不提交 `.env`、密钥、密码、token、数据库 dump 或大型生成物。
- 不执行 `git reset --hard`、`git checkout -- .`、`git clean -fd`，除非用户明确要求丢弃修改，并且已经先展示影响范围。
- 不 force push 到 `main`。
- 不覆盖、回滚或混入用户的无关修改。

## Standard Workflow

### 1. Inspect State

```bash
cd /home/ubuntu/agenthub
git status --short
git branch --show-current
git diff --stat
```

如存在已暂存内容，也检查：

```bash
git diff --cached --stat
git diff --cached
```

### 2. Inspect Changes

查看本次任务相关文件的具体 diff：

```bash
git diff -- <path1> <path2>
```

对新文件先确认体量：

```bash
wc -l <new-file>
```

### 3. Create Or Confirm Branch

如果当前在 `main`，先创建工作分支：

```bash
git switch -c feat/<short-name>
```

如果已经在任务分支上，继续使用当前分支。不要在未确认的情况下切走用户正在使用的分支。

### 4. Stage Only Relevant Files

```bash
git add <path1> <path2>
git status --short
git diff --cached --stat
```

提交前必须确认 staged diff 只包含本次任务内容：

```bash
git diff --cached
```

### 5. Commit

提交格式：

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <short summary>

<optional details>
EOF
)"
```

常用 type：

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`

示例：

```bash
git commit -m "$(cat <<'EOF'
docs(b2): organize orchestrator specs

- Move orchestrator specs into a dedicated package
- Update B2 spec index
- Preserve old implementation evidence as focused reports
EOF
)"
```

### 6. Push

```bash
git push -u origin <branch-name>
```

后续同分支推送：

```bash
git push
```

如果 push 被拒绝，先 `git fetch origin` 并检查远端差异，不要直接 force push。

### 7. Prepare PR

PR 标题格式：

```text
<type>(<scope>): <short summary>
```

PR body：

```markdown
## Summary
- ...

## Test plan
- [ ] ...

## Risk
- ...
```

如 `gh` CLI 不可用，使用浏览器打开：

```text
https://github.com/brqs/agenthub/compare/main...<branch-name>
```

## Conflict Handling

需要同步远端时，先保留现场：

```bash
git status --short
git fetch origin
git log --oneline --decorate --graph --max-count=12 --all
```

若有本地修改，优先不要自动 stash。确需 stash 时使用带说明的 stash：

```bash
git stash push -m "wip before syncing <task-name>" -- <path1> <path2>
```

恢复后必须检查冲突和 diff：

```bash
git stash pop
git status --short
git diff --stat
```

## Final Report Checklist

- 当前分支。
- 提交 SHA。
- 已提交文件列表。
- 实际运行的测试 / lint / type check。
- 未运行测试的原因。
- PR 链接或可打开的 compare 链接。
