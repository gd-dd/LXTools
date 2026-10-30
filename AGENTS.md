# LXTools 工作目录
正式仓库为 E:\project\LXTools\LXTools。所有修改、测试和构建在此执行。
旧目录 E:\Ruanjian\LXTool 已清空，不要重新写入或恢复旧副本。
用户要求学习手动 Git 操作；未经新的明确指示，不自动 commit、push、打标签或发布 Release。
工具源码、运行数据和构建结果不得加入工具架 Git 提交，遵循 .gitignore。

工具和工具架均严格使用 GitHub Releases 发布版本。正式起点 0.0.1，之后递增；默认分支提交不等于发布工具，禁止重新引入 releases.json 或历史完整包目录。

开发约定：start-dev.bat / start.bat 运行 0.0.0 开发外壳；两版共用发现工具/我的工具/设置与更新，开发版仅额外提供 GitHub 默认分支 0.0.0 工具快照。不要恢复本地工具开发页、自动克隆或本地工具面板预览。开发数据在 runtime/development/profile；正式用户客户端为 E:/Ruanjian/LXTools，仅使用公开 Release。工具架源码可热重载，工具修改须先推送再通过商店更新。现有 tools 目录连接不作为开发预览来源，不递归删除其源码。具体流程见 docs/开发与发布工作流.md 和 lx-tools-workflow Skill。
