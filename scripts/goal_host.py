#!/usr/bin/env python3
"""Opt-in host receipts over existing crew, runner and runtime observations.

Explicit bridge calls wrap native host tools; this module neither dispatches
agents nor installs hooks. Native hooks consume stdin JSON when installed by
the user. Local receipts are trusted telemetry, never acceptance authority.
"""
import argparse
import contextlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


crew, trace = module('goal_crew'), module('goal_trace')
budget, store = crew.budget, crew.store
require = crew.require
TOKEN = re.compile(r'^([0-9a-f]{32}):([0-9a-f]{32})$')
HEADER = re.compile(r'^GOAL_HOST_TICKET ([0-9a-f]{32}:[0-9a-f]{32})(?:\n|$)')
TERMINAL = {'completed': ('returned', 0), 'errored': ('failed', 1), 'failed': ('failed', 1),
            'interrupted': ('cancelled', 130), 'cancelled': ('cancelled', 130)}
ERRORS = (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, store.StoreError)


def identity(value):
    require(isinstance(value, str) and bool(value) and '\0' not in value and '\n' not in value,
            'invalid host identity')
    return value


def folder(project, create=False):
    root = Path(project).resolve(strict=True)
    path = root / '.goal'
    require(path.is_dir() and not path.is_symlink(), 'missing/invalid goal directory')
    for part in ('evidence', 'host'):
        path = path / part
        require(not path.is_symlink(), 'symlink host directory refused')
        if create:
            path.mkdir(exist_ok=True)
        require(path.is_dir(), 'missing host directory')
    return root, path


def safe(path):
    require(not path.is_symlink(), 'symlink host record refused')
    return path


def save(path, value):
    safe(path)
    store._atomic(path, store._encode(dict(payload=value, sha256=store._hash(store._encode(value)))))


def load(path):
    safe(path)
    obj = json.loads(path.read_bytes())
    require(isinstance(obj, dict) and set(obj) == {'payload', 'sha256'}
            and obj['sha256'] == store._hash(store._encode(obj['payload'])), 'host receipt checksum mismatch')
    require(isinstance(obj['payload'], dict) and obj['payload'].get('version') == 1, 'invalid host receipt version')
    return obj['payload']


@contextlib.contextmanager
def locked(project, create=False):
    root, path = folder(project, create)
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        end = time.monotonic() + 2
        while True:
            try:
                store.fcntl.flock(fd, store.fcntl.LOCK_EX | store.fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    raise ValueError('host receipt busy; retry without dispatch')
                time.sleep(.005)
        yield root, path
    finally:
        os.close(fd)


def session_path(path, backend, session, prefix='session'):
    return path / (prefix + '-' + store._hash(store._encode([identity(backend), identity(session)])) + '.json')


def capture(backend, session, kind):
    return dict(backend=identity(backend), session=identity(session), kind=kind,
                epoch=time.time(), monotonic=time.monotonic(), boot=budget.boot_identity())


def begin(project, backend, session, seconds, origin=None):
    """Bind an explicit goal session; manual entry observes tool entry only."""
    backend, session = identity(backend), identity(session)
    require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0, 'invalid host budget')
    observed = capture(backend, session, 'tool') if origin is None else budget.host_origin(origin)
    require(observed['backend'] == backend and observed['session'] == session, 'origin/session mismatch')
    root = Path(project).resolve(strict=True)
    state = root / '.goal'
    require(not state.is_symlink(), 'symlink goal directory refused')
    if not state.exists():
        result = subprocess.run(['bash', str(Path(__file__).with_name('goal_ctl.sh')), 'init', '--project', str(root)],
                                capture_output=True, timeout=30)
        require(result.returncode == 0, 'goal initialization failed')
    with locked(root, create=True) as (_, path):
        cached = session_path(path, backend, session, 'prompt')
        if origin is None and cached.exists():
            receipt = load(cached)
            require(receipt.get('project') == str(root), 'prompt target mismatch')
            observed = receipt['origin']
        adopted = budget.adopt_host(state, observed, seconds)
        target = session_path(path, backend, session)
        previous = load(target) if target.exists() else None
        if previous:
            require(previous['run'] == adopted['run'], 'session belongs to another run')
        value = dict(version=1, backend=backend, session=session, project=str(root), run=adopted['run'],
                     seconds=min(seconds, previous['seconds']) if previous else seconds, active=True)
        save(target, value)
        return dict(value, scope=adopted['scope'], deadline_epoch=adopted['deadline'],
                    deadline_monotonic=adopted['monotonic']['deadline'])


