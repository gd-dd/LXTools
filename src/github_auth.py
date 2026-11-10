"""GitHub device authorization and Windows user-bound credential storage."""
import ctypes,json,time,hashlib,threading
from ctypes import wintypes
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError
CLIENT_ID='Ov23liRjA9hGeZqYzn4r'
class CredentialLoadError(ValueError):pass
class CredentialCleanupError(OSError):
    def __init__(self,persistent):
        self.persistent=persistent
        super().__init__('登录信息未能删除，但旧会话已标记失效，重开不会重新启用。' if persistent else '无法持久退出：配置目录不可写，重开仍可能读到旧凭据。请检查目录权限后重试。')
_account_lock=threading.RLock()

def validate_account(account):
    if not isinstance(account,dict) or not isinstance(account.get('token'),str) or not account['token'] or not isinstance(account.get('login'),str) or not account['login']:
        raise CredentialLoadError('本机 GitHub 登录信息格式无效，尚未删除。请重新登录，或主动退出以清除。')
    return account

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
def protect(data,decrypt=False):
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));output=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(output.data,output.size)
    finally:
        kernel=ctypes.WinDLL('kernel32');kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree(output.data)
def load(root):
    with _account_lock:return _load(root)
def _decode(data):
    try:return validate_account(json.loads(protect(data,True)))
    except (OSError,ValueError,UnicodeError):
        raise CredentialLoadError('本机 GitHub 登录信息无法解密或已损坏，尚未删除。请重新登录，或主动退出以清除。') from None
def _load(root):
    path=Path(root)/'github-account.bin'
    try:data=path.read_bytes()
    except FileNotFoundError:return {}
    except OSError:raise CredentialLoadError('无法读取本机 GitHub 登录信息，尚未删除。请检查配置目录权限后重试。') from None
    marker=Path(root)/'github-account.invalid.json'
    try:invalid=json.loads(marker.read_text('utf-8'))
    except FileNotFoundError:invalid={}
    except (OSError,ValueError):raise CredentialLoadError('本机登录失效记录无法读取，尚未删除凭据。请检查配置目录或重新登录。') from None
    if not isinstance(invalid,dict):raise CredentialLoadError('本机登录失效记录格式无效，请重新登录。')
    if invalid.get('encryptedAccountSha256')==hashlib.sha256(data).hexdigest():
        raise CredentialLoadError('GitHub 登录已失效，旧凭据尚未删除且已停用。请重新登录，或主动清除本机登录信息。')
    return _decode(data)
def save(root,account):
    with _account_lock:
        validate_account(account)
        path=Path(root)/'github-account.bin';path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp');temporary.write_bytes(protect(json.dumps(account).encode()));temporary.replace(path)
        # A stale marker only binds the previous encrypted file, never this login.
        try:(Path(root)/'github-account.invalid.json').unlink(missing_ok=True)
        except OSError:pass
def logout(root,expected_token=None):
    with _account_lock:
        path=Path(root)/'github-account.bin'
        try:snapshot=path.read_bytes()
        except FileNotFoundError:return True
        if expected_token is not None:
            try:account=_decode(snapshot)
            except CredentialLoadError:return False
            if account.get('token')!=expected_token:return False
        # Persist only a fingerprint of the encrypted snapshot, never raw tokens.
        persistent=False;marker=Path(root)/'github-account.invalid.json'
        try:
            temporary=marker.with_suffix('.tmp')
            temporary.write_text(json.dumps({'encryptedAccountSha256':hashlib.sha256(snapshot).hexdigest()}),'utf-8');temporary.replace(marker);persistent=True
        except OSError:pass
        try:
            if path.read_bytes()!=snapshot:return False
            path.unlink();return True
        except FileNotFoundError:return True
        except OSError:raise CredentialCleanupError(persistent) from None
def post(endpoint,**values):
    request=Request('https://github.com/login/'+endpoint,data=urlencode(values).encode(),headers={'Accept':'application/json','User-Agent':'LXTools'})
    with urlopen(request,timeout=25) as response:return json.load(response)
def begin():
    result=post('device/code',client_id=CLIENT_ID,scope='read:user')
    if 'device_code' not in result:raise ValueError('无法开始登录，请确认 OAuth App 已开启 Device Flow。')
    return result
def poll(code,session=None):
    try:return _poll(code,session)
    except HTTPError as error:
        if error.code>=500:return {'pending':'network'}
        headers=error.headers or {}
        if error.code==429 or (error.code==403 and (headers.get('X-RateLimit-Remaining')=='0' or headers.get('Retry-After'))):
            retry=headers.get('Retry-After','')
            return {'pending':'rate_limit','retry_after':int(retry) if retry.isdigit() else 60}
        raise
    except (TimeoutError,URLError,ConnectionError):return {'pending':'network'}
def _poll(code,session=None):
    result=dict(session.get('token_metadata',{}),access_token=session['access_token']) if session and session.get('access_token') else post('oauth/access_token',client_id=CLIENT_ID,device_code=code,grant_type='urn:ietf:params:oauth:grant-type:device_code')
    if 'access_token' in result:
        # Preserve only metadata actually returned by GitHub; no invented refresh
        # token or promise of automatic renewal. DPAPI protects the whole account.
        metadata={k:result[k] for k in ('refresh_token','expires_in','refresh_token_expires_in','scope','token_type') if k in result}
        if isinstance(result.get('expires_in'),(int,float)):
            metadata['expires_at']=result.get('expires_at',time.time()+result['expires_in'])
        elif 'expires_at' in result:metadata['expires_at']=result['expires_at']
        if session is not None:
            session['access_token']=result['access_token'];session['token_metadata']=metadata
        from github_api import github_json
        user=github_json('/user',result['access_token'])
        return dict(metadata,token=result['access_token'],login=user['login'])
    error=result.get('error')
    if error in ('authorization_pending','slow_down'):return {'pending':error}
    raise ValueError({'access_denied':'你取消了授权。','expired_token':'登录码已过期，请重新登录。'}.get(error,'GitHub 授权失败，请重试。'))
