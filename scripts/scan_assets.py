"""Scan production assets and update manifest.
Keeps asset files replaceable without rebuilding studio pages.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path('.')
ASSET_DIR = ROOT / 'assets'
MANIFEST = ROOT / 'asset_manifest.json'


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def scan():
    assets = {}
    if ASSET_DIR.exists():
        for p in ASSET_DIR.rglob('*'):
            if p.is_file():
                assets[str(p)] = {
                    'path': str(p),
                    'sha256': sha256(p),
                    'status': 'registered'
                }
    data = {'assets': assets}
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    scan()
    print('asset_manifest.json updated')
