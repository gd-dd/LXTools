"""Persistent portable profiles and user-controlled check scheduling."""
import os,json,time
from pathlib import Path
TTL=6*3600
class Policy:
 def __init__(self,root):
  self.path=Path(root)/'update-policy.json'
  try:self.data=json.loads(self.path.read_text('utf-8'))
  except (OSError,ValueError):self.data={'mode':'background','lastAttempt':0}
 def save(self):
  self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.data),encoding='utf-8');temp.replace(self.path)
 def claim(self,force=False):
  now=time.time()
  if not force and (self.data.get('mode')=='manual' or 0<=now-self.data.get('lastAttempt',0)<TTL):return False
  self.data['lastAttempt']=now;self.save();return True

def profile(app_root,development=False):
 app_root=Path(app_root)
 if development:root=app_root/'runtime/development/profile'
 elif (app_root/'portable.json').is_file():
  data=json.loads((app_root/'portable.json').read_text('utf-8-sig'))
  if 'profilePath' in data:
   root=Path(data['profilePath'])
   if not root.is_absolute():raise ValueError('profilePath 必须是明确的绝对目录')
   root=root.resolve()
   if root==Path(root.anchor) or root==app_root.resolve():raise ValueError('profilePath 不能是磁盘根或程序根目录')
  else:
   relative=data.get('profile','data');root=(app_root/relative).resolve()
   if not root.is_relative_to(app_root.resolve()) or root==app_root.resolve():raise ValueError('便携相对配置必须是程序目录内的子目录')
 else:return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'LXTool'
 root.mkdir(parents=True,exist_ok=True)
 for name,child in [('LOCALAPPDATA','local'),('APPDATA','roaming'),('TEMP','temp'),('TMP','temp')]:
  folder=root/child;folder.mkdir(exist_ok=True);os.environ[name]=str(folder)
 return root
