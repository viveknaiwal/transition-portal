from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        target = ROOT / self.path.lstrip("/")
        if self.path.startswith("/login") or (not target.exists() and "." not in self.path.rsplit("/", 1)[-1]):
            self.path = "/index.html"
        super().do_GET()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8501), Handler)
    print("Transition Portal running at http://127.0.0.1:8501")
    server.serve_forever()
