#!/usr/bin/env python3
"""Execute a frozen finite probe scope and qualify forge dry evidence."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('forge_budget', Path(__file__).with_name('goal_runner.py'))
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)
store = budget.store
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_file(project, name):
    require(store._valid_name(name) and not {'.goal', '.git'}.intersection(name.split('/')),
            'invalid probe input/instrument path')
    path = store._close_path(project, name)
    require(path.is_file(), 'missing probe input/instrument: ' + name)
    return path.read_bytes()


def plan(project):
    data = store._close_path(project / '.goal', 'forge-plan.json').read_bytes()
    value = json.loads(data)
    require(isinstance(value, dict) and set(value) == {'version', 'instruments', 'cases', 'blind_spots'}
            and type(value['version']) is int and value['version'] == 1, 'invalid forge plan')
    require(isinstance(value['blind_spots'], list)
            and all(isinstance(x, str) and x.strip() for x in value['blind_spots']), 'invalid blind spots')
    require(isinstance(value['instruments'], list) and value['instruments']
            and all(isinstance(x, str) for x in value['instruments'])
            and len(set(value['instruments'])) == len(value['instruments']), 'invalid probe instruments')
    files = {name: read_file(project, name) for name in value['instruments']}
    require(isinstance(value['cases'], list) and value['cases'], 'empty probe scope')
    ids = set()
    for case in value['cases']:
        require(isinstance(case, dict) and set(case) == {'id', 'dimension', 'input', 'command'}, 'invalid probe case')
        require(isinstance(case['id'], str) and ID.fullmatch(case['id']) and case['id'] not in ids, 'invalid case id')
        require(isinstance(case['dimension'], str) and ID.fullmatch(case['dimension']), 'invalid probe dimension')
        command = case['command']
        require(isinstance(command, list) and command and all(isinstance(s, str) and '\0' not in s for s in command),
                'invalid probe command')
        files[case['input']] = read_file(project, case['input'])
        ids.add(case['id'])
    identity = store._hash(store._encode({'plan': store._hash(data), 'files': {k: store._hash(v) for k, v in files.items()}}))
    return value, files, identity


def expected_plan(project):
    rows = re.findall(r'(?:^|;)forge=([a-f0-9]{64});?', (project / '.goal/check_freeze').read_text().strip())
    require(len(rows) == 1, 'forge plan has no approved freeze; start a reviewed run with a declared scope')
    return rows[0]


def archive_scope(project, expected):
    definition, files, fingerprint = plan(project)
    require(expected == 'forge=' + fingerprint + ';', 'probe scope changed during approval')
    raw = (project / '.goal/forge-plan.json').read_bytes()
    require(store._hash(store._encode({'plan': store._hash(raw),
                                      'files': {name: store._hash(data) for name, data in files.items()}})) == fingerprint,
            'probe plan changed during capture')
    return dict(version=1, fingerprint=fingerprint, definition=definition,
                plan_base64=base64.b64encode(raw).decode('ascii'),
                files={name: base64.b64encode(data).decode('ascii') for name, data in files.items()})


def adopt(project):
    state = project / '.goal'
    descriptor = int(os.environ.get('GOAL_ACCESS_FD', '-1'))
    require(descriptor >= 3 and os.environ.get('GOAL_ACCESS_MODE') == 'write',
            'use goal_ctl.sh migrate to hold ledger ownership')
    borrowed, directory = os.fstat(descriptor), state.stat()
    require((borrowed.st_dev, borrowed.st_ino) == (directory.st_dev, directory.st_ino),
            'migration lock belongs to another ledger')
    store.verify_views(state)
    freeze = (state / 'check_freeze').read_text().strip()
    definition, files, fingerprint = plan(project)
    sealed = bool(re.search(r'(^|;)forge=', freeze))
    if sealed:
        if fingerprint == expected_plan(project):
            return
        raw = (state / 'evidence/raw/0.txt').read_text()
        require(raw.startswith('FORGE-SCOPE: '), 'missing archived probe scope')
        previous = json.loads(raw[13:])
        require(previous['fingerprint'] == expected_plan(project), 'unbound archived scope')
        old = previous['definition']
        current = {case['id']: case for case in definition['cases']}
        require(len(current) > len(old['cases']) and all(current.get(case['id']) == case for case in old['cases'])
                and definition['blind_spots'] == old['blind_spots']
                and set(old['instruments']).issubset(definition['instruments'])
                and all(files.get(name) == base64.b64decode(data, validate=True) for name, data in previous['files'].items()),
                'migration permits additional probes while preserving approved cases and materials')
    body = subprocess.check_output(['bash', '-c', '. "$1"; gp_ac_body_hash "$2"', 'forge-migration',
                                    str(Path(__file__).with_name('goal_parse.sh')), str(project)]).decode().strip()
    approval = store.current_approval(state)
    require(approval is not None and approval[:8] == body, 'migration cannot amend the approved contract')
    marker = 'forge=' + fingerprint + ';'
    captured = archive_scope(project, marker)
    text = (state / 'state.rec').read_text()
    require(len(re.findall(r'^dry_streak=', text, re.M)) == 1, 'invalid legacy dry counter')
    text = re.sub(r'^dry_streak=.*$', 'dry_streak=0', text, flags=re.M)
    store.mutation_journal(state, 'begin', 'forge', args=('adopt-forge', fingerprint))
    upgraded = re.sub(r'(^|;)forge=[a-f0-9]{64};?', lambda match: match[1] + marker, freeze) if sealed else (
        (freeze.rstrip(';') + ';' if freeze else '') + marker)
    store._atomic(state / 'check_freeze', (upgraded + '\n').encode())
    store._atomic(state / 'state.rec', text.encode())
    raw = store._close_path(state, 'evidence/raw/0.txt')
    raw.parent.mkdir(parents=True, exist_ok=True)
    store._atomic(raw, b'FORGE-SCOPE: ' + store._encode(captured) + b'\n')
    store.mutation_journal(state, 'finish')
    print('FORGE: adopted scope; executed dry evidence must be gathered again')


def reports(project, iteration):
    path = store._close_path(project / '.goal', 'evidence/raw/%s.txt' % iteration)
    return [json.loads(line[7:]) for line in path.read_text().splitlines() if line.startswith('FORGE: ')]


def read_critic(project, iteration, artifact, fingerprint):
    path = store._close_path(project / '.goal', 'evidence/critic-iter-%s.md' % iteration)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError('critic-evidence-missing') from exc
    return critic_record(raw, iteration, artifact, fingerprint)


def critic_record(raw, iteration, artifact, fingerprint):
    rows = [line.split('|', 1) for line in raw.decode('utf-8').splitlines() if line.strip()]
    require(all(len(row) == 2 and row[0] in ('ITERATION', 'ARTIFACT', 'PLAN', 'FINDING', 'CLEAR') for row in rows), 'unknown critic record')
    headers = {name: [row[1] for row in rows if row[0] == name] for name in ('ITERATION', 'ARTIFACT', 'PLAN', 'CLEAR')}
    require(headers['ITERATION'] == [str(iteration)] and headers['ARTIFACT'] == [artifact]
            and headers['PLAN'] == [fingerprint], 'critic evidence is stale or unbound')
    require(len(headers['CLEAR']) == 1 and headers['CLEAR'][0].strip(), 'missing critic conclusion')
    findings = [row[1].split('|', 2) for row in rows if row[0] == 'FINDING']
    require(all(len(row) == 3 and all(value.strip() for value in row) for row in findings), 'malformed critic finding')
    return dict(sha256=store._hash(raw), text=raw.decode('utf-8'), findings=findings)


def case_identity(fingerprint, case, artifact, input_sha):
    return store._hash(store._encode(dict(plan=fingerprint, command=case['command'], input=input_sha, artifact=artifact)))


def probe_identity(case, input_sha):
    return store._hash(store._encode(dict(command=case['command'], input=input_sha)))


def prior_cases(project, iteration):
    observed = set()
    for number in range(1, iteration):
        for report in reports(project, number):
            observed.update(row.get('probe_identity', row['identity']) for row in report.get('cases', [])
                            if row.get('result') == 0)
    return observed


def execute(project, case, data, seconds, artifact, deadline):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='goal-forge-probe-') as tmp:
        root = Path(tmp)
        receipt = root / 'receipt'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('GOAL_ACCESS_', 'GOAL_CLOSE_', 'GOAL_WRITER_'))}
        env.pop('GOAL_RUNNER_FD', None)
        env['GOAL_TRACE_PROJECT'] = str(project)
        if deadline is not None:
            env['GOAL_RUNNER_MONOTONIC_END'] = str(deadline)

        def bound_files():
            _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
            resource.setrlimit(resource.RLIMIT_FSIZE, (min(1024 * 1024, hard) if hard != resource.RLIM_INFINITY else 1024 * 1024, hard))

        with (root / 'input').open('w+b') as source, (root / 'output').open('w+b') as output, (root / 'error').open('w+b') as error:
            source.write(data)
            source.seek(0)
            result = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('goal_bounded.py')),
                                     '--owner', str(os.getpid()), '--seconds', str(seconds),
                                     '--kind', 'verification', '--label', 'forge:' + case['id'],
                                     '--artifact', artifact, '--receipt', str(receipt), '--', *case['command']],
                                    cwd=project, env=env, stdin=source, stdout=output, stderr=error,
                                    start_new_session=True, preexec_fn=bound_files)
            output.seek(0)
            stdout = output.read(1024 * 1024)
            error.seek(0)
            stderr = error.read(1024 * 1024)
        rc = int(receipt.read_text()) if result.returncode == 0 and receipt.is_file() else None
    return dict(result=rc, elapsed=time.monotonic() - started, stdout=stdout.decode('utf-8', 'replace'),
                stdout_base64=base64.b64encode(stdout).decode('ascii'),
                stderr_base64=base64.b64encode(stderr).decode('ascii'))


def run(project, iteration, artifact, floor_result):
    started = time.monotonic()
    state = project / '.goal'
    ledger = None
    ledger_names = set()
    report = dict(version=1, iteration=iteration, artifact=artifact, plan=None, qualified=False,
                  reason=None, cases=[], remaining=[], blind_spots=[], new_cases=0, repeated_cases=0,
                  started=time.time(), elapsed=None, fatal=False, critic=None)
    try:
        definition, files, fingerprint = plan(project)
        report.update(plan=fingerprint, blind_spots=definition['blind_spots'],
                      remaining=[case['id'] for case in definition['cases']])
        require(fingerprint == expected_plan(project), 'frozen probe scope changed')
        report['critic'] = read_critic(project, iteration, artifact, fingerprint)
        require(not report['critic']['findings'], 'critic-has-findings')
        require(floor_result == 0 and '|DEFERRED|' not in
                (project / '.goal' / ('evidence/raw/%s.txt' % iteration)).read_text(), 'floor-verification-incomplete')
        observed = prior_cases(project, iteration)
        ledger_names = store._view_names(state) | {'goal.md', 'forge-plan.json', 'baseline.md', 'work-plan.md',
                                                   'interfaces.md', 'store/commits/current', 'store/pending'}
        ledger = store._capture_files(state, ledger_names)
        cap, expired = budget.gate_limit(project / '.goal', settlement=False)
        timeout = budget.natural(next(line.split('=')[1] for line in (project / '.goal/state.rec').read_text().splitlines()
                                      if line.startswith('check_timeout=')), 'check-timeout')
        for case in definition['cases']:
            left = timeout if cap is None else min(timeout, cap - time.monotonic())
            if expired or left <= 0:
                report['reason'] = 'time-budget-exhausted'
                break
            result = execute(project, case, files[case['input']], left, artifact, cap)
            result.update(id=case['id'], dimension=case['dimension'], input_sha256=store._hash(files[case['input']]),
                          identity=case_identity(fingerprint, case, artifact, store._hash(files[case['input']])),
                          probe_identity=probe_identity(case, store._hash(files[case['input']])))
            report['cases'].append(result)
            report['remaining'].remove(case['id'])
            if result['result'] == 0:
                key = 'repeated_cases' if result['probe_identity'] in observed else 'new_cases'
                report[key] += 1
                observed.add(result['probe_identity'])
            elif result['result'] == 124:
                report['reason'] = 'probe-timeout'
                break
        require(plan(project)[2] == fingerprint, 'probe changed its frozen scope')
        require(read_critic(project, iteration, artifact, fingerprint) == report['critic'], 'critic changed during probing')
        digest = subprocess.check_output(['bash', str(Path(__file__).with_name('goal_gate.sh')), '--digest',
                                          '--project', str(project)]).decode('ascii').strip()
        require(digest == artifact, 'probe changed the artifact')
        if cap is not None and time.monotonic() >= cap:
            report['reason'] = 'time-budget-exhausted'
        report['qualified'] = (not report['remaining'] and report['reason'] is None
                               and all(row['result'] == 0 for row in report['cases']))
        if not report['qualified'] and report['reason'] is None:
            report['reason'] = 'probe-finding-or-failure'
    except (OSError, ValueError, KeyError, TypeError, store.StoreError, subprocess.SubprocessError) as exc:
        report['reason'] = str(exc)
    finally:
        if ledger is not None:
            try:
                unchanged = store._capture_files(state, ledger_names | store._view_names(state)) == ledger
            except (OSError, ValueError, store.StoreError):
                unchanged = False
            if not unchanged:
                report.update(qualified=False, fatal=True, reason='probe-changed-ledger')
    report['elapsed'] = time.monotonic() - started
    return report


def audit(project, iteration, limit, artifact):
    definition, files, fingerprint = plan(project)
    require(fingerprint == expected_plan(project), 'frozen probe scope changed')
    require(limit > 0 and iteration >= limit, 'insufficient executed dry rounds')
    expected = [case['id'] for case in definition['cases']]
    for number in range(iteration - limit + 1, iteration + 1):
        rows = reports(project, number)
        require(len(rows) == 1, 'missing or ambiguous executed dry evidence')
        report = rows[0]
        require(report['version'] == 1 and report['iteration'] == number and report['plan'] == fingerprint
                and report['qualified'] is True and report['remaining'] == [] and report['reason'] is None
                and [row['id'] for row in report['cases']] == expected
                and report['blind_spots'] == definition['blind_spots'] and report['fatal'] is False
                and report['critic'] is not None and report['critic']['findings'] == []
                and all(type(row['result']) is int and row['result'] == 0 for row in report['cases']),
                'unqualified dry evidence')
        if number == iteration:
            require(report['artifact'] == artifact, 'stale dry evidence')
        critic = report['critic']
        require(critic == critic_record(critic['text'].encode('utf-8'), number, report['artifact'], fingerprint),
                'unbound archived critic')
        for case, result in zip(definition['cases'], report['cases']):
            require(result['identity'] == case_identity(fingerprint, case, report['artifact'], store._hash(files[case['input']]))
                    and result['dimension'] == case['dimension']
                    and result['probe_identity'] == probe_identity(case, store._hash(files[case['input']]))
                    and result['input_sha256'] == store._hash(files[case['input']]), 'unbound probe case')
    return dict(cases=len(expected), blind_spots=definition['blind_spots'])


def status(project):
    definition, _, fingerprint = plan(project)
    require(fingerprint == expected_plan(project), 'frozen probe scope changed')
    iteration = int(next(line.split('=')[1] for line in (project / '.goal/state.rec').read_text().splitlines()
                         if line.startswith('iteration=')))
    rows = reports(project, iteration) if iteration else []
    if not rows:
        return dict(qualified=False, reason='no-executed-dry-evidence', executed=0,
                    remaining=[case['id'] for case in definition['cases']], blind_spots=definition['blind_spots'])
    require(len(rows) == 1, 'ambiguous dry evidence')
    report = rows[0]
    return {key: report[key] for key in ('iteration', 'artifact', 'qualified', 'reason', 'new_cases',
                                        'repeated_cases', 'remaining', 'blind_spots')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'archive', 'adopt', 'run', 'audit', 'status'))
    parser.add_argument('--project', default='.')
    parser.add_argument('--iteration', type=int)
    parser.add_argument('--artifact')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--floor-result', type=int)
    parser.add_argument('--expected')
    args = parser.parse_args()
    project = Path(args.project).resolve(strict=True)
    if args.action == 'freeze':
        print('forge=' + plan(project)[2] + ';')
        return 0
    if args.action == 'archive':
        print('FORGE-SCOPE: ' + store._encode(archive_scope(project, args.expected)).decode('ascii'))
        return 0
    if args.action == 'adopt':
        adopt(project)
        return 0
    if args.action == 'status':
        print('CTL: FORGE ' + json.dumps(status(project), sort_keys=True))
        return 0
    if args.action == 'run':
        require(args.iteration is not None and args.iteration > 0 and args.artifact, 'run needs iteration and artifact')
        require(args.floor_result is not None, 'run needs the real verification result')
        report = run(project, args.iteration, args.artifact, args.floor_result)
        print('FORGE: ' + store._encode(report).decode('ascii'))
        return 4 if report['fatal'] else 0 if report['qualified'] else 2
    require(args.iteration is not None and args.limit is not None and args.artifact, 'audit needs iteration, limit and artifact')
    print('FORGE: COVERAGE ' + json.dumps(audit(project, args.iteration, args.limit, args.artifact), sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, store.StoreError) as exc:
        print('FORGE: ERROR ' + str(exc), file=sys.stderr)
        sys.exit(2)
