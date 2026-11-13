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
def access(project, write=False, recovery=False):
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
        pending = (state / 'store/pending').exists()
        crew.require(recovery or not pending, 'recovery-required: run goal_ctl.sh recover --project ' + shlex.quote(str(root)))
        if not pending:
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


def read_input(path):
    """An authored request is input, never a replacement ledger or verdict."""
    crew.require(not path.is_symlink(), 'symlink action input refused')
    return path.read_bytes() if path.exists() else None


def actions(root, revision, commands, auto=False, details=None):
    base = [sys.executable, '-I', str(HERE/'goal_context.py'), 'run', str(root), revision]
    return {name: dict(command=shlex.join(base+[name]+(['--auto'] if auto else [])) if cmd else None,
                       executes=shlex.join(cmd) if cmd else None,
                       parameters=(details or {}).get(name, {}).get('parameters', {'project': str(root)}),
                       missing=(details or {}).get(name, {}).get('missing', []),
                       sources=(details or {}).get(name, {}).get('sources', [str(root/'.goal/state.rec')]))
            for name, cmd in commands.items()}


def close_input(root, state, head, counters, contract, plan):
    path = store._close_path(state, 'proposals/close-iteration.json')
    data = read_input(path)
    known = dict(operation_id='context-i%s-%s' % (int(counters['iteration'])+1, head[:20]),
                 task=None, files=None)
    rows = re.findall(r'^- \[[ x]\] (T[0-9]+)\b[^\n]*?\bfiles[=:] *([^\n]+)', plan, re.M)
    if len(rows) == 1:
        known.update(task=rows[0][0], files=rows[0][1].strip())
    template = dict(known, checks_pass=None, checks_fail=None, checks_unverifiable=None,
                    progress=None, exit_signal=None, adversarial=None, adversarial_note=None)
    objective = re.search(r'^objective: *(maximize|minimize) +(AC-[0-9]+)', contract, re.M)
    if objective:
        template.update(score=None, strategy=None)
    if re.search(r'^exit: *forge', contract, re.M):
        template['dry'] = None
    # Opt-in template: the original close measures these counts itself. Keep
    # the existing template and manual protocol unchanged for all callers.
    criteria = re.findall(r'^- AC-[0-9]+ \|.*?expected: *([^|\n]*)$', contract, re.M)
    measurable = bool(criteria) and not objective and 'dry' not in template and not re.search(r'\bexternal:', contract)
    measurable = measurable and all(re.fullmatch(r'exit=[0-9]+', re.sub(r'\s', '', value)) for value in criteria)
    measured_template = {key: value for key, value in template.items() if not key.startswith('checks_')}
    measured_template.update(checks_source='verify', receipt='yes')
    request = json.loads(data) if data is not None else template
    fields = set(template) | {'score', 'judge_score', 'strategy', 'strategy_delta', 'dry',
                              'error_signature', 'fault', 'fault_outcome', 'fault_note', 'checks_source', 'receipt'}
    crew.require(isinstance(request, dict) and set(request) <= fields, 'unknown close input fields')
    crew.require(request.get('checks_source') in (None, 'verify'), 'invalid close checks_source')
    crew.require(request.get('receipt') in (None, 'yes'), 'invalid close receipt')
    measured = request.get('checks_source') == 'verify'
    crew.require(not measured or measurable, 'measured close needs deterministic exit checks')
    crew.require(not measured or not any(request.get(key) is not None for key in
                     ('checks_pass', 'checks_fail', 'checks_unverifiable')), 'measured close rejects manual counts')
    sources = dict(operation_id='Use this ID for this request and every retry; never replace it after interruption.',
        task=str(state/'work-plan.md')+' or the actual wave task identity',
        files=str(state/'work-plan.md')+' and the actual changed output scope; existence does not prove acceptance',
        checks_pass='Count PASS in the actual named check output from the verify action.',
        checks_fail='Count FAIL/BROKEN in the actual named check output; do not copy work-plan ticks.',
        checks_unverifiable='Actual unresolved judged checks and their PROBE/REASON evidence.',
        progress='Controller judgment from observed artifact/check changes.',
        exit_signal='Controller intent to claim exit; only the original Gate can grant GO.',
        adversarial='Actual second pass against the current artifact: clear or finding; never inferred.',
        adversarial_note='Commands/observations from that second pass.',
        score='Numeric observation from the frozen objective check; controller remeasures it.',
        strategy='The preregistered strategy actually used in this wave.',
        dry='Actual critic receipt and executed frozen probes; never infer dry from checks alone.',
        strategy_delta='Observed reason and changed next approach when progress=no.')
    required = {'operation_id', 'task', 'files', 'checks_pass', 'checks_fail', 'checks_unverifiable', 'progress', 'exit_signal'}
    if measured:
        required -= {'checks_pass', 'checks_fail', 'checks_unverifiable'}
    if request.get('exit_signal') == 'yes':
        required.update(('adversarial', 'adversarial_note'))
    if objective:
        required.update(('score', 'strategy'))
    if 'dry' in template:
        required.add('dry')
    if request.get('progress') == 'no':
        required.add('strategy_delta')
    if request.get('fault') is not None or request.get('fault_outcome') is not None:
        required.update(('fault', 'fault_outcome'))
        sources.update(fault='Actual observed worker failure; references/crew.md fault vocabulary.',
                       fault_outcome='Actual recovery action paired with the observed fault.')
    missing = [dict(name=k, source=sources[k]) for k in sorted(required) if request.get(k) in (None, '')]
    for name, value in request.items():
        if value is None:
            continue
        if name in ('checks_pass', 'checks_fail', 'checks_unverifiable'):
            crew.require(type(value) is int and value >= 0, 'invalid close count: '+name)
        else:
            crew.require(isinstance(value, str) and value and '\0' not in value, 'invalid close input: '+name)
    for name, options in [('progress', ('yes', 'no')), ('exit_signal', ('yes', 'no')),
                          ('dry', ('yes', 'no')), ('adversarial', ('clear', 'finding'))]:
        crew.require(request.get(name) is None or request[name] in options, 'invalid close choice: '+name)
    if request.get('operation_id') is not None:
        crew.require(bool(store._OPERATION.fullmatch(request['operation_id'])), 'invalid close operation_id')
    argv = ['close-iteration', '--project', str(root)]
    # Fixed order is part of the existing exact-argument idempotency protocol.
    for name in ('operation_id', 'task', 'files', 'checks_pass', 'checks_fail', 'checks_unverifiable',
                 'progress', 'exit_signal', 'adversarial', 'adversarial_note', 'score', 'judge_score',
                 'strategy', 'strategy_delta', 'dry', 'error_signature', 'fault', 'fault_outcome', 'fault_note'):
        if request.get(name) is not None:
            argv.extend(('--'+name.replace('_', '-'), str(request[name])))
    if measured:
        argv.append('--checks-from-verify')
    if request.get('receipt') == 'yes':
        argv.append('--receipt')
    if data is None:
        missing.insert(0, dict(name='request_file', source='Write the template to '+str(path)+'; fill required nulls from real evidence, then regenerate context.'))
    return dict(path=str(path), template=template, measured_template=measured_template if measurable else None,
                values=request, missing=missing, sources=sources,
                sha256=store._hash(data) if data is not None else None), argv


