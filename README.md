# LXTool · 通用工具商店

一个当前有效产品仓库对应一个工具。客户端读取作者发布的商店索引，启动先使用本地工具与缓存；完整仓库扫描由作者维护。只有带有效 `.lxtool/manifest.json`、对应资源和公开稳定GitHub Release的项目才提供安装版本，默认分支修改不会自动发布。Max工具集统一包含绑定蒙皮、飘带、骨架重定向等子工具，已合并的历史仓库不重复注册商店卡。

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
```

`kind: lx-tool` 是格式声明，不是密码学认证。图标、Markdown、面板和业务文件都按清单摘要校验。扫描和浏览不会运行工具代码。

`gd-dd/3dmaxScript` 显示为“Max 工具集”，包含六个原脚本及绑定蒙皮、LX飘带、骨架重定向，共九项。场景业务窗口在Max内；目标实例和启动逻辑由工具自身提供，宿主适配范围以对应工具说明和验收记录为准。

## 文件位置与更新

- 工具：EXE 同级 `tools/<仓库名>--<repositoryId>/versions/<version>/`。
- 个人配置：`%LOCALAPPDATA%/LXTool/`。软件配置按工具隔离。
- 工具代码不进入工具架仓库或公共 ZIP，只内置商店展示快照。
- 旧版六个脚本目录已归档到 runtime/backups/legacy-installed/，不会再作为当前工具目录。
- 客户端自更新保留 tools 和个人配置。软件目录之外的插件副本需自行管理。

## 构建

运行 `./build.ps1`，会执行自动测试和 PyInstaller 打包，输出 `dist/LXTool-windows-x64.zip`。

当前公开工具无需GitHub登录即可下载。客户端提供可选的Device Flow登录，私有仓库不在当前公开商店范围。连接失败、限流与登录失效分别处理；0.0.7起提供明确的重新登录入口和公开操作的一次匿名恢复，详见[网络与登录](docs/网络与登录.md)。

## 导航

完整目录与职责见 [文件结构](docs/file-structure.md)。当前作者协议只看 docs/lx-tool-v2.md；旧文档在 docs/history/，旧适配代码在 src/legacy/，早期网页原型与旧商店样例在 archive/。


完整自定义面板：阅读 [native API 1](docs/custom-panel-api.md)，可运行模板在 `examples/native-panel/`。模板不会自动加入用户商店。

Windows 安装包：运行 `./build-installer.ps1`（需要 Inno Setup 6.7 或更高的 6.x 版本），输出安装 EXE、更新 ZIP 和 SHA256SUMS.txt。首次发布请逐步阅读 [Release 教程](docs/first-release.md)。

## 本地开发与正式客户端

日常修改请双击 `start-dev.bat`（`start.bat` 同样进入开发版）。显示 0.0.0，工具架源码保存后自动重载。两版共用发现工具和我的工具；开发版额外提供 GitHub 默认分支 0.0.0 工具快照，工具源码须先推送，不再提供本地工具开发页。正式用户入口为 `E:\Ruanjian\LXTools\LXTool.exe`，只使用 GitHub Releases。完整操作见 [开发与发布工作流](docs/开发与发布工作流.md)。
