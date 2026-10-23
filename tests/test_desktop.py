import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication,QPushButton
from desktop import Window
from core import ToolStore
import test_tool_panels


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_author_store_search_no_user_repository_and_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.show();self.app.processEvents()
            self.assertEqual(window.pages.currentWidget(),window.browse)
            self.assertIn('6 款',window.summary.text())
            self.assertNotIn('添加仓库',[b.text() for b in window.findChildren(QPushButton)])
            window.search.setText('不存在');self.assertIn('0 款',window.summary.text())
            window.search.clear();window.category.setCurrentText('建模');self.assertIn('1 款',window.summary.text())
            window.category.setCurrentIndex(0)
            key=window.library.create_folder('角色动画');window.refresh_folders();window.folders.setCurrentRow(0)
            self.assertEqual(window.browse_title.text(),'角色动画')
            self.assertIn('0 款',window.summary.text())
            window.show_tool('animation-bake')
            self.assertEqual(window.release_list.topLevelItemCount(),1)
            self.assertEqual(window.release_list.topLevelItem(0).text(2),'未安装')
            self.assertFalse(window.detail_tabs.isTabEnabled(1))
            window.close()

    def test_local_panel_and_release_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            package,data=test_tool_panels.ToolPanelTests().fixture(root)
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[dict(data,repository='gd-dd/3dmaxScript',compatibility={'range':'unverified','testedVersions':[]},manifest='releases/unverified/abc/bake/tool.json')]
            window.navigate('library');window.show_tool('bake',True)
            self.assertEqual(window.detail_tabs.currentIndex(),1)
            self.assertTrue(window.detail_tabs.isTabEnabled(1))
            self.assertEqual(window.release_list.topLevelItem(0).text(2),'使用中')
            key=window.library.create_folder('测试夹子');window.show_tool('bake')
            window.move_combo.setCurrentIndex(1)
            self.assertEqual(window.library.data['assignments']['bake'],key)
            window.close()

