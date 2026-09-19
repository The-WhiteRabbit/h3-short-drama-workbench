"""Build studio manifests from generated shot assets.

Keeps the production metadata separate from generated media files.
"""

from pathlib import Path
import json


def build_manifest(project_root: Path):
    return {
        "project": project_root.name,
        "episodes": [],
        "generated_by": "tudou-studio"
    }


def save_manifest(project_root: Path):
    path = project_root / "studio_manifest.json"
    path.write_text(
        json.dumps(build_manifest(project_root), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return path
