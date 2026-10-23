import json
import os
import sys
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QLockFile, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QFileDialog, QSplitter, QProgressBar, QTabWidget)
from tool_panels import ToolWorkspace
from keyring.backends.Windows import WinVaultKeyring
from core import ToolStore
from packaging.version import Version, InvalidVersion

VERSION = '0.2.0'


class Job(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.result.emit(self.fn())
        except Exception as error:
            self.failed.emit(str(error) if isinstance(error, ValueError) else '操作失败，请检查网络、磁盘空间及文件占用。')


class Window(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.vault = WinVaultKeyring()
        self.job = None
        self.setWindowTitle('LXTool · 游戏制作工具架')
        self.resize(1120, 760)
        root = QWidget()
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        app_root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
        self.workspace = ToolWorkspace(app_root / 'tools', store.root)
        self.tabs.addTab(self.workspace, '工具工作区')
        self.tabs.addTab(root, '工具架配置')
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        title = QLabel('LXTool.   游戏制作工具架')
        title.setStyleSheet('font-size:26px;font-weight:700;color:#a9c5ff')
        layout.addWidget(title)
        layout.addWidget(QLabel('工具集中管理 · GitHub 分发 · 历史版本保留'))
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索仓库')
        self.search.textChanged.connect(self.refresh)
        self.category = QComboBox()
        self.category.addItems(['全部', '3ds Max', 'Unity', '通用工具'])
        self.category.currentTextChanged.connect(self.refresh)
        top.addWidget(self.search, 1)
        top.addWidget(self.category)
        layout.addLayout(top)
        actions = QHBoxLayout()
        self.buttons = []
        for label, action in [('添加仓库', self.add), ('导入目录', self.import_catalog), ('同步 GitHub 目录', self.sync_catalog), ('客户端更新', self.update_client)]:
            actions.addWidget(self.button(label, action))
        layout.addLayout(actions)
        splitter = QSplitter()
        self.tools = QListWidget()
        self.tools.currentItemChanged.connect(self.select)
        splitter.addWidget(self.tools)
        panel = QWidget()
        details = QVBoxLayout(panel)
        self.heading = QLabel('选择一个工具，或添加 GitHub 仓库开始')
        details.addWidget(self.heading)
        details.addWidget(QLabel('启用版本仅管理本地包；本版不修改 Max 或 Unity 项目。'))
        row = QHBoxLayout()
        row.addWidget(self.button('检查工具更新', self.releases))
        row.addWidget(self.button('仓库凭据', self.credentials))
        details.addLayout(row)
        details.addWidget(QLabel('远端发布版本 / ZIP 附件'))
        self.remote = QListWidget()
        details.addWidget(self.remote)
        details.addWidget(self.button('下载选中附件', self.install))
        details.addWidget(QLabel('本地版本'))
        self.local = QListWidget()
        details.addWidget(self.local)
        row = QHBoxLayout()
        for label, action in [('启用版本', self.activate), ('打开目录', self.open_package), ('卸载版本', self.uninstall)]:
            row.addWidget(self.button(label, action))
        details.addLayout(row)
        splitter.addWidget(panel)
        splitter.setSizes([300, 750])
        layout.addWidget(splitter, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel('就绪 · v' + VERSION + ' · 数据：' + str(store.root))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh()

    def button(self, label, fn):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.guard(fn))
        self.buttons.append(button)
        return button

    def guard(self, fn):
        try:
            fn()
        except Exception as error:
            self.status.setText(str(error))

    def current(self):
        item = self.tools.currentItem()
        if not item:
            raise ValueError('请先选择工具')
        return self.store.tool(item.data(256))

    def busy(self, fn, done=None):
        if self.job:
            return
        for button in self.buttons:
            button.setEnabled(False)
        self.tools.setEnabled(False)
        self.search.setEnabled(False)
        self.category.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText('正在处理，请稍候…')
        self.job = Job(fn)
        self.job.result.connect(lambda value: self.guard(lambda: self.completed(value, done)))
        self.job.failed.connect(self.status.setText)
        self.job.finished.connect(self.idle)
        self.job.start()

    def completed(self, value, done):
        self.status.setText('操作完成')
        if done:
            done(value)

    def idle(self):
        self.job.deleteLater()
        self.job = None
        for button in self.buttons:
            button.setEnabled(True)
        self.tools.setEnabled(True)
        self.search.setEnabled(True)
        self.category.setEnabled(True)
        self.progress.hide()

    def refresh(self):
        current = self.tools.currentItem().data(256) if self.tools.currentItem() else None
        self.tools.clear()
        for tool in self.store.state['tools']:
            if self.search.text().lower() not in tool['repo'].lower():
                continue
            if self.category.currentText() not in ('全部', tool['category']):
                continue
            item = QListWidgetItem(f"{tool.get('name', tool['repo'])}\n{tool['category']} · {len(tool['versions'])} 个本地版本")
            item.setData(256, tool['id'])
            self.tools.addItem(item)
            if tool['id'] == current:
                self.tools.setCurrentItem(item)

    def select(self, *_):
        self.remote.clear()
        self.local.clear()
        if not self.tools.currentItem():
            self.heading.setText('选择一个工具，或添加 GitHub 仓库开始')
            return
        tool = self.current()
        self.heading.setText(tool['repo'])
        for version in tool['versions']:
            item = QListWidgetItem(f"{'● 当前启用' if tool['active'] == version['key'] else '○'}  {version['tag']} · {version['name']}\n{'已校验远端 SHA-256' if version['verified'] else '远端未提供哈希'}")
            item.setData(256, version['key'])
            self.local.addItem(item)

    def add(self):
        repo, ok = QInputDialog.getText(self, '添加工具', 'GitHub 仓库（owner/repo）')
        if not ok:
            return
        category, ok = QInputDialog.getItem(self, '工具分类', '分类', ['3ds Max', 'Unity', '通用工具'], 0, False)
        if ok:
            self.store.add(repo, category)
            self.refresh()

    def authorize(self, tool):
        token = self.vault.get_password('LXTool', tool['repo'])
        if token:
            self.store.tokens[tool['id']] = token

    def credentials(self):
        tool = self.current()
        token, ok = QInputDialog.getText(self, '仓库凭据', '令牌存入 Windows 凭据管理器；留空清除', QLineEdit.EchoMode.Password)
        if ok:
            if token.strip():
                self.vault.set_password('LXTool', tool['repo'], token.strip())
                self.store.tokens[tool['id']] = token.strip()
            else:
                if self.vault.get_password('LXTool', tool['repo']):
                    self.vault.delete_password('LXTool', tool['repo'])
                self.store.tokens.pop(tool['id'], None)
            self.status.setText('凭据已更新')

    def releases(self):
        tool = self.current()
        self.authorize(tool)
        self.busy(lambda: self.store.releases(tool['id']), self.show_releases)

    def show_releases(self, releases):
        self.remote.clear()
        for release in releases:
            for asset in release['assets']:
                item = QListWidgetItem(f"{release['tag']} {'[预发布]' if release['prerelease'] else ''} · {asset['name']} · {asset['size']/1048576:.1f} MB")
                item.setData(256, asset['id'])
                self.remote.addItem(item)
        if not self.remote.count():
            self.status.setText('没有可下载的 ZIP Release 附件')

    def install(self):
        tool = self.current()
        if not self.remote.currentItem():
            raise ValueError('请选择远端附件')
        asset = self.remote.currentItem().data(256)
        self.busy(lambda: self.store.install(tool['id'], asset), lambda _: self.refresh())

    def local_key(self):
        if not self.local.currentItem():
            raise ValueError('请选择本地版本')
        return self.local.currentItem().data(256)

    def activate(self):
        self.store.activate(self.current()['id'], self.local_key())
        self.select()
        self.status.setText('本地启用版本已切换')

    def open_package(self):
        os.startfile(str(self.store.root / 'packages' / self.current()['id'] / self.local_key()))

    def uninstall(self):
        tool, key = self.current(), self.local_key()
        if QMessageBox.question(self, '卸载版本', '删除此工具的本地版本？当前启用版本需先切换。') == QMessageBox.StandardButton.Yes:
            self.store.uninstall(tool['id'], key)
            self.select()

    def import_catalog(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入工具目录', '', 'JSON (*.json)')
        if path:
            self.store.import_catalog(json.loads(Path(path).read_text('utf-8')))
            self.refresh()

    def sync_catalog(self):
        repo, ok = QInputDialog.getText(self, '同步目录', '目录仓库（读取 catalog/catalog.json）', text='gd-dd/LXTools')
        if not ok:
            return
        def sync():
            import base64
            import re
            if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
                raise ValueError('仓库格式应为 owner/repo')
            source = {'id': 'catalog', 'repo': repo}
            self.authorize(source)
            with self.store.request(source, f'/repos/{repo}/contents/catalog/catalog.json') as response:
                data = json.load(response)
            self.store.import_catalog(json.loads(base64.b64decode(data['content'])))
        self.busy(sync, lambda _: self.refresh())

    def update_client(self):
        def check():
            source = {'id': 'client', 'repo': 'gd-dd/LXTools'}
            self.authorize(source)
            with self.store.request(source, '/repos/gd-dd/LXTools/releases?per_page=100') as response:
                releases = [r for r in json.load(response) if not r['draft'] and not r['prerelease']]
            candidates = []
            for release in releases:
                try:
                    if Version(release['tag_name'].lstrip('v')) > Version(VERSION):
                        candidates.append(release)
                except InvalidVersion:
                    continue
            if not candidates:
                return None
            latest = max(candidates, key=lambda r: Version(r['tag_name'].lstrip('v')))
            assets = [a for a in latest['assets'] if a['name'] == 'LXTool-windows-x64.zip']
            if len(assets) != 1 or not assets[0].get('digest', '').startswith('sha256:'):
                raise ValueError('新版本缺少 LXTool-windows-x64.zip 或 SHA-256，无法自动准备更新')
            updates = ToolStore(self.store.root / 'client-updates')
            if not updates.state['tools']:
                updates.add('gd-dd/LXTools', '通用工具')
            tool = updates.state['tools'][0]
            token = self.vault.get_password('LXTool', tool['repo'])
            if token:
                updates.tokens[tool['id']] = token
            key = str(assets[0]['id'])
            if not any(v['key'] == key for v in tool['versions']):
                updates.install(tool['id'], assets[0]['id'])
            directory = updates.root / 'packages' / tool['id'] / key
            executable = directory / 'LXTool' / 'LXTool.exe'
            if not executable.is_file():
                raise ValueError('更新包缺少 LXTool/LXTool.exe')
            return latest['tag_name'], directory
        def show(releases):
            if not releases:
                self.status.setText('未发现更新的稳定版本（仓库可能尚无发布）；当前 v' + VERSION)
                return
            tag, directory = releases
            self.status.setText(f'更新 {tag} 已下载并校验。关闭当前窗口后，从已打开目录运行新版；旧版保留。')
            os.startfile(str(directory / 'LXTool'))
        self.busy(check, show)

    def closeEvent(self, event):
        if self.job or self.workspace.pull_job:
            self.status.setText('后台任务进行中，请完成后关闭')
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet('QWidget{background:#151c28;color:#e1e9f7;font:14px "Microsoft YaHei"} QPushButton,QLineEdit,QComboBox{padding:9px;background:#25334b;border:1px solid #405573;border-radius:5px} QPushButton:hover{background:#365c91} QPushButton:disabled{color:#68768c} QListWidget{background:#1c2738;border:1px solid #34435a;border-radius:6px} QListWidget::item{padding:12px} QListWidget::item:selected{background:#304f7c;color:#ffffff} QLabel{padding:4px} QProgressBar{max-height:12px}')
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LXTool'
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / 'desktop.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None, 'LXTool', '工具架已经运行，请使用现有窗口。')
        return 0
    window = Window(ToolStore(root))
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())

