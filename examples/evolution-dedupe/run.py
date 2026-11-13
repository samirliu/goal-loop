#!/usr/bin/env python3
"""Paired cost experiment: ordered deduplication, then an optional counterexample.

The observed policy gain is specific to these task distributions. This demo
proves experiment/activation/withdrawal mechanics, not superiority over /goal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '''def dedupe(items):
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
'''
CANDIDATE = '''def dedupe(items):
    return list(dict.fromkeys(items))
'''
REPAIRED = '''def dedupe(items):
    try:
        return list(dict.fromkeys(items))
    except TypeError:
        result = []
        for item in items:
            if item not in result:
                result.append(item)
        return result
'''
DRIVER = '''import json,sys
json.dump(dedupe(json.load(sys.stdin)["items"]),sys.stdout)
'''
GRADER = '''import json,sys
case=json.load(sys.stdin)
try:
    output=json.loads(case["output"])
    expected=json.loads(case["expected"])
    passed=output==expected
    horizon=isinstance(output,list)
except (ValueError,TypeError):
    passed=False; horizon=False
print(json.dumps({"floor":passed,"horizon":horizon,"score":int(passed)}))
'''


def capture_checkpoints(project, candidate):
    scripts = ROOT / 'scripts'

    def invoke(command, *args):
        result = subprocess.run([*command, *args, '--project', str(project)],
                                check=True, stdout=subprocess.PIPE, text=True, timeout=20)
        return result.stdout.strip()

    ctl = ['bash', str(scripts / 'goal_ctl.sh')]
    store = [sys.executable, '-I', str(scripts / 'goal_store.py'), 'incumbent']
    marker = project / '.goal' / 'dedupe-baseline'
    if not marker.exists():
        project.mkdir(parents=True, exist_ok=True)
        invoke(ctl, 'init')
        (project / 'app.py').write_text('from ordered import dedupe\n' + DRIVER)
        (project / 'ordered.py').write_text(BASELINE)
        (project / '.goal/goal.md').write_text(
            '# Goal\n\n## Acceptance criteria\n\n'
            '- AC-1 | preserves order | check: `python3 -B -c "from ordered import dedupe; '
            'assert dedupe([2, 1, 2]) == [2, 1]"` | expected: exit=0\n\n'
            '## Approval\n\napproved: PENDING\n')
        invoke(ctl, 'stamp', '--auto')
        invoke(ctl, 'close-iteration', '--task', 'T1', '--files', 'app.py,ordered.py', '--checks-pass', '1',
               '--checks-fail', '0', '--checks-unverifiable', '0', '--progress', 'yes', '--exit-signal', 'yes',
               '--adversarial', 'clear', '--adversarial-note', 'fresh deterministic check', '--no-gate')
        baseline = invoke(store, 'save', '--file', 'app.py', '--file', 'ordered.py')
        marker.write_text(baseline + '\n')
    baseline = marker.read_text().strip()
    (project / 'ordered.py').write_text(candidate)
    return {'baseline': baseline, 'candidate': invoke(store, 'candidate', '--base', baseline), 'entry': 'app.py'}


def prepare(root, counterexample=False, repair=False, project=None, candidate_file=None, seed_offset=0, task_family='values', pairs=None):
    root.mkdir(parents=True, exist_ok=True)
    candidate = Path(candidate_file).read_text() if candidate_file is not None else REPAIRED if repair else CANDIDATE
    (root / 'grader.py').write_text(GRADER)
    if project is None:
        (root / 'baseline.py').write_text(BASELINE + DRIVER)
        (root / 'candidate.py').write_text(candidate + DRIVER)
        policies = {'baseline': 'baseline.py', 'candidate': 'candidate.py'}
    else:
        policies = capture_checkpoints(project, candidate)
    phases = {}
    count = (14 if repair else 6) if pairs is None else pairs
    if type(count) is not int or count < 6:
        raise ValueError('at least six paired inputs are required')
    for phase, offset in (('development', 17), ('holdout', 10017)):
        cases = []
        for index in range(count):
            randomizer = random.Random(seed_offset + offset + index + (20000 if repair else 0))
            size = 7000 + index * 500 if phase == 'development' else 10000 + index * 500
            items = [randomizer.randrange(size) for _ in range(size)]
            if task_family == 'paths':
                items = ['src/package_%s/module_%s.py' % (item % 97, item) for item in items]
            elif task_family == 'hash-collisions':
                items = [item * sys.hash_info.modulus for item in items]
            if counterexample or (repair and index >= count-2):
                items = [[item] for item in items[:300]] + items[:100]
            expected, seen = [], set()
            for item in items:
                identity = json.dumps(item, sort_keys=True)
                if identity not in seen:
                    seen.add(identity); expected.append(item)
            input_name, expected_name = '%s-%s.input.json' % (phase, index), '%s-%s.expected.json' % (phase, index)
            (root / input_name).write_text(json.dumps({'items': items}))
            (root / expected_name).write_text(json.dumps(expected))
            cases.append({'input': input_name, 'expected': expected_name})
        phases[phase] = cases
    protocol = dict(version=1 if project is None else 2, grader='grader.py',
                    minimum_pairs=6, minimum_cost_gain=0.15, quality_tolerance=0,
                    trial_seconds=5, budget_seconds=60, **phases, **policies)
    path = root / 'protocol.json'
    path.write_text(json.dumps(protocol, indent=2))
    (root / 'proposal-source.json').write_text(json.dumps(dict(
        candidate_origin='supplied-file' if candidate_file is not None else 'built-in-replay',
        source_sha256=hashlib.sha256(candidate.encode()).hexdigest(),
        task_family=task_family, seed_offset=seed_offset), indent=2)+'\n')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checkpoint', action='store_true', help='compare two-file artifact checkpoints from a real goal project')
    parser.add_argument('--candidate-file', type=Path, help='actual proposed dedupe function source, not a built-in replay')
    parser.add_argument('--seed-offset', type=int, default=0, help='fresh input identities; previous holdout may not be reused')
    parser.add_argument('--task-family', choices=('values', 'paths', 'hash-collisions'), default='values')
    parser.add_argument('--pairs', type=int, help='predeclare pairs per development/holdout phase, at least 6')
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument('--counterexample', action='store_true')
    phase.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    project = args.output / 'project' if args.checkpoint else None
    name = 'counterexample' if args.counterexample else 'repaired' if args.repair else 'integer-cases'
    protocol = prepare(args.output / name, args.counterexample, args.repair, project,
                       args.candidate_file, args.seed_offset, args.task_family, args.pairs)
    runner = [sys.executable, '-I', str(ROOT / 'scripts/goal_evolve.py')]
    state_args = ['--state', str(args.output / 'state')]
    project_args = ['--project', str(project)] if project else []
    decision = subprocess.check_output([*runner, str(protocol), *state_args, *project_args], text=True)
    print(decision.strip())
    if project and json.loads(decision)['status'] == 'withdrawn':
        frozen = json.loads(protocol.read_bytes())
        subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/goal_store.py'), 'incumbent', 'restore',
                        '--project', str(project), '--base', frozen['baseline'], '--candidate', frozen['candidate']],
                       check=True, timeout=20)
        subprocess.run(['bash', str(ROOT / 'scripts/goal_gate.sh'), '--project', str(project), '--check'],
                       check=True, timeout=20)
    enabled = json.loads((args.output / 'state/enabled.json').read_bytes())
    if enabled['policy'] is not None:
        program = args.output / 'state' / enabled['program']
        assert hashlib.sha256(program.read_bytes()).hexdigest() == enabled['policy']
        case = json.loads(protocol.read_bytes())['development'][0]
        output = subprocess.run([*runner, 'run-enabled', *state_args, '--seconds', '5'],
                                input=(protocol.parent / case['input']).read_bytes(),
                                capture_output=True, timeout=5, check=True)
        assert json.loads(output.stdout) == json.loads((protocol.parent / case['expected']).read_bytes())
        print('enabled artifact independently rechecked: PASS')
