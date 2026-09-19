"""Run: python -m unittest -v. Tests never change the supplied demo project."""
from pathlib import Path
import contextlib
import json
import shutil
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from server import Project, LocalServer, UserError

DEMO = Path(__file__).parent / 'demo_project'


def make_fixture(root):
    """Self-contained fixture; independent from the user's edited demo project."""
    root.mkdir(parents=True, exist_ok=True)
    def put(path, value):
        p = root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value, encoding='utf-8')
    put('project.json', {'schema_version': 1, 'project_id': 'test', 'title': 'Test project'})
    put('assets/style.md', 'shared style')
    for eid in ('EP001', 'EP002'):
        put(f'episodes/{eid}/episode.json', {'id': eid, 'title': eid, 'script': f'episodes/{eid}/script.md', 'storyboard': f'episodes/{eid}/storyboard.md'})
        put(f'episodes/{eid}/script.md', '# Script')
        put(f'episodes/{eid}/storyboard.md', '# Storyboard')
    for order in (10, 20):
        sid = f'EP001-SH{order:03d}'
        base = f'episodes/EP001/units/{sid}'
        put(base + '/unit.json', {'id': sid, 'order': order, 'title': sid, 'description': 'Test', 'duration_seconds': 3,
            'files': {'image_prompt': base + '/prompts/image.md', 'video_prompt': base + '/prompts/video.md', 'params': base + '/params.json'},
            'references': ['assets/style.md'], 'selected': {'image': base + '/images/frame_v001.png', 'video': base + '/videos/take_v001.mp4'}})
        put(base + '/prompts/image.md', 'image prompt')
        put(base + '/prompts/video.md', 'video prompt')
        put(base + '/params.json', {'duration_seconds': 3})
        put(base + '/images/frame_v001.png', 'test image bytes; no decoder needed')
        target = root / base / 'videos'
        target.mkdir(parents=True, exist_ok=True)
        (target / 'take_v001.mp4').write_bytes(bytes(range(256)) * 4)
        if order == 10:
            (target / 'take_v002.mp4').write_bytes(bytes(reversed(range(256))) * 4)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        make_fixture(self.root)
        self.p = Project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def ep(self):
        return self.p.snapshot()['episodes'][0]

    def approve(self, stage, sid='EP001-SH010', decision='approved', note=''):
        ep = self.ep()
        shot = next((s for s in ep['shots'] if s['id'] == sid), None)
        fp = ep['script_gate']['fingerprint'] if stage == 'script' else ep['board_bundle_fingerprint'] if stage == 'board_all' else shot['board' if stage == 'board' else 'clip']['fingerprint']
        return self.p.action({'action':'review','episode':ep['id'],'shot':sid,'stage':stage,'decision':decision,'expected_fingerprint':fp,'note':note})

    def ready(self):
        self.approve('script')
        self.approve('board_all')
        for s in self.ep()['shots']:
            self.approve('video', s['id'])
        self.assertTrue(self.ep()['ready_for_assembly'])

    def test_initial_gates_and_no_read_side_effects(self):
        before = set(self.root.rglob('*'))
        ep = self.ep()
        self.assertEqual(ep['script_gate']['state'], 'pending')
        self.assertTrue(all(s['board']['state'] == 'blocked' for s in ep['shots']))
        self.assertFalse(ep['ready_for_assembly'])
        self.assertEqual(before, set(self.root.rglob('*')))

    def test_full_three_gate_flow(self):
        self.ready()
        self.assertFalse(self.p.snapshot()['episodes'][1]['ready_for_assembly'])
        self.assertTrue((self.root/'reviews/script--EP001.json').is_file())

    def test_cannot_skip_upstream_gate(self):
        with self.assertRaises(UserError):
            self.approve('board')
        with self.assertRaises(UserError):
            self.approve('video')

    def test_rejection_requires_note_and_blocks_downstream(self):
        self.ready()
        with self.assertRaises(UserError):
            self.approve('board', decision='rejected')
        self.approve('board', decision='rejected', note='持信的手不对')
        self.assertEqual(self.ep()['shots'][0]['clip']['state'], 'blocked')
        self.assertEqual(self.ep()['shots'][1]['clip']['state'], 'approved')

    def test_one_prompt_only_invalidates_its_dependents(self):
        self.ready()
        shot = self.ep()['shots'][0]
        (self.root/shot['prompts']['video_prompt']['path']).write_text('新提示词', encoding='utf-8')
        a,b = self.ep()['shots']
        self.assertEqual(a['board']['state'], 'stale')
        self.assertEqual(a['clip']['state'], 'blocked')
        self.assertEqual(b['board']['state'], 'approved')
        self.assertEqual(b['clip']['state'], 'approved')
        self.approve('board')
        self.assertEqual(self.ep()['shots'][0]['clip']['state'], 'stale')
        self.assertTrue((self.root/a['video']['path']).is_file())

    def test_shared_reference_invalidates_all_references(self):
        self.ready()
        (self.root/'assets/style.md').write_text('共享风格已变化', encoding='utf-8')
        self.assertTrue(all(s['board']['state']=='stale' for s in self.ep()['shots']))

    def test_script_change_does_not_invalidate_other_episode_script(self):
        self.ready()
        ep2_before = self.p.snapshot()['episodes'][1]['script_gate']['fingerprint']
        (self.root/'episodes/EP001/script.md').write_text('新的分集剧本', encoding='utf-8')
        ep = self.ep()
        self.assertEqual(ep['script_gate']['state'], 'stale')
        self.assertTrue(all(s['board']['state']=='blocked' for s in ep['shots']))
        self.assertEqual(self.p.snapshot()['episodes'][1]['script_gate']['fingerprint'], ep2_before)

    def test_stale_approval_request_rejected(self):
        ep = self.ep()
        (self.root/ep['script']['path']).write_text('外部改写', encoding='utf-8')
        with self.assertRaises(UserError) as err:
            self.p.action({'action':'review','episode':ep['id'],'stage':'script','decision':'approved','expected_fingerprint':ep['script_gate']['fingerprint']})
        self.assertEqual(err.exception.status, 409)

    def test_replace_same_filename_invalidates_video_only(self):
        self.ready()
        original = self.ep()['shots'][0]
        path = self.root/original['video']['path']
        content = path.read_bytes()
        path.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
        changed = self.ep()['shots'][0]
        self.assertEqual(changed['board']['state'], 'approved')
        self.assertEqual(changed['clip']['state'], 'stale')
        self.assertNotEqual(changed['video']['hash'], original['video']['hash'])

    def test_new_candidate_does_not_switch_selection_or_approval(self):
        self.ready()
        shot = self.ep()['shots'][0]
        new_path = (self.root/shot['video']['path']).with_name('external_v003.mp4')
        new_path.write_bytes(b'candidate')
        current = self.ep()['shots'][0]
        self.assertEqual(len(current['candidates']['video']),3)
        self.assertEqual(current['video']['path'],shot['video']['path'])
        self.assertEqual(current['clip']['state'],'approved')

    def test_select_existing_version_preserves_files(self):
        self.ready()
        shot = self.ep()['shots'][0]
        new = next(f['path'] for f in shot['candidates']['video'] if f['path'].endswith('v002.mp4'))
        self.p.action({'action':'select','episode':'EP001','shot':shot['id'],'kind':'video','path':new,'expected_hash':shot['config_hash']})
        updated = self.ep()['shots'][0]
        self.assertEqual(updated['video']['path'],new)
        self.assertEqual(updated['clip']['state'],'stale')
        self.assertEqual(updated['board']['state'],'approved')
        self.assertTrue((self.root/shot['video']['path']).exists())

    def test_missing_video_not_approved(self):
        self.ready()
        (self.root/self.ep()['shots'][0]['video']['path']).unlink()
        self.assertEqual(self.ep()['shots'][0]['clip']['state'],'missing')
        self.assertFalse(self.ep()['ready_for_assembly'])

    def test_text_save_keeps_backup_and_detects_edit_conflict(self):
        ep = self.ep();rel=ep['script']['path'];old=(self.root/rel).read_bytes()
        request={'action':'save_text','path':rel,'expected_hash':ep['script']['hash'],'text':'新稿'}
        self.p.action(request)
        backups=list((self.root/'history'/rel).glob('*.bak'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),old)
        with self.assertRaises(UserError) as err:
            self.p.action(request)
        self.assertEqual(err.exception.status,409)

    def test_bad_json_rejected_before_overwriting(self):
        old=(self.root/'project.json').read_bytes()
        with self.assertRaises(ValueError):
            self.p.action({'action':'save_text','path':'project.json','expected_hash':self.p.file_hash('project.json'),'text':'{broken'})
        self.assertEqual(old,(self.root/'project.json').read_bytes())

    def test_invalid_entity_prevents_assembly_and_reviews(self):
        self.ready()
        (self.root/'episodes/EP002/episode.json').write_text('{broken',encoding='utf-8')
        state=self.p.snapshot()
        self.assertTrue(state['errors'])
        self.assertFalse(state['episodes'][0]['ready_for_assembly'])
        with self.assertRaises(UserError):
            self.approve('video')

    def test_traversal_hidden_files_and_symlinks_rejected(self):
        for name in ('../escape','/etc/passwd','.env','folder/../../escape','folder/.env'):
            with self.assertRaises(UserError):
                self.p.safe(name)
        try:
            (self.root/'linked.txt').symlink_to(self.root/'assets/style.md')
        except OSError:
            return
        with self.assertRaises(UserError):
            self.p.safe('linked.txt')

    def test_file_list_detects_external_added_episode(self):
        self.p.put_json('episodes/EP003/episode.json',{'id':'EP003','title':'第三集','script':'episodes/EP003/script.md','storyboard':'episodes/EP003/storyboard.md'})
        state=self.p.snapshot()
        self.assertEqual(len(state['episodes']),3)
        self.assertEqual(state['episodes'][2]['script_gate']['state'],'missing')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)/'project';make_fixture(cls.root)
        cls.server=LocalServer(('127.0.0.1',0),Project(cls.root))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def get(self,path,headers=None):
        try:
            return urlopen(Request(self.url+path,headers=headers or {}),timeout=5)
        except HTTPError as e:
            return e

    def test_page_and_state(self):
        with self.get('/') as r:
            self.assertEqual(r.status,200);self.assertIn(b'<html',r.read());self.assertEqual(r.headers['Cache-Control'],'no-store')
        with self.get('/api/project') as r:
            self.assertEqual(len(json.load(r)['episodes']),2)

    def test_range_prefix_suffix_and_unsatisfiable(self):
        route='/files/episodes/EP001/units/EP001-SH010/videos/take_v001.mp4'
        with self.get(route,{'Range':'bytes=0-99'}) as r:
            self.assertEqual(r.status,206);self.assertEqual(len(r.read()),100);self.assertTrue(r.headers['Content-Range'].startswith('bytes 0-99/'))
        with self.get(route,{'Range':'bytes=-10'}) as r:
            self.assertEqual(r.status,206);self.assertEqual(len(r.read()),10)
        with self.get(route,{'Range':'bytes=999999999-'}) as r:
            self.assertEqual(r.status,416)

    def test_outdated_media_url_fails_instead_of_showing_different_content(self):
        with self.get('/files/episodes/EP001/units/EP001-SH010/videos/take_v001.mp4?v=old') as r:
            self.assertEqual(r.status,409)

    def test_forbidden_host_origin_and_secret(self):
        for path,headers in [('/api/project',{'Host':'evil.example'}),('/api/session',{'Origin':'https://evil.example'}),('/files/.env',{})]:
            with self.get(path,headers) as r:
                self.assertEqual(r.status,403)

    def test_write_requires_token(self):
        req=Request(self.url+'/api/action',data=b'{"action":"rescan"}',headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as err:
            urlopen(req,timeout=5)
        self.assertEqual(err.exception.code,403)
        req.add_header('X-Review-Token',self.server.token)
        with urlopen(req,timeout=5) as r:
            self.assertTrue(json.load(r)['ok'])

    def test_csv_export_and_formula_escape(self):
        (self.root/'=formula.txt').write_text('test',encoding='utf-8')
        with self.get('/api/files.csv') as r:
            text=r.read().decode('utf-8-sig')
            self.assertIn('sha256',text)
            self.assertIn("'=formula.txt",text)


if __name__=='__main__':
    unittest.main()
