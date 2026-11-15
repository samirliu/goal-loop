#!/usr/bin/env python3
"""Bound recursive execution-policy improvement to one existing goal run.

The host agent writes candidates. goal_evolve remains the experiment/selection
authority; its reports and existing runtime spans supply history and usage.
This module never rewrites the installed skill, grader or goal acceptance.
"""
import argparse
import contextlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location('improve_'+name, HERE/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


crew, trace = module('goal_crew'), module('goal_trace')
host = module('goal_host')
engine, budget = crew.evolution(), crew.budget
require = crew.require
CAMPAIGN = 'improvement-campaign.json'
CONFIG = '.goal/proposals/improvement.json'
ALLOCATION = '.goal/evidence/improvement-allocation.json'


def path(root, name, *, proposals=False, exists=True):
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and all(p not in ('', '.', '..') for p in name.split('/')) and '\\' not in name,
            'improvement paths must be project-relative')
    target = root
    for part in name.split('/'):
        target = target/part
        require(not target.is_symlink(), 'symlink improvement path refused')
    if proposals:
        require(len(Path(name).parts) > 2 and Path(name).parts[:2] == ('.goal', 'proposals'),
                'improvement state/protocol must be under .goal/proposals')
    if exists:
        require(target.exists(), 'missing improvement input: '+name)
    return target


def config(root, inputs=True):
    source = path(root, CONFIG)
    value = json.loads(source.read_bytes())
    fields = {'version', 'scope', 'consumer', 'state', 'protocol', 'max_attempts', 'reserve_fraction',
              'intent', 'trigger', 'hypothesis'}
    require(isinstance(value, dict) and set(value) == fields and type(value['version']) is int
            and value['version'] == 1, 'invalid improvement declaration')
    require(value['consumer'] in ('tool', 'routing', 'proposer') and (not inputs or value['intent'] in ('improve', 'monitor')),
            'invalid improvement consumer/intent')
    require(type(value['max_attempts']) is int and 1 <= value['max_attempts'] <= 100,
            'max_attempts must be between 1 and 100')
    require(type(value['reserve_fraction']) in (int, float) and math.isfinite(value['reserve_fraction'])
            and 0 < value['reserve_fraction'] < 1, 'reserve_fraction must be between zero and one')
    require(all(isinstance(value[k], str) and value[k].strip() for k in (('scope', 'hypothesis') if inputs else ('scope',))),
            'scope and hypothesis require actual observations')
    state = path(root, value['state'], proposals=True, exists=False)
    if not inputs:
        return value, state, None
    protocol = path(root, value['protocol'], proposals=True)
    require(not protocol.is_relative_to(state), 'keep experiment inputs outside the policy state directory')
    trigger = value['trigger']
    require(isinstance(trigger, dict) and set(trigger) == {'artifact', 'sha256', 'observation'}
            and isinstance(trigger['observation'], str) and trigger['observation'].strip(), 'invalid improvement trigger')
    evidence = path(root, trigger['artifact'])
    require(evidence.is_file() and engine.digest(evidence.read_bytes()) == trigger['sha256'],
            'improvement trigger evidence changed')
    return value, state, protocol


def binding(root, ledger_fd=None):
    with crew.read_ledger(root, ledger_fd=ledger_fd) as (state, _):
        require((state/'runner.json').is_file(), 'improvement requires an existing bounded host run')
        runner = budget.runner_data((state/'runner.json').read_bytes())
        sessions = [host.load(p) for p in sorted((state/'evidence/host').glob('session-*.json'))]
        require(any(r.get('active') and r.get('run') == runner['run'] and r.get('project') == str(root) for r in sessions),
                'goal host session ended or missing; no recursive work')
        cap, expired = budget.gate_limit(state, settlement=False)
        require(cap is not None, 'improvement requires an existing deadline')
        value = dict(project=str(root), run=runner['run'], boot=budget.boot_identity(),
            contract=engine.digest((state/'goal.md').read_bytes()),
            checks=engine.digest((state/'check_freeze').read_bytes()),
            kernel={p.name:engine.digest(p.read_bytes()) for p in sorted(HERE.iterdir())
                    if p.is_file() and p.suffix in ('.py', '.sh', '.awk')})
    return value, cap, expired