def enter(project, seconds, backend=None, session=None):
    """Discover only a unique recorded host identity; never invent a session."""
    root, path = folder(project)
    with locked(root):
        rows = [load(p) for p in sorted(path.glob('prompt-*.json'))]
        identities = {(r['origin']['backend'], r['origin']['session']) for r in rows
                      if r.get('project') == str(root)}
        if backend is not None:
            identities = {p for p in identities if p[0] == backend}
        if session is not None:
            identities = {p for p in identities if p[1] == session}
        if not identities:
            rows = [load(p) for p in sorted(path.glob('session-*.json'))]
            identities = {(r['backend'], r['session']) for r in rows if r.get('active')
                          and r.get('project') == str(root) and (backend is None or r['backend'] == backend)
                          and (session is None or r['session'] == session)}
        require(len(identities) == 1, 'missing/ambiguous recorded host identity; use begin with actual backend/session')
        chosen_backend, chosen_session = next(iter(identities))
    return begin(root, chosen_backend, chosen_session, seconds)


def active(path, root, session=None, backend=None):
    sessions = [load(p) for p in sorted(path.glob('session-*.json'))]
    sessions = [s for s in sessions if s.get('active') and (session is None or s['session'] == session)
                and (backend is None or s['backend'] == backend)]
    require(len(sessions) == 1, 'missing/ambiguous active goal session')
    value = sessions[0]
    require(value['project'] == str(root), 'host target changed')
    with crew.read_ledger(root) as (state, _):
        current = budget.runner_data((state / 'runner.json').read_bytes())
    require(value['run'] == current['run'], 'host session belongs to another run')
    return value


def limits(root, with_identity=False):
    with crew.read_ledger(root) as (state, _):
        cap, expired = budget.gate_limit(state, settlement=False)
        value = budget.runner_data((state / 'runner.json').read_bytes())
        counters = dict(line.split('=', 1) for line in (state/'state.rec').read_text().splitlines() if '=' in line)
        binding = store._hash(store._encode([value['deadline'], value['monotonic'], counters.get('deadline'),
                                           os.environ.get('GOAL_RUNNER_MONOTONIC_END')]))
    require(not expired and cap is not None and cap > time.monotonic(), 'time-budget-exhausted; no dispatch')
    return (value['deadline'], cap, binding) if with_identity else (value['deadline'], cap)


def attempts(path):
    return [load(p) for p in sorted(path.glob('attempt-*.json'))]


def get(path, ticket):
    match = TOKEN.fullmatch(ticket) if isinstance(ticket, str) else None
    require(match is not None, 'invalid host ticket')
    target = path / ('attempt-' + match[1] + '.json')
    row = load(target)
    require(row.get('id') == match[1] and row.get('nonce') == match[2], 'host ticket nonce mismatch')
    require(row.get('project') == str(path.parents[2]) and isinstance(row.get('trace'), str)
            and crew.ID.fullmatch(row['trace']) and crew.ID.fullmatch(row.get('wave', '')),
            'host ticket target mismatch')
    return target, row


def host_fields(session, event, **values):
    row = dict(backend=session['backend'], session=session['session'], event=event,
               call_id=None, agent_id=None, parent_agent_id=None, task=None, files=None,
               input_sha256=None, output_sha256=None, before_sha256=None, after_sha256=None,
               ready=None, outcome='running', receipt_sha256=None)
    row.update(values)
    return trace.host_metadata(row)


def runtime(row, event, result=None):
    """Resume one persisted Trace without creating a second completion queue."""
    _, directory = trace.directory(row['project'])
    target = safe(directory / (row['trace'] + '.json'))
    envelope = json.loads(target.read_bytes())
    data = envelope['payload']
    require(envelope['sha256'] == trace.checksum(trace.encoded(data)) and data['id'] == row['trace'],
            'runtime receipt checksum mismatch')
    data['host'].update(event=event, call_id=row['call_id'], agent_id=row['agent_id'],
                        parent_agent_id=row['parent_agent_id'], ready=row['ready'], outcome=row['outcome'],
                        after_sha256=row['after_sha256'], output_sha256=row['after_sha256'],
                        receipt_sha256=row['receipts'][-1] if row['receipts'] else None)
    trace.host_metadata(data['host'])
    if result is not None and data['state'] != 'complete':
        require(row['boot'] == budget.boot_identity(), 'boot changed during host attempt')
        data.update(finished=time.time(), elapsed=max(0, time.monotonic()-data['start_monotonic']),
                    result=result, state='complete')
    trace.publish(target, data)


