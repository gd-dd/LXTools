# LX 工具仓库规范 v2

本规范取代“每个脚本是一个工具”的旧约定。**一个 GitHub 仓库就是一个工具**。工具架是通用容器，不以 3ds Max、Unity 或某个宿主作为工具身份。仓库内可以有多个脚本、功能与页面分组，它们都属于同一个工具。

## 1. 标准目录

```text
任意工具仓库/
├─ .lxtool/
│  ├─ manifest.json      必需：LX 工具标识、展示资料、文件清单和动作
│  ├─ icon.png           必需：商店图标（也可用 jpg / webp）
│  ├─ README.md          必需：点击图标后阅读的介绍
│  ├─ panel.json         必需：工具架面板；不需要时写 none
│  └─ releases.json      可选：所有释出版本索引
├─ scripts/             业务代码，目录由工具作者决定
└─ assets/              业务资源
```

`.lxtool/manifest.json` 中 `schemaVersion: 2` 与 `kind: "lx-tool"` 是 LX 格式声明。工具架还会检查图标、Markdown、面板、文件摘要以及引用关系。仅创建一个同名空目录不算 LX 工具。此声明不是数字签名或安全认证；内容来源由 GitHub 仓库归属确认。

## 2. 身份与自动发现

客户端分页扫描 `gd-dd` 账户的仓库列表，检查默认分支的 `.lxtool/manifest.json`。没有标识的普通项目不会进入商店，也不会下载整个游戏工程。

- GitHub 的数值 repository ID 是唯一身份，本地使用 `repo-<repositoryId>`。仓库改名不会创建第二个工具。
- 一个仓库无论有多少脚本、目录或发行版本，都只显示一张商店卡片。
- 自动导入是加入商店目录，安装仍由用户主动选择；发现和阅读介绍不会执行代码。
- 公共仓库无需登录。尚未配置 OAuth 时只能扫描公开仓库；后续授权后才能识别账户可访问的私有来源。
- 格式错误的仓库独立报告，其他仓库继续扫描；网络错误时保留该仓库上次有效缓存。仓库明确移除标识后会从下一次扫描结果消失。
- 普通用户不添加仓库、不填写来源地址。

## 3. manifest.json

```json
{
  "schemaVersion": 2,
  "kind": "lx-tool",
  "name": "短工具名",
  "description": "一句话说明用途。",
  "version": "1.0.0",
  "category": "实用工具",
  "icon": ".lxtool/icon.png",
  "readme": ".lxtool/README.md",
  "panel": ".lxtool/panel.json",
  "applications": {},
  "actions": {},
  "files": {
    ".lxtool/icon.png": "替换为文件的 SHA-256",
    ".lxtool/README.md": "替换为文件的 SHA-256",
    ".lxtool/panel.json": "替换为文件的 SHA-256"
  },
  "releaseNotes": "本次更新内容。",
  "publishedAt": "2026-10-24"
}
```

这是字段示例，不可带摘要占位符直接发布。

| 字段 | 约定 |
| --- | --- |
| name | 必需，1–20 字符，支持中文；商店展示用，不用仓库英文名代替 |
| description | 必需，1–160 字符的简短说明 |
| version | 必需，最长 64 字符；推荐语义版本 1.0.0；已发布同版本不得改内容 |
| category | 可选，自定义短分类；不限定 Max / Unity |
| icon | 必需，包内真实 PNG/JPEG/WebP，最大 1024×1024 和 2 MiB，推荐方形 256×256 |
| readme | 必需，UTF-8 Markdown，最大 256 KiB |
| panel | 必需，UTF-8 JSON，具体类型见下文 |
| applications | 可选，工具需要配置的外部程序；没有外部程序则为空 |
| actions | 可选，工具提供的通用动作 |
| files | 必需，文件路径到小写 SHA-256 的映射，包含图标、说明、面板及所有业务文件 |
| releaseNotes / publishedAt | 可选，版本页更新说明与真实发行日期 |

所有资源路径相对**工具包根目录**，使用 `/`，允许子目录；不能使用绝对路径、`..`、反斜线、Windows 保留设备名或大小写冲突。files 不包含 manifest 自己，也不能占用客户端的 tool.json 收据。最多 2000 文件、单文件 64 MiB、整个工具包 512 MiB。

## 4. 面板属于工具

```json
{
  "type": "declarative",
  "title": "我的操作台",
  "accent": "#86ead5",
  "sections": [
    {"title": "说明", "text": "先准备工作文件。"},
    {"actions": [{"action": "open-editor", "label": "打开编辑器"}]}
  ]
}
```

工具作者决定标题、文字、分组顺序、按钮、强调色；工具架负责渲染、滚动及版本管理。按钮 action 引用 manifest.actions 的键，不再使用工具架内置的 launchHost / openPluginUI / installPlugin 等 Max 专用动作。

无面板工具仍需 `.lxtool/panel.json`：

```json
{"type":"none"}
```

