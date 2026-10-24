import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel
from lx_protocol import validate_panel, discover_packages
from native_panels import NativePanelHandle
from repository_panels import RepositoryWorkspace
import test_repository_protocol as fixtures

CODE = '''from PySide6.QtWidgets import QWidget,QVBoxLayout,QPushButton
from .helper import TITLE
class Panel(QWidget):
    def __init__(self,context,parent):
        super().__init__(parent);self.context=context
        self.setStyleSheet('QPushButton {color: #123456;}')
        layout=QVBoxLayout(self);self.button=QPushButton(TITLE);layout.addWidget(self.button)
        self.button.clicked.connect(self.increment)
    def increment(self):
        value=self.context.load_settings().get('count',0)+1
        self.context.save_settings({'count':value});self.button.setText(str(value))
    def shutdown(self):
        (self.context.data_root/'closed.txt').write_text('closed')
def create_panel(context,parent):return Panel(context,parent)
'''


def native_fixture(root,version='1.0.0',code=CODE):
    package,manifest,_=fixtures.fixture(root,version)
    (package/'ui').mkdir()
    (package/'ui/panel.py').write_text(code,'utf-8')
    (package/'ui/helper.py').write_text('TITLE="工具自己的按钮"','utf-8')
    spec={'type':'native','apiVersion':1,'entry':'ui/panel.py'}
    (package/'.lxtool/panel.json').write_text(json.dumps(spec),'utf-8')
    for path in ('.lxtool/panel.json','ui/panel.py','ui/helper.py'):
        manifest['files'][path]=hashlib.sha256((package/path).read_bytes()).hexdigest()
    (package/'.lxtool/manifest.json').write_text(json.dumps(manifest),'utf-8')
    return dict(manifest,root=package.resolve(),id='repo-42',panelData=spec)


class NativePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_custom_interaction_relative_import_settings_and_version_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);one=native_fixture(root/'tools');two=native_fixture(root/'tools','2.0.0')
            parent=QWidget();style=self.app.styleSheet()
            a=NativePanelHandle(one,root/'config',parent)
            b=NativePanelHandle(two,root/'config',parent)
            self.assertNotEqual(a.namespace,b.namespace)
            a.widget.button.click();self.assertEqual(a.widget.button.text(),'1')
            self.assertEqual(b.context.load_settings(),{'count':1})
            self.assertEqual(self.app.styleSheet(),style)
            a.shutdown();a.shutdown()
            self.assertTrue((a.context.data_root/'closed.txt').exists())
            self.assertFalse(any(n.startswith(a.namespace) for n in sys.modules))
            b.widget.button.click();self.assertEqual(b.widget.button.text(),'2');b.shutdown()
            self.assertFalse(list(one['root'].rglob('__pycache__')))
            self.assertEqual(discover_packages(root/'tools')[1],[])

    def test_bad_api_paths_and_tampering_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tool=native_fixture(root/'tools')
            for spec in ({'type':'native','apiVersion':2,'entry':'ui/panel.py'},
                         {'type':'native','apiVersion':True,'entry':'ui/panel.py'},
                         {'type':'native','apiVersion':1,'entry':'../panel.py'},
                         {'type':'native','apiVersion':1,'entry':'missing.py'}):
                with self.subTest(spec=spec),self.assertRaises(ValueError):validate_panel(spec,tool)
            (tool['root']/'ui/helper.py').write_text('raise RuntimeError("must not run")')
            with self.assertRaisesRegex(ValueError,'摘要'):NativePanelHandle(tool,root/'config',QWidget())

    def test_failed_factory_does_not_leave_modules_or_break_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            bad=native_fixture(root/'tools',code='def create_panel(context,parent):raise RuntimeError("bad factory")')
            before={n for n in sys.modules if n.startswith('_lx_panel_')}
            workspace=RepositoryWorkspace(root/'tools',root/'config')
            workspace.display(bad)
            self.assertIn('bad factory',''.join(x.text() for x in workspace.findChildren(QLabel)))
            self.assertEqual(before,{n for n in sys.modules if n.startswith('_lx_panel_')})
            good=native_fixture(root/'tools','2.0.0');workspace.display(good)
            self.assertIsNotNone(workspace.native_panel.widget)
            workspace.shutdown();self.assertIsNone(workspace.native_panel)

    def test_declared_resources_only_and_bad_factory_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tool=native_fixture(root/'tools');parent=QWidget()
            handle=NativePanelHandle(tool,root/'config',parent)
            for name in ('../escape','tool.json','undeclared.txt'):
                with self.assertRaises(ValueError):handle.context.resource(name)
            handle.shutdown()
            bad=native_fixture(root/'tools','2.0.0',code='def create_panel(context,parent):return 12')
            with self.assertRaisesRegex(TypeError,'QWidget'):NativePanelHandle(bad,root/'config',parent)

    def test_navigation_disposes_panel_without_executing_during_discovery(self):
        from desktop import Window
        from core import ToolStore
        from repository_source import visual_assets,entry_for
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tool=native_fixture(root/'tools')
            entry=entry_for(42,'gd-dd/example',tool,'','a'*40,visual_assets(tool,lambda p:(tool['root']/p).read_bytes()))
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[entry]
            window.show_tool('repo-42')
            self.assertFalse(getattr(window.workspace,'native_panel',None))
            window.navigate('library');window.open_tool_panel('repo-42')
            handle=window.workspace.native_panel
            self.assertIsNotNone(handle.widget)
            window.navigate('store')
            self.assertIsNone(window.workspace.native_panel)
            self.assertTrue((handle.context.data_root/'closed.txt').exists())
            window.close()


if __name__=='__main__':unittest.main()