def ready_launcher(row, verify=False):
    digest = row.get('ready_launcher_sha256')
    if digest is None:
        return None
    script = Path(row['project']) / '.goal/evidence/host' / ('ready-' + row['id'] + '.sh')
    if verify:
        safe(script)
        require(script.is_file() and script.stat().st_size <= 65536
                and store._hash(script.read_bytes()) == digest, 'ready launcher missing or changed')
    return shlex.join(['bash', str(script)])


def response(row):
    ticket = row['id'] + ':' + row['nonce']
    python = row.get('command_python', sys.executable)
    require(isinstance(python, str) and Path(python).is_absolute() and '\0' not in python,
            'invalid ticket interpreter')
    args = [python, '-I', str(Path(__file__).resolve()), 'ready', str(row['project']), ticket]
    command = shlex.join(args)
    tool = [python, '-I', str(Path(__file__).with_name('goal_host_command.py').resolve()),
            str(row['project']), ticket, '--']
    owned_ready = shlex.join(tool + args)
    checked = shlex.join([python, '-I', str(Path(__file__).with_name('goal_host_command.py').resolve()),
                          '--check', str(row['project']), ticket])
    launcher = ready_launcher(row)
    context = row.get('context')
    brief = ('\nTask input map (context selection, not an OS read fence): ' + json.dumps(context, sort_keys=True) + '\n') if context else ''
    return dict(ticket=ticket, header='GOAL_HOST_TICKET ' + ticket,
                ready_command=command, files=row['files'],
                owned_ready_command=owned_ready, launcher_command=launcher,
                check_command=checked, tool_prefix=shlex.join(tool)+' ',
                worker_prefix='GOAL_HOST_TICKET ' + ticket + '\nFirst tool command: ' + (launcher or owned_ready) +
                    '\nRun every shell tool through this owned prefix: ' + shlex.join(tool) +
                    ' COMMAND ARG...\nRun the frozen check without inline shell code: ' + checked + '\n' + brief,
                cancel_file=row['cancel_file'], deadline_epoch=row['deadline_epoch'],
                deadline_monotonic=row['deadline_monotonic'], trace=row['trace'])


