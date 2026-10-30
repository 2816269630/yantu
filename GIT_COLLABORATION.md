# Git 入门与四人协作指南

适用场景：四个人共同开发一个 GitHub 项目。

## 1. Git 和 GitHub 是什么

**Git** 是版本管理工具：记录代码的变化，方便查看历史、恢复版本和合并修改。

**GitHub** 是托管 Git 仓库的平台：保存远端代码，提供任务管理、代码审查等协作功能。

| 概念 | 简单理解 |
| --- | --- |
| 仓库（Repository） | 项目的文件和版本历史 |
| 工作区 | 你正在编辑的文件 |
| 暂存区 | 准备放进下一次提交的修改 |
| 提交（Commit） | 一次有说明的版本记录，保存在本地 |
| 分支（Branch） | 一条独立的开发路线，可以完成后再合并 |
| 远端（Remote） | GitHub 上的仓库，通常命名为 `origin` |
| Pull Request（PR） | 请求把一个分支的修改合并到另一个分支，供大家审查 |
| 冲突（Conflict） | Git 无法自动合并的修改，需要人工确认 |

记住这条路线：**编辑文件 → add 暂存 → commit 本地提交 → push 上传到 GitHub**。

`commit` 不会自动上传；`push` 才会把提交发送到远端。

## 2. 开始使用

### 首次配置（每个人做一次）

先安装 Git，在终端（PowerShell 或 Git Bash）运行 `git --version`，能看到版本号就表示可以使用。后续命令都在终端中执行。

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

这些信息用于标记提交作者，不是 GitHub 登录凭据。

### 获取项目

其他成员接受 GitHub 协作者邀请后，打开仓库页面，点击 **Code → HTTPS**，复制仓库地址。在终端进入准备存放项目的目录，再克隆：

```bash
git clone <仓库地址>
cd <项目目录>
```

例如仓库地址是 `https://github.com/example/yantu.git`：

```bash
git clone https://github.com/example/yantu.git
cd yantu
git status
```

示例地址需要换成你们的真实地址。`clone` 会下载项目和版本历史，并创建项目目录；`cd` 进入该目录。之后的 Git 命令都在项目目录里执行。私有仓库如提示登录，使用已接受邀请的 GitHub 账号完成认证。

已经有本地仓库的人继续使用现有目录，不需要重新 `git init` 或克隆。

本文假设主分支叫 `main`，如果项目实际使用 `master`，将命令中的 `main` 换成 `master`。

### 常用命令

| 命令 | 用途 |
| --- | --- |
| `git status` | 查看当前分支、修改和暂存情况 |
| `git diff` | 查看尚未暂存的具体修改 |
| `git diff --staged` | 查看准备提交的修改 |
| `git add <文件>` | 将指定文件的修改放入暂存区 |
| `git commit -m "说明"` | 保存一次本地提交 |
| `git pull --ff-only origin main` | 在本地 `main` 上更新远端代码；发生分叉时停止 |
| `git push` | 上传当前分支的提交（首次需要设置上游） |
| `git switch <分支>` | 切换到已有分支 |
| `git switch -c <分支>` | 创建并切换到新分支 |
| `git branch` | 查看本地分支，星号标记当前分支 |
| `git branch -a` | 查看本地分支和已获取的远端分支 |
| `git merge <分支>` | 将指定分支的提交合并到当前分支 |
| `git log --oneline -5` | 查看最近五次提交 |

尖括号中的内容是占位符，执行时替换为实际值，不保留尖括号。

## 3. 我们采用的分支策略

采用 **GitHub Flow：main 主分支 + 短期任务分支 + PR 审查**。

`main` 保存经过审查、可以正常运行的代码。每个任务从最新的 `main` 创建分支，完成后通过 PR 合并回来。

| 分支名称 | 用途 | 示例 |
| --- | --- | --- |
| `main` | 稳定主分支 | `main` |
| `feat/*` | 新功能 | `feat/user-login` |
| `fix/*` | 修复问题 | `fix/login-error` |
| `refactor/*` | 重构 | `refactor/api-client` |
| `docs/*` | 文档 | `docs/setup-guide` |

**按任务建分支，不按人建长期分支。** 一个分支尽量只做一件事，目标是在 1～3 天内完成；大任务拆成小任务。初期不额外建立 `develop` 分支。

### 分支究竟怎么用

可以把 `main` 理解为大家共用的正式版本，任务分支是从它出发的一条开发路线。创建分支不需要复制项目文件夹，仍然在同一个目录中编辑代码。

```bash
git switch -c feat/user-login
git branch
```

看到 `* feat/user-login`，表示当前在登录功能分支；接下来的提交记录在这个分支上。它此时只存在于你的电脑，执行 `git push -u origin feat/user-login` 后才会在 GitHub 上出现。

切换已有分支：

```bash
git switch main
git switch feat/user-login
```

