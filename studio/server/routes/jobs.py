"""Job queue API helpers for Tudou Studio.

Keeps generation requests separated from model execution.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


def jobs_file(root: Path):
    return root / "jobs.json"


def load_jobs(root: Path):
    path = jobs_file(root)
    if not path.exists():
        return []
    return json.loads(path.read_text("utf-8"))


def add_job(root: Path, payload: dict):
    jobs = load_jobs(root)
    payload = dict(payload)
    payload.setdefault("status", "waiting")
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    jobs.append(payload)
    jobs_file(root).write_text(json.dumps(jobs, ensure_ascii=False, indent=2), "utf-8")
    return payload