def prepare(project, wave, task, session=None, call_id=None):
    with locked(project) as (root, path):
        current = active(path, root, session)
        end, cap, budget_identity = limits(root, with_identity=True)
        worker = crew.Wave(root, wave)
        graph = crew.load(worker.path)
        require(task in graph['jobs'], 'unregistered host task')
        require(not graph['jobs'][task].get('reused_from'), 'accepted unit is reused; prepare only the failed unit')
        crew.policy_current(graph.get('policy'))
        job = next(j for j in graph['graph']['jobs'] if j['id'] == task)
        prior = [r for r in attempts(path) if r['wave'] == wave and r['task'] == task]
        require(len(prior) <= 1, 'ambiguous host attempt')
        if prior:
            row = prior[0]
            require(row['session'] == current['session'] and row['backend'] == current['backend'], 'attempt/session mismatch')
            require(row['phase'] in ('preparing', 'prepared'), 'host task already terminal')
            if call_id is not None:
                require(row['call_id'] in (None, call_id), 'native call identity changed')
                row['call_id'] = identity(call_id)
        else:
            row = dict(version=1, id=uuid.uuid4().hex, nonce=uuid.uuid4().hex,
                       project=str(root), wave=wave, task=task, files=job['files'],
                       backend=current['backend'], session=current['session'], run=current['run'],
                       call_id=identity(call_id) if call_id is not None else None,
                       agent_id=None, parent_agent_id=None, phase='preparing', outcome='running',
                       ready=None, receipts=[], boot=budget.boot_identity(), command_python=sys.executable,
                       before_sha256=store._hash(store._encode(crew.scope_digest(root, job['files']))),
                       after_sha256=None, deadline_epoch=end, deadline_monotonic=cap, budget_identity=budget_identity)
            if graph['graph']['version'] == 2:
                row['context'] = dict(inputs=job['inputs'], check=job['check'], repair=graph['jobs'][task].get('repair'),
                                      policy=graph.get('policy'))
            row['cancel_file'] = str(path / ('cancel-' + row['id'] + '-' + row['nonce']))
            span = trace.Trace(root, 'executor', 'host-worker:' + task, ['host-dispatch', current['backend']],
                               host=host_fields(current, 'dispatch-requested', task=task, files=job['files'],
                                                call_id=row['call_id'], before_sha256=row['before_sha256'],
                                                input_sha256=store._hash(store._encode(graph['inputs']))))
            row['trace'] = span.identity
        target = path / ('attempt-' + row['id'] + '.json')
        save(target, row)
        try:
            if graph['jobs'][task]['dispatch'] is None:
                worker.event(task, 'dispatch')
            if row['backend'] == 'claude' and row.get('ready_launcher_sha256') is None:
                script = safe(path / ('ready-' + row['id'] + '.sh'))
                body = ('#!/bin/sh\nexec ' + response(row)['owned_ready_command'] + '\n').encode()
                if script.exists():
                    require(script.is_file() and script.read_bytes() == body, 'ready launcher already differs')
                else:
                    store._atomic(script, body)
                row['ready_launcher_sha256'] = store._hash(body)
            row['phase'] = 'prepared'
            if row.get('budget_identity') != budget_identity:
                row['deadline_epoch'] = min(end, row['deadline_epoch'])
                row['deadline_monotonic'] = min(cap, row['deadline_monotonic'])
                row['budget_identity'] = budget_identity
            save(target, row)
            runtime(row, 'prepared')
        except ERRORS as exc:
            row.update(phase='failed', outcome='failed', error=type(exc).__name__,
                       after_sha256=store._hash(store._encode(crew.scope_digest(root, row['files']))))
            save(target, row)
            runtime(row, 'dispatch-rejected', 4)
            raise
        return response(row)


def native_identity(receipt):
    require(isinstance(receipt, dict), 'native receipt must be an object')
    agent, name = receipt.get('agentId'), receipt.get('task_name')
    if agent is not None:
        return identity(agent)
    require(isinstance(name, str) and name.startswith('/') and all(p and p not in ('.', '..') for p in name.split('/')[1:]),
            'receipt lacks native agentId/canonical task_name')
    return identity(name)


def attach(project, ticket, receipt):
    agent = native_identity(receipt)
    digest = store._hash(store._encode(receipt))
    with locked(project) as (_, path):
        target, row = get(path, ticket)
        require(row['phase'] == 'prepared', 'attempt was not dispatched')
        require(row['agent_id'] in (None, agent), 'native agent identity changed')
        require(not any(r['id'] != row['id'] and r['agent_id'] == agent
                        and r['session'] == row['session'] for r in attempts(path)), 'agent already attached to another attempt')
        row['agent_id'] = agent
        if receipt.get('parent_agent_id') is not None:
            row['parent_agent_id'] = identity(receipt['parent_agent_id'])
        if digest not in row['receipts']:
            row['receipts'].append(digest)
        save(target, row)
        runtime(row, 'launch-acknowledged')
        return row


def ready(project, ticket):
    observed = dict(epoch=time.time(), monotonic=time.monotonic())
    with locked(project) as (root, path):
        target, row = get(path, ticket)
        require(row['phase'] == 'prepared', 'attempt is not active')
        limits(root)
        crew.policy_current(crew.load(crew.Wave(root, row['wave']).path).get('policy'))
        require(not safe(Path(row['cancel_file'])).exists(), 'attempt cancellation requested')
        if row['ready'] is None:
            worker = crew.Wave(root, row['wave'])
            graph = crew.load(worker.path)
            if graph['jobs'][row['task']]['started'] is None:
                worker.event(row['task'], 'started')
            row['ready'] = observed
            save(target, row)
            runtime(row, 'first-tool-ready')
        return row


