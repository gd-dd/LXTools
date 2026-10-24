# 完全自定义面板接入约定（native / API 1）

状态：已在本地 LXTool 0.5.0 实现并完成正式 EXE 示例加载验证；尚未发布工具架远端发行版。依赖本接口的工具应注明最低客户端版本 0.5.0。

## 给工具开发对话的结论

工具架负责商店、安装、版本切换、卸载和外层导航；面板内容区全部交给工具。复杂工具不必套用静态 sections 或 session 列表模板。工具可自行实现任意 Qt 控件、布局、绘制、动画、拖拽、表格、内部页面和后台通信。工具架不加入 Max、Unity 等业务分支。

“完整自定义”指内容区和交互由工具所有，并不意味着可以修改工具架的全局主题、商店或其他工具。原生模式运行工具 Python 代码，不是沙箱；文件摘要用于检查完整性，不是安全认证。发现、下载、查看 Markdown 不执行面板代码，用户从“我的工具”打开后才导入。

## 声明与入口

.lxtool/panel.json：

```json
{"type":"native","apiVersion":1,"entry":"ui/panel.py"}
```

manifest 继续使用 schemaVersion 2；panel.json、所有 UI Python 文件、图片、辅助进程都列入 files 并计算 SHA256。entry 为包内 .py 文件，不允许路径越界。未知 API 版本必须拒绝加载并提示更新客户端。旧 declarative / none 保持兼容。

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton

def create_panel(context, parent):
    return Panel(context, parent)

class Panel(QWidget):
    def __init__(self, context, parent):
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        button = QPushButton('由工具定义的按钮', self)
        layout.addWidget(button)
        button.clicked.connect(lambda: button.setText('交互也由工具定义'))

    def shutdown(self):
        # 必须实现，可重复调用；停止自己创建的定时器、任务和连接。
        pass
```

工厂在 GUI 线程调用，必须快速返回一个属于 parent 的 QWidget，并实现 shutdown()。工具架不额外插入标题、路径设置、版本设置或外部滚动区；工具自己决定是否需要这些内容。框架保留面板外的返回和夹子导航。

## context API 1

- api_version：1。
- identity / version：稳定仓库身份与工具版本。
- package_root：只读工具版本目录 Path。不要向版本目录写缓存、设置或字节码。
- data_root：该工具独占的持久数据目录 Path，跨版本保留，回退时自行处理配置兼容；卸载工具包不删除它。
- resource(relative_path)：返回 files 中已声明且摘要校验正确的资源绝对路径。
- load_settings() / save_settings(dict)：读写该工具的原生面板配置，JSON 对象、原子落盘，不混用宿主应用设置。

包内相对导入使用 `from .helper import ...`，入口同目录及其子目录可组织 Python 包。不要依赖 sys.path 修改或直接 import 工具架内部模块。基础运行时为 Windows x64 / Python 3.12 / PySide6 6.8.3，QtCore、QtGui、QtWidgets 是当前嵌入 ABI 的基础保证；标准库受冻结打包收集范围影响，必须在正式 EXE 验证所用模块。不保证 QtWebEngine、第三方 Python 模块或任意二进制扩展。其他依赖建议编译为工具自带独立后台 EXE，通过 QProcess/本地 IPC 通信。

## 生命周期与失败处理

打开面板前复核安装包全部摘要；每次打开创建新实例。离开、换工具、关闭客户端时调用 shutdown，然后释放 QWidget 和导入模块；不能把关闭面板解释成关闭 Max 或杀掉用户应用。外部宿主的所有权、连接恢复由工具自行实现。

加载失败显示错误并保留工具架导航；Qt 回调、工作线程和业务进程错误由工具捕获、显示并恢复。原生代码与工具架同进程，无法承诺隔离崩溃或阻止不遵守协议的代码。长操作不得阻塞 GUI；通过线程/异步 QProcess 加信号传回 UI。不要创建第二个 QApplication、启动第二个 event loop、修改全局 stylesheet、退出工具架进程、覆盖 sys.excepthook 或打开独立控制台替代嵌入面板。

## 3dMax 工具集应如何实现

按该对话用户最新需求：完整面板内自行排版“打开 Max → 连接状态和实例选择 → 工具操作”；只管理本工具启动的 Max。用户自行启动的 Max 无需扫描。实例身份、命令路由、结果回执都属于 Max 工具后台；工具架不认识 Max PID、连接脚本或功能 ID。插件在 Max 内的原有界面可以保留，不另弹一个工具集控制台。

已有 session 声明式扩展可继续兼容，但它只是可选模板，不应成为所有工具的布局上限。当前多实例桥接后台可由工具自己的 QWidget 通过 QProcess 复用。

## 发布验收

1. 完整清单、资源摘要、native API 校验通过。
2. 用正式打包 EXE 打开面板；验证自定义布局、交互、图片、相对导入。
3. 离开并重开、切换工具版本、退出工具架，验证线程/定时器/连接释放且宿主不被误关。
4. 缺依赖、损坏资源、后台退出、慢请求应在面板内清楚显示。
5. 配置跨版本兼容与回退测试；UI 或协议改变也必须发布新版本。

不得只通过格式校验便宣称 Max 多实例真实功能测试成功。

可运行完整模板：`examples/native-panel/`，包含独立图标、清单、两页 UI、动态表格、相对导入和配置持久化。Skill 内也附有相同模板。

验证记录：38 项测试通过（包含加载失败、摘要篡改、模块/版本隔离、配置持久化和离开清理）；正式 PyInstaller EXE 在独立测试目录成功加载示例并操作动态表格。示例无 Max 业务，不能代替 Max 工具自身验收。
