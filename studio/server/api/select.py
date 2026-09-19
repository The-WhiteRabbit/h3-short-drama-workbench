"""Selected clip API helpers."""

from pathlib import Path
import json


def select_clip(root: Path, shot_id: str, clip_id: str):
    path = root / "selected_clips.json"
    data = {"clips": {}}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("clips", {})[shot_id] = clip_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
