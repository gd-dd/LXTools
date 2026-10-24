# LXTool · 通用工具商店

一个 GitHub 仓库就是一个工具。客户端自动分页扫描 **gd-dd** 的仓库，只有带有效 `.lxtool/manifest.json` 和对应资源的项目才进入商店。用户不添加仓库，按需安装作者发布的工具。

## 使用

启动 `dist/LXTool/LXTool.exe` 或 `start.bat`。

- **发现工具**：按分类、关键词、已下载 / 未下载 / 可更新筛选，卡片直接下载、更新、卸载全部版本。点击图标查看 Markdown 介绍，“版本与卸载”用于选择版本、回退或卸载单个版本。这里没有运行面板入口。
- **我的工具**：只列出已下载工具。点击图标或“打开工具”直接进入独立完整面板；面板页没有概览、下载、卸载或版本管理页签，只保留返回、工具名称、夹子归属和工具本身的内容。
- **我的夹子**：中文收纳，点击夹子后仍走“我的工具”直接打开面板。下载完成后请主动进入“我的工具”使用。

工具架不绑定 Max、Unity 或特定宿主。软件路径、启动参数、复制安装操作和面板由各个工具定义；工具架只提供通用下载、渲染和动作执行。

## 工具开发

以 [LX 工具仓库规范 v2](docs/lx-tool-v2.md) 为准。旧 v1 文档仅供历史参考。

```text
工具仓库/.lxtool/
  manifest.json
  icon.png
  README.md
  panel.json
  releases.json   # 可选历史版本列表
```

`kind: lx-tool` 是格式声明，不是密码学认证。图标、Markdown、面板和业务文件都按清单摘要校验。扫描和浏览不会运行工具代码。

当前示例 `gd-dd/3dmaxScript` 合并显示为“Max 工具集”，包含六个脚本功能。Max 的启动命令由这个工具自己的 manifest 声明。当前兼容性待实测。

## 文件位置与更新

- 工具：EXE 同级 `tools/<仓库名>--<repositoryId>/versions/<version>/`。
- 个人配置：`%LOCALAPPDATA%/LXTool/`。软件配置按工具隔离。
- 工具代码不进入工具架仓库或公共 ZIP，只内置商店展示快照。
- 旧版六个脚本目录已归档到 runtime/backups/legacy-installed/，不会再作为当前工具目录。
- 客户端自更新保留 tools 和个人配置。软件目录之外的插件副本需自行管理。

## 构建

运行 `./build.ps1`，会执行自动测试和 PyInstaller 打包，输出 `dist/LXTool-windows-x64.zip`。

公开仓库可直接扫描。私有仓库需要后续接入 GitHub 账户授权；OAuth 尚未配置，见 [注册准备](docs/github-login-setup.md)。

## 导航

完整目录与职责见 [文件结构](docs/file-structure.md)。当前作者协议只看 docs/lx-tool-v2.md；旧文档在 docs/history/，旧适配代码在 src/legacy/，早期网页原型与旧商店样例在 archive/。


完整自定义面板：阅读 [native API 1](docs/custom-panel-api.md)，可运行模板在 `examples/native-panel/`。模板不会自动加入用户商店。

Windows 安装包：运行 `./build-installer.ps1`（需要 Inno Setup 6.7 或更高的 6.x 版本），输出安装 EXE、更新 ZIP 和 SHA256SUMS.txt。首次发布请逐步阅读 [Release 教程](docs/first-release.md)。
