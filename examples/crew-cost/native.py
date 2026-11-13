#!/usr/bin/env python3
"""Prepare/seal a real-host trial; native tools dispatch the actual workers.

No model client, synthetic inference delay or replacement scheduler lives in
this fixture. Receipts are supplied from the caller's actual host tools.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def encode(value):
    return json.dumps(value, indent=2, sort_keys=True)+'\n'


def prepare(output, mode, reuse=None, seconds=3600, session_id='native-suite', origin_file=None):
    started = dict(epoch=time.time(), monotonic=time.monotonic())
    output.mkdir(parents=True, exist_ok=False)
    tasks = module('native_crew_tasks', ROOT / 'examples/agent-evals/tasks.py')
    host = module('native_crew_host', ROOT / 'scripts/goal_host.py')
    if reuse is None:
        control = output / 'control'; control.mkdir()
        work = output / 'work'
        tasks.prepare(work, 'medium', 911207)
        shutil.copy2(ROOT / 'examples/agent-evals/grade.py', control / 'grade.py')
        shutil.copy2(Path(__file__).with_name('native_checks.py'), control / 'job_check.py')
    else:
        work = reuse.resolve(strict=True)
        control = work.parent / 'control'
        for old in host.folder(work)[1].glob('attempt-*.json'):
            if host.load(old)['phase'] not in ('returned', 'failed', 'cancelled'):
                raise RuntimeError('active native worker; refusing to reset owned files')
        for name, code in tasks.STARTERS['medium'].items():
            (work/name).write_text(code)
    if origin_file is None:
        origin = host.capture('work', session_id, 'tool')
        origin.update(epoch=started['epoch'], monotonic=started['monotonic'])
    else:
        origin = json.loads(Path(origin_file).read_bytes())
    session = host.begin(work, 'work', session_id, seconds, origin)
    final = [sys.executable, '-B', str(control/'grade.py'), '--project', '{project}', '--family', 'medium', '--seed', '911207']
    if reuse is None:
        (work / '.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | complete auditlog behavior | check: `'+ ' '.join(s.replace('{project}', '.') for s in final) +
            '` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
        stamped = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), 'stamp', '--auto', '--project', str(work)],
                                  capture_output=True, text=True, timeout=20)
        (control/'stamp.json').write_text(encode(dict(result=stamped.returncode, stdout=stamped.stdout, stderr=stamped.stderr)))
        if stamped.returncode:
            raise RuntimeError('stamp failed; evidence retained')
    files = ['auditlog/'+n for n in ('codec.py', 'aggregate.py', '__main__.py', '__init__.py')]
    if mode == 'fused':
        jobs = [dict(id='T1', files=files, deps=[], check=[sys.executable, '-B', 'public.py'])]
    else:
        jobs = [dict(id='T1', files=[n for n in files if not n.endswith('aggregate.py')], deps=[],
                     check=[sys.executable, '-B', str(control/'job_check.py'), '{project}', 'T1']),
                dict(id='T2', files=['auditlog/aggregate.py'], deps=[],
                     check=[sys.executable, '-B', str(control/'job_check.py'), '{project}', 'T2'])]
    graph = dict(version=1, context=dict(backend='actual-Work-collaboration', task='auditlog-v1',
                                       comparison='single-worker-vs-crew-v2', controller=session_id),
                 capacity=2, jobs=jobs, final_check=final, instruments=['grade.py', 'job_check.py'],
                 inputs=['TASK.md', 'public.py'])
    path = control/('graph-fused.json' if mode == 'fused' else 'graph.json')
    data = encode(graph)
    if path.exists() and path.read_text() != data:
        raise RuntimeError('frozen graph changed')
    path.write_text(data)
    wave = host.crew.begin(work, path, 'crew' if mode == 'crew' else 'inline', output.name)
    sources = [p for p in (ROOT/'scripts').iterdir() if p.is_file() and p.suffix in ('.py', '.sh', '.awk')]
    sources += [Path(__file__), Path(__file__).with_name('native_checks.py'),
                ROOT/'examples/agent-evals/tasks.py', ROOT/'examples/agent-evals/grade.py']
    for source in sources:
        target = output/'sources'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = dict(version=1, mode=mode, started=started, host_origin=origin,
                    project=str(work), control=str(control),
                    session=session, wave=wave, native_receipt_source='actual collaboration tools, explicit bridge',
                    tokens=None, money=None, sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sources})
    (output/'manifest.json').write_text(encode(manifest))
    print(encode(dict(project=str(work), wave=wave, mode=mode)))


def seal(output):
    manifest = json.loads((output/'manifest.json').read_bytes())
    host = module('native_crew_host', ROOT/'scripts/goal_host.py')
    wave = host.crew.Wave(manifest['project'], manifest['wave'])
    result = wave.finish()
    (output/'result.json').write_text(encode(result))
    for job in result['graph']['jobs']:
        for name in job['files']:
            source = Path(manifest['project'])/name
            if source.is_file():
                target = output/'artifact'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    print(encode({k: result[k] for k in ('quality', 'elapsed', 'worker_seconds', 'stage_seconds', 'tokens', 'money')}))


def stage(output, name, phase):
    manifest = json.loads((output/'manifest.json').read_bytes())
    host = module('native_crew_host', ROOT/'scripts/goal_host.py')
    host.crew.Wave(manifest['project'], manifest['wave']).stage(name, phase)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'seal', 'stage'))
    parser.add_argument('output', type=Path)
    parser.add_argument('--mode', choices=('serial', 'crew', 'fused'))
    parser.add_argument('--reuse', type=Path, help='reuse a finished isolated project with the same frozen graph')
    parser.add_argument('--seconds', type=float, default=3600, help='whole suite allowance; reuse cannot extend it')
    parser.add_argument('--session', default='native-suite', help='observed canonical controller identity for comparable batches')
    parser.add_argument('--origin', type=Path, help='real parent host-entry receipt, captured before controller dispatch')
    parser.add_argument('--stage', choices=('coordination', 'join', 'conflict', 'revalidation', 'recovery'))
    parser.add_argument('--phase', choices=('begin', 'end', 'skip'))
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.mode is None:
            parser.error('prepare requires --mode')
        prepare(args.output.resolve(), args.mode, args.reuse, args.seconds, args.session, args.origin)
    elif args.action == 'seal':
        seal(args.output.resolve())
    else:
        if args.stage is None or args.phase is None:
            parser.error('stage requires --stage and --phase')
        stage(args.output.resolve(), args.stage, args.phase)
