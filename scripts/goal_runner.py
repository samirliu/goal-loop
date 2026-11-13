#!/usr/bin/env python3
"""Atomic unattended-run ownership and transactional budget observations.

The permanent runner.lock inode provides kernel exclusion. .goal/lock is only
a legacy-compatible human receipt. Budget files join the controller's immutable
commit history; pointer publication precedes view installation, so interruption
requires recovery instead of exposing a mixture as a valid run.
"""
import contextlib
import fcntl
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('goal_store', Path(__file__).with_name('goal_store.py'))
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def natural(value, label):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise store.StoreError('invalid-' + label)
    return int(value)


def boot_identity():
    if sys.platform.startswith('linux'):
        data = Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
    elif sys.platform == 'darwin':
        # Binary timeval, independent of locale/timezone and wall-clock edits.
        data = subprocess.check_output(['/usr/sbin/sysctl', '-b', 'kern.boottime'], timeout=1)
    else:
        raise store.StoreError('persistent-monotonic-budget-unavailable')
    if not data:
        raise store.StoreError('boot-identity-unavailable')
    return store._hash(data)


def own(state, started, script, args):
    natural(started, 'clock')
    state = Path(state)
    # Reuse the initialized store; do not create a second state hierarchy.
    path = state / 'store/runner.lock'
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise store.StoreError('invalid-runner-lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise store.StoreError('live-lock; another runner owns this run') from exc
        os.lseek(fd, 0, os.SEEK_SET)
        previous_receipt = os.read(fd, 4096)
        if previous_receipt:
            previous_receipt = json.loads(previous_receipt)
            if (not isinstance(previous_receipt, dict) or set(previous_receipt) != {'version', 'pid', 'started'}
                    or type(previous_receipt['version']) is not int or previous_receipt['version'] != 1
                    or type(previous_receipt['pid']) is not int or previous_receipt['pid'] <= 1
                    or type(previous_receipt['started']) is not int or previous_receipt['started'] < 0):
                raise store.StoreError('invalid-runner-lock-receipt')
        receipt = store._close_path(state, 'lock')
        if receipt.exists():
            lines = receipt.read_text().splitlines()
            if len(lines) != 2 or not all(v.isascii() and v.isdigit() for v in lines) or int(lines[0]) <= 1:
                raise store.StoreError('invalid-legacy-runner-lock')
            owned_receipt = previous_receipt and (previous_receipt['pid'], previous_receipt['started']) == tuple(map(int, lines))
            if not owned_receipt:
                try:
                    os.kill(int(lines[0]), 0)
                except ProcessLookupError:
                    pass
                else:
                    raise store.StoreError('live-lock pid=' + lines[0])
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, store._encode(dict(version=1, pid=os.getpid(), started=int(started))))
        os.fsync(fd)
        store._atomic(receipt, ('%s\n%s\n' % (os.getpid(), started)).encode('ascii'))
        env = os.environ.copy()
        env.update(GOAL_RUNNER_FD=str(fd), GOAL_RUNNER_EXEC_PID=str(os.getpid()),
                   GOAL_RUNNER_OWNER_PID=str(os.getpid()), GOAL_RUNNER_STARTED_AT=started,
                   GOAL_RUNNER_MONOTONIC_START=str(time.monotonic()))
        env.pop('GOAL_RUNNER_MONOTONIC_END', None)
        os.set_inheritable(fd, True)
        os.execvpe('bash', ['bash', script, *args], env)
    finally:
        os.close(fd)


@contextlib.contextmanager
def ledger(state):
    fd = os.open(str(state), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise store.StoreError('ledger-busy; budget observation refused') from exc
        if (state / 'store/pending').exists():
            raise store.StoreError('recovery-required')
        store.verify_views(state)
        yield
    finally:
        os.close(fd)


def runner_data(data):
    value = json.loads(data)
    fields = {'version', 'run', 'scope', 'started', 'deadline', 'clock', 'monotonic', 'result'}
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] not in (1, 2)
            or set(value) != fields | ({'origin'} if value['version'] == 2 else set())
            or not isinstance(value['run'], str) or not store._OPERATION.fullmatch(value['run'])
            or value['scope'] not in (('script-entry',) if value['version'] == 1 else
                                      ('script-entry', 'host-prompt-entry', 'host-tool-entry'))
            or any(type(value[n]) is not int or value[n] < 0 for n in ('started', 'deadline', 'clock'))):
        raise store.StoreError('invalid-runner-state')
    if value['version'] == 2:
        host_origin(value['origin'])
        if value['scope'] != 'script-entry' and value['scope'] != 'host-' + value['origin']['kind'] + '-entry':
            raise store.StoreError('invalid-runner-scope')
    mono = value['monotonic']
    if (not isinstance(mono, dict) or set(mono) != {'boot', 'deadline'}
            or not isinstance(mono['boot'], str) or not store._SHA256.fullmatch(mono['boot'])
            or type(mono['deadline']) not in (int, float) or not math.isfinite(mono['deadline']) or mono['deadline'] < 0):
        raise store.StoreError('invalid-persisted-monotonic-budget')
    result = value['result']
    if result is not None and (not isinstance(result, dict) or set(result) != {'outcome', 'gate_completed', 'elapsed', 'timely'}
            or result['outcome'] not in ('delivered', 'incomplete') or type(result['gate_completed']) is not int
            or result['gate_completed'] < 0 or type(result['elapsed']) not in (int, float)
            or not math.isfinite(result['elapsed']) or result['elapsed'] < 0 or type(result['timely']) is not bool):
        raise store.StoreError('invalid-runner-result')
    return value


