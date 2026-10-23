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

    def test_version_switch_uses_saved_environment_and_update_can_restart_after_job(self):
        import json
        import shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            package,data=test_tool_panels.ToolPanelTests().fixture(root)
            data['compatibility']={'range':'unverified','testedVersions':[]}
            data['version']='1.0.0'
            (package/'tool.json').write_text(json.dumps(data),'utf-8')
            second=package.with_name('bake2');shutil.copytree(package,second)
            newer=dict(data,version='2.0.0');(second/'tool.json').write_text(json.dumps(newer),'utf-8')
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[dict(t,repository='gd-dd/3dmaxScript',manifest=f"releases/unverified/{t['version']}/bake/tool.json") for t in (data,newer)]
            window.host_version.setText('unsaved-invalid')
            window.show_tool('bake')
            window.release_list.setCurrentItem(window.release_list.topLevelItem(0))
            with patch.object(window.workspace,'check_compatibility',return_value=True):window.activate_selected()
            self.assertEqual(window.workspace.config['selectedVersions']['2026.3']['bake'],'2.0.0@unverified')
            window.release_list.setCurrentItem(window.release_list.topLevelItem(1))
            with patch.object(window.workspace,'check_compatibility',return_value=True):window.activate_selected()
            self.assertEqual(window.workspace.config['selectedVersions']['2026.3']['bake'],'1.0.0@unverified')
            with patch('desktop.subprocess.Popen') as popen, patch.object(window,'close') as close:
                window.restart_updated(root/'staged')
                popen.assert_called_once();close.assert_called_once()
            window.job=object()
            with patch('desktop.subprocess.Popen') as popen:
                window.restart_updated(root/'staged')
                popen.assert_not_called()
            self.assertEqual(window.pending_restart,root/'staged')
            window.job=None;window.close()

