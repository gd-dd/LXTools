> 历史文档：0.4 起以 [LX 仓库规范 v2](../lx-tool-v2.md) 为准。一仓库一工具，自动扫描，工具声明运行环境。

# 商店目录与版本发布

## 作者负责的目录

`gd-dd/LXTools` 的 `catalog/store.json` 是唯一作者入口。客户端内置一份快照并自动更新缓存。用户不能在界面添加仓库、导入工具源或修改目录。文件系统并不是 DRM 边界，手工修改安装文件不属于受支持的用户流程。

```json
{
  "schemaVersion": 1,
  "sources": ["gd-dd/3dmaxScript"],
  "packages": [{
    "id": "example", "name": "示例", "description": "用途说明",
    "host": "3dsmax", "version": "1.0.0",
    "repository": "gd-dd/3dmaxScript",
    "manifest": "releases/unverified/1.0.0/example/tool.json",
    "compatibility": {"range":"unverified","testedVersions":[]},
    "category": "动画", "notes": "更新说明", "publishedAt": "2026-10-24"
  }]
}
```

示例不是真实发行。sources 控制可接入的仓库，packages 提供首次离线启动时的商店快照。刷新时读取所有作者来源的 tools-index.json，再从固定提交读取各个 tool.json，生成完整版本列表。新工具加入已批准来源的索引后即可出现；新来源需作者修改 sources。

目录同步整体成功后才替换缓存；失败时继续使用原目录。缓存和目录只用于发现，安装时重新校验包内摘要。未在作者目录出现的本地工具不会展示在普通客户端。

## 释出版本

每次发布保留旧版本路径和旧索引条目，新增一个 manifest 条目。工具的 tool.json 可增加：

- `category`：动画、建模、导入或实用工具。
- `releaseNotes`：该版本更新说明。
- `publishedAt`：实际发布日期字符串，推荐 YYYY-MM-DD。

版本列表显示索引全部条目及本地保留版本。版本号优先按语义版本排序，旧提交号版本使用日期/字符串顺序；新工具建议统一语义版本号。当前旧脚本没有发行日期，显示“未提供”。

“安装最新版本”选择排序最新条目；若该条目不兼容，安装按钮禁用，可在版本页选择支持目标软件的旧版。未知兼容性和声明但未实测的版本需用户明确确认测试。

## 工具架自身更新

在 gd-dd/LXTools 创建非草稿、非预发布的 GitHub Release，标签如 v0.3.1，附带干净构建的 `LXTool-windows-x64.zip`。ZIP 根目录必须是 LXTool，其中有 LXTool.exe 和 _internal。必须提供 GitHub 资源的 SHA-256 digest。

客户端选择高于当前版本的最新稳定版，下载并校验，用户确认后从下载目录运行更新帮助进程，等待旧进程退出，备份旧程序文件，再替换并重启。工具目录和用户配置保留。覆盖失败时尝试恢复旧文件，结果写入 `%LOCALAPPDATA%/LXTool/update-result.txt`。

自动构建产生 artifact；发布 Release 仍由作者执行。没有新的 Release 时，客户端显示“未发现新的稳定发行版”。不要为验证界面伪造公开发行版。

## 当前边界

Unity/其他宿主需要增加适配器后才可发布；不要套用 Max 安装动作。GitHub OAuth 尚未配置，私有源登录访问未接通。大规模目录的分页/增量同步、签名发布及多软件宿主后续扩展。
