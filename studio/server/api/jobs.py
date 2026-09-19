"""Job API facade for Tudou Studio."""

from job_queue import create_job


def submit_h3_job(payload):
    return create_job(payload)


def list_jobs(root):
    path = root / "jobs.json"
    if not path.exists():
        return []
    import json
    return json.loads(path.read_text(encoding="utf-8"))
