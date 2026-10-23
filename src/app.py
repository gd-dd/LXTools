import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from core import ToolStore

ROOT = Path(__file__).resolve().parent
store = ToolStore(Path(os.environ.get('LOCALAPPDATA', str(ROOT.parent))) / 'LXTool')
secret = secrets.token_urlsafe(32)
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data, kind='application/json'):
        body = data.encode('utf-8') if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != '/':
            self.reply(404, {'error': '不存在'})
            return
        self.reply(200, (ROOT / 'index.html').read_text('utf-8'), 'text/html')

    def do_POST(self):
        if self.headers.get('X-LXTool-Key') != secret:
            self.reply(403, {'error': '请使用启动器打开界面'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 16384:
                raise ValueError('请求过大')
            data = json.loads(self.rfile.read(length))
            with lock:
                if self.path == '/api/state':
                    result = {'tools': store.state['tools'], 'dataPath': str(store.root), 'authenticated': list(store.tokens)}
                elif self.path == '/api/add':
                    store.add(data['repo'], data['category'])
                    result = {}
                elif self.path == '/api/auth':
                    store.tool(data['id'])
                    token = data['token'].strip()
                    if token:
                        store.tokens[data['id']] = token
                    else:
                        store.tokens.pop(data['id'], None)
                    result = {}
                elif self.path == '/api/releases':
                    result = store.releases(data['id'])
                elif self.path == '/api/install':
                    store.install(data['id'], data['asset'])
                    result = {}
                elif self.path == '/api/activate':
                    store.activate(data['id'], data['key'])
                    result = {}
                elif self.path == '/api/open':
                    tool = store.tool(data['id'])
                    version = next(v for v in tool['versions'] if v['key'] == data['key'])
                    os.startfile(str(store.root / 'packages' / tool['id'] / version['key']))
                    result = {}
                else:
                    raise ValueError('未知操作')
                self.reply(200, result)
        except ValueError as err:
            self.reply(400, {'error': str(err)})
        except Exception:
            self.reply(500, {'error': '操作失败，请检查网络、磁盘空间、文件占用及仓库信息。'})


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/#{secret}'
    print('LXTool 已启动。关闭此窗口或按 Ctrl+C 停止服务。')
    print('本地数据目录：', store.root)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
