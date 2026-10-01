"""Serve only the static UI preview and its original PDF on loopback."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = {
    "/": HERE / "index.html",
    "/index.html": HERE / "index.html",
    "/app.js": HERE / "app.js",
    "/styles.css": HERE / "styles.css",
    "/demo.json": HERE / "demo.json",
    "/source.pdf": ROOT / "raw data/source/FLEXI-ULife Prime Saver.pdf",
}
FILES.update(
    {f"/vendor/{p.name}": p for p in (ROOT / "src/insuretutor/web/vendor").glob("*") if p.is_file()}
)


class Handler(SimpleHTTPRequestHandler):
    extensions_map: ClassVar[dict[str, str]] = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
    }

    def do_GET(self):
        if urlsplit(self.path).path not in FILES:
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path not in FILES:
            self.send_error(404)
            return
        super().do_HEAD()

    def translate_path(self, path):
        return str(FILES[urlsplit(path).path])

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"InsureTutor static preview: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
