"""Studio API routing helpers.

Expose project, jobs, candidates and selection operations through one layer.
"""

from pathlib import Path
from candidate_manager import scan_candidates
from job_queue import add_job, list_jobs


def project_api(root: Path):
    return {
        "jobs": list_jobs(root),
        "candidates": scan_candidates(root),
    }


def create_job(root: Path, payload: dict):
    return add_job(root, payload)
