import base64
import io
import zipfile
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtGui import QImage
from lx_protocol import validate_manifest,validate_panel,discover_packages,MARKER
from repository_source import RepositoryCatalog,entry_for,visual_assets,install_repository
from repository_panels import action_arguments,copy_action


def fixture(root,version='1.0.0',panel_type='declarative'):
    package=Path(root)/'repo-42'/version;(package/'.lxtool').mkdir(parents=True)
    image=QImage(16,16,QImage.Format.Format_RGB32);image.fill(0xff4499aa);image.save(str(package/'.lxtool/icon.png'))
    (package/'.lxtool/README.md').write_text('# 通用工具\n\n与任何 DCC 无关。','utf-8')
    (package/'payload.txt').write_text('hello','utf-8')
    panel={'type':'none'} if panel_type=='none' else {'type':'declarative','title':'作者自定义','sections':[{'actions':[{'action':'run','label':'运行编辑器'}]}]}
    (package/'.lxtool/panel.json').write_text(json.dumps(panel),'utf-8')
    files={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*') if p.is_file()}
    m={'schemaVersion':2,'kind':'lx-tool','name':'通用编辑器','description':'独立工具测试','version':version,'icon':'.lxtool/icon.png','readme':'.lxtool/README.md','panel':'.lxtool/panel.json','applications':{'editor':{'name':'编辑器','executable':'editor.exe'}},'actions':{'run':{'type':'process','application':'editor','arguments':['--file','{file:payload.txt}']},'copy':{'type':'copy','files':['payload.txt'],'destinationFolder':'example'}},'files':files}
    (package/MARKER).write_text(json.dumps(m),'utf-8')
    (package/'tool.json').write_text(json.dumps({'id':'repo-42','repository':'gd-dd/example','repositoryId':42,'version':version}),'utf-8')
    assets=visual_assets(m,lambda p:(package/p).read_bytes())
    entry=entry_for(42,'gd-dd/example',m,'','a'*40,assets);entry['repositoryId']=42
    return package,m,entry


def release_fixture(package,m,entry):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in [MARKER,*m['files']]:archive.writestr(path,(package/path).read_bytes())
    data=buffer.getvalue()
    asset={'id':123,'name':'LXTool-package.zip','size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
    release={'id':7,'tag_name':'v'+m['version'],'draft':False,'prerelease':False,'assets':[asset]}
    entry.update(distribution='github-release',releaseId=7,releaseTag=release['tag_name'],releaseAsset=asset)
    return data,release


class RepositoryProtocolTests(unittest.TestCase):
    def test_readable_storage_migration_and_repository_rename(self):
        from tool_storage import migrate_repository, repository_folder
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);old,m,entry=fixture(root)
            before={p.relative_to(old).as_posix():p.read_bytes() for p in old.rglob('*') if p.is_file()}
            folder=migrate_repository(root,entry)
            self.assertEqual(folder.name,'example--42')
            self.assertFalse(old.exists())
            tools,errors=discover_packages(root)
            self.assertEqual(errors,[]);self.assertEqual(len(tools),1)
            self.assertEqual(tools[0]['root'],folder/'versions'/'1.0.0')
            self.assertEqual(before,{p.relative_to(tools[0]['root']).as_posix():p.read_bytes() for p in tools[0]['root'].rglob('*') if p.is_file()})
            self.assertEqual(repository_folder(root,dict(entry,repository='gd-dd/renamed')),folder)
            self.assertEqual(migrate_repository(root,entry),folder)

    def test_generic_tool_discovery_and_tool_defined_process_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            package,m,entry=fixture(root)
            tools,errors=discover_packages(root);self.assertEqual(len(tools),1);self.assertEqual(errors,[])
            executable=Path(root)/'editor.exe';executable.touch()
            args=action_arguments(tools[0],m['actions']['run'],{'editor':{'path':str(executable)}})
            # Package arguments are canonical paths; Windows TEMP may use an 8.3 alias.
            self.assertEqual(args,[str(executable),'--file',str((package/'payload.txt').resolve())])
            target=Path(root)/'target';target.mkdir()
            copy_action(tools[0],m['actions']['copy'],target)
            self.assertEqual((target/'example'/'1.0.0'/'payload.txt').read_text(),'hello')
            (package/'payload.txt').write_text('changed')
            self.assertEqual(discover_packages(root)[0],[])

    def test_marker_assets_and_actions_are_required(self):
        with tempfile.TemporaryDirectory() as root:
            _,m,_=fixture(root)
            for change in [{'kind':'ordinary-project'},{'name':'x'*21},{'icon':'../outside.png'},{'files':{}},{'actions':{'bad':{'type':'max'}}}]:
                with self.subTest(change=change),self.assertRaises(ValueError):validate_manifest(dict(m,**change))
            self.assertEqual(validate_panel({'type':'none'},m),{'type':'none'})
            with self.assertRaises(ValueError):validate_panel({'type':'declarative','sections':[{'actions':[{'action':'unknown','label':'x'}]}]},m)

    def test_full_pagination_one_repo_one_tool_missing_marker_and_error_isolation(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as root:
            package,m,entry=fixture(Path(root)/'fixture')
            _,release=release_fixture(package,m,entry)
            repo=lambda i:{'id':i,'full_name':'gd-dd/r'+str(i),'owner':{'login':'gd-dd'},'default_branch':'main'}
            pages=[[repo(i) for i in range(100)],[repo(100)]]
            def github(path,token=None):
                if '/repos?' in path:return pages[0] if path.endswith('&page=1') else pages[1]
                if '/releases?' in path:return [release]
                return {'sha':'a'*40}
            def remote(repository,path,ref,token=None,limit=None):
                if repository!='gd-dd/r42' or path=='.lxtool/releases.json':raise urllib.error.HTTPError('test',404,'missing',None,None)
                return (package/path).read_bytes()
            catalog=RepositoryCatalog(Path(root)/'config')
            with patch('repository_source.github_json',side_effect=github),patch('repository_source.read_bytes',side_effect=remote):result=catalog.sync()
            self.assertEqual(result['scannedRepositories'],101)
            self.assertEqual(len(result['packages']),1)
            self.assertEqual(result['packages'][0]['id'],'repo-42')
            self.assertEqual(result['warnings'],[])

    def test_download_pinned_package_and_hash_failure(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);package,m,entry=fixture(root/'fixture')
            data,release=release_fixture(package,m,entry)
            with patch('repository_source.github_json',return_value=release),patch('repository_source.download_release_asset',return_value=data):
                install_repository(entry,root/'installed')
                self.assertEqual(len(discover_packages(root/'installed')[0]),1)
                install_repository(entry,root/'installed')
                with patch('repository_source.download_release_asset',return_value=data.replace(b'PK',b'XX',1)):
                    with self.assertRaises(Exception):install_repository(entry,root/'installed')
                release['draft']=True
                with self.assertRaises(ValueError):install_repository(entry,root/'installed')
            self.assertEqual(len(discover_packages(root/'installed')[0]),1)
            self.assertFalse(list((root/'installed').glob('.download-*')))
