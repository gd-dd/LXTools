# 文件结构与用途

当前版本：一个 GitHub 仓库就是一个工具。六个 Max 脚本是同一个 Max 工具集的内部功能。

## 根目录导航

| 目录或文件 | 用途 | 是否可删除 |
| --- | --- | --- |
| `src/` | 当前桌面程序源码 | 否 |
| `src/legacy/` | v1 兼容模块，仍由历史回归测试使用，当前商店不导入 | 否，不能只凭“旧”字删除 |
| `examples/native-panel/` | 完整自定义面板开发模板，不自动加入商店 | 保留 |
| `tests/` | 协议、安装、回退、界面、动画等自动测试 | 否 |
| `assets/brand/` | 工具架使用的 PNG 和 Windows ICO | 否 |
| `assets/originals/launcher/` | 用户提供的工具架原始高清图片 | 保留原件 |
| `assets/originals/tools/3dmaxScript/` | 用户提供的 Max 专属图标原件；不是工具业务代码 | 保留原件 |
| `catalog/repo-store.json` | 启动时可用的商店展示快照 | 否 |
| `docs/` | 当前协议、架构、品牌、OAuth 和目录说明 | 否 |
| `docs/history/` | 旧版本规范与验收记录，仅供参考 | 按需归档，非当前规范 |
| `archive/web-prototype/` | 最初的网页原型，当前不使用 | 历史源码，保留 |
| `archive/catalog-v1/` | 旧商店格式及样例，legacy.catalog 仍引用 | 保留 |
| `tools/` | 源码运行模式安装的工具及版本 | 删除相当于卸载，不当缓存清理 |
| `dist/LXTool/` | 正式桌面客户端，运行 LXTool.exe | 保留 |
| `dist/LXTool/_internal/` | EXE 必需的 Python、Qt、DLL、资源 | 不可拆删 |
| `dist/LXTool/tools/` | 正式客户端安装的工具 | 与源码模式独立，保留 |
| `dist/LXTool-windows-x64.zip` | 可分发安装包，不含本机工具业务包 | 可重新构建 |
| `build/` | 自动生成的 spec、中间文件和干净打包暂存 | 可清理；构建会再生成 |
| `.venv/` | 固定版本 Python 开发／测试／构建环境 | 可重建，但日常开发保留 |
| `.github/workflows/build.yml` | GitHub 云端构建流程 | 保留 |
| `.gitignore` | 排除工具、个人暂存和生成物，避免提交 | 保留 |
| `build.ps1` | 安装依赖、运行测试、打包并生成 ZIP | 构建入口 |
| `start.bat` | 优先启动成品，没有成品则使用源码环境 | 启动入口 |
| `requirements-lock.txt` | 固定依赖版本 | 保留 |
| `README.md` / `TODO.md` | 使用入口 / 交付与验证清单 | 保留 |

`__pycache__` 是 Python 自动生成的字节码缓存，可以再生成；第三方环境内部文件不做逐项手工精简。

## 本地开发资料（不提交 GitHub）

`runtime/` 不是客户端的个人配置目录。现在按用途分为：

- `audit/`：全量文件清单、整理前后统计、移动和回收记录。
- `tool-authoring/3dmaxScript/initial-v2/`：Max 初次适配 LX v2 的制作暂存。
- `tool-authoring/3dmaxScript/icon-release/`：Max 1.0.1 图标发布准备，含历史版本和维护说明。工具开发资料不会打进工具架发布包。
- `backups/legacy-installed/`：旧版拆成六个工具时的安装数据备份，source / desktop 分别是两种运行模式。
- `backups/prototypes/`：改成商店前的桌面源码快照。
- `backups/catalog-v1/`：早期工具索引备份。

这些历史源文件具有恢复价值；已经归类，未按重复文件直接销毁。

## 一个工具的目录

```text
tools/
  3dmaxScript--1342543761/       仓库名 + 稳定仓库 ID，一款工具
    versions/
      1.0.0/                   完整旧版本，可回退
      1.0.1/                   完整新版本
        .lxtool/
          manifest.json        身份、资源摘要和通用动作声明
          icon.png             工具自己的图标
          README.md            商店详情正文
          panel.json           工具自己的面板
        tool.json              客户端安装收据
        *.ms / Nahida.jpg      工具内部脚本和业务资源
```

源码模式与成品模式都有这样的 tools 目录，各自使用各自安装区；不能把它们合并或删掉其中一套而不改变运行配置。

个人配置位于项目外 `%LOCALAPPDATA%/LXTool/`，保存夹子、选择版本、软件路径及商店缓存。本次整理不修改这些数据。

## 本次清理（2026-10-24）

完整扫描包含隐藏文件、依赖、二进制和工具安装目录。初始清单见 `runtime/audit/cleanup-before.json`；操作记录见同目录 `cleanup-moves.json` 和 `cleanup-recycled.json`。

送入回收站：旧 build 中间产物、根目录生成的 LXTool.spec、update-smoke 测试客户端副本、v2-live 下载验证副本、已完成的一次性关机脚本、与原始图片 SHA256 完全一致的 assets/brand/source.png，以及搬空的 runtime/archive 目录。回收站不自动清空。

原图集中到 assets/originals，保留中文名称；构建只使用 assets/brand/icon.png 和 icon.ico。工具制作暂存和历史备份分别归入 tool-authoring 与 backups。新 spec 统一生成到 build 中，避免再次散落根目录。

当前源码职责见 [架构说明](architecture.md)，作者规范见 [LX v2 协议](lx-tool-v2.md)。本次只整理本地工程，没有推送远端。

构建成功后已再次将 build 暂存送入回收站；dist 成品保留。下次 build.ps1 会自动重建 build。

安装相关目录：`installer/` 保存中文安装脚本、安装说明和安装测试；`build-installer.ps1` 为安装包构建入口；`docs/first-release.md` 为首次发布教程。`runtime/toolchains/` 是本机打包编译器，`runtime/installer-smoke/` 是安装与卸载验证记录，均不提交远端。
