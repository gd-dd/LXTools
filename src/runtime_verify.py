"""Opt-in offscreen frozen acceptance, all output under an explicit directory."""
import os,sys,json,time
from pathlib import Path

def run(root):
 root=root.resolve();root.mkdir(parents=True,exist_ok=True)
 for name in ('TEMP','TMP','APPDATA','LOCALAPPDATA'):
  folder=root/name;folder.mkdir(exist_ok=True);os.environ[name]=str(folder)
 os.environ['QT_QPA_PLATFORM']='offscreen'
 from PySide6.QtWidgets import QApplication
 from desktop import Window
 from core import ToolStore
 from update_policy import Policy,profile
 from lx_protocol import discover_packages
 from native_panels import NativePanelHandle
 from PySide6.QtWidgets import QWidget
 import github_api
 calls=[]
 def offline(*args,**kwargs):calls.append(args[0]);raise TimeoutError('isolated offline test')
 github_api.github_json=offline
 app=QApplication.instance() or QApplication([])
 entry=root/'entry';entry.mkdir(exist_ok=True);(entry/'portable.json').write_text(json.dumps({'profilePath':str(root/'profile')}))
 resolved=profile(entry);assert resolved==root/'profile'
 policy=Policy(root/'profile');policy.data['mode']='manual';policy.save()
 start=time.perf_counter();window=Window(ToolStore(root/'profile'),root/'tools',autoload=True);window.navigate('library');app.processEvents()
 report={'frozen':bool(getattr(sys,'frozen',False)),'windowSeconds':time.perf_counter()-start,'tools':[]}
 window.background_check();report['manualNetworkCalls']=calls[:]
 packages,errors=discover_packages(root/'tools');report['discoveryErrors']=errors
 for tool in packages:
  try:
   if tool['panelData']['type']=='native':
    parent=QWidget();handle=NativePanelHandle(tool,root/'profile',parent);app.processEvents();handle.shutdown();parent.deleteLater()
   else:window.workspace.display(tool);app.processEvents();window.workspace.shutdown()
   report['tools'].append({'id':tool['id'],'version':tool['version'],'ok':True})
  except Exception as error:report['tools'].append({'id':tool['id'],'ok':False,'error':str(error)})
 window.close();report['ok']=not calls and not errors and all(t['ok'] for t in report['tools'])
 (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 return 0 if report['ok'] else 1
