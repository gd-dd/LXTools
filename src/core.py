import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
import copy
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ToolStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.file = self.root / 'state.json'
        self.state = json.loads(self.file.read_text('utf-8')) if self.file.exists() else {'tools': []}
        self.tokens = {}  # Session only: credentials never enter the state file.

    def save(self):
        temp = self.file.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(temp, self.file)

    def tool(self, tool_id):
        tool = next((t for t in self.state['tools'] if t['id'] == tool_id), None)
        if tool is None:
            raise ValueError('工具不存在')
        return tool

    def add(self, repo, category):
        repo = repo.strip().removeprefix('https://github.com/').rstrip('/')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            raise ValueError('仓库格式应为 owner/repo')
        if category not in ('3ds Max', 'Unity', '通用工具'):
            raise ValueError('未知分类')
        if any(t['repo'].lower() == repo.lower() for t in self.state['tools']):
            raise ValueError('此仓库已经添加')
        tool_id = hashlib.sha256(repo.lower().encode()).hexdigest()[:20]
        self.state['tools'].append(dict(id=tool_id, repo=repo, category=category, versions=[], active=None))
        try:
            self.save()
        except Exception:
            self.state['tools'].pop()
            raise

    def request(self, tool, path, binary=False):
        headers = {'User-Agent': 'LXTool-Prototype', 'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json'}
        token = self.tokens.get(tool['id'])
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request('https://api.github.com' + path, headers=headers)
        try:
            return urllib.request.build_opener(NoRedirect).open(req, timeout=60)
        except urllib.error.HTTPError as err:
            if binary and err.code in (301, 302, 303, 307, 308):
                url = err.headers['Location']
                if not url.startswith('https://'):
                    raise ValueError('拒绝非 HTTPS 下载地址')
                # Signed download URL gets no Authorization header.
                return urllib.request.urlopen(url, timeout=60)
            messages = {401: '凭据无效或已过期', 403: '权限不足或 GitHub 限流，请稍后重试', 404: '仓库或资源不存在，或当前账号无访问权限', 429: 'GitHub 限流，请稍后重试'}
            raise ValueError(messages.get(err.code, 'GitHub 请求失败：' + str(err.code))) from None

    def releases(self, tool_id):
        tool = self.tool(tool_id)
        result = []
        for page in range(1, 11):
            with self.request(tool, f"/repos/{tool['repo']}/releases?per_page=100&page={page}") as response:
                batch = json.load(response)
            result.extend(batch)
            if len(batch) < 100:
                break
        return [{'tag': r['tag_name'], 'prerelease': r['prerelease'], 'assets': [{'id': a['id'], 'name': a['name'], 'size': a['size']} for a in r['assets'] if a['name'].lower().endswith('.zip')]} for r in result if not r['draft']]

    def install(self, tool_id, asset_id):
        tool = self.tool(tool_id)
        with self.request(tool, f"/repos/{tool['repo']}/releases/assets/{int(asset_id)}") as response:
            asset = json.load(response)
        if not asset['name'].lower().endswith('.zip') or asset['size'] > 512 * 1024 * 1024:
            raise ValueError('原型只支持不超过 512 MB 的 ZIP 附件')
        release = next((r for r in self.releases(tool_id) if any(a['id'] == asset['id'] for a in r['assets'])), None)
        if not release:
            raise ValueError('无法定位附件所属版本')
        key = str(asset['id'])
        if any(v['key'] == key for v in tool['versions']):
            raise ValueError('该附件已经安装')
        parent = self.root / 'packages' / tool_id
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='staging-', dir=parent))
        try:
            archive = staging / 'download.zip'
            digest = hashlib.sha256()
            total = 0
            with self.request(tool, f"/repos/{tool['repo']}/releases/assets/{asset['id']}", True) as response, archive.open('wb') as out:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 512 * 1024 * 1024:
                        raise ValueError('下载超出大小限制')
                    digest.update(chunk)
                    out.write(chunk)
            if total != asset['size']:
                raise ValueError('下载不完整')
            expected = asset.get('digest')
            actual = 'sha256:' + digest.hexdigest()
            if expected and expected != actual:
                raise ValueError('附件哈希校验失败')
            unpack = staging / 'content'
            unpack.mkdir()
            safe_extract(archive, unpack)
            target = parent / key
            os.replace(unpack, target)
            tool['versions'].append(dict(key=key, tag=release['tag'], name=asset['name'], sha256=actual, verified=bool(expected)))
            try:
                self.save()
            except Exception:
                tool['versions'].pop()
                shutil.rmtree(target)
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def activate(self, tool_id, key):
        tool = self.tool(tool_id)
        if not any(v['key'] == key for v in tool['versions']):
            raise ValueError('版本未安装')
        if not (self.root / 'packages' / tool_id / key).is_dir():
            raise ValueError('版本目录已丢失')
        previous = tool['active']
        tool['active'] = key
        try:
            self.save()
        except Exception:
            tool['active'] = previous
            raise

    def uninstall(self, tool_id, key):
        tool = self.tool(tool_id)
        if tool['active'] == key:
            raise ValueError('请先切换到其他版本后再卸载当前版本')
        version = next((v for v in tool['versions'] if v['key'] == key), None)
        if version is None:
            raise ValueError('版本未安装')
        parent = self.root / 'packages' / tool_id
        target = parent / key
        trash = parent / ('removed-' + key)
        if target.exists():
            os.replace(target, trash)
        index = tool['versions'].index(version)
        tool['versions'].remove(version)
        try:
            self.save()
        except Exception:
            tool['versions'].insert(index, version)
            if trash.exists():
                os.replace(trash, target)
            raise
        shutil.rmtree(trash, ignore_errors=True)

    def import_catalog(self, catalog):
        if not isinstance(catalog, dict) or catalog.get('schemaVersion') != 1 or not isinstance(catalog.get('tools'), list):
            raise ValueError('不支持的目录格式')
        entries = catalog['tools']
        ids, repos = set(), set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('无效目录条目')
            identity, repo = entry.get('id', ''), entry.get('repository', '')
            if not isinstance(identity, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,63}', identity) or identity in ids:
                raise ValueError('工具 ID 无效或重复')
            if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or repo.lower() in repos:
                raise ValueError('仓库格式无效或重复')
            if entry.get('category') not in ('Unity', '3ds Max', '通用工具') or entry.get('delivery') != 'github-release-zip':
                raise ValueError('分类或分发格式不支持')
            if not isinstance(entry.get('name'), str) or not entry['name'].strip():
                raise ValueError('工具名称不能为空')
            ids.add(identity)
            repos.add(repo.lower())
        previous = copy.deepcopy(self.state)
        try:
            for entry in entries:
                repo = entry['repository']
                tool = next((t for t in self.state['tools'] if t['repo'].lower() == repo.lower()), None)
                if not tool:
                    tool = dict(id=hashlib.sha256(repo.lower().encode()).hexdigest()[:20], repo=repo, versions=[], active=None)
                    self.state['tools'].append(tool)
                tool.update(name=entry['name'], category=entry['category'], catalogId=entry['id'])
            self.save()
        except Exception:
            self.state = previous
            raise


def safe_extract(archive, dest):
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 20000 or sum(i.file_size for i in z.infolist()) > 2 * 1024**3:
            raise ValueError('解压体积或文件数量超限')
        seen = set()
        for info in z.infolist():
            name = info.filename.replace('\\', '/')
            parts = name.rstrip('/').split('/')
            if any(p in ('', '.', '..') or ':' in p or p.endswith((' ', '.')) or p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(10)), *('LPT'+str(i) for i in range(10))} for p in parts):
                raise ValueError('ZIP 含不安全路径')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('ZIP 不允许符号链接')
            target = dest.joinpath(*parts)
            normalized = str(target).lower()
            if normalized in seen:
                raise ValueError('ZIP 含重复路径')
            seen.add(normalized)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, target.open('wb') as out:
                    shutil.copyfileobj(source, out)
