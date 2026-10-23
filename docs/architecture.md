# LXTool 0.3 架构

Windows 原生 PySide6 UI，PyInstaller onedir 分发。

- desktop.py：商店 / 工具库 / 夹子 / 详情 / 版本 / 设置；后台线程处理网络与下载。
- library.py：作者固定目录、离线快照缓存、用户夹子、工具版本卸载。
- tool_source.py：固定提交下载单个或多个声明式工具包，逐文件 SHA-256 校验和原子入库。
- panel_spec.py / tool_panels.py：工具自定义面板协议、验证与宿主动作；none 支持无面板。
- compatibility.py：宿主数字版本比较、范围及实测状态。
- updater.py：标准 Release 下载准备、等待旧客户端退出、程序备份替换与重启。
- core.py：归档校验与 Release 下载基础设施；旧原型仓库管理接口不再暴露给用户。

作者维护的 catalog/store.json 决定来源。仓库索引必须保留每个释出版本，客户端自动构建版本列表，不允许普通用户添加源。每次下载绑定到目录同步时获取的提交，防止中途源变化。

目录快照内置于 _internal/catalog，运行缓存保存在用户 LocalAppData。工具业务文件位于程序同级 tools，不进入工具架源码或分发 ZIP。用户夹子只存工具 ID 到夹子 ID 的映射，不移动工具包物理位置。

面板只允许声明式动作，不加载第三方 UI 可执行代码。Max 脚本仅在用户点击入口动作并通过兼容性检查后执行。宿主自身插件 UI 保持不变。

账户登录未启用；注册 OAuth / 选择最终授权方式后再接入，不把私人令牌打进客户端。