复杂工具可使用 native API 1，由工具提供完整 PySide6 QWidget，自行决定全部布局、样式、控件及交互。入口声明为 `{"type":"native","apiVersion":1,"entry":"ui/panel.py"}`。完整约定、运行环境与生命周期见 [自定义面板 API](custom-panel-api.md)。声明式 JSON 与 none 继续兼容；不要将 native Python 执行能力混入声明式文本。

## 5. 通用动作：工具决定打开哪个软件

以下例子展示如何由工具声明一个外部编辑器，名称与参数都不写死在工具架内：

```json
{
  "applications": {
    "editor": {"name":"我的编辑器", "executable":"editor.exe"}
  },
  "actions": {
    "open-editor": {
      "type":"process", "application":"editor",
      "arguments":["--open", "{file:assets/example.txt}"]
    },
    "show-files": {"type":"openFolder"},
    "install-files": {
      "type":"copy", "files":["assets/example.txt"],
      "destinationFolder":"MyTool"
    }
  }
}
```

- **process**：使用用户在该工具面板配置的 application，或 `executable: "bin/my-tool.exe"` 指向包内 EXE，二者选一。包内 EXE 必须在 files 中。arguments 为独立参数数组，以 shell=False 启动，不拼接 shell 命令。
- `{file:相对路径}`：展开为工具包内的绝对文件路径，引用必须在 files 中；执行前再次校验。
- **copy**：用户选择安装目标目录，然后复制 files 指定的文件到 `<目标>/<destinationFolder>/<version>`，存在同名版本不覆盖。
- **openFolder**：打开已安装工具包目录。

3ds Max 工具可以自行声明 `executable: "3dsmax.exe"` 和参数 `['-U', 'MAXScript', '{file:某脚本.ms}']`；其他工具可声明自己的 EXE、参数和资源。这是工具的业务定义，工具架不包含该命令或按宿主名写分支。

application 可包含 compatibility：`{"range":"2024.1~2026.3","testedVersions":["2026.3"]}`。范围含两端；未测试用 unverified。当前此可选范围语法适用于年份式版本，其他工具可省略并在 Markdown 说明运行要求。配置按仓库身份隔离，不污染其他工具。

## 6. Markdown 介绍

在“发现工具”点击**图片图标**或“详情”进入介绍，默认渲染 README.md。工具面板仅从“我的工具”或夹子打开，打开后独占内容区，不混入概览或下载卸载管理。建议包括用途、截图说明、功能列表、使用步骤、依赖、兼容性及更新信息。当前支持文本、标题、列表、代码块和表格；介绍不会加载外部图片或本地文件，也不会自动打开链接。商店图标必须是单独图片文件，不能依赖 Markdown 的远程资源。

## 7. 所有释出版本

没有 releases.json 时，默认收录根目录 manifest 声明的当前版本。要提供历史版本与回退，作者必须保留历史包并添加索引：

```json
{
  "schemaVersion": 2,
  "releases": [
    {"version":"1.0.0", "path":"releases/unverified/1.0.0"},
    {"version":"1.1.0", "path":"releases/2024.1~2026.3/1.1.0"}
  ]
}
```

每个 path 下都包含完整 `.lxtool/` 和自己的业务文件，manifest 的 version 必须与索引一致。空字符串 path 表示仓库根目录。索引中版本号不能重复。兼容目录命名是工具仓库自己的组织约定，通用工具可以采用 `releases/1.0.0`。

客户端将列表和文件固定到同一个 Git commit 后下载，不下载未列入 files 的其他工程文件。安装位置是 `tools/<仓库名>--<仓库ID>/versions/<version>/`。更新保留旧包，版本页可切换回退和卸载。仓库内增加多少版本都不增加商店卡片。

## 8. 发布检查

1. 准备图标、README、panel 与工具业务文件。
2. 明确软件依赖和动作；不需要面板则选择 none。
3. 计算 files 中每个文件的真实摘要；更改面板/Markdown/图标也需要更新摘要。
4. 验证所有动作引用存在，确认扫描和介绍不执行代码；native 仅在用户打开工具面板时导入，构造不自动启动宿主。
5. 提交到 gd-dd 账户下的工具仓库默认分支；需要回退时同时维护 releases.json。
6. 客户端点击“扫描作者仓库”，核对一仓库一张卡片、图标和 Markdown。
7. 在干净目录测试安装、执行、版本切换和卸载。

已有示例：`gd-dd/3dmaxScript/.lxtool/`，显示名“Max 工具集”。原六个脚本作为一个工具的内部功能；原脚本业务 UI 没有改写。旧协议脚本目录保留但 v2 不再作为六个商店工具导入。

工具图标属于工具，由 manifest.icon 定义；工具架品牌图仅用于工具架自身。客户端保留 repository ID 作为身份，仓库改名复用现有目录；旧 repo-ID 目录仍可读取，下次安装时整体迁入可读目录。
