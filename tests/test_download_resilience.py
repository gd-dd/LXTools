"""Real loopback HTTP truncation; no remote requests or real credentials."""
import hashlib
import http.client
import io
import json
import socket
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.parse
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import github_api as api
import repository_source as source
from http_transport import get_bytes,TransferFailed,progress_reporting
from core import ToolStore
from updater import prepare_update
import test_repository_protocol as fixtures


@contextmanager
def server(spec):
    """spec(request number, path, headers) -> body/length/status/chunked response."""
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*a):pass
        def do_GET(self):
            requests.append((self.path,dict(self.headers)))
            item=spec(len(requests),self.path,self.headers)
            body=item.get('body',b'');self.send_response(item.get('status',200))
            if item.get('chunked'):self.send_header('Transfer-Encoding','chunked')
            elif item.get('length',len(body)) is not None:self.send_header('Content-Length',str(item.get('length',len(body))))
            self.send_header('Connection','close')
            for name,value in item.get('headers',{}).items():self.send_header(name,value)
            self.end_headers()
            try:self.wfile.write(body);self.wfile.flush();self.connection.shutdown(socket.SHUT_RDWR)
            except (OSError,ValueError):pass
            self.close_connection=True
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    # Explicitly bypass proxies for this loopback-only test client, not the OS.
    local=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base=f'http://127.0.0.1:{http.server_port}'
    def reroute(request,**options):
        url=request if isinstance(request,str) else request.full_url
        path=urllib.parse.urlparse(url).path
        headers={} if isinstance(request,str) else dict(request.header_items())
        return local.open(urllib.request.Request(base+path,headers=headers),**options)
    try:yield base,requests,local,reroute
    finally:http.shutdown();http.server_close();thread.join(2)


class CompleteGetTests(unittest.TestCase):
    def test_real_short_200_retries_with_new_request_and_discards_fragment(self):
        payload=b'correct-complete-body';notices=[];factories=[]
        with server(lambda n,*_: {'body':payload[:4] if n==1 else payload,'length':len(payload)}) as (url,requests,local,_):
            def factory():
                request=urllib.request.Request(url+'/file');factories.append(request);return request
            with progress_reporting(notices.append):
                result=get_bytes(factory,stage='下载测试包',max_bytes=100,expected_size=len(payload),open_request=local.open)
        self.assertEqual(result,payload);self.assertEqual(len(requests),2)
        self.assertIsNot(factories[0],factories[1]);self.assertIn('2/3',notices[0])

    def test_continuous_real_truncation_stops_at_three_and_reports_stage(self):
        with server(lambda *args:{'body':b'partial','length':40}) as (url,requests,local,_):
            with self.assertRaises(TransferFailed) as caught:
                get_bytes(lambda:urllib.request.Request(url+'/always'),stage='读取清单',max_bytes=100,open_request=local.open)
        self.assertEqual(len(requests),3);self.assertEqual(caught.exception.attempts,3)
        self.assertIn('读取清单',str(caught.exception));self.assertIn('重试已用尽',str(caught.exception));self.assertIn('不会注销登录',str(caught.exception))

    def test_real_incomplete_chunk_then_success(self):
        with server(lambda n,*args:{'body':b'5\r\nabc','chunked':True} if n==1 else {'body':b'whole'}) as (url,requests,local,_):
            self.assertEqual(get_bytes(lambda:urllib.request.Request(url),stage='测试',max_bytes=20,open_request=local.open),b'whole')
        self.assertEqual(len(requests),2)

    def test_short_without_content_length_uses_known_asset_size(self):
        with server(lambda n,*args:{'body':b'xy' if n==1 else b'whole','length':None}) as (url,requests,local,_):
            self.assertEqual(get_bytes(lambda:urllib.request.Request(url),stage='附件',max_bytes=20,expected_size=5,open_request=local.open),b'whole')
        self.assertEqual(len(requests),2)

    def test_http_permission_rate_limit_and_not_found_are_not_retried(self):
        for code in (401,403,404,429):
            with self.subTest(code=code),server(lambda *args:{'status':code}) as (url,requests,local,_):
                with self.assertRaises(HTTPError):get_bytes(lambda:urllib.request.Request(url),stage='查询',max_bytes=100,open_request=local.open)
                self.assertEqual(len(requests),1)

    def test_size_violation_and_complete_but_wrong_expected_size_do_not_retry(self):
        for body,limit,expected in ((b'oversize',3,None),(b'wrong',20,6)):
            with server(lambda *args:{'body':body}) as (url,requests,local,_):
                with self.assertRaises(ValueError):get_bytes(lambda:urllib.request.Request(url),stage='附件',max_bytes=limit,expected_size=expected,open_request=local.open)
                self.assertEqual(len(requests),1)

    def test_connection_reset_and_permission_error_classification(self):
        calls=[]
        def reset_then_whole(request,**options):
            calls.append(True)
            if len(calls)==1:raise ConnectionResetError('synthetic reset')
            return io.BytesIO(b'whole')
        self.assertEqual(get_bytes(lambda:urllib.request.Request('https://unused.invalid'),stage='查询',max_bytes=10,open_request=reset_then_whole),b'whole')
        self.assertEqual(len(calls),2)
        with patch('http_transport.time.sleep') as sleep:
            with self.assertRaises(PermissionError):get_bytes(lambda:urllib.request.Request('https://unused.invalid'),stage='查询',max_bytes=10,open_request=lambda *a,**k:(_ for _ in ()).throw(PermissionError('denied')))
            sleep.assert_not_called()

    def test_post_is_rejected_before_open_or_retry_and_signed_redirect_never_downgrades(self):
        from http_transport import HttpsOnlyRedirect
        with patch('http_transport.urllib.request.urlopen') as opener,patch('http_transport.time.sleep') as sleep:
            with self.assertRaises(ValueError):get_bytes(lambda:urllib.request.Request('https://unused.invalid',data=b'not retried'),stage='测试',max_bytes=100)
            opener.assert_not_called();sleep.assert_not_called()
        handler=HttpsOnlyRedirect();request=urllib.request.Request('https://signed.example/a',headers={'Authorization':'Bearer synthetic'})
        redirected=handler.redirect_request(request,None,302,'redirect',{},'https://another.example/b')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(ValueError):handler.redirect_request(request,None,302,'redirect',{},'http://another.example/b')


