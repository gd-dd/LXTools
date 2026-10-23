"""Declarative, local tool packages. Tool sources never belong to the shelf repo."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt
from panel_spec import panel_for, ACTION_LABELS
from compatibility import host_version, compatibility_state, LABELS
from tool_source import fetch_packages
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QLineEdit, QFileDialog, QStackedWidget, QComboBox, QCheckBox, QMessageBox, QScrollArea)


class PullJob(QThread):
    result = Signal(str)
    def __init__(self, root, version, unverified):
        super().__init__()
        self.args = root, version, unverified
    def run(self):
        try:
            names = fetch_packages('gd-dd/3dmaxScript', *self.args)
            self.result.emit(f'已拉取或核对 {len(names)} 个工具版本')
        except Exception as error:
            self.result.emit('拉取失败：' + str(error))


def discover_tools(root):
    tools, errors = [], []
    root = Path(root).resolve()
    for manifest_path in sorted(root.rglob('tool.json')):
        if any(p.startswith(('.download-', '.removed-')) for p in manifest_path.parts):
            continue
        try:
            data = json.loads(manifest_path.read_text('utf-8'))
            if data.get('schemaVersion') != 1 or data.get('host') != '3dsmax':
                raise ValueError('不支持的格式或宿主')
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', data.get('id', '')):
                raise ValueError('工具 ID 无效')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', data.get('version', '')) or data['version'].endswith('.'):
                raise ValueError('工具版本无效')
            package = manifest_path.parent.resolve()
            entry = (package / data['entry']).resolve()
            if not package.is_relative_to(root) or not entry.is_relative_to(package) or entry.suffix.lower() != '.ms' or not entry.is_file():
                raise ValueError('入口路径无效或超出工具目录')
            if hashlib.sha256(entry.read_bytes()).hexdigest() != data.get('sha256'):
                raise ValueError('脚本已修改，需核对并更新 manifest 中的 SHA-256')
            compatibility_state(data.get('compatibility'), '2026.3')
            panel_for(data)
            if any((t['id'], package_key(t)) == (data['id'], package_key(data)) for t in tools):
                continue
            data.update(root=package, entry_path=entry)
            tools.append(data)
        except Exception as error:
            errors.append(f'{manifest_path.parent.name}：{error}')
    return tools, errors


def package_key(tool):
    return tool['version'] + '@' + tool.get('compatibility', {}).get('range', 'unverified')


def launch_arguments(executable, tool=None):
    path = Path(executable)
    if not path.is_file() or path.name.lower() != '3dsmax.exe':
        raise ValueError('请配置实际安装的 3dsmax.exe')
    args = [str(path)]
    if tool:
        args.extend(['-U', 'MAXScript', str(tool['entry_path'])])
    return args


def install_script(tool, scripts_directory):
    parent = Path(scripts_directory)
    if not parent.is_dir():
        raise ValueError('请选择 3ds Max 用户脚本目录')
    target = parent / 'LXTool' / tool['id'] / tool['version']
    if target.exists():
        if (target / tool['entry']).read_bytes() != tool['entry_path'].read_bytes():
            raise ValueError('目标版本已存在且内容不同，未覆盖')
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + '.installing')
    if staging.exists():
        raise ValueError('存在未完成安装目录，请先检查：' + str(staging))
    try:
        shutil.copytree(tool['root'], staging)
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return target


class ToolWorkspace(QWidget):
    def __init__(self, tools_root, config_root, managed=False):
        super().__init__()
        self.managed = managed
        self.tools_root = Path(tools_root)
        self.tools_root.mkdir(parents=True, exist_ok=True)
        self.config_file = Path(config_root) / 'hosts.json'
        self.config = json.loads(self.config_file.read_text('utf-8')) if self.config_file.exists() else {}
        self.pull_job = None
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel('我的工具 · 面板由工具定义'))
        row = QHBoxLayout()
        self.executable = QLineEdit(self.config.get('3dsmax', ''))
        self.executable.setPlaceholderText('配置 3dsmax.exe 后可启动软件或打开插件 UI')
        row.addWidget(self.executable, 1)
        choose = QPushButton('选择 3ds Max')
        choose.clicked.connect(self.choose_host)
        row.addWidget(choose)
        reload_button = QPushButton('刷新本地工具')
        reload_button.clicked.connect(self.reload)
        row.addWidget(reload_button)
        outer.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('目标 Max 版本'))
        self.host_version = QLineEdit(self.config.get('hostVersion', '2026.3'))
        self.host_version.editingFinished.connect(lambda: self.run_action(self.change_host_version))
        row.addWidget(self.host_version)
        self.only_compatible = QCheckBox('仅显示范围匹配版本')
        self.only_compatible.toggled.connect(self.reload)
        row.addWidget(self.only_compatible)
        self.allow_unverified = QCheckBox('拉取待验证版本')
        row.addWidget(self.allow_unverified)
        self.pull = QPushButton('拉取 Max 工具')
        self.pull.clicked.connect(lambda: self.run_action(self.pull_tools))
        row.addWidget(self.pull)
        outer.addLayout(row)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumWidth(300)
        self.pages = QStackedWidget()
        self.list.currentRowChanged.connect(self.pages.setCurrentIndex)
        row.addWidget(self.list)
        row.addWidget(self.pages, 1)
        outer.addLayout(row, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        outer.addWidget(QLabel('本地工具目录：' + str(self.tools_root)))
        self.reload()
        if managed:
            # The application shell owns discovery and settings; only embed the author panel.
            for child in self.findChildren(QWidget):
                if child.parent() is self and child not in (self.pages, self.status):
                    child.hide()
            self.list.hide()

    def save_config(self):
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.config_file.with_suffix('.tmp')
        temp.write_text(json.dumps(self.config, ensure_ascii=False), 'utf-8')
        os.replace(temp, self.config_file)

    def change_host_version(self):
        host_version(self.host_version.text())
        self.config['hostVersion'] = self.host_version.text()
        self.save_config()
        self.reload()

    def pull_tools(self):
        host_version(self.host_version.text())
        if self.pull_job:
            return
        self.pull.setEnabled(False)
        self.status.setText('正在拉取匹配的软件版本…')
        self.pull_job = PullJob(self.tools_root, self.host_version.text(), self.allow_unverified.isChecked())
        self.pull_job.result.connect(self.pull_result)
        self.pull_job.finished.connect(self.pull_finished)
        self.pull_job.start()

    def pull_result(self, message):
        self.reload()
        self.status.setText(message)

    def pull_finished(self):
        self.pull_job.deleteLater()
        self.pull_job = None
        self.pull.setEnabled(True)

    def choose_version(self, identity, version):
        self.config.setdefault('selectedVersions', {}).setdefault(self.host_version.text(), {})[identity] = version
        self.save_config()
        self.reload()

    def check_compatibility(self, tool):
        state = compatibility_state(tool.get('compatibility'), self.host_version.text())
        if state == 'incompatible':
            raise ValueError('工具不支持目标软件版本，请切换工具版本')
        if state in ('unverified', 'declared'):
            return QMessageBox.question(self, '兼容性尚未实测', LABELS[state] + '。仍要继续进行测试？') == QMessageBox.StandardButton.Yes
        return True

    def choose_host(self):
        filename, _ = QFileDialog.getOpenFileName(self, '选择 3ds Max', '', '3ds Max (3dsmax.exe)')
        if filename:
            self.executable.setText(filename)
            self.config['3dsmax'] = filename
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps(self.config, ensure_ascii=False), 'utf-8')

    def run_action(self, action):
        try:
            result = action()
            self.status.setText(str(result or '操作完成'))
        except Exception as error:
            self.status.setText(str(error))

    def launch(self, tool=None):
        if tool and not self.check_compatibility(tool):
            return '已取消'
        subprocess.Popen(launch_arguments(self.executable.text(), tool), shell=False)
        return '已请求启动 3ds Max' + (' 并加载工具界面；请在软件内确认。' if tool else '。')

    def install(self, tool):
        if not self.check_compatibility(tool):
            return '已取消'
        directory = QFileDialog.getExistingDirectory(self, '选择 3ds Max 用户 scripts 目录')
        if directory:
            target = install_script(tool, directory)
            return '脚本已安装到 ' + str(target) + '；可通过 Max 的“运行脚本”调用。'
        return '已取消安装'

    def dispatch_panel_action(self, action, tool):
        if action == 'launchHost':
            return self.launch()
        if action == 'installPlugin':
            return self.install(tool)
        if action == 'openPluginUI':
            return self.launch(tool)
        if action == 'openFolder':
            return os.startfile(str(tool['root']))
        raise ValueError('不支持的面板操作')

    def reload(self):
        selected_id = self.list.currentItem().data(256) if self.list.currentItem() else None
        self.list.clear()
        while self.pages.count():
            widget = self.pages.widget(0)
            self.pages.removeWidget(widget)
            widget.deleteLater()
        tools, errors = discover_tools(self.tools_root)
        try:
            host_version(self.host_version.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        groups = {}
        for tool in tools:
            state = compatibility_state(tool.get('compatibility'), self.host_version.text())
            if self.only_compatible.isChecked() and state in ('incompatible', 'unverified'):
                continue
            groups.setdefault(tool['id'], []).append(tool)
        for identity, versions in groups.items():
            selection = self.config.get('selectedVersions', {}).get(self.host_version.text(), {}).get(identity)
            tool = next((t for t in versions if package_key(t) == selection), versions[0])
            item = QListWidgetItem(tool['name'])
            item.setData(256, identity)
            self.list.addItem(item)
            panel = QWidget()
            layout = QVBoxLayout(panel)
            title = QLabel(tool['name'])
            title.setStyleSheet('font-size:25px;font-weight:700;color:#a9c5ff')
            layout.addWidget(title)
            title.setVisible(not self.managed)
            description = QLabel(tool['description'])
            description.setWordWrap(True)
            layout.addWidget(description)
            description.setVisible(not self.managed)
            layout.addWidget(QLabel('3ds Max 脚本  ·  版本 ' + tool['version']))
            selector = QComboBox()
            for version in versions:
                compatibility = version.get('compatibility', {})
                selector.addItem(version['version'] + '  |  ' + compatibility.get('range', 'unverified'), package_key(version))
            selector.setCurrentIndex(versions.index(tool))
            selector.currentIndexChanged.connect(lambda index, control=selector, key=identity: self.choose_version(key, control.itemData(index)))
            layout.addWidget(selector)
            selector.setVisible(not self.managed)
            compatibility = tool.get('compatibility', {})
            state = compatibility_state(compatibility, self.host_version.text())
            layout.addWidget(QLabel('兼容范围：' + compatibility.get('range', '未声明').replace('unverified', '待验证') + '  ·  ' + LABELS[state]))
            definition = panel_for(tool)
            if definition['type'] == 'none':
                label = QLabel('此工具不提供自定义面板。可在宿主软件中使用。')
                layout.addWidget(label)
            else:
                content = QWidget()
                content_layout = QVBoxLayout(content)
                if definition.get('title'):
                    heading = QLabel(definition['title'])
                    heading.setTextFormat(Qt.TextFormat.PlainText)
                    heading.setStyleSheet('font-size:20px;font-weight:600;color:' + definition.get('accent', '#a9c5ff'))
                    content_layout.addWidget(heading)
                for section in definition['sections']:
                    for key in ('title', 'text'):
                        if key in section:
                            label = QLabel(section[key])
                            label.setTextFormat(Qt.TextFormat.PlainText)
                            label.setWordWrap(True)
                            if key == 'title':
                                label.setStyleSheet('font-weight:600')
                            content_layout.addWidget(label)
                    for action in section.get('actions', []):
                        button = QPushButton(action.get('label', ACTION_LABELS[action['action']]))
                        button.clicked.connect(lambda checked=False, a=action['action'], t=tool:
                            self.run_action(lambda: self.dispatch_panel_action(a, t)))
                        content_layout.addWidget(button)
                content_layout.addStretch()
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setWidget(content)
                layout.addWidget(scroll, 1)
            layout.addStretch()
            self.pages.addWidget(panel)
        if self.list.count():
            self.list.setCurrentRow(next((i for i in range(self.list.count()) if self.list.item(i).data(256) == selected_id), 0))
        self.status.setText('\n'.join(errors) if errors else ('' if self.managed else f'已加载 {len(tools)} 个工具版本'))

