"""GitHub device authorization and Windows user-bound credential storage."""
import ctypes,json,time
from ctypes import wintypes
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
CLIENT_ID='Ov23liRjA9hGeZqYzn4r'
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
    path=Path(root)/'github-account.bin'
    try:return json.loads(protect(path.read_bytes(),True))
    except (OSError,ValueError):return {}
def save(root,account):
    path=Path(root)/'github-account.bin';path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_bytes(protect(json.dumps(account).encode()));temporary.replace(path)
def logout(root):
    (Path(root)/'github-account.bin').unlink(missing_ok=True)
def post(endpoint,**values):
    request=Request('https://github.com/login/'+endpoint,data=urlencode(values).encode(),headers={'Accept':'application/json','User-Agent':'LXTools'})
    with urlopen(request,timeout=25) as response:return json.load(response)
def begin():
    result=post('device/code',client_id=CLIENT_ID,scope='read:user')
    if 'device_code' not in result:raise ValueError('无法开始登录，请确认 OAuth App 已开启 Device Flow。')
    return result
def poll(code):
    result=post('oauth/access_token',client_id=CLIENT_ID,device_code=code,grant_type='urn:ietf:params:oauth:grant-type:device_code')
    if 'access_token' in result:
        from github_api import github_json
        user=github_json('/user',result['access_token'])
        return {'token':result['access_token'],'login':user['login']}
    error=result.get('error')
    if error in ('authorization_pending','slow_down'):return {'pending':error}
    raise ValueError({'access_denied':'你取消了授权。','expired_token':'登录码已过期，请重新登录。'}.get(error,'GitHub 授权失败，请重试。'))