def recovery_view(root, state, auto):
    pending = read_input(state/'store/pending')
    envelope = json.loads(pending)
    record = envelope.get('payload')
    crew.require(isinstance(record, dict) and envelope.get('sha256') == store._hash(store._encode(record)), 'corrupt recovery journal')
    if record.get('version') in (1, 2, 3, 6):
        record = store._close_record(state/'store/pending')
    request = read_input(state/'proposals/close-iteration.json')
    binding = dict(head=store.Store(state/'store/commits').read()[0], pending=store._hash(pending),
                   views=store.guard_digest(state), close_input=store._hash(request) if request else None, auto=auto)
    revision = store._hash(store._encode(binding))
    commands = {'recover': ['bash', str(HERE/'goal_ctl.sh'), 'recover', '--project', str(root)]}
    value = dict(version=2, project=str(root), revision=revision, binding=binding, next='recover-ledger',
                 actions=actions(root, revision, commands, auto),
                 recovery=dict(operation_id=record.get('operation'), intent=record.get('intent'),
                               original_arguments=record.get('arguments'),
                               source=str(state/'store/pending'), request_path=str(state/'proposals/close-iteration.json'),
                               next='Recover first, regenerate context, then retry the same request with its original ID and parameters. Recovery never replays checks.'))
    return value, commands


