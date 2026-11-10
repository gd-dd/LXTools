"""Synthetic credentials only; all persistence stays in the test temp root."""
import hashlib
import io
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import github_api as api
import github_auth as auth
import repository_source as source
from core import ToolStore
from desktop import Job, Window
from PySide6.QtWidgets import QApplication
import test_repository_protocol as fixtures


def http(code,headers=None,url='https://api.github.com/repos/gd-dd/example'):
    return HTTPError(url,code,'synthetic error',headers or {},None)


class TransportRecoveryTests(unittest.TestCase):
    def test_only_authenticated_github_401_expires_and_secrets_are_not_in_repr(self):
        class Opener:
            def open(self,*a,**kw):raise http(401)
        with patch('github_api.urllib.request.build_opener',return_value=Opener()):
            with self.assertRaises(api.AuthenticationExpired) as caught:api.github_json('/user','synthetic-secret')
            self.assertNotIn('synthetic-secret',str(caught.exception)+repr(caught.exception))
            with self.assertRaises(HTTPError):api.github_json('/user')
        self.assertFalse(api.authenticated_error(http(401,url='https://other.example/test'),'synthetic-secret'))

    def test_public_action_retries_once_and_never_retries_permissions_or_network(self):
        calls=[];notices=[]
        def operation(token):
            calls.append(token)
            if token:raise api.AuthenticationExpired(token)
            return 'verified public result'
        self.assertEqual(api.public_request(operation,'old',lambda:notices.append(True)),'verified public result')
        self.assertEqual(calls,['old',None]);self.assertEqual(notices,[True])
        for error in (http(403,{'X-RateLimit-Remaining':'0'}),http(403),http(429),TimeoutError(),URLError('offline')):
            calls=[];notices=[]
            def fail(token):calls.append(token);raise error
            with self.assertRaises(type(error)):api.public_request(fail,'old',lambda:notices.append(True))
            self.assertEqual(calls,['old']);self.assertEqual(notices,[])
        calls=[]
        def denied_anonymous(token):
            calls.append(token)
            if token:raise api.AuthenticationExpired(token)
            raise http(403)
        with self.assertRaises(HTTPError):api.public_request(denied_anonymous,'old')
        self.assertEqual(calls,['old',None])

    def test_metadata_redirect_never_forwards_token_to_another_host(self):
        request=Request('https://api.github.com/repos/gd-dd/example',headers={'Authorization':'Bearer synthetic'})
        redirect=api.GitHubRedirect()
        other=redirect.redirect_request(request,None,302,'redirect',{},'https://other.example/path')
        same=redirect.redirect_request(request,None,302,'redirect',{},'https://api.github.com/repos/gd-dd/renamed')
        self.assertIsNone(other.get_header('Authorization'));self.assertEqual(same.get_header('Authorization'),'Bearer synthetic')
        with self.assertRaises(ValueError):redirect.redirect_request(request,None,302,'redirect',{},'http://other.example/path')

    def test_actual_local_refused_proxy_is_network_not_expired(self):
        # Bound but not listening: deterministic local refusal, no external request.
        with socket.socket() as closed_service:
            closed_service.bind(('127.0.0.1',0));port=closed_service.getsockname()[1]
            with patch.dict(os.environ,{'https_proxy':f'http://127.0.0.1:{port}'},clear=True):
                with self.assertRaises(URLError) as caught:api.github_json('/rate_limit')
        message=api.error_message(caught.exception)
        self.assertIn('10061',message);self.assertIn('代理',message);self.assertNotIsInstance(caught.exception,api.AuthenticationExpired)

    def test_rate_limit_permission_and_timeout_messages_are_distinct(self):
        self.assertIn('额度已用尽',api.error_message(http(403,{'X-RateLimit-Remaining':'0'})))
        self.assertIn('尚不能确定',api.error_message(http(403)))
        self.assertIn('限流',api.error_message(http(429)))
        self.assertIn('保留 GitHub 登录',api.error_message(URLError(TimeoutError())))

    def test_update_transport_retains_authentication_classification(self):
        class Opener:
            def open(self,*a,**kw):raise http(401)
        with tempfile.TemporaryDirectory() as tmp:
            store=ToolStore(tmp);tool={'id':'client'};store.tokens['client']='synthetic'
            with patch('core.urllib.request.build_opener',return_value=Opener()):
                with self.assertRaises(api.AuthenticationExpired):store.request(tool,'/repos/gd-dd/LXTools/releases')

    def test_fallback_installer_still_validates_release_commit_and_asset_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,manifest,entry=fixtures.fixture(root/'fixture')
            payload,release=fixtures.release_fixture(package,manifest,entry)
            calls=[]
            def github(path,token=None):
                calls.append((path,token))
                if token:raise api.AuthenticationExpired(token)
                return {'sha':'a'*40} if '/commits/' in path else release
            def commit(repository,ref,token=None):
                calls.append(('sha-only',token));return 'a'*40
            class Opener:
                def open(self,*a,**kw):return io.BytesIO(payload)
            with patch('repository_source.github_json',side_effect=github),patch('repository_source.github_commit_sha',side_effect=commit),patch('repository_source.read_json',return_value=manifest),patch('repository_source.urllib.request.build_opener',return_value=Opener()):
                installed=api.public_request(lambda token:source.install_repository(entry,root/'installed',token),'old')
                self.assertTrue((Path(installed)/'payload.txt').is_file())
                self.assertEqual([token for _,token in calls],['old',None,None])
                entry['commit']='b'*40
                with self.assertRaisesRegex(ValueError,'提交已变化'):
                    api.public_request(lambda token:source.install_repository(entry,root/'bad-commit',token),'old')
                self.assertFalse((root/'bad-commit').exists())
                entry['commit']='a'*40;entry['releaseAsset']['digest']='sha256:'+'0'*64
                with self.assertRaises(ValueError):
                    api.public_request(lambda token:source.install_repository(entry,root/'bad-digest',token),'old')
                self.assertFalse((root/'bad-digest').exists())


