# 首次发布 LXTools（v0.0.1）

## 本次交付文件

都在项目的 dist 目录：

- LXTools-Setup-0.0.1-windows-x64.exe：给普通 Windows 用户双击安装，中文向导，不需要预装 Python。
- LXTool-windows-x64.zip：免安装版，也是客户端自更新指定读取的文件名，不能改名。
- SHA256SUMS.txt：上述两个文件的校验和，方便核对下载完整性。

安装包本身安装 0.0.1，不会联网拉取最新版。以后在“设置与更新”点击检查更新，下载并校验更新包，用户确认后重启替换程序。草稿、预览版和不高于当前版本的发行不会被更新器采用。

## 先完成源码对应

目前远端 main 仍是旧代码，不能直接给它打 v0.0.1 正式标签。先把经过本轮构建的源码同步到 main，再检查 GitHub Actions 的 Windows build 成功。同步不能包含 .venv、build、dist、runtime、tools 或个人配置。

本地 build-installer.ps1 会构建并生成安装程序；Inno Setup 编译器需安装，或传入 -Compiler 指定 ISCC.exe。build.ps1 只构建客户端 ZIP，适合普通开发验证。

## 编辑已保存的草稿

1. 打开 https://github.com/gd-dd/LXTools/releases，进入 LXTools v0.0.1 草稿，点击编辑。
2. 标签保持 v0.0.1，Target 保持已同步并验证的 main。
3. 标题 LXTools v0.0.1。保留已填的功能说明，增加下面的“下载说明”。
4. 在正文下方 Attach binaries 区域上传上面三个文件，不是上传到正文附件按钮。
5. 等所有上传进度结束，核对安装 EXE、固定名称 ZIP 和 SHA256SUMS.txt 都在附件列表。
6. Release label 选 None（正式稳定版本），不要选 Pre-release，否则当前客户端不会更新到它。
7. 确认版本、源码和附件一致后，由作者亲手点击 Publish release。
8. 发布后打开公开页面重新下载 EXE / ZIP，校验 SHA256；安装 EXE 并启动客户端。

可以追加到 Release 正文：

```markdown
## 下载说明
- 普通用户：下载 LXTools-Setup-0.0.1-windows-x64.exe，双击安装。
- 免安装使用：下载 LXTool-windows-x64.zip，完整解压后运行 LXTool.exe，不要单独移动 EXE。
- 后续更新：在工具架“设置与更新”中检查新版并确认安装。
- 各个工具按需下载，更新保留工具与个人配置。
- 卸载工具架会保留已下载工具和个人配置。
```

## 本地验证与尚未验证

本次安装、重复安装、卸载、卸载注册信息及工具数据保留已在独立目录实测。实际客户端启动并读取商店正常；本地更新器替换程序文件后仍保留 tools、配置和卸载器，卸载可清理新增运行库文件。

42 项自动测试通过（含 Release 分页、草稿过滤、附件摘要、ZIP 路径和旧缓存隔离）。安装包与 ZIP 均已生成。尚未公开发布，因此不能把真实 GitHub 新旧版本下载升级写成已通过；首版 0.0.1 不会升级到自己，需在以后发布更高版本时再做端到端升级验证。

编译器来源及签名经过验证，但本项目安装包当前没有作者代码签名证书，不应标注为已签名。

技术参考：Inno Setup https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm 与 https://jrsoftware.org/ishelp/topic_filessection.htm 。

本次首次版本编号从原 0.5.0 更正为 0.0.1。旧客户端不会自动降级，请手动重装；后续版本递增。工具同样仅通过 GitHub Releases 发布。
