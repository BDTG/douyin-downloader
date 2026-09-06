"""Web frontend native thay nginx: redirect / ve gallery, serve files.html + proxy /api/ -> :8000, /gallery/ -> :8001.

Chay: .venv/Scripts/python.exe web/server.py  (nghe 127.0.0.1:8080)
Chi dung stdlib. Stream response nen video seek (Range) van chay.
"""
import os
import shutil
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
API = "http://127.0.0.1:8000"
GALLERY = "http://127.0.0.1:8001"
HOST, PORT = "127.0.0.1", 8080

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}
HOP = {"connection", "keep-alive", "transfer-encoding", "upgrade"}


def proxy(self, base, path):
    url = base + path
    data = None
    if self.command in ("POST", "PUT", "PATCH"):
        try:
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        except Exception:
            data = b""
    req = urllib.request.Request(url, data=data, method=self.command)
    for k, v in self.headers.items():
        if k.lower() not in HOP and k.lower() != "host":
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            self.send_response(r.status)
            for k, v in r.headers.items():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                shutil.copyfileobj(r, self.wfile)
    except urllib.error.HTTPError as e:
        self.send_response(e.code)
        body = e.read()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    except Exception as e:
        msg = f"proxy loi ({base}): {e}".encode("utf-8")
        self.send_response(502)
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)


def serve_file(self, name):
    p = HERE / name
    if not p.is_file():
        self.send_error(404)
        return
    body = p.read_bytes()
    self.send_response(200)
    self.send_header("Content-Type", MIME.get(p.suffix, "application/octet-stream"))
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)


class H(BaseHTTPRequestHandler):
    server_version = "douyin-web/1.0"

    def _route(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/gallery":
            self.send_response(301)
            self.send_header("Location", "/gallery/")
            self.end_headers()
        elif path == "/files" or path == "/files/" or path == "/files.html":
            serve_file(self, "files.html")
        elif path.startswith("/api/"):
            proxy(self, API, self.path)
        elif path.startswith("/gallery/"):
            proxy(self, GALLERY, self.path[len("/gallery"):] or "/")
        elif path == "/gallery":
            self.send_response(301)
            self.send_header("Location", "/gallery/")
            self.end_headers()
        else:
            # file tinh khac (neu co) trong thu muc web/
            p = (HERE / path.lstrip("/")).resolve()
            try:
                p.relative_to(HERE.resolve())
            except Exception:
                self.send_error(400)
                return
            if p.is_file() and p.suffix == ".html":
                serve_file(self, p.name)
            else:
                self.send_response(301)
                self.send_header("Location", "/gallery/")
                self.end_headers()

    do_GET = _route
    do_POST = _route
    do_HEAD = _route

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"web: http://{HOST}:{PORT}/  (api :8000, gallery :8001)", flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
