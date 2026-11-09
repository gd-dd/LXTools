import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import test_repository_protocol as f
from repository_source import RepositoryCatalog,validate_index,install_repository,MAX_INDEX

class IndexTests(unittest.TestCase):
    def fixture(self,root):
        package,m,e=f.fixture(root/'fixture');payload,release=f.release_fixture(package,m,e)
        return {'schemaVersion':2,'packages':[e],'warnings':[]},m,release

    def test_200_304_restart_offline_and_empty_keep_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,_,_=self.fixture(root)
            catalog=RepositoryCatalog(root/'profile')
            response=io.BytesIO(json.dumps(data).encode());response.headers={'ETag':'"one"'}
            with patch('repository_source.urllib.request.urlopen',return_value=response) as request,patch('repository_source.github_json') as api:
                catalog.sync('never-send-this-token');api.assert_not_called()
                self.assertIsNone(request.call_args.args[0].get_header('Authorization'))
            original=catalog.cache.read_bytes()
            catalog=RepositoryCatalog(root/'profile')
            with patch('repository_source.urllib.request.urlopen',side_effect=HTTPError('index',304,'same',{},None)) as request:
                self.assertEqual(catalog.sync()['packages'],data['packages'])
                self.assertEqual(request.call_args.args[0].get_header('If-none-match'),'"one"')
            for failure in [TimeoutError('offline'),HTTPError('index',403,'limited',{},None)]:
                with patch('repository_source.urllib.request.urlopen',side_effect=failure):
                    with self.assertRaises(Exception):catalog.sync()
                self.assertEqual(catalog.cache.read_bytes(),original)
            for bad in [b'{}',b'not json',b'{"schemaVersion":2,"packages":[]}',b' '* (MAX_INDEX+1)]:
                response=io.BytesIO(bad);response.headers={}
                with patch('repository_source.urllib.request.urlopen',return_value=response):
                    with self.assertRaises(ValueError):catalog.sync()
                self.assertEqual(catalog.cache.read_bytes(),original)

    def test_index_identity_assets_and_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,_,_=self.fixture(Path(tmp));validate_index(data)
            for key,value in [('repository','other/example'),('repositoryId',True),('commit','x'*40),('releaseTag','v9.0.0'),('distribution','branch'),('readmeText','forged'),('panelBytes','e30='),('iconData','e30=')]:
                bad=copy.deepcopy(data);bad['packages'][0][key]=value
                with self.subTest(key=key),self.assertRaises((ValueError,KeyError,TypeError)):validate_index(bad)
            data['packages']*=2
            with self.assertRaises(ValueError):validate_index(data)

    def test_304_without_valid_cache_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch('repository_source.resource_path',return_value=Path(tmp)/'missing'):
            catalog=RepositoryCatalog(tmp)
            with patch('repository_source.urllib.request.urlopen',side_effect=HTTPError('index',304,'same',{},None)):
                with self.assertRaises(HTTPError):catalog.sync()

    def test_changed_tag_or_source_stops_before_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,m,release=self.fixture(root);e=data['packages'][0]
            for sha,manifest in [('b'*40,m),('a'*40,dict(m,description='changed'))]:
                with patch('repository_source.github_json',side_effect=lambda path,token=None:{'sha':sha} if '/commits/' in path else release),patch('repository_source.read_json',return_value=manifest),patch('repository_source.download_release_asset') as download:
                    with self.assertRaises(ValueError):install_repository(e,root/'tools')
                    download.assert_not_called()
                    self.assertFalse((root/'tools').exists())
