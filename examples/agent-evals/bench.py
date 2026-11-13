#!/usr/bin/env python3
"""Prepare and adjudicate fresh host-agent trials with a fixed outer deadline."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('agent_eval_tasks', Path(__file__).with_name('tasks.py'))
tasks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tasks)
BUDGET = 600


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n')
    os.replace(temporary, path)


def source_files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes().decode('utf-8', errors='replace')
            for path in root.rglob('*') if path.is_file() and '__pycache__' not in path.parts}


def brief(folder, workspace, package, arm):
    common = f'''Execute one fresh benchmark attempt. Your workdir is {workspace}.
Read TASK.md, public.py and permitted source. Implement all requirements and
test actual behavior. Do not change TASK.md/public.py or the skill package.
Do not read hidden evaluators, other trials, gold fixtures or the root repository.
Work serially: you plus the controller use the capacity of two model agents.
Read {folder}/LIMIT.json for the dispatch deadline. The 600 seconds include
reading, planning, startup, implementation, testing and independent acceptance.
Aim to finish 35 seconds before cutoff. Stop on the sibling STOP file or deadline.
Retain actual test output and failures in tests-run.txt (or .goal/evidence/).
Finish ALL artifact/evidence writes before atomically publishing
{folder}/DONE.json with honest complete, tests and gate fields. Then stop writes.
The marker and READY/STOP belong outside the work tree; do not invalidate a
finished artifact by adding a control message inside it. Do not await permission.
'''
    modes = {
        'plain': 'Use your ordinary implement/test/fix workflow. Do not use goal-loop or native Goal tools.\n',
        'skill': f'''Read {package}/SKILL.md and apply the actual normal goal-loop lifecycle,
including the small-task fast lane when appropriate. Automatic execution is
authorized. Stamp with only the remaining budget, use project-relative check
commands, and obtain an actual final gate result. Do not call native Goal tools.
''',
        'native': '''Use the actual host native Goal tools: create_goal with objective exactly
the full TASK.md text, then get_goal to verify persistence. Work toward that goal
using your ordinary tools. Mark complete only after all task requirements pass.
Before DONE, retain native-goal.json in the work tree with actual thread_id,
objective, created_status, status, tokens_used, and full raw create/get/completion
receipts. Do not use goal-loop. Native accounting is partial and must not be
invented. If unfinished, keep the real goal state and report failure honestly.
''',
    }
    return common + '\n' + modes[arm]


def prepare(root, pilot=False):
    root.mkdir(parents=True, exist_ok=False)
    package = root / 'skill'
    for name in ('scripts', 'assets', 'agents', 'references'):
        shutil.copytree(ROOT / name, package / name, ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))
    shutil.copy2(ROOT / 'SKILL.md', package / 'SKILL.md')
    oracle = root / 'oracle'
    oracle.mkdir()
    for name in ('grade.py', 'tasks.py', 'bench.py', 'pre-reg.md', 'report.py', 'check_harness.py'):
        shutil.copy2(Path(__file__).with_name(name), oracle / name)
    frozen = {str(path): sha(path) for folder in (package, oracle) for path in folder.rglob('*') if path.is_file()}
    trials = []
    families = ['small'] if pilot else list(tasks.TASKS)
    for family_index, family in enumerate(families):
        for repetition in range(1 if pilot else 3):
            seed = (9137 if pilot else 329003) + family_index * 100 + repetition
            order = ('plain', 'skill', 'native')
            shift = (family_index + repetition) % 3
            for arm in order[shift:] + order[:shift]:
                folder = root / 'trials' / uuid.uuid4().hex
                folder.mkdir(parents=True)
                workspace = folder / 'work'
                tasks.prepare(workspace, family, seed)
                protected = {name: sha(workspace / name) for name in ('TASK.md', 'public.py')}
                if family == 'recovery':
                    protected['seed-data/source.jsonl'] = sha(workspace / 'seed-data/source.jsonl')
                config = dict(version=1, arm=arm, family=family, seed=seed, repetition=repetition,
                              status='prepared', workspace=str(workspace), skill=str(package),
                              oracle=str(oracle / 'grade.py'), frozen=frozen, protected=protected,
                              initial=source_files(workspace), budget_seconds=BUDGET,
                              started=None, start_monotonic=None, deadline=None, first_valid=None,
                              observations=[], agent=None, tokens=None, money=None)
                (folder / 'BRIEF.md').write_text(brief(folder, workspace, package, arm))
                config['brief_sha256'] = sha(folder / 'BRIEF.md')
                save(folder / 'trial.json', config)
                trials.append(str(folder))
    save(root / 'manifest.json', dict(version=1, pilot=pilot, capacity=2, simultaneous_trials=1,
                                     arms=['plain', 'skill', 'native'], trials=trials,
                                     model='parent-inherited; no override', host='Codex collaboration host',
                                     host_build=None, budget_seconds=BUDGET, frozen=frozen))
    return trials


def bounded(config, command, cwd, seconds):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-I', config['skill'] + '/scripts/goal_bounded.py',
                             '--owner', str(os.getpid()), '--seconds', str(seconds), '--', *command],
                            cwd=cwd, env=env, capture_output=True, timeout=seconds + 4)
    return dict(result=result.returncode, stdout=result.stdout.decode('utf-8', 'replace'),
                stderr=result.stderr.decode('utf-8', 'replace'))


def start(folder, agent=None):
    path = folder / 'trial.json'
    config = json.loads(path.read_bytes())
    if config['status'] != 'prepared':
        raise ValueError('trial already dispatched')
    config.update(status='running', started=time.time(), start_monotonic=time.monotonic(),
                  deadline=time.time() + config['budget_seconds'], agent=agent)
    save(folder / 'LIMIT.json', {k: config[k] for k in ('started', 'deadline', 'budget_seconds')})
    save(path, config)
    return {name: config[name] for name in ('arm', 'family', 'seed', 'workspace', 'skill', 'deadline', 'budget_seconds')}


def attach(folder, agent):
    """Retain the actual host dispatch acknowledgement, separately from the artifact."""
    config = json.loads((folder / 'trial.json').read_bytes())
    if config['status'] != 'running' or not agent:
        raise ValueError('a running trial and actual host agent name are required')
    path = folder / 'host.json'
    if path.exists():
        raise ValueError('host dispatch already attached')
    event = dict(agent=agent, acknowledged=time.time(),
                 acknowledged_seconds=time.monotonic() - config['start_monotonic'])
    save(path, event)
    return event


def sidecar(folder, name):
    try:
        return json.loads((folder / name).read_bytes())
    except (OSError, ValueError):
        return None


def observe(folder):
    path = folder / 'trial.json'
    config = json.loads(path.read_bytes())
    elapsed = time.monotonic() - config['start_monotonic']
    if config['status'] != 'running':
        return dict(status=config['status'], elapsed=elapsed)
    if elapsed >= config['budget_seconds']:
        return dict(status='deadline', elapsed=elapsed)
    result = bounded(config, [sys.executable, '-B', 'public.py'], config['workspace'],
                     min(12, config['budget_seconds'] - elapsed))
    result['elapsed_from_dispatch'] = time.monotonic() - config['start_monotonic']
    config['observations'].append(result)
    if result['result'] == 0 and config['first_valid'] is None:
        config['first_valid'] = result['elapsed_from_dispatch']
    save(path, config)
    return dict(status='running', elapsed=result['elapsed_from_dispatch'], public_pass=result['result'] == 0,
                first_valid=config['first_valid'])


def finish(folder, terminal='returned', message=None):
    path = folder / 'trial.json'
    config = json.loads(path.read_bytes())
    if (folder / 'result.json').is_file():
        return json.loads((folder / 'result.json').read_bytes())
    if config['status'] != 'running':
        raise ValueError('trial is not running')
    returned = time.monotonic() - config['start_monotonic']
    snapshot = folder / 'snapshot'
    shutil.copytree(config['workspace'], snapshot, ignore=shutil.ignore_patterns('__pycache__'))
    frozen = all(Path(name).is_file() and sha(Path(name)) == expected for name, expected in config['frozen'].items())
    frozen = frozen and sha(folder / 'BRIEF.md') == config['brief_sha256']
    protected = all((snapshot / name).is_file() and sha(snapshot / name) == expected for name, expected in config['protected'].items())
    command = [sys.executable, '-I', '-B', config['oracle'], '--project', str(snapshot),
               '--family', config['family'], '--seed', str(config['seed'])]
    grade = bounded(config, command, snapshot, 20)
    gate = None
    if config['arm'] == 'skill':
        gate = bounded(config, ['bash', config['skill'] + '/scripts/goal_gate.sh', '--project', str(snapshot), '--check'],
                       snapshot, 15)
    quality = None
    try:
        quality = json.loads(grade['stdout'])
    except ValueError:
        pass
    current = source_files(snapshot)
    allowed = set(tasks.STARTERS[config['family']])
    extra = set(current) - set(config['initial'])
    changed = {name for name in config['initial'] if current.get(name) != config['initial'][name]}
    in_scope = changed <= allowed | {'BENCHMARK.md', 'seed-data/output.jsonl', 'seed-data/state.json'}
    patch = []
    for name in sorted(set(config['initial']) | set(current)):
        if name.startswith('.goal/') or name in config['protected']:
            continue
        patch.extend(difflib.unified_diff(config['initial'].get(name, '').splitlines(keepends=True),
                                          current.get(name, '').splitlines(keepends=True),
                                          fromfile='a/' + name, tofile='b/' + name))
    (folder / 'artifact.patch').write_text(''.join(patch))
    elapsed = time.monotonic() - config['start_monotonic']
    protocol = gate is None or gate['result'] == 0
    native = None
    if config['arm'] == 'native':
        native_path = snapshot / 'native-goal.json'
        try:
            native = json.loads(native_path.read_bytes()) if native_path.is_file() else None
        except (ValueError, OSError):
            native = None
        protocol = bool(isinstance(native, dict) and native.get('thread_id') and native.get('status') == 'complete'
                        and native.get('objective') == (snapshot / 'TASK.md').read_text())
        if not isinstance(native, dict):
            native = None
    result = dict(version=1, arm=config['arm'], family=config['family'], seed=config['seed'],
                  terminal=terminal, returned_seconds=returned, independent_finished_seconds=elapsed,
                  first_observed_public_pass=config['first_valid'], quality=quality, grader=grade, gate=gate,
                  frozen=frozen, protected=protected, edits_in_scope=in_scope, extra_files=sorted(extra),
                  native_goal=native, tokens=native.get('tokens_used') if native else None, money=None,
                  protocol_compliant=protocol,
                  host_dispatch=sidecar(folder, 'host.json'), worker_ready=sidecar(folder, 'READY.json'),
                  accepted=bool(quality and quality['ok'] and frozen and protected and in_scope),
                  timely=elapsed <= config['budget_seconds'], budget_seconds=config['budget_seconds'],
                  agent_message=message)
    result['accepted_within_budget'] = result['accepted'] and result['timely']
    config['status'] = terminal
    save(path, config)
    save(folder / 'result.json', result)
    return result


def monitor(folder):
    config = json.loads((folder / 'trial.json').read_bytes())
    # Control-plane messages must never invalidate an already accepted artifact.
    marker = folder / 'DONE.json'
    next_check = time.monotonic() + 10
    while time.monotonic() - config['start_monotonic'] < config['budget_seconds']:
        if marker.is_file():
            return finish(folder, 'returned', marker.read_text())
        if time.monotonic() >= next_check:
            observe(folder)
            next_check = time.monotonic() + 10
        time.sleep(.2)
    (folder / 'STOP').write_text('Trial budget exhausted. Stop work.\n')
    return finish(folder, 'timeout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'attach', 'observe', 'monitor', 'finish', 'summary'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--terminal', default='returned')
    parser.add_argument('--message')
    parser.add_argument('--agent')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.path.resolve(), args.pilot)
    elif args.action == 'start':
        result = start(args.path.resolve())
    elif args.action == 'attach':
        result = attach(args.path.resolve(), args.agent)
    elif args.action == 'observe':
        result = observe(args.path.resolve())
    elif args.action == 'finish':
        result = finish(args.path.resolve(), args.terminal, args.message)
    elif args.action == 'monitor':
        result = monitor(args.path.resolve())
    else:
        manifest = json.loads((args.path / 'manifest.json').read_bytes())
        result = [json.loads((Path(name) / 'result.json').read_bytes()) for name in manifest['trials']
                  if (Path(name) / 'result.json').is_file()]
    print(json.dumps(result, ensure_ascii=True))
