import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from updater import prepare_update


class ReleaseUpdateTests(unittest.TestCase):
    def test_old_client_selects_newest_stable_and_requires_digest(self):
        releases=[
            {'tag_name':'v0.0.1','draft':False,'prerelease':False,'assets':[]},
            {'tag_name':'v3.0.0','draft':True,'prerelease':False,'assets':[]},
            {'tag_name':'v2.0.0','draft':False,'prerelease':True,'assets':[]},
            {'tag_name':'v0.6.0','draft':False,'prerelease':False,'assets':[{'name':'LXTool-windows-x64.zip','id':42,'digest':'sha256:'+'a'*64}]},
        ]
        class Store:
            def __init__(self,root):
                self.root=Path(root);self.state={'tools':[{'id':'client','versions':[]}]};self.tokens={}
            def request(self,*args):return io.StringIO(json.dumps(releases))
            def install(self,identity,asset):
                assert asset==42
                stage=self.root/'packages'/identity/str(asset)/'LXTool'
                (stage/'_internal').mkdir(parents=True);(stage/'LXTool.exe').write_bytes(b'test')
        with tempfile.TemporaryDirectory() as root,patch('updater.ToolStore',Store):
            tag,stage=prepare_update(root)
            self.assertEqual(tag,'v0.6.0');self.assertTrue((stage/'LXTool.exe').exists())
            releases[-1]['assets'][0]['digest']=None
            with self.assertRaisesRegex(ValueError,'SHA-256'):prepare_update(root)
            releases.pop()
            self.assertIsNone(prepare_update(root))


if __name__=='__main__':unittest.main()
