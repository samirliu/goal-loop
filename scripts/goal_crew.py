#!/usr/bin/env python3
"""Crew cost observations and conservative DAG advice; not a worker scheduler.

The host dispatches its existing Agent/tool workers. This helper timestamps
observed lifecycle events, verifies outputs before adoption, and keeps all
outcomes. No work queue, agent service or acceptance authority is introduced.
"""
import argparse
import contextlib
import functools
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('crew_budget', Path(__file__).with_name('goal_runner.py'))
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)
store = budget.store
boot = functools.lru_cache(maxsize=1)(budget.boot_identity)
STAGES = {'coordination', 'join', 'conflict', 'revalidation', 'recovery'}
ID = re.compile(r'^[0-9a-f]{32}$')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(value):
    return isinstance(value, list) and bool(value) and all(isinstance(s, str) and '\0' not in s for s in value)


def safe_file(name):
    return (isinstance(name, str) and store._valid_name(name) and
            name.split('/')[0] not in ('.goal', '.git') and not name.startswith('/'))


def load_graph(path):
    path = Path(path).resolve(strict=True)
    graph = json.loads(path.read_bytes())
    require(isinstance(graph, dict) and set(graph) == {'version', 'context', 'capacity', 'jobs', 'final_check', 'instruments', 'inputs'},
            'unknown crew graph fields')
    require(type(graph['version']) is int and graph['version'] in (1, 2) and isinstance(graph['context'], dict), 'invalid graph version/context')
    json.dumps(graph['context'], allow_nan=False)
    require(type(graph['capacity']) is int and 1 <= graph['capacity'] <= 128, 'invalid observed host capacity')
    require(command(graph['final_check']) and isinstance(graph['instruments'], list) and isinstance(graph['inputs'], list), 'invalid grader/input declarations')
    require(isinstance(graph['jobs'], list) and bool(graph['jobs']), 'empty graph')
    names = set()
    for job in graph['jobs']:
        fields = {'id', 'files', 'deps', 'check'} | ({'inputs'} if graph['version'] == 2 else set())
        require(isinstance(job, dict) and set(job) == fields, 'unknown job fields')
        require(isinstance(job['id'], str) and re.fullmatch(r'T[1-9][0-9]*', job['id']) and job['id'] not in names, 'invalid/duplicate task id')
        names.add(job['id'])
        require(isinstance(job['files'], list) and bool(job['files']) and all(safe_file(n) for n in job['files'])
                and len(set(job['files'])) == len(job['files']), 'invalid owned file scope')
        require(isinstance(job['deps'], list) and all(isinstance(n, str) for n in job['deps'])
                and len(set(job['deps'])) == len(job['deps']) and command(job['check']), 'invalid dependency/check')
    for job in graph['jobs']:
        require(set(job['deps']) <= names and job['id'] not in job['deps'], 'unknown/self dependency')
    require(all(safe_file(n) for n in graph['inputs']) and len(set(graph['inputs'])) == len(graph['inputs']), 'invalid immutable input scope')
    require(not any(x == y or x.startswith(y+'/') or y.startswith(x+'/')
                    for x in graph['inputs'] for j in graph['jobs'] for y in j['files']), 'input and owned output overlap')
    ordered, left = [], list(graph['jobs'])
    while left:
        ready = [j for j in left if set(j['deps']) <= {x['id'] for x in ordered}]
        require(bool(ready), 'cyclic dependency graph')
        ordered.extend(ready)
        left = [j for j in left if j not in ready]
    # Overlapping writes acquire an explicit precedence in topological order.
    # File count is never evidence that concurrent work is independent.
    def overlaps(a, b):
        return any(x == y or x.startswith(y + '/') or y.startswith(x + '/') for x in a for y in b)
    edges = {j['id']: set(j['deps']) for j in ordered}
    for i, job in enumerate(ordered):
        if graph['version'] == 2:
            require(isinstance(job['inputs'], list) and len(set(job['inputs'])) == len(job['inputs'])
                    and all(safe_file(n) for n in job['inputs']), 'invalid unit inputs')
            parents = [p for p in ordered if p['id'] in job['deps']]
            available = set(graph['inputs']) | {n for p in parents for n in p['files']}
            require(set(job['inputs']) <= available, 'unit input lacks immutable source or producer')
            require(all(set(p['files']) & set(job['inputs']) for p in parents),
                    'dependency has no consumed artifact; remove the wait')
            require(not any(overlaps(job['files'], old['files']) for old in ordered[:i]),
                    'overlapping reusable units must be fused; version 1 preserves ordered shared writes')
        edges[job['id']].update(old['id'] for old in ordered[:i] if overlaps(job['files'], old['files']))
    instruments, instrument_paths = {}, {}
    for name in graph['instruments']:
        require(isinstance(name, str), 'invalid instrument path')
        source = (path.parent / name).resolve(strict=True)
        require(source.is_file(), 'instrument is not a file')
        instruments[name] = store._hash(source.read_bytes())
        instrument_paths[name] = str(source)
    graph['instrument_hashes'] = instruments
    graph['instrument_paths'] = instrument_paths
    return graph, ordered, edges


