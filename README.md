# LXTool

Windows 游戏制作工具架。首版负责工具获取、更新、多版本管理，不修改 3ds Max 或 Unity 项目。

## 使用

解压完整的 `LXTool-windows-x64.zip`，运行其中 `LXTool/LXTool.exe`，无需安装 Python。不要单独移动 EXE，需保留同目录的 `_internal`。

1. 添加 GitHub 仓库（owner/repo），选择分类。
2. 选中工具，检查工具更新，选择 ZIP 附件下载。
3. 在本地版本中选择并启用；可以保留多个版本、打开目录、卸载非当前版本。
4. 私有仓库通过“仓库凭据”保存令牌到 Windows 凭据管理器，留空提交可清除。不要将令牌写进代码或发送到聊天。
5. 导入目录接受 catalog/catalog.schema.json 定义的 JSON；同步 GitHub 目录读取指定仓库的 catalog/catalog.json。

数据存于 `%LOCALAPPDATA%/LXTool`，升级程序目录不影响工具数据。只能运行一个桌面实例。

ZIP 下载上限 512 MB，解压上限 2 GB、20000 文件；拒绝路径穿越和符号链接。远端提供 SHA-256 时核对，否则明确显示未验证远端哈希。下载后的工具不会自动执行。版本查询最多覆盖 1000 个 Release。

## 客户端发布

客户端更新源为 gd-dd/LXTools。检查稳定发布，下载命名为 LXTool-windows-x64.zip 且具有 SHA-256 的更新包，校验后准备到独立目录并打开。关闭旧窗口后运行新版，保留旧版本及用户数据；不原地覆盖正在运行的程序。

源码和目录文件已提交到 gd-dd/LXTools，真实目录同步已验证。当前尚无 Release；客户端升级和私有资源仍待真实发布资源验收。具体工具后续添加。

## 构建

Windows + Python 3.12：运行 `powershell -ExecutionPolicy Bypass -File build.ps1`，安装锁定依赖、运行测试、使用 PyInstaller 生成桌面包和 ZIP。源码入口 `src/desktop.py`；旧浏览器入口 `src/app.py` 仅供历史参考。

GitHub Actions 工作流位于 `.github/workflows/build.yml`，构建产物作为工作流 Artifact 保存。未配置自动发布 Release。

验证：`.venv/Scripts/python.exe -m unittest discover -s tests -v`。

## 人工验收

检查窗口大小与中文显示；添加仓库并查询版本；下载两个版本后切换、关闭重开确认状态；检查空仓库、无 ZIP 发布与网络失败的提示。

构建、测试与尚未完成项见 TODO.md。工具分发约定见 docs/tool-distribution.md。
