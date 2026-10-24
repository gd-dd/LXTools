"""Current user library: Chinese folders, assignments and uninstall."""
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    os.replace(temporary, path)


def resource_path(path):
    return (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / path


class Library:
    def __init__(self, root, tools_root):
        self.path = Path(root) / 'library.json'
        self.tools_root = Path(tools_root).resolve()
        self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'folders': {}, 'assignments': {}}

    def save(self):
        write_json(self.path, self.data)

    def folder_name(self, name, excluding=None):
        name = name.strip()
        if not name or len(name) > 40 or any(ord(c) < 32 for c in name):
            raise ValueError('夹子名称请使用 1–40 个可见字符')
        if any(value == name and key != excluding for key, value in self.data['folders'].items()):
            raise ValueError('已有同名夹子')
        return name

    def create_folder(self, name):
        name = self.folder_name(name)
        key = uuid.uuid4().hex
        self.data['folders'][key] = name
        self.save()
        return key

    def rename_folder(self, key, name):
        if key not in self.data['folders']:
            raise ValueError('夹子不存在')
        self.data['folders'][key] = self.folder_name(name, key)
        self.save()

    def remove_folder(self, key):
        self.data['folders'].pop(key, None)
        self.data['assignments'] = {k: v for k, v in self.data['assignments'].items() if v != key}
        self.save()

    def move(self, identity, folder):
        if folder is not None and folder not in self.data['folders']:
            raise ValueError('夹子不存在')
        if folder is None:
            self.data['assignments'].pop(identity, None)
        else:
            self.data['assignments'][identity] = folder
        self.save()

    def uninstall(self, tool):
        target = Path(tool['root']).resolve()
        if target == self.tools_root or not target.is_relative_to(self.tools_root) or not (target / 'tool.json').is_file():
            raise ValueError('拒绝卸载工具目录之外的文件')
        trash = self.tools_root / ('.removed-' + uuid.uuid4().hex)
        os.replace(target, trash)
        try:
            shutil.rmtree(trash)
        except Exception:
            if trash.exists():
                os.replace(trash, target)
            raise