切换时，Git 会把文件切换为对应分支的版本。**先提交当前修改再切换**，不要把未提交的修改当作已保存在分支里的版本。

## 4. 完成一个任务的标准流程

### 第一步：明确任务

在 GitHub 创建 Issue，写清楚“要做什么、谁负责、怎样算完成”。每个任务安排一位负责人和另一位审查人。

### 第二步：更新代码，创建分支

先用 `git status` 检查当前修改，提交或妥善保存后再切换分支。

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/user-login
```

### 第三步：开发、检查、提交

完成修改后，运行项目需要的检查或测试，并确认提交内容：

```bash
git status
git diff
git add <本次修改的文件>
git diff --staged
git commit -m "feat: 添加用户登录功能"
git push -u origin feat/user-login
```

`-u` 设置当前分支对应的远端分支，之后可以直接运行 `git push`。

提交说明保持简短明确，例如 `feat: 添加注册页面`、`fix: 修复密码校验`、`docs: 更新启动说明`。

### 第四步：提交 PR，审查并合并

在 GitHub 创建 PR：来源为任务分支，目标为 `main`。写清楚修改内容、验证方式和关联 Issue；写 `Closes #12` 可在合并后关闭对应任务。

另一位成员审查，负责人处理反馈，通过检查后使用 **Squash and merge** 合并。这样一个任务在 `main` 上形成一条清晰的提交。

创建 PR 时，在仓库的 **Pull requests → New pull request** 中选择 `base: main`、`compare: feat/user-login`。合并发生在 GitHub 上，你电脑里的 `main` 需要执行下一步的 `pull` 才能更新。

### 第五步：清理分支，准备下一个任务

在 GitHub 删除已合并的远端任务分支，本地执行：

```bash
git switch main
git pull --ff-only origin main
```

本地旧分支可以稍后删除。使用 Squash 合并后，`git branch -d` 可能拒绝删除；确认 PR 已合并且没有遗漏的提交后，才使用 `git branch -D <旧分支>`。

## 5. 同步修改与处理冲突

### 理解合并的方向

**`git merge X` 的意思是：把 X 分支的提交合并进你当前所在的分支。** 执行前先用 `git branch` 确认当前位置。

| 场景 | 当前分支（接收修改） | 合并来源 | 团队采用的方式 |
| --- | --- | --- | --- |
| 获取大家最新的代码 | 自己的任务分支 | `origin/main` | 本地执行 `git merge origin/main` |
| 把完成的功能交给大家 | GitHub 上的 `main` | 自己的任务分支 | 在 GitHub 通过 PR 合并 |

用于理解本地合并的命令示例：

```bash
git switch main
git merge feat/user-login
```

这会把登录分支的提交合并到**本地 main**，不会自动上传到 GitHub。团队实际交付功能时走 PR 流程；本示例只解释合并方向，不作为日常交付步骤。

### 在任务分支上同步主分支

开发期间，如果其他人的代码已合并到 `main`，在自己的任务分支同步：

```bash
git switch feat/user-login
git fetch origin
git merge origin/main
```

`fetch` 获取远端更新，`origin/main` 表示本地记录的远端主分支状态；`merge` 把它合并到当前任务分支。同步前先提交或妥善保存工作区修改。同步后检查运行结果，再执行 `git push`。

合并成功后两个分支仍然存在，合并不会自动删除来源分支。

### 遇到冲突怎么办

如果出现冲突：

1. 用 `git status` 找出冲突文件。
2. 打开文件，查看 `<<<<<<<`、`=======`、`>>>>>>>` 标记。
3. 确定正确内容并删除标记；涉及他人逻辑时一起确认。
4. 执行 `git add <冲突文件>`，再执行 `git commit` 完成合并。
5. 重新验证，执行 `git push` 更新 PR。

如果暂时无法处理，可以执行 `git merge --abort` 取消本次合并。

## 6. 四人团队的共同约定

- **所有修改通过 PR 合并到 main**，至少由另一人审查。
- **合并前确保项目可运行**，通过已有构建、代码检查和相关测试。
- **提前约定接口**：路径、字段、返回格式和错误处理，避免前后端各自猜测。
- **公共修改提前沟通**：数据库、公共模块、依赖配置等变更先在 Issue 中说明。
- **不提交密码和密钥**：用 `.gitignore` 排除本地配置，提供 `.env.example` 作为填写示例。
- **不随意强制推送**：尤其禁止对 `main` 使用 `push --force`。

仓库支持时，用分支保护或 Rulesets 强制执行 PR、审查和检查要求。用 GitHub Actions 自动运行构建和测试；发布时从验证通过的 `main` 打版本标签，例如 `v0.1.0`。

## 7. 每次开发的速查清单

**开始：** 明确任务 → 更新 main → 创建任务分支。

**开发：** 修改 → 检查 → 暂存 → 提交 → 推送。

**结束：** 创建 PR → 他人审查 → 通过检查 → 合并 → 更新本地 main。