class AccountPersistenceTests(unittest.TestCase):
    def test_unlink_failure_marks_encrypted_snapshot_and_new_login_is_not_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);auth.save(root,{'token':'old','login':'tester'});original_unlink=Path.unlink
            def protected_file(path,*args,**kwargs):
                if path.name in ('github-account.bin','github-account.invalid.json'):raise PermissionError('synthetic delete denied')
                return original_unlink(path,*args,**kwargs)
            with patch.object(Path,'unlink',protected_file):
                with self.assertRaises(auth.CredentialCleanupError) as caught:auth.logout(root,expected_token='old')
                self.assertTrue(caught.exception.persistent)
                marker=(root/'github-account.invalid.json').read_text();self.assertNotIn('old',marker)
                with self.assertRaises(auth.CredentialLoadError):auth.load(root)
                auth.save(root,{'token':'new','login':'tester'})
                self.assertEqual(auth.load(root)['token'],'new')

    def test_unwritable_marker_and_unlink_failure_are_explicit_about_restart_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);auth.save(root,{'token':'old','login':'tester'})
            with patch.object(Path,'write_text',side_effect=PermissionError('synthetic read-only profile')),patch.object(Path,'unlink',side_effect=PermissionError('synthetic read-only profile')):
                with self.assertRaises(auth.CredentialCleanupError) as caught:auth.logout(root,expected_token='old')
            self.assertFalse(caught.exception.persistent);self.assertIn('重开仍可能读到旧凭据',str(caught.exception))
            self.assertEqual(auth.load(root)['token'],'old')

    def test_corrupt_store_is_reported_and_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'github-account.bin';path.write_bytes(b'not a DPAPI account')
            with self.assertRaises(auth.CredentialLoadError):auth.load(tmp)
            self.assertFalse(auth.logout(tmp,expected_token='old'))
            self.assertEqual(path.read_bytes(),b'not a DPAPI account')

    def test_compare_before_clear_preserves_new_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth.save(tmp,{'token':'new','login':'tester'})
            self.assertFalse(auth.logout(tmp,expected_token='old'))
            self.assertEqual(auth.load(tmp)['token'],'new')

    def test_poll_retains_code_and_actual_refresh_metadata_across_profile_timeout(self):
        session={};payload={'access_token':'synthetic','refresh_token':'synthetic-refresh','expires_in':3600,'scope':'read:user','token_type':'bearer'}
        with patch.object(auth,'post',return_value=payload) as post,patch('github_api.github_json',side_effect=[TimeoutError(),{'login':'tester'}]):
            self.assertEqual(auth.poll('device-code',session),{'pending':'network'})
            account=auth.poll('device-code',session);self.assertEqual(post.call_count,1)
        self.assertEqual(account['refresh_token'],'synthetic-refresh');self.assertIn('expires_at',account)
        with tempfile.TemporaryDirectory() as tmp:
            auth.save(tmp,account);self.assertEqual(auth.load(tmp),account)
            self.assertNotIn(b'synthetic-refresh',(Path(tmp)/'github-account.bin').read_bytes())
        with patch.object(auth,'post',return_value={'access_token':'synthetic'}),patch('github_api.github_json',return_value={'login':'tester'}):
            self.assertNotIn('refresh_token',auth.poll('device-code'))

    def test_poll_network_and_rate_limit_remain_pending(self):
        for error in (URLError(ConnectionRefusedError(10061,'synthetic refusal')),TimeoutError(),http(503)):
            with patch.object(auth,'post',side_effect=error):self.assertEqual(auth.poll('same-code'),{'pending':'network'})
        with patch.object(auth,'post',side_effect=http(429,{'Retry-After':'30'})):
            self.assertEqual(auth.poll('same-code'),{'pending':'rate_limit','retry_after':30})


class AuthUiRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def window(self,root,account=None):
        if account:auth.save(root/'profile',account)
        with patch('desktop.development.enabled',return_value=False):
            return Window(ToolStore(root/'profile'),root/'tools',autoload=False)

    def finish(self,window):
        job=window.job;job.run();job.finished.emit();self.app.processEvents()

    def test_401_clears_matching_session_and_offers_clickable_login_after_anonymous_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root,{'token':'old','login':'tester'});calls=[]
            def operation(token):
                calls.append(token)
                if token:raise api.AuthenticationExpired(token)
                return 'installed'
            with patch.object(Job,'start'),patch('desktop.webbrowser.open') as browser:
                w.busy(operation,lambda value:w.status.setText(value),'download',public=True);self.finish(w)
                self.assertEqual(calls,['old',None]);self.assertEqual(w.account,{})
                self.assertFalse((root/'profile/github-account.bin').exists())
                self.assertFalse(w.reauth_button.isHidden());self.assertIn('登录已失效',w.status.text())
                w.reauth_button.click();self.assertEqual(w.pages.currentWidget(),w.settings)
                self.assertIn('重新登录',w.login_button.text());browser.assert_not_called()
            w.close()

    def test_403_429_and_network_failures_keep_account_and_persisted_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root,{'token':'keep','login':'tester'});path=root/'profile/github-account.bin';before=path.read_bytes()
            for error in (http(403,{'X-RateLimit-Remaining':'0'}),http(403),http(429),URLError(ConnectionRefusedError(10061,'refused')),TimeoutError()):
                def operation(token):raise error
                with patch.object(Job,'start'):
                    w.busy(operation,lambda _:None,'download',public=True);self.finish(w)
                self.assertEqual(w.account['token'],'keep');self.assertEqual(path.read_bytes(),before)
                self.assertTrue(w.reauth_button.isHidden())
            w.close()

    def test_late_old_401_does_not_clear_new_login_or_same_token_new_epoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root,{'token':'old','login':'tester'});old_epoch=w.auth_epoch
            w.account={'token':'new','login':'new-user'};w.auth_epoch+=1;auth.save(root/'profile',w.account)
            w.invalidate_account({'token':'old','epoch':old_epoch})
            self.assertEqual(auth.load(root/'profile')['token'],'new');self.assertEqual(w.account['token'],'new')
            w.invalidate_account({'token':'new','epoch':old_epoch})
            self.assertEqual(w.account['token'],'new');w.close()

    def test_failed_credential_cleanup_is_visible_and_does_not_claim_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root,{'token':'old','login':'tester'});path=root/'profile/github-account.bin';before=path.read_bytes()
            with patch.object(auth,'logout',side_effect=PermissionError('synthetic protected profile')):
                w.invalidate_account({'token':'old','epoch':w.auth_epoch})
            self.assertEqual(w.account,{});self.assertEqual(path.read_bytes(),before)
            self.assertIn('凭据清理失败',w.account_label.text());self.assertNotIn('已清除',w.account_label.text());w.close()

    def test_corrupt_credentials_have_explicit_ui_and_preserve_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile';profile.mkdir();path=profile/'github-account.bin';path.write_bytes(b'corrupt')
            w=self.window(root);self.assertEqual(path.read_bytes(),b'corrupt')
            self.assertIn('无法解密或已损坏',w.account_label.text());self.assertFalse(w.reauth_button.isHidden())
            self.assertFalse(w.logout_button.isHidden());w.close()

    def test_delete_failure_reopen_does_not_resurrect_rejected_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root,{'token':'old','login':'tester'});original_unlink=Path.unlink
            def protected(path,*args,**kwargs):
                if path.name=='github-account.bin':raise PermissionError('synthetic delete denied')
                return original_unlink(path,*args,**kwargs)
            with patch.object(Path,'unlink',protected):w.invalidate_account({'token':'old','epoch':w.auth_epoch})
            self.assertTrue((root/'profile/github-account.bin').exists());self.assertFalse(w.logout_button.isHidden())
            w.close();reopened=self.window(root);self.assertEqual(reopened.account,{})
            self.assertIn('已停用',reopened.account_label.text());reopened.close()

    def test_completed_authorization_save_retry_does_not_request_another_code_or_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root);session={'device_code':'code','deadline':time.monotonic()+60};w.login_session=session
            result={'token':'new','login':'tester'}
            with patch.object(Job,'start'),patch.object(auth,'poll',return_value=result) as poll,patch.object(auth,'save',side_effect=PermissionError('synthetic profile read-only')):
                w.poll_login();self.finish(w);self.assertEqual(poll.call_count,1)
            self.assertIs(w.login_session,session);self.assertFalse(w.retry_save_button.isHidden());self.assertFalse(w.login_timer.isActive())
            self.assertIn('无需重新授权',w.account_label.text())
            with patch.object(Job,'start'),patch.object(auth,'poll',side_effect=AssertionError('must reuse completed authorization')):
                w.retry_save_button.click();self.finish(w)
            self.assertEqual(auth.load(root/'profile')['token'],'new');self.assertIsNone(w.login_session);w.close()

    def test_login_network_poll_preserves_same_code_and_new_login_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root)
            session={'device_code':'same-code','deadline':time.monotonic()+60,'interval':5};w.login_session=session;w.login_code.setText('ABCD-EFGH')
            with patch.object(Job,'start'),patch.object(auth,'poll',return_value={'pending':'network'}):
                w.poll_login();self.finish(w)
            self.assertIs(w.login_session,session);self.assertEqual(w.login_code.text(),'ABCD-EFGH');self.assertTrue(w.login_timer.isActive())
            w.login_timer.stop()
            with patch.object(Job,'start'),patch.object(auth,'poll',return_value={'token':'new','login':'tester'}):
                w.poll_login();self.finish(w)
            self.assertEqual(w.account['token'],'new');w.close()
            reopened=self.window(root);self.assertEqual(reopened.account['token'],'new');reopened.close()

    def test_late_login_response_after_logout_cannot_restore_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root);session={'device_code':'old-code','deadline':time.monotonic()+60};w.login_session=session
            with patch.object(Job,'start'),patch.object(auth,'poll',return_value={'token':'late','login':'tester'}):
                w.poll_login();w.logout_github();self.finish(w)
            self.assertEqual(w.account,{});self.assertFalse((root/'profile/github-account.bin').exists());w.close()

    def test_background_auth_notice_remains_visible_without_navigation_or_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root,{'token':'old','login':'tester'});w.policy.data['mode']='background'
            def request(path,token=None):
                if token:raise api.AuthenticationExpired(token)
                return {'tag_name':'v0.0.6'}
            original_page=w.pages.currentWidget()
            with patch.object(Job,'start'),patch('github_api.github_json',side_effect=request),patch('desktop.webbrowser.open') as browser:
                w.background_check();job=w.check_job;job.run();job.finished.emit();self.app.processEvents()
                self.assertIn('登录已失效',w.status.text());self.assertEqual(w.pages.currentWidget(),original_page);browser.assert_not_called()
            w.close()

    def test_release_in_development_uses_same_public_recovery_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=self.window(root);w.development=True
            entry={'id':'repo-42','distribution':'github-release','version':'1.0.0'}
            with patch.object(Job,'start'):
                w.install_entry(entry);self.assertTrue(w.job.public)
                job=w.job;job.finished.emit();self.app.processEvents()
            w.close()

    def test_offscreen_runtime_auth_hook_uses_only_isolated_synthetic_sessions(self):
        from runtime_verify import verify_auth_recovery
        with tempfile.TemporaryDirectory() as tmp:
            result=verify_auth_recovery(Path(tmp),self.app)
            self.assertTrue(result['ok']);self.assertTrue(all(result['checks'].values()))


if __name__=='__main__':unittest.main()
