"""Discover LX repositories and install their declared packages; owner is fixed."""
import base64
import hashlib
import io
import re
import zipfile
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from PySide6.QtGui import QImage
from github_api import github_json, github_commit_sha, http_error_message, AuthenticationExpired, authenticated_error
from http_transport import get_bytes,read_get,TransferFailed,open_https,notify_progress
from core import NoRedirect
from library import write_json,resource_path
from lx_protocol import MARKER,validate_manifest,validate_panel,safe_path,checked_bytes
from tool_storage import migrate_repository

OWNER='gd-dd'


def read_bytes(repository,path,ref,token=None,limit=64*1024*1024):
    safe_path(path)
    def api_read(fallback=False):
        endpoint=f'/repos/{repository}/contents/{urllib.parse.quote(path,safe="/")}?ref={urllib.parse.quote(ref,safe="")}'
        data=github_json(endpoint,token,attempts=1) if fallback else github_json(endpoint,token)
        if data.get('encoding')!='base64':raise ValueError('仓库文件编码不支持')
        return base64.b64decode(data['content'])
    if token:
        result=api_read()
    else:
        url='https://raw.githubusercontent.com/'+repository+'/'+urllib.parse.quote(ref,safe='')+'/'+urllib.parse.quote(path,safe='/')
        try:result=get_bytes(lambda:urllib.request.Request(url,headers={'User-Agent':'LXTool'}),stage='读取工具清单/资源',max_bytes=limit,timeout=15,attempts=2)
        except TransferFailed:
            # Preserve raw-domain fallback without exceeding 3 total GETs.
            notify_progress('读取工具清单/资源：通过 GitHub API 获取同一提交（第 3/3 次）…')
            try:result=api_read(fallback=True)
            except TransferFailed as error:raise TransferFailed('读取工具清单/资源（raw 与 API）',3,error) from None
    if len(result)>limit:raise ValueError('工具资源超过大小限制')
    return result


def read_json(repository,path,ref,token=None):return json.loads(read_bytes(repository,path,ref,token,2*1024*1024))


def visual_assets(m,reader):
    icon=checked_bytes(reader(m['icon']),m['files'][m['icon']])
    image=QImage.fromData(icon)
    if image.isNull() or image.width()>1024 or image.height()>1024 or len(icon)>2*1024*1024:raise ValueError('图标必须是有效图片，最大 1024×1024 / 2 MiB')
    readme=checked_bytes(reader(m['readme']),m['files'][m['readme']])
    if len(readme)>256*1024:raise ValueError('Markdown 介绍超过 256 KiB')
    panel_bytes=checked_bytes(reader(m['panel']),m['files'][m['panel']])
    panel=validate_panel(json.loads(panel_bytes),m)
    return {'iconData':base64.b64encode(icon).decode(),'readmeText':readme.decode('utf-8-sig'),'panelData':panel,
            'readmeData':base64.b64encode(readme).decode(),'panelBytes':base64.b64encode(panel_bytes).decode()}


def entry_for(repo_id,repository,m,prefix,commit,assets):
    return dict(m,id='repo-'+str(repo_id),repositoryId=repo_id,repository=repository,packagePath=prefix,commit=commit,
                manifestData=m,notes=m.get('releaseNotes','作者未提供更新说明。'),**assets)


PACKAGE_ASSET='LXTool-package.zip'
MAX_PACKAGE=512*1024*1024


def release_asset(release):
    assets=[a for a in release.get('assets',[]) if a['name']==PACKAGE_ASSET]
    if len(assets)!=1:raise ValueError('Release 缺少唯一的 LXTool-package.zip')
    a=assets[0]
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',a.get('digest') or ''):raise ValueError('附件缺少 SHA256 校验值')
    if not 0<a['size']<=MAX_PACKAGE:raise ValueError('附件大小超限')
    return {k:a[k] for k in ('id','name','size','digest')}


