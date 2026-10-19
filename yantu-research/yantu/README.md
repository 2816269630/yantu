# 研途模块开发指南

本目录包含科研系统的前端、后端和测试。日常开发在 `dev/hawkpp` 分支进行。

不知道修改某个功能该找哪个文件时，先看 [功能导图与代码对照](docs/FUNCTION_MODULES.md)。

## 启动与更新

从上一级 `yantu-research` 目录启动 Docker Desktop 后运行 `./Start-Research.ps1`。
首次启动会生成本地 `.env.research`；数据库和附件分别保存在 Docker 数据卷中。
修改代码后，在同一目录运行：

```powershell
docker compose --env-file .env.research -f compose.local.yaml up -d --build
```

## 前端：按界面维护

| 目录 | 职责 |
| --- | --- |
| `frontend/app.js` | 加载页面模块、绑定全局事件、启动应用 |
| `frontend/core/` | 请求、会话、共享状态、路由、动作分发 |
| `frontend/core/session-state.js` | 退出和登录失效时统一清理会话；业务模块登记自己的资源清理函数 |
| `frontend/components/` | 图标、表单、弹窗、导航、资料链接等公共组件 |
| `frontend/pages/home/` | 工作台、通知、搜索 |
| `frontend/pages/learning/` | 我的学习、学习路线、前辈经验 |
| `frontend/pages/collaboration/` | 任务与反馈、研究记录、组会 |
| `frontend/pages/drive/` | 云盘、目录、共享、上传、资料详情、独立阅读器 |
| `frontend/pages/assistant/` | 科研助手、来源选择、问答 |
| `frontend/pages/settings/` | 个人资料、课题组、成员与邀请、交接 |
| `frontend/pages/settings/handovers.js` | 交接列表、任务与资料多选、提交和接收；具体权限由后端复核 |
| `frontend/styles/` | 公共样式及各页面模块样式 |

前端使用浏览器原生 ES Modules，无需打包即可运行。依赖必须通过 `import` 声明；
不要向 `window` 注入业务函数或在其他文件中覆盖函数。页面注册到 `core/state.js`
导出的 `pages` 注册表，再由 `core/router.js` 调用。

页面模板和列表展示放在对应页面文件；交互动作和表单提交放在相邻的 `actions.js`
或 `*-actions.js`。跨页面复用的能力提取到 `components` 或 `core`。

新增交互时在 `core/actions.js` 的动作/表单注册表登记处理函数；应用入口无需添加
业务判断。页面样式放到 `styles/pages`，公共颜色、字体和组件保持统一。

## 后端：按业务维护

`backend/yantu/app.py` 只负责创建应用、配置数据库及注册路由。

每个 `backend/yantu/modules/<业务>/` 模块按照实际需要包含：

- `router.py`：接口地址、请求参数、身份依赖、调用业务函数。
- `service.py`：权限检查、状态流转、查询及事务。
- `models.py`：该业务的数据库表。
- `schemas.py`：该业务使用的请求结构或格式约定。

现有模块：`auth`、`teams`、`learning`、`tasks`、`meetings`、`progress`、`drive`、
`assistant`、`handovers`、`notifications`、`dashboard`。

公共能力：

- `core/database.py`：统一 SQLAlchemy Base、ID 和时间默认值。
- `core/models.py`：显式导入各业务模型以注册全部数据表，以及公共扩展元数据。
- `core/dependencies.py`：请求级数据库会话、当前用户、集成服务上下文。
- `core/permissions.py`：课题组角色和任务访问等共享权限规则。
- `core/metadata.py`、`validation.py`、`presentation.py`：公共数据工具。
- `integrations/plane.py`、`ollama.py`：外部服务客户端及文档检索。
- `migrations/`：保持现有表名与数据的数据库升级。

接口通过 `APIRouter` 显式注册，不使用重复路由覆盖机制。不同业务调用共享能力时
使用明确的函数导入；存在双向业务依赖时，跨模块导入放到调用函数内，避免初始化循环。
集成服务通过 `ServiceContext` 显式传入，不使用全局可变数据库会话。

## 验证

后端测试使用临时 SQLite 数据库，不使用正在运行的科研业务数据库。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q

npm ci
npm run test:ui
```

浏览器验收使用单独、尚未初始化的临时服务，不能指向日常业务服务。
`test_browser.cjs` 会创建测试账号和记录，并在启动前检查服务未初始化：

```powershell
$env:YANTU_TEST_BASE_URL = 'http://127.0.0.1:18089'
$env:YANTU_BROWSER_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:browser
```

## 本次迁移范围

旧的 `features.py`、`cloud_drive.py`、根目录 `models.py`、`security.py`、
`plane_client.py`、`research_assistant.py`、`bootstrap.py` 和 `migrations.py`
已迁移至上述模块；旧前端 `cloud-drive.js`、`cloud-upload.js`、`styles.css`、
`reader.js`、`reader.css` 也已替换。原文件不再保留第二套实现。

`app.py`、`frontend/app.js` 保留为轻量入口。PDF.js 第三方文件、部署配置、许可证、
数据库表结构和业务数据保持原有用途。