def host_origin(origin):
    """Validate an adapter receipt; it is evidence of observation, not authority.

    Adapters must capture both clocks at their actual prompt/tool entry. The
    core cannot authenticate who wrote a local receipt, so no model-supplied
    timestamp should be passed to this API by a host adapter.
    """
    if (not isinstance(origin, dict) or set(origin) != {'backend', 'session', 'kind', 'epoch', 'monotonic', 'boot'}
            or any(not isinstance(origin[n], str) or not origin[n] for n in ('backend', 'session'))
            or origin['kind'] not in ('prompt', 'tool')
            or any(type(origin[n]) not in (int, float) or not math.isfinite(origin[n]) or origin[n] < 0
                   for n in ('epoch', 'monotonic'))
            or not isinstance(origin['boot'], str) or not store._SHA256.fullmatch(origin['boot'])):
        raise store.StoreError('invalid-host-origin')
    return dict(origin)


def _persisted_limits(state, snapshot, previous, now):
    high = previous['clock'] if previous else 0
    deadlines = [previous['deadline']] if previous else []
    # Import legacy sidecars once, without forgiving corruption or rollback.
    for name in ('runner.clock', 'runner.deadline'):
        path = store._close_path(state, name)
        if path.exists():
            value = natural(path.read_text().strip(), name.replace('.', '-'))
            if name.endswith('clock'):
                high = max(high, value)
            else:
                deadlines.append(value)
    if now < high:
        raise store.StoreError('clock-regressed')
    rows = [line[9:] for line in snapshot['state.rec'].decode('ascii').splitlines() if line.startswith('deadline=')]
    if len(rows) != 1:
        raise store.StoreError('invalid-contract-deadline')
    contract = natural(rows[0], 'contract-deadline')
    if contract:
        deadlines.append(contract)
    return deadlines


def _monotonic_limit(previous, boot, now, candidate):
    if previous:
        if previous['monotonic']['boot'] == boot:
            candidate = min(candidate, previous['monotonic']['deadline'])
        elif now <= previous['clock']:
            raise store.StoreError('clock-regressed-across-reboot')
    inherited = os.environ.get('GOAL_RUNNER_MONOTONIC_END')
    if inherited:
        inherited = float(inherited)
        if not math.isfinite(inherited) or inherited < 0:
            raise store.StoreError('invalid-monotonic-deadline')
        candidate = min(candidate, inherited)
    if not math.isfinite(candidate) or candidate < 0:
        raise store.StoreError('invalid-monotonic-deadline')
    return candidate


def _publish_budget(state, commits, head, snapshot, value, action):
    """One commit point and recovery path for script and host observations."""
    files = {'runner.json': store._encode(value), 'runner.clock': ('%s\n' % value['clock']).encode('ascii'),
             'runner.deadline': ('%s\n' % value['deadline']).encode('ascii')}
    if any(snapshot.get(name) != data for name, data in files.items()):
        updated = dict(snapshot)
        # Operation-specific retry receipts do not belong to this commit.
        updated.pop(store._CLOSE_META, None)
        updated.pop(store._MUTATION_META, None)
        updated.update(files)
        meta = json.loads(snapshot[store._VIEW_META])
        meta['views'].update({name: store._hash(data) for name, data in files.items()})
        updated[store._VIEW_META] = store._encode(meta)
        def fault(stage):
            if os.environ.get('GOAL_RUNNER_FAULT') == stage:
                os._exit(91)
        commits.commit('runner-' + uuid.uuid4().hex, store._encode({'action': action, 'clock': value['clock']}),
                       updated, expected_head=head, fault=fault)
        # A crash here leaves a mismatched projection, never valid old time.
        store._restore_views(state, files)


