"""Local Review Studio API.

Provides a small JSON API between the fixed HTML reviewer and project assets.
This module is intentionally framework-free for local single-user workflows.
"""

import json
from pathlib import Path
from scanner import scan_project
from review import load_review


class StudioAPI:
    def __init__(self, project_root):
        self.project_root = Path(project_root)

    def project(self):
        return {
            "assets": scan_project(self.project_root),
            "review": load_review(self.project_root),
        }

    def write_review(self, payload):
        target = self.project_root / "review_state.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return payload
