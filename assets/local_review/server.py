#!/usr/bin/env python3
"""Local, file-first review workbench. Python 3.10+, standard library only.

Not a public web service. Run with a dedicated media project, not your home directory.
HTTP/file review foundation adapted from the user-provided local review starter.
workbench.py extends it with unit review, uploads and the H3 worker.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
import webbrowser

BASE = Path(__file__).resolve().parent
TEXT_EXT = {'.md', '.txt', '.json', '.yaml', '.yml', '.csv', '.srt', '.vtt', '.ass'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
VIDEO_EXT = {'.mp4', '.webm', '.mov', '.m4v', '.mkv'}
AUDIO_EXT = {'.wav', '.mp3', '.m4a', '.ogg', '.flac'}
IGNORE_DIRS = {'node_modules', '__pycache__', 'venv', 'service', 'jobs', 'history', 'reviews'}
MAX_TEXT = 2 * 1024 * 1024
ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,100}$')


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


class UserError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Project:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise UserError('项目目录不存在')
        self.lock = threading.RLock()
        self.hash_cache: dict[str, tuple[tuple[int, ...], str]] = {}

    def safe(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative:
            raise UserError('无效的相对路径')
        p = Path(relative)
        if p.is_absolute() or any(x in ('.', '..') or x.startswith('.') or x in {'node_modules', '__pycache__', 'venv', 'service'} for x in p.parts):
            raise UserError('只允许访问项目内的非隐藏文件', 403)
        # Reject symlinks rather than following them, including links inside the project.
        current = self.root
        for part in p.parts:
            current = current / part
            if current.is_symlink():
                raise UserError('不允许通过符号链接访问文件', 403)
        result = current.resolve()
        if not result.is_relative_to(self.root):
            raise UserError('路径越过项目边界', 403)
        return result

    def read_json(self, relative: str) -> dict:
        path = self.safe(relative)
        if path.stat().st_size > MAX_TEXT:
            raise UserError(f'JSON 超过大小限制：{relative}')
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            raise UserError(f'JSON 必须是对象：{relative}')
        return value

    def file_hash(self, relative: str, force: bool = False) -> str | None:
        path = self.safe(relative)
        if not path.is_file():
            return None
        st = path.stat()
        key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        cached = self.hash_cache.get(relative)
        if not force and cached and cached[0] == key:
            return cached[1]
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        after = path.stat()
        next_key = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if key != next_key:
            raise UserError(f'文件正在写入，请写完后重试：{relative}', 409)
        value = h.hexdigest()
        self.hash_cache[relative] = (key, value)
        return value

    def atomic_write(self, relative: str, data: bytes) -> None:
        path = self.safe(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name('.tmp-' + uuid.uuid4().hex)
        try:
            with tmp.open('xb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        self.hash_cache.pop(relative, None)

    def put_json(self, relative: str, value: object) -> None:
        self.atomic_write(relative, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())

    def backup(self, relative: str) -> None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        target = f'history/{relative}/{stamp}-{uuid.uuid4().hex[:8]}.bak'
        self.atomic_write(target, self.safe(relative).read_bytes())

    def list_files(self, force: bool = False) -> list[dict]:
        files = []
        for folder, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in IGNORE_DIRS and not (Path(folder) / d).is_symlink())
            for name in sorted(names):
                if name.startswith('.') or name.endswith(('.part', '.tmp')):
                    continue
                path = Path(folder) / name
                if path.is_symlink() or not path.is_file():
                    continue
                rel = path.relative_to(self.root).as_posix()
                try:
                    st = path.stat()
                    suffix = path.suffix.lower()
                    kind = '文本' if suffix in TEXT_EXT else '图片' if suffix in IMAGE_EXT else '视频' if suffix in VIDEO_EXT else '音频' if suffix in AUDIO_EXT else '文件'
                    files.append({'path': rel, 'kind': kind, 'bytes': st.st_size,
                                  'mtime': st.st_mtime, 'hash': self.file_hash(rel, force)})
                except FileNotFoundError:
                    continue  # An external writer may atomically rename files during a scan.
        return files

    def review(self, key: str, fingerprint: str, exists: bool = True, blocked: bool = False) -> dict:
        name = 'reviews/' + key.replace(':', '--') + '.json'
        latest = None
        if self.safe(name).exists():
            log = self.read_json(name)
            latest = log.get('latest')
        state = 'missing' if not exists else 'blocked' if blocked else 'pending'
        if exists and not blocked and latest:
            state = latest.get('decision', 'pending') if latest.get('fingerprint') == fingerprint else 'stale'
        return {'state': state, 'fingerprint': fingerprint, 'record': latest}

    def snapshot(self, force: bool = False) -> dict:
        with self.lock:
            project = self.read_json('project.json')
            inventory = self.list_files(force)
            file_map = {f['path']: f for f in inventory}
            errors: list[str] = []
            claimed: set[str] = {'project.json'}
            episodes = []
            all_ids: set[str] = set()

            def ref(relative: object, required: bool = True) -> dict:
                if not isinstance(relative, str) or not relative:
                    return {'path': '', 'hash': None, 'missing': required}
                self.safe(relative)
                claimed.add(relative)
                f = file_map.get(relative)
                return {'path': relative, 'hash': f['hash'] if f else None, 'missing': required and not f}

            configs = sorted(self.root.glob('episodes/*/episode.json'))
            for config in configs:
                rel = config.relative_to(self.root).as_posix()
                try:
                    ep = self.read_json(rel)
                    eid = ep['id']
                    if not isinstance(eid, str) or not ID_PATTERN.fullmatch(eid) or eid in all_ids:
                        raise UserError(f'分集 ID 无效或重复：{eid}')
                    all_ids.add(eid)
                    claimed.add(rel)
                    script = ref(ep.get('script'))
                    script_fp = digest({'episode_id': eid, 'title': ep.get('title', ''), 'script': script})
                    script_gate = self.review('script:' + eid, script_fp, bool(script['hash']))
                    board_text = ref(ep.get('storyboard'))
                    shots = []
                    for shot_path in sorted(config.parent.glob('units/*/unit.json')):
                        shot_rel = shot_path.relative_to(self.root).as_posix()
                        try:
                            item = self.read_json(shot_rel)
                            sid = item['id']
                            if not isinstance(sid, str) or not ID_PATTERN.fullmatch(sid) or sid in all_ids:
                                raise UserError(f'镜头 ID 无效或重复：{sid}')
                            all_ids.add(sid)
                            claimed.add(shot_rel)
                            files = item.get('files', {})
                            selected = item.get('selected', {})
                            if not isinstance(files, dict) or not isinstance(selected, dict):
                                raise UserError('files / selected 必须是对象')
                            refs = [ref(p) for p in item.get('references', [])]
                            prompts = {k: ref(files.get(k)) for k in ('image_prompt', 'video_prompt', 'params')}
                            image = ref(selected.get('image'), required=bool(selected.get('image')))
                            video = ref(selected.get('video'))
                            board_content = {k: v for k, v in item.items() if k not in ('selected', 'files', 'references')}
                            board_fp = digest({'script': script_fp, 'board_text': board_text,
                                               'shot': board_content, 'prompts': prompts, 'refs': refs, 'image': image})
                            board_exists = bool(board_text['hash']) and all(not r['missing'] for r in [*refs, *prompts.values(), image])
                            board_gate = self.review('board:' + sid, board_fp, board_exists, script_gate['state'] != 'approved')
                            video_fp = digest({'board': board_fp, 'video': video})
                            video_gate = self.review('video:' + sid, video_fp, bool(video['hash']), board_gate['state'] != 'approved')
                            prefix = shot_path.parent.relative_to(self.root).as_posix() + '/'
                            candidates = {kind: [f for f in inventory if f['path'].startswith(prefix + folder + '/') and Path(f['path']).suffix.lower() in suffixes]
                                          for kind, folder, suffixes in [('video', 'videos', VIDEO_EXT), ('image', 'images', IMAGE_EXT)]}
                            shots.append({'id': sid, 'order': int(item.get('order', 0)), 'title': item.get('title', sid),
                                          'description': item.get('description', ''), 'duration_seconds': item.get('duration_seconds', 0),
                                          'config_path': shot_rel, 'config_hash': file_map[shot_rel]['hash'],
                                          'prompts': prompts, 'references': refs, 'image': image, 'video': video,
                                          'candidates': candidates, 'board': board_gate, 'clip': video_gate})
                        except (KeyError, TypeError, ValueError, OSError, UserError) as e:
                            errors.append(f'{shot_rel}: {e}')
                    shots.sort(key=lambda s: (s['order'], s['id']))
                    bundle_fp = digest([(s['id'], s['board']['fingerprint']) for s in shots])
                    episodes.append({'id': eid, 'title': ep.get('title', eid), 'script': script,
                                     'storyboard': board_text, 'script_gate': script_gate, 'shots': shots,
                                     'board_bundle_fingerprint': bundle_fp,
                                     'ready_for_assembly': bool(shots) and all(s['clip']['state'] == 'approved' for s in shots)})
                except (KeyError, TypeError, ValueError, OSError, UserError) as e:
                    errors.append(f'{rel}: {e}')
            for f in inventory:
                f['referenced'] = f['path'] in claimed
            # Invalid entities anywhere prevent an automatic handoff. Browsing/review remain available.
            if errors:
                for ep in episodes:
                    ep['ready_for_assembly'] = False
            result = {'project': project, 'episodes': episodes, 'files': inventory, 'errors': errors}
            result['revision'] = digest(result)
            return result

    @staticmethod
    def episode(state: dict, eid: str) -> dict:
        for ep in state['episodes']:
            if ep['id'] == eid:
                return ep
        raise UserError('分集不存在', 404)

    @staticmethod
    def shot(ep: dict, sid: str) -> dict:
        for shot in ep['shots']:
            if shot['id'] == sid:
                return shot
        raise UserError('镜头不存在', 404)

    def record(self, key: str, fp: str, decision: str, note: str, reviewer: str) -> None:
        rel = 'reviews/' + key.replace(':', '--') + '.json'
        existing = self.read_json(rel) if self.safe(rel).exists() else {'history': []}
        row = {'event_id': uuid.uuid4().hex, 'at': now(), 'decision': decision, 'fingerprint': fp,
               'reviewer': reviewer or 'local-reviewer', 'note': note}
        existing['history'].append(row)
        existing['latest'] = row
        self.put_json(rel, existing)

    def action(self, data: dict) -> dict:
        with self.lock:
            action = data.get('action')
            if action == 'rescan':
                self.hash_cache.clear()
                return {'ok': True}
            if action == 'save_text':
                rel = data.get('path', '')
                path = self.safe(rel)
                if rel.startswith(('reviews/', 'history/')) or path.suffix.lower() not in TEXT_EXT:
                    raise UserError('该文件不允许在编辑器中改写')
                text = data.get('text')
                if not isinstance(text, str) or len(text.encode()) > MAX_TEXT:
                    raise UserError('文本无效或过大')
                if not path.is_file():
                    raise UserError('文件不存在', 404)
                if self.file_hash(rel, True) != data.get('expected_hash'):
                    raise UserError('文件已被外部修改；请保留草稿，重新读取后合并', 409)
                if path.suffix.lower() == '.json':
                    json.loads(text)
                self.backup(rel)
                self.atomic_write(rel, text.encode())
                return {'ok': True, 'message': '已保存，并保留原文件备份'}
            state = self.snapshot(force=True)
            ep = self.episode(state, data.get('episode', ''))
            if action == 'select':
                shot = self.shot(ep, data.get('shot', ''))
                if shot['config_hash'] != data.get('expected_hash'):
                    raise UserError('镜头配置已变化，请刷新后重试', 409)
                kind = data.get('kind')
                if kind not in ('image', 'video'):
                    raise UserError('无效的资产类型')
                path = data.get('path')
                if path not in [f['path'] for f in shot['candidates'][kind]]:
                    raise UserError('请把文件放入该镜头的 images 或 videos 目录，再选择版本')
                item = self.read_json(shot['config_path'])
                item.setdefault('selected', {})[kind] = path
                self.backup(shot['config_path'])
                self.put_json(shot['config_path'], item)
                return {'ok': True}
            if action != 'review':
                raise UserError('不支持的操作')
            if state['errors']:
                raise UserError('项目有配置错误，请修复后再提交审核')
            decision = data.get('decision')
            if decision not in ('approved', 'rejected'):
                raise UserError('审核结论只能为 approved / rejected')
            stage = data.get('stage')
            if stage == 'script':
                fp = ep['script_gate']['fingerprint']
                targets = [('script:' + ep['id'], ep['script_gate'])]
            elif stage == 'board_all':
                fp = ep['board_bundle_fingerprint']
                targets = [('board:' + s['id'], s['board']) for s in ep['shots']]
                if not targets:
                    raise UserError('当前分集没有镜头')
            elif stage in ('board', 'video'):
                shot = self.shot(ep, data.get('shot', ''))
                gate = shot['board' if stage == 'board' else 'clip']
                fp = gate['fingerprint']
                targets = [(stage + ':' + shot['id'], gate)]
            else:
                raise UserError('未知审核阶段')
            if fp != data.get('expected_fingerprint'):
                raise UserError('审核对象已经变化；请重新查看当前版本后再审核', 409)
            if any(gate['state'] in ('missing', 'blocked') for _, gate in targets):
                raise UserError('文件缺失或上游尚未审核通过，不能越过审核关卡', 409)
            note = str(data.get('note', '')).strip()[:4000]
            if decision == 'rejected' and not note:
                raise UserError('退回时请填写修改意见')
            reviewer = str(data.get('reviewer', 'local-reviewer')).strip()[:100]
            for key, gate in targets:
                self.record(key, gate['fingerprint'], decision, note, reviewer)
            return {'ok': True}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, project: Project):
        self.project = project
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)
        port = self.server_address[1]
        self.hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        self.origins = {f'http://{host}' for host in self.hosts}


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def log_message(self, fmt, *args):
        if not str(args[0]).startswith('GET /api/project'):
            super().log_message(fmt, *args)

    def guard(self, write: bool = False) -> None:
        if self.headers.get('Host') not in self.server.hosts:
            raise UserError('无效 Host', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in self.server.origins:
            raise UserError('禁止跨站访问', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise UserError('禁止跨站访问', 403)
        if write:
            if self.headers.get('X-Review-Token') != self.server.token:
                raise UserError('写入令牌无效；请重新打开页面', 403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise UserError('仅接受 JSON 请求', 415)

    def send_headers(self, status: int, content_type: str, length: int, extra: dict | None = None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def reply(self, value: object, status: int = 200):
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_headers(status, 'application/json; charset=utf-8', len(payload))
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def serve_bytes(self, payload: bytes, mime: str, extra: dict | None = None):
        self.send_headers(200, mime, len(payload), extra)
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def handle_error(self, e: Exception):
        if isinstance(e, (BrokenPipeError, ConnectionResetError)):
            return
        status = e.status if isinstance(e, UserError) else 404 if isinstance(e, FileNotFoundError) else 400 if isinstance(e, (ValueError, TypeError, KeyError)) else 500
        self.reply({'error': str(e)}, status)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self.guard()
            url = urlsplit(self.path)
            path = unquote(url.path)
            query = parse_qs(url.query)
            if path in ('/', '/index.html'):
                self.serve_bytes((BASE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            elif path == '/favicon.ico':
                self.send_headers(204, 'image/x-icon', 0)
            elif path == '/api/session':
                self.reply({'token': self.server.token})
            elif path == '/api/project':
                self.reply(self.server.project.snapshot())
            elif path == '/api/text':
                rel = query.get('path', [''])[0]
                f = self.server.project.safe(rel)
                if f.suffix.lower() not in TEXT_EXT or f.stat().st_size > MAX_TEXT:
                    raise UserError('文件不适合文本预览')
                with self.server.project.lock:
                    h = self.server.project.file_hash(rel, True)
                    expected = query.get('v', [''])[0]
                    if expected and expected != h:
                        raise UserError('文件内容已经变化，请刷新预览', 409)
                    text = f.read_text(encoding='utf-8-sig')
                self.reply({'path': rel, 'hash': h, 'text': text})
            elif path == '/api/files.csv':
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(['path', 'kind', 'bytes', 'modified_utc', 'sha256', 'referenced'])
                for f in self.server.project.snapshot()['files']:
                    values = [f['path'], f['kind'], f['bytes'], datetime.fromtimestamp(f['mtime'], timezone.utc).isoformat(), f['hash'], f['referenced']]
                    writer.writerow(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in values])
                self.serve_bytes(('\ufeff' + buf.getvalue()).encode(), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="assets-index.csv"'})
            elif path.startswith('/files/'):
                self.serve_file(path[len('/files/'):], query.get('v', [''])[0])
            else:
                raise UserError('地址不存在', 404)
        except Exception as e:
            self.handle_error(e)

    def serve_file(self, rel: str, version: str):
        p = self.server.project.safe(rel)
        if not p.is_file():
            raise UserError('文件不存在', 404)
        if version and version != self.server.project.file_hash(rel):
            raise UserError('该版本文件已经被替换；请刷新工作台', 409)
        suffix = p.suffix.lower()
        if suffix in TEXT_EXT:
            mime = 'text/plain; charset=utf-8'
        elif suffix in IMAGE_EXT | VIDEO_EXT | AUDIO_EXT:
            mime = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
        else:
            mime = 'application/octet-stream'
        extra = {'Accept-Ranges': 'bytes'}
        if mime == 'application/octet-stream':
            extra['Content-Disposition'] = 'attachment'
        with p.open('rb') as f:
            size = os.fstat(f.fileno()).st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get('Range')
            if range_header:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
                if not match or not any(match.groups()) or size == 0:
                    self.headers_response_416(size)
                    return
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                else:
                    length = int(right)
                    if length <= 0:
                        self.headers_response_416(size)
                        return
                    start = max(0, size - length)
                if start >= size or end < start:
                    self.headers_response_416(size)
                    return
                status = 206
                extra['Content-Range'] = f'bytes {start}-{end}/{size}'
            length = max(0, end - start + 1)
            self.send_headers(status, mime, length, extra)
            if self.command == 'HEAD':
                return
            f.seek(start)
            remaining = length
            while remaining:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def headers_response_416(self, size: int):
        self.send_headers(416, 'text/plain', 0, {'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})

    def do_POST(self):
        try:
            self.guard(write=True)
            if urlsplit(self.path).path != '/api/action':
                raise UserError('地址不存在', 404)
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_TEXT + 65536:
                raise UserError('请求大小无效', 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise UserError('请求必须是 JSON 对象')
            self.reply(self.server.project.action(data))
        except Exception as e:
            self.handle_error(e)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=BASE / 'demo_project')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='打开默认浏览器')
    args = parser.parse_args()
    try:
        project = Project(args.project)
        project.read_json('project.json')
        server = LocalServer(('127.0.0.1', args.port), project)
    except (OSError, ValueError, UserError) as e:
        parser.error(str(e))
    address = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'项目目录：{project.root}\n审核工作台：{address}\n仅限本机。Ctrl+C 停止。', flush=True)
    if args.open:
        webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
