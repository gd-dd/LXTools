"""LXTool: author-curated tool store and desktop workspace."""
import os
import base64
import json
import sys
import subprocess
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QLockFile, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QFileDialog, QProgressBar, QStackedWidget, QFrame,
    QScrollArea, QTreeWidget, QTreeWidgetItem, QTextBrowser, QLayout, QHeaderView, QSizePolicy)
from packaging.version import Version, InvalidVersion
from core import ToolStore
from repository_panels import RepositoryWorkspace as ToolWorkspace
from lx_protocol import discover_packages as discover_tools, package_key, compatibility_label
from library import Library
from repository_source import RepositoryCatalog as AuthorCatalog, install_repository
from updater import VERSION, prepare_update, apply_update
from brand import icon_path
from gold_effect import GoldButton

from theme import STYLE
import development


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


class PageScroll(QScrollArea):
    """One scroll surface for all page content, without a height cap."""
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.setWidget(self.content)
        self.page_layout = QVBoxLayout(self.content)
        self.page_layout.setContentsMargins(0, 0, 16, 12)
        self.page_layout.setSpacing(18)
        self.page_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.page_layout.setAlignment(Qt.AlignTop)


class MarkdownView(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_content)

    def fit_content(self, *_):
        height = int(self.document().size().height()) + 2 * self.frameWidth() + 32
        if self.height() != height:
            self.setFixedHeight(max(60, height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_content()

    def wheelEvent(self, event):
        event.ignore()

    def loadResource(self, kind, url):
        # Documentation never fetches remote images or local file URLs.
        return None


class ReleaseList(QTreeWidget):
    def wheelEvent(self, event):
        event.ignore()


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
        self.development = development.enabled()
        self.display_version = "0.0.0 · 本地开发" if self.development else VERSION
        app_root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
        self.tools_root = Path(tools_root) if tools_root else app_root / 'tools'
        self.catalog = AuthorCatalog(store.root)
        self.library = Library(store.root, self.tools_root)
        self.current_id = None
        self.view_mode = 'store'
        self.folder_id = None
        self.pending_restart = None
        self.setWindowTitle('LXTool · '+('0.0.0 本地开发' if self.development else '创作工具商店'))
        self.setWindowIcon(QIcon(str(icon_path())))
        self.resize(1280, 840)
        self.setMinimumSize(1040, 720)
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0,0,0,0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)
        sidebar = QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar); side.setContentsMargins(20,26,20,20); side.setSpacing(12)
        brand_image=QLabel();brand_image.setPixmap(QPixmap(str(icon_path())).scaled(96,96,Qt.KeepAspectRatio,Qt.SmoothTransformation));brand_image.setFixedSize(96,96);side.addWidget(brand_image)
        brand = label('LX / TOOLS'); brand.setStyleSheet('font-size:25px;font-weight:800;color:#507522')
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
        side.addWidget(label('LXTool  ' + self.display_version, 'subtitle'))
        root_layout.addWidget(sidebar)
        body=QWidget(); body_layout=QVBoxLayout(body);body_layout.setContentsMargins(28,24,28,16)
        self.pages=QStackedWidget();body_layout.addWidget(self.pages,1)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();body_layout.addWidget(self.progress)
        self.status=label('已载入作者目录。公开工具无需登录即可安装。','subtitle');body_layout.addWidget(self.status)
        root_layout.addWidget(body,1)
        self.build_browse()
        self.build_detail()
        self.build_tool_panel()
        self.build_settings()
        self.refresh_folders()
        self.navigate('store')
        if self.development:
            self.project_root=app_root
            self.dev_stamp=development.fingerprint(app_root)
            self.dev_pending=None
            self.dev_timer=QTimer(self);self.dev_timer.timeout.connect(self.check_development);self.dev_timer.start(1000)
            self.navigate('store')
            if autoload:QTimer.singleShot(1000,self.sync_catalog)
        if autoload and not self.development and QApplication.platformName() != 'offscreen':
            QTimer.singleShot(300, self.sync_catalog)

    def button(self, text, fn, kind=None):
        button=GoldButton(text)
        if kind:button.setObjectName(kind)
        button.clicked.connect(lambda checked=False:self.guard(fn))
        return button

    def guard(self, fn):
        try:return fn()
        except Exception as error:self.status.setText(str(error))

    def build_browse(self):
        self.browse=PageScroll();layout=self.browse.page_layout
        row=QHBoxLayout();self.browse_title=label('发现工具','title');row.addWidget(self.browse_title,1)
        self.sync_button=self.button('扫描作者仓库',self.sync_catalog);row.addWidget(self.sync_button);layout.addLayout(row)
        self.hero=QFrame();self.hero.setObjectName('hero');hero=QVBoxLayout(self.hero);hero.setContentsMargins(24,20,24,20)
        hero.addWidget(label('把重复工作交给工具。','title'))
        hero.addWidget(label('浏览作者持续维护的创作工具，按需安装，随时切换版本。','subtitle'))
        self.hero_count=label('','badge');hero.addWidget(self.hero_count);layout.addWidget(self.hero)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('搜索工具名称或用途…');self.search.textChanged.connect(self.render_cards)
        row.addWidget(self.search,1);self.category=QComboBox();self.category.addItems(['全部分类']+sorted({e.get('category','实用工具') for e in self.catalog.data['packages']}));self.category.currentTextChanged.connect(self.render_cards);row.addWidget(self.category)
        self.install_filter=QComboBox();self.install_filter.addItems(['全部状态','已下载','未下载','可更新']);self.install_filter.currentTextChanged.connect(self.render_cards);row.addWidget(self.install_filter)
        layout.addLayout(row)
        self.summary=label('','subtitle');layout.addWidget(self.summary)
        self.card_area=QWidget();self.card_area.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum);self.cards=QGridLayout(self.card_area);self.cards.setSpacing(16);self.cards.setContentsMargins(0,0,8,0)
        layout.addWidget(self.card_area);self.pages.addWidget(self.browse)

    def build_detail(self):
        self.detail=PageScroll();layout=self.detail.page_layout
        row=QHBoxLayout();row.addWidget(self.button('‹ 返回发现工具',lambda:self.navigate('store')));row.addStretch();layout.addLayout(row)
        header=QHBoxLayout();header.setSpacing(24)
        self.detail_icon=QLabel();self.detail_icon.setFixedSize(160,160);self.detail_icon.setAlignment(Qt.AlignCenter)
        self.detail_icon.setAccessibleName('工具大图标');header.addWidget(self.detail_icon)
        info=QVBoxLayout();info.addStretch()
        self.detail_title=label('','title');info.addWidget(self.detail_title)
        self.detail_description=label('','subtitle');info.addWidget(self.detail_description);info.addStretch()
        header.addLayout(info,1);layout.addLayout(header)
        self.overview=QWidget();overview=QVBoxLayout(self.overview);overview.setContentsMargins(24,24,24,24);overview.setSpacing(18)
        self.detail_badge=label('','badge');overview.addWidget(self.detail_badge)
        self.detail_help=label('');overview.addWidget(self.detail_help)
        self.install_button=self.button('安装工具',self.install_latest,'primary');overview.addWidget(self.install_button)
        self.readme=MarkdownView();self.readme.setOpenExternalLinks(False);self.readme.setOpenLinks(False);overview.addWidget(self.readme,1)
        layout.addWidget(self.overview)
        releases=QWidget();rl=QVBoxLayout(releases);rl.setContentsMargins(20,20,20,20)
        rl.addWidget(label('全部释出版本','title'));rl.addWidget(label('安装新版本不会删除旧版本。选择已安装版本即可切换或回退。','subtitle'))
        self.release_list=ReleaseList();self.release_list.setHeaderLabels(['版本','兼容范围','本地状态','发布日期']);self.release_list.setRootIsDecorated(False);self.release_list.setColumnWidth(0,170);self.release_list.setColumnWidth(1,200);self.release_list.setColumnWidth(2,120)
        self.release_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.release_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.release_list.header().setSectionResizeMode(QHeaderView.Stretch)
        self.release_list.setWordWrap(True)
        self.release_list.currentItemChanged.connect(self.release_selected);rl.addWidget(self.release_list,1)
        self.release_notes=label('选择版本查看更新说明。');rl.addWidget(self.release_notes)
        row=QHBoxLayout();self.download_button=self.button('安装选中版本',self.install_selected,'primary');row.addWidget(self.download_button)
        self.activate_button=self.button('切换到此版本',self.activate_selected);row.addWidget(self.activate_button)
        self.uninstall_button=self.button('卸载此版本',self.uninstall_selected,'danger');row.addWidget(self.uninstall_button);rl.addLayout(row)
        layout.addWidget(releases);self.pages.addWidget(self.detail)

    def build_tool_panel(self):
        self.tool_panel=QWidget();layout=QVBoxLayout(self.tool_panel);layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();row.addWidget(self.button('‹ 返回我的工具',lambda:self.navigate('library',self.folder_id)))
        self.panel_title=label('','title');row.addWidget(self.panel_title,1)
        row.addWidget(label('收纳到','subtitle'));self.move_combo=QComboBox();self.move_combo.setMinimumWidth(140)
        self.move_combo.currentIndexChanged.connect(self.move_tool);row.addWidget(self.move_combo);layout.addLayout(row)
        self.workspace=ToolWorkspace(self.tools_root,self.store.root,managed=True)
        layout.addWidget(self.workspace,1);self.pages.addWidget(self.tool_panel)

    def open_tool_panel(self,identity):
        if self.view_mode!='library':raise ValueError('请从“我的工具”打开工具面板')
        installed=[t for t in self.installed() if t['id']==identity]
        if not installed:raise ValueError('此工具尚未下载，请到“发现工具”安装')
        active=self.active_key(identity,installed)
        tool=next(t for t in installed if t['version']==active)
        self.current_id=identity;self.panel_title.setText(tool['name']+' · '+tool['version'])
        self.move_combo.blockSignals(True);self.move_combo.clear();self.move_combo.addItem('未分类',None)
        for key,name in self.library.data['folders'].items():self.move_combo.addItem(name,key)
        self.move_combo.setCurrentIndex(max(0,self.move_combo.findData(self.library.data['assignments'].get(identity))))
        self.move_combo.blockSignals(False)
        self.workspace.display(tool);self.pages.setCurrentWidget(self.tool_panel)

    def build_settings(self):
        self.settings=QWidget();layout=QVBoxLayout(self.settings);layout.setContentsMargins(0,0,0,0);layout.setSpacing(18)
        layout.addWidget(label('设置与更新','title'));layout.addWidget(label('设置创作环境，其余交给工具架。','subtitle'))
        layout.addWidget(label('运行环境由各个工具自行声明，请在对应工具面板中配置。','subtitle'))
        frame=QFrame();frame.setObjectName('card');form=QVBoxLayout(frame);form.setContentsMargins(24,20,24,20)
        form.addWidget(label('工具架更新','title'));form.addWidget(label('当前版本 '+self.display_version+' · 更新保留已装工具、夹子和软件设置。','subtitle'))
        self.update_button=self.button('检查并下载更新',self.update_client);form.addWidget(self.update_button)
        if self.development:
            self.update_button.setEnabled(False)
            form.addWidget(label('开发版直接运行 project 源码，不接收客户端更新；正式商店仍只列 GitHub Release。','subtitle'))
        result=self.store.root/'update-result.txt'
        if result.exists():form.addWidget(label(result.read_text('utf-8'),'subtitle'))
        layout.addWidget(frame)
        frame=QFrame();frame.setObjectName('card');form=QVBoxLayout(frame);form.setContentsMargins(24,20,24,20)
        form.addWidget(label('账户与工具来源','title'));form.addWidget(label('公开商店可直接使用。GitHub 登录待作者注册应用后启用。','subtitle'))
        form.addWidget(label('自动扫描 gd-dd 的仓库；只有带有效 .lxtool 标识的项目进入商店。一仓库一工具。','subtitle'))
        form.addWidget(self.button('打开本地工具目录',lambda:os.startfile(str(self.tools_root))))
        layout.addWidget(frame);layout.addStretch();self.pages.addWidget(self.settings)

    def installed(self):
        tools, errors=discover_tools(self.tools_root)
        known={e['id'] for e in self.catalog.data['packages']}
        return [t for t in tools if t['id'] in known and (self.development or t.get('distribution')!='github-branch')]

    def navigate(self, mode, folder=None):
        if hasattr(self,'workspace'):self.workspace.shutdown()
        selected_mode=mode
        self.view_mode=mode;self.folder_id=folder
        for key,button in self.nav.items():button.setChecked(key==selected_mode)
        if mode=='settings':self.pages.setCurrentWidget(self.settings);return
        self.browse_title.setText(self.library.data['folders'].get(folder,'我的工具') if mode=='library' else '发现工具')
        self.hero.setVisible(mode=='store');self.pages.setCurrentWidget(self.browse);self.render_cards()
        self.install_filter.setVisible(mode=='store');self.sync_button.setVisible(mode=='store')
        self.sync_button.setText('扫描作者仓库')

    def render_cards(self):
        for row in range(self.cards.rowCount()):self.cards.setRowStretch(row,0)
        while self.cards.count():
            item=self.cards.takeAt(0)
            if item.widget():
                item.widget().hide();item.widget().deleteLater()
        installed=self.installed();installed_ids={t['id'] for t in installed}
        groups={}
        for entry in sorted(self.catalog.data['packages'],key=version_order,reverse=True):groups.setdefault(entry['id'],entry)
        count=0
        for entry in groups.values():
            identity=entry['id']
            local=[t for t in installed if t['id']==identity]
            update_entry=next((e for e in self.catalog.data['packages'] if e['id']==identity and e.get('distribution')=='github-branch' and any(t['version']=='0.0.0' and t.get('commit')!=e.get('commit') for t in local)),entry)
            update=bool(local) and (update_entry is not entry or version_order(entry)>max(version_order(t) for t in local) or (entry.get('distribution')=='github-branch' and any(t['version']=='0.0.0' and t.get('commit')!=entry.get('commit') for t in local)))
            if self.view_mode=='library' and identity not in installed_ids:continue
            if self.view_mode=='library' and self.folder_id and self.library.data['assignments'].get(identity)!=self.folder_id:continue
            if self.search.text().strip().lower() not in (entry['name']+' '+entry['description']).lower():continue
            if self.category.currentText() not in ('全部分类',entry.get('category','实用工具')):continue
            if self.view_mode=='store':
                state=self.install_filter.currentText()
                if state=='已下载' and not local:continue
                if state=='未下载' and local:continue
                if state=='可更新' and not update:continue
            card=QFrame();card.setObjectName('card');card.setMinimumHeight(214)
            layout=QVBoxLayout(card);layout.setContentsMargins(20,18,20,18);layout.setSpacing(10)
            header=QHBoxLayout()
            open_action=self.open_tool_panel if self.view_mode=='library' else self.show_tool
            icon=self.button('',lambda i=identity,fn=open_action:fn(i),'brandIcon')
            pixmap=QPixmap();pixmap.loadFromData(base64.b64decode(entry['iconData']))
            icon.setIcon(QIcon(pixmap));icon.setIconSize(QSize(64,64));icon.setFixedSize(82,82)
            icon.setToolTip(('打开工具面板：' if self.view_mode=='library' else '阅读介绍：')+entry['name']);header.addWidget(icon);header.addStretch()
            header.addWidget(label('可更新' if update else '已下载' if local else '未下载','badge'));layout.addLayout(header)
            title=label(entry['name']);title.setStyleSheet('font-size:19px;font-weight:600');layout.addWidget(title)
            layout.addWidget(label(entry['description'],'subtitle'),1)
            row=QHBoxLayout();row.addWidget(label(entry.get('category','实用工具'),'badge'),1)
            if self.view_mode=='library':
                row.addWidget(self.button('打开工具',lambda i=identity:self.open_tool_panel(i),'primary'))
            else:
                row.addWidget(self.button('详情',lambda i=identity:self.show_tool(i)))
                if not local or update:
                    action=self.button('更新' if update else '下载',lambda e=update_entry:self.install_entry(e),'primary');action.setEnabled(not self.job);row.addWidget(action)
                if local:
                    action=self.button('卸载',lambda i=identity:self.uninstall_tool(i),'danger');action.setEnabled(not self.job);row.addWidget(action)
            layout.addLayout(row)
            self.cards.addWidget(card,count//2,count%2);count+=1
        if count==0:
            empty=label('没有符合筛选条件的工具。试试其他分类或关键词。' if self.view_mode=='store' else '这里还没有已下载工具。请在“发现工具”下载，或调整分类和关键词。','subtitle');self.cards.addWidget(empty,0,0,1,2)
        self.reflow_cards()

        self.hero_count.setText(f'{len(groups)} 款工具  /  已安装 {len(installed_ids)} 款  /  版本自由切换')
        self.summary.setText(f'{count} 款工具'+(' · 作者精选' if self.view_mode=='store' else ' · 你的本地工具库'))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'cards'):
            QTimer.singleShot(0,self.reflow_cards)

    def reflow_cards(self):
        columns = 2 if self.browse.viewport().width() >= 900 else 1
        widgets = [self.cards.itemAt(i).widget() for i in range(self.cards.count())]
        for widget in widgets:
            self.cards.removeWidget(widget)
        for i, widget in enumerate(widgets):
            self.cards.addWidget(widget, i // columns, i % columns)
        self.cards.setColumnStretch(0, 1)
        self.cards.setColumnStretch(1, 1 if columns == 2 else 0)

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

    def show_tool(self, identity):
        self.view_mode='store'
        for key,button in self.nav.items():button.setChecked(key=='store')
        entries=sorted([e for e in self.catalog.data['packages'] if e['id']==identity],key=version_order,reverse=True)
        if not entries:raise ValueError('此工具已从作者目录撤下')
        self.current_id=identity;entry=entries[0]
        pixmap=QPixmap();pixmap.loadFromData(base64.b64decode(entry['iconData']))
        self.detail_icon.setPixmap(pixmap.scaled(160,160,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        self.detail_title.setText(entry['name']);self.detail_description.setText(entry['description'])
        installed=[t for t in self.installed() if t['id']==identity]
        self.detail_badge.setText(entry.get('category','实用工具')+'  /  '+str(len(entries))+' 个可安装版本')
        self.readme.setMarkdown(entry.get('readmeText','作者未提供介绍。'))
        self.detail_help.setText('最新版 '+entry['version']+' · '+compatibility_label(entry)+'\n'+entry.get('notes',''))
        newest_local=any(package_key(t)==package_key(entry) and (entry.get('distribution')!='github-branch' or t.get('commit')==entry.get('commit')) for t in installed)
        self.install_button.setText('已安装最新版本' if newest_local else '安装最新版本' if not installed else '更新到最新版本')
        self.install_button.setEnabled(not newest_local and not self.job)
        active=self.active_key(identity,installed)
        self.release_list.clear()
        available={package_key(e):e for e in entries}
        for tool in installed:
            if package_key(tool) not in available:available[package_key(tool)]=dict(tool,notes='本地保留版本；当前商店不再提供下载。',local_only=True)
        for entry in sorted(available.values(),key=version_order,reverse=True):
            key=package_key(entry);local=next((t for t in installed if package_key(t)==key),None)
            item=QTreeWidgetItem([('0.0.0 · '+entry.get('branch','最新分支')+' · '+entry.get('commit','')[:8] if entry.get('distribution')=='github-branch' else entry['version']), compatibility_label(entry), '使用中' if active==key else '已安装' if local else '未安装',entry.get('publishedAt') or '未提供'])
            item.setData(0,256,{'entry':entry,'local':local});self.release_list.addTopLevelItem(item)
        if self.release_list.topLevelItemCount():self.release_list.setCurrentItem(self.release_list.topLevelItem(0))
        self.pages.setCurrentWidget(self.detail)
        self.release_list.doItemsLayout()
        rows_height=sum(self.release_list.sizeHintForRow(i) for i in range(self.release_list.topLevelItemCount()))
        self.release_list.setFixedHeight(rows_height+self.release_list.header().height()+2*self.release_list.frameWidth()+4)
        self.detail.verticalScrollBar().setValue(0)

    def active_key(self, identity, installed):
        return self.workspace.selected(identity,installed)

    def selected_release(self):
        item=self.release_list.currentItem()
        if not item:raise ValueError('请选择一个版本')
        return item.data(0,256)

    def release_selected(self,*_):
        if not self.release_list.currentItem():return
        selection=self.selected_release();entry,local=selection['entry'],selection['local']
        self.release_notes.setText(compatibility_label(entry)+'\n'+entry.get('notes','作者未提供更新说明。'))
        branch_update=bool(local and entry.get('distribution')=='github-branch' and local.get('commit')!=entry.get('commit'))
        self.download_button.setText('更新分支快照' if branch_update else '安装选中版本')
        self.download_button.setEnabled((not local or branch_update) and not entry.get('local_only') and not self.job)
        active=self.active_key(entry['id'],[t for t in self.installed() if t['id']==entry['id']])
        self.activate_button.setText('正在使用此版本' if active==package_key(entry) else '切换到此版本')
        self.activate_button.setEnabled(bool(local) and active!=package_key(entry) and not self.job)
        self.uninstall_button.setEnabled(bool(local) and not self.job)

    def install_latest(self):
        entries=[e for e in self.catalog.data['packages'] if e['id']==self.current_id]
        self.install_entry(max(entries,key=version_order))

    def install_selected(self):self.install_entry(self.selected_release()['entry'])

    def install_entry(self,entry):
        if self.job:return
        identity=entry['id'];version=package_key(entry)
        def done(_):
            self.workspace.choose_version(identity,version)
            self.status.setText('下载完成，已选择 '+entry['version']+'。请从“我的工具”打开。')
        if entry.get('distribution')=='github-branch':
            if not self.development:raise ValueError('正式版只接受 Release')
            installer=development.install_branch
        else:installer=install_repository
        self.busy(lambda:installer(entry,self.tools_root),done,'正在下载并校验工具…')

    def activate_selected(self):
        if self.job:return
        selection=self.selected_release();tool=selection['local']
        if not tool:raise ValueError('请先安装此版本')
        self.workspace.choose_version(tool['id'],package_key(tool));self.show_tool(tool['id']);QTimer.singleShot(0,lambda:self.detail.ensureWidgetVisible(self.activate_button))
        self.status.setText('已切换到 '+tool['version']+'，旧版本保留。')

    def uninstall_selected(self):
        if self.job:return
        tool=self.selected_release()['local']
        if not tool:raise ValueError('此版本未安装')
        if QMessageBox.question(self,'卸载工具版本','卸载 '+tool['name']+' '+tool['version']+'？\n会删除工具架内该版本的文件。此前复制到其他软件目录的文件需自行管理。')!=QMessageBox.StandardButton.Yes:return
        self.library.uninstall(tool)
        selected=self.workspace.config.get('selectedVersions',{})
        if selected.get(tool['id'])==package_key(tool):selected.pop(tool['id'],None);self.workspace.save_config()
        self.show_tool(tool['id']);self.status.setText('此版本已卸载。其他版本和夹子保留。')

    def uninstall_tool(self,identity):
        if self.job:return
        installed=[t for t in self.installed() if t['id']==identity]
        if not installed:return
        if QMessageBox.question(self,'卸载工具','卸载 '+installed[0]['name']+' 的全部 '+str(len(installed))+' 个本地版本？\n外部软件中的插件副本不会被删除。')!=QMessageBox.StandardButton.Yes:return
        for tool in installed:self.library.uninstall(tool)
        self.workspace.config.get('selectedVersions',{}).pop(identity,None);self.workspace.save_config()
        self.render_cards();self.status.setText('已卸载工具全部本地版本。')

    def busy(self,fn,done,message):
        if self.job:return
        self.progress.show();self.status.setText(message)
        self.job=Job(fn);self.job.result.connect(lambda value:self.guard(lambda:done(value)));self.job.failed.connect(lambda message:self.status.setText('未完成：'+message+'。已有工具和目录仍可使用。'))
        self.job.finished.connect(self.idle);self.sync_button.setEnabled(False);self.update_button.setEnabled(False)
        for button in (self.install_button,self.download_button,self.activate_button,self.uninstall_button):button.setEnabled(False)
        self.render_cards()
        self.job.start()

    def idle(self):
        self.job.deleteLater();self.job=None;self.progress.hide();self.sync_button.setEnabled(True);self.update_button.setEnabled(not self.development)
        if self.pages.currentWidget()==self.detail and self.current_id and any(e['id']==self.current_id for e in self.catalog.data['packages']):
            position=self.detail.verticalScrollBar().value();self.show_tool(self.current_id);QTimer.singleShot(0,lambda:self.detail.verticalScrollBar().setValue(position))
        elif self.pages.currentWidget()==self.tool_panel:
            self.open_tool_panel(self.current_id)
        else:self.render_cards()
        if self.pending_restart:
            stage=self.pending_restart;self.pending_restart=None
            self.guard(lambda:self.restart_updated(stage))

    def sync_catalog(self):
        def done(data):
            self.catalog.data=data
            selected=self.category.currentText();self.category.blockSignals(True);self.category.clear()
            self.category.addItems(['全部分类']+sorted({e.get('category','实用工具') for e in data['packages']}))
            self.category.setCurrentIndex(max(0,self.category.findText(selected)));self.category.blockSignals(False)
            self.render_cards()
            warning=' · '+str(len(data.get('warnings',[])))+' 个仓库需检查' if data.get('warnings') else ''
            self.status.setText('已扫描 '+str(data.get('scannedRepositories',0))+' 个仓库 · 发现 '+str(len({e['id'] for e in data['packages']}))+' 个 LX 工具'+warning)
            self.status.setToolTip('\n'.join(data.get('warnings',[])))
        def scan():
            data=AuthorCatalog(self.store.root).sync()
            if self.development:
                branches,warnings=development.scan_branches()
                data['packages'].extend(branches);data.setdefault('warnings',[]).extend(warnings)
            return data
        self.busy(scan,done,'正在扫描 gd-dd 的仓库并验证 LX 标识…')

    def check_development(self):
        current=development.fingerprint(self.project_root)
        if current==self.dev_stamp:return
        if current!=self.dev_pending:
            self.dev_pending=current;return
        if self.job or QApplication.activeModalWidget():return
        self.reload_development()

    def reload_development(self):
        if not self.development:return
        if self.job:
            self.status.setText('等待当前任务完成后重载。');return
        try:
            paths=list((self.project_root/'src').glob('*.py'))
            for path in paths:compile(path.read_bytes(),str(path),'exec')
        except (SyntaxError,OSError) as error:
            self.status.setText('暂不重载，请先修复源码：'+str(error));return
        state={'view':self.view_mode}
        (self.store.root/'preview-state.json').write_text(json.dumps(state),encoding='utf-8')
        self.workspace.shutdown()
        QApplication.instance().exit(75)

    def update_client(self):
        if self.development:
            self.status.setText('本地开发版通过源码更新，不接收 Release 覆盖。');return
        def done(result):
            if result is None:self.status.setText('未发现新的稳定发行版，当前 '+VERSION+'。');return
            tag,stage=result
            if not getattr(sys,'frozen',False):self.status.setText('已准备 '+tag+'；源码模式不自动替换，请使用 EXE 测试更新。');return
            if QMessageBox.question(self,'安装工具架更新',tag+' 已下载并校验。现在关闭并更新工具架？已装工具和夹子会保留。')==QMessageBox.StandardButton.Yes:self.restart_updated(stage)
        self.busy(lambda:prepare_update(self.store.root),done,'正在检查并准备工具架更新…')

    def restart_updated(self,stage):
        if self.job:
            self.pending_restart=stage
            return
        subprocess.Popen([str(stage/'LXTool.exe'),'--apply-update',str(Path(sys.executable).parent),str(os.getpid())],cwd=str(stage))
        self.close()

    def closeEvent(self,event):
        if self.job:
            self.status.setText('下载或更新进行中，请完成后关闭。');event.ignore()
        else:
            self.workspace.shutdown()
            event.accept()


def main():
    if len(sys.argv)==4 and sys.argv[1]=='--apply-update':
        return apply_update(Path(sys.executable).parent,Path(sys.argv[2]),int(sys.argv[3]))
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE);app.setWindowIcon(QIcon(str(icon_path())))
    project=Path(__file__).resolve().parents[1]
    root=project/'runtime/development/profile' if development.enabled() else Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'LXTool'
    root.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(root/'desktop.lock'))
    if not lock.tryLock(100):QMessageBox.information(None,'LXTool','工具架已经运行，请使用现有窗口。');return 0
    window=Window(ToolStore(root),project/'tools' if development.enabled() else None)
    state_file=root/'preview-state.json'
    if development.enabled() and state_file.exists():
        try:
            state=json.loads(state_file.read_text('utf-8'))
            mode=state.get('view','store')
            window.navigate(mode if mode in ('store','library','settings') else 'store')
        except (ValueError,OSError):pass
    window.show();return app.exec()


if __name__=='__main__':sys.exit(main())
