"""
Tudou Studio asset scanner.

Scans a project directory and returns a lightweight manifest.
The scanner never decides approval; it only discovers files.
"""
from pathlib import Path
import hashlib
import json

MEDIA_EXT = {".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".md", ".json"}


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(root):
    root = Path(root)
    assets = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in MEDIA_EXT:
            assets.append({
                "path": str(p.relative_to(root)),
                "type": p.suffix.lower().replace(".", ""),
                "size": p.stat().st_size,
                "sha256": sha256(p),
            })
    return {"root": str(root), "assets": assets}


if __name__ == "__main__":
    import sys
    print(json.dumps(scan(sys.argv[1]), ensure_ascii=False, indent=2))