def oracle(protocol, programs, phases):
    return dict(version=protocol['version'], grader=engine.digest(engine.program_bytes(programs['grader'])),
        entry=protocol.get('entry'),
        calibration=engine.digest(engine.encode([(kind, index, engine.digest(output), engine.digest(expected))
                                               for kind, index, output, expected in phases['calibration']])),
        minimum_cost_gain=protocol['minimum_cost_gain'], quality_tolerance=protocol['quality_tolerance'])


def declaration(value):
    return {k:value[k] for k in ('scope', 'consumer', 'state', 'max_attempts', 'reserve_fraction')}


def campaign(state):
    record = json.loads(engine.optional_bytes(state/CAMPAIGN))
    require(isinstance(record, dict) and set(record) == {'payload', 'sha256'}
            and engine.digest(engine.encode(record['payload'])) == record['sha256'], 'improvement campaign checksum mismatch')
    return record['payload'], record['sha256']


def allocation(root, state, identity=None):
    source = path(root, ALLOCATION, exists=False)
    if not source.exists():
        return None
    row = json.loads(engine.optional_bytes(source))
    require(isinstance(row, dict) and set(row) == {'payload', 'sha256'}
            and row['sha256'] == engine.digest(engine.encode(row['payload'])), 'improvement allocation checksum mismatch')
    require(row['payload']['state'] == str(state.relative_to(root))
            and (identity is None or row['payload']['campaign'] == identity),
            'goal improvement allocation is fixed; do not fork state to reset attempts or testing history')
    return row['payload']


def reports(state, record, identity, ignore=None):
    found = []
    for run, checksum in record['ancestors'].items():
        require(engine.digest(engine.optional_bytes(state/run/'report.json') or b'') == checksum,
                'ancestor experiment report changed or missing')
    for source in sorted(state.glob('*/report.json')):
        run = source.parent.name
        require(engine.hash_identity(run, 32), 'unknown improvement run directory')
        if run == ignore:
            continue
        raw = source.read_bytes()
        if run in record['ancestors']:
            continue
        report = json.loads(raw)
        require(report.get('run') == run and report.get('improvement', {}).get('campaign') == identity,
                'policy state contains an unattributed experiment; retain its evidence and inspect before continuing')
        found.append(report)
    found.sort(key=lambda r:r['improvement']['attempt'])
    require([r['improvement']['attempt'] for r in found] == list(range(1, len(found)+1)),
            'improvement attempt history is not contiguous')
    return found


def uses(root, state, selected):
    if not selected or not selected['policy']:
        return []
    prefix = ['improvement-consume', str(state.relative_to(root)), selected['policy'], selected.get('qualification')]
    found = [r['id'] for r in trace.records(root) if r['label'] == 'improvement-consume'
            and r['state'] == 'complete' and r['result'] == 0 and r['command'][:4] == prefix
            and r['contract_sha256'] == trace.file_hash(root/'.goal/goal.md')]
    for source in sorted((root/'.goal/evidence/crew').glob('*.json')):
        wave = crew.load(source)
        policy = wave.get('policy') or {}
        if (policy.get('state') == str(state) and policy.get('selection') == selected
                and wave['finished'] is not None and wave['quality']
                and any(j['adopted'] is not None for j in wave['jobs'].values())):
            found.append('crew:'+wave['id'])
    return found


def depths(record, history):
    result = {record['baseline']:0}
    for report in history:
        meta = report['improvement']
        if report['status'] == 'enabled' and meta['intent'] == 'improve':
            result[report['policies']['candidate']] = meta['candidate_depth']
    return result


