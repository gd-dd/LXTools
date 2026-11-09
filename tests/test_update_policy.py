import unittest,tempfile,os,json
from pathlib import Path
from unittest.mock import patch
from update_policy import Policy,profile
class PolicyTests(unittest.TestCase):
 def test_manual_ttl_and_restart(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Policy(tmp);p.data['mode']='manual';p.save();self.assertFalse(Policy(tmp).claim())
   self.assertTrue(p.claim(True));p.data['mode']='background';p.save();self.assertFalse(Policy(tmp).claim())
   with patch('update_policy.time.time',return_value=p.data['lastAttempt']+21601):self.assertTrue(Policy(tmp).claim())
 def test_portable_persists_and_rejects_escape(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ):
   root=Path(tmp);(root/'portable.json').write_text('{"profile":"data"}')
   self.assertEqual(profile(root),root.resolve()/'data');self.assertTrue(Path(os.environ['APPDATA']).is_relative_to(root.resolve()))
   (root/'portable.json').write_text(json.dumps({'profilePath':str(root/'external-profile'),'profile':'../ignored'}))
   self.assertEqual(profile(root),root.resolve()/'external-profile')
   (root/'portable.json').write_text('{"profile":"../escape"}')
   with self.assertRaises(ValueError):profile(root)

 def test_manual_and_slow_background_do_not_block_tools(self):
  import time
  from PySide6.QtWidgets import QApplication
  from PySide6.QtTest import QTest
  from desktop import Window
  from core import ToolStore
  app=QApplication.instance() or QApplication([])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);w=Window(ToolStore(root/'profile'),root/'tools',autoload=False)
   w.policy.data['mode']='manual'
   with patch('github_api.github_json') as network:
    w.background_check();self.assertEqual(network.call_count,0)
   w.policy.data['mode']='background'
   def slow(*a,**kw):time.sleep(.2);raise TimeoutError('offline')
   with patch('github_api.github_json',side_effect=slow) as network:
    start=time.perf_counter();w.background_check();w.background_check()
    self.assertLess(time.perf_counter()-start,.15);self.assertIsNone(w.job);self.assertTrue(w.sync_button.isEnabled())
    QTest.qWait(350);self.assertEqual(network.call_count,1);w.background_check();self.assertEqual(network.call_count,1)
   w.close()

 def test_update_preserves_custom_portable_and_tools(self):
  from updater import replace_program
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);stage=root/'stage';target=root/'app'
   for path in (stage,target):
    (path/'_internal').mkdir(parents=True);(path/'LXTool.exe').write_bytes(b'app')
   (target/'portable.json').write_text('{"profilePath":"E:/user-profile"}')
   (stage/'portable.json').write_text('{"profile":"data"}')
   (target/'tools').mkdir();(target/'tools/user-file').write_bytes(b'keep')
   replace_program(stage,target)
   self.assertIn('profilePath',(target/'portable.json').read_text());self.assertEqual((target/'tools/user-file').read_bytes(),b'keep')

 def test_relative_and_external_profile_stage(self):
  from updater import detach_stage,replace_program
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for mode in ('relative','external'):
    target=root/mode;target.mkdir();(target/'LXTool.exe').write_bytes(b'old');(target/'_internal').mkdir()
    data=target/'data' if mode=='relative' else root/'outside'
    stage=data/'client-updates/stage';(stage/'_internal').mkdir(parents=True);(stage/'LXTool.exe').write_bytes(b'new')
    (data/'user.json').write_text('keep');(target/'portable.json').write_text('custom')
    detached=detach_stage(stage,target);self.assertFalse(detached.is_relative_to(target))
    replace_program(detached,target);self.assertEqual((target/'LXTool.exe').read_bytes(),b'new')
    self.assertEqual((data/'user.json').read_text(),'keep');self.assertEqual((target/'portable.json').read_text(),'custom')
