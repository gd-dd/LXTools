# LXTool 工具开发规范 v1

工具架负责发现、下载、版本管理和统一样式；工具作者定义面板内容与顺序。插件在 Max 中的原始 UI 不受影响。当前可运行适配器仅支持 3ds Max 的 `.ms` 脚本；Unity 和独立程序尚未实现，不应冒用 Max 格式。

## 目录与发布

工具源代码和资源放在工具自己的仓库，不提交到 LXTools 仓库。

```text
工具仓库/
  tools-index.json
  releases/
    unverified/1.0.0/my-max-tool/
      tool.json
      main.ms
      resource.jpg
```

验证后可使用 `releases/2024.1~2026.3/1.0.0/my-max-tool/`，范围含两端。这个范围只是示例，不表示现有工具通过验证。工具版本和宿主版本互相独立。已发布版本不得改内容，修改脚本、资源或面板都发布新的工具版本。

客户端下载到 EXE 同级的 `tools/<id>/<兼容范围>/<工具版本>/`，按宿主版本记住选用的工具版本。

## tool.json 字段

| 字段 | 约定 |
| --- | --- |
| schemaVersion | 固定为整数 1 |
| id | 稳定标识，1–64 个小写字母、数字、短横线，首字符字母或数字 |
| name / description | 展示名称和用途说明 |
| host | 当前固定为 `3dsmax` |
| entry | 包内 `.ms` 入口文件名 |
| version | 1–64 个字母、数字、点、下划线或短横线，首字符字母或数字，不能以点结尾；推荐 `1.0.0` |
| sha256 | 入口脚本文件的 SHA-256 小写十六进制摘要 |
| files | 所有待下载文件名到 SHA-256 的映射，包含入口和资源，不包含 tool.json 自己 |
| compatibility | `range` 为 `unverified` 或版本范围；`testedVersions` 为实际验证过的软件版本数组 |
| source | 可选溯源对象：repository、commit、path |
| panel | 新工具必须显式声明，见下文；旧包省略时使用兼容面板 |

当前下载协议只支持同目录文件名，不允许子目录、绝对路径或 `..`。资源统一放在入口旁边，脚本自行用自身文件路径定位资源。下载固定到单次提交并逐文件校验摘要。

## 工具自定义面板

完整清单示例：[有面板](examples/tool-with-panel.json)、[无面板](examples/tool-without-panel.json)。示例中的摘要是占位值，发布前必须替换，示例不包含业务脚本。

```json
{
  "type": "declarative",
  "title": "动画工具",
  "sections": [
    {"title": "准备", "text": "选择需要处理的对象。"},
    {"actions": [{"action": "openPluginUI", "label": "启动 Max 并打开动画工具"}]}
  ]
}
```

以上对象放进 tool.json 的 panel 字段。分组和按钮按数组顺序显示；工具作者决定内容，客户端决定颜色、字体、间距和滚动方式。工具名称、版本选择和兼容信息由工具架管理，不属于自定义面板。

- `type` 必须是 `declarative` 或 `none`。
- `title` 可选，1–120 字符。
- `sections` 必填，1–20 个分组。分组支持 `title`、`text`、`actions`，不可为空。
- 分组 `title` 最多 120 字符，`text` 最多 2000 字符，均为非空纯文本，不解析 HTML。
- 每组最多 10 个按钮，按钮只允许 `action` 和可选 `label`；label 为 1–120 字符的非空文本。
- 未知字段、未知操作、超限内容会拒绝加载该工具，并显示错误，不影响其他工具。

| action | 实际行为 |
| --- | --- |
| launchHost | 启动配置的 3ds Max |
| installPlugin | 选择用户 scripts 目录并复制工具到 LXTool/id/version；不是自动注册系统插件 |
| openPluginUI | 新开 Max 实例，通过 `-U MAXScript` 执行 entry；是否显示 UI 由脚本决定，不能调用已经打开的 Max 实例 |
| openFolder | 打开本地工具目录 |

按钮不允许自行填写命令、程序路径、网络 URL 或 Python/JavaScript 代码。安装和执行入口沿用宿主配置与兼容性检查。查看面板不会执行脚本。v1 不提供输入框、参数传递、动态状态或自定义 HTML；需要这些能力时升级协议和宿主适配器，不在文本中嵌入命令。

## 无面板工具

```json
{"type": "none"}
```

无面板模式不能带 title 或 sections。工具仍出现在“我的工具”，保留工具架的名称、说明、版本及兼容信息，但没有工具自定义内容和操作按钮，选中也不会自动运行。适合仅在宿主中使用的工具；若需要一键安装或启动，请使用声明式面板放置相应按钮。

## 商店索引和发布检查

仓库根目录 tools-index.json：

```json
{"schemaVersion":1,"packages":[{"manifest":"releases/unverified/1.0.0/my-max-tool/tool.json","compatibility":{"range":"unverified","testedVersions":[]}}]}
```

索引的 compatibility 必须与 manifest 一致，目录范围、版本、ID 必须与 manifest 一致。

1. 编写脚本与面板，选择稳定 ID 和新版本号。
2. 计算所有业务文件摘要，填写 files 和入口 sha256。
3. 先放入本地 tools 目录，刷新并检查面板和错误信息。
4. 在对应 Max 版本实测插件；仅记录真实测试结果。
5. 更新兼容目录、manifest、索引，提交到工具仓库。
6. 在干净工具目录验证下载、切换、安装和脚本启动。

现有六个脚本保留旧格式兼容面板；没有把未实测的 2026.3 写成已支持。

## 商店展示与艺术风格补充

工具可在顶层提供 category、releaseNotes、publishedAt，供商店分类与版本页使用。可选 panel.accent 为 `#RRGGBB` 强调色（仅 declarative 模式），当前应用于面板自定义标题。作者自由安排分组、说明与按钮顺序；工具架保留可读性、滚动和系统级管理操作的一致性。不接受任意 CSS/代码。

工具来源由作者的 catalog/store.json 维护，用户不能添加源。索引发布规则见 [商店与发布](store-publishing.md)。