def download_release_asset(repository,asset,token=None,tag=None):
    # Public versioned downloads avoid the REST asset endpoint and its quota.
    # Metadata is still freshly checked by install_repository before this call.
    public = not token and tag is not None
    if public:
        if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',tag):
            raise ValueError('Release 标签无效')
        url=f'https://github.com/{repository}/releases/download/{tag}/{PACKAGE_ASSET}'
    else:
        url=f"https://api.github.com/repos/{repository}/releases/assets/{int(asset['id'])}"
    headers={'User-Agent':'LXTool','Accept':'application/octet-stream','Cache-Control':'no-cache'}
    if token:headers['Authorization']='Bearer '+token
    def open_asset(request,**options):
        try:
            return urllib.request.build_opener(NoRedirect).open(request,**options)
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):raise
            signed_url=error.headers['Location']
            if urllib.parse.urlparse(signed_url).scheme!='https':raise ValueError('附件下载必须使用 HTTPS')
            # Never forward credentials to the signed asset URL.
            return open_https(signed_url,**options)
    try:
        data=get_bytes(lambda:urllib.request.Request(url,headers=headers),stage='下载工具附件',max_bytes=MAX_PACKAGE,expected_size=asset['size'],timeout=60,open_request=open_asset)
    except urllib.error.HTTPError as error:
        if authenticated_error(error,token):raise AuthenticationExpired(token) from None
        raise RuntimeError(http_error_message(error,'下载工具附件')) from error
    if len(data)!=asset['size'] or len(data)>MAX_PACKAGE:raise ValueError('附件大小不匹配')
    return checked_bytes(data,asset['digest'].removeprefix('sha256:'))


def unpack_release(data):
    result={};seen=set();total=0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            name=info.filename
            if info.is_dir():
                safe_path(name.rstrip('/'));continue
            safe_path(name)
            if name.casefold() in seen or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP 路径重复或为符号链接')
            seen.add(name.casefold());total+=info.file_size
            if info.file_size>64*1024*1024 or total>MAX_PACKAGE or len(seen)>2001:raise ValueError('ZIP 解压大小超限')
            result[name]=archive.read(info)
    if MARKER not in result:raise ValueError('ZIP 根目录必须包含 .lxtool/manifest.json')
    return result


INDEX_URL='https://raw.githubusercontent.com/gd-dd/LXTools/main/catalog/repo-store.json'
MAX_INDEX=32*1024*1024


def validate_index(data):
    if not isinstance(data,dict) or data.get('schemaVersion')!=2:raise ValueError('商店索引格式无效')
    packages=data.get('packages')
    if not isinstance(packages,list) or not 1<=len(packages)<=1000:raise ValueError('商店索引为空或数量超限，保留原目录')
    seen=set();repositories={}
    for e in packages:
        if not isinstance(e,dict):raise ValueError('工具条目格式无效')
        m=validate_manifest(e['manifestData'])
        repo_id=e['repositoryId'];repository=e['repository']
        if type(repo_id) is not int or repo_id<=0 or e['id']!='repo-'+str(repo_id):raise ValueError('工具身份无效')
        if not isinstance(repository,str) or not re.fullmatch(OWNER+r'/[A-Za-z0-9_.-]+',repository):raise ValueError('工具作者无效')
        if repositories.setdefault(repo_id,repository)!=repository:raise ValueError('仓库身份冲突')
        if any(k!=repo_id and v==repository for k,v in repositories.items()):raise ValueError('仓库身份重复')
        if not re.fullmatch(r'[a-f0-9]{40}',e['commit']):raise ValueError('提交无效')
        if e.get('distribution')!='github-release' or e['releaseTag']!='v'+m['version'] or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',e['releaseTag']):raise ValueError('仅允许稳定 Release')
        if type(e['releaseId']) is not int or e['releaseId']<=0:raise ValueError('Release 身份无效')
        if type(e['releaseAsset']['id']) is not int or e['releaseAsset']['id']<=0:raise ValueError('附件身份无效')
        release_asset({'assets':[e['releaseAsset']]})
        key=(repo_id,m['version'])
        if key in seen:raise ValueError('版本重复')
        seen.add(key)
        # Release metadata owns these two display fields; original manifest is
        # retained verbatim for source/package comparison during installation.
        if any(e.get(k)!=v for k,v in m.items() if k not in ('publishedAt','notes')) or e.get('packagePath')!='':raise ValueError('目录与工具清单不一致')
        raw={m['icon']:base64.b64decode(e['iconData'],validate=True),m['readme']:base64.b64decode(e['readmeData'],validate=True),m['panel']:base64.b64decode(e['panelBytes'],validate=True)}
        assets=visual_assets(m,raw.__getitem__)
        if any(e.get(k)!=v for k,v in assets.items()):raise ValueError('工具预览内容不一致')
    if not isinstance(data.get('warnings',[]),list) or any(not isinstance(s,str) or len(s)>4096 for s in data.get('warnings',[])):raise ValueError('索引提示无效')
    return data


