"""Generic tool-owned panels and actions. The shelf knows no DCC commands."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QFileDialog,QMessageBox,QScrollArea
from library import write_json
from lx_protocol import discover_packages,checked_bytes
from compatibility import compatibility_state,LABELS,host_version
from brand import readable_accent,ACCENT
from gold_effect import GoldButton as QPushButton


def action_arguments(tool,action,settings):
    if 'application' in action:
        key=action['application'];app=tool['applications'][key]
        executable=Path(settings.get(key,{}).get('path',''))
        if not executable.is_file() or executable.name.lower()!=app['executable'].lower():raise ValueError('请在本工具面板配置 '+app['name'])
    else:
        executable=(tool['root']/action['executable']).resolve()
        if not executable.is_relative_to(tool['root']):raise ValueError('程序路径越界')
        checked_bytes(executable.read_bytes(),tool['files'][action['executable']])
    args=[str(executable)]
    for value in action.get('arguments',[]):
        if value.startswith('{file:') and value.endswith('}'):
            path=value[6:-1];file=(tool['root']/path).resolve()
            if not file.is_relative_to(tool['root']):raise ValueError('参数文件越界')
            checked_bytes(file.read_bytes(),tool['files'][path]);value=str(file)
        args.append(value)
    return args


def copy_action(tool,action,directory):
    base=Path(directory).resolve();target=(base/action['destinationFolder']/tool['version']).resolve()
    if not base.is_dir() or not target.is_relative_to(base):raise ValueError('复制目标无效')
    if target.exists():raise ValueError('目标版本已存在，未覆盖')
    staging=Path(tempfile.mkdtemp(prefix='.lx-copy-',dir=base))
    try:
        for path in action['files']:
            source=(tool['root']/path).resolve()
            if not source.is_relative_to(tool['root']):raise ValueError('源文件越界')
            data=checked_bytes(source.read_bytes(),tool['files'][path]);output=staging/path;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
        target.parent.mkdir(parents=True,exist_ok=True);os.replace(staging,target)
    finally:
        if staging.exists() and staging.resolve().is_relative_to(base):shutil.rmtree(staging)
    return '已复制到 '+str(target)


class RepositoryWorkspace(QWidget):
    def __init__(self,tools_root,config_root,managed=True):
        super().__init__();self.tools_root=Path(tools_root);self.tools_root.mkdir(parents=True,exist_ok=True)
        self.config_file=Path(config_root)/'repository-tools-v2.json'
        self.config=json.loads(self.config_file.read_text('utf-8')) if self.config_file.exists() else {'selectedVersions':{},'applications':{}}
        self.layout=QVBoxLayout(self);self.current=None

    def save_config(self):write_json(self.config_file,self.config)

    def shutdown(self):
        if getattr(self,'native_panel',None):
            self.native_panel.shutdown();self.native_panel=None
        if getattr(self,'session_panel',None):
            self.session_panel.shutdown();self.session_panel=None

    def choose_version(self,identity,version):
        self.config.setdefault('selectedVersions',{})[identity]=version;self.save_config()

    def selected(self,identity,installed):
        selected=self.config.get('selectedVersions',{}).get(identity)
        return selected if any(t['version']==selected for t in installed) else (installed[0]['version'] if installed else None)

    def display(self,tool):
        self.shutdown()
        self.current=tool
        while self.layout.count():
            item=self.layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        if not tool:self.layout.addWidget(QLabel('请先安装工具。'));return
        if tool['panelData']['type']=='native':
            from native_panels import NativePanelHandle
            container=QWidget(self);content=QVBoxLayout(container);content.setContentsMargins(0,0,0,0)
            try:
                self.native_panel=NativePanelHandle(tool,self.config_file.parent,container)
                content.addWidget(self.native_panel.widget)
                self.layout.addWidget(container,1)
            except (Exception,SystemExit) as error:
                container.deleteLater()
                label=QLabel('工具面板加载失败：'+str(error)+'\n请更新工具或向工具作者反馈。')
                label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);self.layout.addWidget(label)
            return
        if 'session' in tool['panelData']:
            from session_panels import SessionPanel
            settings=self.config.get('applications',{}).get(tool['id'],{})
            def save(settings):
                self.config.setdefault('applications',{})[tool['id']]=settings;self.save_config()
            scroll=QScrollArea();scroll.setWidgetResizable(True)
            self.session_panel=SessionPanel(tool,tool['panelData']['session'],settings,save,self)
            scroll.setWidget(self.session_panel);self.layout.addWidget(scroll,1)
            return
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();layout=QVBoxLayout(content);layout.setSpacing(14)
        settings=self.config.get('applications',{}).get(tool['id'],{})
        for key,app in tool.get('applications',{}).items():
            title=QLabel(app['name']+' · 工具声明的运行环境');title.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(title)
            row=QHBoxLayout();path=QLineEdit(settings.get(key,{}).get('path',''));path.setReadOnly(True);path.setPlaceholderText('选择 '+app['executable']);row.addWidget(path,1)
            choose=QPushButton('选择程序');choose.clicked.connect(lambda checked=False,k=key:self.guard(lambda:self.pick_app(k)));row.addWidget(choose);layout.addLayout(row)
            compatibility=app.get('compatibility')
            if compatibility:
                row=QHBoxLayout();row.addWidget(QLabel('目标软件版本'));version=QLineEdit(settings.get(key,{}).get('version',''));version.setPlaceholderText('例如 2026.3，由工具要求填写');row.addWidget(version)
                save=QPushButton('保存版本');save.clicked.connect(lambda checked=False,k=key,v=version:self.guard(lambda:self.set_version(k,v.text())));row.addWidget(save);layout.addLayout(row)
                layout.addWidget(QLabel('作者声明：'+compatibility.get('range','unverified').replace('unverified','待验证')))
        panel=tool['panelData']
        if panel['type']=='none':layout.addWidget(QLabel('该工具不提供工具架面板。请按介绍文档使用。'))
        else:
            if panel.get('title'):
                title=QLabel(panel['title']);title.setTextFormat(Qt.TextFormat.PlainText);title.setStyleSheet('font-size:22px;font-weight:600;color:'+readable_accent(panel.get('accent',ACCENT)));layout.addWidget(title)
            for section in panel['sections']:
                for field in ('title','text'):
                    if field in section:
                        item=QLabel(section[field]);item.setTextFormat(Qt.TextFormat.PlainText);item.setWordWrap(True)
                        if field=='title':item.setStyleSheet('font-size:17px;font-weight:600')
                        layout.addWidget(item)
                for item in section.get('actions',[]):
                    button=QPushButton(item['label']);button.clicked.connect(lambda checked=False,key=item['action']:self.guard(lambda:self.execute(key)));layout.addWidget(button)
        layout.addStretch();scroll.setWidget(content);self.layout.addWidget(scroll,1)
        self.status=QLabel('');self.status.setWordWrap(True);self.layout.addWidget(self.status)

    def guard(self,fn):
        try:self.status.setText(str(fn() or '操作完成'))
        except Exception as error:self.status.setText(str(error))

    def pick_app(self,key):
        app=self.current['applications'][key]
        path,_=QFileDialog.getOpenFileName(self,'选择 '+app['name'],'','程序 ('+app['executable']+')')
        if not path:return '已取消'
        if Path(path).name.lower()!=app['executable'].lower():raise ValueError('需要 '+app['executable'])
        self.config.setdefault('applications',{}).setdefault(self.current['id'],{}).setdefault(key,{})['path']=path
        self.save_config();self.display(self.current)

    def set_version(self,key,value):
        host_version(value)
        self.config.setdefault('applications',{}).setdefault(self.current['id'],{}).setdefault(key,{})['version']=value
        self.save_config();return '软件版本已保存'

    def execute(self,key):
        tool=self.current
        # Revalidate on click: discovery does not execute any code.
        candidates=discover_packages(self.tools_root)[0]
        verified=next((t for t in candidates if t['id']==tool['id'] and t['version']==tool['version']),None)
        if not verified:raise ValueError('工具文件已改变，请重新安装或核对')
        action=tool['actions'][key];settings=self.config.get('applications',{}).get(tool['id'],{})
        if action['type']=='process':
            args=action_arguments(tool,action,settings)
            if 'application' in action:
                app=tool['applications'][action['application']];compatibility=app.get('compatibility')
                if compatibility:
                    selected=settings.get(action['application'],{}).get('version','')
                    if not selected:raise ValueError('请填写本工具的目标软件版本')
                    state=compatibility_state(compatibility,selected)
                    if state=='incompatible':raise ValueError('该工具版本不支持所填软件版本')
                    if state!='tested' and QMessageBox.question(self,'兼容性待验证',LABELS[state]+'。仍要测试运行？')!=QMessageBox.StandardButton.Yes:return '已取消'
            subprocess.Popen(args,cwd=str(tool['root']),shell=False);return '已请求运行，请在目标程序中确认。'
        if action['type']=='copy':
            directory=QFileDialog.getExistingDirectory(self,'选择工具文件的安装目录')
            return copy_action(tool,action,directory) if directory else '已取消'
        if action['type']=='openFolder':os.startfile(str(tool['root']));return '已打开工具目录'
        raise ValueError('未知操作')
