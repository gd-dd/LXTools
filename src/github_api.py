"""Shared GitHub REST transport."""
import json
import threading
_request_lock=threading.Lock()
import urllib.request
import urllib.error
import urllib.parse
import socket
import ssl
import re
from datetime import datetime
from http_transport import read_get, TransferFailed


class AuthenticationExpired(RuntimeError):
    """A GitHub API 401 for the supplied token; secrets never enter args/repr."""
    def __init__(self, token):
        super().__init__('GitHub 登录已失效，请重新登录。公开工具仍可匿名使用。')
        self.rejected_token = token


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise ValueError('拒绝非 HTTPS 跳转地址')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urllib.parse.urlparse(newurl).netloc != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


def authenticated_error(error, token):
    return bool(token and error.code == 401 and
                urllib.parse.urlparse(error.url or '').hostname == 'api.github.com')


def public_request(operation, token=None, invalidated=None):
    """Retry the whole validated public operation once, only for our token's 401."""
    try:
        return operation(token)
    except AuthenticationExpired as error:
        if not token or error.rejected_token != token:
            raise
        if invalidated is not None:
            invalidated()
        return operation(None)


def _github_bytes(path,token,accept,limit,stage,with_headers=False,attempts=3):
    headers = {'User-Agent': 'LXTool', 'Accept': accept,'Cache-Control':'no-cache'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        with _request_lock:
            payload=read_get(lambda:urllib.request.Request('https://api.github.com'+path,headers=headers),stage=stage,max_bytes=limit,timeout=12,attempts=attempts,
                             open_request=lambda request,**options:urllib.request.build_opener(GitHubRedirect).open(request,**options))
            return payload if with_headers else payload[0]
    except urllib.error.HTTPError as error:
        if authenticated_error(error, token):
            raise AuthenticationExpired(token) from None
        raise


def github_json(path, token=None, *, attempts=3):
    return json.loads(_github_bytes(path,token,'application/vnd.github+json',16*1024*1024,'读取 GitHub 版本信息',attempts=attempts))


def github_commit_sha(repository,ref,token=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not isinstance(ref,str) or not ref.startswith(('tags/','heads/')) or not ref.split('/',1)[1]:
        raise ValueError('提交查询必须指定仓库和明确的 tag/branch ref')
    path=f'/repos/{repository}/commits/{urllib.parse.quote(ref,safe="")}'
    value,headers=_github_bytes(path,token,'application/vnd.github.sha',64,'核对版本提交 SHA',with_headers=True)
    if headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/vnd.github.sha':raise ValueError('GitHub 提交响应媒体类型无效')
    if not re.fullmatch(b'[a-f0-9]{40}',value):raise ValueError('GitHub 未返回有效的 40 位提交 SHA')
    return value.decode('ascii')


def error_message(error, stage='网络请求'):
    if isinstance(error,TransferFailed):return str(error)
    if isinstance(error, urllib.error.HTTPError):
        return http_error_message(error, stage)
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    code = getattr(reason, 'winerror', None) or getattr(reason, 'errno', None)
    if isinstance(reason, ConnectionRefusedError) or code in (10061, 111, 61) or '10061' in str(reason):
        return stage + '连接被拒绝（10061）：请检查代理是否正在运行、代理端口是否正确，或目标服务端口是否可用。这不是 GitHub 登录失效。'
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return stage + '超时，请检查网络或代理后重试；已保留 GitHub 登录。'
    if isinstance(reason, socket.gaierror):
        return stage + '无法解析服务器地址，请检查网络或代理；已保留 GitHub 登录。'
    if isinstance(reason, ssl.SSLError):
        return stage + '安全连接失败，请检查网络、代理与系统时间；已保留 GitHub 登录。'
    if isinstance(error, (urllib.error.URLError, ConnectionError)):
        return stage + '连接失败，请检查网络或代理后重试；已保留 GitHub 登录。'
    return str(error)


def http_error_message(error, stage='网络请求'):
    headers = error.headers or {}
    host = urllib.parse.urlparse(error.url or '').hostname or '远端服务'
    prefix = f'{stage}失败（HTTP {error.code}，{host}）：'
    if headers.get('X-RateLimit-Remaining') == '0':
        reset = headers.get('X-RateLimit-Reset', '')
        try:
            until = datetime.fromtimestamp(int(reset)).strftime('%H:%M:%S')
            return prefix + f'GitHub 请求额度已用尽，请在当地时间 {until} 后重试。'
        except (ValueError, OverflowError, OSError):
            return prefix + 'GitHub 请求额度已用尽，请稍后重试。'
    retry = headers.get('Retry-After', '')
    if retry.isdigit():
        return prefix + f'服务暂时限流，请等待 {retry} 秒后重试。'
    if error.code == 401:
        return prefix + '服务器要求身份验证或未接受此请求。请核对资源访问要求；未据此清除本机登录。'
    if error.code == 429:
        return prefix + '服务暂时限流，请稍后重试。'
    if error.code == 403:
        return prefix + '服务器拒绝访问，尚不能确定是权限、临时限流还是下载链接问题。请重试；仍失败时请提供此提示。'
    if error.code == 404:
        return prefix + '版本或附件不存在，或账户无访问权限，请刷新工具目录。'
    return prefix + '请稍后重试。'
