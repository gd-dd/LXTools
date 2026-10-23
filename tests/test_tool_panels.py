import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from tool_panels import discover_tools, install_script, launch_arguments, ToolWorkspace


class ToolPanelTests(unittest.TestCase):
    def fixture(self, root):
        package = root / 'tools' / 'bake'
        package.mkdir(parents=True)
        (package / 'bake.ms').write_text('print "hello"', 'utf-8')
        data = dict(schemaVersion=1, id='bake', name='烘焙', description='测试', host='3dsmax', entry='bake.ms', version='abc', sha256=hashlib.sha256((package/'bake.ms').read_bytes()).hexdigest())
        (package / 'tool.json').write_text(json.dumps(data), 'utf-8')
        return package, data

    def test_discovery_rejects_escape_and_modified_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, data = self.fixture(root)
            tools, errors = discover_tools(root/'tools')
            self.assertEqual(len(tools), 1)
            (package/'bake.ms').write_text('modified')
            self.assertEqual(len(discover_tools(root/'tools')[0]), 0)
            data['entry'] = '../../outside.ms'
            (package/'tool.json').write_text(json.dumps(data))
            self.assertEqual(len(discover_tools(root/'tools')[0]), 0)

    def test_install_and_host_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            tool = discover_tools(root/'tools')[0][0]
            scripts = root/'scripts'
            scripts.mkdir()
            target = install_script(tool, scripts)
            self.assertTrue((target/'bake.ms').exists())
            self.assertEqual(install_script(tool, scripts), target)
            exe = root/'3dsmax.exe'
            exe.touch()
            self.assertEqual(launch_arguments(exe, tool), [str(exe), '-U', 'MAXScript', str(tool['entry_path'])])

    def test_tool_panel_loads_without_host(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            workspace = ToolWorkspace(root/'tools', root/'config')
            self.assertEqual(workspace.list.count(), 1)
            self.assertEqual(workspace.pages.count(), 1)
            with self.assertRaises(ValueError):
                workspace.launch()
            workspace.close()

