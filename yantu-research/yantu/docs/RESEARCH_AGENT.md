# 科研 Agent

科研助手支持持续会话、流式回答、停止生成、参考资料、工具执行过程与历史记录。输入框中可切换 Agent / 对话模式，以及已经配置的连接和模型。同一段会话可以切换模型。历史记录仅当前研途账号可见。

## API 连接

点击右上角头像进入“设置 → 模型与连接”。支持三种协议：

- OpenAI Responses：API 地址通常为 `https://api.openai.com/v1`。
- 兼容接口：使用供应商的 Chat Completions API 地址，通常以 `/v1` 结尾。
- Ollama：Docker 中访问宿主机通常填写 `http://host.docker.internal:11434`。

填写连接名称、地址、API Key 和模型 ID（每行一个），保存后即可使用。“读取模型”会连接服务读取列表，也用于检查认证；不提供列表接口的服务可手工填写模型 ID。编辑时密钥留空表示保持原值。API Key 不会返回前端，不保存在浏览器存储中。

## Codex 账号连接

设置页提供“使用 ChatGPT 登录 Codex”。官方 app-server 启动设备代码登录后，点击验证链接，在 OpenAI 官方页面完成登录并输入代码。若账号未开启设备代码登录，需要先在官方账号的 Codex 安全设置中开启。完成后刷新连接状态和模型列表。

该连接由官方 `@openai/codex`（固定 0.166.0）处理。每个研途用户有独立的 Codex 状态目录，不导入宿主机 Codex 登录，不读取浏览器 Cookie，也不要求用户复制令牌。研途页面显示账号连接状态和可用模型；账号实际支持的模型、额度和登录能力由官方服务决定。

官方参考：[App Server](https://learn.chatgpt.com/docs/app-server)、[Function calling](https://developers.openai.com/api/docs/guides/function-calling)。

## 工具与确认

Agent 可以检索和阅读当前账号可访问的资料、查看有权限的任务和组会，并起草 Markdown 笔记。模型每次调用工具时都重新检查用户权限。引用原文会附上可返回云盘的来源。

笔记工具只生成待确认草稿。只有用户点击“保存到我的云盘”才创建私有文件；取消不会写入云盘，重复确认不会重复创建文件。Agent 不运行终端命令、不修改原资料、不自动共享文件。

对话模式不会主动调用工具；用户选定的参考资料仍会作为本次上下文。每轮最多选择 10 份资料。未配置模型时可使用“本地资料检索”，该模式返回相关原文，不模拟模型生成。

## 部署与备份

在 `yantu-research` 中执行：

```powershell
docker compose --env-file .env.research -f compose.local.yaml up -d --build --wait
```

新增的 `yt_agent_*` 表由原有启动迁移创建，不修改已有业务表数据。API 密钥使用 Fernet 加密；加密密钥及每个用户的 Codex 状态位于上传卷 `.agent/` 目录，不能通过云盘文件接口获取。完整备份须同时保留数据库和整个上传卷；丢失 `.agent/encryption.key` 后需重新配置 API Key。登录状态和密钥都属于私人数据，勿提交 Git。

本地测试使用临时 SQLite 和模拟上游服务，覆盖多轮切换模型、真实工具循环、账号隔离、密钥加密、取消生成、草稿确认与 Codex stdio 协议。实际远程模型调用还需要用户提供可用 API Key 或完成自己的 Codex 登录。
