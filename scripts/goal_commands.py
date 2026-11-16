#!/usr/bin/env python3
"""User controls over the existing goal ledger, host receipts and Gate."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
import importlib.util

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location('commands_'+name, HERE/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


host = module('goal_host')
store, budget, require = host.store, host.budget, host.require
COMMANDS = ('status', 'pause', 'resume', 'clear', 'check', 'recover', 'doctor', 'help')
ALIASES = {'continue': 'resume', '继续': 'resume'}
CLEAR_PENDING = store.CLEAR_PENDING


def context_result(action, *args):
    context = module('goal_context')
    try:
        return getattr(context, action)(*args)
    except context.store.StoreError as exc:
        # Each isolated loader owns its StoreError class. Normalize the
        # original state error instead of leaking a traceback/exit=1.
        raise ValueError(str(exc)) from exc


def command(action, project, backend=None, session=None):
    argv = [sys.executable, '-I', str(HERE/'goal_commands.py'), action, '--project', str(project)]
    if backend is not None:
        argv += ['--backend', backend, '--session', session]
    return shlex.join(argv)


def prompt_action(prompt):
    match = re.fullmatch(r'\s*/(?:goal-loop|goal-loop-host:goal-loop)(?:\s+(.*?))?\s*', prompt, re.S)
    if match is None:
        return None
    args = (match[1] or '').split()
    if not args:
        return 'status'
    first = ALIASES.get(args[0], args[0])
    return first if first in COMMANDS else None


def root_path(project):
    root = Path(project).resolve(strict=True)
    require(root.is_dir() and not (root/'.goal').is_symlink(), 'invalid/symlink goal directory')
    return root


@contextlib.contextmanager
def access(root, write=False):
    # Reuse the same inode lock and inherited-descriptor checks as the map.
    with module('goal_context').access(root, write=write, recovery=True, verify=False) as value:
        yield value


def runner(state):
    path = host.safe(state/'runner.json')
    return budget.runner_data(path.read_bytes()) if path.exists() else None


def records(root):
    path = root/'.goal/evidence/host'
    if not path.exists():
        return [], []
    host.folder(root)
    sessions = [host.load(p) for p in sorted(path.glob('session-*.json'))]
    require(all(r.get('project') == str(root) for r in sessions), 'host target mismatch')
    return sessions, host.attempts(path)


def outstanding(rows):
    return [dict(ticket=r['id']+':'+r['nonce'], agent_id=r['agent_id'], backend=r['backend'],
                 session=r['session'], phase=r['phase'], cancellation=r['outcome'])
            for r in rows if r['phase'] not in ('returned', 'failed', 'cancelled')]


def status(project):
    root = root_path(project)
    state = root/'.goal'
    if not state.exists():
        return dict(state='none', project=str(root), next='Start a goal with /goal-loop <objective>.')
    with access(root) as (_, state, _):
        if (state/CLEAR_PENDING).exists():
            return dict(state='recovery-required', project=str(root), next=command('recover', root),
                        reason='Interrupted clear; the archive must be finished before starting another goal.')
        if store.empty_ledger(state):
            last = host.load(host.safe(state/'cleared.json')) if (state/'cleared.json').exists() else None
            return dict(state='none', project=str(root), archive=last['archive'] if last else None,
                        next='Start a goal with /goal-loop <objective>.')
        if (state/'store/pending').exists():
            return dict(state='recovery-required', project=str(root), next=command('recover', root))
        head = store.verify_views(state)
        data = dict(line.split('=', 1) for line in (state/'state.rec').read_text().splitlines() if '=' in line)
        value = runner(state)
        cap, expired = budget.gate_limit(state, settlement=False)
        control = host.goal_control(root)
        sessions, rows = records(root)
        plan = (state/'work-plan.md').read_text() if (state/'work-plan.md').exists() else ''
        goal = (state/'goal.md').read_text() if (state/'goal.md').exists() else ''
        objective = re.search(r'^## (?:Goal|Objective)[^\n]*\n+([^#<][^\n]*)', goal, re.M)
        mode = ('paused' if control and control['mode'] == 'paused' else 'expired' if expired else
                'active' if any(s.get('active') for s in sessions) else 'ended' if sessions else
                'draft' if goal else 'none')
        return dict(state=mode, project=str(root), goal=objective[1].strip() if objective else None,
            run=value['run'] if value else None, head=head, iteration=int(data['iteration']),
            max_iterations=int(data['max_iterations']), breaker=data['breaker'],
            false_completes=int(data['false_completes']), no_progress_streak=int(data['no_progress_streak']),
            deadline_epoch=None if cap is None else time.time()+cap-time.monotonic(),
            remaining_seconds=None if cap is None else max(0, cap-time.monotonic()), expired=expired,
            last_reason=data.get('last_reason'), last_hint=data.get('last_hint'),
            pending=[s for s in plan.splitlines() if s.startswith('- [ ]')],
            accepted=[s for s in plan.splitlines() if s.startswith('- [x]')], workers=outstanding(rows),
            next=('Settle with check/close, or clear; no new work budget remains.' if expired else
                  'Resume or clear the paused goal; its original deadline still applies.' if mode == 'paused' else
                  'Inspect the current context and its actual acceptance evidence.'),
            completion_verified=False)


def publish_control(state, control):
    """Publish control intent at the existing immutable commit point."""
    require(not (state/'store/pending').exists(), 'recovery-required: run recover before changing goal control')
    head = store.verify_views(state)
    raw = store._encode(dict(payload=control, sha256=store._hash(store._encode(control))))
    store.publish_views(state, 'control', {store.CONTROL_FILE:raw},
                        'control-'+uuid.uuid4().hex, store._encode(control),
                        expected_head=head, fault=lambda stage:fault('control-'+stage),
                        preserve_receipts=True)
    fault('control-installed')


def pause_locked(root, state):
    value = runner(state)
    control = dict(version=1, project=str(root), run=value['run'] if value else None,
                   mode='paused', updated=time.time())
    # Publish the fence before touching sessions or issuing cancellation.
    publish_control(state, control)
    if (state/'evidence/host').exists():
        with host.locked(root) as (_, path):
            sessions, rows = records(root)
            for row in rows:
                host._cancel(path, path/('attempt-'+row['id']+'.json'), row)
            for session in sessions:
                session.update(active=False, paused=True)
                host.save(host.session_path(path, session['backend'], session['session']), session)
    else:
        rows = []
    return dict(state='paused', cancellation_pending=outstanding(rows), budget_retained=True,
                next='Interrupt pending native workers and reconcile their real terminal receipts before resume/clear.')


def pause(project):
    root = root_path(project)
    if not (root/'.goal').exists():
        return status(root)
    with access(root, True) as (_, state, _):
        require(not (state/CLEAR_PENDING).exists(), 'clear-recovery-required: run recover')
        if store.empty_ledger(state):
            return dict(state='none', project=str(root))
        require(not (state/'store/pending').exists(), 'recovery-required: run recover before pause')
        store.verify_views(state)
        if runner(state) is None:
            return dict(state='draft', paused=False, next='No bounded host execution exists to pause; enter with the actual initial budget before execution.')
        return pause_locked(root, state)


def resume(project, backend, session, auto=False):
    root = root_path(project)
    require(backend is not None and session is not None, 'resume needs the actual --backend and --session from the host')
    backend, session = host.identity(backend), host.identity(session)
    with access(root, True) as (_, state, _):
        require(not (state/CLEAR_PENDING).exists() and not (state/'store/pending').exists(), 'recovery-required: run recover first')
        store.verify_views(state)
        value = runner(state)
        require(value is not None, 'resume needs an existing bounded host run; use enter with the actual initial budget')
        cap, expired = budget.gate_limit(state, settlement=False)
        if expired or cap is not None and cap <= time.monotonic():
            return dict(state='expired', resumed=False, budget_retained=True, next='Use check/close to settle or clear to archive.'), 3
        sessions, rows = records(root)
        require(sessions and all(s['run'] == value['run'] for s in sessions), 'missing/conflicting original host run')
        current = [s for s in sessions if s.get('active')]
        same = len(current) == 1 and (current[0]['backend'], current[0]['session']) == (backend, session)
        control = host.goal_control(root)
        if not same or control and control['mode'] == 'paused':
            pause_locked(root, state)
            sessions, rows = records(root)
        waiting = outstanding([r for r in rows if r['outcome'] == 'cancel-requested'])
        if waiting:
            return dict(state='paused', resumed=False, cancellation_pending=waiting,
                        next='Interrupt/reconcile these native workers, then resume again.'), 3
        requests = {s['request'] for s in sessions if s.get('request') is not None}
        require(len(requests) <= 1, 'conflicting original requests; retain the ledger and inspect before resuming')
        with host.locked(root) as (_, path):
            control = dict(version=1, project=str(root), run=value['run'], mode='paused', updated=time.time())
            publish_control(state, control)
            for old in sessions:
                old.update(active=False, paused=False)
                host.save(host.session_path(path, old['backend'], old['session']), old)
            bound = dict(version=1, backend=backend, session=session, project=str(root), run=value['run'],
                         seconds=min(s['seconds'] for s in sessions), active=True, paused=False)
            if requests:
                bound['request'] = next(iter(requests))
            host.save(host.session_path(path, backend, session), bound)
            control.update(mode='active', updated=time.time())
            publish_control(state, control)
    return dict(state='active', resumed=True, budget_retained=True, host=bound,
                context=context_result('show', root, auto)), 0


def fault(stage):
    if os.environ.get('GOAL_COMMAND_FAULT') == stage:
        os._exit(91)


@contextlib.contextmanager
def archive_locks(state):
    # Trials/consumers hold their policy directory; unattended runs hold this
    # fixed file inode. Never move either while it has a live owner.
    with contextlib.ExitStack() as stack:
        lock = host.safe(state/'store/runner.lock')
        paths = [lock] if lock.exists() else []
        proposals = state/'proposals'
        if proposals.exists():
            require(not proposals.is_symlink(), 'symlink proposals directory refused')
            paths += [Path(base) for base, _, _ in os.walk(proposals, followlinks=False)]
        for path in paths:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
            try:
                store.fcntl.flock(fd, store.fcntl.LOCK_EX | store.fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('goal execution still owns '+str(path)+'; stop it before clear') from exc
        yield


def archive_path(state, record):
    require(set(record) == {'version', 'project', 'run', 'head', 'archive', 'cleared_at', 'entries'}
            and record['version'] == 1 and record['project'] == str(state.parent)
            and isinstance(record['archive'], str) and re.fullmatch(r'history/[0-9a-f]{32}', record['archive'])
            and isinstance(record['entries'], list), 'invalid clear journal')
    names = set()
    for row in record['entries']:
        require(isinstance(row, dict) and set(row) == {'name', 'device', 'inode'}
                and isinstance(row['name'], str) and row['name'] not in store.retained_fields() | {'', '.', '..', CLEAR_PENDING, '.archive.json'}
                and '/' not in row['name'] and '\\' not in row['name'] and '\0' not in row['name']
                and row['name'] not in names and type(row['device']) is int and type(row['inode']) is int,
                'invalid clear entry')
        names.add(row['name'])
    history = host.safe(state/'history')
    require(not history.exists() or history.is_dir(), 'invalid history directory')
    return host.safe(state/record['archive'])


def finish_clear(state):
    record = host.load(host.safe(state/CLEAR_PENDING))
    archive = archive_path(state, record)
    require(archive.is_dir(), 'missing clear archive directory')
    for row in record['entries']:
        source, target = state/row['name'], archive/row['name']
        src, dst = os.path.lexists(source), os.path.lexists(target)
        require(src != dst, 'clear conflict: '+row['name']+' must exist at exactly one recorded location')
        observed = (source if src else target).lstat()
        require((observed.st_dev, observed.st_ino) == (row['device'], row['inode']), 'clear entry changed: '+row['name'])
        if src:
            source.rename(target)
            store._fsync_dir(archive)
            store._fsync_dir(state)
            fault('moved-'+row['name'])
    allowed = store.retained_fields() | {CLEAR_PENDING}
    require({p.name for p in state.iterdir()} <= allowed, 'clear conflict: new entries appeared; preserve them before recovery')
    meta = host.safe(archive/'.archive.json')
    require(not meta.exists() or host.load(meta) == record, 'clear archive metadata changed')
    host.save(meta, record)
    host.save(state/'cleared.json', record)
    fault('archive-published')
    (state/CLEAR_PENDING).unlink()
    store._fsync_dir(state)
    return dict(state='none', cleared=True, archive=str(archive), history_retained=True,
                next='Start a new goal; the archived run keeps its original budget and receipts.')


def clear(project):
    root = root_path(project)
    if not (root/'.goal').exists():
        return status(root), 0
    with access(root, True) as (_, state, _):
        require(not (state/CLEAR_PENDING).exists(), 'clear-recovery-required: run recover')
        if store.empty_ledger(state):
            return dict(state='none', cleared=False), 0
        require(not (state/'store/pending').exists(), 'recovery-required: run recover before clear')
        store.verify_views(state)
        paused = pause_locked(root, state)
        if paused['cancellation_pending']:
            return dict(paused, cleared=False), 3
        with archive_locks(state):
            head = store.verify_views(state)
            value = runner(state)
            entries = [dict(name=p.name, device=p.lstat().st_dev, inode=p.lstat().st_ino)
                       for p in sorted(state.iterdir()) if p.name not in store.retained_fields()]
            record = dict(version=1, project=str(root), run=value['run'] if value else None, head=head,
                          archive='history/'+uuid.uuid4().hex, cleared_at=time.time(), entries=entries)
            archive = archive_path(state, record)
            archive.parent.mkdir(exist_ok=True)
            archive.mkdir()
            store._fsync_dir(archive.parent)
            host.save(state/CLEAR_PENDING, record)
            fault('clear-prepared')
            return finish_clear(state), 0


def recover(project):
    root = root_path(project)
    require((root/'.goal').is_dir(), 'no goal ledger to recover')
    if (root/'.goal'/CLEAR_PENDING).exists():
        with access(root, True) as (_, state, _), archive_locks(root/'.goal'):
            return finish_clear(state)
    if store.empty_ledger(root/'.goal'):
        return dict(recovered=False, status=status(root))
    result = subprocess.run(['bash', str(HERE/'goal_ctl.sh'), 'recover', '--project', str(root)],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, result.stdout+result.stderr)
    return dict(recovered=True, output=result.stdout.strip(), status=status(root))


def check(project):
    root = root_path(project)
    with access(root, True) as (_, state, _):
        require(not (state/CLEAR_PENDING).exists() and not (state/'store/pending').exists(), 'recovery-required: run recover first')
        store.verify_views(state)
        _, snapshot = store.Store(state/'store/commits').read()
        if store.CONTROL_FILE not in json.loads(snapshot[store._VIEW_META])['views']:
            control = host.goal_control(root)
            if control is not None:
                publish_control(state, control)
    return context_result('receipt', root)


def doctor():
    install = module('goal_install')
    dependencies = install.doctor()
    names = install.inventory()
    version = (HERE.parent/'VERSION').read_text().strip()
    manifest = json.loads((HERE.parent/'.claude-plugin/plugin.json').read_text())
    require(manifest['version'] == version, 'plugin version differs from VERSION')
    return dict(healthy=True, version=version, implementation=str(HERE.parent),
                files=len(names), dependencies=dependencies, commands=list(COMMANDS),
                hooks='bundled for plugin installs; standalone skills require the explicit host bridge')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='status', choices=COMMANDS+tuple(ALIASES))
    parser.add_argument('--project', default='.')
    parser.add_argument('--backend')
    parser.add_argument('--session')
    parser.add_argument('--auto', action='store_true', help='resume: only with existing automatic approval authorization')
    args = parser.parse_args()
    if (args.backend is None) != (args.session is None):
        parser.error('--backend and --session must be supplied together')
    action = ALIASES.get(args.action, args.action)
    if args.auto and action != 'resume':
        parser.error('--auto is only valid for resume')
    rc = 0
    if action == 'help':
        value = dict(commands=list(COMMANDS), aliases=ALIASES, default='status',
                     usage='/goal-loop-host:goal-loop <command>',
                     budget='Pause and resume retain the original deadline. Clear archives the old run.')
    elif action == 'doctor':
        value = doctor()
    elif action == 'check':
        value = check(args.project)
        failures = {r['result'] for r in value['checks'].values()}
        rc = 0 if value['completion_verified'] else 4 if 4 in failures else 3 if 3 in failures else 2
    elif action == 'resume':
        value, rc = resume(args.project, args.backend, args.session, args.auto)
    elif action == 'clear':
        value, rc = clear(args.project)
    else:
        value = globals()[action](args.project)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return rc


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, store.StoreError, subprocess.SubprocessError) as exc:
        print('GOAL_COMMAND: ERROR '+str(exc), file=sys.stderr)
        sys.exit(4)
