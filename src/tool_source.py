"""Fetch declarative tool packages from a fixed GitHub commit, without executing them."""
import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from compatibility import compatibility_state


def github_json(path, token=None):
    headers = {'User-Agent': 'LXTool', 'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com' + path, headers=headers), timeout=60) as response:
        return json.load(response)


def fetch_packages(repository, destination, selected_host, include_unverified=False, token=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('仓库格式应为 owner/repo')
    base = '/repos/' + repository
    commit = github_json(base + '/commits/HEAD', token)['sha']
    def read(path):
        if path.startswith('/') or any(p in ('', '.', '..') for p in path.split('/')) or '\\' in path:
            raise ValueError('非法源文件路径')
        data = github_json(base + '/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + commit, token)
        if data.get('encoding') != 'base64':
            raise ValueError('源文件过大或编码不支持')
        return base64.b64decode(data['content'])
    index = json.loads(read('tools-index.json'))
    if index.get('schemaVersion') != 1:
        raise ValueError('不支持的工具索引版本')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    installed = []
    for item in index['packages']:
        state = compatibility_state(item.get('compatibility'), selected_host)
        if state == 'incompatible' or (state == 'unverified' and not include_unverified):
            continue
        manifest = json.loads(read(item['manifest']))
        for key in ('id', 'version'):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', manifest.get(key, '')) or manifest[key].endswith('.'):
                raise ValueError('工具标识或版本无效')
        if manifest.get('compatibility') != item.get('compatibility'):
            raise ValueError('索引与工具兼容声明不一致')
        range_name = manifest['compatibility']['range']
        if range_name != 'unverified':
            compatibility_state(manifest['compatibility'], selected_host)
        target = destination / manifest['id'] / range_name / manifest['version']
        prefix = item['manifest'].rsplit('/', 1)[0]
        expected_prefix = f"releases/{range_name}/{manifest['version']}/{manifest['id']}"
        if prefix != expected_prefix:
            raise ValueError('仓库路径与兼容范围或版本不一致')
        staging = Path(tempfile.mkdtemp(prefix='.download-', dir=destination))
        try:
            files = manifest.get('files', {})
            if manifest.get('entry') not in files or not files:
                raise ValueError('工具包缺少入口校验信息')
            for name, digest in files.items():
                if '/' in name or '\\' in name or ':' in name or name in ('.', '..', 'tool.json') or name.endswith(('.', ' ')):
                    raise ValueError('工具资源名称无效')
                data = read(prefix + '/' + name)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError('工具资源校验失败')
                (staging / name).write_bytes(data)
            (staging / 'tool.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
            if target.exists():
                for name in [*files, 'tool.json']:
                    if not (target / name).is_file() or (target / name).read_bytes() != (staging / name).read_bytes():
                        raise ValueError('同版本本地内容不同，已保留，未覆盖：' + str(target))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, target)
            installed.append(manifest['name'])
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return installed

