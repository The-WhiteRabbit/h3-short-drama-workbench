"""Export approved clips into timeline data."""

from pathlib import Path
import json


def build_timeline(root: Path):
    selected = root / "selected_clips.json"
    if not selected.exists():
        return {"timeline": []}
    return json.loads(selected.read_text(encoding="utf-8"))


def save_timeline(root: Path):
    data = build_timeline(root)
    target = root / "timeline.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
