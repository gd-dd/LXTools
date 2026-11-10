"""Bounded, complete GETs. Each retry opens a fresh request, never resumes bytes."""
import http.client
import socket
import ssl
import time
import urllib.error
import urllib.request
import urllib.parse
from contextlib import contextmanager
from contextvars import ContextVar

MAX_ATTEMPTS=3
_progress=ContextVar('http_get_progress',default=None)


class ShortResponse(OSError):pass


class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlparse(newurl).scheme!='https':raise ValueError('拒绝非 HTTPS 下载跳转')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None:redirected.remove_header('Authorization')
        return redirected


def open_https(request,**options):
    return urllib.request.build_opener(HttpsOnlyRedirect).open(request,**options)


class TransferFailed(urllib.error.URLError):
    def __init__(self,stage,attempts,error):
        reason=error.reason if isinstance(error,urllib.error.URLError) else error
        code=getattr(reason,'winerror',None) or getattr(reason,'errno',None)
        if isinstance(reason,ConnectionRefusedError) or code in (10061,111,61):detail='连接被拒绝（10061），请检查代理进程、代理端口或目标服务。'
        elif isinstance(reason,(TimeoutError,socket.timeout)):detail='连接超时，请检查网络或代理。'
        else:detail='连接中断或响应未完整接收，请检查网络或代理。'
        self.stage,self.attempts,self.error_type=stage,attempts,type(error).__name__
        self.message=f'{stage}失败：共尝试 {attempts} 次，重试已用尽。{detail} 已有工具和目录保持；此类网络错误不会注销登录。'
        super().__init__(self.message)
    def __str__(self):return self.message


@contextmanager
def progress_reporting(callback):
    handle=_progress.set(callback)
    try:yield
    finally:_progress.reset(handle)


def notify_progress(message):
    callback=_progress.get()
    if callback:callback(message)


def _retryable(error):
    if isinstance(error,urllib.error.HTTPError):return False
    reason=error.reason if isinstance(error,urllib.error.URLError) else error
    if isinstance(reason,(PermissionError,ssl.SSLCertVerificationError)):return False
    return isinstance(error,(urllib.error.URLError,http.client.IncompleteRead,http.client.RemoteDisconnected,EOFError,ConnectionError,TimeoutError,ShortResponse,ssl.SSLEOFError)) or isinstance(reason,(ConnectionError,TimeoutError)) or (getattr(reason,'winerror',None) or getattr(reason,'errno',None)) in (10053,10054,54,104)


def read_get(request_factory,*,stage,max_bytes,timeout=12,expected_size=None,open_request=None,attempts=MAX_ATTEMPTS):
    """Return (whole body, response headers), retrying transport failures only.

    open_request must reopen the original URL and resolve redirects each time;
    callers must not supply a cached signed URL. Validation errors stay fatal.
    """
    if expected_size is not None and not 0<=expected_size<=max_bytes:raise ValueError('响应预期大小无效')
    if type(attempts) is not int or not 1<=attempts<=MAX_ATTEMPTS:raise ValueError('GET 尝试次数无效')
    for attempt in range(1,attempts+1):
        try:
            request=request_factory()
            if not hasattr(request,'get_method') or request.get_method()!='GET' or getattr(request,'data',None) is not None:raise ValueError('安全下载只允许无请求体的 GET，不重试 POST')
            with (open_request or urllib.request.urlopen)(request,timeout=timeout) as response:
                headers=getattr(response,'headers',None) or {}
                declared=headers.get('Content-Length')
                if declared is not None:
                    try:declared=int(declared)
                    except (TypeError,ValueError):raise ValueError('响应 Content-Length 无效') from None
                    if declared<0 or declared>max_bytes:raise ValueError('响应大小超过限制')
                chunks=[];total=0
                while True:
                    chunk=response.read(min(1024*1024,max_bytes+1-total))
                    if not chunk:break
                    chunks.append(chunk);total+=len(chunk)
                    if total>max_bytes:raise ValueError('响应大小超过限制')
                if declared is not None and total<declared:raise ShortResponse('short Content-Length')
                if declared is not None and total>declared:raise ValueError('响应大小与 Content-Length 不一致')
                if expected_size is not None and total!=expected_size:
                    if total<expected_size and declared is None:raise ShortResponse('short expected size')
                    raise ValueError('响应大小与发行元数据不一致')
                return b''.join(chunks),headers
        except Exception as error:
            if not _retryable(error):raise
            if attempt==attempts:raise TransferFailed(stage,attempt,error) from None
            notify_progress(f'{stage}：响应中断，正在重新获取（第 {attempt+1}/{attempts} 次）…')
            time.sleep(.15*attempt)


def get_bytes(request_factory,**options):return read_get(request_factory,**options)[0]