def condition_key(graph, baseline, inputs, state, transport, policy=None):
    # Absolute local instrument locations are bindings, not task difficulty.
    # Actual bytes, declared context/shape and the initial owned artifact are
    # still part of the comparison condition; trial identities are separate.
    definition = {k: v for k, v in graph.items() if k != 'instrument_paths'}
    value = dict(graph=definition, baseline=baseline, inputs=inputs, approval=store.current_approval(state),
                 contract=store._hash((state / 'goal.md').read_bytes()), observer=store._hash(Path(__file__).read_bytes()),
                 observer_transport=transport,
                 check_freeze=store._hash((state / 'check_freeze').read_bytes()) if (state / 'check_freeze').exists() else None)
    if policy is not None:
        value['routing'] = policy_identity(policy)
    return store._hash(store._encode(value))


def batch_key(graph, baseline, inputs, state, transport, policy=None):
    # Compare one worker with a decomposition only when the whole accepted
    # workload, frozen final check, actual inputs and starting bytes match.
    whole = {k: graph[k] for k in ('version', 'context', 'final_check', 'instrument_hashes')}
    return condition_key(whole, baseline, inputs, state, transport, policy)


@functools.lru_cache(maxsize=1)
def evolution():
    spec = importlib.util.spec_from_file_location('crew_evolve', Path(__file__).with_name('goal_evolve.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def policy_identity(policy):
    return {k: policy[k] for k in ('state', 'selection', 'decision')}


def routing(project, graph, policy_state=None):
    """Consume the existing qualified archive; only a serial restriction is allowed."""
    if policy_state is None:
        return None
    root = Path(project).resolve(strict=True)
    state = Path(policy_state).resolve(strict=True)
    require(state.is_relative_to(root / '.goal/proposals'), 'routing policy must be in project proposals')
    engine = evolution()
    with read_ledger(root) as (ledger, _):
        cap, expired = budget.gate_limit(ledger, settlement=False)
        contract = store._hash((ledger/'goal.md').read_bytes())
    require(not expired and (cap is None or cap > time.monotonic()), 'time-budget-exhausted; no policy execution')
    payload = dict(version=1, context=graph['context'], jobs=graph['jobs'], capacity=graph['capacity'],
                   inputs=scope_digest(root, graph['inputs']), instruments=graph['instrument_hashes'], contract=contract)
    started = time.monotonic()
    try:
        fd = engine.policy_lock(state, False)
        try:
            engine.require_settled(state)
            selected = engine.enabled_policy(state)
        finally:
            os.close(fd)
        if selected is None or selected['policy'] is None:
            return dict(state=str(state), selection=selected, decision=dict(match=False, choice='baseline', reason='no-qualified-policy'),
                        input_sha256=store._hash(store._encode(payload)), elapsed=time.monotonic()-started)
        output, rc, reason, error, selected = engine.run_enabled(state, min(2, max(0, cap-time.monotonic())) if cap else 2,
                                                               store._encode(payload), with_identity=True)
        require(rc == 0 and reason is None, 'routing policy failed: ' + str(reason or error or rc))
        decision = json.loads(output)
        require(isinstance(decision, dict) and set(decision) == {'match', 'choice', 'reason'}
                and type(decision['match']) is bool and decision['choice'] in ('baseline', 'serial')
                and isinstance(decision['reason'], str) and 0 < len(decision['reason']) <= 512
                and (decision['match'] or decision['choice'] == 'baseline'), 'invalid bounded routing decision')
        return dict(state=str(state), selection=selected, decision=decision, input_sha256=store._hash(store._encode(payload)),
                    output_sha256=store._hash(output), elapsed=time.monotonic()-started)
    except engine.ExperimentError as exc:
        raise ValueError('routing: ' + str(exc)) from exc


def policy_current(policy):
    if policy is None:
        return
    engine = evolution()
    try:
        state = Path(policy['state'])
        fd = engine.policy_lock(state, False)
        try:
            engine.require_settled(state)
            require(engine.enabled_policy(state) == policy['selection'], 'routing policy changed; replan before dispatch')
        finally:
            os.close(fd)
    except engine.ExperimentError as exc:
        raise ValueError('routing: ' + str(exc)) from exc


def unit_key(graph, task, contract):
    # Task/strategy labels cannot reset failure history for the same owned unit.
    job = next(j for j in graph['jobs'] if j['id'] == task)
    return store._hash(store._encode([contract, sorted(job['files'])]))


def unit_binding(project, graph, task, policy=None, ledger=None):
    jobs = {j['id']: j for j in graph['jobs']}
    job = jobs[task]
    names = set(graph['inputs'] if graph['version'] == 1 else job['inputs'])
    pending, seen = list(job['deps']), set()
    while pending:
        parent = pending.pop()
        if parent in seen:
            continue
        seen.add(parent)
        names.update(jobs[parent]['files'])
        names.update(jobs[parent].get('inputs', graph['inputs']))
        pending.extend(jobs[parent]['deps'])
    with (read_ledger(project) if ledger is None else contextlib.nullcontext((ledger, None))) as (state, _):
        contract = store._hash((state / 'goal.md').read_bytes())
        interface = state / 'interfaces.md'
        require(not interface.is_symlink(), 'symlink interface refused')
        interfaces = store._hash(interface.read_bytes()) if interface.exists() else None
        checker = state / 'check_freeze'
        freeze = store._hash(checker.read_bytes()) if checker.exists() else None
    return dict(inputs=scope_digest(project, sorted(names)), outputs=scope_digest(project, job['files']),
                interfaces=interfaces, contract=contract, check_freeze=freeze,
                check=job['check'], instruments=graph['instrument_hashes'], context=graph['context'],
                policy=policy_identity(policy) if policy is not None else None)


def reuse_units(project, value, retry_note):
    history = [load(p) for p in sorted(folder(project).glob('*.json'))]
    for task, row in value['jobs'].items():
        key = unit_key(value['graph'], task, value['contract_sha256'])
        row['unit_key'] = key
        binding = unit_binding(project, value['graph'], task, value.get('policy'))
        prior = [(w, r) for w in history for r in w['jobs'].values() if r.get('unit_key') == key]
        require(not any(r['dispatch'] is not None and r['returned'] is None for _, r in prior), 'unit still active; observe its terminal state')
        valid = [(w, r) for w, r in prior if w['finished'] is not None and r.get('proof') == binding
                 and r['adopted'] is not None and not r.get('reused_from')]
        if valid:
            old, accepted = max(valid, key=lambda p: p[0]['started'])
            row.update(returned=0, result=0, adopted=0, adopted_digest=binding['outputs'], proof=binding,
                       reused_from=dict(wave=old['id'], unit=key), reuse_reason='unchanged-bound-inputs-and-output')
            continue
        failed = [(w, r) for w, r in prior if w['finished'] is not None and r['dispatch'] is not None
                  and (r['fault'] or r['adopted'] is None)]
        row['failed_attempts'] = len(failed)
        require(len(failed) < 3, 'unit retry limit reached; revise the plan without renaming the unit')
        if failed:
            previous = max(failed, key=lambda p: p[0]['started'])[1]
            require(binding != previous.get('dispatch_binding') or
                    (isinstance(retry_note, str) and retry_note.strip() and retry_note != previous.get('retry_note')),
                    'unchanged retry; change a relevant condition or supply a revised breakpoint brief')
            row['repair'] = dict(scope=list(binding['outputs']), failed_checks=previous['validations'][-1:],
                                 fault=previous['fault'], attempts=len(failed), retry_note=retry_note)
        row['retry_note'] = retry_note


def scope_digest(project, files):
    result = {}
    for name in files:
        require(safe_file(name), 'invalid scope path')
        path = store._close_path(project, name)
        if not path.exists():
            result[name] = None
        else:
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode), 'scope must name regular files')
            result[name] = [stat.S_IMODE(info.st_mode), store._hash(path.read_bytes())]
    return result