def statuses(receipt):
    """Normalize only structured native status fields, never message text."""
    if isinstance(receipt, list):
        rows = []
        for row in receipt:
            if 'agent_name' in row:
                agent = native_identity({'task_name': row['agent_name']})
                status = row.get('agent_status')
                # Work's completion variant contains final prose as its
                # value. Only the structured variant name is evidence.
                if isinstance(status, dict):
                    status = 'completed' if set(status) == {'completed'} else 'unknown'
            else:
                agent, status = native_identity(row), row.get('status')
            rows.append((agent, status if isinstance(status, str) else 'unknown'))
        return rows
    require(isinstance(receipt, dict), 'invalid host status receipt')
    if receipt.get('method') in ('turn/completed', 'item/completed'):
        return statuses(receipt['params'])
    if 'agents' in receipt:
        return statuses(receipt['agents'])
    if 'item' in receipt:
        item = receipt['item']
        require(isinstance(item, dict) and item.get('type') == 'collabAgentToolCall', 'unknown native item')
        return statuses(item)
    if 'agentsStates' in receipt:
        require(isinstance(receipt['agentsStates'], dict), 'invalid native agent states')
        return [(identity(k), v.get('status')) for k, v in receipt['agentsStates'].items() if isinstance(v, dict)]
    if 'threadId' in receipt and isinstance(receipt.get('turn'), dict):
        return [(identity(receipt['threadId']), receipt['turn'].get('status'))]
    return [(native_identity(receipt), receipt.get('status'))]


def _terminal(root, path, target, row, outcome, code, digest):
    if row['phase'] in ('returned', 'failed', 'cancelled'):
        require(row['outcome'] == outcome, 'conflicting terminal host status')
        runtime(row, 'native-terminal', code)
        return False
    require(row['phase'] == 'prepared', 'attempt was not dispatched')
    worker = crew.Wave(root, row['wave'])
    graph = crew.load(worker.path)
    if graph['jobs'][row['task']]['returned'] is None:
        worker.event(row['task'], 'returned' if outcome == 'returned' else 'cancelled' if outcome == 'cancelled' else 'fault',
                     result=code, note='structured native host status: ' + outcome)
    row.update(phase=outcome, outcome=outcome,
               after_sha256=store._hash(store._encode(crew.scope_digest(root, row['files']))))
    if digest not in row['receipts']:
        row['receipts'].append(digest)
    save(target, row)
    runtime(row, 'native-terminal', code)
    return True


def reconcile(project, receipt, session=None, backend=None):
    observed = statuses(receipt)
    digest = store._hash(store._encode(receipt))
    with locked(project) as (root, path):
        current = active(path, root, session, backend)
        result = []
        for agent, status in observed:
            rows = [r for r in attempts(path) if r['session'] == current['session']
                    and r['backend'] == current['backend'] and r['agent_id'] == agent]
            if not rows:
                continue
            require(len(rows) == 1, 'ambiguous native agent identity')
            row = rows[0]
            if status not in TERMINAL:
                if digest not in row['receipts']:
                    row['receipts'].append(digest)
                    save(path / ('attempt-' + row['id'] + '.json'), row)
                    runtime(row, 'native-status-observed')
                continue
            outcome, code = TERMINAL[status]
            _terminal(root, path, path / ('attempt-' + row['id'] + '.json'), row, outcome, code, digest)
            result.append(dict(ticket=row['id'] + ':' + row['nonce'], outcome=outcome))
        return result


def _cancel(path, target, row):
    if row['phase'] in ('returned', 'failed', 'cancelled'):
        return row
    token = safe(Path(row['cancel_file']))
    require(token.parent == path and token.name == 'cancel-' + row['id'] + '-' + row['nonce'], 'invalid cancel token path')
    if not token.exists():
        store._atomic(token, b'cancel-requested\n')
    row['outcome'] = 'cancel-requested'
    save(target, row)
    runtime(row, 'cancel-requested')
    return row


def cancel(project, ticket):
    """Request only; host interrupt confirmation must arrive via reconcile."""
    with locked(project) as (_, path):
        target, row = get(path, ticket)
        return _cancel(path, target, row)


def validate(project, ticket):
    with locked(project) as (root, path):
        _, row = get(path, ticket)
        require(row['phase'] == 'returned', 'validation requires native worker completion')
    # A grader may use the whole remaining allowance. Other workers must be
    # cancellable while it runs; the crew validator holds its own view lock.
    return crew.Wave(root, row['wave']).validate(row['task'])