def initialize(project):
    root = Path(project).resolve(strict=True)
    value, state, protocol_path = config(root)
    bound, cap, expired = binding(root)
    require(not expired and cap > time.monotonic(), 'time-budget-exhausted; no improvement')
    protocol, programs, phases, _, _ = engine.load_protocol(protocol_path, root)
    state.mkdir(parents=True, exist_ok=True)
    # One allocation receipt fixes this goal's experiment state. It does not
    # grant acceptance or duplicate the engine's trial/selection ledger.
    allocation_fd = os.open(root/'.goal/evidence', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        crew.store.fcntl.flock(allocation_fd, crew.store.fcntl.LOCK_EX | crew.store.fcntl.LOCK_NB)
        fd = engine.policy_lock(state, True)
    except BaseException:
        os.close(allocation_fd)
        raise
    try:
        engine.require_settled(state)
        allocation(root, state)
        if (state/CAMPAIGN).exists():
            existing, _ = campaign(state)
            require(existing['binding'] == bound and existing['declaration'] == declaration(value),
                    'improvement campaign is immutable; do not renew its attempts or budget')
            record = existing
        else:
            selected = engine.qualified_policy(state)
            baseline = engine.digest(engine.program_bytes(programs['baseline']))
            require(selected is None or selected['policy'] in (None, baseline),
                    'start improvement from the actual currently enabled archive')
            now = time.monotonic()
            record = dict(version=1, binding=bound, declaration=declaration(value), baseline=baseline,
                oracle=oracle(protocol, programs, phases), cutoff=now+(cap-now)*(1-value['reserve_fraction']),
                ancestors={p.parent.name:engine.digest(p.read_bytes()) for p in state.glob('*/report.json')})
            engine.atomic(state/CAMPAIGN, dict(payload=record, sha256=engine.digest(engine.encode(record))))
        identity = engine.digest(engine.encode(record))
        if allocation(root, state, identity) is None:
            row = dict(state=value['state'], campaign=identity, run=record['binding']['run'])
            engine.atomic(root/ALLOCATION, dict(payload=row, sha256=engine.digest(engine.encode(row))))
        return record
    finally:
        os.close(fd)
        os.close(allocation_fd)


def inspect(project, ignore=None, inputs=True, ledger_fd=None):
    root = Path(project).resolve(strict=True)
    value, state, protocol_path = config(root, inputs)
    bound, cap, expired = binding(root, ledger_fd)
    record, identity = campaign(state)
    require(allocation(root, state, identity) is not None, 'start the improvement allocation before evaluation')
    require(record['binding'] == bound and record['declaration'] == declaration(value),
            'goal, kernel or immutable improvement declaration changed')
    history = reports(state, record, identity, ignore)
    selected = engine.qualified_policy(state)
    cutoff = min(cap, record['cutoff'], engine.run_deadline(cap))
    return root, value, state, protocol_path, record, identity, history, selected, cutoff, expired


@contextlib.contextmanager
def deadline(end):
    previous = os.environ.get('GOAL_RUNNER_MONOTONIC_END')
    os.environ['GOAL_RUNNER_MONOTONIC_END'] = str(engine.run_deadline(end))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('GOAL_RUNNER_MONOTONIC_END', None)
        else:
            os.environ['GOAL_RUNNER_MONOTONIC_END'] = previous


def evaluate(project):
    root = Path(project).resolve(strict=True)
    value, state, protocol_path = config(root)
    record, identity = campaign(state)

    def guard(locked_state, current, protocol, programs, run):
        _, actual, target, source, frozen, fingerprint, history, selected, cutoff, expired = inspect(root, run)
        require(target == locked_state.resolve() and source == protocol_path and actual == value
                and fingerprint == identity and frozen == record and current == selected,
                'improvement proposal/parent changed; regenerate context')
        if run is None:
            require(not expired and time.monotonic() < cutoff, 'improvement reserve reached; finish the original goal')
        require(len(history) < record['declaration']['max_attempts'], 'improvement attempt limit reached')
        _, _, phases, _, _ = engine.load_protocol(protocol_path, root)
        require(oracle(protocol, programs, phases) == record['oracle'],
                'improvement cannot change the grader, calibration or success thresholds')
        baseline, candidate = [engine.digest(engine.program_bytes(programs[k])) for k in ('baseline', 'candidate')]
        parent = selected['policy'] if selected else None
        known_depths = depths(record, history)
        if actual['intent'] == 'monitor':
            require(selected and candidate == parent, 'monitor must test the actual active candidate')
            _, qualified = engine.qualified_policy(state, selected, with_report=True)
            require(baseline == qualified['policies']['baseline'], 'monitor must retain the qualified fallback')
        else:
            require(baseline == (parent or record['baseline']), 'next generation must descend from the active archive')
            require(not history or not parent or parent == record['baseline'] or uses(root, state, selected),
                    'consume the qualified parent on actual work before proposing its next generation')
        return dict(campaign=identity, attempt=len(history)+1, intent=actual['intent'],
            parent=selected, candidate_depth=known_depths.get(baseline, 0)+1,
            trigger=actual['trigger'], hypothesis=actual['hypothesis'], consumer=actual['consumer'])

    _, _, _, _, _, _, _, _, cutoff, expired = inspect(root)
    require(not expired and time.monotonic() < cutoff, 'improvement reserve reached; finish the original goal')
    with deadline(cutoff):
        return engine.experiment(protocol_path, state, root, proposal_guard=guard)


def consume(project, seconds, data, validator=None, expected=None):
    require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0, 'invalid consumption budget')
    root = Path(project).resolve(strict=True)
    _, state, _ = config(root, inputs=False)
    fd = engine.policy_lock(state, False)
    try:
        engine.require_settled(state)
        _, _, _, _, _, _, _, selected, _, _ = inspect(root, inputs=False)
        require(expected is None or selected == expected, 'selected policy changed; regenerate the parent input')
        _, cap, expired = binding(root)
        require(not expired and time.monotonic() < cap and selected and selected['policy'],
                'no remaining goal allowance or qualified policy')
        command = ['improvement-consume', str(state.relative_to(root)), selected['policy'],
                   selected['qualification'], engine.digest(data)]
        span = trace.Trace(root, 'command', 'improvement-consume', command)
        with deadline(cap):
            output, rc, reason, error = engine.run_enabled(state, seconds, data)
        span.data['artifact'] = engine.digest(output)
        if rc == 0 and reason is None and validator is not None:
            try:
                validator(output)
            except (ValueError, TypeError, KeyError):
                span.finish(4)
                raise
        span.finish(rc if rc is not None else 4)
        return output, rc, reason, error
    finally:
        os.close(fd)


