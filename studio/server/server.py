"""
Tudou Studio local review server.

Provides:
- fixed HTML UI
- dynamic asset scanning
- review state persistence API
"""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
from review_store import load_review, save_review
from scanner import scan_assets

ROOT = Path.cwd()


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if self.path == "/api/health":
            self.send_json({"ok": True, "service": "tudou-studio"})
            return

        if self.path == "/api/project":
            self.send_json({
                "root": str(ROOT),
                "assets": scan_assets(ROOT / "assets"),
                "review": load_review(ROOT)
            })
            return

        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/review":
            payload = self.read_body()
            result = save_review(ROOT, payload)
            self.send_json(result)
            return

        self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    print("Tudou Studio running on http://127.0.0.1:8787")
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