def adopt_host(state, origin, seconds):
    """Charge an actual host-entry receipt to this run's existing budget.

    Re-entry can only tighten either clock, never replacing an existing run
    or upgrading a previously script-scoped run's coverage claim.
    """
    state = Path(state)
    origin = host_origin(origin)
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise store.StoreError('invalid-host-budget')
    if not math.isfinite(origin['epoch'] + seconds) or not math.isfinite(origin['monotonic'] + seconds):
        raise store.StoreError('invalid-host-budget')
    with ledger(state):
        epoch, mono = time.time(), time.monotonic()
        now, boot = int(epoch), boot_identity()
        if origin['boot'] != boot:
            raise store.StoreError('stale-host-origin-boot')
        if origin['epoch'] > epoch or origin['monotonic'] > mono:
            raise store.StoreError('future-host-origin')
        commits = store.Store(state / 'store/commits')
        head, snapshot = commits.read()
        previous = runner_data(snapshot['runner.json']) if 'runner.json' in snapshot else None
        deadlines = _persisted_limits(state, snapshot, previous, now)
        # Sidecars and shell callers use integral epoch seconds. Round down so
        # the projection cannot grant a fraction of a second beyond the host.
        deadline = min([math.floor(origin['epoch'] + seconds), *deadlines])
        mono_end = _monotonic_limit(previous, boot, now,
                                   min(origin['monotonic'] + seconds, mono + max(0, deadline - epoch)))
        value = previous or dict(version=2, run=uuid.uuid4().hex,
                                 scope='host-' + origin['kind'] + '-entry',
                                 started=int(origin['epoch']), result=None)
        earliest = value.get('origin')
        if earliest is None or (earliest['boot'] == boot and
                               (origin['monotonic'], origin['epoch']) < (earliest['monotonic'], earliest['epoch'])):
            earliest = origin
        if value['scope'] != 'script-entry':
            value['scope'] = 'host-' + earliest['kind'] + '-entry'
        value.update(version=2, origin=earliest, deadline=deadline, clock=now,
                     monotonic=dict(boot=boot, deadline=mono_end))
        _publish_budget(state, commits, head, snapshot, value, 'adopt-host')
        return value


def _elapsed(value, mono_start, mono_now, now, boot):
    elapsed = mono_now - mono_start
    origin = value.get('origin')
    if origin:
        if origin['boot'] == boot:
            elapsed = max(elapsed, mono_now - origin['monotonic'])
        else:
            elapsed = max(elapsed, now - origin['epoch'])
        if value['scope'] == 'script-entry' and value['started'] < origin['epoch']:
            elapsed = max(elapsed, now - value['started'])
    else:
        # v1 has no persisted monotonic origin, but its epoch start still
        # includes previous owners instead of resetting elapsed on resume.
        elapsed = max(elapsed, now - value['started'])
    if value['result'] is not None:
        elapsed = max(elapsed, value['result']['elapsed'])
    return elapsed


def gate_limit(state, settlement=True):
    """Read-only batch envelope: earliest run limit, one finite settlement.

    The caller already owns ledger access. Returning an absolute monotonic
    deadline lets a supervised child reuse it without granting each AC (or
    a nested gate) another allowance. No deadline is created for an unbudgeted
    contract; check_timeout still bounds its individual commands.
    """
    state = Path(state)
    epoch, mono = time.time(), time.monotonic()
    remaining = []
    state_file = store._close_path(state, 'state.rec')
    if state_file.exists():
        rows = [line[9:] for line in state_file.read_text().splitlines() if line.startswith('deadline=')]
        if len(rows) > 1:
            raise store.StoreError('invalid-contract-deadline')
        if rows:
            deadline = natural(rows[0], 'contract-deadline')
            if deadline:
                remaining.append(deadline - epoch)
    legacy = store._close_path(state, 'runner.deadline')
    if legacy.exists():
        remaining.append(natural(legacy.read_text().strip(), 'runner-deadline') - epoch)
    current = store._close_path(state, 'runner.json')
    if current.exists():
        value = runner_data(current.read_bytes())
        if epoch < value['clock']:
            raise store.StoreError('clock-regressed')
        remaining.append(value['deadline'] - epoch)
        if value['monotonic']['boot'] == boot_identity():
            remaining.append(value['monotonic']['deadline'] - mono)
        elif epoch <= value['clock']:
            raise store.StoreError('clock-regressed-across-reboot')
    inherited = os.environ.get('GOAL_RUNNER_MONOTONIC_END')
    if inherited is not None:
        inherited = float(inherited)
        if not math.isfinite(inherited) or inherited < 0:
            raise store.StoreError('invalid-monotonic-deadline')
    expired = bool(remaining) and min(remaining) <= 0
    entered = os.environ.get('GOAL_GATE_MONOTONIC_START')
    if entered is not None:
        entered = float(entered)
        if not math.isfinite(entered) or not 0 <= entered <= mono:
            raise store.StoreError('invalid-gate-monotonic-origin')
    cap = ((mono if entered is None else entered) + 3 if expired and settlement
           else mono + min(remaining)) if remaining else None
    shell_epoch = os.environ.get('GOAL_GATE_SHELL_EPOCH')
    if expired and settlement and shell_epoch is not None:
        # A shell observation predates interpreter startup. It can only
        # tighten the existing cap; never replace the authenticated lock origin.
        observed = float(shell_epoch)
        if not math.isfinite(observed) or observed < 0:
            raise store.StoreError('invalid-gate-shell-origin')
        cap = min(cap, mono + max(0, observed + 3 - epoch))
    if inherited is not None:
        cap = inherited if cap is None else min(cap, inherited)
    return cap, expired