def initial_view(root, auto):
    info = root.stat()
    binding = dict(project=[info.st_dev, info.st_ino], state_exists=False, auto=auto)
    revision = store._hash(store._encode(binding))
    commands = {'init': ['bash', str(HERE/'goal_ctl.sh'), 'init', '--project', str(root),
                         '--operation-id', 'context-init-'+revision[:20]]}
    return dict(version=2, project=str(root), revision=revision, binding=binding,
                next='initialize-ledger', actions=actions(root, revision, commands, auto),
                entry=dict(source='Actual host identity and user wall-clock budget; never guess a session.',
                           missing=['backend', 'session', 'seconds'],
                           next='Use goal_host.py begin with those actual inputs before execution; it also initializes the ledger.')), commands


def execution_view(root, state, head, waves, enabled):
    """Describe existing crew/host entrypoints without running a policy/planner."""
    graph_path = store._close_path(state, 'proposals/crew.json')
    graph_bytes = read_input(graph_path)
    host_files = {str(p.relative_to(state)): store._hash(store._close_path(state, str(p.relative_to(state))).read_bytes())
                  for p in sorted((state/'evidence/host').glob('*.json'))}
    binding = dict(host=host_files)
    commands, details = {}, {}
    if graph_bytes is None:
        return binding, commands, details, None
    graph, _, _ = crew.load_graph(graph_path)
    binding['graph'] = store._hash(store._encode(graph))
    path = store._close_path(state, 'proposals/execution.json')
    data = read_input(path)
    request = json.loads(data) if data else {}
    crew.require(isinstance(request, dict) and set(request) <= {'mode', 'trial', 'policy_state', 'receipts', 'retry_note'}, 'unknown execution input fields')
    receipts = request.get('receipts', {})
    crew.require(isinstance(receipts, dict) and all(isinstance(k, str) and isinstance(v, dict)
                 and set(v) <= {'launch', 'terminal'} and all(isinstance(s, str) and s and '\0' not in s for s in v.values())
                 for k, v in receipts.items()), 'invalid execution receipt paths')
    binding['input'] = store._hash(data) if data else None
    draft = dict(mode=None, trial='context-'+head[:20]+'-w'+str(len(waves)+1), policy_state=None, receipts={})
    description = dict(path=str(path), template=draft,
                       next='Run plan, choose mode from its measured advice, and provide actual host receipt paths when available; regenerate context.')
    if not enabled:
        return binding, commands, details, description
    common = [sys.executable, '-I', str(HERE/'goal_crew.py')]
    args = ['--project', str(root), '--graph', str(graph_path)]
    if request.get('policy_state') is not None:
        policy_path = Path(request['policy_state']).resolve(strict=True)
        crew.require(policy_path.is_relative_to(state/'proposals'), 'policy must be in project proposals')
        engine = crew.evolution()
        lock = engine.policy_lock(policy_path, False)
        try:
            engine.require_settled(policy_path)
            binding['policy'] = engine.enabled_policy(policy_path)
        finally:
            os.close(lock)
        args += ['--policy-state', str(policy_path)]
    commands['plan'] = common+['plan', *args]
    active = sorted([w for w in waves if w['finished'] is None], key=lambda w: w['started'])
    if not active:
        mode, trial = request.get('mode'), request.get('trial', draft['trial'])
        crew.require(mode is None or mode in ('inline', 'crew'), 'invalid execution mode')
        crew.require(isinstance(trial, str) and trial, 'invalid execution trial')
        repeated = any(w['trial'] == trial for w in waves)
        commands['begin-wave'] = common+['begin', *args, '--mode', mode, '--trial', trial] if mode and not repeated else None
        if commands['begin-wave'] and request.get('retry_note'):
            commands['begin-wave'] += ['--retry-note', request['retry_note']]
        details['begin-wave'] = dict(parameters=dict(graph=str(graph_path), mode=mode, trial=trial),
            missing=([dict(name='mode', source='plan output and controller judgment; write '+str(path))] if not mode else [])+
                    ([dict(name='trial', source='This trial already exists; use the new template for a new wave, or resume the recorded wave.')] if repeated else []), sources=[str(graph_path), str(path)])
        return binding, commands, details, description
    crew.require(len(active) == 1, 'multiple active waves; inspect actual host terminals before choosing another action')
    wave = active[0]
    # Load checksummed host receipts with the existing adapter's reader.
    spec = importlib.util.spec_from_file_location('context_host', HERE/'goal_host.py')
    host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
    folder = state/'evidence/host'
    sessions = [host.load(p) for p in sorted(folder.glob('session-*.json'))]
    sessions = [s for s in sessions if s.get('active') and s.get('project') == str(root)]
    attempts = [host.load(p) for p in sorted(folder.glob('attempt-*.json'))]
    host_command = [sys.executable, '-I', str(HERE/'goal_host.py')]
    for task, row in wave['jobs'].items():
        if row.get('reused_from') or row.get('adopted') is not None:
            continue
        found = [r for r in attempts if r['wave'] == wave['id'] and r['task'] == task]
        if not found:
            ready = row['dispatch'] is None and all(wave['jobs'][d]['adopted'] is not None for d in wave['edges'][task])
            capacity = 1 if wave['mode'] == 'inline' else wave['graph']['capacity']
            ready &= sum(r['dispatch'] is not None and r['returned'] is None for r in wave['jobs'].values()) < capacity
            if ready:
                commands['prepare-'+task] = host_command+['prepare', str(root), wave['id'], task, '--session', sessions[0]['session']] if len(sessions) == 1 else None
                details['prepare-'+task] = dict(parameters=dict(wave=wave['id'], task=task), sources=[str(folder)],
                    missing=[] if len(sessions) == 1 else [dict(name='host_session', source='Bind actual host identity with goal_host.py begin; do not guess a session.')])
            continue
        crew.require(len(found) == 1, 'ambiguous host attempt')
        attempt = found[0]; ticket = attempt['id']+':'+attempt['nonce']
        phase = attempt['phase']
        if phase == 'returned':
            commands['validate-'+task] = host_command+['validate', str(root), ticket]
            if row['validations'] and row['validations'][-1]['result'] == 0:
                commands['adopt-'+task] = host_command+['adopt', str(root), ticket]
        else:
            name = 'attach-'+task if attempt.get('agent_id') is None else 'reconcile-'+task
            kind = 'launch' if name.startswith('attach') else 'terminal'
            receipt = request.get('receipts', {}).get(task, {}).get(kind)
            if receipt:
                source = Path(receipt).resolve(strict=True)
                binding[name] = store._hash(read_input(source))
                commands[name] = host_command+(['attach', str(root), ticket, str(source)] if kind == 'launch' else ['reconcile', str(root), str(source), '--session', attempt['session'], '--backend', attempt['backend']])
            else:
                commands[name] = None
            details[name] = dict(parameters=dict(wave=wave['id'], task=task, ticket=ticket), sources=[str(folder), str(path)],
                                 missing=[] if receipt else [dict(name=kind+'_receipt', source='Actual native host '+kind+' tool result; set receipts.'+task+'.'+kind+' in '+str(path))])
    if all(r['returned'] is not None for r in wave['jobs'].values()):
        commands['finish-wave'] = common+['finish', '--project', str(root), '--wave', wave['id']]
    return binding, commands, details, description


