import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication
from core import ToolStore
from desktop import Window
import development
import test_repository_protocol as fixtures


class DevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_source(self, root):
        import shutil
        package, _, entry = fixtures.fixture(root / 'fixture')
        target = root / 'tools/sample'
        shutil.copytree(package, target)
        return target, entry

    def test_development_separate_from_store_and_frozen_client(self):
        with patch.object(sys, 'argv', ['desktop.py', '--dev']), patch.object(sys, 'frozen', True, create=True):
            self.assertFalse(development.enabled())
        with tempfile.TemporaryDirectory() as temp, patch.object(sys, 'argv', ['desktop.py', '--dev']):
            root = Path(temp)
            _, entry = self.make_source(root)
            window = Window(ToolStore(root / 'profile'), root / 'tools', autoload=False)
            try:
                self.assertEqual(set(window.nav),{'store','library','settings'})
                self.assertFalse(hasattr(window,'dev_tools'))
                self.assertEqual(window.pages.currentWidget(),window.browse)
                self.assertIn('0.0.0', window.display_version)
                window.catalog.data['packages'] = [entry]
                window.navigate('store')
                self.assertEqual(window.installed(), [])
                self.assertFalse(window.update_button.isEnabled())
                with patch('desktop.prepare_update') as update:
                    window.update_client()
                    update.assert_not_called()
                self.assertEqual(window.catalog.data['packages'], [entry])
            finally:
                window.dev_timer.stop();window.close()

    def test_reload_debounces_and_waits_for_busy_tasks(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(sys, 'argv', ['desktop.py', '--dev']):
            root=Path(temp)
            window=Window(ToolStore(root/'profile'),root/'tools',autoload=False)
            try:
                window.project_root=root
                window.dev_stamp=('old',)
                with patch('development.fingerprint',return_value=('new',)), patch.object(self.app,'exit') as exit_app:
                    window.check_development()
                    exit_app.assert_not_called()
                    window.job=object()
                    window.check_development()
                    exit_app.assert_not_called()
                    window.job=None
                    window.check_development()
                    exit_app.assert_called_once_with(75)
                self.assertTrue((root/'profile/preview-state.json').exists())
            finally:
                window.job=None;window.dev_timer.stop();window.close()

    def test_branch_download_update_failure_and_production_gate(self):
        from lx_protocol import discover_packages
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            package,m,entry=fixtures.fixture(root/'source')
            entry.update(version='0.0.0',distribution='github-branch',branch='main',sourceManifest=m)
            with self.assertRaises(ValueError):development.install_branch(entry,root/'installed')
            with patch.object(sys,'argv',['desktop.py','--dev']), patch('repository_source.read_json',return_value=m), patch('repository_source.read_bytes',side_effect=lambda repo,path,sha,token:(package/path).read_bytes()) as read:
                target=Path(development.install_branch(entry,root/'installed'))
                self.assertTrue(all(c.args[2]=='a'*40 for c in read.call_args_list))
                entry['commit']='b'*40
                (package/'payload.txt').write_text('latest branch code')
                development.install_branch(entry,root/'installed')
                self.assertEqual((target/'payload.txt').read_text(),'latest branch code')
                tools,errors=discover_packages(root/'installed')
                self.assertEqual(errors,[])
                self.assertEqual(tools[0]['commit'],'b'*40)
                self.assertEqual(tools[0]['version'],'0.0.0')
                with patch('repository_source.read_bytes',side_effect=OSError('offline')):
                    with self.assertRaises(OSError):development.install_branch(entry,root/'installed')
                self.assertEqual((target/'payload.txt').read_text(),'latest branch code')

    def test_branch_update_in_discover_and_open_from_library(self):
        from lx_protocol import discover_packages
        with tempfile.TemporaryDirectory() as temp, patch.object(sys,'argv',['desktop.py','--dev']):
            root=Path(temp);package,m,release=fixtures.fixture(root/'fixture')
            branch=dict(release,version='0.0.0',distribution='github-branch',branch='main',sourceManifest=m)
            with patch('repository_source.read_json',return_value=m), patch('repository_source.read_bytes',side_effect=lambda repo,path,sha,token:(package/path).read_bytes()):
                development.install_branch(branch,root/'tools')
            window=Window(ToolStore(root/'profile'),root/'tools',autoload=False)
            try:
                window.catalog.data['packages']=[release,dict(branch,commit='b'*40)]
                window.navigate('store');window.show_tool(branch['id'])
                self.assertEqual(window.release_list.topLevelItemCount(),2)
                window.release_list.setCurrentItem(window.release_list.topLevelItem(1))
                self.assertTrue(window.download_button.isEnabled())
                self.assertEqual(window.download_button.text(),'更新分支快照')
                window.navigate('library');window.open_tool_panel(branch['id'])
                self.assertEqual(window.workspace.current['version'],'0.0.0')
                self.assertEqual(window.workspace.current['distribution'],'github-branch')
            finally:
                window.dev_timer.stop();window.close()

    def test_missing_binary_requires_exact_manifest_digest(self):
        import hashlib, io, zipfile
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as temp, patch.object(sys,'argv',['desktop.py','--dev']):
            root=Path(temp);package,m,entry=fixtures.fixture(root/'source')
            m['files']['bin/worker.exe']=hashlib.sha256(b'expected compiled bytes').hexdigest()
            entry.update(version='0.0.0',distribution='github-branch',branch='main',sourceManifest=m)
            def read(repo,path,sha,token):
                if path=='bin/worker.exe':raise HTTPError('https://example.invalid',404,'missing',{},None)
                return (package/path).read_bytes()
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('bin/worker.exe',b'wrong binary')
                z.writestr('.lxtool/manifest.json',json.dumps(m))
            with patch('repository_source.read_json',return_value=m), patch('repository_source.read_bytes',side_effect=read), patch('urllib.request.urlopen',return_value=io.BytesIO(archive.getvalue())):
                with self.assertRaisesRegex(ValueError,'摘要不匹配'):
                    development.install_branch(entry,root/'tools')
            self.assertFalse((root/'tools/example--42/versions/0.0.0').exists())
