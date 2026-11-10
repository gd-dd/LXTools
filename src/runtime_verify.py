"""Opt-in offscreen frozen acceptance, all output under an explicit directory."""
import os,sys,json,time
from pathlib import Path

def verify_download_resilience(root,app):
 """Fake transport only: exercise packaged reader, SHA media and worker signal."""
 import io,urllib.request,threading
 from urllib.error import HTTPError
 from http_transport import get_bytes,TransferFailed
 from github_api import github_commit_sha
 from desktop import Window
 from core import ToolStore
 checks={};requests=[];notices=[];results=[];threads=[]
 original=urllib.request.build_opener
 def response(body,length=5,media=None):
  value=io.BytesIO(body);value.headers={'Content-Length':str(length)}
  if media:value.headers['Content-Type']=media
  return value
 def open_once(request,**options):
  requests.append(request);threads.append(threading.get_ident())
  return response(b'wh' if len(requests)==1 else b'whole')
 window=Window(ToolStore(root/'profile'),root/'no-tools',autoload=False)
 try:
  main_thread=threading.get_ident()
  window.busy(lambda:get_bytes(lambda:urllib.request.Request('https://synthetic.invalid/file'),stage='synthetic complete GET',max_bytes=10,open_request=open_once),results.append,'synthetic retry test')
  window.job.progress.connect(notices.append)
  deadline=time.monotonic()+5
  while window.job is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
  checks['wholeBodyAfterFreshRetry']=results==[b'whole'] and len(requests)==2 and requests[0] is not requests[1]
  checks['retryProgressSignal']=bool(notices) or '2/3' in window.status.text()
  checks['retryRunsInWorker']=bool(threads) and all(item!=main_thread for item in threads)
  calls=[]
  def short(request,**options):calls.append(True);return response(b'wh')
  try:get_bytes(lambda:urllib.request.Request('https://synthetic.invalid/file'),stage='synthetic exhausted',max_bytes=10,open_request=short)
  except TransferFailed:checks['boundedFailureNoPartial']=len(calls)==3
  calls=[]
  def denied(request,**options):calls.append(True);raise HTTPError(request.full_url,403,'synthetic denied',{},None)
  try:get_bytes(lambda:urllib.request.Request('https://synthetic.invalid/file'),stage='synthetic permission',max_bytes=10,open_request=denied)
  except HTTPError:checks['permissionNotRetried']=len(calls)==1
  calls=[]
  try:get_bytes(lambda:urllib.request.Request('https://synthetic.invalid',data=b'not OAuth'),stage='synthetic nonGET',max_bytes=10,open_request=lambda *a,**k:calls.append(True))
  except ValueError:checks['postNeverOpened']=not calls
  class Sha:
   def open(self,request,**options):
    assert request.get_header('Accept')=='application/vnd.github.sha' and 'tags%2Fv1.0.0' in request.full_url
    return response(b'a'*40,40,'application/vnd.github.sha; charset=utf-8')
  urllib.request.build_opener=lambda *a,**k:Sha()
  checks['strictShaMedia']=github_commit_sha('gd-dd/example','tags/v1.0.0')=='a'*40
  assert len(checks)==7 and all(checks.values()),'synthetic download assertions failed'
  return {'ok':True,'checks':checks,'network':'synthetic in-process responses only; no remote requests'}
 finally:
  urllib.request.build_opener=original;window.close()

def verify_auth_recovery(root,app):
 """Synthetic sessions only; never read the interactive client's account."""
 import desktop,github_auth,github_api,urllib.request
 from urllib.error import HTTPError
 from core import ToolStore
 checks={};windows=[];browser_calls=[]
 original_api=github_api.github_json;original_opener=urllib.request.build_opener;original_browser=desktop.webbrowser.open
 desktop.webbrowser.open=lambda *args:browser_calls.append(True)
 def make_window(name,token):
  profile_root=root/name
  github_auth.save(profile_root,{'token':token,'login':'isolated-synthetic-user'})
  window=desktop.Window(ToolStore(profile_root),root/'no-tools',autoload=False);windows.append(window)
  return window,profile_root
 def wait(window):
  deadline=time.monotonic()+5
  while window.job is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
  assert window.job is None,'synthetic auth worker timed out'
 try:
  window,profile_root=make_window('expired','synthetic-expired')
  class RefusedCredential:
   def open(self,request,**kwargs):raise HTTPError(request.full_url,401,'synthetic invalid credential',{},None)
  urllib.request.build_opener=lambda *args,**kwargs:RefusedCredential()
  requests=[]
  def public_operation(token):
   requests.append(bool(token))
   if token:return original_api('/user',token)
   return 'anonymous-completed'
  window.busy(public_operation,lambda value:window.status.setText(value),'isolated auth verification',public=True);wait(window)
  checks['401AnonymousOnceAndCleared']=requests==[True,False] and not window.account and not (profile_root/'github-account.bin').exists()
  checks['explicitLoginButton']=not window.reauth_button.isHidden() and '重新登录' in window.login_button.text()
  window.reauth_button.click();checks['loginEntryNavigatesSettings']=window.pages.currentWidget()==window.settings
  window2,profile2=make_window('new-session','synthetic-new')
  window2.auth_epoch+=1
  window2.invalidate_account({'token':'synthetic-expired','epoch':0})
  checks['old401KeepsNewLogin']=window2.account.get('token')=='synthetic-new' and github_auth.load(profile2).get('token')=='synthetic-new'
  def offline(token):raise TimeoutError('synthetic network timeout')
  window2.busy(offline,lambda _:None,'isolated network verification',public=True);wait(window2)
  checks['networkKeepsLogin']=window2.account.get('token')=='synthetic-new' and github_auth.load(profile2).get('token')=='synthetic-new'
  reopened=desktop.Window(ToolStore(profile2),root/'no-tools',autoload=False);windows.append(reopened)
  checks['persistedLoginReopens']=reopened.account.get('token')=='synthetic-new'
  checks['noAutomaticBrowser']=not browser_calls
  assert all(checks.values()),'synthetic auth assertions failed'
  return {'ok':True,'checks':checks,'credentials':'synthetic only; token values omitted','automaticRefreshImplemented':False}
 finally:
  urllib.request.build_opener=original_opener;desktop.webbrowser.open=original_browser
  for window in windows:window.close()

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
 real_github_json=github_api.github_json;github_api.github_json=offline
 entry=root/'entry';entry.mkdir(exist_ok=True);(entry/'portable.json').write_text(json.dumps({'profilePath':str(root/'profile')}))
 resolved=profile(entry);assert resolved==root/'profile'
 app=QApplication.instance() or QApplication([])
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
 window.close()
 github_api.github_json=real_github_json
 try:report['authRecovery']=verify_auth_recovery(root/'synthetic-auth',app)
 except Exception as error:report['authRecovery']={'ok':False,'error':str(error)}
 try:report['downloadResilience']=verify_download_resilience(root/'synthetic-download',app)
 except Exception as error:report['downloadResilience']={'ok':False,'error':str(error)}
 report['ok']=not calls and not errors and all(t['ok'] for t in report['tools']) and report['authRecovery']['ok'] and report['downloadResilience']['ok']
 (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 return 0 if report['ok'] else 1
