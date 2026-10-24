# 研途 Yantu

实验室版保存在 [`ymh` 分支](https://github.com/2816269630/yantu/tree/ymh)，基于 `lxc` 分支的 `a3f4932` 改造。

- 打开 **http://localhost:8089**，点击“创建新账号”自行注册，无默认账号。
- 在 Windows 上双击根目录的 `Start-Yantu.cmd`，或运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Yantu.ps1`。
- 新实例使用独立的数据库和文件卷，首次为空；仅绑定本机 `127.0.0.1`。
- 已整合上游云盘：登录后进入“我的资料 → 我的云盘”，使用三栏目录、上传、共享和版本管理；课题与组会可明确授权后引用云盘文件。

- [本地使用、启停与验收说明](LOCAL_SETUP.md)
- [六模块最终功能约定](yantu-research/LAB_REDESIGN.md)
- [版本序列与发布规则](VERSIONS.md)
- [更新记录](CHANGELOG.md)

`DEVELOPMENT_PLAN.md` 和旧部署文档是上游历史资料；本次实验室版的功能及部署以以上两份说明为准。
