"""Author-owned catalog and user-owned library organization."""
import base64
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import quote
from tool_source import github_json
from compatibility import compatibility_state
from panel_spec import panel_for

CATALOG_REPOSITORY = 'gd-dd/LXTools'


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    os.replace(temporary, path)


def resource_path(path):
    return (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / path


def read_remote(repository, path, commit, token=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('作者目录包含无效仓库')
    if path.startswith('/') or '\\' in path or any(p in ('', '.', '..') for p in path.split('/')):
        raise ValueError('作者目录包含无效路径')
    data = github_json(f'/repos/{repository}/contents/{quote(path, safe="/")}?ref={commit}', token)
    if data.get('encoding') != 'base64':
        raise ValueError('目录文件编码不支持')
    return json.loads(base64.b64decode(data['content']))


def validate_catalog(data):
    if not isinstance(data, dict) or data.get('schemaVersion') != 1 or not isinstance(data.get('sources'), list) or not isinstance(data.get('packages'), list):
        raise ValueError('作者目录格式无效')
    if any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', s) for s in data['sources']):
        raise ValueError('作者来源无效')
    seen = set()
    for entry in data['packages']:
        if not isinstance(entry, dict):
            raise ValueError('工具条目无效')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', entry.get('id', '')):
            raise ValueError('工具 ID 无效')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', entry.get('version', '')) or entry['version'].endswith('.'):
            raise ValueError('工具版本无效')
        if entry.get('repository') not in data['sources'] or entry.get('host') != '3dsmax':
            raise ValueError('工具来源或宿主无效')
        for field in ('name','description'):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError('工具缺少名称或说明')
        compatibility_state(entry.get('compatibility'), '2026.3')
        compatible = entry['compatibility']['range']
        if entry.get('manifest') != f"releases/{compatible}/{entry['version']}/{entry['id']}/tool.json":
            raise ValueError('工具目录与标识不一致')
        key = (entry['id'], entry['version'], compatible)
        if key in seen:
            raise ValueError('目录包含重复工具版本')
        seen.add(key)
    return data


class AuthorCatalog:
    def __init__(self, root):
        self.cache = Path(root) / 'author-catalog.json'
        self.data = validate_catalog(json.loads(resource_path('catalog/store.json').read_text('utf-8')))
        self.cached = False
        if self.cache.exists():
            try:
                self.data = validate_catalog(json.loads(self.cache.read_text('utf-8')))
                self.cached = True
            except (ValueError, KeyError, TypeError):
                pass

    def sync(self, token=None):
        # Only this author's directory can introduce repositories; no user repository picker.
        revision = github_json(f'/repos/{CATALOG_REPOSITORY}/commits/HEAD', token)['sha']
        try:
            authority = validate_catalog(read_remote(CATALOG_REPOSITORY, 'catalog/store.json', revision, token))
        except Exception as error:
            # Until the new directory is published, retain the bundled author source list.
            from urllib.error import HTTPError
            if not isinstance(error, HTTPError) or error.code != 404:
                raise
            authority = self.data
        packages = []
        previous = {e['id']: e for e in authority['packages']}
        for repository in authority['sources']:
            commit = github_json(f'/repos/{repository}/commits/HEAD', token)['sha']
            index = read_remote(repository, 'tools-index.json', commit, token)
            if index.get('schemaVersion') != 1 or not isinstance(index.get('packages'), list):
                raise ValueError('工具源索引格式无效')
            for entry in index['packages']:
                manifest = read_remote(repository, entry['manifest'], commit, token)
                panel_for(manifest)
                if manifest.get('compatibility') != entry.get('compatibility'):
                    raise ValueError('索引兼容性不一致')
                metadata = previous.get(manifest['id'], {})
                package = {k: manifest[k] for k in ('id', 'name', 'description', 'host', 'version', 'compatibility')}
                package.update(repository=repository, manifest=entry['manifest'], commit=commit,
                               category=manifest.get('category', metadata.get('category', '实用工具')),
                               notes=manifest.get('releaseNotes', metadata.get('notes', '作者未提供此版本的更新说明。')),
                               publishedAt=manifest.get('publishedAt', ''))
                packages.append(package)
        result = validate_catalog({'schemaVersion': 1, 'sources': authority['sources'], 'packages': packages})
        write_json(self.cache, result)
        return result


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

