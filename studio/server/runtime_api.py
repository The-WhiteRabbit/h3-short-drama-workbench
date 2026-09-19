"""Runtime API helpers for Tudou Studio.

Provides unified access for jobs, candidates and selection state.
"""

from pathlib import Path
import json


def read_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_jobs(root: Path):
    return read_json(root / "jobs.json", {"jobs": []})


def list_candidates(root: Path):
    return read_json(root / "candidates.json", {"shots": []})


def select_clip(root: Path, shot_id: str, clip_id: str):
    state = read_json(root / "selection.json", {"selected": {}})
    state["selected"][shot_id] = clip_id
    write_json(root / "selection.json", state)
    return state
