# 本地工具与面板

开发环境工具目录是项目根目录的 tools；打包环境为 LXTool.exe 同级 tools。目录被 Git 忽略，不属于工具架源码或公共分发包。打包流程从干净构建目录生成 ZIP，不把用户本地工具带进工具架发行包，也不清空已有 tools。

每个工具独立目录包含 tool.json、入口脚本和资源文件。schemaVersion 为 1，必需字段：id、name、description、host、entry、version、sha256。当前 host 支持 3dsmax，入口必须是目录内的 .ms。source 记录 repository、commit、path。

面板由工具架按描述渲染统一标题、说明、版本、宿主操作和目录入口。业务脚本保留在工具目录，加载面板不会执行脚本。未知类型、校验不符或路径越界会拒绝加载并展示错误。

本轮接入 gd-dd/3dmaxScript 的 6 个实际工具，固定提交 131f754d2ee5abc9e168dbc4e7646ff134cd5e28，排除模板。用户已确认保留插件原界面，只统一工具架面板。

启动软件使用配置的 3dsmax.exe。启动并打开工具使用 Autodesk 支持的 `-U MAXScript <入口脚本>`，这是新进程启动加载，不是向现有实例发送命令。安装操作把脚本及资源复制到用户选择的 scripts/LXTool/id/version；不会改写其他插件或场景。

已打开实例的桥接、Max 版本兼容性和软件内实际执行，待提供可运行的 Max 后实现和验证。当前没有 Unity 插件样本，不为普通游戏工程伪造插件安装按钮。

## 软件版本与工具版本

仓库使用 releases/<兼容范围>/<工具版本>/<工具ID>/，例如 releases/2024.1~2026.3/1.0.0/animation-bake/。此路径仅为格式示例，不代表现有脚本已兼容该范围。未测试包使用 unverified。tools-index.json 提供各包 manifest 路径及 compatibility 信息；manifest 的 compatibility.range 和 testedVersions 分别记录声明范围与实际测过的具体版本。

软件范围两端均包含，使用数字元组比较，2024.10 大于 2024.2。目标版本范围外禁止安装和带脚本启动；未知范围或范围内但未经实测时需要明确选择测试。客户端可过滤匹配范围，勾选待验证后拉取当前六个脚本。下载绑定到单个 Git commit，逐文件核对 SHA-256，同版本内容不同不覆盖。版本选择按目标软件版本分别保存。

3ds Max 2026.3 的实际测试由用户后续进行，当前 testedVersions 为空。发布新兼容范围时同步更新目录、manifest 和 tools-index.json，保留已有版本。

面板内容现支持由工具自行声明，开发准则见 [工具开发规范](tool-authoring.md)。旧包继续使用兼容面板；新包显式设置 panel。

