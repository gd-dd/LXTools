import tempfile,unittest,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import storage_cleanup as clean
class CleanupTests(unittest.TestCase):
 def test_boundaries(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);cache=root/'cache';cache.mkdir();(cache/'data').write_bytes(b'123')
   with self.assertRaises(ValueError):clean.remove(root,root)
   with self.assertRaises(ValueError):clean.remove(root.parent,root)
   self.assertEqual(clean.size(clean.checked(cache,root)),3);clean.remove(cache,root);self.assertFalse(cache.exists())
 def test_account_states(self):
  os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
  from PySide6.QtWidgets import QApplication
  from desktop import Window
  from core import ToolStore
  app=QApplication.instance() or QApplication([])
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);window=Window(ToolStore(root/'profile'),root/'tools',autoload=False)
   self.assertFalse(window.login_button.isHidden());self.assertTrue(window.logout_button.isHidden())
   window.login_session={};window.login_code.setText('ABCD-EFGH');window.refresh_account_ui()
   self.assertFalse(window.login_code.isHidden());self.assertTrue(window.login_button.isHidden())
   window.account={'login':'tester'};window.login_session=None;window.refresh_account_ui()
   self.assertTrue(window.login_code.isHidden());self.assertFalse(window.account_manage_button.isHidden())
   window.close()
