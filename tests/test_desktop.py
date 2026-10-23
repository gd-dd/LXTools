import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication
from desktop import Window
from core import ToolStore


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_filter_select_and_version_display(self):
        with tempfile.TemporaryDirectory() as root:
            store = ToolStore(root)
            store.add('example/unity', 'Unity')
            store.add('example/max', '3ds Max')
            window = Window(store)
            window.show()
            self.app.processEvents()
            self.assertEqual(window.tools.count(), 2)
            window.category.setCurrentText('Unity')
            self.assertEqual(window.tools.count(), 1)
            window.tools.setCurrentRow(0)
            self.assertEqual(window.heading.text(), 'example/unity')
            window.show_releases([{'tag': 'v1', 'prerelease': False, 'assets': [{'id': 123, 'name': 'test.zip', 'size': 100}]}])
            self.assertEqual(window.remote.item(0).data(256), 123)
            window.search.setText('missing')
            self.assertEqual(window.tools.count(), 0)
            window.close()


if __name__ == '__main__':
    unittest.main()