class GitHubGetPathTests(unittest.TestCase):
    def test_ready_update_waits_for_both_jobs_and_applies_once_in_either_finish_order(self):
        from desktop import Window,Job
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        for background_first in (False,True):
            with self.subTest(background_first=background_first),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);window=Window(ToolStore(root/'profile'),root/'tools',autoload=False)
                window.check_job=Job(lambda:None);window.job=Job(lambda:None)
                stage=root/'synthetic-stage'
                with patch('desktop.subprocess.Popen') as process,patch.object(window,'close') as close:
                    window.restart_updated(stage);process.assert_not_called();close.assert_not_called()
                    if background_first:window.background_finished()
                    else:window.idle()
                    process.assert_not_called();close.assert_not_called();self.assertEqual(window.pending_restart,stage)
                    if background_first:window.idle()
                    else:window.background_finished()
                    app.processEvents();process.assert_called_once();close.assert_called_once();self.assertIsNone(window.pending_restart)
                window.close()

    def test_closing_during_background_retry_never_waits_on_ui_thread(self):
        import time
        from desktop import Window
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window=Window(ToolStore(Path(tmp)/'profile'),Path(tmp)/'tools',autoload=False)
            def slow(*a,**k):time.sleep(.25);return {'tag_name':'v0.0.7'}
            with patch('github_api.github_json',side_effect=slow):
                window.background_check();start=time.perf_counter();window.close()
                self.assertLess(time.perf_counter()-start,.1);self.assertIsNotNone(window.check_job)
                deadline=time.monotonic()+3
                while window.check_job is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
                self.assertIsNone(window.check_job)
            window.close()

    def test_actual_worker_retry_keeps_ui_responsive_and_keeps_account(self):
        import time
        import github_auth
        from desktop import Window
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);github_auth.save(root/'profile',{'token':'synthetic','login':'tester'})
                window=Window(ToolStore(root/'profile'),root/'tools',autoload=False)
                ticks=[];results=[];main_thread=threading.get_ident();workers=[]
                with server(lambda n,*args:{'body':b'wh' if fail or n==1 else b'whole','length':5}) as (url,requests,local,_):
                    def op(request,**options):workers.append(threading.get_ident());return local.open(request,**options)
                    QTimer.singleShot(25,lambda:ticks.append(True))
                    window.busy(lambda token:get_bytes(lambda:urllib.request.Request(url),stage='测试工具附件',max_bytes=10,open_request=op),results.append,'download',public=True)
                    deadline=time.monotonic()+5
                    while window.job is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
                    self.assertIsNone(window.job);self.assertTrue(ticks);self.assertTrue(all(item!=main_thread for item in workers))
                    self.assertEqual(window.account['token'],'synthetic');self.assertEqual(github_auth.load(root/'profile')['token'],'synthetic')
                    self.assertTrue(window.reauth_button.isHidden())
                    if fail:self.assertEqual(len(requests),3);self.assertIn('重试已用尽',window.status.text());self.assertEqual(results,[])
                    else:self.assertEqual(results,[b'whole']);self.assertEqual(len(requests),2)
                window.close()

    def test_real_api_json_truncation_135363_of_319485_then_complete(self):
        base=json.dumps({'sha':'a'*40,'padding':''}).encode();body=json.dumps({'sha':'a'*40,'padding':'x'*(319485-len(base))}).encode()
        self.assertEqual(len(body),319485)
        with server(lambda n,*args:{'body':body[:135363] if n==1 else body,'length':len(body)}) as (_,requests,_,reroute):
            class Opener:
                def open(self,request,**options):return reroute(request,**options)
            with patch('github_api.urllib.request.build_opener',return_value=Opener()):self.assertEqual(api.github_json('/example')['sha'],'a'*40)
        self.assertEqual(len(requests),2)

    def test_sha_only_media_ref_and_format_are_strict(self):
        with server(lambda *args:{'body':b'a'*40,'headers':{'Content-Type':'application/vnd.github.sha; charset=utf-8'}}) as (_,requests,_,reroute):
            class Opener:
                def open(self,request,**options):return reroute(request,**options)
            with patch('github_api.urllib.request.build_opener',return_value=Opener()):
                self.assertEqual(api.github_commit_sha('gd-dd/example','tags/v1.0.0'),'a'*40)
            self.assertIn('tags%2Fv1.0.0',requests[0][0]);self.assertEqual(requests[0][1]['Accept'],'application/vnd.github.sha')
            self.assertNotIn('If-None-Match',requests[0][1])
        for body,media in ((b'"'+b'a'*40+b'"','application/vnd.github.sha'),(b'a'*40,'application/json'),(b'<html>error</html>','application/vnd.github.sha')):
            response=io.BytesIO(body);response.headers={'Content-Type':media}
            class BadOpener:
                def open(self,*a,**k):return response
            with patch('github_api.urllib.request.build_opener',return_value=BadOpener()):
                with self.assertRaises(ValueError):api.github_commit_sha('gd-dd/example','tags/v1.0.0')
        with self.assertRaises(ValueError):api.github_commit_sha('gd-dd/example','ambiguous-tag')

    def test_real_raw_resource_recovers_without_api_or_fragment_merge(self):
        body=b'{"manifest":"complete"}'
        with server(lambda n,*args:{'body':body[:4] if n==1 else body,'length':len(body)}) as (_,requests,_,reroute):
            with patch('repository_source.urllib.request.urlopen',side_effect=reroute),patch('repository_source.github_json') as api_call:
                self.assertEqual(source.read_json('gd-dd/example','.lxtool/manifest.json','a'*40),{'manifest':'complete'});api_call.assert_not_called()
        self.assertEqual(len(requests),2)

    def test_raw_domain_fallback_uses_same_ref_and_total_budget_three(self):
        with server(lambda *args:{'body':b'partial','length':100}) as (_,requests,_,reroute):
            import base64
            with patch('repository_source.urllib.request.urlopen',side_effect=reroute),patch('repository_source.github_json',return_value={'encoding':'base64','content':base64.b64encode(b'complete').decode()}) as alternate:
                self.assertEqual(source.read_bytes('gd-dd/example','payload.txt','a'*40),b'complete')
                self.assertEqual(len(requests),2);self.assertIn('ref='+'a'*40,alternate.call_args.args[0]);self.assertEqual(alternate.call_args.kwargs,{'attempts':1})

    def test_index_failure_retains_previous_memory_and_cache_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,m,entry=fixtures.fixture(root/'fixture');fixtures.release_fixture(package,m,entry)
            body=json.dumps({'schemaVersion':2,'packages':[entry],'warnings':[]}).encode()
            with server(lambda *args:{'body':body}) as (url,_,_,_):
                catalog=source.RepositoryCatalog(root/'profile')
                with patch('repository_source.INDEX_URL',url):catalog.sync()
            before=catalog.cache.read_bytes();previous=catalog.data
            with server(lambda *args:{'body':body[:12],'length':len(body)}) as (url,requests,_,_):
                with patch('repository_source.INDEX_URL',url):
                    with self.assertRaises(TransferFailed):catalog.sync()
            self.assertEqual(len(requests),3);self.assertEqual(catalog.cache.read_bytes(),before);self.assertIs(catalog.data,previous)

    def test_signed_asset_is_refetched_each_retry_and_digest_mismatch_is_fatal(self):
        body=b'validated zip bytes';asset={'id':7,'size':len(body),'digest':'sha256:'+hashlib.sha256(body).hexdigest()};initial=[];signed=[]
        class Redirect:
            def open(self,request,**options):
                initial.append(request)
                raise HTTPError(request.full_url,302,'signed',{'Location':f'https://signed.example/attempt-{len(initial)}?secret=not-logged'},None)
        with server(lambda n,*args:{'body':body[:4] if n==1 else body,'length':len(body)}) as (_,requests,_,reroute):
            def redirect_read(url,**options):signed.append(url);return reroute(url,**options)
            with patch('repository_source.urllib.request.build_opener',return_value=Redirect()),patch('repository_source.open_https',side_effect=redirect_read):
                self.assertEqual(source.download_release_asset('gd-dd/example',asset,'synthetic',tag='v1.0.0'),body)
        self.assertEqual(len(initial),2);self.assertNotEqual(signed[0],signed[1]);self.assertIsNot(initial[0],initial[1])
        initial=[]
        class Whole:
            def open(self,request,**options):initial.append(request);return io.BytesIO(body)
        with patch('repository_source.urllib.request.build_opener',return_value=Whole()):
            with self.assertRaises(ValueError):source.download_release_asset('gd-dd/example',dict(asset,digest='sha256:'+'0'*64),tag='v1.0.0')
        self.assertEqual(len(initial),1)

    def test_failed_zip_download_keeps_old_installation_and_never_creates_new_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,m,entry=fixtures.fixture(root/'fixture');body,release=fixtures.release_fixture(package,m,entry)
            old=root/'tools/old-version/keep.txt';old.parent.mkdir(parents=True);old.write_bytes(b'old data')
            with server(lambda *args:{'body':body[:8],'length':len(body)}) as (_,requests,_,reroute):
                class Opener:
                    def open(self,request,**options):return reroute(request,**options)
                with patch('repository_source.github_json',return_value=release),patch('repository_source.github_commit_sha',return_value='a'*40),patch('repository_source.read_json',return_value=m),patch('repository_source.urllib.request.build_opener',return_value=Opener()):
                    with self.assertRaises(TransferFailed):source.install_repository(entry,root/'tools')
            self.assertEqual(len(requests),3);self.assertEqual(old.read_bytes(),b'old data');self.assertEqual(list((root/'tools').iterdir()),[old.parent])

    def test_self_update_real_zip_retry_and_existing_cache_preservation(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('LXTool/LXTool.exe',b'synthetic exe, not executed');archive.writestr('LXTool/_internal/runtime.txt',b'synthetic')
        body=buffer.getvalue();asset={'id':99,'name':'LXTool-windows-x64.zip','size':len(body),'digest':'sha256:'+hashlib.sha256(body).hexdigest()}
        release={'tag_name':'v99.0.0','draft':False,'prerelease':False,'assets':[asset]}
        for always_fail in (True,False):
            with self.subTest(always_fail=always_fail),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);keep=root/'client-updates/packages/old/keep.bin';keep.parent.mkdir(parents=True);keep.write_bytes(b'keep')
                counts=[]
                class ApiOpener:
                    def open(self,request,**options):
                        if request.get_header('Accept')=='application/octet-stream':
                            counts.append(True);raise HTTPError(request.full_url,302,'signed',{'Location':f'https://signed.example/{len(counts)}'},None)
                        value=asset if '/releases/assets/' in request.full_url else [release]
                        return io.BytesIO(json.dumps(value).encode())
                with server(lambda n,*args:{'body':body[:5] if always_fail or n==1 else body,'length':len(body)}) as (_,requests,_,reroute):
                    with patch('core.urllib.request.build_opener',return_value=ApiOpener()),patch('core.open_https',side_effect=reroute):
                        if always_fail:
                            with self.assertRaises(TransferFailed):prepare_update(root)
                        else:
                            tag,stage=prepare_update(root);self.assertEqual(tag,'v99.0.0');self.assertTrue((stage/'LXTool.exe').is_file())
                self.assertEqual(len(counts),3 if always_fail else 2);self.assertEqual(keep.read_bytes(),b'keep')


if __name__=='__main__':unittest.main()
