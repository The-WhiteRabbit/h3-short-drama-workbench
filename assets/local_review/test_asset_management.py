"""Offline asset lifecycle tests; never contacts the generation gateway."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from workbench import Project
from server import UserError


class AssetManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = Project(Path(self.tmp.name))
        self.p.put_json('asset_manifest.json', {'assets': [], 'generations': []})
        self.p.put_json('episodes/EP001/episode.json', {'assets': [], 'assets_ready': True})
        self.path = 'assets/props/WATCH001/test.png'
        self.p.atomic_write(self.path, b'original-media')
        self.p.sync_catalog()

    def trash(self, path=None, expected=None):
        path = path or self.path
        return self.p.action({'action': 'asset_trash', 'path': path,
                              'expected_hash': expected or self.p.file_hash(path)})

    def membership(self, include, expected=None):
        return self.p.action({'action': 'asset_review_set', 'path': self.path, 'episode': 'EP001',
                              'include': include, 'expected_config_hash': expected or self.p.file_hash('episodes/EP001/episode.json')})

    def verify_catalog(self):
        for row in self.p.read_json('asset_manifest.json')['assets']:
            raw = self.p.safe(row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])

    def test_round_trip_retains_bytes_and_catalog(self):
        self.trash()
        self.assertFalse(self.p.safe(self.path).exists())
        row = self.p.trash_items()[0]
        self.verify_catalog()
        self.p.action({'action': 'asset_restore', 'id': row['id']})
        self.assertEqual(self.p.safe(self.path).read_bytes(), b'original-media')
        self.assertEqual(self.p.trash_items(), [])
        self.verify_catalog()
        current = [x for x in self.p.read_json('asset_manifest.json')['assets'] if x['current'] and x['role'] == self.path]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['path'], self.path)

    def test_review_membership_blocks_trash_until_removed(self):
        self.membership(True)
        with self.assertRaises(UserError):
            self.trash()
        self.membership(False)
        self.assertTrue(self.p.safe(self.path).exists())
        self.trash()

    def test_character_binding_blocks_trash(self):
        self.p.put_json('assets/characters/CHAR001/character.json', {'looks': {'LOOK01': {'image': self.path}}})
        with self.assertRaisesRegex(UserError, 'character.json'):
            self.trash()

    def test_unit_reference_blocks_trash(self):
        self.p.put_json('episodes/EP001/units/H3-001/params.json', {'references': [{'path': self.path}]})
        with self.assertRaisesRegex(UserError, 'params.json'):
            self.trash()

    def test_active_job_blocks_trash(self):
        self.p.put_json('jobs/JOB-1/job.json', {'id': 'JOB-1', 'state': 'running', 'input_hashes': {self.path: 'hash'}})
        with self.assertRaisesRegex(UserError, 'JOB-1'):
            self.trash()

    def test_stale_hash_rejected(self):
        old = self.p.file_hash(self.path)
        self.p.atomic_write(self.path, b'changed')
        with self.assertRaises(UserError):
            self.trash(expected=old)
        self.assertEqual(self.p.safe(self.path).read_bytes(), b'changed')

    def test_stale_review_list_rejected(self):
        old = self.p.file_hash('episodes/EP001/episode.json')
        self.membership(True)
        with self.assertRaises(UserError):
            self.membership(False, old)

    def test_restore_never_overwrites(self):
        self.trash()
        row = self.p.trash_items()[0]
        self.p.atomic_write(self.path, b'new-file')
        with self.assertRaisesRegex(UserError, '同名'):
            self.p.action({'action': 'asset_restore', 'id': row['id']})
        self.assertEqual(self.p.safe(self.path).read_bytes(), b'new-file')
        self.assertTrue(self.p.safe(row['stored_path']).exists())

    def test_protected_paths_and_configs(self):
        self.p.atomic_write('original.png', b'original')
        self.p.put_json('assets/props/config.json', {})
        for path in ['original.png', 'assets/../original.png', 'assets/props/config.json']:
            with self.assertRaises(UserError):
                self.trash(path, 'hash')
        self.assertTrue(self.p.safe('original.png').exists())

    def test_symlink_rejected(self):
        link = self.p.root / 'assets/link.png'
        link.symlink_to(self.p.root / self.path)
        with self.assertRaises(UserError):
            self.trash('assets/link.png', 'hash')


if __name__ == '__main__':
    unittest.main()