@contextlib.contextmanager
def read_ledger(project):
    state = Path(project).resolve(strict=True) / '.goal'
    fd = os.open(str(state), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        store.fcntl.flock(fd, store.fcntl.LOCK_SH | store.fcntl.LOCK_NB)
        require(not (state / 'store/pending').exists(), 'recovery-required')
        store.verify_views(state)
        yield state, fd
    finally:
        os.close(fd)


def folder(project, create=False):
    project = Path(project).resolve(strict=True)
    path = project / '.goal'
    for part in ('evidence', 'crew'):
        require(not path.is_symlink(), 'symlink crew path')
        path = path / part
        if create:
            path.mkdir(exist_ok=True)
    require(path.is_dir() and not path.is_symlink(), 'missing/invalid crew observation directory')
    return path


def save(path, value):
    store._atomic(path, store._encode({'payload': value, 'sha256': store._hash(store._encode(value))}))


def load(path):
    require(path.is_file() and not path.is_symlink(), 'invalid observation file')
    obj = json.loads(path.read_bytes())
    require(isinstance(obj, dict) and set(obj) == {'payload', 'sha256'} and obj['sha256'] == store._hash(store._encode(obj['payload'])),
            'crew observation checksum mismatch')
    value = obj['payload']
    require(isinstance(value, dict) and type(value.get('version')) is int and value['version'] == 1, 'unknown crew observation version')
    require(isinstance(value.get('id'), str) and ID.fullmatch(value['id']) and path.stem == value['id'], 'observation identity/path mismatch')
    require(value.get('mode') in ('inline', 'crew') and isinstance(value.get('trial'), str) and value['trial'], 'invalid observation mode/trial')
    complete = value.get('finished') is not None
    if 'book_iteration' in value:
        require(type(value['book_iteration']) is int and value['book_iteration'] >= 0, 'invalid wave book iteration')
    finite = lambda n: type(n) in (int, float) and math.isfinite(n) and n >= 0
    require(finite(value.get('started')) and finite(value.get('origin')) and isinstance(value.get('jobs'), dict), 'invalid observation clock/jobs')
    if complete:
        require(finite(value.get('elapsed')) and type(value.get('quality')) is bool, 'invalid completed wave')
    for row in value['jobs'].values():
        require(isinstance(row, dict), 'invalid worker observation')
        for key in ('dispatch', 'started', 'returned', 'adopted', 'first_valid'):
            t = row.get(key)
            require(t is None or finite(t) and (not complete or t <= value['elapsed']), 'invalid worker timestamp')
        if row.get('started') is not None:
            require(row.get('dispatch') is not None and row['started'] >= row['dispatch'], 'startup before dispatch')
        if row.get('returned') is not None:
            if row.get('dispatch') is None:
                reused = row.get('reused_from')
                require((isinstance(row.get('fault'), dict) and row['fault'].get('kind') == 'not-dispatched') or
                        (value['graph']['version'] == 2 and isinstance(reused, dict) and set(reused) == {'wave', 'unit'}
                         and isinstance(reused['wave'], str) and ID.fullmatch(reused['wave'])
                         and reused['unit'] == row.get('unit_key') and row['returned'] == row['adopted'] == 0
                         and row.get('proof', {}).get('outputs') == row['adopted_digest']), 'terminal event without dispatch')
            else:
                require(row['returned'] >= (row.get('started') if row.get('started') is not None else row['dispatch']), 'return before worker start')
        if complete:
            require(row.get('returned') is not None, 'completed wave has pending worker')
    return value


def begin(project, graph_path, mode, trial, policy_state=None, retry_note=None):
    require(mode in ('inline', 'crew') and isinstance(trial, str) and bool(trial), 'invalid mode/trial identity')
    project = Path(project).resolve(strict=True)
    graph, ordered, edges = load_graph(graph_path)
    policy = routing(project, graph, policy_state)
    if policy is not None and policy['decision']['choice'] == 'serial':
        mode = 'inline'
    with read_ledger(project) as (state, _):
        cap, expired = budget.gate_limit(state, settlement=False)
        require(not expired and (cap is None or cap > time.monotonic()), 'time-budget-exhausted; no dispatch')
        baseline = scope_digest(project, [n for j in ordered for n in j['files']])
        inputs = scope_digest(project, graph['inputs'])
        transport = 'cli' if __name__ == '__main__' else 'python-api'
        key = condition_key(graph, baseline, inputs, state, transport, policy)
        whole = batch_key(graph, baseline, inputs, state, transport, policy)
        book_iteration = budget.natural(next(line.split('=', 1)[1] for line in (state/'state.rec').read_text().splitlines()
                                             if line.startswith('iteration=')), 'wave-book-iteration')
    identity = uuid.uuid4().hex
    value = dict(version=1, id=identity, mode=mode, trial=trial, graph=graph, edges={k: sorted(v) for k, v in edges.items()},
                 condition=key, batch_condition=whole, baseline=baseline, inputs=inputs,
                 observer_transport=transport,
                 contract_sha256=store._hash((state / 'goal.md').read_bytes()),
                 boot=boot(), started=time.time(), origin=time.monotonic(), clock=time.time(), deadline=cap,
                 jobs={j['id']: dict(dispatch=None, started=None, returned=None, result=None, fault=None,
                                     validations=[], first_valid=None, adopted=None, adopted_digest=None,
                                     adoption_version=None) for j in ordered},
                 stages=[], finished=None, elapsed=None, quality=None, final_validation=None, tokens=None, money=None)
    value['book_iteration'] = book_iteration
    if policy is not None:
        value['policy'] = policy
    path = folder(project, create=True) / (identity + '.json')
    fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        store.fcntl.flock(fd, store.fcntl.LOCK_EX | store.fcntl.LOCK_NB)
        policy_current(policy)
        if graph['version'] == 2:
            reuse_units(project, value, retry_note)
        save(path, value)
    finally:
        os.close(fd)
    return identity


class Wave:
    def __init__(self, project, identity):
        require(isinstance(identity, str) and bool(ID.fullmatch(identity)), 'invalid wave identity')
        self.project = Path(project).resolve(strict=True)
        self.folder = folder(project)
        self.path = self.folder / (identity + '.json')

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(str(self.folder), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            store.fcntl.flock(fd, store.fcntl.LOCK_EX | store.fcntl.LOCK_NB)
            value = load(self.path)
            require(value['finished'] is None, 'wave already finished')
            require(value['boot'] == boot() and time.time() >= value['clock'], 'clock/boot changed during wave')
            value['clock'] = time.time()
            yield value
            save(self.path, value)
        finally:
            os.close(fd)

    def now(self, value):
        return time.monotonic() - value['origin']

    def refresh_deadline(self, value, state):
        require(store._hash((state / 'goal.md').read_bytes()) == value['contract_sha256'], 'contract changed during wave')
        require(scope_digest(self.project, value['graph']['inputs']) == value['inputs'], 'frozen inputs changed')
        current, expired = budget.gate_limit(state, settlement=False)
        if current is not None:
            value['deadline'] = current if value['deadline'] is None else min(value['deadline'], current)
        return expired

    def event(self, task, event, result=None, note=None):
        require(event in ('dispatch', 'started', 'returned', 'fault', 'cancelled', 'cancel', 'adopt'), 'unknown worker event')
        with self.locked() as value:
            require(task in value['jobs'], 'unknown worker')
            row = value['jobs'][task]
            now = self.now(value)
            if event == 'dispatch':
                policy_current(value.get('policy'))
                require(not row.get('reused_from'), 'accepted unit is reused; dispatch only the failed unit')
                require(row['dispatch'] is None, 'duplicate dispatch')
                require(row['returned'] is None, 'worker was already cancelled')
                with read_ledger(self.project) as (state, _):
                    require(not self.refresh_deadline(value, state), 'time-budget-exhausted; no dispatch')
                require(value['deadline'] is None or time.monotonic() < value['deadline'], 'time-budget-exhausted; no dispatch')
                require(all(value['jobs'][d]['adopted'] is not None for d in value['edges'][task]), 'dependency not adopted')
                for parent in value['edges'][task]:
                    producer = next(j for j in value['graph']['jobs'] if j['id'] == parent)
                    accepted = value['jobs'][parent]
                    require(scope_digest(self.project, producer['files']) == accepted['adopted_digest'],
                            'dependency evidence is stale; repair the producer')
                    if accepted.get('proof') is not None:
                        require(unit_binding(self.project, value['graph'], parent, value.get('policy')) == accepted['proof'],
                                'dependency evidence is stale; repair the producer')
                active = [r for r in value['jobs'].values() if r['dispatch'] is not None and r['returned'] is None]
                limit = 1 if value['mode'] == 'inline' else value['graph']['capacity']
                require(len(active) < limit, 'host capacity exceeded')
                row['dispatch'] = now
                if value['graph']['version'] == 2:
                    row['dispatch_binding'] = unit_binding(self.project, value['graph'], task, value.get('policy'))
            elif event == 'started':
                require(row['dispatch'] is not None and row['started'] is None and row['returned'] is None, 'invalid started event')
                row['started'] = now
            elif event == 'cancel':
                require(row['dispatch'] is None and row['returned'] is None and isinstance(note, str) and note,
                        'cancel needs an undispatched task and observed reason')
                row.update(returned=now, fault=dict(kind='not-dispatched', note=note))
            elif event in ('returned', 'fault', 'cancelled'):
                require(row['dispatch'] is not None and row['returned'] is None, 'invalid terminal event')
                if event == 'returned':
                    require(type(result) is int and 0 <= result <= 255, 'invalid worker result')
                    row['result'] = result
                    if result:
                        row['fault'] = dict(kind='death' if result >= 128 else 'tool-error', note='nonzero worker result')
                else:
                    require(isinstance(note, str) and bool(note), 'fault needs observed reason')
                    row['fault'] = dict(kind='cancelled' if event == 'cancelled' else 'death', note=note)
                row['returned'] = now
            else:
                require(row['returned'] is not None and row['validations'], 'adoption needs terminal worker and validation')
                latest = row['validations'][-1]
                job = next(j for j in value['graph']['jobs'] if j['id'] == task)
                require(latest['result'] == 0 and scope_digest(self.project, job['files']) == latest['digest'], 'adoption evidence is stale/failed')
                if value['graph']['version'] == 2:
                    require(latest.get('binding') == unit_binding(self.project, value['graph'], task, value.get('policy')),
                            'unit validation evidence is stale')
                version = len(row['validations'])-1
                require(row['adoption_version'] is None or row['adoption_version'] < version, 'duplicate adoption')
                row.update(adopted=now, adopted_digest=latest['digest'], adoption_version=version)
                if value['graph']['version'] == 2:
                    row['proof'] = unit_binding(self.project, value['graph'], task, value.get('policy'))

    def _instruments(self, value):
        for name, expected in value['graph']['instrument_hashes'].items():
            require(store._hash(Path(value['graph']['instrument_paths'][name]).read_bytes()) == expected,
                    'frozen instrument changed')

    def _check(self, value, cmd, files):
        self._instruments(value)
        started = self.now(value)
        before = scope_digest(self.project, files)
        with read_ledger(self.project) as (state, fd):
            self.refresh_deadline(value, state)
            seconds = 120 if value['deadline'] is None else min(120, max(0, value['deadline']+3-time.monotonic()))
            env = dict(os.environ, GOAL_ACCESS_FD=str(fd), GOAL_ACCESS_OWNER_PID=str(os.getpid()), GOAL_ACCESS_MODE='read',
                       GOAL_TRACE_PROJECT=str(self.project))
            env.pop('GOAL_ACCESS_EXEC_PID', None)
            args = [s.replace('{project}', str(self.project)) for s in cmd]
            result = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('goal_bounded.py')),
                                     '--owner', str(os.getpid()), '--seconds', str(seconds), '--kind', 'measurement',
                                     '--label', 'crew-validation', '--', *args], cwd=self.project, env=env,
                                    pass_fds=(fd,), capture_output=True, timeout=seconds+2)
            store.verify_views(self.project / '.goal')
        after = scope_digest(self.project, files)
        self._instruments(value)
        require(before == after, 'grader changed owned output')
        rc = result.returncode if result.returncode >= 0 else 128-result.returncode
        return dict(start=started, end=self.now(value), result=rc, digest=after,
                    command_sha256=store._hash(store._encode(cmd)), stdout=result.stdout.decode('utf-8', 'replace'),
                    stderr=result.stderr.decode('utf-8', 'replace'))

    def validate(self, task):
        with self.locked() as value:
            require(task in value['jobs'] and value['jobs'][task]['dispatch'] is not None, 'worker not dispatched')
            job = next(j for j in value['graph']['jobs'] if j['id'] == task)
            binding = unit_binding(self.project, value['graph'], task, value.get('policy')) if value['graph']['version'] == 2 else None
            if binding is not None:
                dispatched = value['jobs'][task].get('dispatch_binding')
                require(dispatched is not None and {k: v for k, v in binding.items() if k != 'outputs'} ==
                        {k: v for k, v in dispatched.items() if k != 'outputs'}, 'unit inputs changed while worker active')
            row = self._check(value, job['check'], job['files'])
            if binding is not None:
                require(binding == unit_binding(self.project, value['graph'], task, value.get('policy')), 'unit inputs changed during validation')
                row['binding'] = binding
            value['jobs'][task]['validations'].append(row)
            if row['result'] == 0 and value['jobs'][task]['first_valid'] is None:
                value['jobs'][task]['first_valid'] = row['end']
            return row['result']

    def stage(self, name, action):
        require(name in STAGES and action in ('begin', 'end', 'skip'), 'invalid controller stage')
        with self.locked() as value:
            active = [r for r in value['stages'] if r['name'] == name and r['end'] is None]
            if action == 'skip':
                require(not any(r['name'] == name for r in value['stages']), 'stage already observed')
                now = self.now(value)
                value['stages'].append(dict(name=name, start=now, end=now, skipped='no operation performed'))
            elif action == 'begin':
                require(not active, 'stage already active')
                value['stages'].append(dict(name=name, start=self.now(value), end=None))
            else:
                require(len(active) == 1, 'stage was not started')
                active[0]['end'] = self.now(value)

    def finish(self):
        with self.locked() as value:
            require(all(r['returned'] is not None for r in value['jobs'].values()), 'worker still pending; record actual fault first')
            require(all(r['end'] is not None for r in value['stages']), 'controller stage still active')
            files = list(value['baseline'])
            value['final_validation'] = self._check(value, value['graph']['final_check'], files)
            value['stages'].append(dict(name='revalidation', start=value['final_validation']['start'],
                                        end=value['final_validation']['end'], source='frozen-final-check'))
            expected = {}
            for row in sorted(value['jobs'].values(), key=lambda r: -1 if r['adopted'] is None else r['adopted']):
                expected.update(row['adopted_digest'] or {})
            value['quality'] = (value['final_validation']['result'] == 0
                                and all(r['adopted'] is not None for r in value['jobs'].values())
                                and expected == value['final_validation']['digest'])
            if value['graph']['version'] == 2:
                value['quality'] &= all(r.get('proof') == unit_binding(self.project, value['graph'], task, value.get('policy'))
                                        for task, r in value['jobs'].items())
            value['elapsed'] = self.now(value)
            value['finished'] = time.time()
            value['worker_seconds'] = sum(r['returned']-r['dispatch'] for r in value['jobs'].values() if r['dispatch'] is not None)
            value['stage_seconds'] = {name: sum(r['end']-r['start'] for r in value['stages'] if r['name'] == name)
                                      if any(r['name'] == name for r in value['stages']) else None for name in STAGES}
            for task, row in value['jobs'].items():
                parents = [value['jobs'][d]['adopted'] for d in value['edges'][task]] or [0]
                ready = max(parents) if all(p is not None for p in parents) else None
                row['dependency_queue_seconds'] = None if row['dispatch'] is None or ready is None else row['dispatch']-ready
                row['startup_queue_seconds'] = None if row['started'] is None else row['started']-row['dispatch']
        return value


