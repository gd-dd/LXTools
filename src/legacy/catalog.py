"""Historical v1 catalog, retained only for regression tests."""
import base64
import json
import re
from urllib.parse import quote
from library import write_json,resource_path
from github_api import github_json
from compatibility import compatibility_state
from legacy.panel_spec import panel_for
from pathlib import Path
CATALOG_REPOSITORY="gd-dd/LXTools"

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
        self.data = validate_catalog(json.loads(resource_path('archive/catalog-v1/store.json').read_text('utf-8')))
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


