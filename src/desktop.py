"""LXTool: author-curated tool store and desktop workspace."""
import os
import sys
import subprocess
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QLockFile, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QFileDialog, QProgressBar, QStackedWidget, QFrame,
    QScrollArea, QTabWidget, QTreeWidget, QTreeWidgetItem)
from packaging.version import Version, InvalidVersion
from core import ToolStore
from tool_panels import ToolWorkspace, discover_tools, package_key
from library import AuthorCatalog, Library
from tool_source import fetch_packages
from compatibility import compatibility_state, host_version, LABELS
from updater import VERSION, prepare_update, apply_update

STYLE = '''
QWidget { background:#11141b; color:#e7eaf1; font:14px "Microsoft YaHei"; }
QWidget#sidebar { background:#191d27; border-right:1px solid #282d3b; }
QFrame#hero { background:#232d46; border:1px solid #354664; border-radius:16px; }
QFrame#card { background:#1b202c; border:1px solid #303748; border-radius:12px; }
QLabel { background:transparent; border:0; }
QLabel#title { font-size:29px; font-weight:700; }
QLabel#subtitle { color:#9ba8bf; }
QLabel#badge { color:#b7caff; font-size:12px; }
QPushButton { background:#272f40; border:1px solid #3b465b; border-radius:7px; padding:9px 14px; }
QPushButton:hover { background:#35445e; border-color:#6c8fd5; }
QPushButton:disabled { color:#67738a; background:#1d2330; border-color:#2b3240; }
QPushButton#primary { background:#6485f5; color:#fff; border:0; font-weight:600; }
QPushButton#primary:hover { background:#7a98ff; }
QPushButton#primary:disabled { background:#263249; color:#8c9cba; }
QPushButton#nav { text-align:left; padding:14px; border:0; background:transparent; }
QPushButton#nav:checked { background:#2c3956; color:#cbd8ff; }
QPushButton#danger { color:#ffafaf; }
QLineEdit,QComboBox { padding:9px; border:1px solid #364158; border-radius:7px; background:#1c2230; }
QListWidget,QTreeWidget { background:#191f2b; border:1px solid #30394d; border-radius:8px; outline:0; }
QListWidget::item,QTreeWidget::item { padding:12px; }
QListWidget::item:selected,QTreeWidget::item:selected { background:#344c77; color:#fff; }
QHeaderView::section { background:#252e40; color:#aebdd6; border:0; padding:10px; }
QScrollArea { border:0; }
QTabWidget::pane { border:1px solid #30394d; border-radius:8px; }
QTabBar::tab { padding:12px 22px; background:#1a202c; color:#9eabc2; }
QTabBar::tab:selected { color:#dbe6ff; background:#2b3850; }
QProgressBar { max-height:6px; border:0; background:#222a39; }
QProgressBar::chunk { background:#6485f5; }
QScrollBar:vertical { width:10px; background:#171c26; }
QScrollBar::handle:vertical { background:#414e66; border-radius:4px; min-height:30px; }
'''