def union_length(intervals):
    end, total = 0, 0
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total


def _plan(project, graph_path, history=None, policy=None):
    graph, jobs, edges = load_graph(graph_path)
    with read_ledger(project) as (state, _):
        baseline = scope_digest(Path(project).resolve(), [n for j in jobs for n in j['files']])
        inputs = scope_digest(Path(project).resolve(), graph['inputs'])
        # Compare the producer's transport. Reading API observations through
        # the public CLI must not silently turn them into a different cohort.
        keys = {t: condition_key(graph, baseline, inputs, state, t, policy) for t in ('cli', 'python-api')}
        wholes = {t: batch_key(graph, baseline, inputs, state, t, policy) for t in keys}
        key = keys['cli' if __name__ == '__main__' else 'python-api']
        cap, expired = budget.gate_limit(state, settlement=False)
    report = dict(choice='serial', reason='insufficient-observed-costs', condition=key, serial_lower=None, crew_upper=None,
                  observations=None, failures=None, pending=None, tokens=None, money=None, budget_fit='unknown')
    report['effective_dependencies'] = {k: sorted(v) for k, v in edges.items()}
    if expired or cap is not None and cap <= time.monotonic():
        report.update(choice='stop', reason='time-budget-exhausted')
        return report
    try:
        directory = Path(history) if history else folder(project)
    except ValueError:
        return report
    rows, singles = [], []
    for path in directory.glob('*.json'):
        value = load(path)
        transport = value.get('observer_transport')
        if transport not in keys:
            continue  # Legacy records cannot establish a producer identity.
        if value.get('condition') == keys[transport]:
            rows.append(value)
        elif (value.get('batch_condition') == wholes[transport] and value.get('mode') == 'inline'
              and len(value['jobs']) == 1):
            singles.append(value)
    observed = rows + singles
    report.update(observations=len(observed), single_observations=len(singles),
                  failures=sum(r.get('quality') is False for r in observed),
                  pending=sum(r.get('finished') is None for r in observed))
    transports = {r['observer_transport'] for r in observed}
    if len(transports) > 1:
        report['reason'] = 'mixed-observer-transports'
        return report
    if transports:
        report['observer_transport'] = next(iter(transports))
        report['condition'] = keys[report['observer_transport']]
    trials = [(r['mode'], r['trial']) for r in observed]
    if len(set(trials)) != len(trials):
        report['reason'] = 'duplicate-trial-identity'
        return report
    ancestors = {}
    for job in jobs:
        ancestors[job['id']] = set(edges[job['id']])
        for dependency in edges[job['id']]:
            ancestors[job['id']].update(ancestors[dependency])
    if not any(a['id'] not in ancestors[b['id']] and b['id'] not in ancestors[a['id']]
               for i, a in enumerate(jobs) for b in jobs[i+1:]):
        report['reason'] = 'dependency-or-scope-bound'
        return report
    # A fixed latest window retains failures, never cherry-picks fast successes.
    by_mode = {mode: sorted([r for r in rows if r.get('mode') == mode], key=lambda r: r['started'])[-3:]
               for mode in ('inline', 'crew')}
    single = sorted(singles, key=lambda r: r['started'])[-3:]
    if singles and len(single) < 3:
        report['reason'] = 'insufficient-single-worker-baseline'
        return report
    if len(by_mode['crew']) < 3 or not single and len(by_mode['inline']) < 3:
        return report
    if any(not r.get('quality') or any(j['fault'] or j['started'] is None for j in r['jobs'].values())
           for r in (by_mode['crew'] + by_mode['inline'] + single)):
        report['reason'] = 'failure-or-unknown-startup-in-latest-window'
        return report
    def overhead(row):
        return max(0, row['elapsed'] - union_length([(j['dispatch'], j['returned']) for j in row['jobs'].values()]))
    inline, crew = by_mode['inline'], by_mode['crew']
    serial = (sum(min(r['jobs'][j['id']]['returned']-r['jobs'][j['id']]['dispatch'] for r in inline) for j in jobs)
              + min(map(overhead, inline))) if len(inline) >= 3 else math.inf
    serial_worker = sum(min(r['jobs'][j['id']]['returned']-r['jobs'][j['id']]['dispatch'] for r in inline) for j in jobs) if len(inline) >= 3 else math.inf
    basis = 'serial-delegation'
    if single:
        report['single_worker_lower'] = min(r['elapsed'] for r in single)
        if report['single_worker_lower'] <= serial:
            serial = report['single_worker_lower']
            serial_worker = min(r['worker_seconds'] for r in single)
            basis = 'single-worker'
    durations = {j['id']: max(r['jobs'][j['id']]['returned']-r['jobs'][j['id']]['dispatch'] for r in crew) for j in jobs}
    slots, ends = [0.0]*graph['capacity'], {}
    for job in jobs:
        earliest = max([ends[d] for d in edges[job['id']]] or [0])
        slot = min(range(len(slots)), key=slots.__getitem__)
        ends[job['id']] = max(earliest, slots[slot]) + durations[job['id']]
        slots[slot] = ends[job['id']]
    parallel = max(max(ends.values()) + max(map(overhead, crew)), max(r['elapsed'] for r in crew))
    report.update(serial_lower=serial, crew_upper=parallel, budget_fit='yes' if cap is None or serial < cap-time.monotonic() else 'no',
                  serial_basis=basis, serial_worker_seconds_lower=serial_worker,
                  crew_worker_seconds_upper=sum(durations.values()),
                  reason='startup-coordination-or-dependency-cost', uncertainty='observed-range; not a confidence interval')
    if graph['capacity'] > 1 and serial-parallel > max(0.05, serial*0.1):
        if cap is None or parallel < cap-time.monotonic():
            if (basis == 'single-worker' and sum(durations.values()) > serial_worker
                    and (cap is None or serial < cap-time.monotonic())):
                report['reason'] = 'latency-gain-with-worker-cost-tradeoff'
            else:
                reason = 'only-observed-deadline-fit' if cap is not None and serial >= cap-time.monotonic() else 'observed-latency-benefit'
                report.update(choice='crew', reason=reason, budget_fit='yes')
    if report['choice'] == 'serial' and cap is not None and serial >= cap-time.monotonic():
        report.update(choice='stop', reason='insufficient-measured-budget', budget_fit='no')
    return report