def budget(state, action, started, wallclock, now):
    state = Path(state)
    started = natural(started, 'clock')
    wallclock = natural(wallclock, 'wallclock')
    now = natural(now, 'clock')
    mono_start = float(os.environ['GOAL_RUNNER_MONOTONIC_START'])
    mono_now = time.monotonic()
    boot = boot_identity()
    if not math.isfinite(mono_start) or mono_start > mono_now:
        raise store.StoreError('invalid-monotonic-origin')
    with ledger(state):
        commits = store.Store(state / 'store/commits')
        head, snapshot = commits.read()
        previous = runner_data(snapshot['runner.json']) if 'runner.json' in snapshot else None
        deadlines = [started + wallclock, *_persisted_limits(state, snapshot, previous, now)]
        if now < started or started < (previous['clock'] if previous else 0) and action == 'begin':
            raise store.StoreError('clock-regressed')
        deadline = min(deadlines)
        mono_end = _monotonic_limit(previous, boot, now,
                                    min(mono_start + wallclock, mono_now + max(0, deadline - now)))
        value = previous or dict(version=1, run=uuid.uuid4().hex, scope='script-entry',
                                 started=started, deadline=deadline, clock=now, result=None)
        value.update(deadline=deadline, clock=now, monotonic=dict(boot=boot, deadline=mono_end))
        if action == 'begin':
            value['result'] = None
        if action in ('delivered', 'incomplete'):
            value['result'] = dict(outcome=action, gate_completed=now,
                                   elapsed=_elapsed(value, mono_start, mono_now, now, boot),
                                   timely=action == 'delivered' and now < deadline and mono_now < mono_end)
        elif action not in ('begin', 'observe'):
            raise store.StoreError('unknown-budget-action')
        _publish_budget(state, commits, head, snapshot, value, action)
        remaining = max(0, math.ceil(min(deadline-now, mono_end-time.monotonic())))
        print('%s %s %s %.9f' % (deadline, now, remaining, mono_end))
        if action in ('delivered', 'incomplete'):
            print('GOAL_LOOP: RESULT outcome=%s timing=%s scope=%s' %
                  (action, 'within-budget' if value['result']['timely'] else 'after-deadline' if action == 'delivered' else 'incomplete',
                   value['scope']),
                  file=sys.stderr)


if __name__ == '__main__':
    try:
        if len(sys.argv) >= 6 and sys.argv[1] == 'own':
            own(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
        elif len(sys.argv) == 7 and sys.argv[1] == 'budget':
            budget(*sys.argv[2:])
        elif len(sys.argv) == 5 and sys.argv[1] == 'adopt-host':
            value = adopt_host(sys.argv[2], json.loads(Path(sys.argv[3]).read_bytes()), float(sys.argv[4]))
            print(store._encode(value).decode('ascii'))
        elif len(sys.argv) == 3 and sys.argv[1] == 'gate-limit':
            cap, expired = gate_limit(sys.argv[2])
            print('%s %s' % ('none' if cap is None else '%.9f' % cap, int(expired)))
        else:
            raise store.StoreError('invalid-runner-command')
    except (store.StoreError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print('GOAL_LOOP: ERROR %s' % exc, file=sys.stderr)
        sys.exit(4)
