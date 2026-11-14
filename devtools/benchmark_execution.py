#!/usr/bin/env python3
"""Paired local timings of two source trees; no models or general utility claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def module(root):
    spec = importlib.util.spec_from_file_location('bench_store', root/'scripts/goal_store.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def invoke(root, project, *args):
    result = subprocess.run(['bash', str(root/'scripts/goal_ctl.sh'), *args, '--project', str(project)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def prepare(root, project, store, files, generations):
    project.mkdir()
    invoke(root, project, 'init')
    state = project/'.goal'
    (state/'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
        '- AC-1 | output | check: `test -s artifact` | expected: exit=0\n\n'
        '## Approval\n\napproved: PENDING\n')
    (project/'artifact').write_text('valid\n')
    invoke(root, project, 'stamp', '--auto')
    for i in range(files):
        folder = project/('package-%s' % (i % 20)); folder.mkdir(exist_ok=True)
        (folder/('file-%s.txt' % i)).write_bytes(b'bound content\n' * 10)
    if generations:
        raw = state/'evidence/raw'; raw.mkdir(exist_ok=True)
        (raw/'1.txt').write_bytes(b'original measurement\n' * 8192)
        commits = store.Store(state/'store/commits')
        head, snapshot = commits.read()
        store.attach_views(state, snapshot)
        for i in range(generations):
            head = commits.commit('bench-history-%s' % i, b'fixture history', snapshot, head)


def observed(root, project, kind, store):
    if kind == 'store':
        head, snapshot = store.Store(project/'.goal/store/commits').read()
        return head, {name: hashlib.sha256(data).hexdigest() for name, data in snapshot.items()}
    command = ([sys.executable, '-I', str(root/'scripts/goal_context.py'), 'show', str(project)]
               if kind == 'context' else
               ['bash', str(root/'scripts/goal_gate.sh'), '--digest', '--project', str(project)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    if kind == 'digest':
        return result.stdout.strip()
    value = json.loads(result.stdout)
    return {name: value.get(name) for name in ('next', 'expired', 'contract')}, {
        name: value['binding'][name] for name in ('head', 'artifact', 'work_plan', 'evidence')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, default=ROOT)
    parser.add_argument('--pairs', type=int, default=9)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 2:
        parser.error('at least two pairs required')
    roots = {'before': args.before.resolve(strict=True), 'after': args.after.resolve(strict=True)}
    stores = {label: module(root) for label, root in roots.items()}
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {label: {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted((root/'scripts').iterdir()) if p.is_file()}
                for label, root in roots.items()}
    report = dict(scope='local production entry costs; synthetic history; not end-to-end agent utility',
                  python=sys.version, platform=platform.platform(), sources=manifest, cases={})
    with tempfile.TemporaryDirectory(prefix='goal-execution-bench-') as tmp:
        for scale, files, generations in [('small', 0, 0), ('large', 2000, 35)]:
            project = Path(tmp)/scale
            prepare(roots['before'], project, stores['before'], files, generations)
            for kind in ('store', 'digest', 'context'):
                observations = []
                expected = observed(roots['before'], project, kind, stores['before'])
                for index in range(args.pairs):
                    order = ['before', 'after'] if index % 2 == 0 else ['after', 'before']
                    row = dict(order=order)
                    for label in order:
                        started = time.perf_counter()
                        value = observed(roots[label], project, kind, stores[label])
                        row[label] = time.perf_counter() - started
                        if value != expected:
                            raise RuntimeError('observed state/identity changed: ' + scale + '/' + kind)
                    observations.append(row)
                totals = {label: sum(row[label] for row in observations) for label in roots}
                report['cases'][scale+'-'+kind] = dict(pairs=observations,
                    median_seconds={label: statistics.median(row[label] for row in observations) for label in roots},
                    cost_gain=1-totals['after']/totals['before'],
                    after_faster_pairs=sum(row['after'] < row['before'] for row in observations),
                    identities_equal=True)
                (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({name: {k: v for k, v in value.items() if k != 'pairs'}
                      for name, value in report['cases'].items()}, indent=2))


if __name__ == '__main__':
    main()
