"""Discover LX repositories and install their declared packages; owner is fixed."""
import base64
import hashlib
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


class RepositoryCatalog:
    def __init__(self,root):
        self.cache=Path(root)/'repository-catalog-v2.json'
        self.data={'schemaVersion':2,'packages':[],'warnings':[]}
        for path in (resource_path('catalog/repo-store.json'),self.cache):
            if path.exists():
                try:
                    data=json.loads(path.read_text('utf-8'))
                    if data.get('schemaVersion')!=2 or not isinstance(data.get('packages'),list):continue
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
                commit=github_json(f'/repos/{repository}/commits/{urllib.parse.quote(repo["default_branch"],safe="")}',token)['sha']
                current=validate_manifest(read_json(repository,MARKER,commit,token))
                try:
                    index=read_json(repository,'.lxtool/releases.json',commit,token)
                    if index.get('schemaVersion')!=2 or not isinstance(index.get('releases'),list) or not index['releases']:raise ValueError('发行索引格式无效')
                    releases=index['releases']
                except urllib.error.HTTPError as error:
                    if error.code!=404:raise
                    releases=[{'version':current['version'],'path':''}]
                versions=set();found=[]
                for release in releases:
                    prefix=release['path']
                    if prefix:safe_path(prefix)
                    path=(prefix+'/' if prefix else '')
                    m=validate_manifest(read_json(repository,path+MARKER,commit,token))
                    if m['version']!=release['version'] or m['version'] in versions:raise ValueError('版本号重复或与 manifest 不一致')
                    versions.add(m['version'])
                    assets=visual_assets(m,lambda p:read_bytes(repository,path+p,commit,token))
                    e=entry_for(repo['id'],repository,m,prefix,commit,assets);e['repositoryId']=repo['id'];found.append(e)
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
    prefix=entry['packagePath'];prefix=(safe_path(prefix)+'/' if prefix else '')
    read=lambda path:read_bytes(entry['repository'],prefix+path,entry['commit'],token)
    m=validate_manifest(json.loads(read(MARKER)))
    if m!=entry['manifestData']:raise ValueError('清单与商店快照不一致，请重新扫描')
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