def suggest(project):
    """Let the qualified proposer operate on its own source and real feedback.

    Output is a candidate proposal for host review, never a direct file edit.
    Neither fresh holdout gold nor a model client enters this interface.
    """
    root = Path(project).resolve(strict=True)
    _, value, state, _, record, _, history, selected, cutoff, expired = inspect(root, inputs=False)
    require(value['consumer'] == 'proposer' and selected and selected['policy'], 'no qualified proposer selected')
    require(not expired and time.monotonic() < cutoff and len(history) < record['declaration']['max_attempts'],
            'improvement reserve or attempt limit reached; finish the original goal')
    request = dict(version=1, scope=value['scope'], goal=(root/'.goal/goal.md').read_text(), parent=selected,
        parent_program=engine.material_path(state, selected['program']).read_text(),
        feedback=engine.feedback(state, history[-1]['run']) if history else None)
    def validate(output):
        proposal = json.loads(output)
        require(isinstance(proposal, dict) and set(proposal) == {'hypothesis', 'files'}
                and isinstance(proposal['hypothesis'], str) and proposal['hypothesis'].strip(), 'invalid proposer hypothesis')
        files = proposal['files']
        require(isinstance(files, dict) and files and all(crew.safe_file(k) and (v is None or isinstance(v, str))
                                                       for k, v in files.items()), 'invalid proposer file scope')
    with deadline(cutoff):
        output, rc, reason, error = consume(root, 2, engine.encode(request), validator=validate, expected=selected)
    require(rc == 0 and reason is None, 'qualified proposer failed: '+str(error or reason or rc))
    return dict(parent=selected, proposal=json.loads(output), output_sha256=engine.digest(output),
                next='Host reviews these proposed files in a new experiment directory; preserve the evaluator and supply fresh holdout. Nothing was applied.')


