import sys
import tempfile
import unittest
import zipfile
import io
import json
import hashlib
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import ToolStore, safe_extract


class StoreTests(unittest.TestCase):
    def test_catalog_atomic_import(self):
        with tempfile.TemporaryDirectory() as root:
            store = ToolStore(root)
            entry = dict(id='tool', repository='example/tool', name='Tool', category='Unity', delivery='github-release-zip')
            store.import_catalog({'schemaVersion': 1, 'tools': [entry]})
            with self.assertRaises(ValueError):
                store.import_catalog({'schemaVersion': 1, 'tools': [entry, entry]})
            self.assertEqual(len(ToolStore(root).state['tools']), 1)
            with patch.object(store, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.import_catalog({'schemaVersion': 1, 'tools': [dict(entry, name='Changed')]})
            self.assertEqual(store.state['tools'][0]['name'], 'Tool')

    def test_uninstall_rollback_and_active_protection(self):
        with tempfile.TemporaryDirectory() as root:
            store = ToolStore(root)
            store.add('example/tool', 'Unity')
            tool = store.state['tools'][0]
            target = Path(root) / 'packages' / tool['id'] / '1'
            target.mkdir(parents=True)
            (target / 'content').write_text('keep')
            tool['versions'] = [{'key': '1'}]
            store.activate(tool['id'], '1')
            with self.assertRaises(ValueError):
                store.uninstall(tool['id'], '1')
            tool['active'] = None
            with patch.object(store, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.uninstall(tool['id'], '1')
            self.assertTrue((target / 'content').exists())
            store.uninstall(tool['id'], '1')
            self.assertFalse(target.exists())
            self.assertEqual(ToolStore(root).state['tools'][0]['versions'], [])

    def test_failed_add_does_not_leave_phantom_tool(self):
        with tempfile.TemporaryDirectory() as root:
            store = ToolStore(root)
            with patch.object(store, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.add('example/tool', 'Unity')
            self.assertEqual(store.state['tools'], [])
            store.add('example/tool', 'Unity')
            self.assertEqual(len(ToolStore(root).state['tools']), 1)

    def test_install_and_failed_install_preserve_previous_version(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('tool.txt', 'version content')
        payload = buffer.getvalue()
        with tempfile.TemporaryDirectory() as root:
            store = ToolStore(root)
            store.add('example/tool', 'Unity')
            tool = store.state['tools'][0]
            asset = {'id': 1, 'name': 'tool.zip', 'size': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
            def request(_tool, _path, binary=False):
                return io.BytesIO(payload if binary else json.dumps(asset).encode())
            with patch.object(store, 'request', side_effect=request), patch.object(store, 'releases', return_value=[{'tag': 'v1', 'assets': [asset]}]):
                store.install(tool['id'], 1)
                store.activate(tool['id'], '1')
                asset['id'] = 2
                with patch.object(store, 'save', side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):
                        store.install(tool['id'], 2)
                self.assertEqual([v['key'] for v in tool['versions']], ['1'])
                self.assertEqual(tool['active'], '1')
                self.assertFalse((Path(root) / 'packages' / tool['id'] / '2').exists())
                asset['digest'] = 'sha256:invalid'
                with self.assertRaisesRegex(ValueError, '哈希'):
                    store.install(tool['id'], 2)
                self.assertEqual(ToolStore(root).state['tools'][0]['active'], '1')
                self.assertFalse(list((Path(root) / 'packages' / tool['id']).glob('staging-*')))

    def test_persistence_and_switch(self):
        with tempfile.TemporaryDirectory() as root:
            store = ToolStore(root)
            store.add('example/tool', 'Unity')
            tool = store.state['tools'][0]
            for key in ('1', '2'):
                (Path(root) / 'packages' / tool['id'] / key).mkdir(parents=True)
                tool['versions'].append({'key': key})
            store.tokens[tool['id']] = 'secret-test-value'
            store.activate(tool['id'], '1')
            store.activate(tool['id'], '2')
            restored = ToolStore(root)
            self.assertEqual(restored.state['tools'][0]['active'], '2')
            self.assertNotIn('secret-test-value', store.file.read_text())
            with self.assertRaises(ValueError):
                store.activate(tool['id'], 'missing')
            self.assertEqual(tool['active'], '2')

    def test_unsafe_zip_paths(self):
        for name in ('../escape.txt', '/absolute.txt', 'C:/escape.txt', 'CON.txt', 'a/../../escape', 'a\\..\\escape'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                archive = Path(root) / 'input.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr(name, 'unsafe')
                dest = Path(root) / 'out'
                dest.mkdir()
                with self.assertRaises(ValueError):
                    safe_extract(archive, dest)

    def test_normal_zip(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / 'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('scripts/tool.ms', 'print "test"')
            dest = Path(root) / 'out'
            dest.mkdir()
            safe_extract(archive, dest)
            self.assertTrue((dest / 'scripts/tool.ms').exists())


if __name__ == '__main__':
    unittest.main()