def plan(project, graph_path, history=None, policy_state=None):
    graph, _, _ = load_graph(graph_path)
    policy = routing(project, graph, policy_state)
    report = _plan(project, graph_path, history, policy)
    if policy is not None:
        report['policy'] = policy
        if report['choice'] != 'stop' and policy['decision']['choice'] == 'serial':
            report.update(choice='serial', reason='qualified-routing-policy')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('begin', 'event', 'validate', 'stage', 'finish', 'plan'))
    parser.add_argument('--project', default='.')
    parser.add_argument('--graph')
    parser.add_argument('--wave')
    parser.add_argument('--mode', choices=('inline', 'crew'))
    parser.add_argument('--trial')
    parser.add_argument('--task')
    parser.add_argument('--event')
    parser.add_argument('--result', type=int)
    parser.add_argument('--note')
    parser.add_argument('--stage')
    parser.add_argument('--phase', choices=('begin', 'end', 'skip'))
    parser.add_argument('--history')
    parser.add_argument('--policy-state')
    parser.add_argument('--retry-note')
    args = parser.parse_args()
    if args.action == 'begin':
        print(begin(args.project, args.graph, args.mode, args.trial, args.policy_state, args.retry_note))
    elif args.action == 'plan':
        print(json.dumps(plan(args.project, args.graph, args.history, args.policy_state), sort_keys=True))
    else:
        wave = Wave(args.project, args.wave)
        if args.action == 'event':
            wave.event(args.task, args.event, args.result, args.note)
        elif args.action == 'validate':
            return wave.validate(args.task)
        elif args.action == 'stage':
            wave.stage(args.stage, args.phase)
        elif args.action == 'finish':
            print(json.dumps(wave.finish(), sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, store.StoreError, subprocess.SubprocessError) as exc:
        print('CREW: ERROR %s' % exc, file=sys.stderr)
        sys.exit(4)
