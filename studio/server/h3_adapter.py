"""Adapter interface for MiniMax H3 generation.

This keeps generation providers separate from review workflow.
"""

import json
from pathlib import Path


class H3Adapter:
    def __init__(self, config=None):
        self.config = config or {}

    def create_job(self, shot):
        return {
            "type": "video_generation",
            "provider": "MiniMax-H3",
            "shot_id": shot.get("id"),
            "prompt": shot.get("prompt"),
            "status": "waiting"
        }

    def save_job(self, path, job):
        Path(path).write_text(
            json.dumps(job, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return job