def adopt(project, ticket):
    with locked(project) as (root, path):
        target, row = get(path, ticket)
        require(row['phase'] == 'returned', 'adoption requires native worker completion')
        worker = crew.Wave(root, row['wave'])
        graph = crew.load(worker.path)
        job = graph['jobs'][row['task']]
        if job['adoption_version'] != len(job['validations'])-1 or job['adopted'] is None:
            worker.event(row['task'], 'adopt')
        else:
            require(crew.scope_digest(root, row['files']) == job['adopted_digest'], 'adoption evidence is stale/failed')
        row['after_sha256'] = store._hash(store._encode(crew.scope_digest(root, row['files'])))
        save(target, row)
        runtime(row, 'validated-adoption')
        return row


def deny(reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': 'goal-loop: ' + reason}}


def owned_write(root, files, value):
    """Check the declared path of a known structured write, not arbitrary code."""
    require(isinstance(value, str) and value and '\0' not in value,
            'structured worker write requires file_path')
    try:
        candidate = Path(value)
        target = (candidate if candidate.is_absolute() else root / candidate).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError('structured worker write path cannot be resolved') from exc
    require(target != root and root in target.parents,
            'structured worker write outside project')
    relative = target.relative_to(root)
    require('.goal' not in relative.parts, 'structured worker write to .goal refused')
    require(any(target == root / name or root / name in target.parents for name in files),
            'structured worker write outside owned scope')


def owned_shell(root, path, current, payload):
    """Bind first-tool tickets without guessing Start-event arrival order."""
    agent = payload.get('agent_id')
    if agent is None:
        return {}
    identity(agent)
    tool = payload.get('tool_input')
    shell = payload.get('tool_name') in ('Bash', 'shell', 'shell_command', 'exec_command', 'functions.exec_command')
    key = 'cmd' if isinstance(tool, dict) and 'cmd' in tool else 'command'
    command = tool.get(key) if isinstance(tool, dict) else None
    rows = [r for r in attempts(path) if r['session'] == current['session'] and r['backend'] == current['backend']]
    linked = [r for r in rows if r['agent_id'] == agent]
    if not linked and shell and isinstance(command, str):
        for row in rows:
            brief = response(row)
            if command.strip() in (brief['ready_command'], brief['owned_ready_command'], brief['launcher_command']):
                if command.strip() == brief['launcher_command']:
                    ready_launcher(row, verify=True)
                attach(root, row['id']+':'+row['nonce'], {'agentId': agent})
                linked = [get(path, row['id']+':'+row['nonce'])[1]]
                break
    require(len(linked) == 1, 'unregistered native worker; execute its exact owned_ready_command first')
    row = linked[0]
    crew.policy_current(crew.load(crew.Wave(root, row['wave']).path).get('policy'))
    require(row['phase'] == 'prepared' and not safe(Path(row['cancel_file'])).exists(), 'attempt is not active or cancellation requested')
    if not shell:
        if current['backend'] == 'claude' and payload.get('tool_name') in ('Write', 'Edit'):
            owned_write(root, row['files'], tool.get('file_path') if isinstance(tool, dict) else None)
        return {}
    require(isinstance(command, str) and command, 'unsupported native shell input; use the owned command wrapper')
    brief = response(row)
    if command.strip() == brief['launcher_command']:
        ready_launcher(row, verify=True)
        return {}
    if command.strip() in (brief['ready_command'], brief['check_command']):
        return {}
    prefix = [row.get('command_python', sys.executable), '-I', str(Path(__file__).with_name('goal_host_command.py').resolve()),
              str(root), row['id']+':'+row['nonce'], '--']
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = []
    if argv[:len(prefix)] == prefix and shlex.join(argv) == command.strip():
        return {}
    wrapped = shlex.join(prefix + ['/bin/sh', '-c', command])
    if current['backend'] == 'codex':
        # Codex accepts updatedInput only with an explicit allow. Retrying the
        # canonical wrapper preserves the host's normal permission decision.
        return deny('run this owned command through normal host permissions: ' + wrapped)
    updated = dict(tool); updated[key] = wrapped
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'updatedInput': updated}}


