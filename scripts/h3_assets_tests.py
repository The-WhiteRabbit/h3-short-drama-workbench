"""Offline tests for project asset catalog behavior."""

import argparse
import tempfile
import unittest
from pathlib import Path

import h3_assets as assets


class AssetCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        assets.init(argparse.Namespace(
            project_dir=self.root, project_id="FIXTURE", title="Fixture"
        ))
        self.manifest = self.root / "asset_manifest.json"

    def add(self, path, asset_id, logical_id, version, current=True, derived=None):
        assets.add(argparse.Namespace(
            manifest=self.manifest,
            path=path,
            id=asset_id,
            logical_id=logical_id,
            type="panel",
            role="fixture panel",
            status="approved",
            version=version,
            current=current,
            derived_from=derived or [],
            used_by=["H3-001"],
        ))

    def test_new_version_replaces_current_without_deleting_history(self):
        first = self.root / "storyboard" / "first.png"
        second = self.root / "storyboard" / "second.png"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        self.add(first, "PANEL-001-R1", "PANEL-001", 1)
        self.add(second, "PANEL-001-R2", "PANEL-001", 2)
        doc = assets.read(self.manifest)
        self.assertEqual([row["current"] for row in doc["assets"]], [False, True])
        self.assertFalse(assets.validate(doc, self.root))

    def test_hash_drift_and_unknown_parent_are_rejected(self):
        path = self.root / "storyboard" / "panel.png"
        path.write_bytes(b"original")
        self.add(path, "PANEL-001-R1", "PANEL-001", 1)
        path.write_bytes(b"changed")
        self.assertTrue(any("SHA-256" in e for e in assets.validate(assets.read(self.manifest), self.root)))
        path.write_bytes(b"original")
        with self.assertRaises(ValueError):
            self.add(path, "PANEL-002-R1", "PANEL-002", 1, derived=["UNKNOWN"])


if __name__ == "__main__":
    unittest.main()
