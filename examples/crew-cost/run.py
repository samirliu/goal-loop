#!/usr/bin/env python3
"""Paired local process calibration, fresh-input check, and bounded recovery.

This fixture observes actual subprocess work and checks. Startup delay is an
explicit fault injection, not a claim about a model provider or Agent API.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


crew = module('cost_crew', ROOT / 'scripts/goal_crew.py')
task = module('factor_task', Path(__file__).with_name('task.py'))


def ctl(project, *args):
    result = subprocess.run(['bash', str(ROOT / 'scripts/goal_ctl.sh'), *args, '--project', str(project)],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def setup(project):
    ctl(project, 'init')
    shutil.copy2(Path(__file__).with_name('task.py'), project / 'task.py')
    (project / '.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n' + '\n'.join(
        '- AC-%s | valid factor certificates | check: `python3 task.py grade T%s` | expected: exit=0' % (i, i)
        for i in range(1, 4)) + '\n\n## Approval\n\napproved: PENDING\n')
    ctl(project, 'stamp', '--auto', '--time-budget=600')
    (project / '.goal/proposals').mkdir()


def graph(project, startup, only=None):
    value = dict(version=1, context={'backend': 'local-process-demo-v1', 'startup_delay_seconds': startup,
                                     'controller': 'python-fixture-v1',
                                     'input_shape': {'jobs': 3, 'items': 18, 'factor_bits': 20},
                                     'host_capacity': 3}, capacity=3,
                 jobs=[dict(id='T%s' % i, files=['output-T%s.json' % i], deps=[],
                            check=[sys.executable, 'task.py', 'grade', 'T%s' % i])
                       for i in (only if only is not None else range(1, 4))],
                 final_check=[sys.executable, 'task.py', 'grade-all'], instruments=['../../task.py'],
                 inputs=['input-T%s.json' % i for i in range(1, 4)])
    path = project / '.goal/proposals/crew.json'
    path.write_text(json.dumps(value, sort_keys=True))
    return path, value


def inputs(project, seed, clear=True):
    previous = Path.cwd()
    os.chdir(project)
    try:
        task.make_inputs(seed)
        if clear:
            for i in range(1, 4):
                path = project / ('output-T%s.json' % i)
                if path.exists():
                    path.unlink()
    finally:
        os.chdir(previous)


def trial(project, graph_path, definition, mode, label, delay, fail=None, recovery=False, policy_state=None):
    wave = crew.Wave(project, crew.begin(project, graph_path, mode, label, policy_state=policy_state))
    if recovery:
        wave.stage('recovery', 'begin')
    children, logs, ready_lines = {}, {}, {}
    cap = crew.load(wave.path)['deadline']

    def dispatch(job):
        name = job['id']
        wave.event(name, 'dispatch')
        seconds = 120 if cap is None else max(0, cap-time.monotonic()-3)
        args = [sys.executable, '-I', str(ROOT / 'scripts/goal_bounded.py'), '--owner', str(os.getpid()),
                '--seconds', str(seconds), '--kind', 'executor', '--label', name, '--',
                sys.executable, 'task.py', 'work', name, str(delay if mode == 'crew' else 0)]
        if name == fail:
            args.append('fail')
        children[name] = subprocess.Popen(args, cwd=project, env=dict(os.environ, GOAL_TRACE_PROJECT=str(project)),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def ready(job):
        name = job['id']; child = children[name]
        ready_lines[name] = child.stdout.readline()
        if ready_lines[name].strip() == 'READY':
            wave.event(name, 'started')

    def join(jobs):
        pending = {j['id'] for j in jobs}
        wave.stage('join', 'begin')
        while pending:
            for name in list(pending):
                child = children[name]
                if child.poll() is not None:
                    out, err = child.communicate(timeout=2)
                    logs[name] = dict(stdout=ready_lines[name]+out, stderr=err, result=child.returncode)
                    wave.event(name, 'returned', child.returncode)
                    pending.remove(name)
            if pending:
                time.sleep(0.002)
        wave.stage('join', 'end')

    def validate(jobs):
        for job in jobs:
            if wave.validate(job['id']) == 0:
                wave.event(job['id'], 'adopt')

    try:
        if mode == 'crew':
            wave.stage('coordination', 'begin')
            for job in definition['jobs']:
                dispatch(job)
            for job in definition['jobs']:
                ready(job)
            wave.stage('coordination', 'end')
            join(definition['jobs'])
            validate(definition['jobs'])
        else:
            for job in definition['jobs']:
                wave.stage('coordination', 'begin')
                dispatch(job); ready(job)
                wave.stage('coordination', 'end')
                join([job]); validate([job])
        wave.stage('conflict', 'skip')
        if recovery:
            wave.stage('recovery', 'end')
        result = wave.finish()
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
            child.communicate(timeout=4)
    print('%s mode=%s quality=%s elapsed=%.3f worker-seconds=%.3f' %
          (label, mode, result['quality'], result['elapsed'], result['worker_seconds']), flush=True)
    return dict(observation=result, raw=logs)


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    observed_start = time.monotonic()
    # Seal every trial as it completes, including failed development versions.
    # Fresh-input identities cannot be silently reused after a repair.
    trial_dir = output / 'trials'
    trial_dir.mkdir(exist_ok=True)
    used = set()
    for path in [*output.glob('*results.json'), *trial_dir.glob('*.json')]:
        for seed in re.findall(r'fresh-([0-9]+)', path.read_text()):
            used.add(int(seed))
    fresh_seed = 1009
    while fresh_seed in used:
        fresh_seed += 1
    run_id = uuid.uuid4().hex
    (output / ('run-' + run_id + '.json')).write_text(json.dumps(dict(
        fresh_seed=fresh_seed, calibration_seeds=[41, 73, 109], startup_delays=[0.01, 8],
        sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                 [ROOT/'scripts/goal_crew.py', Path(__file__), Path(__file__).with_name('task.py')]},
        logical_cpus=os.cpu_count(), tokens=None, money=None), indent=2)+'\n')
    def run_trial(*args, **kwargs):
        result = trial(*args, **kwargs)
        (trial_dir / (result['observation']['id'] + '.json')).write_text(json.dumps(result, indent=2)+'\n')
        return result
    reports, choices = [], []
    with tempfile.TemporaryDirectory(prefix='goal-crew-cost-') as tmp:
        project = Path(tmp)
        setup(project)
        for profile, delay in [('low', 0.01), ('high', 8.0)]:
            path, definition = graph(project, delay)
            # Alternate AB/BA; all input identities and failures are retained.
            for i, seed in enumerate((41, 73, 109)):
                for mode in (('inline', 'crew') if i % 2 == 0 else ('crew', 'inline')):
                    inputs(project, seed)
                    reports.append(run_trial(project, path, definition, mode, '%s-cal-%s' % (profile, seed), delay))
            inputs(project, fresh_seed)
            decision = crew.plan(project, path)
            heldout = {}
            for mode in ('crew', 'inline'):
                inputs(project, fresh_seed)
                result = run_trial(project, path, definition, mode, '%s-fresh-%s' % (profile, fresh_seed), delay)
                reports.append(result)
                heldout[mode] = result['observation']['elapsed']
            choices.append(dict(profile=profile, decision_before_fresh_input=decision, fresh_delivery_seconds=heldout))
        # A separate failure preserves useful siblings, then only T2 is rerun.
        inputs(project, 307)
        path, definition = graph(project, 0.01)
        failed = run_trial(project, path, definition, 'crew', 'fault-307', 0.01, fail='T2')
        reports.append(failed)
        before = {name: hashlib.sha256((project / name).read_bytes()).hexdigest()
                  for name in ('output-T1.json', 'output-T3.json')}
        fault_book = ctl(project, 'close-iteration', '--task', 'T1[crew:3]', '--files', 'output-T1.json,output-T3.json',
                         '--checks-pass', '2', '--checks-fail', '1', '--checks-unverifiable', '0', '--progress', 'yes',
                         '--exit-signal', 'no', '--fault', 'death', '--fault-outcome', 're-run',
                         '--fault-note', 'T2 self SIGKILL after backend READY; useful siblings retained', '--no-gate')
        path, definition = graph(project, 0.01, only=[2])
        repaired = run_trial(project, path, definition, 'inline', 'recovery-307', 0, recovery=True)
        reports.append(repaired)
        assert repaired['observation']['quality'] and not failed['observation']['quality']
        assert all(hashlib.sha256((project / name).read_bytes()).hexdigest() == digest for name, digest in before.items())
        final_book = ctl(project, 'close-iteration', '--task', 'T2[crew:1]', '--files', 'output-T2.json',
                         '--checks-pass', '3', '--checks-fail', '0', '--checks-unverifiable', '0', '--progress', 'yes',
                         '--exit-signal', 'yes', '--adversarial', 'clear', '--adversarial-note',
                         'factor certificates independently checked; adopted sibling bytes preserved', '--no-gate')
        gate = subprocess.run(['bash', str(ROOT / 'scripts/goal_gate.sh'), '--check', '--project', str(project)],
                              capture_output=True, text=True, timeout=15)
        assert gate.returncode == 0, gate.stdout+gate.stderr
        (output / 'fault-loop-log.md').write_bytes((project / '.goal/loop-log.md').read_bytes())
        (output / 'faults.rec').write_bytes((project / '.goal/evidence/faults.rec').read_bytes())
        result = dict(version=1, backend='controlled local subprocesses, not native Agent API', fresh_seed=fresh_seed,
                      observation_scope='example-main-entry', total_observed_seconds=time.monotonic()-observed_start,
                      trials=reports, choices=choices, preserved_sibling_sha256=before,
                      fault_book=fault_book, recovery_book=final_book, final_gate=gate.stdout+gate.stderr,
                      tokens=None, money=None)
        (output / 'results.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    main(args.output.resolve())
