"""Version-one declarative panels: no executable UI code from packages."""
import re

ACTION_LABELS = {
    'launchHost': '启动 3ds Max',
    'installPlugin': '安装脚本到用户目录',
    'openPluginUI': '启动 Max 并打开此工具 UI',
    'openFolder': '打开工具文件夹',
}


def _text(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name} 必须是非空文本，长度不超过 {limit}')


def validate_panel(panel):
    if not isinstance(panel, dict):
        raise ValueError('panel 必须是对象')
    kind = panel.get('type')
    if kind not in ('none', 'declarative'):
        raise ValueError('panel.type 只支持 none 或 declarative')
    allowed = {'type'} if kind == 'none' else {'type', 'title', 'sections', 'accent'}
    if set(panel) - allowed:
        raise ValueError('panel 含未知字段或无面板模式包含内容')
    if kind == 'none':
        return panel
    if 'accent' in panel and (not isinstance(panel['accent'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', panel['accent'])):
        raise ValueError('panel.accent 必须是 #RRGGBB 颜色')
    if 'title' in panel:
        _text(panel['title'], 'panel.title', 120)
    sections = panel.get('sections')
    if not isinstance(sections, list) or not 1 <= len(sections) <= 20:
        raise ValueError('panel.sections 必须包含 1 至 20 个分组')
    for section in sections:
        if not isinstance(section, dict) or set(section) - {'title', 'text', 'actions'} or not section:
            raise ValueError('面板分组格式无效')
        for key in ('title', 'text'):
            if key in section:
                _text(section[key], key, 120 if key == 'title' else 2000)
        actions = section.get('actions', [])
        if not isinstance(actions, list) or len(actions) > 10:
            raise ValueError('每组最多 10 个操作')
        if not any(k in section for k in ('title', 'text')) and not actions:
            raise ValueError('分组不能为空')
        for action in actions:
            if not isinstance(action, dict) or set(action) - {'action', 'label'}:
                raise ValueError('面板操作格式无效')
            if not isinstance(action.get('action'), str) or action['action'] not in ACTION_LABELS:
                raise ValueError('不支持的面板操作')
            if 'label' in action:
                _text(action['label'], 'label', 120)
    return panel


def panel_for(tool):
    # Old manifests retain their familiar controls; new tools must declare a panel.
    panel = tool.get('panel', {'type': 'declarative', 'sections': [
        {'actions': [{'action': action} for action in ACTION_LABELS]},
        {'text': '将启动新的 Max 实例并打开工具界面。暂不支持在已打开的 Max 实例中呼出。'},
    ]})
    return validate_panel(panel)

