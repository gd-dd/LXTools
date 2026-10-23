import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from library import Library,AuthorCatalog,validate_catalog
from tool_source import fetch_packages
from tool_panels import discover_tools
from updater import replace_program


class LibraryTests(unittest.TestCase):
    def test_chinese_folders_persist_and_removing_does_not_delete_tools(self):
        with tempfile.TemporaryDirectory() as root:
            library=Library(root,Path(root)/'tools')
            key=library.create_folder('角色动画')
            library.move('bake',key);library.rename_folder(key,'常用动画')
            loaded=Library(root,Path(root)/'tools')
            self.assertEqual(loaded.data['folders'][key],'常用动画')
            self.assertEqual(loaded.data['assignments']['bake'],key)
            with self.assertRaises(ValueError):loaded.create_folder('常用动画')
            loaded.remove_folder(key)
            self.assertEqual(loaded.data,{'folders':{},'assignments':{}})

    def test_single_tool_pinned_download_switch_candidates_and_uninstall(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);repo='author/tools';commit='a'*40
            payload={};packages=[]
            for identity,version in [('bake','1.0.0'),('bake','2.0.0'),('other','1.0.0')]:
                prefix=f'releases/unverified/{version}/{identity}'
                script=('print "'+version+'"').encode()
                digest=hashlib.sha256(script).hexdigest()
                manifest={'schemaVersion':1,'id':identity,'version':version,'name':identity,'description':'test','host':'3dsmax','entry':'main.ms','sha256':digest,'files':{'main.ms':digest},'compatibility':{'range':'unverified','testedVersions':[]},'panel':{'type':'none'}}
                payload[prefix+'/tool.json']=json.dumps(manifest).encode();payload[prefix+'/main.ms']=script
                packages.append({'manifest':prefix+'/tool.json','compatibility':manifest['compatibility']})
            payload['tools-index.json']=json.dumps({'schemaVersion':1,'packages':packages}).encode()
            def remote(path,token=None):
                self.assertIn('?ref='+commit,path)
                key=path.split('/contents/')[1].split('?')[0]
                return {'encoding':'base64','content':base64.b64encode(payload[key]).decode()}
            with patch('tool_source.github_json',side_effect=remote):
                fetch_packages(repo,root/'tools','2026.3',True,manifest_path=packages[0]['manifest'],commit=commit)
                tools,errors=discover_tools(root/'tools');self.assertEqual(len(tools),1);self.assertEqual(errors,[])
                fetch_packages(repo,root/'tools','2026.3',True,manifest_path=packages[1]['manifest'],commit=commit)
                tools,_=discover_tools(root/'tools');self.assertEqual({t['version'] for t in tools},{'1.0.0','2.0.0'})
                self.assertFalse((root/'tools'/'other').exists())
                library=Library(root,root/'tools');library.uninstall(tools[0])
                self.assertEqual(len(discover_tools(root/'tools')[0]),1)
                with self.assertRaises(ValueError):library.uninstall({'root':root})
                payload['releases/unverified/1.0.0/bake/main.ms']=b'tampered'
                with self.assertRaises(ValueError):fetch_packages(repo,root/'tools','2026.3',True,manifest_path=packages[0]['manifest'],commit=commit)
                self.assertEqual(len(discover_tools(root/'tools')[0]),1)
                self.assertFalse(list((root/'tools').glob('.download-*')))

    def test_catalog_reject_unapproved_repository(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=AuthorCatalog(root)
            catalog.data['packages'][0]['repository']='stranger/repo'
            with self.assertRaises(ValueError):validate_catalog(catalog.data)

    def test_self_update_preserves_tools_and_rolls_back_failure(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);stage=root/'stage';target=root/'client'
            for folder,content in [(stage,'new'),(target,'old')]:
                (folder/'_internal').mkdir(parents=True)
                (folder/'LXTool.exe').write_text(content)
                (folder/'_internal'/'dll').write_text(content)
            (target/'tools').mkdir();(target/'tools'/'keep').write_text('user tools')
            with patch('updater.shutil.copytree',side_effect=OSError('locked')):
                with self.assertRaises(OSError):replace_program(stage,target)
            self.assertEqual((target/'LXTool.exe').read_text(),'old')
            self.assertEqual((target/'_internal'/'dll').read_text(),'old')
            backup=replace_program(stage,target)
            self.assertEqual((target/'LXTool.exe').read_text(),'new')
            self.assertEqual((target/'tools'/'keep').read_text(),'user tools')
            self.assertEqual((backup/'LXTool.exe').read_text(),'old')