class RepositoryCatalog:
    def __init__(self,root):
        self.cache=Path(root)/'repository-catalog-v2.json'
        self.data={'schemaVersion':2,'packages':[],'warnings':[]}
        for path in (resource_path('catalog/repo-store.json'),self.cache):
            if path.exists():
                try:
                    if path.stat().st_size>MAX_INDEX:continue
                    data=validate_index(json.loads(path.read_text('utf-8')))
                    self.data=data
                except (ValueError,KeyError,TypeError):pass

    def sync(self,token=None):
        # Public author index never receives an OAuth token. ETag is bound to the
        # exact validated document, persisted atomically in the same cache file.
        headers={'User-Agent':'LXTool','Accept':'application/json'}
        etag=self.data.get('_indexEtag')
        if isinstance(etag,str) and len(etag)<512 and '\n' not in etag and '\r' not in etag:headers['If-None-Match']=etag
        try:
            payload,response_headers=read_get(lambda:urllib.request.Request(INDEX_URL,headers=headers),stage='刷新工具商店',max_bytes=MAX_INDEX,timeout=12)
            data=validate_index(json.loads(payload))
            data.pop('_indexEtag',None)
            fresh_etag=response_headers.get('ETag')
            if fresh_etag:data['_indexEtag']=fresh_etag
        except urllib.error.HTTPError as error:
            if error.code==304 and etag and self.data['packages']:return self.data
            raise
        write_json(self.cache,data)
        self.data=data
        return data

    def scan_author(self,token=None):
        """Explicit author-maintenance operation; never called by stable UI."""
        repos=[];page=1
        while True:
            endpoint=(f'/users/{OWNER}/repos?type=owner&per_page=100&page={page}')
            batch=github_json(endpoint,token)
            if not isinstance(batch,list):raise ValueError('GitHub 仓库列表返回异常')
            repos.extend(r for r in batch if r['owner']['login'].lower()==OWNER)
            if len(batch)<100:break
            page+=1
        packages=[];warnings=[];seen=set()
        for repo in repos:
            repository=repo['full_name'];identity='repo-'+str(repo['id'])
            if identity in seen:continue
            seen.add(identity)
            try:
                # A missing marker is a normal non-tool repository; never clone entire game repos.
                read_json(repository,MARKER,repo['default_branch'],token)
            except urllib.error.HTTPError as error:
                if error.code==404:continue
                warnings.append(repository+'：读取标识失败');packages.extend(e for e in self.data['packages'] if e['id']==identity);continue
            except Exception as error:
                warnings.append(repository+'：'+str(error));packages.extend(e for e in self.data['packages'] if e['id']==identity);continue
            try:
                releases=[];release_page=1
                while True:
                    batch=github_json(f'/repos/{repository}/releases?per_page=100&page={release_page}',token)
                    if not isinstance(batch,list):raise ValueError('Release 列表返回异常')
                    releases.extend(batch)
                    if len(batch)<100:break
                    release_page+=1
                versions=set();found=[]
                for release in releases:
                    if release.get('draft') or release.get('prerelease'):continue
                    try:
                        tag=release['tag_name']
                        if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',tag):continue
                        asset=release_asset(release)
                        commit=github_commit_sha(repository,'tags/'+tag,token)
                        m=validate_manifest(read_json(repository,MARKER,commit,token))
                        if tag!='v'+m['version'] or m['version'] in versions:raise ValueError('Release 标签与工具版本不一致或重复')
                        assets=visual_assets(m,lambda p:read_bytes(repository,p,commit,token))
                        e=entry_for(repo['id'],repository,m,'',commit,assets)
                        e.update(distribution='github-release',releaseId=release['id'],releaseTag=tag,releaseAsset=asset,
                                 notes=release.get('body') or m.get('releaseNotes',''),publishedAt=release.get('published_at',''))
                        found.append(e);versions.add(m['version'])
                    except Exception as error:
                        warnings.append(repository+' / '+str(release.get('tag_name',''))+'：'+str(error))
                packages.extend(found)
            except Exception as error:
                warnings.append(repository+'：'+str(error))
                packages.extend(e for e in self.data['packages'] if e['id']==identity)
        data={'schemaVersion':2,'packages':packages,'warnings':warnings,'scannedRepositories':len(seen),'detectedRepositories':len({e['id'] for e in packages})}
        return validate_index(data)


