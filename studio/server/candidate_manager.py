"""Manage generated clip candidates for each shot.

Scans shot video folders and keeps version candidates separate from selection.
"""
from pathlib import Path
import json
import hashlib


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_candidates(video_dir):
    video_dir = Path(video_dir)
    result = []
    if not video_dir.exists():
        return result

    for item in sorted(video_dir.glob("*")):
        if item.suffix.lower() in [".mp4", ".mov", ".webm"]:
            result.append({
                "id": item.stem,
                "file": item.name,
                "size": item.stat().st_size,
                "sha256": sha256_file(item),
                "status": "candidate"
            })
    return result


def save_candidates(path, shot_id, candidates, selected=None):
    data = {
        "shot_id": shot_id,
        "candidates": candidates,
        "selected": selected
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
