# LXTools 0.0.6：按需检查与便携配置

启动先渲染本地目录与已安装工具。默认每6小时检查一次工具架最新版本，仅提示，不下载、不切换工具；工具目录通过“刷新工具商店”手动获取作者静态索引。设置中可选择“仅手动检查”，之后启动不发送更新或目录网络请求。

工具架更新分成“检查工具架更新”“下载并校验更新”“确认应用”。工具下载/版本切换仍由用户显式操作。未实现二进制差分下载，未增加后台常驻服务。

EXE旁 portable.json 默认内容为 {"profile":"data"}。本地用户可设置 {"profilePath":"E:/project/LXTools/runtime/user-profile"}。profilePath优先，必须绝对路径且不能是盘根/程序根；相对profile仅允许程序目录内子目录。每次普通双击启动都读取标记。更新保留已有标记和tools、data，不覆盖本地绝对路径设置。

便携及源码开发模式在 QApplication 创建前设置进程环境：LOCALAPPDATA=<profile>/local、APPDATA=<profile>/roaming、TEMP/TMP=<profile>/temp、USERPROFILE=<profile>/user，并创建 user/Desktop、user/Documents、user/Downloads，避免首次文件夹选择时默认目录不存在。每次正常启动重新应用，仅影响该进程及子进程，不修改系统环境或注册表，不覆盖已有目录文件。账户文件和工具架配置直接位于profile根。Windows 已注册的 Known Folders、工具自定义硬编码路径不保证跟随环境变量，不自动迁移用户资产。不会自动读取或复制旧token；迁移非敏感配置由本机负责人显式执行。

验收命令：LXTool.exe --verify-runtime <E盘隔离验收目录>。此模式只显示离屏界面，在指定目录写报告/环境，加载该目录tools下的已校验工具包，不启动宿主。报告区分冻结加载与实际Max业务/用户窗口验收。
