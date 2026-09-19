#!/usr/bin/env python3
"""Project-local unit review server and persistent New API H3 worker."""
from __future__ import annotations
import argparse
import base64
import fcntl
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import shutil
import threading
import time
from urllib.parse import quote, urlsplit
import uuid
import webbrowser

import server as base
import newapi_h3 as h3

MAX_UPLOAD = 256 * 1024 * 1024
ACTIVE = {'queued', 'submitting', 'submitted', 'running', 'submission_unknown'}


def ident(value):
    if not isinstance(value, str) or not base.ID_PATTERN.fullmatch(value):
        raise base.UserError('无效 ID')
    return value


class Project(base.Project):
    def jobs(self):
        return sorted([self.read_json(p.relative_to(self.root).as_posix())
                for p in sorted((self.root / 'jobs').glob('*/job.json'))], key=lambda j: (j.get('created_at', ''), j['id']))

    def save_job(self, job):
        self.put_json(f"jobs/{ident(job['id'])}/job.json", job)

    def meta(self, path):
        return {'path': path, 'hash': self.file_hash(path), 'missing': not self.file_hash(path)}

    def snapshot(self, force=False):
        with self.lock:
            state = super().snapshot(force)
            jobs = self.jobs()
            for ep in state['episodes']:
                config = self.read_json(f"episodes/{ep['id']}/episode.json")
                if not self.safe(ep['script']['path']).read_text(encoding='utf-8').strip():
                    ep['script_gate']['state'] = 'missing'
                assets = [self.meta(p) for p in config.get('assets', [])]
                ep['assets'] = assets
                assets_fp = base.digest({'episode': ep['id'], 'assets': assets})
                ep['assets_gate'] = self.review('assets:' + ep['id'], assets_fp,
                    bool(config.get('assets_ready')) and all(a['hash'] for a in assets),
                    ep['script_gate']['state'] != 'approved')
                for shot in ep['shots']:
                    unit = self.read_json(shot['config_path'])
                    params = self.read_json(shot['prompts']['params']['path'])
                    slots = {'image': 0, 'video': 0, 'audio': 0}
                    extras = []
                    for r in params.get('references', []):
                        kind = r.get('kind', '')
                        slots[kind] = slots.get(kind, 0) + 1
                        extras.append(dict(self.meta(r['path']), kind=kind, slot=slots[kind], role=r.get('role', 'reference'), character_id=r.get('character_id'), look_id=r.get('look_id')))
                    panels = [self.meta(p) for p in unit.get('panels', [])]
                    shot['panels'] = panels
                    shot['execution_references'] = extras
                    shot['board']['fingerprint'] = base.digest({'base': shot['board']['fingerprint'],
                        'execution_references': extras, 'panels': panels})
                    complete = (unit.get('ready') is True and bool(panels or shot['image']['hash'])
                        and all(p['hash'] for p in panels + extras)
                        and shot['board']['state'] not in {'missing'})
                    shot['board'] = self.review('board:' + shot['id'], shot['board']['fingerprint'], complete,
                        ep['script_gate']['state'] != 'approved' or ep['assets_gate']['state'] != 'approved')
                    clip_fp = base.digest({'board': shot['board']['fingerprint'], 'video': shot['video']})
                    shot['clip'] = self.review('video:' + shot['id'], clip_fp, bool(shot['video']['hash']),
                        shot['board']['state'] != 'approved')
                    shot['jobs'] = [dict(j, input_current=j['fingerprint'] == shot['board']['fingerprint'])
                                    for j in jobs if j['episode'] == ep['id'] and j['unit'] == shot['id']]
                    shot['references'] += [r for r in extras if r['path'] not in {a['path'] for a in shot['references']}]
                ep['board_bundle_fingerprint'] = base.digest([(s['id'], s['board']['fingerprint']) for s in ep['shots']])
                ep['ready_for_assembly'] = False  # This edition delivers units only.
            state['root'] = str(self.root)
            state['asset_folders'] = sorted(p.relative_to(self.root).as_posix() for p in (self.root / 'assets').rglob('*') if p.is_dir() and not p.is_symlink() and not any(x.startswith('.') for x in p.relative_to(self.root).parts))
            state['jobs'] = jobs
            state['agent_next'] = self.next_action(state)
            state['revision'] = base.digest(state)
            return state

    def next_action(self, state):
        if state['errors']:
            return '修复项目配置；当前阻止投产。'
        units = [(e, s) for e in state['episodes'] for s in e['shots']]
        for ep in state['episodes']:
            if ep['script_gate']['state'] != 'approved':
                return f"{ep['id']}：准备/审核剧本及精简单元规划，不展开全剧详细分镜。"
            if ep['assets_gate']['state'] != 'approved':
                return f"{ep['id']}：准备当前单元所需角色造型提示词、导入声音和素材，等待素材审核。"
        for ep, s in units:
            if s['board']['state'] != 'approved':
                return f"{s['id']}：完善当前单元并等待分镜审核；不要创建下一个详细单元。"
        if units and units[0][1]['clip']['state'] != 'approved':
            return '首个样片等待视频验收；通过后再准备下一单元。'
        plan = self.read_json('plan.json')
        built = {(e['id'], s['id']) for e, s in units}
        nxt = next((u for u in plan.get('units', []) if (u['episode'], u['id']) not in built), None)
        if nxt:
            return f"准备 {nxt['episode']}/{nxt['id']} 的详细提示词和 image2.5 分镜图（也可上传）。最多一个未通过分镜的单元。"
        return '精简规划暂无后续单元；查看待审核视频或补充 plan.json。不自动剪辑。'

    def sync_catalog(self):
        """Archive each observed revision, maintaining existing h3_assets schema."""
        with self.lock:
            doc = self.read_json('asset_manifest.json')
            changed = False
            for f in self.list_files():
                p = f['path']
                if not (p.startswith(('assets/', 'sources/')) or
                        p.startswith('episodes/') and Path(p).name not in {'episode.json', 'unit.json'}):
                    continue
                logical = 'FILE-' + base.digest(p)[:20].upper()
                previous = next((r for r in doc['assets'] if r['logical_id'] == logical and r['current']), None)
                if previous and previous['sha256'] == f['hash']:
                    continue
                version = 1 if previous is None else previous['version'] + 1
                aid = f'{logical}-V{version}'
                archive = f"history/catalog/{aid}{Path(p).suffix}"
                raw = self.safe(p).read_bytes()
                import hashlib
                if hashlib.sha256(raw).hexdigest() != f['hash']:
                    continue
                self.atomic_write(archive, raw)
                if previous:
                    previous['current'] = False
                    previous['path'] = previous['archive_path']
                kind = ('source' if p.startswith('sources/') or Path(p).name == 'script.md' else
                        'audio' if Path(p).suffix.lower() in base.AUDIO_EXT else
                        'generation' if '/videos/' in p else 'panel' if '/images/' in p or '/panels/' in p else
                        'character' if p.startswith('assets/characters/') else 'prompt')
                doc['assets'].append(dict(id=aid, logical_id=logical, type=kind, role=p, path=p,
                    status='source' if kind == 'source' else 'generated' if kind == 'generation' else 'draft', version=version, current=True,
                    sha256=f['hash'], bytes=len(raw), derived_from=[previous['id']] if previous else [],
                    used_by=[], archive_path=archive))
                changed = True
            if changed:
                self.put_json('asset_manifest.json', doc)

    def validate_generation(self, ep, shot):
        unit = self.read_json(shot['config_path'])
        params = self.read_json(shot['prompts']['params']['path'])
        refs = params.get('references', [])
        if not refs:
            raise base.UserError('H3 Ref2VA 至少需要一个实际参考输入')
        for kind, maximum in [('image', 9), ('video', 3), ('audio', 3)]:
            if sum(r.get('kind') == kind for r in refs) > maximum:
                raise base.UserError('参考输入超过数量限制：' + kind)
        for r in refs:
            if r.get('kind') not in {'image', 'video', 'audio'} or not self.safe(r['path']).is_file():
                raise base.UserError('无效参考输入')
        if not 0 < float(params.get('duration_seconds', 0)) <= 30:
            raise base.UserError('必须设置明确的单元时长（0–30 秒内，具体能力以网关为准）')
        if params.get('aspect_ratio', '16:9') not in {'21:9','16:9','4:3','1:1','3:4','9:16'}:
            raise base.UserError('无效画幅')
        if not isinstance(params.get('short_edge',768), int) or params.get('short_edge',768) <= 0:
            raise base.UserError('无效分辨率')
        if not self.safe(shot['prompts']['video_prompt']['path']).read_text().strip():
            raise base.UserError('缺少视频提示词')
        if params.get('model', 'MiniMax-H3-Ref2VA') != 'MiniMax-H3-Ref2VA':
            raise base.UserError('此适配器仅接入 MiniMax-H3-Ref2VA')
        return unit, params

    def enqueue(self, ep, shot):
        unit, params = self.validate_generation(ep, shot)
        fp = shot['board']['fingerprint']
        existing = [j for j in self.jobs() if j['episode'] == ep['id'] and j['unit'] == shot['id'] and j['fingerprint'] == fp]
        if existing:
            if existing[-1]['state'] == 'stale' and not existing[-1].get('remote_id'):
                existing[-1]['state'] = 'queued'
                self.save_job(existing[-1])
            return existing[-1]  # Never blindly charge again for the same approval.
        if len(self.jobs()) >= int(self.read_json('project.json')['automation']['max_jobs']):
            raise base.UserError('已达到项目任务上限，请在项目设置中明确调整后继续')
        jid = 'JOB-' + uuid.uuid4().hex[:16]
        paths = {ep['script']['path'], ep['storyboard']['path'], shot['config_path'],
                 *(p['path'] for p in shot['prompts'].values()),
                 *(p['path'] for p in shot['references']), *(p['path'] for p in shot['panels']),
                 *(r['path'] for r in params['references'])}
        if shot['image']['path']:
            paths.add(shot['image']['path'])
        expected_hashes = {path: self.file_hash(path, True) for path in paths}
        import hashlib
        for path in sorted(paths):
            raw = self.safe(path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected_hashes[path]:
                raise base.UserError('复制输入时文件改变，请重新审核', 409)
            self.atomic_write(f'jobs/{jid}/inputs/{path}', raw)
        fresh = self.shot(self.episode(self.snapshot(True), ep['id']), shot['id'])
        if fresh['board']['fingerprint'] != fp or fresh['board']['state'] != 'approved':
            raise base.UserError('准备任务时输入已变化，请重新审核', 409)
        job = dict(id=jid, episode=ep['id'], unit=shot['id'], fingerprint=fp, state='queued',
                   created_at=base.now(), proxy_mode='direct', params=params, input_hashes=expected_hashes,
                   prompt_path=shot['prompts']['video_prompt']['path'],
                   output=f"{Path(shot['config_path']).parent.as_posix()}/videos/{jid}.mp4")
        self.save_job(job)
        return job

    def action(self, data):
        with self.lock:
            act = data.get('action')
            if act == 'save_text':
                path = data.get('path', '')
                if not path.startswith(('sources/', 'assets/', 'episodes/')):
                    raise base.UserError('网页只编辑创作文件；任务、审核及台账由服务维护', 403)
            if act == 'review' and data.get('stage') == 'script':
                ep = self.episode(self.snapshot(True), data['episode'])
                if ep['script_gate']['state'] == 'missing':
                    raise base.UserError('请先填入可审核的剧本')
            if act == 'review' and data.get('stage') == 'board_all':
                raise base.UserError('滚动生产请按单元审核')
            if act == 'review' and data.get('stage') == 'assets':
                ep = self.episode(self.snapshot(True), data['episode'])
                gate = ep['assets_gate']
                if gate['state'] in {'blocked', 'missing'} or gate['fingerprint'] != data.get('expected_fingerprint'):
                    raise base.UserError('素材未准备好、上游未通过或页面已过期', 409)
                decision = data.get('decision')
                if decision not in {'approved', 'rejected'} or decision == 'rejected' and not data.get('note', '').strip():
                    raise base.UserError('无效审核或缺少退回意见')
                self.record('assets:' + ep['id'], gate['fingerprint'], decision, data.get('note', ''), 'local-reviewer')
                return {'ok': True}
            if act == 'review' and data.get('stage') == 'board' and data.get('decision') == 'approved':
                ep = self.episode(self.snapshot(True), data['episode'])
                shot = self.shot(ep, data['shot'])
                if data.get('generate') is not True:
                    raise base.UserError('请使用“通过本单元并生成”提交审核')
                self.validate_generation(ep, shot)
                result = super().action(data)
                ep = self.episode(self.snapshot(True), data['episode'])
                result['job'] = self.enqueue(ep, self.shot(ep, data['shot']))
            else:
                result = super().action(data)
            self.sync_catalog()
            return result

    def upload(self, folder, filename, raw):
        with self.lock:
            if not folder.startswith('assets/') and not re.fullmatch(r'episodes/[A-Za-z0-9_-]+/units/[A-Za-z0-9_-]+/(images|videos|panels)', folder):
                raise base.UserError('请选择角色素材目录或单元图片/视频目录')
            suffix = Path(filename).suffix.lower()
            if suffix not in base.IMAGE_EXT | base.VIDEO_EXT | base.AUDIO_EXT:
                raise base.UserError('只允许图片、视频和音频')
            if not raw or len(raw) > MAX_UPLOAD:
                raise base.UserError('文件为空或超过 256 MB')
            path = f'{folder}/import-{uuid.uuid4().hex[:12]}{suffix}'
            self.atomic_write(path, raw)
            self.put_json(path + '.meta.json', {'source': 'manual_import', 'original_name': Path(filename).name,
                'sha256': self.file_hash(path, True), 'created_at': base.now()})
            self.sync_catalog()
            return {'ok': True, 'path': path}


def probe_media(path):
    executable = shutil.which('ffprobe')
    if executable:
        result = subprocess.run([executable, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            return {'technical_status': 'failed', 'reason': 'ffprobe 无法解析文件', 'human_review': 'pending'}
        value = json.loads(result.stdout)
        return {'technical_status': 'passed', 'streams': value.get('streams', []), 'format': value.get('format', {}), 'human_review': 'pending'}
    try:
        import av
        with av.open(str(path)) as container:
            video = next((s for s in container.streams if s.type == 'video'), None)
            if video is None or next(container.decode(video), None) is None:
                raise ValueError('no video frame')
            return {'technical_status': 'passed', 'duration_seconds': container.duration / av.time_base if container.duration else None,
                    'width': video.width, 'height': video.height, 'audio_present': any(s.type == 'audio' for s in container.streams), 'human_review': 'pending'}
    except ImportError:
        return {'technical_status': 'header_only', 'reason': '未安装 ffprobe/PyAV；仅验证 MP4 文件头', 'human_review': 'pending'}
    except Exception:
        return {'technical_status': 'failed', 'reason': 'PyAV 无法解码视频', 'human_review': 'pending'}


class Worker:
    def __init__(self, project, client_factory=None):
        self.p = project
        self.client_factory = client_factory or self.client
        self.stop = threading.Event()

    @staticmethod
    def client():
        h3.ENV_PATH = Path(os.getenv('H3_WORKBENCH_ENV_FILE', str(Path.home() / '.codex/skills/newapi-h3-direct/.env')))
        url, key = h3.settings()
        return h3.Client(url, key, 'direct', 45)

    def payload(self, job):
        params = job['params']
        root = self.p.safe(f"jobs/{job['id']}/inputs")
        refs = params['references']
        return {'model': 'MiniMax-H3-Ref2VA', 'task': 'ref2va',
            'prompt': (root / job['prompt_path']).read_text(encoding='utf-8'),
            'seconds': float(params['duration_seconds']),
            'target': {'duration_seconds': float(params['duration_seconds']),
                       'aspect_ratio': params.get('aspect_ratio', '16:9'), 'short_edge': params.get('short_edge', 768)},
            'conditions': [{'type': r['kind'], 'role': 'reference',
                            'uri': h3.data_uri(root / r['path'], r['kind'])} for r in refs],
            'seed': params.get('seed', secrets.randbelow(2**63)), 'num_outputs_per_prompt': 1,
            'num_inference_steps': params.get('steps', 9), 'flow_shift': params.get('flow_shift', 6),
            'audio_flow_shift': params.get('audio_flow_shift', 3), 'quality': params.get('quality', 'lossless')}

    def tick(self):
        with self.p.lock:
            jobs = self.p.jobs()
            pending = [j for j in jobs if j['state'] in {'submitted', 'running'}]
            job = pending[0] if pending else next((j for j in jobs if j['state'] == 'queued'), None)
            if not job:
                return
            if not pending and self.p.read_json('project.json')['automation'].get('paused'):
                return
            if not pending and any(j['state'] in {'submission_unknown', 'submitting'} for j in jobs):
                return
            if job['state'] == 'queued':
                state = self.p.snapshot(True)
                try:
                    s = self.p.shot(self.p.episode(state, job['episode']), job['unit'])
                    valid = not state['errors'] and s['board']['state'] == 'approved' and s['board']['fingerprint'] == job['fingerprint']
                except base.UserError:
                    valid = False
                if not valid:
                    job['state'] = 'stale'
                    self.p.save_job(job)
                    return
        try:
            client = self.client_factory()
        except Exception:
            with self.p.lock:
                job['message'] = 'H3 凭据未配置；设置 NEWAPI_BASE_URL / NEWAPI_API_KEY 或 H3_WORKBENCH_ENV_FILE 后重启服务。'
                self.p.save_job(job)
            return
        if job['state'] == 'queued':
            try:
                payload = self.payload(job)
                with self.p.lock:
                    current = self.p.shot(self.p.episode(self.p.snapshot(True), job['episode']), job['unit'])
                    if current['board']['state'] != 'approved' or current['board']['fingerprint'] != job['fingerprint']:
                        job['state'] = 'stale'
                        self.p.save_job(job)
                        return
                    job['state'] = 'submitting'
                    job.pop('message', None)
                    # Persist actual seed/parameters, never inline references or credentials.
                    self.p.put_json(f"jobs/{job['id']}/request.json", {k: v for k, v in payload.items() if k != 'conditions'})
                    self.p.save_job(job)
                result = client.request_json('POST', '/videos', payload)
                task_id = result.get('id') or result.get('task_id')
                if not isinstance(task_id, str) or not task_id:
                    raise ValueError('missing task ID')
                job.update(state='submitted', remote_id=task_id)
            except Exception:
                # A transport error cannot prove that the provider did not accept the job.
                job.update(state='submission_unknown', message='提交结果不确定；禁止自动重提，请由 Agent 核实远端任务。')
        else:
            try:
                remote = quote(job['remote_id'], safe='')
                response = client.request_json('GET', f'/videos/{remote}')
                status = str(response.get('status', '')).lower()
                if status in h3.FAILURE:
                    job.update(state='failed', message='远端生成失败；请查看服务端任务，返工不会自动重试。')
                elif status in h3.SUCCESS:
                    raw, _ = client.request('GET', f'/videos/{remote}/content')
                    if len(raw) < 12 or raw[4:8] != b'ftyp':
                        raise ValueError('not MP4')
                    with self.p.lock:
                        self.p.atomic_write(job['output'], raw)
                        qa = probe_media(self.p.safe(job['output']))
                        self.p.put_json(job['output'] + '.qa.json', qa)
                        if qa['technical_status'] == 'failed':
                            job.update(state='failed', message='视频无法解码，已保留文件与检查结果；不自动重试。')
                            self.p.save_job(job)
                            return
                        self.p.put_json(job['output'] + '.meta.json', {'source': 'generated', 'job_id': job['id'],
                            'input_fingerprint': job['fingerprint'], 'sha256': self.p.file_hash(job['output'], True)})
                        job.update(state='succeeded', message='已下载 MP4；待人工视频验收。')
                        ep = self.p.episode(self.p.snapshot(True), job['episode'])
                        shot = self.p.shot(ep, job['unit'])
                        config = self.p.read_json(shot['config_path'])
                        if not config['selected'].get('video') and shot['board']['state'] == 'approved' and shot['board']['fingerprint'] == job['fingerprint']:
                            config['selected']['video'] = job['output']
                            self.p.put_json(shot['config_path'], config)
                        self.p.sync_catalog()
                else:
                    job.update(state='running', message='远端任务处理中')
            except Exception:
                job['message'] = '查询或下载暂时失败；保留远端任务号，下轮重查，不重新提交。'
        with self.p.lock:
            job['updated_at'] = base.now()
            self.p.save_job(job)

    def run(self):
        with self.p.lock:
            for job in self.p.jobs():
                if job['state'] == 'submitting':
                    job.update(state='submission_unknown', message='服务在提交期间中断，需核实远端任务。')
                    self.p.save_job(job)
        while not self.stop.is_set():
            try:
                self.p.sync_catalog()
                self.tick()
            except Exception:
                # Do not serialize arbitrary provider errors or credentials into a log.
                print('任务检查失败；请检查项目文件。', flush=True)
            self.stop.wait(5)


class Handler(base.Handler):
    def do_POST(self):
        if urlsplit(self.path).path != '/api/upload':
            return super().do_POST()
        try:
            if self.headers.get('X-Review-Token') != self.server.token:
                raise base.UserError('写入令牌无效', 403)
            self.guard()
            from urllib.parse import parse_qs
            q = parse_qs(urlsplit(self.path).query)
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_UPLOAD:
                raise base.UserError('上传大小无效（上限 256 MB）', 413)
            self.reply(self.server.project.upload(q.get('folder', [''])[0], q.get('name', [''])[0], self.rfile.read(size)))
        except Exception as e:
            self.handle_error(e)


def serve(root, port=8765, open_browser=False):
    # Single writer process. The lock is released by the OS even after a crash.
    lock = (root / '.service.lock').open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('该项目审核服务已运行；请使用已有地址。')
    p = Project(root)
    p.read_json('project.json')
    server = base.LocalServer(('127.0.0.1', port), p)
    server.RequestHandlerClass = Handler
    worker = Worker(p)
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    address = f'http://127.0.0.1:{server.server_address[1]}'
    (root / '.service.json').write_text(json.dumps({'pid': os.getpid(), 'url': address, 'root': str(root)}))
    print(f'项目：{root}\n审核：{address}\nH3：直连（不使用代理）', flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop.set()
        server.server_close()
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    serve(args.project.resolve(), args.port, args.open)
