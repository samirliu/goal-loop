#!/usr/bin/env python3
"""Bounded offline entry overhead; no models, synthetic utility, or promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]


def run(source, project, mapped):
    project.mkdir()
    rows = []
    def call(stage, argv, expected=0, payload=None):
        began = time.monotonic()
        value = subprocess.run(argv, cwd=project, input=payload, capture_output=True, text=True, timeout=30)
        rows.append(dict(stage=stage, argv=argv, seconds=time.monotonic()-began, result=value.returncode,
                         stdout=value.stdout, stderr=value.stderr, stdout_bytes=len(value.stdout.encode())))
        (project.parent/(project.name+'.calls.json')).write_text(json.dumps(rows, indent=2)+'\n')
        if value.returncode != expected:
            raise RuntimeError(rows[-1])
        return value.stdout
    scripts = source/'scripts'
    ctl = ['bash', str(scripts/'goal_ctl.sh')]
    context = lambda: json.loads(call('context', ctl+['context', '--project', str(project), '--auto']))
    def consume(stage, view, action, fallback=None):
        command = view['actions'].get(action, {}).get('command')
        return call(stage, shlex.split(command) if command else fallback)
    began = time.monotonic()
    call('entry', [sys.executable, '-I', str(scripts/'goal_host.py'), 'begin', str(project),
                   'offline-measurement', 'explicit-offline-fixture', '90'])
    for _ in range(3):
        call('hook', [sys.executable, '-I', str(scripts/'goal_host.py'), 'hook', '--backend', 'codex'],
             payload=json.dumps(dict(hook_event_name='PreToolUse', cwd=str(project),
                                     session_id='explicit-offline-fixture', tool_name='Read', tool_input={'file_path':'answer'})))
    view = context()
    (project/'check.py').write_text('from pathlib import Path\nraise SystemExit(0 if Path("answer").read_bytes()==b"42\\n" else 1)\n')
    (project/'answer').write_bytes(b'42\n')
    template = view['author_contract']['template'].replace('<outcome>', 'verified answer').replace(
        '<yes/no statement>', 'answer is forty-two').replace('<command>', 'python3 check.py')
    (project/'.goal/goal.md').write_text(template)
    (project/'.goal/work-plan.md').write_text('- [ ] T1 answer | owner=controller | files=answer\n')
    view = context()
    consume('smoke', view, 'verify', ['bash', str(scripts/'goal_gate.sh'), '--verify', '--project', str(project)])
    consume('stamp', context(), 'stamp')
    # A real cold check rejects the wrong bytes, then independently accepts the
    # restored delivery. This is controller overhead, not agent task utility.
    (project/'answer').write_bytes(b'43\n')
    call('independent-negative', [sys.executable, '-I', str(project/'check.py')], expected=1)
    (project/'answer').write_bytes(b'42\n')
    call('independent-positive', [sys.executable, '-I', str(project/'check.py')])
    (project/'.goal/work-plan.md').write_text('- [x] T1 answer | owner=controller | files=answer\n')
    view = context()
    raw = consume('verify', view, 'verify', ['bash', str(scripts/'goal_gate.sh'), '--verify', '--project', str(project)])
    if 'AC-1|PASS|exit=0' not in raw:
        raise RuntimeError('missing actual check result')
    note = 'Exact-byte cold check rejected 43 and accepted 42; original named verifier also passed.'
    if mapped:
        request = view['close_input']['template']
        request.update(checks_pass=1, checks_fail=0, checks_unverifiable=0, progress='yes',
                       exit_signal='yes', adversarial='clear', adversarial_note=note)
        path = Path(view['close_input']['path']); path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(request))
        consume('close', context(), 'close')
    else:
        call('close', ctl+['close-iteration', '--project', str(project), '--operation-id', 'measurement-close',
             '--task', 'T1', '--files', 'answer', '--checks-pass', '1', '--checks-fail', '0',
             '--checks-unverifiable', '0', '--progress', 'yes', '--exit-signal', 'yes',
             '--adversarial', 'clear', '--adversarial-note', note])
    view = context()
    receipt = json.loads(consume('receipt', view, 'receipt', [sys.executable, '-I', str(scripts/'goal_context.py'), 'receipt', str(project)]))
    if not receipt['completion_verified']:
        raise RuntimeError(receipt)
    return dict(kind='offline-controller-overhead; no model or agent utility', elapsed=time.monotonic()-began,
                calls=rows, completion_verified=True, protocol_lookup_seconds=None, model_protocol_lookups=None,
                tokens=None, money=None, source={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(scripts.glob('*')) if p.is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {}
    for name, source, mapped in [('before', args.baseline.resolve(), False), ('after', ROOT, True)]:
        result[name] = run(source, args.output/name, mapped)
        (args.output/(name+'.json')).write_text(json.dumps(result[name], indent=2)+'\n')
    summary = {}
    for name, value in result.items():
        summary[name] = dict(elapsed=value['elapsed'], calls=len(value['calls']),
            seconds={stage:sum(r['seconds'] for r in value['calls'] if r['stage']==stage)
                     for stage in sorted({r['stage'] for r in value['calls']})},
            context_bytes=sum(r['stdout_bytes'] for r in value['calls'] if r['stage']=='context'),
            context_calls=sum(r['stage']=='context' for r in value['calls']))
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