def view(project, ledger_fd=None):
    """Read-only action input; no execution, auto-promotion or extra ledger."""
    root = Path(project).resolve(strict=True)
    if not (root/CONFIG).exists():
        return None, {}
    value, state, _ = config(root, inputs=False)
    allocation(root, state)
    result = dict(scope=value['scope'], consumer=value['consumer'],
        state=str(state), binding=dict(config=engine.digest(engine.encode(value))),
        guidance='The host agent proposes code from actual feedback. Keep the grader and goal fixed; use the active archive as parent, fresh holdout and the same state. A consumed result is not a quality PASS.')
    command = [sys.executable, '-I', str(HERE/'goal_improve.py')]
    if not (state/CAMPAIGN).exists() or not (root/ALLOCATION).exists():
        _, _, protocol_path = config(root)
        _, _, _, _, fingerprint = engine.load_protocol(protocol_path, root, ledger_fd)
        result['binding']['protocol'] = fingerprint
        result['next'] = 'start-improvement'
        return result, {'start-improvement':command+['start', str(root)]}
    fd = engine.policy_lock(state, False)
    try:
        pending = engine.optional_bytes(state/engine.PENDING)
        if pending:
            result.update(next='recover-improvement', pending=True)
            result['binding']['pending'] = engine.digest(pending)
            return result, {'recover-improvement':command+['recover', str(root)]}
        _, _, _, _, record, identity, history, selected, cutoff, expired = inspect(root, inputs=False, ledger_fd=ledger_fd)
        result['binding'].update(campaign=identity, reports=engine.digest(engine.encode(history)), selection=selected,
                                 uses=uses(root, state, selected))
        result.update(attempts=len(history), max_attempts=record['declaration']['max_attempts'],
            cutoff_monotonic=cutoff, selected=selected, actual_uses=result['binding']['uses'],
            generation_depth=depths(record, history).get(selected['policy'], 0) if selected else 0,
            lineage=[dict(run=r['run'], status=r['status'], enabled=r['enabled'], **r['improvement']) for r in history])
        if history:
            result['feedback'] = engine.feedback(state, history[-1]['run'])
        stopped = expired or time.monotonic() >= cutoff or len(history) >= record['declaration']['max_attempts']
        needs_use = value['intent'] == 'improve' and selected and selected['policy'] and selected['policy'] != record['baseline'] and not result['actual_uses']
        result['next'] = 'finish-original-goal' if stopped else 'consume-or-stop' if needs_use else 'propose-and-evaluate'
        commands = {} if stopped or needs_use else {'evaluate-improvement':command+['evaluate', str(root)]}
        _, cap, _ = binding(root, ledger_fd)
        result['consume_command'] = shlex.join(command+['consume', str(root), '--seconds', '2']) if selected and selected['policy'] and not expired and cap > time.monotonic() else None
        result['parent_archive'] = str(state/selected['program']) if selected and selected['policy'] else None
        result['routing_state'] = str(state) if value['consumer'] == 'routing' and selected and selected['policy'] else None
        if value['consumer'] == 'proposer' and selected and selected['policy'] and not stopped:
            commands['suggest-improvement'] = command+['suggest', str(root)]
            if needs_use:
                result['next'] = 'generate-next-proposal'
        try:
            _, _, protocol_path = config(root)
            protocol, programs, phases, _, fingerprint = engine.load_protocol(protocol_path, root, ledger_fd)
            result['binding']['protocol'] = fingerprint
            result['protocol'] = str(protocol_path)
            if not stopped and not needs_use:
                require(oracle(protocol, programs, phases) == record['oracle'],
                        'retain the frozen evaluator and thresholds in the next proposal')
                baseline, candidate = [engine.digest(engine.program_bytes(programs[k])) for k in ('baseline', 'candidate')]
                parent = selected['policy'] if selected else None
                if value['intent'] == 'improve':
                    require(baseline == (parent or record['baseline']), 'prepare the next generation from parent_archive')
                else:
                    require(parent and candidate == parent, 'monitor the actual active archive')
                exposed = set(json.loads(engine.optional_bytes(state/'used-holdout.json') or b'[]'))
                require(not exposed.intersection(case[0] for case in phases['holdout']),
                        'prepare fresh held-out inputs before the next evaluation')
        except (ValueError, OSError, KeyError, TypeError, engine.ExperimentError) as exc:
            result['proposal_error'] = str(exc)
            if not stopped and not needs_use:
                result.update(error=str(exc), next='prepare-next-generation')
            commands.pop('evaluate-improvement', None)
        return result, commands
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('start', 'evaluate', 'consume', 'suggest', 'show', 'recover'))
    parser.add_argument('project')
    parser.add_argument('--seconds', type=float, default=2)
    args = parser.parse_args()
    if args.command == 'consume':
        output, rc, reason, error = consume(args.project, args.seconds, sys.stdin.buffer.read())
        sys.stdout.buffer.write(output)
        if error or reason:
            print(error or reason, file=sys.stderr)
        return 4 if rc is None else rc
    if args.command == 'recover':
        root = Path(args.project).resolve(strict=True)
        _, state, _ = config(root, inputs=False)
        result = engine.recover_policy(state, abort_incomplete=True)
    elif args.command == 'show':
        result = view(args.project)[0]
    elif args.command == 'suggest':
        result = suggest(args.project)
    else:
        result = initialize(args.project) if args.command == 'start' else evaluate(args.project)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, engine.ExperimentError, crew.store.StoreError) as exc:
        print('IMPROVE: ERROR '+str(exc), file=sys.stderr)
        sys.exit(4)