def compile_view(root, state, fd, auto=False):
    if (state/'store/pending').exists():
        return recovery_view(root, state, auto)
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
    settlement_cap = budget.gate_limit(state, settlement=True)[0] if expired else cap
    if authored:
        digest = protected(root, ['bash', str(HERE / 'goal_gate.sh'), '--digest', '--project', str(root)], settlement_cap, fd)
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
    close, close_argv = close_input(root, state, head, counters, contract, plan)
    binding['close_input'] = close['sha256']
    binding['evidence'] = store.guard_digest(state)
    binding['crew'] = store._hash(store._encode(waves))
    blocks = re.split(r'^## iteration\b', log, flags=re.M)
    claimed = len(blocks) > 1 and re.search(r'^exit_signal=yes\s*$', blocks[-1], re.M) is not None
    ticked = any(s.startswith('- [x]') for s in plan.splitlines())
    unbooked = (len(blocks) == 1 and ticked) or any(w['finished'] is not None and
        (w.get('book_iteration') == int(counters['iteration']) or len(blocks) == 1) for w in waves)
    execution, exec_commands, exec_details, exec_input = execution_view(root, state, head, waves,
        stamped and not expired and not claimed and not unbooked)
    binding['execution'] = execution
    binding['implementation'] = {name: store._hash((HERE/name).read_bytes()) for name in
        ('goal_context.py', 'goal_ctl.sh', 'goal_gate.sh', 'goal_parse.sh', 'goal_store.py', 'goal_runner.py', 'goal_crew.py', 'goal_host.py')}
    revision = store._hash(store._encode(binding))
    commands = {'status': ['bash', str(HERE / 'goal_ctl.sh'), 'status', '--project', str(root)],
                'audit': ['bash', str(HERE / 'goal_audit.sh'), '--project', str(root)],
                'gate': ['bash', str(HERE / 'goal_gate.sh'), '--check', '--project', str(root)]}
    details = {name: dict(parameters={'project': str(root)}, sources=[str(state/'goal.md'), str(state/'state.rec')]) for name in commands}
    if authored:
        commands['verify'] = ['bash', str(HERE/'goal_gate.sh'), '--verify', '--project', str(root)]
    if not stamped and authored and not expired:
        commands['stamp'] = ['bash', str(HERE / 'goal_ctl.sh'), 'stamp', '--project', str(root)] + (['--auto'] if auto else [])
    if expired or not authored:
        commands = {'status': commands['status']}
    objective = re.search(r'^## (?:Goal|Objective)[^\n]*\n+([^#<][^\n]*)', contract, re.M)
    next_step = ('settle-or-stop' if expired else 'author-contract-and-smoke' if not stamped else
                 'close-unbooked-wave' if unbooked else
                 'verify-gate-and-deliver' if claimed else
                 'review-and-close-iteration' if len(blocks) > 1 else 'implement-or-dispatch')
    if stamped:
        commands['receipt'] = [sys.executable, '-I', str(HERE/'goal_context.py'), 'receipt', str(root)]
        # A complete request may be historical after a lost acknowledgement.
        # The original controller decides REPLAY and never books it twice.
        commands['close'] = ['bash', str(HERE/'goal_ctl.sh'), *close_argv] if not close['missing'] else None
        details['close'] = dict(parameters=close['values'], missing=close['missing'], sources=[close['path'], str(state/'work-plan.md')])
        if not close['missing']:
            op, intent = store._close_request(close_argv)
            prior = store._close_committed(state, op, intent)
            if prior is not None:
                details['close']['parameters'] = dict(close['values'], historical_result=prior[0]['result'])
        if claimed:
            # Do not suggest another close/work wave after an exit declaration.
            commands.pop('close', None)
        _, snapshot = store.Store(state/'store/commits').read()
        if store._CLOSE_META in snapshot:
            meta = json.loads(snapshot[store._CLOSE_META])
            if meta.get('version') == 2:
                store._close_committed(state, meta['operation'], meta['intent'])
                commands['retry-close'] = ['bash', str(HERE/'goal_ctl.sh'), *meta['arguments']]
                details['retry-close'] = dict(parameters=dict(operation_id=meta['operation'], intent=meta['intent'],
                    original_arguments=meta['arguments'], historical_result=meta['result']),
                    sources=[str(state/'store/commits')], missing=[])
    commands.update(exec_commands)
    details.update(exec_details)
    if not expired:
        if not stamped:
            commands = {k: v for k, v in commands.items() if k in ('status', 'verify', 'stamp')}
        elif claimed:
            commands = {k: v for k, v in commands.items() if k in ('status', 'receipt', 'retry-close')}
        else:
            commands.pop('gate', None)
            commands.pop('receipt', None)
    value = dict(version=2, project=str(root), revision=revision, binding=binding,
                 goal=objective[1].strip() if objective else (contract.splitlines() or ['Goal contract not authored'])[0], stamped=stamped,
                 iteration=counters.get('iteration'), breaker=counters.get('breaker'),
                 deadline_epoch=None if cap is None else time.time()+cap-time.monotonic(), deadline_monotonic=cap,
                 budget_scope=runner['scope'] if runner else 'contract-only',
                 remaining_seconds=None if cap is None else max(0, cap-time.monotonic()),
                 expired=expired, accepted=[s for s in plan.splitlines() if s.startswith('- [x]')],
                 read_deadline=settlement_cap,
                 pending=[s for s in plan.splitlines() if s.startswith('- [ ]')],
                 accepted_units=[u for u in units.values() if u['accepted']],
                 repair_units=[u for u in units.values() if not u['accepted']], policies=policies,
                 unknown=['work-plan ticks are not acceptance; only a fresh gate decides GO'],
                 next=next_step,
                 actions=actions(root, revision, commands, auto, details),
                 settle_command=actions(root, revision, {'receipt': commands['receipt']}, auto)['receipt']['command'] if 'receipt' in commands else None,
                 evidence=dict(contract=str(state/'goal.md'), ledger=str(state/'store/commits'),
                               log=str(state/'loop-log.md'), host=str(state/'evidence/host')))
    if stamped and not claimed:
        value['close_input'] = {k: v for k, v in close.items() if k != 'values' or close['sha256'] is not None}
        value['implementation'] = dict(tasks=value['pending'], source=str(state/'work-plan.md'),
            judgment='Implement the named scope using host tools; run verify, review the artifact, then fill close_input. Ticks and worker reports never supply check counts.')
    if exec_input:
        value['execution_input'] = exec_input
    if not authored and not expired:
        value['author_contract'] = dict(path=str(contract_path), already_initialized=True,
            next='Write this small contract, run its named check as a smoke test, then regenerate context; do not re-init or inspect implementation files for syntax.',
            template='# Goal\n\n## Objective\n\n<outcome>\n\n## Acceptance criteria\n\n'
                     '- AC-1 | <yes/no statement> | check: `<command>` | expected: exit=0\n\n'
                     '## Approval\n\napproved: PENDING\n')
    return value, commands


