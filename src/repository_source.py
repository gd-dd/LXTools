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
from github_api import github_json
from core import NoRedirect
from library import write_json,resource_path
from lx_protocol import MARKER,validate_manifest,validate_panel,safe_path,checked_bytes
from tool_storage import migrate_repository

OWNER='gd-dd'


def read_bytes(repository,path,ref,token=None,limit=64*1024*1024):
    safe_path(path)
    def api_read():
        data=github_json(f'/repos/{repository}/contents/{urllib.parse.quote(path,safe="/")}?ref={urllib.parse.quote(ref,safe="")}',token)
        if data.get('encoding')!='base64':raise ValueError('仓库文件编码不支持')
        return base64.b64decode(data['content'])
    if token:
        result=api_read()
    else:
        url='https://raw.githubusercontent.com/'+repository+'/'+urllib.parse.quote(ref,safe='')+'/'+urllib.parse.quote(path,safe='/')
        request=urllib.request.Request(url,headers={'User-Agent':'LXTool'})
        try:
            with urllib.request.urlopen(request,timeout=15) as response:result=response.read(limit+1)
        except urllib.error.HTTPError as error:
            if error.code==404:raise
            result=api_read()
        except (urllib.error.URLError,TimeoutError,OSError):
            result=api_read()
    if len(result)>limit:raise ValueError('工具资源超过大小限制')
    return result


def read_json(repository,path,ref,token=None):return json.loads(read_bytes(repository,path,ref,token,2*1024*1024))


def visual_assets(m,reader):
    icon=checked_bytes(reader(m['icon']),m['files'][m['icon']])
    image=QImage.fromData(icon)
    if image.isNull() or image.width()>1024 or image.height()>1024 or len(icon)>2*1024*1024:raise ValueError('图标必须是有效图片，最大 1024×1024 / 2 MiB')
    readme=checked_bytes(reader(m['readme']),m['files'][m['readme']])
    if len(readme)>256*1024:raise ValueError('Markdown 介绍超过 256 KiB')
    panel=validate_panel(json.loads(checked_bytes(reader(m['panel']),m['files'][m['panel']])),m)
    return {'iconData':base64.b64encode(icon).decode(),'readmeText':readme.decode('utf-8-sig'),'panelData':panel}


def entry_for(repo_id,repository,m,prefix,commit,assets):
    return dict(m,id='repo-'+str(repo_id),repository=repository,packagePath=prefix,commit=commit,
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


def download_release_asset(repository,asset,token=None):
    headers={'User-Agent':'LXTool','Accept':'application/octet-stream'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(f"https://api.github.com/repos/{repository}/releases/assets/{int(asset['id'])}",headers=headers)
    try:
        response=urllib.request.build_opener(NoRedirect).open(request,timeout=60)
    except urllib.error.HTTPError as error:
        if error.code not in (301,302,303,307,308):raise
        url=error.headers['Location']
        if urllib.parse.urlparse(url).scheme!='https':raise ValueError('附件下载必须使用 HTTPS')
        # Never forward the private-repository credential to the signed asset URL.
        response=urllib.request.urlopen(url,timeout=60)
    with response:data=response.read(MAX_PACKAGE+1)
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


class RepositoryCatalog:
    def __init__(self,root):
        self.cache=Path(root)/'repository-catalog-v2.json'
        self.data={'schemaVersion':2,'packages':[],'warnings':[]}
        for path in (resource_path('catalog/repo-store.json'),self.cache):
            if path.exists():
                try:
                    data=json.loads(path.read_text('utf-8'))
                    if data.get('schemaVersion')!=2 or not isinstance(data.get('packages'),list):continue
                    data['packages']=[e for e in data['packages'] if e.get('distribution')=='github-release']
                    for e in data['packages']:
                        validate_manifest(e['manifestData'])
                        if e['id']!='repo-'+str(e['repositoryId']) or not e['repository'].startswith(OWNER+'/'):raise ValueError('目录身份无效')
                    self.data=data
                except (ValueError,KeyError,TypeError):pass

    def sync(self,token=None):
        repos=[];page=1
        while True:
            endpoint=(f'/user/repos?affiliation=owner&per_page=100&page={page}' if token else f'/users/{OWNER}/repos?type=owner&per_page=100&page={page}')
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
                        commit=github_json(f'/repos/{repository}/commits/{urllib.parse.quote(tag,safe="")}',token)['sha']
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
        write_json(self.cache,data)
        return data


def install_repository(entry,destination,token=None):
    if not entry['repository'].startswith(OWNER+'/') or entry['id']!='repo-'+str(entry['repositoryId']):raise ValueError('工具来源身份无效')
    import re
    if not re.fullmatch(r'[a-f0-9]{40}',entry['commit']):raise ValueError('下载必须固定到提交')
    if entry.get('distribution')!='github-release':raise ValueError('仅支持 GitHub Release 工具包，请重新扫描')
    release=github_json(f"/repos/{entry['repository']}/releases/{int(entry['releaseId'])}",token)
    if release.get('draft') or release.get('prerelease') or release['tag_name']!=entry['releaseTag']:raise ValueError('Release 状态已变化，请重新扫描')
    asset=release_asset(release)
    if asset!=entry['releaseAsset']:raise ValueError('Release 附件已变化，请重新扫描')
    payload=download_release_asset(entry['repository'],asset,token)
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
