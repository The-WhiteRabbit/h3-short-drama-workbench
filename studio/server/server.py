"""
Tudou Studio local review server.

Responsibilities:
- Serve fixed HTML UI.
- Read project manifests dynamically.
- Detect asset changes without rebuilding HTML.
- Keep human review state separate from generated files.

This is the first implementation layer. Production adapters for MiniMax H3 and ComfyUI will be added separately.
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
    def do_GET(self):
        if self.path == "/api/assets":
            body = json.dumps(scan_assets(ROOT / "assets"), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


if __name__ == "__main__":
    print("Tudou Studio running on http://127.0.0.1:8787")
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