def show(project, auto=False):
    root = Path(project).resolve(strict=True)
    if not (root/'.goal').exists():
        return initial_view(root, auto)[0]
    with access(project, recovery=True) as (root, state, fd):
        value, _ = compile_view(root, state, fd, auto)
        return value


def brief_view(value):
    """Presentation only: run always recompiles the complete binding under lock."""
    result = {k: v for k, v in value.items() if k != 'binding'}
    if 'close_input' in result:
        # Missing fields already carry their evidence source. Keep the exact
        # submitted values visible, including after an interrupted request.
        result['close_input'] = {k: v for k, v in result['close_input'].items()
                                 if k != 'sources'}
    return result


def run(project, revision, action, auto=False):
    # The lock is retained across exec, so a cooperating ledger writer cannot
    # change the validated revision before the existing command consumes it.
    if action == 'init':
        root = Path(project).resolve(strict=True)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            store.fcntl.flock(fd, store.fcntl.LOCK_EX | store.fcntl.LOCK_NB)
            crew.require(not (root/'.goal').exists(), 'stale-context: ledger already initialized')
            value, commands = initial_view(root, auto)
            crew.require(value['revision'] == revision, 'stale-context: regenerate context')
            os.execvp(commands[action][0], commands[action])
        finally:
            os.close(fd)
    with access(project, write=action in ('stamp', 'gate', 'verify', 'close', 'retry-close', 'receipt', 'recover'), recovery=action == 'recover') as (root, state, fd):
        value, commands = compile_view(root, state, fd, auto)
        crew.require(value['revision'] == revision, 'stale-context: regenerate goal_ctl.sh context')
        if action != 'recover':
            _, expired_now = budget.gate_limit(state, settlement=False)
            value['expired'] = value.get('expired', False) or expired_now
        crew.require(action in commands and commands[action] is not None and (not value.get('expired') or action in ('status', 'close', 'retry-close', 'receipt')),
                     'action unavailable; settle with goal_context.py receipt')
        os.set_inheritable(fd, True)
        env = dict(os.environ, GOAL_ACCESS_FD=str(fd), GOAL_ACCESS_OWNER_PID=str(os.getpid()),
                   GOAL_ACCESS_EXEC_PID=str(os.getpid()), GOAL_ACCESS_MODE='write' if action in ('stamp', 'close', 'retry-close', 'receipt', 'recover') else
                   'exclusive-read' if action in ('gate', 'verify') else 'read')
        # Preserve any actual inherited deadline. The map's bounded read is
        # not a new aggregate close budget: the original controller owns its
        # existing raw-verification and acceptance envelopes independently.
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
    parser.add_argument('--brief', action='store_true', help='show: omit internal binding hashes and repeated close fields')
    args = parser.parse_args()
    if args.brief and args.action != 'show':
        parser.error('--brief is only valid for show')
    if args.action == 'run':
        run(args.project, args.revision, args.operation, args.auto)
    result = show(args.project, args.auto) if args.action == 'show' else receipt(args.project)
    if args.brief:
        result = brief_view(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if args.action == 'show' or result['completion_verified'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, store.StoreError, subprocess.SubprocessError) as exc:
        print('CONTEXT: ERROR ' + str(exc), file=sys.stderr)
        sys.exit(4)
