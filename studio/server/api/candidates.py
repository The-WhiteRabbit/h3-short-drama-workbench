"""Candidate API facade."""

from candidate_manager import scan_candidates


def get_candidates(folder):
    return scan_candidates(folder)


def select_candidate(data):
    return {
        "selected": data.get("asset_id"),
        "shot_id": data.get("shot_id")
    }