def label(text, kind=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if kind:
        widget.setObjectName(kind)
    return widget


def version_order(entry):
    try:
        return 1, Version(entry['version'])
    except InvalidVersion:
        return 0, entry.get('publishedAt', '') + entry['version']


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
            from urllib.error import HTTPError
            message = str(error)
            if isinstance(error, HTTPError):
                message = {401:'账户授权已失效', 403:'下载服务限流或权限不足，请稍后再试',
                           404:'目录或工具版本不存在，请刷新目录', 429:'下载服务繁忙，请稍后再试'}.get(error.code, '网络请求失败')
            self.failed.emit(message)


class Window(QMainWindow):
    def __init__(self, store, tools_root=None, autoload=True):
        super().__init__()
        self.store, self.job = store, None
        app_root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
        self.tools_root = Path(tools_root) if tools_root else app_root / 'tools'
        self.catalog = AuthorCatalog(store.root)
        self.library = Library(store.root, self.tools_root)
        self.current_id = None
        self.view_mode = 'store'
        self.folder_id = None
        self.pending_restart = None
        self.setWindowTitle('LXTool · 创作工具商店')
        self.resize(1280, 840)
        self.setMinimumSize(1040, 720)
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0,0,0,0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)
        sidebar = QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar); side.setContentsMargins(20,26,20,20); side.setSpacing(12)
        brand = label('LX / TOOLS'); brand.setStyleSheet('font-size:25px;font-weight:800;color:#b9cbff')
        side.addWidget(brand)
        side.addWidget(label('你的创作工具箱', 'subtitle'))
        side.addSpacing(24)
        self.nav = {}
        for key, title in [('store','发现工具'), ('library','我的工具'), ('settings','设置与更新')]:
            button = self.button(title, lambda k=key:self.navigate(k), 'nav')
            button.setCheckable(True); side.addWidget(button); self.nav[key]=button
        side.addSpacing(20)
        folder_header = QHBoxLayout(); folder_header.addWidget(label('我的夹子', 'subtitle'))
        folder_header.addWidget(self.button('+', self.create_folder)); side.addLayout(folder_header)
        self.folders = QListWidget(); self.folders.setMaximumHeight(270)
        self.folders.currentItemChanged.connect(self.folder_selected)
        side.addWidget(self.folders)
        folder_actions=QHBoxLayout()
        folder_actions.addWidget(self.button('改名', self.rename_folder))
        folder_actions.addWidget(self.button('移除', self.remove_folder))
        side.addLayout(folder_actions)
        side.addStretch()
        side.addWidget(label('作者精选 · 按需安装', 'subtitle'))
        side.addWidget(label('LXTool  ' + VERSION, 'subtitle'))
        root_layout.addWidget(sidebar)
        body=QWidget(); body_layout=QVBoxLayout(body);body_layout.setContentsMargins(28,24,28,16)
        self.pages=QStackedWidget();body_layout.addWidget(self.pages,1)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();body_layout.addWidget(self.progress)
        self.status=label('已载入作者目录。公开工具无需登录即可安装。','subtitle');body_layout.addWidget(self.status)
        root_layout.addWidget(body,1)
        self.build_browse()
        self.build_detail()
        self.build_settings()
        self.refresh_folders()
        self.navigate('store')
        if autoload and QApplication.platformName() != 'offscreen':
            QTimer.singleShot(300, self.sync_catalog)

    def button(self, text, fn, kind=None):
        button=QPushButton(text)
        if kind:button.setObjectName(kind)
        button.clicked.connect(lambda checked=False:self.guard(fn))
        return button

    def guard(self, fn):
        try:return fn()
        except Exception as error:self.status.setText(str(error))

    def build_browse(self):
        self.browse=QWidget();layout=QVBoxLayout(self.browse);layout.setContentsMargins(0,0,0,0);layout.setSpacing(18)
        row=QHBoxLayout();self.browse_title=label('发现工具','title');row.addWidget(self.browse_title,1)
        self.sync_button=self.button('刷新商店',self.sync_catalog);row.addWidget(self.sync_button);layout.addLayout(row)
        self.hero=QFrame();self.hero.setObjectName('hero');hero=QVBoxLayout(self.hero);hero.setContentsMargins(24,20,24,20)
        hero.addWidget(label('把重复工作交给工具。','title'))
        hero.addWidget(label('浏览作者持续维护的创作工具，按需安装，随时切换版本。','subtitle'))
        self.hero_count=label('','badge');hero.addWidget(self.hero_count);layout.addWidget(self.hero)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('搜索工具名称或用途…');self.search.textChanged.connect(self.render_cards)
        row.addWidget(self.search,1);self.category=QComboBox();self.category.addItems(['全部分类','动画','建模','导入','实用工具']);self.category.currentTextChanged.connect(self.render_cards);row.addWidget(self.category)
        layout.addLayout(row)
        self.summary=label('','subtitle');layout.addWidget(self.summary)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        self.card_area=QWidget();self.cards=QGridLayout(self.card_area);self.cards.setSpacing(16);self.cards.setContentsMargins(0,0,8,0)
        scroll.setWidget(self.card_area);layout.addWidget(scroll,1);self.pages.addWidget(self.browse)

    def build_detail(self):
        self.detail=QWidget();layout=QVBoxLayout(self.detail);layout.setContentsMargins(0,0,0,0);layout.setSpacing(16)
        row=QHBoxLayout();row.addWidget(self.button('‹ 返回工具列表',lambda:self.navigate(self.view_mode, self.folder_id)));row.addStretch()
        row.addWidget(label('收纳到','subtitle'));self.move_combo=QComboBox();self.move_combo.setMinimumWidth(150);self.move_combo.currentIndexChanged.connect(self.move_tool);row.addWidget(self.move_combo);layout.addLayout(row)
        self.detail_title=label('','title');layout.addWidget(self.detail_title)
        self.detail_description=label('','subtitle');layout.addWidget(self.detail_description)
        self.detail_tabs=QTabWidget();layout.addWidget(self.detail_tabs,1)
        self.overview=QWidget();overview=QVBoxLayout(self.overview);overview.setContentsMargins(24,24,24,24);overview.setSpacing(18)
        self.detail_badge=label('','badge');overview.addWidget(self.detail_badge)
        self.detail_help=label('');overview.addWidget(self.detail_help)
        self.install_button=self.button('安装工具',self.install_latest,'primary');overview.addWidget(self.install_button)
        self.panel_button=self.button('打开工具面板',self.open_panel);overview.addWidget(self.panel_button)
        overview.addWidget(label('工具和宿主插件分开管理：安装到工具架后，可从工具面板安装到 Max 或启动插件。','subtitle'))
        overview.addStretch();self.detail_tabs.addTab(self.overview,'概览')
        self.workspace=ToolWorkspace(self.tools_root,self.store.root,managed=True)
        self.detail_tabs.addTab(self.workspace,'工具面板')
        releases=QWidget();rl=QVBoxLayout(releases);rl.setContentsMargins(20,20,20,20)
        rl.addWidget(label('全部释出版本','title'));rl.addWidget(label('安装新版本不会删除旧版本。选择已安装版本即可切换或回退。','subtitle'))
        self.release_list=QTreeWidget();self.release_list.setHeaderLabels(['版本','兼容范围','本地状态','发布日期']);self.release_list.setRootIsDecorated(False);self.release_list.setColumnWidth(0,170);self.release_list.setColumnWidth(1,200);self.release_list.setColumnWidth(2,120)
        self.release_list.currentItemChanged.connect(self.release_selected);rl.addWidget(self.release_list,1)
        self.release_notes=label('选择版本查看更新说明。');rl.addWidget(self.release_notes)
        row=QHBoxLayout();self.download_button=self.button('安装选中版本',self.install_selected,'primary');row.addWidget(self.download_button)
        self.activate_button=self.button('切换到此版本',self.activate_selected);row.addWidget(self.activate_button)
        self.uninstall_button=self.button('卸载此版本',self.uninstall_selected,'danger');row.addWidget(self.uninstall_button);rl.addLayout(row)
        self.detail_tabs.addTab(releases,'版本与卸载');self.pages.addWidget(self.detail)

    def build_settings(self):
        self.settings=QWidget();layout=QVBoxLayout(self.settings);layout.setContentsMargins(0,0,0,0);layout.setSpacing(18)
        layout.addWidget(label('设置与更新','title'));layout.addWidget(label('设置创作环境，其余交给工具架。','subtitle'))
        frame=QFrame();frame.setObjectName('card');form=QVBoxLayout(frame);form.setContentsMargins(24,24,24,24)
        form.addWidget(label('3ds Max 环境','title'));form.addWidget(label('软件路径和版本用于插件启动及兼容性检查。','subtitle'))
        row=QHBoxLayout();self.host_path=QLineEdit(self.workspace.executable.text());self.host_path.setPlaceholderText('选择已安装的 3dsmax.exe');row.addWidget(self.host_path,1);row.addWidget(self.button('选择软件',self.pick_host));form.addLayout(row)
        row=QHBoxLayout();row.addWidget(label('软件版本'));self.host_version=QLineEdit(self.workspace.host_version.text());row.addWidget(self.host_version);row.addWidget(self.button('保存环境',self.save_host,'primary'));form.addLayout(row);layout.addWidget(frame)
        frame=QFrame();frame.setObjectName('card');form=QVBoxLayout(frame);form.setContentsMargins(24,20,24,20)
        form.addWidget(label('工具架更新','title'));form.addWidget(label('当前版本 '+VERSION+' · 更新保留已装工具、夹子和软件设置。','subtitle'))
        self.update_button=self.button('检查并下载更新',self.update_client);form.addWidget(self.update_button)
        result=self.store.root/'update-result.txt'
        if result.exists():form.addWidget(label(result.read_text('utf-8'),'subtitle'))
        layout.addWidget(frame)
        frame=QFrame();frame.setObjectName('card');form=QVBoxLayout(frame);form.setContentsMargins(24,20,24,20)
        form.addWidget(label('账户与工具来源','title'));form.addWidget(label('公开商店可直接使用。GitHub 登录待作者注册应用后启用。','subtitle'))
        form.addWidget(label('工具目录由作者维护，随刷新自动更新。用户无需填写仓库地址。','subtitle'))
        form.addWidget(self.button('打开本地工具目录',lambda:os.startfile(str(self.tools_root))))
        layout.addWidget(frame);layout.addStretch();self.pages.addWidget(self.settings)

    def installed(self):
        tools, errors=discover_tools(self.tools_root)
        known={e['id'] for e in self.catalog.data['packages']}
        return [t for t in tools if t['id'] in known]

    def navigate(self, mode, folder=None):
        self.view_mode=mode;self.folder_id=folder
        for key,button in self.nav.items():button.setChecked(key==mode)
        if mode=='settings':self.pages.setCurrentWidget(self.settings);return
        self.browse_title.setText(self.library.data['folders'].get(folder,'我的工具') if mode=='library' else '发现工具')
        self.hero.setVisible(mode=='store');self.pages.setCurrentWidget(self.browse);self.render_cards()

    def render_cards(self):
        for row in range(self.cards.rowCount()):self.cards.setRowStretch(row,0)
        while self.cards.count():
            item=self.cards.takeAt(0)
            if item.widget():item.widget().deleteLater()
        installed=self.installed();installed_ids={t['id'] for t in installed}
        groups={}
        for entry in sorted(self.catalog.data['packages'],key=version_order,reverse=True):groups.setdefault(entry['id'],entry)
        count=0
        for entry in groups.values():
            identity=entry['id']
            if self.view_mode=='library' and identity not in installed_ids:continue
            if self.view_mode=='library' and self.folder_id and self.library.data['assignments'].get(identity)!=self.folder_id:continue
            if self.search.text().strip().lower() not in (entry['name']+' '+entry['description']).lower():continue
            if self.category.currentText() not in ('全部分类',entry.get('category','实用工具')):continue
            card=QFrame();card.setObjectName('card');card.setMinimumHeight(214)
            layout=QVBoxLayout(card);layout.setContentsMargins(20,18,20,18);layout.setSpacing(10)
            header=QHBoxLayout();icon=label({'动画':'AN','建模':'3D','导入':'IN'}.get(entry.get('category'),'TO'))
            icon.setStyleSheet('font-size:22px;font-weight:800;color:#a8c4ff;background:#2d3b58;border-radius:8px;padding:10px;');icon.setFixedWidth(64);header.addWidget(icon);header.addStretch()
            header.addWidget(label('已安装' if identity in installed_ids else '可安装','badge'));layout.addLayout(header)
            title=label(entry['name']);title.setStyleSheet('font-size:19px;font-weight:600');layout.addWidget(title)
            layout.addWidget(label(entry['description'],'subtitle'),1)
            row=QHBoxLayout();row.addWidget(label('3ds Max · '+entry.get('category','实用工具'),'badge'),1)
            row.addWidget(self.button('打开' if identity in installed_ids and self.view_mode=='library' else '查看工具',lambda i=identity:self.show_tool(i, self.view_mode=='library')));layout.addLayout(row)
            self.cards.addWidget(card,count//2,count%2);count+=1
        if count==0:
            empty=label('这里还没有工具。去商店安装，或换个关键词试试。','subtitle');self.cards.addWidget(empty,0,0,1,2)
        self.cards.setRowStretch((count+1)//2,1)
        self.cards.setColumnStretch(0,1);self.cards.setColumnStretch(1,1)
        self.hero_count.setText(f'{len(groups)} 款工具  /  已安装 {len(installed_ids)} 款  /  版本自由切换')
        self.summary.setText(f'{count} 款工具'+(' · 作者精选' if self.view_mode=='store' else ' · 你的本地工具库'))

    def refresh_folders(self):
        self.folders.blockSignals(True);self.folders.clear()
        for key,name in self.library.data['folders'].items():
            item=QListWidgetItem(name);item.setData(256,key);self.folders.addItem(item)
            if key==self.folder_id:self.folders.setCurrentItem(item)
        self.folders.blockSignals(False)

    def folder_selected(self, item, *_):
        if item:self.navigate('library',item.data(256))

    def create_folder(self):
        name,ok=QInputDialog.getText(self,'新建夹子','给夹子起个名字，例如：角色动画')
        if ok:
            key=self.library.create_folder(name);self.folder_id=key;self.refresh_folders();self.navigate('library',key)

    def rename_folder(self):
        item=self.folders.currentItem()
        if not item:raise ValueError('先选择左侧的夹子')
        key=item.data(256);name,ok=QInputDialog.getText(self,'重命名夹子','夹子名称',text=self.library.data['folders'][key])
        if ok:self.library.rename_folder(key,name);self.refresh_folders();self.navigate('library',key)

    def remove_folder(self):
        item=self.folders.currentItem()
        if not item:raise ValueError('先选择左侧的夹子')
        if QMessageBox.question(self,'移除夹子','只移除夹子，里面的工具仍保留在“我的工具”。')!=QMessageBox.StandardButton.Yes:return
        self.library.remove_folder(item.data(256));self.folder_id=None;self.refresh_folders();self.navigate('library')

    def move_tool(self):
        if self.current_id:
            self.guard(lambda:self.library.move(self.current_id,self.move_combo.currentData()))

    def show_tool(self, identity, panel=False):
        entries=sorted([e for e in self.catalog.data['packages'] if e['id']==identity],key=version_order,reverse=True)
        if not entries:raise ValueError('此工具已从作者目录撤下')
        self.current_id=identity;entry=entries[0]
        self.detail_title.setText(entry['name']);self.detail_description.setText(entry['description'])
        installed=[t for t in self.installed() if t['id']==identity]
        self.detail_badge.setText('3ds Max  /  '+entry.get('category','实用工具')+'  /  '+str(len(entries))+' 个释出版本')
        state=compatibility_state(entry['compatibility'],self.host_version.text())
        self.detail_help.setText('最新版 '+entry['version']+' · '+LABELS[state]+'\n'+entry.get('notes',''))
        newest_local=any(package_key(t)==package_key(entry) for t in installed)
        self.install_button.setText('已安装最新版本' if newest_local else '安装最新版本' if not installed else '更新到最新版本')
        self.install_button.setEnabled(not newest_local and state!='incompatible' and not self.job)
        self.panel_button.setEnabled(bool(installed));self.detail_tabs.setTabEnabled(1,bool(installed))
        self.move_combo.blockSignals(True);self.move_combo.clear();self.move_combo.addItem('未分类',None)
        for key,name in self.library.data['folders'].items():self.move_combo.addItem(name,key)
        self.move_combo.setCurrentIndex(max(0,self.move_combo.findData(self.library.data['assignments'].get(identity))))
        self.move_combo.setEnabled(bool(installed));self.move_combo.blockSignals(False)
        self.workspace.reload()
        for i in range(self.workspace.list.count()):
            if self.workspace.list.item(i).data(256)==identity:self.workspace.list.setCurrentRow(i);break
        active=self.active_key(identity,installed)
        self.release_list.clear()
        available={package_key(e):e for e in entries}
        for tool in installed:
            if package_key(tool) not in available:available[package_key(tool)]=dict(tool,notes='本地保留版本；当前商店不再提供下载。',local_only=True)
        for entry in sorted(available.values(),key=version_order,reverse=True):
            key=package_key(entry);local=next((t for t in installed if package_key(t)==key),None)
            item=QTreeWidgetItem([entry['version'], entry['compatibility']['range'].replace('unverified','待验证'), '使用中' if active==key else '已安装' if local else '未安装',entry.get('publishedAt') or '未提供'])
            item.setData(0,256,{'entry':entry,'local':local});self.release_list.addTopLevelItem(item)
        if self.release_list.topLevelItemCount():self.release_list.setCurrentItem(self.release_list.topLevelItem(0))
        self.detail_tabs.setCurrentIndex(1 if panel and installed else 0);self.pages.setCurrentWidget(self.detail)

    def active_key(self, identity, installed):
        selected=self.workspace.config.get('selectedVersions',{}).get(self.host_version.text(),{}).get(identity)
        return selected if any(package_key(t)==selected for t in installed) else (package_key(installed[0]) if installed else None)

    def selected_release(self):
        item=self.release_list.currentItem()
        if not item:raise ValueError('请选择一个版本')
        return item.data(0,256)

    def release_selected(self,*_):
        if not self.release_list.currentItem():return
        selection=self.selected_release();entry,local=selection['entry'],selection['local']
        state=compatibility_state(entry['compatibility'],self.host_version.text())
        self.release_notes.setText(LABELS[state]+'\n'+entry.get('notes','作者未提供更新说明。'))
        self.download_button.setEnabled(not local and not entry.get('local_only') and state!='incompatible' and not self.job)
        active=self.active_key(entry['id'],[t for t in self.installed() if t['id']==entry['id']])
        self.activate_button.setText('正在使用此版本' if active==package_key(entry) else '切换到此版本')
        self.activate_button.setEnabled(bool(local) and active!=package_key(entry) and state!='incompatible' and not self.job)
        self.uninstall_button.setEnabled(bool(local) and not self.job)

    def open_panel(self):self.detail_tabs.setCurrentIndex(1)

    def install_latest(self):
        entries=[e for e in self.catalog.data['packages'] if e['id']==self.current_id]
        self.install_entry(max(entries,key=version_order))

    def install_selected(self):self.install_entry(self.selected_release()['entry'])

    def install_entry(self,entry):
        if self.job:return
        if not self.workspace.check_compatibility(entry):return
        identity=entry['id'];version=package_key(entry)
        def done(_):
            self.workspace.choose_version(identity,version);self.show_tool(identity,True)
            self.status.setText('安装完成，已切换到 '+entry['version']+'。可在工具面板继续操作。')
        self.busy(lambda:fetch_packages(entry['repository'],self.tools_root,self.host_version.text(),True,
                  manifest_path=entry['manifest'],commit=entry.get('commit')),done,'正在下载并校验工具…')

    def activate_selected(self):
        if self.job:return
        selection=self.selected_release();tool=selection['local']
        if not tool:raise ValueError('请先安装此版本')
        if not self.workspace.check_compatibility(tool):return
        self.workspace.choose_version(tool['id'],package_key(tool));self.show_tool(tool['id'],True)
        self.status.setText('已切换到 '+tool['version']+'，旧版本保留。')

    def uninstall_selected(self):
        if self.job:return
        tool=self.selected_release()['local']
        if not tool:raise ValueError('此版本未安装')
        if QMessageBox.question(self,'卸载工具版本','卸载 '+tool['name']+' '+tool['version']+'？\n会删除工具架内该版本的文件。此前复制到 Max 的脚本需在宿主目录自行管理。')!=QMessageBox.StandardButton.Yes:return
        self.library.uninstall(tool)
        selected=self.workspace.config.get('selectedVersions',{}).get(self.host_version.text(),{})
        if selected.get(tool['id'])==package_key(tool):selected.pop(tool['id'],None);self.workspace.save_config()
        self.show_tool(tool['id']);self.status.setText('此版本已卸载。其他版本和夹子保留。')

    def busy(self,fn,done,message):
        if self.job:return
        self.progress.show();self.status.setText(message)
        self.job=Job(fn);self.job.result.connect(lambda value:self.guard(lambda:done(value)));self.job.failed.connect(lambda message:self.status.setText('未完成：'+message+'。已有工具和目录仍可使用。'))
        self.job.finished.connect(self.idle);self.sync_button.setEnabled(False);self.update_button.setEnabled(False)
        for button in (self.install_button,self.download_button,self.activate_button,self.uninstall_button):button.setEnabled(False)
        self.job.start()

    def idle(self):
        self.job.deleteLater();self.job=None;self.progress.hide();self.sync_button.setEnabled(True);self.update_button.setEnabled(True)
        if self.pages.currentWidget()==self.detail and self.current_id and any(e['id']==self.current_id for e in self.catalog.data['packages']):
            tab=self.detail_tabs.currentIndex();self.show_tool(self.current_id);self.detail_tabs.setCurrentIndex(tab)
        else:self.render_cards()
        if self.pending_restart:
            stage=self.pending_restart;self.pending_restart=None
            subprocess.Popen([str(stage/'LXTool.exe'),'--apply-update',str(Path(sys.executable).parent),str(os.getpid())],cwd=str(stage))
            self.close()

    def sync_catalog(self):
        def done(data):self.catalog.data=data;self.render_cards();self.status.setText('商店已更新 · '+str(len({e['id'] for e in data['packages']}))+' 款工具可供选择。')
        self.busy(lambda:self.catalog.sync(),done,'正在获取作者最新工具目录…')

    def pick_host(self):
        filename,_=QFileDialog.getOpenFileName(self,'选择 3ds Max','','3ds Max (3dsmax.exe)')
        if filename:self.host_path.setText(filename)

    def save_host(self):
        host_version(self.host_version.text())
        value=self.host_path.text().strip()
        if value and (not Path(value).is_file() or Path(value).name.lower()!='3dsmax.exe'):raise ValueError('请选择实际的 3dsmax.exe')
        self.workspace.executable.setText(value);self.workspace.host_version.setText(self.host_version.text())
        self.workspace.config.update({'3dsmax':value,'hostVersion':self.host_version.text()});self.workspace.save_config();self.workspace.reload()
        self.status.setText('创作环境已保存。')

    def update_client(self):
        def done(result):
            if result is None:self.status.setText('未发现新的稳定发行版，当前 '+VERSION+'。');return
            tag,stage=result
            if not getattr(sys,'frozen',False):self.status.setText('已准备 '+tag+'；源码模式不自动替换，请使用 EXE 测试更新。');return
            if QMessageBox.question(self,'安装工具架更新',tag+' 已下载并校验。现在关闭并更新工具架？已装工具和夹子会保留。')==QMessageBox.StandardButton.Yes:self.pending_restart=stage
        self.busy(lambda:prepare_update(self.store.root),done,'正在检查并准备工具架更新…')

    def closeEvent(self,event):
        if self.job or self.workspace.pull_job:
            self.status.setText('下载或更新进行中，请完成后关闭。');event.ignore()
        else:event.accept()


def main():
    if len(sys.argv)==4 and sys.argv[1]=='--apply-update':
        return apply_update(Path(sys.executable).parent,Path(sys.argv[2]),int(sys.argv[3]))
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'LXTool';root.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(root/'desktop.lock'))
    if not lock.tryLock(100):QMessageBox.information(None,'LXTool','工具架已经运行，请使用现有窗口。');return 0
    window=Window(ToolStore(root));window.show();return app.exec()


if __name__=='__main__':sys.exit(main())

