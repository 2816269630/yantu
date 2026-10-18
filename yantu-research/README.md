# 研途科研系统

研途是一个独立的本地科研协作系统。用户只需要访问 `http://localhost:8088`，即可在同一套界面中完成学习路线、学习计划、科研任务、审核反馈、组会、资料库、研究记录、经验传承、成员权限、资料交接和数据导出。

## 启动

确保 Docker Desktop 已启动，然后在 PowerShell 中进入本目录并运行：

```powershell
.\Start-Research.ps1
```

也可以直接运行 `start.cmd`。容器启动完成后打开 `http://localhost:8088`。首次访问会引导创建管理员和第一个课题组，后续成员可通过负责人生成的邀请链接注册。

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

## 数据与备份

科研业务数据保存在 PostgreSQL Docker 卷，上传文件保存在独立附件卷。系统内“空间与权限 → 导出与备份”可以导出当前账号有权读取的结构化科研记录；完整恢复还需备份数据库卷和附件卷。

## 开发验证

模块说明见 [模块开发指南](yantu/README.md)。测试使用独立临时数据，不访问日常业务数据库。

```powershell
cd yantu
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
npm ci
npm run test:ui
```
