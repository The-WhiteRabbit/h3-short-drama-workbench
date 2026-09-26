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
    def test_reveal_file_uses_safe_argument_vector(self):
        rel = 'assets/props/a quoted ; file.png'
        self.p.atomic_write(rel, b'image')
        with patch('workbench.sys.platform', 'darwin'), patch('workbench.subprocess.run') as run:
            self.assertTrue(self.p.action({'action':'reveal_file','path':rel})['ok'])
            self.assertEqual(run.call_args.args[0], ['/usr/bin/open', '-R', str((self.root / rel).resolve())])

    def test_unready_is_distinct_from_missing_files(self):
        self.prepare()
        path = 'episodes/EP001/units/H3-001/unit.json'
        unit = self.p.read_json(path)
        unit.update(ready=False, blockers=['首帧模式未接入'])
        self.p.put_json(path, unit)
        shot = self.shot()
        self.assertEqual(shot['board']['state'], 'not_ready')
        self.assertEqual(shot['board']['reason'], '首帧模式未接入')
        with self.assertRaises(UserError):
            self.approve('board')
        self.assertEqual(self.client.submits, 0)
        self.p.safe(unit['selected']['image']).unlink()
        self.assertEqual(self.shot()['board']['state'], 'missing')

    def test_windows_reveal_selects_file(self):
        rel = 'assets/props/watch space.png'
        self.p.atomic_write(rel, b'image')
        with patch('workbench.sys.platform', 'win32'), patch('workbench.subprocess.run') as run:
            self.assertEqual(self.p.snapshot(True)['file_browser_label'], '在资源管理器中显示')
            self.p.action({'action':'reveal_file','path':rel})
            self.assertEqual(run.call_args.args[0], ['explorer.exe', '/select,', str((self.root / rel).resolve())])

    def test_reveal_file_rejects_unsafe_or_missing_paths(self):
        with patch('workbench.subprocess.run') as run:
            for rel in ['../outside.png', '/tmp/outside.png', 'assets/missing.png']:
                with self.assertRaises(UserError):
                    self.p.action({'action':'reveal_file','path':rel})
            run.assert_not_called()

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
    def regenerate(self, parent=None, fingerprint=None):
        shot=self.shot()
        return self.p.action({'action':'regenerate','episode':'EP001','shot':shot['id'],
            'expected_fingerprint':fingerprint or shot['board']['fingerprint'],
            'retry_of':parent or self.p.jobs()[-1]['id'],'generate':True,'note':'用户希望重新生成'})
    def test_regenerate_preserves_output_and_deduplicates(self):
        self.prepare();self.approve('board');self.worker.tick();self.worker.tick()
        original=self.p.jobs()[0];selected=self.shot()['video']['path']
        new=self.regenerate(original['id'])['job']
        self.assertNotEqual(new['id'],original['id'])
        self.assertEqual(new['retry_of'],original['id'])
        self.assertEqual(self.regenerate(original['id'])['job']['id'],new['id'])
        self.assertEqual(len(self.p.jobs()),2)
        self.worker.tick();self.worker.tick()
        self.assertEqual(self.client.submits,2)
        self.assertEqual(self.shot()['video']['path'],selected)
        self.assertTrue(self.p.safe(original['output']).is_file())
        self.assertTrue(self.p.safe(new['output']).is_file())
        self.assertEqual(self.regenerate(original['id'])['job']['id'],new['id'])
        self.assertEqual(len(self.p.jobs()),2)
    def test_regenerate_rejects_active_unknown_stale_and_changed_inputs(self):
        prefix=self.prepare();self.approve('board');parent=self.p.jobs()[0]['id']
        with self.assertRaises(UserError): self.regenerate(parent)
        job=self.p.jobs()[0];job['state']='submission_unknown';self.p.save_job(job)
        with self.assertRaises(UserError): self.regenerate(parent)
        job['state']='failed';self.p.save_job(job)
        with self.assertRaises(UserError): self.regenerate('old-page-job')
        with self.assertRaises(UserError): self.regenerate(parent,'old-fingerprint')
        self.p.atomic_write(prefix+'/prompts/video_en.md',b'changed input')
        with self.assertRaises(UserError): self.regenerate(parent)
        self.assertEqual(len(self.p.jobs()),1)
    def test_regenerate_failed_job_and_limit(self):
        self.prepare();self.approve('board');job=self.p.jobs()[0]
        job['state']='failed';self.p.save_job(job)
        config=self.p.read_json('project.json');config['automation']['max_jobs']=1;self.p.put_json('project.json',config)
        with self.assertRaises(UserError): self.regenerate(job['id'])
        config['automation']['max_jobs']=2;self.p.put_json('project.json',config)
        self.assertEqual(self.regenerate(job['id'])['job']['state'],'queued')

    def test_sampling_editor_preserves_refs_seed_and_invalidates_review(self):
        self.prepare();self.approve('board');s=self.shot();rel=s['prompts']['params']['path'];old=self.p.read_json(rel)
        data={'action':'save_generation_params','episode':'EP001','shot':s['id'],'expected_hash':self.p.file_hash(rel,True),'params':{'steps':50,'seed':'7730965860811950444','execution_profile':'current'}}
        self.p.action(data);new=self.p.read_json(rel)
        self.assertEqual(new['references'],old['references'])
        self.assertEqual(new['seed'],7730965860811950444)
        self.assertEqual(new['steps'],50)
        self.assertEqual(self.shot()['board']['state'],'stale')
        self.assertEqual(len(self.p.jobs()),1)
        with self.assertRaises(UserError): self.p.action(data)
    def test_sampling_editor_rejects_bad_values(self):
        self.prepare();s=self.shot();rel=s['prompts']['params']['path']
        for changes in [{'steps':0},{'steps':2.5},{'flow_shift':float('nan')},{'seed':'9223372036854775808'},{'references':[]},{'execution_profile':'bogus'}]:
            with self.assertRaises(UserError):self.p.action({'action':'save_generation_params','episode':'EP001','shot':s['id'],'expected_hash':self.p.file_hash(rel,True),'params':changes})
    def test_base_preset_uses_same_model_client_without_extra_route_config(self):
        self.prepare();s=self.shot();rel=s['prompts']['params']['path']
        self.p.action({'action':'save_generation_params','episode':'EP001','shot':s['id'],'expected_hash':self.p.file_hash(rel,True),'params':{'execution_profile':'base','seed':'123'}})
        self.approve('board');payload=self.worker.payload(self.p.jobs()[0])
        self.assertEqual(payload['model'],'MiniMax-H3-Ref2VA')
        self.assertEqual(payload['num_inference_steps'],50)
        self.assertEqual(payload['flow_shift'],12)
        self.assertEqual(payload['audio_flow_shift'],3)
        self.assertEqual(payload['seed'],123)
        self.worker.tick();self.worker.tick()
        self.assertEqual(self.client.submits,1)
        self.assertEqual(self.p.jobs()[0]['state'],'succeeded')
        self.assertTrue(self.p.snapshot(True)['generation_services']['shared_connection'])

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
        cli.batch(self.root,['EP001/H3-002'])
        cli.unit(self.root,'EP001','H3-002','第二单元')
        self.assertEqual(len(self.ep()['shots']),2)
        plan=self.p.read_json('plan.json')
        plan['units'].append({'episode':'EP001','id':'H3-003','duration_seconds':4,'shot_count':3})
        self.p.put_json('plan.json',plan)
        cli.batch(self.root,['EP001/H3-002','EP001/H3-003'])
        cli.unit(self.root,'EP001','H3-003','第三单元')
        self.assertEqual(len(self.ep()['shots']),3)
        self.assertEqual(self.ep()['shots'][2]['shot_count'],3)
        self.assertIn('2 个单元',self.p.snapshot(True)['agent_next'])

    def test_batch_boundary_and_delivery(self):
        prefix=self.prepare()
        self.approve('board');self.worker.tick();self.worker.tick();self.approve('video')
        with self.assertRaises(ValueError):cli.unit(self.root,'EP001','H3-002','outside')
        with self.assertRaises(ValueError):cli.batch(self.root,['EP001/unknown'])
        cli.batch(self.root,['EP001/H3-002'])
        cli.unit(self.root,'EP001','H3-002','in batch')
        result=self.p.action({'action':'export_approved'})
        self.assertEqual(result['count'],1)
        rows=self.p.read_json(result['path']+'/manifest.json')['units']
        self.assertEqual(self.p.safe(rows[0]['source']).read_bytes(),self.p.safe(rows[0]['file']).read_bytes())
        self.p.atomic_write(prefix+'/prompts/video_en.md',b'new prompt')
        with self.assertRaises(UserError):self.p.export_approved()
        self.assertTrue(self.p.safe(rows[0]['file']).exists())

    def test_two_episodes_shared_looks_and_local_changes(self):
        first=self.prepare()
        self.approve('board');self.worker.tick();self.worker.tick();self.approve('video')
        old_video=self.shot()['video']['path']
        cli.episode(self.root,'EP002','second episode')
        # An unfinished later episode does not block earlier work or mask the batch.
        cli.batch(self.root,['EP001/H3-002'])
        self.assertIn('EP001/H3-002',self.p.snapshot(True)['agent_next'])
        cli.unit(self.root,'EP001','H3-002','second unit')
        plan=self.p.read_json('plan.json')
        plan['units'].append({'episode':'EP002','id':'EP002-U001','duration_seconds':4,'shot_count':2})
        self.p.put_json('plan.json',plan)
        self.p.atomic_write('episodes/EP002/script.md',b'second script')
        self.p.atomic_write('episodes/EP002/storyboard.md',b'second outline')
        look2='assets/characters/CHAR001/looks/LOOK02/b.png'
        self.p.atomic_write(look2,b'look two')
        ep=self.p.read_json('episodes/EP002/episode.json');ep.update(assets_ready=True,assets=[look2])
        self.p.put_json('episodes/EP002/episode.json',ep)
        def approve_second(stage):
            e=self.p.episode(self.p.snapshot(True),'EP002')
            gate=e['script_gate'] if stage=='script' else e['assets_gate'] if stage=='assets' else e['shots'][0]['board']
            self.p.action({'action':'review','stage':stage,'episode':'EP002','shot':'EP002-U001',
                'decision':'approved','generate':stage=='board','expected_fingerprint':gate['fingerprint']})
        approve_second('script');approve_second('assets')
        cli.batch(self.root,['EP002/EP002-U001'])
        cli.unit(self.root,'EP002','EP002-U001','multi shot')
        second='episodes/EP002/units/EP002-U001'
        for name in ('image','video_zh','video_en'):
            self.p.atomic_write(second+'/prompts/'+name+'.md',b'Use <Picture 1> as reference.')
        self.p.atomic_write(second+'/images/board.png',b'board')
        u=self.p.read_json(second+'/unit.json');u.update(ready=True,panels=[look2,look2]);u['selected']['image']=second+'/images/board.png'
        self.p.put_json(second+'/unit.json',u)
        params=self.p.read_json(second+'/params.json');params['references']=[{'kind':'image','path':look2}]
        self.p.put_json(second+'/params.json',params)
        approve_second('board')
        with self.assertRaisesRegex(ValueError,'全项目唯一'):
            cli.unit(self.root,'EP002','H3-001','duplicate')
        # Changing EP002 or its look leaves EP001's approved video intact.
        self.p.atomic_write('episodes/EP002/script.md',b'edited second script')
        self.assertEqual(self.shot()['clip']['state'],'approved')
        approve_second('script');approve_second('board')
        self.p.atomic_write(look2,b'replaced second look')
        self.assertEqual(self.shot()['clip']['state'],'approved')
        self.assertNotEqual(self.p.episode(self.p.snapshot(True),'EP002')['shots'][0]['board']['state'],'approved')
        self.assertTrue(self.p.safe(old_video).exists())
        # Referenced first look invalidates its consumer, without deleting video.
        self.p.atomic_write('assets/characters/CHAR001/looks/LOOK01/a.png',b'replaced first look')
        self.assertNotEqual(self.shot()['clip']['state'],'approved')
        self.assertTrue(self.p.safe(old_video).exists())
        with self.assertRaises(ValueError):cli.unit(self.root,'EP002','H3-001','duplicate')

    def test_first_frame_count_and_legacy_panels(self):
        prefix=self.prepare()
        unit=self.p.read_json(prefix+'/unit.json')
        unit.update(shot_count=3,panels=[unit['selected']['image']])
        self.p.put_json(prefix+'/unit.json',unit)
        self.assertEqual(self.shot()['board']['state'],'not_ready')
        with self.assertRaises(UserError):self.approve('board')
        unit['panels'] *= 3
        self.p.put_json(prefix+'/unit.json',unit)
        self.assertNotEqual(self.shot()['board']['state'],'not_ready')
        del unit['shot_count']
        self.p.put_json(prefix+'/unit.json',unit)
        self.assertEqual(self.shot()['shot_count'],3)

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
