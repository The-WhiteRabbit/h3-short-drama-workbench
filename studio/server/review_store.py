"""Persistent review state storage for Tudou Studio."""

from pathlib import Path
import json
from datetime import datetime, timezone

STATE = Path("review_state.json")


def load_state():
    if not STATE.exists():
        return {
            "script": {"status": "pending"},
            "storyboard": {"status": "pending"},
            "clip": {"status": "pending"}
        }
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_review(stage, status, note=""):
    data = load_state()
    data[stage] = {
        "status": status,
        "note": note,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
