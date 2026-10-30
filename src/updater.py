"""Staged self-update; only program files are replaced, local tools are preserved."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from packaging.version import Version, InvalidVersion
from core import ToolStore

VERSION = '0.0.2'


def prepare_update(root, token=None):
    store = ToolStore(Path(root) / 'client-updates')
    if not store.state['tools']:
        store.add('gd-dd/LXTools', '通用工具')
    tool = store.state['tools'][0]
    if token:
        store.tokens[tool['id']] = token
    with store.request(tool, '/repos/gd-dd/LXTools/releases?per_page=100') as response:
        releases = json.load(response)
    candidates = []
    for release in releases:
        try:
            if not release['draft'] and not release['prerelease'] and Version(release['tag_name'].lstrip('v')) > Version(VERSION):
                candidates.append(release)
        except InvalidVersion:
            continue
    if not candidates:
        return None
    latest = max(candidates, key=lambda r: Version(r['tag_name'].lstrip('v')))
    asset = next((a for a in latest['assets'] if a['name'] == 'LXTool-windows-x64.zip'), None)
    if not asset or not (asset.get('digest') or '').startswith('sha256:'):
        raise ValueError('新版本缺少标准更新包或 SHA-256，暂不能更新')
    key = str(asset['id'])
    if not any(v['key'] == key for v in tool['versions']):
        store.install(tool['id'], asset['id'])
    stage = store.root / 'packages' / tool['id'] / key / 'LXTool'
    if not (stage / 'LXTool.exe').is_file() or not (stage / '_internal').is_dir():
        raise ValueError('更新包结构不完整')
    return latest['tag_name'], stage


def replace_program(stage, target):
    stage, target = Path(stage).resolve(), Path(target).resolve()
    if stage == target or stage.is_relative_to(target) or target.is_relative_to(stage):
        raise ValueError('更新目录不能相互包含')
    if not (stage / 'LXTool.exe').is_file() or not (target / 'LXTool.exe').is_file():
        raise ValueError('目标不是 LXTool 安装目录')
    backup = target.parent / ('.lxtool-backup-' + uuid.uuid4().hex)
    backup.mkdir()
    moved, installed = [], []
    try:
        for name in ('LXTool.exe', '_internal'):
            source = stage / name
            if not source.exists():
                raise ValueError('更新缺少程序文件')
            old = target / name
            if old.exists():
                os.replace(old, backup / name)
                moved.append(name)
            installed.append(name)
            if source.is_dir():
                shutil.copytree(source, old)
            else:
                shutil.copy2(source, old)
    except Exception:
        for name in installed:
            current = target / name
            if current.is_dir():
                shutil.rmtree(current)
            elif current.exists():
                current.unlink()
        for name in moved:
            os.replace(backup / name, target / name)
        raise
    return backup


def apply_update(stage, target, pid):
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LXTool'
    root.mkdir(parents=True, exist_ok=True)
    log = root / 'update-result.txt'
    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, int(pid))
        if handle:
            try:
                if kernel.WaitForSingleObject(handle, 60000) != 0:
                    raise ValueError('等待旧版退出超时，未更新')
            finally:
                kernel.CloseHandle(handle)
        backup = replace_program(stage, target)
        log.write_text('更新成功，旧版备份：' + str(backup), 'utf-8')
        subprocess.Popen([str(Path(target) / 'LXTool.exe')], cwd=str(target))
    except Exception as error:
        log.write_text('更新失败：' + str(error), 'utf-8')
        ctypes.windll.user32.MessageBoxW(None, '更新未完成，旧程序已尽可能保留。\n' + str(error), 'LXTool 更新', 0x10)
        return 1
    return 0
