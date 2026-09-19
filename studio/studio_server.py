"""Local production studio server.
Reads project json and assets dynamically so HTML does not need regeneration.
"""

from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return str(ROOT / path.lstrip('/'))

if __name__ == '__main__':
    print('Tudou Studio: http://localhost:8000')
    HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
