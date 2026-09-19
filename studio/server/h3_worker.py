"""MiniMax H3 worker adapter.

Consumes queued generation jobs and converts them into provider tasks.
The provider-specific request code remains isolated here.
"""

from pathlib import Path
import json


def load_job(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare_h3_request(job):
    return {
        "provider": job.get("provider", "MiniMax-H3"),
        "shot_id": job.get("shot_id"),
        "prompt_file": job.get("prompt_file"),
        "references": job.get("references", [])
    }


def run_job(job_path):
    job = load_job(job_path)
    return prepare_h3_request(job)