def lifecycle(root, path, current, payload):
    """Unpaired Start/Stop remains an unknown lifecycle observation."""
    fields = {key: payload.get(key) for key in ('hook_event_name', 'tool_use_id', 'agent_id', 'turn_id')}
    fields.update(backend=current['backend'], session=current['session'])
    digest = store._hash(store._encode(fields))
    target = path / ('event-' + digest + '.json')
    if not target.exists():
        event = dict(version=1, event=fields['hook_event_name'], known=False, agent_id=fields['agent_id'],
                     backend=current['backend'], session=current['session'], receipt_sha256=digest)
        span = trace.Trace(root, 'command', 'host-lifecycle', ['host-event', fields['hook_event_name']],
                           host=host_fields(current, fields['hook_event_name'], agent_id=fields['agent_id'], receipt_sha256=digest))
        event['trace'] = span.identity
        save(target, event)


def hook(payload, backend, project=None):
    require(isinstance(payload, dict), 'hook input must be an object')
    event, session = payload.get('hook_event_name'), payload.get('session_id')
    if not isinstance(session, str) or not session:
        return {}
    target = project if project is not None else payload.get('cwd')
    if not isinstance(target, (str, Path)):
        return {}
    root = Path(target).resolve(strict=True)
    prompt = payload.get('prompt', '')
    requested = (event == 'UserPromptSubmit' and isinstance(prompt, str)
                 and re.match(r'^\s*/(?:goal-loop|goal-loop-host:goal-loop)\s+\S', prompt) is not None
                 and prompt.split(maxsplit=1)[1].strip() not in ('status', 'continue', 'resume', '继续'))
    origin = capture(backend, session, 'prompt') if event == 'UserPromptSubmit' and (requested or project is not None) else None
    if requested and not (root / '.goal').exists():
        initialized = subprocess.run(['bash', str(Path(__file__).with_name('goal_ctl.sh')), 'init', '--project', str(root)],
                                     capture_output=True, timeout=3)
        require(initialized.returncode == 0, 'goal initialization failed at prompt entry')
    if not (root / '.goal').is_dir() or (root / '.goal').is_symlink():
        return {}
    try:
        _, path = folder(root)
    except ValueError:
        # Explicit prompt target may cache entry for a later opt-in begin.
        if event != 'UserPromptSubmit' or not (requested or project is not None):
            return {}
        _, path = folder(root, create=True)
    if event == 'UserPromptSubmit' and (requested or project is not None):
        with locked(root):
            cached = session_path(path, backend, session, 'prompt')
            if not cached.exists():
                save(cached, dict(version=1, project=str(root), origin=origin))
        return {}
    try:
        current = active(path, root, session, backend)
    except ValueError as exc:
        if 'missing/ambiguous' in str(exc):
            return {}
        raise
    if event == 'PreToolUse':
        try:
            limits(root)
            shell_result = owned_shell(root, path, current, payload)
            if shell_result:
                return shell_result
            if payload.get('tool_name') in ('Agent', 'Task', 'spawn_agent'):
                tool = payload.get('tool_input')
                require(isinstance(tool, dict), 'missing native agent input')
                message = tool.get('prompt', tool.get('message'))
                match = HEADER.match(message) if isinstance(message, str) else None
                require(match is not None, 'unregistered agent dispatch; prepare a host ticket')
                with locked(root):
                    record, row = get(path, match[1])
                    crew.policy_current(crew.load(crew.Wave(root, row['wave']).path).get('policy'))
                    require(row['backend'] == backend and row['session'] == session and row['phase'] == 'prepared', 'ticket/session scope mismatch')
                    require(not safe(Path(row['cancel_file'])).exists(), 'attempt cancellation requested')
                    require('files' not in tool or tool['files'] == row['files'], 'native owned scope differs from registered task')
                    call = identity(payload.get('tool_use_id'))
                    require(row['call_id'] in (None, call), 'ticket already bound to another native call')
                    require(not any(r['id'] != row['id'] and r['call_id'] == call and r['session'] == session for r in attempts(path)),
                            'native call already bound')
                    row['call_id'] = call
                    save(record, row)
                    runtime(row, 'native-pre-tool')
        except ERRORS as exc:
            return deny(str(exc))
        return {}
    if event in ('SubagentStart', 'SubagentStop', 'Stop', 'SessionEnd'):
        with locked(root):
            lifecycle(root, path, current, payload)
        return {}
    if event == 'Interrupt':
        with locked(root):
            for row in attempts(path):
                if row['session'] == session and row['backend'] == backend:
                    _cancel(path, path / ('attempt-' + row['id'] + '.json'), row)
        return {}
    if event in ('PostToolUse', 'PostToolUseFailure'):
        rows = [r for r in attempts(path) if r['call_id'] == payload.get('tool_use_id') and r['session'] == session
                and r['backend'] == backend and r['call_id'] is not None]
        if not rows:
            return {}
        require(len(rows) == 1, 'ambiguous native call')
        row = rows[0]
        ticket = row['id'] + ':' + row['nonce']
        if event == 'PostToolUseFailure':
            digest = store._hash(store._encode({k: payload.get(k) for k in ('tool_use_id', 'is_interrupt')}))
            with locked(root):
                target, row = get(path, ticket)
                if payload.get('is_interrupt') is True:
                    _cancel(path, target, row)
                else:
                    _terminal(root, path, target, row, 'failed', 1, digest)
            return {}
        receipt = payload.get('tool_response')
        if isinstance(receipt, dict) and ('agentId' in receipt or 'task_name' in receipt):
            if row['phase'] == 'prepared':
                attach(root, ticket, receipt)
            reconcile(root, receipt, session, backend)
        return {}
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('begin')
    p.add_argument('project'); p.add_argument('backend'); p.add_argument('session'); p.add_argument('seconds', type=float)
    p.add_argument('--origin', type=Path)
    p.add_argument('--context', action='store_true', help='return the current action map with the bound host entry')
    p.add_argument('--auto', action='store_true', help='context: only with existing automatic approval authorization')
    p = commands.add_parser('enter')
    p.add_argument('project'); p.add_argument('seconds', type=float)
    p.add_argument('--backend'); p.add_argument('--session')
    p.add_argument('--context', action='store_true', help='return the current action map with the bound host entry')
    p.add_argument('--auto', action='store_true', help='context: only with existing automatic approval authorization')
    p = commands.add_parser('prepare')
    p.add_argument('project'); p.add_argument('wave'); p.add_argument('task'); p.add_argument('--session'); p.add_argument('--call-id')
    for name in ('attach', 'ready', 'cancel', 'validate', 'adopt'):
        p = commands.add_parser(name); p.add_argument('project'); p.add_argument('ticket')
        if name == 'attach': p.add_argument('receipt', type=Path)
    p = commands.add_parser('reconcile')
    p.add_argument('project'); p.add_argument('receipt', type=Path); p.add_argument('--session'); p.add_argument('--backend')
    p = commands.add_parser('hook')
    p.add_argument('--backend', choices=('claude', 'codex'), required=True); p.add_argument('--project')
    args = parser.parse_args()
    if getattr(args, 'auto', False) and not args.context:
        parser.error('--auto requires --context')
    if args.command == 'hook':
        payload = json.load(sys.stdin)
        try:
            result = hook(payload, args.backend, args.project)
        except ERRORS as exc:
            if isinstance(payload, dict) and payload.get('hook_event_name') == 'PreToolUse':
                result = deny(str(exc))
            else:
                raise
    elif args.command == 'enter':
        result = enter(args.project, args.seconds, args.backend, args.session)
    elif args.command == 'begin':
        result = begin(args.project, args.backend, args.session, args.seconds,
                       json.loads(args.origin.read_bytes()) if args.origin else None)
    elif args.command == 'prepare':
        result = prepare(args.project, args.wave, args.task, args.session, args.call_id)
    elif args.command == 'attach':
        result = attach(args.project, args.ticket, json.loads(args.receipt.read_bytes()))
    elif args.command == 'reconcile':
        result = reconcile(args.project, json.loads(args.receipt.read_bytes()), args.session, args.backend)
    else:
        result = globals()[args.command](args.project, args.ticket)
    if getattr(args, 'context', False):
        context = module('goal_context')
        try:
            view = context.show(args.project, args.auto)
        except context.store.StoreError as exc:
            raise ValueError(str(exc)) from exc
        result = dict(host=result, context=view)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except ERRORS as exc:
        print('GOAL_HOST: ERROR %s' % exc, file=sys.stderr)
        sys.exit(4)
