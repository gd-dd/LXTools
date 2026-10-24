import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import test_repository_protocol as f
from repository_source import RepositoryCatalog,install_repository,unpack_release,download_release_asset,release_asset

class GitHubReleaseTests(unittest.TestCase):
    def test_release_pages_skip_drafts_and_bad_tags_no_default_branch_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,m,entry=f.fixture(root/'fixture')
            data,release=f.release_fixture(package,m,entry)
            repo={'id':42,'full_name':'gd-dd/example','owner':{'login':'gd-dd'},'default_branch':'main'}
            draft=dict(release,draft=True)
            pre=dict(release,prerelease=True)
            broken=dict(release,tag_name='v2.0.0')
            pages=[[draft]*99+[pre],[release,broken]]
            def github(path,token=None):
                if '/users/' in path:return [repo]
                if '/releases?' in path:return pages[0] if path.endswith('page=1') else pages[1]
                return {'sha':'a'*40}
            def read(repo,path,ref,token=None,limit=None):
                self.assertNotEqual(path,'.lxtool/releases.json')
                return (package/path).read_bytes()
            with patch('repository_source.github_json',side_effect=github),patch('repository_source.read_bytes',side_effect=read):
                catalog=RepositoryCatalog(root/'cache');result=catalog.sync()
                self.assertEqual([p['version'] for p in result['packages']],['1.0.0'])
                self.assertEqual(len(result['warnings']),1)
                catalog.data=result;pages=[[]]
                self.assertEqual(catalog.sync()['packages'],[])

    def test_asset_digest_and_zip_validation_preserve_installed_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,m,entry=f.fixture(root/'fixture');data,release=f.release_fixture(package,m,entry)
            class Opener:
                def open(self,*a,**kw):return io.BytesIO(data)
            with patch('repository_source.urllib.request.build_opener',return_value=Opener()):
                self.assertEqual(download_release_asset('gd-dd/example',entry['releaseAsset']),data)
                bad=dict(entry['releaseAsset'],digest='sha256:'+'0'*64)
                with self.assertRaises(ValueError):download_release_asset('gd-dd/example',bad)
            with patch('repository_source.github_json',return_value=release),patch('repository_source.download_release_asset',return_value=data):
                install_repository(entry,root/'installed')
                buffer=io.BytesIO(data)
                with zipfile.ZipFile(buffer,'a') as z:z.writestr('undeclared.py','bad')
                with patch('repository_source.download_release_asset',return_value=buffer.getvalue()):
                    with self.assertRaises(ValueError):install_repository(entry,root/'installed')
                self.assertEqual(len(f.discover_packages(root/'installed')[0]),1)
            for name in ['../escape','C:/escape','dir/../../escape']:
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,'w') as z:z.writestr(name,'bad')
                with self.assertRaises(ValueError):unpack_release(buffer.getvalue())
            bad=copy.deepcopy(release);bad['assets'][0]['digest']=None
            with self.assertRaises(ValueError):release_asset(bad)

    def test_legacy_cache_is_not_a_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,_,entry=f.fixture(root/'fixture')
            (root/'repository-catalog-v2.json').write_text(json.dumps({'schemaVersion':2,'packages':[entry]}),'utf-8')
            self.assertEqual(RepositoryCatalog(root).data['packages'],[])
