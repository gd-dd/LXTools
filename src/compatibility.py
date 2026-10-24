import re


def host_version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}(?:\.\d+){0,2}', value):
        raise ValueError('软件版本应为 2026.3 或 2026.3.1 等数字格式')
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (3 - len(parts))


def compatibility_state(compatibility, selected):
    current = host_version(selected)
    if not compatibility or compatibility.get('range') == 'unverified':
        return 'unverified'
    name = compatibility.get('range', '')
    parts = name.split('~')
    if len(parts) != 2:
        raise ValueError('兼容范围格式应为 2024.1~2026.3')
    lower, upper = map(host_version, parts)
    if lower > upper:
        raise ValueError('兼容范围起始版本不能高于结束版本')
    if not lower <= current <= upper:
        return 'incompatible'
    tested = compatibility.get('testedVersions', [])
    if not isinstance(tested, list):
        raise ValueError('testedVersions 应为版本列表')
    return 'tested' if current in [host_version(v) for v in tested] else 'declared'


LABELS = {'unverified': '兼容性待验证', 'incompatible': '不支持所选软件版本', 'declared': '范围内 · 尚无此版本实测记录', 'tested': '此软件版本已实测'}
