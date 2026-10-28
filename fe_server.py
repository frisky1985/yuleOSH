#!/usr/bin/env python3
"""静态文件服务 + API 反向代理，用于预览 yuleOSH Desktop Web UI。

要点：
- 用 Handler.directory 类属性而非 os.chdir()，避免 rebuild 删目录导致 cwd 失效
- ThreadingMixIn 支持并发请求
- fix_path 对 URL path 做 unquote，让 %2F 还原成 / 与后端 relPath 对齐
"""
import functools
import http.server
import os
import socketserver
import sys
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit, urlunsplit

STATIC_DIR = '/workspace/frontend/out'
BACKEND = 'http://127.0.0.1:18788'
PORT = 18789

os.makedirs(STATIC_DIR, exist_ok=True)


def fix_path(p: str) -> str:
    parts = urlsplit(p)
    return urlunsplit(('', '', unquote(parts.path), parts.query, parts.fragment))


class Handler(http.server.SimpleHTTPRequestHandler):
    # 注意：SimpleHTTPRequestHandler.__init__ 会用传入的 directory 参数覆盖
    # 这个类属性（默认 os.getcwd()），因此实际生效的是下面 partial 传入的值。
    directory = STATIC_DIR

    def log_message(self, fmt, *args):
        sys.stdout.write("[fe] %s %s -> %s\n" % (self.command, self.path, fmt % args))
        sys.stdout.flush()

    def _proxy(self, method: str) -> None:
        backend = BACKEND + fix_path(self.path)
        try:
            if method == 'GET':
                req = urllib.request.Request(backend, method='GET')
            else:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length else b''
                req = urllib.request.Request(backend, data=body, method=method)
                for h, v in self.headers.items():
                    if h.lower() in ('content-type', 'cookie'):
                        req.add_header(h, v)
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                for h, v in resp.headers.items():
                    if h.lower() not in ('transfer-encoding', 'content-encoding', 'connection'):
                        self.send_header(h, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for h, v in e.headers.items():
                if h.lower() not in ('transfer-encoding', 'content-encoding', 'connection'):
                    self.send_header(h, v)
            self.end_headers()
            try:
                self.wfile.write(e.read())
            except Exception:
                pass
        except BrokenPipeError:
            pass
        except Exception as e:
            sys.stdout.write("[fe] proxy error: %s\n" % e)
            sys.stdout.flush()
            try:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(("Proxy error: %s" % e).encode())
            except Exception:
                pass

    def end_headers(self):
        # HTML 不缓存，避免 rebuild 后浏览器仍用旧 chunk 触发已修复的崩溃；
        # 带 hash 的静态资源可长缓存。
        p = self.path.split('?', 1)[0]
        if p.endswith('.html') or p.endswith('/') or '.' not in p.rsplit('/', 1)[-1]:
            self.send_header('Cache-Control', 'no-store, must-revalidate')
        elif '/_next/static/' in p:
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
        else:
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_GET(self):
        try:
            if self.path.startswith('/api/'):
                return self._proxy('GET')
            p = self.path.replace('/yuleOSH', '')
            if p in ('', '/'):
                p = '/desktop/'
            self.path = p
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        except BrokenPipeError:
            pass
        except Exception as e:
            sys.stdout.write("[fe] GET error: %s\n" % e)
            sys.stdout.flush()

    def do_POST(self):
        try:
            if self.path.startswith('/api/'):
                return self._proxy('POST')
            self.send_error(404)
        except BrokenPipeError:
            pass
        except Exception as e:
            sys.stdout.write("[fe] POST error: %s\n" % e)
            sys.stdout.flush()


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


if __name__ == '__main__':
    # 关键：必须把 directory 显式传给 handler 构造函数。
    # 只设类属性不管用 —— SimpleHTTPRequestHandler.__init__ 会用
    # `directory = os.getcwd()` 覆盖掉它。
    handler = functools.partial(Handler, directory=STATIC_DIR)
    srv = ThreadingServer(('0.0.0.0', PORT), handler)
    print("[fe] serving on 0.0.0.0:%d (STATIC_DIR=%s, pid=%d)" % (PORT, STATIC_DIR, os.getpid()), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
