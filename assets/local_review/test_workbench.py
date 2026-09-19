"""Offline invariant tests: no credentials or real model requests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import h3_project as cli
from workbench import Project, Worker
from server import UserError

class FakeClient:
    def __init__(self): self.submits = 0; self.fail_submit = False
    def request_json(self, method, path, payload=None):
        if method == 'POST':
            self.submits += 1
            if self.fail_submit: raise TimeoutError('simulated uncertain submission')
            return {'id': 'remote-1'}
        return {'status': 'completed'}
    def request(self, method, path): return b'\x00\x00\x00\x18ftyp' + b'0' * 32, 'video/mp4'

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'production'
        cli.init(self.root, '测试项目')
        self.p = Project(self.root)
        self.client = FakeClient()
        self.worker = Worker(self.p, lambda: self.client)
        self.probe = patch('workbench.probe_media', return_value={'technical_status':'passed','human_review':'pending'})
        self.probe.start(); self.addCleanup(self.probe.stop)
    def tearDown(self): self.temp.cleanup()
    def ep(self): return self.p.snapshot(True)['episodes'][0]
    def shot(self): return self.ep()['shots'][0]
    def approve(self, stage, decision='approved', note=''):
        ep = self.ep(); shot = ep['shots'][0] if ep['shots'] else None
        gate = ep['script_gate'] if stage == 'script' else ep['assets_gate'] if stage == 'assets' else shot['board' if stage == 'board' else 'clip']
        return self.p.action({'action':'review','stage':stage,'episode':'EP001','shot':shot['id'] if shot else None,
                             'decision':decision,'note':note,'generate':stage=='board','expected_fingerprint':gate['fingerprint']})
    def prepare(self):
        self.p.atomic_write('episodes/EP001/script.md', '真实剧本'.encode())
        self.p.atomic_write('episodes/EP001/storyboard.md', '精简单元规划'.encode())
        self.approve('script')
        cli.character(self.root, 'CHAR001', '主角', ['LOOK01','LOOK02'])
        self.p.atomic_write('assets/characters/CHAR001/looks/LOOK01/a.png', b'image')
        ep = self.p.read_json('episodes/EP001/episode.json')
        ep.update(assets_ready=True, assets=['assets/characters/CHAR001/looks/LOOK01/a.png'])
        self.p.put_json('episodes/EP001/episode.json', ep)
        self.approve('assets')
        self.p.put_json('plan.json', {'units':[{'episode':'EP001','id':'H3-001','duration_seconds':4}, {'episode':'EP001','id':'H3-002','duration_seconds':4}]})
        cli.unit(self.root, 'EP001', 'H3-001', '第一单元')
        prefix='episodes/EP001/units/H3-001'
        self.p.atomic_write(prefix+'/prompts/video_en.md', b'Use <Picture 1> as identity reference.')
        self.p.atomic_write(prefix+'/prompts/video_zh.md', '中文分镜'.encode())
        self.p.atomic_write(prefix+'/prompts/image.md', b'panel prompt')
        self.p.atomic_write(prefix+'/images/grid.png', b'image')
        unit=self.p.read_json(prefix+'/unit.json'); unit.update(ready=True)
        unit['selected']['image']=prefix+'/images/grid.png'
        self.p.put_json(prefix+'/unit.json', unit)
        params=self.p.read_json(prefix+'/params.json');params['references']=[{'kind':'image','path':ep['assets'][0]}]
        self.p.put_json(prefix+'/params.json', params)
        return prefix
    def test_init_empty_complete_non_overwrite(self):
        self.assertTrue((self.root/'service/workbench.py').is_file())
        self.assertEqual(self.ep()['shots'], [])
        with self.assertRaises(ValueError): cli.init(self.root, '覆盖')
        with self.assertRaises(UserError): self.approve('script')
    def test_no_submission_before_board_review(self):
        self.prepare(); self.worker.tick()
        self.assertEqual(self.client.submits,0)
        self.approve('board'); self.worker.tick(); self.worker.tick()
        self.assertEqual(self.client.submits,1)
        self.assertEqual(self.p.jobs()[0]['state'],'succeeded')
        self.assertNotEqual(self.shot()['clip']['state'],'approved')
    def test_duplicate_approval_no_duplicate_charge(self):
        self.prepare();self.approve('board');self.approve('board')
        self.assertEqual(len(self.p.jobs()),1)
        self.worker.tick();self.worker.tick();self.worker.tick()
        self.assertEqual(self.client.submits,1)
    def test_changed_queued_job_never_submits(self):
        prefix=self.prepare();self.approve('board')
        self.p.atomic_write(prefix+'/prompts/video_en.md',b'changed')
        self.worker.tick()
        self.assertEqual(self.client.submits,0)
        self.assertEqual(self.p.jobs()[0]['state'],'stale')
    def test_inflight_result_is_old_and_not_adopted(self):
        prefix=self.prepare();self.approve('board');self.worker.tick()
        self.p.atomic_write(prefix+'/prompts/video_en.md',b'changed')
        self.worker.tick()
        self.assertEqual(self.p.jobs()[0]['state'],'succeeded')
        self.assertFalse(self.shot()['jobs'][0]['input_current'])
        self.assertFalse(self.shot()['video']['path'])
    def test_uncertain_submission_never_retries(self):
        self.prepare();self.approve('board');self.client.fail_submit=True
        self.worker.tick();self.worker.tick()
        self.assertEqual(self.p.jobs()[0]['state'],'submission_unknown')
        self.assertEqual(self.client.submits,1)
    def test_actual_reference_changes_invalidate_board(self):
        self.prepare();self.approve('board')
        self.p.atomic_write('assets/characters/CHAR001/looks/LOOK01/a.png', b'changed')
        self.assertNotEqual(self.shot()['board']['state'],'approved')
    def test_catalog_preserves_old_bytes_and_hash(self):
        self.prepare(); self.p.sync_catalog()
        path='assets/characters/CHAR001/looks/LOOK01/a.png'
        self.p.atomic_write(path,b'new-image');self.p.sync_catalog()
        rows=[r for r in self.p.read_json('asset_manifest.json')['assets'] if r['role']==path]
        self.assertEqual(len(rows),2)
        self.assertFalse(rows[0]['current']);self.assertTrue(rows[1]['current'])
        self.assertEqual(self.p.safe(rows[0]['path']).read_bytes(),b'image')
    def test_rolling_and_pilot_gate(self):
        self.prepare()
        with self.assertRaises(ValueError):cli.unit(self.root,'EP001','H3-002','第二单元')
        self.approve('board')
        with self.assertRaises(ValueError):cli.unit(self.root,'EP001','H3-002','第二单元')
        self.worker.tick();self.worker.tick();self.approve('video')
        cli.unit(self.root,'EP001','H3-002','第二单元')
        self.assertEqual(len(self.ep()['shots']),2)
    def test_upload_and_traversal(self):
        self.prepare()
        value=self.p.upload('episodes/EP001/units/H3-001/images','external.png',b'upload')
        self.assertTrue(self.p.safe(value['path']).exists())
        self.assertFalse(self.shot()['image']['path']==value['path'])
        with self.assertRaises(UserError):self.p.upload('assets/../../escape','x.png',b'x')
        with self.assertRaises(UserError):self.p.upload('reviews','x.png',b'x')
    def test_approval_is_for_whole_unit_and_stale_page_rejected(self):
        prefix=self.prepare();s=self.shot()
        self.p.atomic_write(prefix+'/prompts/video_en.md',b'changed')
        with self.assertRaises(UserError):
            self.p.action({'action':'review','stage':'board','episode':'EP001','shot':'H3-001','decision':'approved',
                          'generate':True,'expected_fingerprint':s['board']['fingerprint']})
        self.assertEqual(self.p.jobs(),[])
    def test_bad_media_is_not_adopted_or_retried(self):
        self.prepare(); self.approve('board'); self.worker.tick()
        with patch('workbench.probe_media', return_value={'technical_status':'failed'}):
            self.worker.tick()
        self.assertEqual(self.p.jobs()[0]['state'], 'failed')
        self.assertFalse(self.shot()['video']['path'])
        self.worker.tick(); self.assertEqual(self.client.submits,1)
    def test_paused_project_does_not_submit(self):
        self.prepare(); self.approve('board')
        config=self.p.read_json('project.json');config['automation']['paused']=True
        self.p.put_json('project.json', config); self.worker.tick()
        self.assertEqual(self.client.submits,0)
        self.assertEqual(self.p.jobs()[0]['state'],'queued')
    def test_catalog_compatible_with_existing_validator(self):
        import h3_assets
        self.prepare(); self.p.sync_catalog()
        self.assertEqual(h3_assets.validate(self.p.read_json('asset_manifest.json'),self.root),[])
    def test_same_inputs_can_resume_unsubmitted_stale_job(self):
        prefix=self.prepare(); original=self.p.safe(prefix+'/prompts/video_en.md').read_bytes()
        self.approve('board'); self.p.atomic_write(prefix+'/prompts/video_en.md',b'changed');self.worker.tick()
        self.p.atomic_write(prefix+'/prompts/video_en.md',original);self.approve('board');self.worker.tick()
        self.assertEqual(len(self.p.jobs()),1); self.assertEqual(self.client.submits,1)
    def test_no_prompt_api_secret_written(self):
        self.prepare();self.approve('board');self.worker.tick()
        request=self.p.read_json('jobs/'+self.p.jobs()[0]['id']+'/request.json')
        self.assertNotIn('conditions', request)
        self.assertNotIn('Authorization',str(request))

if __name__ == '__main__': unittest.main()
