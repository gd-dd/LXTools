"""Source-only development support; never changes the Release catalog."""
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError

from lx_protocol import MARKER, validate_manifest, validate_panel, MAX_FILE_BYTES


def enabled():
    return not getattr(sys, 'frozen', False) and '--dev' in sys.argv


def fingerprint(project):
    project = Path(project)
    paths = list((project / 'src').rglob('*.py')) + list((project / 'assets').rglob('*.png'))
    result = []
    for path in sorted(set(paths)):
        try:
            stat = path.stat()
            result.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            result.append((str(path), None, None))
    return tuple(result)


def scan_branches(token=None):
    from github_api import github_json
    from repository_source import read_json, read_bytes, visual_assets, entry_for
    entries, warnings = [], []
    page = 1
    while True:
        repos = github_json(f'/users/gd-dd/repos?per_page=100&page={page}', token)
        for repo in repos:
            if repo['name'] == 'LXTools' or repo.get('archived'):
                continue
            try:
                repository = repo['full_name']
                validate_manifest(read_json(repository, MARKER, repo['default_branch'], token))
                # Resolve once; every resource must come from this immutable commit.
                from urllib.parse import quote
                commit = github_json(f'/repos/{repository}/commits/{quote(repo["default_branch"],safe="")}', token)['sha']
                original = validate_manifest(read_json(repository, MARKER, commit, token))
                manifest = dict(original, version='0.0.0', files=dict(original['files']))
                payload = {original[k]: read_bytes(repository, original[k], commit, token) for k in ('icon', 'readme', 'panel')}
                for path, data in payload.items():
                    manifest['files'][path] = hashlib.sha256(data).hexdigest()
                assets = visual_assets(manifest, lambda p: payload[p])
                entry = entry_for(repo['id'], repository, manifest, '', commit, assets)
                entry.update(distribution='github-branch', branch=repo['default_branch'],
                             sourceManifest=original, notes='GitHub 默认分支 '+repo['default_branch']+' · '+commit[:12]+'。未正式发布的开发快照；未提交的编译文件仅在摘要匹配时从对应 Release 补齐。', publishedAt='最新分支')
                entries.append(entry)
            except HTTPError as error:
                if error.code != 404:warnings.append(repo['name']+': '+str(error))
            except Exception as error:
                warnings.append(repo['name']+': '+str(error))
        if len(repos) < 100:break
        page += 1
    return entries, warnings


def install_branch(entry, destination, token=None):
    if not enabled():raise ValueError('只有源码开发版可以安装分支快照')
    import re
    import tempfile
    import shutil
    from repository_source import read_json, read_bytes, visual_assets, release_asset, download_release_asset, unpack_release
    from github_api import github_json
    from tool_storage import repository_folder
    from library import write_json
    if (entry.get('distribution') != 'github-branch' or entry.get('version') != '0.0.0'
            or not re.fullmatch(r'gd-dd/[A-Za-z0-9_.-]+', entry['repository'])
            or entry['id'] != 'repo-'+str(entry['repositoryId'])
            or not re.fullmatch(r'[a-f0-9]{40}', entry['commit'])):
        raise ValueError('分支快照身份无效')
    repository, commit = entry['repository'], entry['commit']
    original = validate_manifest(read_json(repository, MARKER, commit, token))
    if original != entry['sourceManifest']:raise ValueError('分支清单与扫描结果不一致，请重新扫描')
    manifest = dict(original, version='0.0.0', files={})
    destination = Path(destination).resolve();destination.mkdir(parents=True, exist_ok=True)
    target = (repository_folder(destination, entry)/'versions/0.0.0').resolve()
    if not target.is_relative_to(destination):raise ValueError('安装路径越界')
    staging = Path(tempfile.mkdtemp(prefix='.branch-', dir=destination))
    backup = staging.parent/(staging.name+'-previous')
    committed = False
    try:
        total = 0
        release_files = None
        supplemented = []
        for path in original['files']:
            try:
                data = read_bytes(repository, path, commit, token)
            except HTTPError as error:
                if error.code != 404 or Path(path).suffix.lower() not in ('.exe','.dll','.pyd'):
                    raise ValueError('分支缺少文件：'+path) from error
                # Git-ignored compiled outputs may live in the corresponding Release.
                # Require the exact digest declared by this branch, never substitute latest.
                if release_files is None:
                    if token:
                        release=github_json(f'/repos/{repository}/releases/tags/v{original["version"]}',token)
                        if release.get('draft') or release.get('prerelease') or release['tag_name']!='v'+original['version']:
                            raise ValueError('缺少与分支清单匹配的编译文件 Release')
                        payload=download_release_asset(repository,release_asset(release),token)
                    else:
                        from urllib.request import Request, urlopen
                        from urllib.parse import quote
                        url=f'https://github.com/{repository}/releases/download/v{quote(original["version"],safe="")}/LXTool-package.zip'
                        with urlopen(Request(url,headers={'User-Agent':'LXTool'}),timeout=60) as response:
                            payload=response.read(512*1024*1024+1)
                        if len(payload)>512*1024*1024:raise ValueError('编译附件超过大小限制')
                    release_files=unpack_release(payload)
                data=release_files.get(path,b'')
                if not data or hashlib.sha256(data).hexdigest()!=original['files'][path]:
                    raise ValueError('分支缺少编译文件且 Release 摘要不匹配：'+path)
                supplemented.append(path)
            total += len(data)
            if total > 512*1024*1024:raise ValueError('快照超过 512 MiB')
            manifest['files'][path] = hashlib.sha256(data).hexdigest()
            output=staging/path;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
        validate_manifest(manifest)
        visual_assets(manifest, lambda p:(staging/p).read_bytes())
        write_json(staging/MARKER, manifest)
        write_json(staging/'tool.json', dict(id=entry['id'], repository=repository, repositoryId=entry['repositoryId'],
                   version='0.0.0', commit=commit, distribution='github-branch', branch=entry['branch'],releaseSupplement=supplemented))
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():os.replace(target,backup)
        try:os.replace(staging,target)
        except Exception:
            if backup.exists():os.replace(backup,target)
            raise
        committed = True
        return str(target)
    finally:
        for temporary in ([staging,backup] if committed else [staging]):
            if temporary.exists() and temporary.resolve().is_relative_to(destination):shutil.rmtree(temporary)
