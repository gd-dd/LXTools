import tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import github_auth as auth
class AuthTests(unittest.TestCase):
 def test_encrypted_roundtrip_and_logout(self):
  with tempfile.TemporaryDirectory() as root:
   account={'login':'test','token':'secret-test-value'};auth.save(root,account)
   self.assertNotIn(b'secret-test-value',(Path(root)/'github-account.bin').read_bytes())
   self.assertEqual(auth.load(root),account);auth.logout(root);self.assertEqual(auth.load(root),{})
 def test_pending_and_denied(self):
  with patch.object(auth,'post',return_value={'error':'slow_down'}):self.assertEqual(auth.poll('test'),{'pending':'slow_down'})
  with patch.object(auth,'post',return_value={'error':'access_denied'}):
   with self.assertRaises(ValueError):auth.poll('test')
 def test_user_identity(self):
  with patch.object(auth,'post',return_value={'access_token':'test'}),patch('github_api.github_json',return_value={'login':'tester'}):self.assertEqual(auth.poll('test')['login'],'tester')
