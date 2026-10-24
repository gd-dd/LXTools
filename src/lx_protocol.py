"""LX repository protocol v2. No DCC- or engine-specific behavior."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

MARKER = '.lxtool/manifest.json'
MAX_FILE_BYTES = 64 * 1024 * 1024
RESERVED = {'CON','PRN','AUX','NUL', *('COM'+str(i) for i in range(10)), *('LPT'+str(i) for i in range(10))}


def safe_path(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or value.startswith('/'):
        raise ValueError('资源必须使用包内相对路径')
    if any(p in ('','.','..') or p.endswith((' ','.')) or p.split('.')[0].upper() in RESERVED for p in value.split('/')):
        raise ValueError('资源路径无效')
    return value


def text(value, limit, field):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError(field+' 必须是非空文本，长度不超过 '+str(limit))


def validate_manifest(m):
    if not isinstance(m,dict) or m.get('schemaVersion')!=2 or m.get('kind')!='lx-tool':
        raise ValueError('缺少有效 LX 工具声明（schemaVersion=2, kind=lx-tool）')
    text(m.get('name'),20,'name');text(m.get('description'),160,'description')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',m.get('version','')) or m['version'].endswith('.'):
        raise ValueError('工具版本无效')
    for field in ('icon','readme','panel'):safe_path(m.get(field))
    if not m['icon'].lower().endswith(('.png','.jpg','.jpeg','.webp')):raise ValueError('图标必须是 PNG/JPEG/WebP 图片')
    if not m['readme'].lower().endswith('.md'):raise ValueError('介绍文件必须是 Markdown')
    files=m.get('files')
    if not isinstance(files,dict) or not 3<=len(files)<=2000:raise ValueError('files 必须列出 3–2000 个文件的 SHA-256')
    seen=set()
    for path,digest in files.items():
        safe_path(path)
        if path.lower() in seen or path==MARKER or path.lower()=='tool.json':raise ValueError('文件路径重复或使用客户端保留名称')
        seen.add(path.lower())
        if not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('文件摘要必须是小写 SHA-256')
    if any(m[k] not in files for k in ('icon','readme','panel')):raise ValueError('files 必须包含图标、介绍和面板')
    apps=m.get('applications',{})
    if not isinstance(apps,dict):raise ValueError('applications 必须是对象')
    for key,app in apps.items():
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,40}',key) or not isinstance(app,dict):raise ValueError('软件配置无效')
        text(app.get('name'),60,'application.name')
        exe=app.get('executable','')
        safe_path(exe)
        if '/' in exe or not exe.lower().endswith('.exe'):raise ValueError('executable 必须是 EXE 文件名')
        if 'compatibility' in app:
            from compatibility import compatibility_state
            compatibility_state(app['compatibility'],'2026.3')
    actions=m.get('actions',{})
    if not isinstance(actions,dict) or len(actions)>100:raise ValueError('actions 必须是操作对象，最多 100 项')
    for key,action in actions.items():
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,50}',key) or not isinstance(action,dict):raise ValueError('操作 ID 无效')
        kind=action.get('type')
        if kind=='process':
            if ('application' in action)==('executable' in action):raise ValueError('进程操作指定 application 或包内 executable 之一')
            if 'application' in action and action['application'] not in apps:raise ValueError('操作引用未知软件')
            if 'executable' in action:
                if safe_path(action['executable']) not in files or not action['executable'].lower().endswith('.exe'):raise ValueError('包内程序必须是列入 files 的 EXE')
            args=action.get('arguments',[])
            if not isinstance(args,list) or len(args)>100 or any(not isinstance(a,str) or len(a)>4096 for a in args):raise ValueError('arguments 必须是字符串数组')
            for arg in args:
                if arg.startswith('{file:') and arg.endswith('}') and arg[6:-1] not in files:raise ValueError('操作引用未列入包清单的文件')
                if '{' in arg and not (arg.startswith('{file:') and arg.endswith('}') and arg[6:-1] in files):raise ValueError('不支持的参数占位符')
        elif kind=='copy':
            selected=action.get('files')
            if not isinstance(selected,list) or not selected or any(p not in files for p in selected):raise ValueError('复制操作必须指定包清单中的文件')
            safe_path(action.get('destinationFolder',''))
        elif kind!='openFolder':raise ValueError('不支持的通用操作类型')
    return m


def validate_panel(panel,manifest):
    if not isinstance(panel,dict) or panel.get('type') not in ('none','declarative','native'):raise ValueError('面板类型必须是 none、declarative 或 native')
    if panel['type']=='native':
        if set(panel)!={'type','apiVersion','entry'}:raise ValueError('原生面板字段必须为 type、apiVersion、entry')
        if type(panel['apiVersion']) is not int or panel['apiVersion']!=1:raise ValueError('不支持的原生面板 API，请更新工具架')
        entry=safe_path(panel['entry'])
        if not entry.endswith('.py') or entry not in manifest['files']:raise ValueError('原生入口必须是 files 中的 Python 文件')
        return panel
    if panel['type']=='none':
        if set(panel)!={'type'}:raise ValueError('无面板模式不能包含内容')
        return panel
    if set(panel)-{'type','title','accent','sections','session'}:raise ValueError('面板包含未知字段')
    if 'title' in panel:text(panel['title'],120,'panel.title')
    if 'accent' in panel and not re.fullmatch(r'#[0-9a-fA-F]{6}',panel['accent']):raise ValueError('强调色应为 #RRGGBB')
    if 'session' in panel:
        session=panel['session']
        if not isinstance(session,dict) or set(session)-{'provider','application','subtitle','launchLabel','tools'}:raise ValueError('会话面板配置无效')
        action=manifest.get('actions',{}).get(session.get('provider'),{})
        if action.get('type')!='process' or 'executable' not in action:raise ValueError('会话提供者必须是包内进程')
        if session.get('application') not in manifest.get('applications',{}):raise ValueError('会话引用未知软件')
        for field in ('subtitle','launchLabel'):
            if field in session:text(session[field],160,field)
        tools=session.get('tools')
        if not isinstance(tools,list) or not 1<=len(tools)<=40:raise ValueError('会话工具应有 1–40 项')
        seen=set()
        for item in tools:
            if not isinstance(item,dict) or set(item)-{'id','label','description','group'}:raise ValueError('会话工具字段无效')
            identity=item.get('id','')
            if not isinstance(identity,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,50}',identity) or identity in seen:raise ValueError('会话工具 ID 无效或重复')
            seen.add(identity);text(item.get('label'),60,'session.tool.label')
            for field in ('description','group'):
                if field in item:text(item[field],120,field)
    sections=panel.get('sections',[] if 'session' in panel else None)
    if not isinstance(sections,list) or not (0 if 'session' in panel else 1)<=len(sections)<=30:raise ValueError('面板应有 1–30 个分组')
    for section in sections:
        if not isinstance(section,dict) or set(section)-{'title','text','actions'} or not section:raise ValueError('面板分组无效')
        for field in ('title','text'):
            if field in section:text(section[field],2000,field)
        actions=section.get('actions',[])
        if not isinstance(actions,list) or len(actions)>20:raise ValueError('每组最多 20 个按钮')
        for a in actions:
            if not isinstance(a,dict) or set(a)-{'action','label'} or a.get('action') not in manifest.get('actions',{}):raise ValueError('面板引用未知操作')
            text(a.get('label'),80,'action.label')
    return panel


def checked_bytes(data,digest):
    if len(data)>MAX_FILE_BYTES or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('工具资源摘要校验失败或文件过大')
    return data


def package_key(tool):return tool['version']


def compatibility_label(tool):
    requirements=[]
    for app in tool.get('applications',{}).values():
        value=app.get('compatibility',{}).get('range')
        requirements.append(app['name']+(' · '+value.replace('unverified','待验证') if value else ''))
    return '；'.join(requirements) or '无外部软件要求'


def discover_packages(root):
    tools,errors=[],[];root=Path(root).resolve()
    receipts = set(root.glob('repo-*/*/tool.json')) | set(root.glob('*/versions/*/tool.json'))
    for receipt in sorted(receipts):
        try:
            saved=json.loads(receipt.read_text('utf-8'))
            package=receipt.parent.resolve()
            if not package.is_relative_to(root):raise ValueError('安装目录越界')
            m=validate_manifest(json.loads((package/MARKER).read_text('utf-8')))
            folder = receipt.parent.parent
            identity = saved.get('id', '')
            valid_folder = (folder.parent.name.endswith('--' + identity.removeprefix('repo-'))
                            if folder.name == 'versions' else folder.name == identity)
            if not re.fullmatch(r'repo-[0-9]+', identity) or not valid_folder or saved.get('version')!=m['version'] or receipt.parent.name!=m['version']:raise ValueError('安装收据身份不一致')
            for path,digest in m['files'].items():
                file=(package/path).resolve()
                if not file.is_relative_to(package):raise ValueError('文件越界')
                checked_bytes(file.read_bytes(),digest)
            panel=validate_panel(json.loads((package/m['panel']).read_text('utf-8')),m)
            tools.append(dict(m,id=saved['id'],repository=saved['repository'],root=package,panelData=panel))
        except Exception as error:errors.append(str(receipt)+': '+str(error))
    return tools,errors