def install_repository(entry,destination,token=None):
    if not entry['repository'].startswith(OWNER+'/') or entry['id']!='repo-'+str(entry['repositoryId']):raise ValueError('工具来源身份无效')
    import re
    if not re.fullmatch(r'[a-f0-9]{40}',entry['commit']):raise ValueError('下载必须固定到提交')
    if entry.get('distribution')!='github-release':raise ValueError('仅支持 GitHub Release 工具包，请重新扫描')
    release=github_json(f"/repos/{entry['repository']}/releases/{int(entry['releaseId'])}",token)
    if release.get('draft') or release.get('prerelease') or release['tag_name']!=entry['releaseTag']:raise ValueError('Release 状态已变化，请重新扫描')
    asset=release_asset(release)
    if asset!=entry['releaseAsset']:raise ValueError('Release 附件已变化，请重新扫描')
    commit=github_commit_sha(entry['repository'],'tags/'+entry['releaseTag'],token)
    if commit!=entry['commit']:raise ValueError('Release 标签提交已变化，请刷新商店')
    source=validate_manifest(read_json(entry['repository'],MARKER,commit,token))
    if source!=entry['manifestData'] or entry['releaseTag']!='v'+source['version']:raise ValueError('Release 源码清单已变化，请刷新商店')
    payload=download_release_asset(entry['repository'],asset,token,tag=entry['releaseTag'])
    files=unpack_release(payload)
    read=lambda path:files[path]
    m=validate_manifest(json.loads(read(MARKER)))
    if m!=entry['manifestData']:raise ValueError('包清单与 Release 标签源码不一致')
    if set(files)!={MARKER,*m['files']}:raise ValueError('ZIP 包必须只包含 manifest 和声明文件')
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    target=(migrate_repository(destination,entry)/'versions'/m['version']).resolve()
    if not target.is_relative_to(destination):raise ValueError('版本目录越界')
    staging=Path(tempfile.mkdtemp(prefix='.download-',dir=destination))
    try:
        total=0
        for path,digest in m['files'].items():
            data=checked_bytes(read(path),digest);total+=len(data)
            if total>512*1024*1024:raise ValueError('工具包超过 512 MiB')
            file=staging/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
        visual_assets(m,lambda p:(staging/p).read_bytes())
        marker=staging/MARKER;marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text(json.dumps(m,ensure_ascii=False,indent=2),'utf-8')
        receipt={'id':entry['id'],'repository':entry['repository'],'repositoryId':entry['repositoryId'],'version':m['version'],'commit':entry['commit']}
        write_json(staging/'tool.json',receipt)
        if target.exists():
            for path in [MARKER,*m['files']]:
                if not (target/path).is_file() or (target/path).read_bytes()!=(staging/path).read_bytes():raise ValueError('本地同版本内容不同，保留原文件；请作者发布新版本')
        else:
            target.parent.mkdir(parents=True,exist_ok=True);os.replace(staging,target)
        return str(target)
    finally:
        if staging.exists() and staging.resolve().is_relative_to(destination):shutil.rmtree(staging)
