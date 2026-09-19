"""Tudou Studio local review server.

Provides a fixed UI backend with dynamic local asset state.
"""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import hashlib

ROOT = Path.cwd()


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_assets(folder: Path):
    result = []
    if not folder.exists():
        return result
    for p in folder.rglob("*"):
        if p.is_file():
            result.append({
                "path": str(p.relative_to(folder)),
                "size": p.stat().st_size,
                "sha256": sha256_file(p)
            })
    return result


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            self.send_json({"ok": True, "service": "tudou-studio"})
            return
        if self.path == "/api/assets":
            self.send_json(scan_assets(ROOT / "assets"))
            return
        if self.path == "/api/project":
            self.send_json({
                "root": str(ROOT),
                "assets": scan_assets(ROOT / "assets")
            })
            return
        return super().do_GET()


if __name__ == "__main__":
    print("Tudou Studio running on http://127.0.0.1:8787")
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
