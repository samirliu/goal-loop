#!/usr/bin/env python3
"""Compile current ledger facts into a small action map; no new state authority."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
import importlib.util
SPEC = importlib.util.spec_from_file_location('context_crew', Path(__file__).with_name('goal_crew.py'))
crew = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crew)
store, budget = crew.store, crew.budget
HERE = Path(__file__).resolve().parent


@contextlib.contextmanager
def access(project, write=False):
    root = Path(project).resolve(strict=True)
    state = root / '.goal'
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    inherited = os.environ.get('GOAL_ACCESS_FD')
    try:
        if inherited is not None:
            other = int(inherited)
            a, b = os.fstat(fd), os.fstat(other)
            crew.require((a.st_dev, a.st_ino) == (b.st_dev, b.st_ino), 'inherited lock target mismatch')
            owner = int(os.environ['GOAL_ACCESS_OWNER_PID'])
            os.kill(owner, 0)
            crew.require(not write or (os.environ.get('GOAL_ACCESS_MODE') == 'write' and owner == os.getpid()), 'nested-writer')
            os.close(fd)
            fd = os.dup(other)
        else:
            store.fcntl.flock(fd, (store.fcntl.LOCK_EX if write else store.fcntl.LOCK_SH) | store.fcntl.LOCK_NB)
        crew.require(not (state / 'store/pending').exists(), 'recovery-required: run goal_ctl.sh recover --project ' + shlex.quote(str(root)))
        store.verify_views(state)
        yield root, state, fd
    finally:
        os.close(fd)


def protected(root, command, cap, fd, mode='read'):
    """Reuse the existing process supervisor and the one shared deadline."""
    remaining = 30 if cap is None else max(0, cap-time.monotonic())
    crew.require(remaining > 0, 'time-budget-exhausted')
    descriptor, name = tempfile.mkstemp(prefix='goal-context-', dir=tempfile.gettempdir())
    os.close(descriptor)
    receipt = Path(name)
    env = dict(os.environ, GOAL_ACCESS_FD=str(fd), GOAL_ACCESS_OWNER_PID=str(os.getpid()), GOAL_ACCESS_MODE=mode)
    env.pop('GOAL_ACCESS_EXEC_PID', None)
    if cap is not None:
        env['GOAL_RUNNER_MONOTONIC_END'] = str(cap)
    try:
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-I', str(HERE / 'goal_bounded.py'), '--owner', str(os.getpid()),
                                 '--seconds', str(remaining), '--receipt', name, '--kind', 'verification',
                                 '--label', 'context', '--', *command], cwd=root, env=env, pass_fds=(fd,),
                                capture_output=True, text=True, timeout=remaining+3)
        crew.require(result.returncode == 0 and receipt.read_text().strip().isdigit(), 'context command supervision failed')
        return dict(command=command, result=int(receipt.read_text()), stdout=result.stdout,
                    stderr=result.stderr, elapsed=time.monotonic()-started)
    finally:
        receipt.unlink(missing_ok=True)


def compile_view(root, state, fd, auto=False):
    head = store.verify_views(state)
    contract_path = state/'goal.md'
    contract = contract_path.read_text() if contract_path.exists() else ''
    authored = bool(contract.strip())
    counters = dict(line.split('=', 1) for line in (state / 'state.rec').read_text().splitlines() if '=' in line)
    cap, expired = budget.gate_limit(state, settlement=False)
    expired |= cap is not None and cap <= time.monotonic()
    runner_file = state/'runner.json'
    runner = budget.runner_data(runner_file.read_bytes()) if runner_file.exists() else None
    artifact = None
    if not expired:
        digest = protected(root, ['bash', str(HERE / 'goal_gate.sh'), '--digest', '--project', str(root)], cap, fd)
        crew.require(digest['result'] == 0 and re.fullmatch(r'v2-[0-9a-f]{64}', digest['stdout'].strip()), 'artifact digest unavailable')
        artifact = digest['stdout'].strip()
    plan = (state / 'work-plan.md').read_text() if (state / 'work-plan.md').exists() else ''
    log = (state / 'loop-log.md').read_text()
    stamped = re.search(r'^approved: [0-9a-f]{6,}', contract, re.M) is not None
    waves = [crew.load(p) for p in sorted((state/'evidence/crew').glob('*.json'))]
    units, policies = {}, {}
    for wave in sorted(waves, key=lambda w: w['started']):
        policy_matches = True
        if wave.get('policy'):
            path = Path(wave['policy']['state'])
            engine = crew.evolution()
            lock = engine.policy_lock(path, False)
            try:
                engine.require_settled(path)
                policies[str(path)] = engine.enabled_policy(path)
                policy_matches = policies[str(path)] == wave['policy']['selection']
            finally:
                os.close(lock)
        for task, row in wave['jobs'].items():
            if not row.get('unit_key'):
                continue
            current = policy_matches and row.get('proof') is not None and row['proof'] == crew.unit_binding(root, wave['graph'], task, wave.get('policy'), ledger=state)
            units[row['unit_key']] = dict(task=task, wave=wave['id'], accepted=current,
                                         scope=list(row.get('adopted_digest') or {}),
                                         repair=row.get('repair'), fault=row.get('fault'))
    interface = state/'interfaces.md'
    crew.require(not interface.is_symlink(), 'symlink interface refused')
    binding = dict(head=head, contract=store._hash(contract.encode()) if contract_path.exists() else None, artifact=artifact,
                   work_plan=store._hash(plan.encode()), units=store._hash(store._encode(units)), policies=policies,
                   interfaces=store._hash(interface.read_bytes()) if interface.exists() else None, auto=auto,
                   budget=dict(contract=counters.get('deadline'), runner=store._hash(runner_file.read_bytes()) if runner else None,
                               inherited=os.environ.get('GOAL_RUNNER_MONOTONIC_END')))
    revision = store._hash(store._encode(binding))
    base = [sys.executable, '-I', str(HERE / 'goal_context.py'), 'run', str(root), revision]
    commands = {'status': ['bash', str(HERE / 'goal_ctl.sh'), 'status', '--project', str(root)],
                'audit': ['bash', str(HERE / 'goal_audit.sh'), '--project', str(root)],
                'gate': ['bash', str(HERE / 'goal_gate.sh'), '--check', '--project', str(root)]}
    if not stamped and authored and not expired:
        commands['stamp'] = ['bash', str(HERE / 'goal_ctl.sh'), 'stamp', '--project', str(root)] + (['--auto'] if auto else [])
    if expired or not authored:
        commands = {'status': commands['status']}
    objective = re.search(r'^## (?:Goal|Objective)[^\n]*\n+([^#<][^\n]*)', contract, re.M)
    blocks = re.split(r'^## iteration\b', log, flags=re.M)
    claimed = len(blocks) > 1 and re.search(r'^exit_signal=yes\s*$', blocks[-1], re.M) is not None
    ticked = any(s.startswith('- [x]') for s in plan.splitlines())
    next_step = ('settle-or-stop' if expired else 'author-contract-and-smoke' if not stamped else
                 'close-unbooked-wave' if len(blocks) == 1 and ticked else
                 'verify-gate-and-deliver' if claimed else
                 'review-and-close-iteration' if len(blocks) > 1 else 'implement-or-dispatch')
    value = dict(version=1, project=str(root), revision=revision, binding=binding,
                 goal=objective[1].strip() if objective else (contract.splitlines() or ['Goal contract not authored'])[0], stamped=stamped,
                 iteration=counters.get('iteration'), breaker=counters.get('breaker'),
                 deadline_epoch=None if cap is None else time.time()+cap-time.monotonic(), deadline_monotonic=cap,
                 budget_scope=runner['scope'] if runner else 'contract-only',
                 remaining_seconds=None if cap is None else max(0, cap-time.monotonic()),
                 expired=expired, accepted=[s for s in plan.splitlines() if s.startswith('- [x]')],
                 pending=[s for s in plan.splitlines() if s.startswith('- [ ]')],
                 accepted_units=[u for u in units.values() if u['accepted']],
                 repair_units=[u for u in units.values() if not u['accepted']], policies=policies,
                 unknown=['work-plan ticks are not acceptance; only a fresh gate decides GO'],
                 next=next_step,
                 actions={name: dict(command=shlex.join(base+[name]+(['--auto'] if auto else [])), executes=shlex.join(cmd)) for name, cmd in commands.items()},
                 settle_command=shlex.join([sys.executable, '-I', str(HERE/'goal_context.py'), 'receipt', str(root)]),
                 evidence=dict(contract=str(state/'goal.md'), ledger=str(state/'store/commits'),
                               log=str(state/'loop-log.md'), host=str(state/'evidence/host')))
    if not authored and not expired:
        value['author_contract'] = dict(path=str(contract_path), already_initialized=True,
            next='Write this small contract, run its named check as a smoke test, then regenerate context; do not re-init or inspect implementation files for syntax.',
            template='# Goal\n\n## Objective\n\n<outcome>\n\n## Acceptance criteria\n\n'
                     '- AC-1 | <yes/no statement> | check: `<command>` | expected: exit=0\n\n'
                     '## Approval\n\napproved: PENDING\n')
    return value, commands


def show(project, auto=False):
    with access(project) as (root, state, fd):
        value, _ = compile_view(root, state, fd, auto)
        return value


def run(project, revision, action, auto=False):
    # The lock is retained across exec, so a cooperating ledger writer cannot
    # change the validated revision before the existing command consumes it.
    with access(project, write=action in ('stamp', 'gate')) as (root, state, fd):
        value, commands = compile_view(root, state, fd, auto)
        crew.require(value['revision'] == revision, 'stale-context: regenerate goal_ctl.sh context')
        crew.require(action in commands and (not value['expired'] or action in ('status',)),
                     'action unavailable; settle with goal_context.py receipt')
        os.set_inheritable(fd, True)
        env = dict(os.environ, GOAL_ACCESS_FD=str(fd), GOAL_ACCESS_OWNER_PID=str(os.getpid()),
                   GOAL_ACCESS_EXEC_PID=str(os.getpid()), GOAL_ACCESS_MODE='write' if action == 'stamp' else
                   'exclusive-read' if action == 'gate' else 'read')
        os.execvpe(commands[action][0], commands[action], env)


def receipt(project):
    with access(project, write=True) as (root, state, fd):
        before = store.verify_views(state)
        cap, _ = budget.gate_limit(state, settlement=True)
        checks = {name: protected(root, ['bash', str(HERE/script), *args, '--project', str(root)], cap, fd, 'exclusive-read')
                  for name, script, args in [('audit', 'goal_audit.sh', []), ('gate', 'goal_gate.sh', ['--check'])]}
        crew.require(before == store.verify_views(state), 'ledger changed during receipt')
        rows = [crew.load(p) for p in sorted((state/'evidence/crew').glob('*.json'))]
        result = dict(version=1, project=str(root), head=before,
                      completion_verified=all(r['result'] == 0 for r in checks.values()), checks=checks,
                      policies=[dict(wave=w['id'], **w['policy']) for w in rows if w.get('policy')],
                      reused_units=[dict(wave=w['id'], task=t, source=r['reused_from'])
                                    for w in rows for t, r in w['jobs'].items() if r.get('reused_from')],
                      unresolved=[name for name, r in checks.items() if r['result'] != 0], tokens=None, money=None)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('show', 'run', 'receipt'))
    parser.add_argument('project')
    parser.add_argument('revision', nargs='?')
    parser.add_argument('operation', nargs='?')
    parser.add_argument('--auto', action='store_true', help='only with existing authorization for automatic contract approval')
    args = parser.parse_args()
    if args.action == 'run':
        run(args.project, args.revision, args.operation, args.auto)
    result = show(args.project, args.auto) if args.action == 'show' else receipt(args.project)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if args.action == 'show' or result['completion_verified'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, store.StoreError, subprocess.SubprocessError) as exc:
        print('CONTEXT: ERROR ' + str(exc), file=sys.stderr)
        sys.exit(4)
