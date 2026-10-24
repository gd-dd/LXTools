import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from gold_effect import GoldButton


class GoldEffectTests(unittest.TestCase):
    def test_selected_edge_animates_without_blocking_click_and_stops_when_hidden(self):
        app=QApplication.instance() or QApplication([])
        button=GoldButton('Selected');button.resize(180,48);button.setCheckable(True);button.setChecked(True)
        button.show();app.processEvents()
        before=button.grab().toImage()
        QTest.qWait(160)
        after=button.grab().toImage()
        self.assertNotEqual(before,after)
        clicked=[];button.clicked.connect(lambda:clicked.append(True));button.click()
        self.assertEqual(clicked,[True])
        button.hide();self.assertFalse(button.timer.isActive());button.close()
