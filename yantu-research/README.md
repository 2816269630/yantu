# 研途科研系统

研途是一个独立的本地科研协作系统。用户只需要访问 `http://localhost:8088`，即可在同一套界面中完成学习路线、学习计划、科研任务、审核反馈、组会、资料库、研究记录、经验传承、成员权限、资料交接和数据导出。

## 启动

确保 Docker Desktop 已启动，然后在 PowerShell 中进入本目录并运行：

```powershell
.\Start-Research.ps1
```

也可以直接运行 `start.cmd`。容器启动完成后打开 `http://localhost:8088`。首次访问会引导创建管理员和第一个课题组。后续用户可在登录页点击“创建账号”，使用姓名、邮箱和密码直接注册，注册后自动登录并获得个人空间。邀请码为选填项，用于加入对应课题组；普通注册不会自动加入任何已有课题组。

默认开放账号注册。如需仅允许受邀成员注册，可在本地 `.env.research` 中设置 `ALLOW_PUBLIC_SIGNUP=0` 后重新启动。

## 供局域网成员使用

将 `.env.research` 中的 `RESEARCH_BIND` 设置为 `0.0.0.0`，重新运行启动命令，并在 Windows 防火墙中允许 TCP 8088。其他成员随后可通过 `http://你的局域网IP:8088` 访问；负责人在“空间与权限 → 成员与邀请”中生成邀请链接。

## 更新代码后重新部署

```powershell
docker compose --env-file .env.research -f compose.local.yaml up -d --build
```

查看状态和日志：

```powershell
docker compose --env-file .env.research -f compose.local.yaml ps
docker compose --env-file .env.research -f compose.local.yaml logs -f --tail=100
```

停止系统：

```powershell
docker compose --env-file .env.research -f compose.local.yaml down
```

`down` 不会删除数据库和附件。不要附加 `-v`，除非明确要清空本地数据。

## 科研 Agent 与模型配置

在“设置 → 模型与连接”添加 OpenAI Responses、兼容 Chat Completions 或 Ollama API，也可以使用 ChatGPT 账号登录 Codex。科研助手输入框可切换模型和 Agent / 对话模式，保留历史会话，并展示工具执行过程。笔记草稿由用户确认后保存。

连接、工具范围与备份说明见 [科研 Agent 文档](yantu/docs/RESEARCH_AGENT.md)。

## 数据与备份

科研业务数据保存在 PostgreSQL Docker 卷，上传文件保存在独立附件卷。系统内“空间与权限 → 导出与备份”可以导出当前账号有权读取的结构化科研记录；完整恢复还需备份数据库卷和附件卷。

## 开发验证

```powershell
cd yantu\backend
..\..\.venv\Scripts\python.exe -m pytest -q
C:\Users\33518\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --check ..\frontend\app.js
```
