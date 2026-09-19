"""Candidate clip management helpers."""

from pathlib import Path
from candidate_manager import scan_candidates


def list_shot_candidates(root, shot_path):
    return scan_candidates(Path(root) / shot_path)


def select_candidate(record, candidate_id):
    record["selected"] = candidate_id
    return record
