"""Selected clip version management."""

import json
from pathlib import Path


def selection_path(root: Path):
    return root / "selection.json"


def select_clip(root: Path, shot_id: str, clip_id: str):
    path = selection_path(root)
    data = {}
    if path.exists():
        data = json.loads(path.read_text("utf-8"))
    data[shot_id] = clip_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return {"shot_id": shot_id, "selected": clip_id}
