# 本地实验室版

需求确认：2026-10-24。源码从 `https://github.com/2816269630/yantu` 的 `lxc` 分支克隆，起点提交 `a3f4932`。实验室版及云盘整合代码保存在同仓库的 `ymh` 分支，运行环境仍为本机 Docker。

## 使用

1. 打开 Docker Desktop，使用 Linux 容器。
2. 双击根目录 `Start-Yantu.cmd`。也可运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Yantu.ps1`；只启动已有镜像时加 `-NoBuild`。
3. 打开 http://localhost:8089 ，点击“创建新账号”。使用有效邮箱格式、姓名和至少 12 位密码注册；不需要邀请码，也不会自动创建课题。
4. 在“课题管理”创建课题成为负责人，或申请加入已有课题。负责人在课题详情的“加入申请”中审批。
5. 审批后可在“我的资料”选择课题，上传课题资料、查看组会、参与讨论。负责人或学长在此安排和维护组会；每次组会中可以上传材料和录好的视频。
6. 负责人在“课题管理 → 课题详情 → 任务分配”中分配、编辑任务；执行人的“我的任务”只显示列表和筛选。
7. 所有登录成员都可在“学长留言”发布及评论，作者可编辑、删除自己的留言。
8. 在“我的资料 → 我的云盘”使用个人云盘。未加入课题也能建立多层文件夹、上传和管理自己的文件。列表及目录支持更多操作菜单；搜索按钮支持 Ctrl+F。共享文件以云朵图标标记，只有查看和下载权限。
9. 云盘支持批量选择、拖拽上传、进度提示与失败重试；文件可重命名、移动、修改说明、上传新版本、下载历史版本。PDF 支持阅读进度和个人笔记。文件默认私有，可通过“共享管理”选择同课题成员，只读授权或撤销。
10. 课题资料、组会资料中的“从云盘引用”会明确列出当前成员，确认后授权并引用同一份文件，后续版本同步显示。新加入的成员需单独授权；移出课题会使该课题下的共享失效。课题原有上传文件和录像仍仅对当前成员开放。

首页中间留白，右上角显示已加入课题中最近一次未来组会的倒计时，没有安排时显示“暂无安排”。资料、组会讨论及录像统一在“我的资料”。个人浏览记录可以从“历史记录”打开或清空。

普通文件上限 20 MiB，组会录像上限 1 GiB。视频建议使用浏览器支持的 MP4 或 WebM；其他容器格式可能需要下载后观看。文件、录像、预览和评论均由后端检查课题成员身份；离组后失去读取权限。

## 实例与数据

| 项目 | 本地设置 |
| --- | --- |
| 工作目录 | `D:\yantu1001\yantu` |
| Compose 文件 | `yantu-research/compose.local.yaml` |
| Compose 项目 | `yantu-lxc-lab` |
| 应用地址 | `http://localhost:8089` |
| 数据库 | PostgreSQL 15.7，数据库端口只在 Docker 内部开放 |
| 数据卷 | `yantu-lxc-lab_research_data` |
| 上传卷 | `yantu-lxc-lab_research_uploads` |
| 配置文件 | `yantu-research/.env.research`，已忽略，不提交 Git |

数据库密码由启动脚本随机生成，与网页登录密码无关。本实例不导入旧数据；旧目录、旧容器和旧数据卷均保留。

在 `yantu-research` 目录执行：

```powershell
# 查看状态
docker compose --env-file .env.research -f compose.local.yaml ps
# 停止并保留数据
docker compose --env-file .env.research -f compose.local.yaml stop
# 启动已有镜像
.\Start-Research.ps1 -NoBuild
# 修改源码后重建
.\Start-Research.ps1
# 查看应用日志
docker compose --env-file .env.research -f compose.local.yaml logs --tail 100 research
```

数据保存在以上两个 Docker 卷中。备份和迁移时须同时保留数据库、上传文件及配置。日常启停使用 `stop` 或启动脚本即可。

## 验证

当前版本的验收集是 `backend/tests/test_lab.py`、`backend/tests/test_lab_drive.py`、`backend/tests/test_version.py`，以及两个 `test_lab_*frontend.cjs` 前端验收文件。云盘目录及上传的核心验收复用了上游测试，并适配本系统的申请审批流程。其他上游学习成长和旧反馈流程测试保留作历史参考。

从 `yantu-research/yantu` 目录执行后端测试：

```powershell
docker build -f backend/Dockerfile -t yantu-lxc-lab:local .
docker build -f backend/Dockerfile.test -t yantu-lxc-lab:test .
docker run --rm --network none yantu-lxc-lab:test
```

前端使用 Node.js 24.15 或更高的 24.x 版本：

```powershell
npm ci --no-audit --no-fund
npm run test:ui
```

后端测试使用临时 SQLite 数据库和临时上传目录，覆盖注册、审批、资料隔离、录像范围读取、任务只读、普通成员留言、浏览历史、输入校验、移除旧入口、Cookie 登录退出及版本信息。前端测试验证登录屏障、六模块导航、首页留白、课题选择范围、任务只读、发布留言、文本转义、错误重试与退出。

云盘新增验收覆盖三级目录、账号隔离、重复上传标识、搜索、移动、版本下载、共享撤销、云盘引用与版本同步、个人阅读历史、离组授权失效，以及不能通过云盘绕过课题资料权限。前端验收还覆盖三栏布局、共享文件操作限制、重命名、移动、百分号关键词搜索、共享管理与明确授权引用。

2026-10-24 云盘整合前的数据库、上传文件、运行源码与配置备份在 `backups/before-cloud-20261024`；旧镜像标签为 `yantu-lxc-lab:before-cloud-20261024`。

浏览器验收使用单独的临时容器及测试账号；正式的 8089 实例保留空数据库供用户注册。
