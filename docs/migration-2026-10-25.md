# 开发目录迁移记录

2026-10-25：正式开发仓库改为 `E:\project\LXTools\LXTools`。
旧目录 `E:\Ruanjian\LXTool` 暂留作迁移前备份，不再继续开发。

## 文件去向
- 源码、文档、素材、测试：新仓库原位保留；迁移前核对与旧目录一致。
- `tools/`：源码模式已安装工具。
- `dist/LXTool/tools/`：EXE 模式已安装工具。
- `runtime/tool-authoring/`：独立工具开发源码，尤其 3ds Max 工具集。
- `runtime/toolchains/`：本地 Inno Setup 编译器。
- `runtime/backups/`、`runtime/audit/`：备份和验证证据。
- `runtime/deliverables/`：历史交付快照。旧源码 ZIP 仅为迁移前快照，不要再覆盖当前仓库。
- `.venv/`：在新位置重新创建，不使用旧虚拟环境。
- `build/`、`dist/`：新位置重新构建；后续发布使用新 `dist` 下同一轮的 EXE、ZIP、SHA256SUMS.txt。
- `%LOCALAPPDATA%\LXTool`：个人配置原位保留，迁移前 JSON 另备份在 `runtime/backups/migration-2026-10-25-profile/`。

共迁移并逐文件校验 781 个文件，明细见 `runtime/audit/migration-files.json`（记录复制时状态，重新构建后 dist 中程序文件会变化）。
Git 的 `.git`、现有未提交修改保留；没有代为 commit、push 或发布。

## 验证
- 新 `.venv`：Python 3.12.9。
- `./build.ps1`：39 项测试通过，PyInstaller 构建成功。
- `./build-installer.ps1 -SkipClientBuild`：Inno Setup 编译成功。
- 日志：`runtime/audit/migration-build.log`、`runtime/audit/migration-installer.log`。

## 日常操作
双击新仓库 `start.bat` 启动，或运行 `dist/LXTool/LXTool.exe`。
在 Codex 中使用新仓库作为项目目录；当前绑定旧目录的会话需显式使用新工作目录。
其他编辑器和 3ds Max 工具开发会话也需改用新路径，避免继续编辑旧副本。
旧目录待用户确认新客户端、工具和编辑器均正常后再清理。

客户端新 EXE 已实际启动，通过 UI 自动化确认商店扫描 11 个仓库、发现 1 个 LX 工具；我的工具保留 Max 工具集，中文夹子“角色动画”保留。截图受其他窗口遮挡，未将截图视作视觉验收证据。

已从‘我的工具’打开 Max 工具集 1.1.0 自定义面板，六个工具按钮和 3ds Max 程序路径正常加载；本次未启动 3ds Max 执行工具业务。


## Max 工具开发对话迁移复核

- 对旧、新 runtime/tool-authoring/3dmaxScript 逐文件比较，82 个文件无遗漏、内容一致（更新本地维护说明之前）。
- 当前开发入口：runtime/tool-authoring/3dmaxScript/multi-instance；同级 AGENTS.md 记录维护边界。
- 更新历史维护说明中的协议路径；已发布包和文件摘要保持原样。
- 新环境 39 项测试通过，工具 1.1.0 / 1.0.1 / 1.0.0 包校验通过。
- 新源码包及新 EXE 安装包的后台 hello 均成功；本轮没有启动 Max 或重做多实例业务测试。
- 运行中的 LXTool 来自新 dist 路径。未自动提交、推送或发布。
- 详细记录：runtime/audit/max-migration-2026-10-25.json。

## 清理结果（2026-10-25）
按用户要求，旧目录内全部文件已移入回收站，不再作为开发副本保留。旧路径目前仅为空文件夹，被现有会话进程占用。
过时的 runtime/deliverables/LXTools-source-0.5.0.zip 已移入回收站。
切换 Codex 和编辑器到新仓库，关闭旧目录关联会话后可删除旧空文件夹。
个人配置及必要的迁移备份保留，新仓库运行环境和当前交付包保留。
