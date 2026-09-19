#!/usr/bin/env python3
"""Initialize and operate a project-local H3 short-drama review workbench."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

SKILL = Path(__file__).resolve().parent.parent
RUNTIME = SKILL / 'assets/local_review'
sys.path.insert(0, str(RUNTIME))
from workbench import Project, ident


def put_new(root, path, value):
    f = root / path
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open('x', encoding='utf-8') as out:
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n' if isinstance(value, dict) else value)


def init(root, title, script=None):
    if script and not script.is_file():
        raise ValueError('原稿文件不存在')
    if root.exists() and any(root.iterdir()):
        raise ValueError('初始化只接受新目录或空目录；不会覆盖已有项目。')
    root.mkdir(parents=True, exist_ok=True)
    for folder in ('sources', 'assets/characters', 'assets/locations', 'assets/props', 'assets/style',
                   'episodes', 'jobs', 'reviews', 'history', 'deliverables'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    shutil.copytree(RUNTIME, root / 'service', ignore=shutil.ignore_patterns('__pycache__', 'test_*.py'))
    put_new(root, 'project.json', {'schema_version': 2, 'project_id': root.name, 'title': title,
        'automation': {'paused': False, 'max_jobs': 100, 'max_pending_units': 1, 'pilot_first': True},
        'video_route': 'newapi-h3-direct', 'image_route': 'image2.5-or-manual', 'audio_route': 'manual',
        'editing': False})
    put_new(root, 'asset_manifest.json', {'schema_version': 1, 'project_id': root.name, 'title': title, 'assets': [], 'generations': []})
    put_new(root, 'plan.json', {'units': []})
    if script:
        shutil.copy2(script, root / 'sources' / script.name)
    put_new(root, 'AGENTS.md', f'''# 短剧项目

- 创作 Skill：{SKILL / 'SKILL.md'}
- 本项目采用 `reference/LOCAL_PROJECT_WORKFLOW.md` 的滚动单元流程，优先于旧的静态 HTML / ComfyUI 流程。
- 先完整阅读 sources，再写精简 plan.json；最多一个未通过分镜审核的详细单元。首个单元视频验收后再扩展。
- 角色的 identity、looks/LOOKxx、voice 放在同一个角色目录。声音由用户提供；造型和分镜图由 image2.5 或用户导入。
- 人工结论以 reviews 为准；Agent 不得自行写通过记录。单元图和提示词在网页整体审核，通过并生成即授权一次 H3 任务。
- Agent 创作文件原子写入，保留人工修改；通过后不原地覆盖。服务维护 jobs、reviews、asset_manifest.json。
- 运行：`python3 service/workbench.py --open`（在项目根目录）。状态：访问 /api/project 或 Skill 的 h3_project.py status。
- 启动前检查 .service.json 和现有服务；项目服务只绑定 127.0.0.1。不自动剪辑。
- API 密钥只从环境或外部 H3_WORKBENCH_ENV_FILE 读取，禁止写入本项目。默认 H3 直连，不走代理。
- 页面意见不会主动唤醒已结束的 Agent；Agent 活跃时读取状态推进，结束后用户调用“继续这个项目”。不要声称有后台文字模型。
''')
    put_new(root, '启动审核.command', '#!/bin/sh\ncd "$(dirname "$0")"\nexec python3 service/workbench.py --open\n')
    (root / '启动审核.command').chmod(0o755)
    episode(root, 'EP001', title)
    Project(root).sync_catalog()


def episode(root, eid, title):
    ident(eid)
    prefix = f'episodes/{eid}'
    if (root / prefix).exists():
        raise ValueError('分集已存在')
    put_new(root, prefix + '/episode.json', {'id': eid, 'title': title, 'script': prefix + '/script.md',
        'storyboard': prefix + '/storyboard.md', 'assets': [], 'assets_ready': False})
    put_new(root, prefix + '/script.md', '')
    put_new(root, prefix + '/storyboard.md', '')
    (root / prefix / 'units').mkdir()


def character(root, cid, name, looks):
    ident(cid)
    prefix = f'assets/characters/{cid}'
    if (root / prefix).exists():
        raise ValueError('角色已存在')
    for look in looks:
        ident(look)
    put_new(root, prefix + '/character.json', {'id': cid, 'name': name, 'identity': None, 'voice': None,
        'looks': {look: {'image': None, 'prompt': f'{prefix}/looks/{look}/prompt.md'} for look in looks}})
    for folder in ('identity', 'voice', *(f'looks/{look}' for look in looks)):
        (root / prefix / folder).mkdir(parents=True, exist_ok=True)
    for look in looks:
        put_new(root, f'{prefix}/looks/{look}/prompt.md', '')
    put_new(root, prefix + '/voice/description.md', '')


def unit(root, eid, uid, title):
    ident(eid); ident(uid)
    p = Project(root)
    state = p.snapshot(True)
    ep = p.episode(state, eid)
    if ep['script_gate']['state'] != 'approved' or ep['assets_gate']['state'] != 'approved':
        raise ValueError('先完成剧本和素材阶段审核')
    built = [(e, s) for e in state['episodes'] for s in e['shots']]
    if any(s['board']['state'] != 'approved' for e, s in built):
        raise ValueError('已有待审单元；最多只展开一个详细单元')
    if built and state['project']['automation']['pilot_first'] and built[0][1]['clip']['state'] != 'approved':
        raise ValueError('先验收首个样片视频，再准备下一单元')
    plan = p.read_json('plan.json')['units']
    known = {(e['id'], s['id']) for e, s in built}
    nxt = next((u for u in plan if (u['episode'], u['id']) not in known), None)
    if not nxt or (nxt['episode'], nxt['id']) != (eid, uid):
        raise ValueError('只能展开 plan.json 中下一个未制作单元')
    prefix = f'episodes/{eid}/units/{uid}'
    if (root / prefix).exists():
        raise ValueError('单元已存在')
    put_new(root, prefix + '/unit.json', {'id': uid, 'order': len(ep['shots']) + 1, 'title': title,
        'description': '', 'duration_seconds': nxt.get('duration_seconds', 0), 'ready': False,
        'files': {'image_prompt': prefix + '/prompts/image.md', 'video_prompt': prefix + '/prompts/video_en.md',
                  'params': prefix + '/params.json'},
        'references': [prefix + '/prompts/video_zh.md'], 'panels': [],
        'selected': {'image': None, 'video': None}})
    for file in ('image.md', 'video_en.md', 'video_zh.md'):
        put_new(root, prefix + '/prompts/' + file, '')
    put_new(root, prefix + '/params.json', {'model': 'MiniMax-H3-Ref2VA',
        'duration_seconds': nxt.get('duration_seconds', 0), 'aspect_ratio': '16:9', 'short_edge': 768,
        'references': []})
    for folder in ('images', 'panels', 'videos'):
        (root / prefix / folder).mkdir()


def status(root):
    state = Project(root).snapshot(True)
    return {'project': str(root), 'next': state['agent_next'], 'errors': state['errors'],
        'episodes': [{'id': e['id'], 'script': e['script_gate']['state'], 'assets': e['assets_gate']['state'],
                      'units': [{'id': s['id'], 'board': s['board']['state'], 'video': s['clip']['state']}
                                for s in e['shots']]} for e in state['episodes']],
        'jobs': [{k: j.get(k) for k in ('id', 'unit', 'state', 'message', 'remote_id')} for j in state['jobs']]}


def start(root, port):
    root = root.resolve()
    marker = root / '.service.json'
    opener = build_opener(ProxyHandler({}))
    if marker.exists():
        saved = json.loads(marker.read_text())
        try:
            with opener.open(saved['url'] + '/api/project', timeout=2) as response:
                if json.load(response).get('root') == str(root):
                    return saved['url']
        except Exception:
            pass
    with (root / '.service.log').open('ab') as log:
        child = subprocess.Popen([sys.executable, str(root / 'service/workbench.py'), '--project', str(root), '--port', str(port)],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        if child.poll() is not None:
            raise ValueError('服务启动失败，请查看项目 .service.log 最后 100 行')
        if marker.exists():
            saved = json.loads(marker.read_text())
            if saved.get('pid') == child.pid:
                try:
                    with opener.open(saved['url'] + '/api/project', timeout=1) as response:
                        if json.load(response).get('root') == str(root):
                            return saved['url']
                except Exception:
                    pass
        time.sleep(.1)
    raise ValueError('服务启动超时；请检查 .service.log，避免重复启动')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for cmd in ('init', 'start', 'status', 'episode', 'character', 'unit'):
        p = sub.add_parser(cmd)
        p.add_argument('project', type=Path)
        if cmd in {'init', 'episode', 'unit'}:
            p.add_argument('--title', required=True)
        if cmd in {'start', 'init'}:
            p.add_argument('--port', type=int, default=8765)
        if cmd == 'init':
            p.add_argument('--script', type=Path)
            p.add_argument('--start', action='store_true')
        if cmd == 'episode':
            p.add_argument('--id', required=True)
        if cmd == 'character':
            p.add_argument('--id', required=True); p.add_argument('--name', required=True)
            p.add_argument('--looks', nargs='+', default=['LOOK01'])
        if cmd == 'unit':
            p.add_argument('--episode', required=True); p.add_argument('--id', required=True)
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.command == 'init':
            init(root, args.title, args.script)
            print(start(root, args.port) if args.start else root)
        elif args.command == 'start':
            print(start(root, args.port))
        elif args.command == 'status':
            print(json.dumps(status(root), ensure_ascii=False, indent=2))
        elif args.command == 'episode':
            episode(root, args.id, args.title)
        elif args.command == 'character':
            character(root, args.id, args.name, args.looks)
        elif args.command == 'unit':
            unit(root, args.episode, args.id, args.title)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
