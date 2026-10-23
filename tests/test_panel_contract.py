import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton, QLabel
from panel_spec import validate_panel, panel_for
from tool_panels import ToolWorkspace, discover_tools
import test_tool_panels


class PanelContractTests(unittest.TestCase):
    def test_examples_and_legacy(self):
        for path in Path('docs/examples').glob('tool-*.json'):
            panel_for(json.loads(path.read_text('utf-8')))
        self.assertEqual(panel_for({})['type'], 'declarative')
        self.assertEqual(validate_panel({'type': 'none'}), {'type': 'none'})

    def test_reject_unknown_or_executable_content(self):
        for value in [None, {}, {'type':'html'}, {'type':'none','title':'x'},
                      {'type':'declarative','sections':[]},
                      {'type':'declarative','sections':[{'actions':[]}]},
                      {'type':'declarative','sections':[{'actions':[{'action':'shell'}]}]},
                      {'type':'declarative','sections':[{'actions':[{'action':'launchHost','command':'anything'}]}]}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_panel(value)

    def test_render_dispatch_none_and_invalid_isolation(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, data = test_tool_panels.ToolPanelTests().fixture(root)
            data['panel']={'type':'declarative','title':'作者的面板','sections':[{'text':'<b>纯文本</b>','actions':[{'action':'launchHost','label':'作者的按钮'}]}]}
            manifest=package/'tool.json'
            manifest.write_text(json.dumps(data),'utf-8')
            workspace=ToolWorkspace(root/'tools',root/'config')
            workspace.show(); app.processEvents()
            page=workspace.pages.currentWidget()
            buttons=page.findChildren(QPushButton)
            self.assertEqual([b.text() for b in buttons], ['作者的按钮'])
            with patch.object(workspace,'launch',return_value='launched') as launch:
                buttons[0].click()
                launch.assert_called_once_with()
            data['panel']={'type':'none'}
            manifest.write_text(json.dumps(data),'utf-8')
            workspace.reload(); app.processEvents()
            self.assertEqual(workspace.pages.currentWidget().findChildren(QPushButton),[])
            self.assertEqual(workspace.list.count(),1)
            data['panel']={'type':'invalid'}
            manifest.write_text(json.dumps(data),'utf-8')
            tools,errors=discover_tools(root/'tools')
            self.assertEqual(tools,[])
            self.assertIn('panel.type',errors[0])
            workspace.close()


