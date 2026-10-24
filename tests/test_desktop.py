import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication,QPushButton,QLineEdit
from desktop import Window
from core import ToolStore
import test_repository_protocol as fixtures


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_one_repository_card_icon_opens_markdown_without_max_settings(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            _,_,entry=fixtures.fixture(root/'fixture')
            window.catalog.data['packages']=[entry];window.render_cards()
            window.show();self.app.processEvents()
            self.assertIn('1 款',window.summary.text())
            self.assertFalse(hasattr(window,'host_version'))
            self.assertNotIn('添加仓库',[b.text() for b in window.findChildren(QPushButton)])
            icons=[b for b in window.card_area.findChildren(QPushButton) if not b.icon().isNull()]
            self.assertEqual(len(icons),1);icons[0].click()
            self.assertIn('通用工具',window.readme.toPlainText())
            self.assertFalse(window.detail_icon.pixmap().isNull())
            self.assertEqual(window.detail_icon.width(),160)
            self.assertEqual(window.pages.currentWidget(),window.detail)
            self.assertEqual([window.detail_tabs.tabText(i) for i in range(window.detail_tabs.count())],['概览','版本与卸载'])
            self.assertFalse(hasattr(window,'panel_button'))
            window.close()

    def test_generic_panel_versions_and_chinese_folders(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);_,_,one=fixtures.fixture(root/'tools','1.0.0');_,_,two=fixtures.fixture(root/'tools','2.0.0')
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[one,two];window.show_tool('repo-42')
            self.assertEqual(window.release_list.topLevelItemCount(),2)
            window.navigate('library');window.open_tool_panel('repo-42')
            self.assertEqual(window.pages.currentWidget(),window.tool_panel)
            self.assertEqual([b.text() for b in window.workspace.findChildren(QPushButton) if b.text()=='运行编辑器'],['运行编辑器'])
            window.show_tool('repo-42');window.release_list.setCurrentItem(window.release_list.topLevelItem(0));window.activate_selected()
            self.assertEqual(window.workspace.config['selectedVersions']['repo-42'],'2.0.0')
            window.release_list.setCurrentItem(window.release_list.topLevelItem(1));window.activate_selected()
            self.assertEqual(window.workspace.config['selectedVersions']['repo-42'],'1.0.0')
            key=window.library.create_folder('中文夹子');window.navigate('library');window.open_tool_panel('repo-42');window.move_combo.setCurrentIndex(1)
            self.assertEqual(window.library.data['assignments']['repo-42'],key)
            window.navigate('library',key);self.assertIn('1 款',window.summary.text())
            with patch('desktop.subprocess.Popen') as popen,patch.object(window,'close') as close:
                window.restart_updated(root/'staged');popen.assert_called_once();close.assert_called_once()
            window.close()

    def test_card_uses_tool_owned_icon_and_groups_versions(self):
        import base64
        from PySide6.QtGui import QPixmap
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            _,_,one=fixtures.fixture(root/'tools','1.0.0')
            _,_,two=fixtures.fixture(root/'tools','2.0.0')
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[one,two];window.render_cards()
            self.app.sendPostedEvents();self.app.processEvents()
            buttons=[window.cards.itemAt(i).widget().findChild(QPushButton,'brandIcon') for i in range(window.cards.count()) if window.cards.itemAt(i).widget()]
            buttons=[b for b in buttons if b is not None]
            self.assertEqual(len(buttons),1)
            expected=QPixmap();expected.loadFromData(base64.b64decode(two['iconData']))
            self.assertEqual(buttons[0].icon().pixmap(16,16).toImage(),expected.toImage())
            buttons[0].click();self.assertEqual(window.release_list.topLevelItemCount(),2)
            window.close()

    def test_store_filters_and_library_icon_opens_only_full_panel(self):
        from PySide6.QtWidgets import QTabWidget
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            _,_,one=fixtures.fixture(root/'tools','1.0.0')
            _,_,two=fixtures.fixture(root/'remote','2.0.0')
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[one,two];window.navigate('store')
            for state,count in [('已下载',1),('未下载',0),('可更新',1)]:
                window.install_filter.setCurrentText(state)
                self.assertTrue(window.summary.text().startswith(str(count)+' 款'))
            with self.assertRaises(ValueError):window.open_tool_panel('repo-42')
            window.navigate('library')
            self.assertTrue(window.summary.text().startswith('1 款'))
            card=window.cards.itemAt(0).widget()
            self.assertEqual([b.text() for b in card.findChildren(QPushButton) if b.text()],['打开工具'])
            card.findChild(QPushButton,'brandIcon').click()
            self.assertEqual(window.pages.currentWidget(),window.tool_panel)
            self.assertEqual(window.tool_panel.findChildren(QTabWidget),[])
            self.assertFalse(window.detail.isVisible())
            self.assertEqual(window.workspace.current['version'],'1.0.0')
            window.show_tool('repo-42')
            with patch.object(window,'busy',side_effect=lambda fn,done,message:done(None)):
                window.install_entry(two)
            self.assertEqual(window.pages.currentWidget(),window.detail)
            window.close()

    def test_store_uninstall_all_versions_and_cancel(self):
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            _,_,one=fixtures.fixture(root/'tools','1.0.0')
            _,_,two=fixtures.fixture(root/'tools','2.0.0')
            window=Window(ToolStore(root/'config'),root/'tools',autoload=False)
            window.catalog.data['packages']=[one,two];window.navigate('store')
            with patch('desktop.QMessageBox.question',return_value=QMessageBox.No):window.uninstall_tool('repo-42')
            self.assertEqual(len(window.installed()),2)
            with patch('desktop.QMessageBox.question',return_value=QMessageBox.Yes):window.uninstall_tool('repo-42')
            self.assertEqual(window.installed(),[])
            window.navigate('library');self.assertTrue(window.summary.text().startswith('0 款'))
            window.close()
