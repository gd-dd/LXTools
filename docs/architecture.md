# 当前架构（LX 仓库协议 v2）

桌面入口是 src/desktop.py。这是通用工具容器，没有内置 Max 业务命令。一个仓库对应一个稳定 repository ID，多个功能和多个版本都属于这个工具。

| 模块 | 职责 |
| --- | --- |
| desktop.py | 商店、详情、版本页、夹子、设置 |
| repository_source.py | 扫描作者仓库、固定提交、资源校验、安装 |
| lx_protocol.py | 声明、面板、动作和本地包校验 |
| tool_storage.py | 可读仓库目录、稳定身份与旧目录迁移 |
| native_panels.py | native API 1 加载、资源摘要、独立数据及面板生命周期 |
| repository_panels.py | 工具面板、工具声明的通用动作 |
| library.py | 中文夹子、工具归属、卸载、原子配置写入 |
| github_api.py | GitHub REST 请求 |
| compatibility.py | 可选年份式软件版本范围 |
| updater.py | 工具架自更新与保留用户数据 |
| theme.py | 黑白灰三级中性色、翠绿与半透明渐变 |
| gold_effect.py | 金色旋转边框、少量色散与隐藏时停止动画 |
| brand.py | 工具架品牌、文字对比度 |
| core.py | 历史存储兼容和更新器共享能力，当前入口仍引用 |
| legacy/ | 旧 v1 目录、Max 专用适配器，仅供回归；当前入口不导入 |

数据流：作者默认分支 .lxtool → 扫描 → 商店缓存 → 用户选择安装 → 固定 commit 下载和摘要校验 → tools/仓库名--ID/versions/版本 → 用户主动点击动作。

商店图片来自工具 manifest.icon，Markdown 来自工具 manifest.readme。工具架品牌图只用于 EXE、窗口和侧栏。发现和查看介绍不执行工具代码。

旧 repo-ID/版本目录仍可识别；下次安装前整体迁移到可读目录。内容、身份、夹子归属和软件配置不变。遇到冲突、损坏或未知文件会保留原目录并提示。

作者规范见 [LX 工具 v2](lx-tool-v2.md)，目录导航见 [文件结构](file-structure.md)。OAuth 尚未配置，当前入口扫描公开仓库；Max 软件内执行待作者实测。
