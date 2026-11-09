"""Shared GitHub REST transport."""
import json
import threading
_request_lock=threading.Lock()
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

def github_json(path, token=None):
    headers = {'User-Agent': 'LXTool', 'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with _request_lock:
        with urllib.request.urlopen(urllib.request.Request('https://api.github.com' + path, headers=headers), timeout=12) as response:
            return json.load(response)


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
        return prefix + '账户授权已失效，请重新授权。'
    if error.code == 429:
        return prefix + '服务暂时限流，请稍后重试。'
    if error.code == 403:
        return prefix + '服务器拒绝访问，尚不能确定是权限、临时限流还是下载链接问题。请重试；仍失败时请提供此提示。'
    if error.code == 404:
        return prefix + '版本或附件不存在，或账户无访问权限，请刷新工具目录。'
    return prefix + '请稍后重试。'
