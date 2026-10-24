import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication
from lx_protocol import validate_manifest,validate_panel
from session_panels import SessionPanel
import test_repository_protocol as fixtures


class SessionPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def make(self,root):
        package,m,entry=fixtures.fixture(root)
        m['files']['provider.exe']='0'*64
        m['actions']['provider']={'type':'process','executable':'provider.exe','arguments':[]}
        panel={'type':'declarative','session':{'provider':'provider','application':'editor','tools':[
            {'id':'one','label':'工具一','description':'第一项'}, {'id':'two','label':'工具二'}]}}
        validate_manifest(m);validate_panel(panel,m)
        return dict(m,root=package,panelData=panel,id='repo-42'),panel

    def test_provider_is_packaged_and_no_html_or_duplicate_tools(self):
        with tempfile.TemporaryDirectory() as root:
            tool,panel=self.make(root)
            for change in [{'provider':'run'},{'application':'missing'}, {'tools':[{'id':'../escape','label':'x'}]},
                           {'tools':[{'id':'one','label':'x'},{'id':'one','label':'y'}]}, {'html':'<script/>'}]:
                candidate=copy.deepcopy(panel);candidate['session'].update(change)
                with self.subTest(change=change),self.assertRaises(ValueError):validate_panel(candidate,tool)

    def test_render_does_not_execute_provider_and_targets_are_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            tool,panel=self.make(root)
            w=SessionPanel(tool,panel['session'],{},lambda _:None)
            w.show();self.app.processEvents()
            self.assertEqual(w.process.state(),QProcess.NotRunning)
            self.assertTrue(all(not b.isEnabled() for b in w.buttons.values()))
            data={'sessions':[{'id':'a','title':'窗口 A','state':'ready'}, {'id':'b','title':'窗口 B','state':'connecting'}], 'events':[], 'pending':[]}
            w.apply_response(data);self.assertEqual(w.active_id,'a')
            with patch.object(w,'command') as command:
                w.buttons['one'].click();command.assert_called_once_with('run',sessionId='a',toolId='one')
            w.list.setCurrentItem(w.list.topLevelItem(1))
            self.assertFalse(w.buttons['two'].isEnabled())
            data['sessions'][1]['state']='ready';w.apply_response(data)
            self.assertEqual(w.active_id,'b');self.assertTrue(w.buttons['two'].isEnabled())
            data['pending']=[{'sessionId':'b','toolId':'two'}];w.apply_response(data)
            self.assertFalse(w.buttons['two'].isEnabled());self.assertTrue(w.buttons['one'].isEnabled())
            data['sessions']=[];data['pending']=[];w.apply_response(data)
            self.assertIsNone(w.active_id);self.assertTrue(w.empty.isVisible())
            w.shutdown();w.close()

    def test_invalid_provider_state_rejected_and_panel_shutdown_preserves_hosts(self):
        with tempfile.TemporaryDirectory() as root:
            tool,panel=self.make(root);w=SessionPanel(tool,panel['session'],{},lambda _:None)
            for data in [{'sessions':[{'id':'a','state':'execute'}]}, {'sessions':[{'id':'a','state':'ready'},{'id':'a','state':'ready'}]},
                         {'sessions':[],'pending':[{'sessionId':'a','toolId':'bad'}]}]:
                with self.subTest(data=data),self.assertRaises(ValueError):w.apply_response(data)
            with patch.object(w.process,'kill') as kill:
                w.shutdown();kill.assert_not_called()
            w.close()


if __name__=='__main__':unittest.main()
