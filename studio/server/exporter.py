"""Export approved clips into timeline data."""

import json
from pathlib import Path


def export_timeline(project_root: Path):
    source = project_root / "studio" / "schema" / "export_timeline.json"
    target = project_root / "timeline.json"
    if source.exists():
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target
