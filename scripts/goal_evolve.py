#!/usr/bin/env python3
"""Run a frozen, paired Python-policy experiment and activate/withdraw locally.

This is an opt-in cost experiment, not a sandbox or a generalization claim.
Workers receive task input; only the separately launched grader receives gold.
"""
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import uuid


class ExperimentError(RuntimeError):
    pass


class Bundle:
    """Runnable owned files from a matched pair of artifact checkpoints."""
    def __init__(self, entry, files, context, snapshot=None):
        self.entry = entry
        self.files = files
        self.context = context
        self.snapshot = snapshot

    def archive(self):
        return encode({'entry': self.entry, 'files': self.files, 'context': self.context})


def checkpoint_programs(protocol, project):
    if project is None:
        raise ExperimentError('version 2 requires --project')
    spec = importlib.util.spec_from_file_location('goal_store', Path(__file__).with_name('goal_store.py'))
    store = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(store)
    state = Path(project).resolve(strict=True) / '.goal'
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if (state / 'store/pending').exists():
            raise ExperimentError('checkpoint project requires recovery')
        store.verify_views(state)
        best, trial = store._incumbent_pair(state, protocol['baseline'], protocol['candidate'])
    except store.StoreError as exc:
        raise ExperimentError(str(exc)) from exc
    finally:
        os.close(fd)
    entry = protocol['entry']
    if (not isinstance(entry, str) or not entry.endswith('.py')
            or any(record['files'].get(entry) is None for record in (best, trial))):
        raise ExperimentError('entry must be an owned Python file in both checkpoints')
    return {side: Bundle(entry, record['files'], record['context'], encode(record))
            for side, record in (('baseline', best), ('candidate', trial))}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_bytes(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.evolve-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic(path, value):
    atomic_bytes(path, encode(value))


PENDING = 'policy-pending.json'


def optional_bytes(path):
    if path.is_symlink():
        raise ExperimentError('symlink policy state refused')
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def policy_lock(state, exclusive):
    descriptor = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def require_settled(state):
    if os.path.lexists(state / PENDING):
        raise ExperimentError('policy-recovery-required: run goal_evolve.py recover --state ' + str(state))


def blob(data):
    return None if data is None else base64.b64encode(data).decode('ascii')


def unblob(value):
    if value is not None and not isinstance(value, str):
        raise ExperimentError('invalid policy transition bytes')
    return None if value is None else base64.b64decode(value, validate=True)


def hash_identity(value, size=64):
    return isinstance(value, str) and len(value) == size and all(c in '0123456789abcdef' for c in value)


def pending_policy(state):
    envelope = json.loads(optional_bytes(state / PENDING))
    if (not isinstance(envelope, dict) or set(envelope) != {'payload', 'sha256'}
            or envelope['sha256'] != digest(encode(envelope['payload']))):
        raise ExperimentError('policy transition checksum mismatch')
    value = envelope['payload']
    fields = {'version', 'phase', 'run', 'before', 'report', 'materials'}
    if isinstance(value, dict) and value.get('phase') == 'transition':
        fields.update({'after', 'report_before'})
    if (not isinstance(value, dict) or set(value) != fields or type(value['version']) is not int
            or value['version'] != 1 or value['phase'] not in ('evaluating', 'transition')
            or not hash_identity(value['run'], 32)):
        raise ExperimentError('invalid policy transition')
    unblob(value['before'])
    report = value['report']
    if (not isinstance(report, dict) or report.get('run') != value['run']
            or not hash_identity(report.get('protocol')) or not isinstance(value['materials'], dict)
            or 'protocol.json' not in value['materials']):
        raise ExperimentError('invalid policy transition report')
    if value['phase'] == 'transition':
        unblob(value['after']); unblob(value['report_before'])
    return value


def publish_pending(state, value):
    atomic(state / PENDING, {'payload': value, 'sha256': digest(encode(value))})


def transition_fault(stage):
    if os.environ.get('GOAL_EVOLVE_FAULT') == stage:
        os._exit(91)


def material_path(run, name):
    if (not isinstance(name, str) or '\\' in name or '\0' in name
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ExperimentError('invalid policy transition material path')
    path = run
    for part in name.split('/'):
        path = path / part
        if path.is_symlink():
            raise ExperimentError('symlink policy transition material refused')
    return path


def finish_policy_transition(state, pending):
    """Roll a qualified decision forward; never execute a policy or grader."""
    if pending['phase'] != 'transition':
        raise ExperimentError('unfinished-policy-evaluation: no qualified transition; '
                              'use recover --abort-incomplete to quarantine without replay')
    before, after = unblob(pending['before']), unblob(pending['after'])
    previous = policy_record(state, before)
    selected = policy_record(state, after)
    report = pending['report']
    if (report.get('enabled') != (selected['policy'] if selected else None)
            or (before != after and (selected is None or selected['run'] != pending['run']
                                     or selected['protocol'] != report['protocol']))):
        raise ExperimentError('policy transition selection/report mismatch')
    if before != after and selected is not None and selected.get('qualification') is not None:
        if selected['qualification'] != digest(encode(report)):
            raise ExperimentError('policy transition qualification/report mismatch')
    # An unchanged pointer may reference the earlier successful qualification.
    if previous is not None and selected is not None and previous['version'] != selected['version']:
        raise ExperimentError('policy transition version mismatch')
    run = material_path(state, pending['run'])
    if not run.is_dir():
        raise ExperimentError('missing policy transition run')
    for name, checksum in pending['materials'].items():
        if not hash_identity(checksum) or digest(material_path(run, name).read_bytes()) != checksum:
            raise ExperimentError('policy transition frozen material changed')
    protocol = json.loads(material_path(run, 'protocol.json').read_bytes())
    if protocol.get('fingerprint') != report['protocol']:
        raise ExperimentError('policy transition protocol mismatch')
    selection, target = state / 'enabled.json', run / 'report.json'
    current, observed = optional_bytes(selection), optional_bytes(target)
    final = encode(report)
    if current not in (before, after):
        raise ExperimentError('policy transition pointer conflict; preserve user edits')
    if observed not in (unblob(pending['report_before']), final):
        raise ExperimentError('policy transition report conflict; preserve user edits')
    if current != after:
        # Missing-to-missing is a no-op; disabling uses an explicit null-policy
        # record, never deletion of an already published pointer.
        if after is None:
            raise ExperimentError('policy transition cannot remove its pointer')
        atomic_bytes(selection, after)
    transition_fault('selection-published')
    if observed != final:
        atomic(target, report)
    transition_fault('report-published')
    (state / PENDING).unlink()
    directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    transition_fault('acknowledgement')
    return report


def recover_policy(state_path, abort_incomplete=False):
    state = Path(state_path)
    directory = policy_lock(state, True)
    try:
        if not os.path.lexists(state / PENDING):
            selected = enabled_policy(state)
            return {'status': 'clean', 'enabled': selected['policy'] if selected else None}
        pending = pending_policy(state)
        if pending['phase'] == 'evaluating' and abort_incomplete:
            run = material_path(state, pending['run'])
            incomplete = optional_bytes(run / 'report.json')
            if incomplete is None:
                raise ExperimentError('missing incomplete policy report')
            archive = material_path(run, 'report-interrupted.json')
            previous = optional_bytes(archive)
            if previous is not None and previous != incomplete:
                raise ExperimentError('incomplete policy report archive conflict')
            if previous is None:
                atomic_bytes(archive, incomplete)
            # This is quarantine after uncertainty, not a measured regression.
            # Keep the incomplete report and original pointer for later review.
            report = dict(pending['report'], status='interrupted-uncertain', enabled=None, within_budget=False,
                          recovery={'action': 'abort-incomplete',
                                    'previous_pointer': policy_record(state, unblob(pending['before'])),
                                    'incomplete_report': archive.name, 'incomplete_report_sha256': digest(incomplete)})
            materials = dict(pending['materials'], **{archive.name: digest(incomplete)})
            report = commit_policy(state, pending, report, materials)
        else:
            report = finish_policy_transition(state, pending)
        return {'status': 'recovered', 'enabled': report['enabled'],
                'report': str(state / report['run'] / 'report.json')}
    finally:
        os.close(directory)


def program_bytes(program):
    return program.archive() if isinstance(program, Bundle) else program


def load_protocol(path, project=None):
    path = Path(path).resolve()
    data = path.read_bytes()
    protocol = json.loads(data)
    required = {'version', 'baseline', 'candidate', 'grader', 'development', 'holdout',
                'minimum_pairs', 'minimum_cost_gain', 'quality_tolerance', 'trial_seconds', 'budget_seconds', 'calibration'}
    version = protocol.get('version') if isinstance(protocol, dict) else None
    if type(version) is int and version in (1, 2) and 'calibration' not in protocol:
        raise ExperimentError('calibration-required: declare good and bad output/expected fixtures before a new comparison; '
                              'existing archives remain readable and recoverable')
    fields = required.union({'entry'} if version == 2 else ())
    if (type(version) is not int or version not in (1, 2)
            or set(protocol) != fields):
        raise ExperimentError('unknown experiment protocol')
    minimum = protocol['minimum_pairs']
    if type(minimum) is not int or minimum < 6:
        raise ExperimentError('minimum_pairs must be at least 6')
    for name in ('minimum_cost_gain', 'quality_tolerance', 'trial_seconds', 'budget_seconds'):
        value = protocol[name]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ExperimentError('invalid ' + name)
    if not 0 < protocol['minimum_cost_gain'] < 1 or not protocol['trial_seconds'] or not protocol['budget_seconds']:
        raise ExperimentError('require a positive cost gain and bounded trial/run budgets')
    frozen = {str(path): data}

    def read(name):
        if not isinstance(name, str):
            raise ExperimentError('file names must be strings')
        candidate = (path.parent / name).resolve()
        if not candidate.is_relative_to(path.parent) or not candidate.is_file():
            raise ExperimentError('experiment files must be inside protocol directory')
        if str(candidate) in frozen:
            return frozen[str(candidate)]
        data = candidate.read_bytes()
        frozen[str(candidate)] = data
        return data

    programs = (checkpoint_programs(protocol, project) if version == 2 else
                {name: read(protocol[name]) for name in ('baseline', 'candidate')})
    programs['grader'] = read(protocol['grader'])
    if program_bytes(programs['baseline']) == program_bytes(programs['candidate']):
        raise ExperimentError('candidate has no behavioral version difference')
    phases, seen = {}, set()
    for phase in ('development', 'holdout'):
        cases = protocol[phase]
        if not isinstance(cases, list) or len(cases) < minimum:
            raise ExperimentError('insufficient paired cases in ' + phase)
        phases[phase] = []
        for case in cases:
            if not isinstance(case, dict) or set(case) != {'input', 'expected'}:
                raise ExperimentError('invalid case')
            task, expected = read(case['input']), read(case['expected'])
            expected.decode('utf-8')  # Invalid gold is a protocol error, not a worker failure.
            identity = digest(task)
            if identity in seen:
                raise ExperimentError('development/holdout task inputs must be distinct')
            seen.add(identity)
            phases[phase].append((identity, task, expected))
    if 'calibration' in protocol:
        calibration = protocol['calibration']
        if not isinstance(calibration, dict) or set(calibration) != {'good', 'bad'}:
            raise ExperimentError('calibration requires good and bad fixtures')
        known = set()
        phases['calibration'] = []
        for kind in ('good', 'bad'):
            cases = calibration[kind]
            if not isinstance(cases, list) or not cases:
                raise ExperimentError('calibration needs at least one ' + kind + ' fixture')
            for index, case in enumerate(cases):
                if not isinstance(case, dict) or set(case) != {'output', 'expected'}:
                    raise ExperimentError('invalid calibration fixture')
                output, expected = read(case['output']), read(case['expected'])
                identity = digest(encode([output.decode('utf-8'), expected.decode('utf-8')]))
                if identity in known:
                    raise ExperimentError('calibration fixtures must be distinct')
                known.add(identity)
                phases['calibration'].append((kind, index, output, expected))
    fingerprint = digest(encode({str(Path(name).relative_to(path.parent)): digest(data)
                                for name, data in sorted(frozen.items())}))
    return protocol, programs, phases, frozen, fingerprint


def run_program(program, stdin, deadline):
    """Measure from workspace preparation through owned-process cleanup."""
    with tempfile.TemporaryDirectory(prefix='goal-policy-trial-') as tmp:
        root = Path(tmp)
        work = root / 'work'
        work.mkdir()
        if isinstance(program, Bundle):
            for name, value in program.files.items():
                if value is not None:
                    path = work / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(base64.b64decode(value['bytes'], validate=True))
                    path.chmod(value['mode'])
            # -I excludes all implicit imports from the caller and the task.
            # Add only the explicitly materialized workspace and entry parent.
            invocation = ['-c', 'import os,runpy,sys; entry=sys.argv.pop(1); '
                          'sys.path[:0]=[os.path.dirname(entry),os.getcwd()]; '
                          'runpy.run_path(entry,run_name="__main__")', str(work / program.entry)]
        else:
            (work / 'policy.py').write_bytes(program)
            invocation = [str(work / 'policy.py')]

        def bound_files():
            soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
            cap = min([1024 * 1024] + [limit for limit in (soft, hard) if limit != resource.RLIM_INFINITY])
            resource.setrlimit(resource.RLIMIT_FSIZE, (cap, hard))

        bounded = Path(__file__).with_name('goal_bounded.py').resolve()
        receipt = root / 'receipt'
        env = os.environ.copy()
        env.pop('GOAL_RUNNER_FD', None)
        env['GOAL_RUNNER_MONOTONIC_END'] = str(deadline)
        with (root / 'stdin').open('w+b') as source, (root / 'stdout').open('w+b') as output, (root / 'stderr').open('w+b') as error:
            source.write(stdin)
            source.seek(0)
            if time.monotonic() >= deadline:
                return b'', None, 'timeout', ''
            completed = subprocess.run([sys.executable, '-I', str(bounded), '--owner', str(os.getpid()),
                                        '--receipt', str(receipt), '--', sys.executable, '-I', '-B', *invocation],
                                       cwd=work, stdin=source, stdout=output, stderr=error, env=env,
                                       start_new_session=True, preexec_fn=bound_files)
            output.seek(0)
            stdout = output.read(1024 * 1024 + 1)
            error.seek(0)
            stderr = error.read(4096).decode('utf-8', errors='replace')
        if completed.returncode or not receipt.is_file():
            return stdout, None, 'supervisor-failed', stderr
        rc = int(receipt.read_text(encoding='ascii'))
        reason = {124: 'timeout', 130: 'cancelled', 143: 'cancelled', 128 + signal.SIGXFSZ: 'output-limit'}.get(rc)
        return stdout, rc, reason, stderr


def trial(program, grader, task, expected, seconds, deadline):
    started = time.monotonic()
    trial_end = min(started + seconds, deadline)
    record = dict(ok=False, reason='run-budget', elapsed=None, score=None, output_sha256=None,
                  floor=None, horizon=None, tokens=None, money=None, regression=False)
    if started >= trial_end:
        return record, b''
    output, rc, reason, error = run_program(program, task, trial_end)
    record.update(reason=reason or ('worker-exit=%s' % rc if rc else None),
                  output_sha256=digest(output), stderr=error, worker_exit=rc,
                  regression=reason == 'output-limit' or (reason is None and rc != 0))
    if reason is None and rc == 0:
        try:
            request = encode({'output': output.decode('utf-8'), 'expected': expected.decode('utf-8')})
        except UnicodeError:
            record.update(reason='worker-output-not-utf8', regression=True)
        else:
            result, grade_rc, grade_reason, grade_error = run_program(grader, request, trial_end)
            record.update(grader_stdout=result[:4096].decode('utf-8', errors='replace'),
                          grader_sha256=digest(result), grader_exit=grade_rc, grader_stderr=grade_error)
            if grade_reason in ('timeout', 'cancelled'):
                record['reason'] = 'grader-' + grade_reason
            else:
                apply_grade(record, result, grade_rc, grade_reason)
    record['elapsed'] = time.monotonic() - started
    return record, output


def apply_grade(record, result, rc, reason):
    try:
        if rc or reason:
            raise ExperimentError('grader command failed')
        grade = json.loads(result)
        if (not isinstance(grade, dict) or set(grade) != {'floor', 'horizon', 'score'}
                or type(grade['floor']) is not bool or type(grade['horizon']) is not bool
                or type(grade['score']) not in (int, float) or not math.isfinite(grade['score'])):
            raise ExperimentError('invalid grader result')
        passed = grade['floor'] and grade['horizon']
        record.update(ok=passed, score=grade['score'], floor=grade['floor'], horizon=grade['horizon'],
                      reason=None if passed else 'floor-or-horizon', regression=not passed)
    except (ValueError, ExperimentError, OverflowError) as exc:
        record.update(reason='instrument-invalid', grader_error=str(exc))


def calibrate(grader, cases, seconds, deadline, run):
    """Test the actual grader on frozen known answers before running policies."""
    started = time.monotonic()
    rows = []
    for kind, index, output, expected in cases:
        record = dict(ok=False, floor=None, horizon=None, score=None)
        result, rc, reason, error = run_program(
            grader, encode({'output': output.decode('utf-8'), 'expected': expected.decode('utf-8')}),
            min(deadline, time.monotonic() + seconds))
        apply_grade(record, result, rc, reason)
        matched = record.get('reason') != 'instrument-invalid' and record['ok'] == (kind == 'good')
        name = 'calibration-%s-%s.out' % (kind, index)
        atomic_bytes(run / name, result)
        rows.append(dict(kind=kind, index=index, matched=matched, observed=record,
                         grader_exit=rc, reason=reason, stderr=error,
                         output=name, output_sha256=digest(result)))
        if not matched:
            break
    return dict(status='passed' if len(rows) == len(cases) and all(row['matched'] for row in rows)
                else 'failed', cases=rows, elapsed=time.monotonic() - started)


def compare(pairs, protocol, alpha=0.05):
    """Preregistered paired cost improvement with exact one-sided sign test."""
    if len(pairs) < protocol['minimum_pairs'] or any(not row[side]['ok'] for row in pairs for side in ('baseline', 'candidate')):
        return {'pass': False, 'reason': 'insufficient-or-ineligible-pairs'}
    quality_deltas = [row['candidate']['score'] - row['baseline']['score'] for row in pairs]
    quality = statistics.mean(quality_deltas)
    baseline = sum(row['baseline']['elapsed'] for row in pairs)
    candidate = sum(row['candidate']['elapsed'] for row in pairs)
    positive = sum(row['candidate']['elapsed'] < row['baseline']['elapsed'] for row in pairs)
    negative = sum(row['candidate']['elapsed'] > row['baseline']['elapsed'] for row in pairs)
    n = positive + negative
    probability = sign_probability(positive, n)
    reverse_probability = sign_probability(negative, n)
    quality_p = sign_probability(sum(delta < 0 for delta in quality_deltas),
                                 sum(delta != 0 for delta in quality_deltas))
    gain = (baseline - candidate) / baseline if baseline else 0
    passed = quality >= -protocol['quality_tolerance'] and gain >= protocol['minimum_cost_gain'] and probability <= alpha
    return {'pass': passed, 'reason': 'paired-cost-benefit' if passed else 'no-confirmed-benefit',
            'pairs': len(pairs), 'quality_delta': quality, 'cost_gain': gain,
            'regressed': ((quality < -protocol['quality_tolerance'] and quality_p <= alpha)
                          or (gain <= -protocol['minimum_cost_gain'] and reverse_probability <= alpha)),
            'one_sided_sign_p': probability, 'alpha': alpha,
            'quality_delta_sd': statistics.stdev(quality_deltas),
            'paired_seconds_sd': statistics.stdev(row['baseline']['elapsed'] - row['candidate']['elapsed'] for row in pairs),
            'baseline_seconds': baseline, 'candidate_seconds': candidate}


def sign_probability(positive, nonzero):
    return sum(math.comb(nonzero, k) for k in range(positive, nonzero + 1)) / 2 ** nonzero


def policy_record(state, data):
    if data is None:
        return None
    record = json.loads(data)
    fields = {'version', 'policy', 'program', 'run', 'protocol'}
    if (not isinstance(record, dict) or set(record) not in (fields, fields | {'qualification'})
            or type(record['version']) is not int or record['version'] not in (1, 2)
            or not hash_identity(record['run'], 32) or not hash_identity(record['protocol'])):
        raise ExperimentError('invalid enabled policy record')
    if 'qualification' in record and (record['policy'] is None or not hash_identity(record['qualification'])):
        raise ExperimentError('invalid policy qualification identity')
    identity = record['policy']
    suffix = '.py' if record['version'] == 1 else '.json'
    if (identity is not None and (not isinstance(identity, str) or len(identity) != 64
                                  or any(char not in '0123456789abcdef' for char in identity))
            or record['program'] != (None if identity is None else 'policies/' + identity + suffix)):
        raise ExperimentError('invalid enabled policy record')
    if identity is not None and digest(material_path(state, record['program']).read_bytes()) != identity:
        raise ExperimentError('corrupt archived policy')
    return record


def enabled_policy(state):
    return policy_record(state, optional_bytes(state / 'enabled.json'))


def qualified_policy(state, selected=None, with_report=False):
    """Validate the immutable qualification before consuming an active policy.

    Historical pointers remain readable for recovery. They do not silently
    acquire the guarantees of a newly calibrated, evidence-bound comparison.
    """
    selected = enabled_policy(state) if selected is None else selected
    if selected is None or selected['policy'] is None:
        return (selected, None) if with_report else selected
    if 'qualification' not in selected:
        raise ExperimentError('policy-requalification-required: compare the active archive with good/bad calibration and fresh holdout')
    try:
        run = material_path(state, selected['run'])
        raw = optional_bytes(run / 'report.json')
        if raw is None or digest(raw) != selected['qualification']:
            raise ExperimentError('policy-qualification-invalid: report checksum mismatch')
        report = json.loads(raw)
        if (not isinstance(report, dict) or report.get('version') != selected['version']
                or report.get('run') != selected['run'] or report.get('protocol') != selected['protocol']
                or report.get('enabled') != selected['policy']):
            raise ExperimentError('policy-qualification-invalid: selection/report mismatch')
        frozen = optional_bytes(run / 'protocol.json')
        if frozen is None or digest(frozen) != report['frozen_manifest_sha256']:
            raise ExperimentError('policy-qualification-invalid: frozen manifest changed')
        manifest = json.loads(frozen)
        source = Path(manifest['source'])
        if not source.is_absolute() or str(source) not in manifest['files']:
            raise ExperimentError('policy-qualification-invalid: missing frozen protocol source')
        hashes = {}
        for name, checksum in manifest['files'].items():
            relative = Path(name).relative_to(source.parent).as_posix()
            hashes[relative] = checksum
            if not hash_identity(checksum) or digest(material_path(run, 'frozen/' + relative).read_bytes()) != checksum:
                raise ExperimentError('policy-qualification-invalid: frozen material changed')
        if digest(encode(hashes)) != manifest['fingerprint'] or manifest['fingerprint'] != selected['protocol']:
            raise ExperimentError('policy-qualification-invalid: protocol fingerprint mismatch')
        protocol = manifest['protocol']
        calibration = report['calibration']
        expected = [(kind, index) for kind in ('good', 'bad') for index in range(len(protocol['calibration'][kind]))]
        if (calibration['status'] != 'passed' or not all(protocol['calibration'].values())
                or [(row['kind'], row['index']) for row in calibration['cases']] != expected):
            raise ExperimentError('policy-qualification-invalid: incomplete calibration')
        for row in calibration['cases']:
            if (row['matched'] is not True or row['observed']['ok'] != (row['kind'] == 'good')
                    or digest(material_path(run, row['output']).read_bytes()) != row['output_sha256']):
                raise ExperimentError('policy-qualification-invalid: calibration evidence changed')
        if selected['policy'] == report['policies']['candidate']:
            evaluation = report['holdout_evaluation']
            if (report['status'] != 'enabled' or report['within_budget'] is not True
                    or type(evaluation) is not int or evaluation < 1
                    or report['holdout_alpha'] != .05 / (evaluation * (evaluation + 1))):
                raise ExperimentError('policy-qualification-invalid: candidate not qualified')
            for phase in ('development', 'holdout'):
                value = report['phases'][phase]
                alpha = .05 if phase == 'development' else report['holdout_alpha']
                if (len(value['pairs']) != value['scheduled_pairs'] or value['scheduled_pairs'] != len(protocol[phase])
                        or not compare(value['pairs'], protocol, alpha)['pass']):
                    raise ExperimentError('policy-qualification-invalid: incomplete or ineligible pairs')
        else:
            rows = [pair for phase in report['phases'].values() for pair in phase['pairs']]
            if selected['policy'] != report['policies']['baseline'] or not rows or not all(pair['baseline']['ok'] for pair in rows):
                raise ExperimentError('policy-qualification-invalid: no verified fallback')
        return (selected, report) if with_report else selected
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ExperimentError('policy-qualification-invalid: ' + str(exc)) from exc


def run_enabled(state, seconds, stdin, with_identity=False, with_qualification=False):
    if not math.isfinite(seconds) or seconds <= 0:
        raise ExperimentError('execution budget must be positive and finite')
    end = run_deadline(time.monotonic() + seconds)
    state = Path(state)
    directory = policy_lock(state, False)
    try:
        require_settled(state)
        selected, qualification = qualified_policy(state, with_report=True)
        if selected is None or selected['policy'] is None:
            raise ExperimentError('no qualified policy enabled')
        program = material_path(state, selected['program']).read_bytes()
        if digest(program) != selected['policy']:
            raise ExperimentError('corrupt archived policy')
        if selected['version'] == 2:
            record = json.loads(program)
            program = Bundle(record['entry'], record['files'], record['context'])
            for name in program.files:
                if not name or '\\' in name or any(part in ('', '.', '..') for part in name.split('/')):
                    raise ExperimentError('invalid archived policy path')
            if program.files.get(program.entry) is None:
                raise ExperimentError('invalid archived policy entry')
        # Holding the reader lock through cleanup prevents a cooperating writer
        # from publishing a withdrawal while this execution is being released.
        result = run_program(program, stdin, end)
        if with_qualification:
            return (*result, selected, qualification)
        return (*result, selected) if with_identity else result
    finally:
        os.close(directory)


def run_deadline(local_end):
    outer = os.environ.get('GOAL_RUNNER_MONOTONIC_END')
    if outer:
        outer_end = float(outer)
        if not math.isfinite(outer_end):
            raise ExperimentError('invalid runner deadline')
        return min(local_end, outer_end)
    return local_end


def testing_budget(state):
    data = optional_bytes(state / 'statistical-budget.json')
    value = json.loads(data) if data is not None else {'version': 1, 'evaluations': 0}
    if (not isinstance(value, dict) or set(value) != {'version', 'evaluations'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['evaluations']) is not int or value['evaluations'] < 0):
        raise ExperimentError('invalid sequential testing budget')
    return value


def feedback(state_path, run_id):
    """Read-only repair guidance derived from a recorded run and current selection."""
    if not hash_identity(run_id, 32):
        raise ExperimentError('invalid feedback run identity')
    state = Path(state_path).resolve(strict=True)
    directory = policy_lock(state, False)
    try:
        require_settled(state)
        run = material_path(state, run_id)
        report = json.loads(optional_bytes(run / 'report.json'))
        protocol = json.loads(optional_bytes(run / 'protocol.json'))['protocol']
        if report['run'] != run_id:
            raise ExperimentError('feedback run/report mismatch')
        evaluation = testing_budget(state)['evaluations'] + 1
        alpha = .05 / (evaluation * (evaluation + 1))
        pairs = max(protocol['minimum_pairs'], math.ceil(-math.log2(alpha)))
        findings, decisions = [], {}
        for phase, value in report['phases'].items():
            decisions[phase] = value['decision']
            for index, pair in enumerate(value['pairs']):
                for side in ('baseline', 'candidate'):
                    row = pair[side]
                    if not row['ok'] and len(findings) < 4:
                        findings.append(dict(phase=phase, index=index, side=side, case=pair['case'],
                            reason=row.get('reason'), stderr=row.get('stderr', '')[:4096],
                            input=str(material_path(run, 'frozen/' + protocol[phase][index]['input'])),
                            output=str(run / ('%s-%s-%s.out' % (phase, index, side)))))
        calibration = report.get('calibration', {'status': 'not-declared', 'cases': []})
        selection = enabled_policy(state)
        historical = (selection['policy'] if selection else None) != report['enabled']
        if report['status'] == 'enabled' and selection is not None:
            historical |= selection['run'] != run_id or selection['protocol'] != report['protocol']
        qualification = dict(verified=True, reason=None)
        try:
            qualified_policy(state, selection)
        except ExperimentError as exc:
            qualification = dict(verified=False, reason=str(exc))
        next_action = ('repair-instrument' if report['status'] == 'instrument-invalid' else
                       'repair-candidate' if report['status'] == 'withdrawn' else
                       'repair-baseline' if report['status'] == 'blocked-no-qualified-policy' else
                       'increase-fresh-pairs' if any(d.get('reason') == 'holdout-underpowered' for d in decisions.values()) else
                       'monitor-enabled-policy' if report['status'] in ('enabled', 'retained-insufficient-counterevidence') else
                       'revise-candidate')
        return dict(run=run_id, status=report['status'], selection=selection,
                    selection_changed_since_run=historical,
                    calibration=dict(status=calibration['status'],
                                     failures=[row for row in calibration['cases'] if not row['matched']]),
                    qualification=qualification,
                    next_action='requalify-policy' if not qualification['verified'] else
                                'review-current-selection' if historical else next_action,
                    findings=findings, decisions=decisions,
                    next_holdout=dict(evaluation=evaluation, alpha=alpha, minimum_pairs=pairs,
                                      fresh_inputs_required=True,
                                      exposure_registry=str(state / 'used-holdout.json')))
    finally:
        os.close(directory)


def record_trial(run, phase, index, side, case_id, record, output):
    # Keep attempted results available even if the next trial or phase dies.
    (run / ('%s-%s-%s.out' % (phase, index, side))).write_bytes(output)
    with (run / 'trials.jsonl').open('ab') as log:
        log.write(encode(dict(phase=phase, index=index, side=side, case=case_id, result=record)) + b'\n')
        log.flush()
        os.fsync(log.fileno())


def instrument_failed(record):
    return record.get('reason') in ('instrument-invalid', 'supervisor-failed')


def disposition(report, identities, current, timely):
    incumbent = current['policy'] if current else None
    status = report['status']
    if status == 'instrument-invalid':
        return status, incumbent
    if status == 'holdout-validated' and timely:
        return 'enabled', identities['candidate']
    phases = report['phases'].values()
    rows = [pair for phase in phases for pair in phase['pairs']]
    baseline = identities['baseline'] if rows and all(row['baseline']['ok'] for row in rows) else None
    if incumbent == identities['candidate']:
        regressed = any(row['candidate'].get('regression') or row['candidate'].get('floor') is False
                        or row['candidate'].get('horizon') is False for row in rows)
        regressed |= any(phase['decision'].get('regressed', False)
                         and len(phase['pairs']) == phase['scheduled_pairs'] for phase in phases)
        if not regressed:
            return 'retained-insufficient-counterevidence', incumbent
        return ('withdrawn', baseline) if baseline else ('blocked-no-qualified-policy', None)
    if baseline is not None:
        return status if status != 'holdout-validated' else 'run-budget', baseline
    if incumbent is not None and not any(row['baseline'].get('regression') for row in rows):
        return 'retained-insufficient-counterevidence', incumbent
    return 'blocked-no-qualified-policy', None


def commit_policy(state, guard, report, materials):
    if pending_policy(state) != guard:
        raise ExperimentError('policy evaluation guard changed')
    before = unblob(guard['before'])
    current = policy_record(state, before)
    incumbent = current['policy'] if current else None
    after = before
    if report['status'] != 'instrument-invalid' and (current is None or incumbent != report['enabled'] or report['status'] == 'enabled'):
        identity = report['enabled']
        suffix = '.py' if report['version'] == 1 else '.json'
        record = {'version': report['version'], 'policy': identity,
                  'program': 'policies/' + identity + suffix if identity is not None else None,
                  'run': report['run'], 'protocol': report['protocol']}
        if identity is not None:
            record['qualification'] = digest(encode(report))
        after = encode(record)
    pending = dict(version=1, phase='transition', run=report['run'], before=blob(before), after=blob(after),
                   report_before=blob(optional_bytes(state / report['run'] / 'report.json')),
                   report=report, materials=materials)
    publish_pending(state, pending)
    transition_fault('transition-prepared')
    return finish_policy_transition(state, pending)


def experiment(protocol_path, state_path, project=None):
    started = time.monotonic()
    runner = Path(__file__).read_bytes()
    protocol, programs, phases, frozen, fingerprint = load_protocol(protocol_path, project)
    version = protocol['version']
    support = ['goal_bounded.py', 'goal_owner_watch.py', 'goal_trace.py']
    if version == 2:
        support.append('goal_store.py')
    runtime_sources = {Path(__file__).with_name(name): Path(__file__).with_name(name).read_bytes()
                       for name in support}
    deadline = run_deadline(started + protocol['budget_seconds'])
    state = Path(state_path)
    state.mkdir(parents=True, exist_ok=True)
    directory = policy_lock(state, True)
    try:
        require_settled(state)
        serialized = {name: program_bytes(program) for name, program in programs.items()}
        identities = {name: digest(data) for name, data in serialized.items()}
        before = optional_bytes(state / 'enabled.json')
        current = policy_record(state, before)
        if current is not None and current['version'] != version:
            raise ExperimentError('use a separate state directory for a different protocol version')
        if current is not None and current.get('policy') not in (None, identities['baseline'], identities['candidate']):
            raise ExperimentError('protocol does not compare the currently enabled policy')
        used_path = state / 'used-holdout.json'
        previous = json.loads(used_path.read_bytes()) if used_path.exists() else []
        if not isinstance(previous, list) or any(not isinstance(value, str) or len(value) != 64 for value in previous):
            raise ExperimentError('invalid holdout exposure registry')
        used = set(previous)
        holdout_ids = [case[0] for case in phases['holdout']]
        if used.intersection(holdout_ids):
            raise ExperimentError('holdout inputs already exposed; use fresh held-out tasks')
        budget_path = state / 'statistical-budget.json'
        testing = testing_budget(state)
        policies = state / 'policies'; policies.mkdir(exist_ok=True)
        suffix = '.py' if version == 1 else '.json'
        for name in ('baseline', 'candidate'):
            target = policies / (identities[name] + suffix)
            if target.exists() and target.read_bytes() != serialized[name]:
                raise ExperimentError('corrupt archived policy')
            if not target.exists():
                atomic_bytes(target, serialized[name])
        run_id = uuid.uuid4().hex
        run = state / run_id; run.mkdir()
        materials = {'runner.py': digest(runner)}
        (run / 'runner.py').write_bytes(runner)
        for source, data in runtime_sources.items():
            (run / source.name).write_bytes(data)
            materials[source.name] = digest(data)
        protocol_root = Path(protocol_path).resolve().parent
        for name, data in frozen.items():
            relative = Path('frozen') / Path(name).relative_to(protocol_root)
            copy = run / relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(data)
            materials[relative.as_posix()] = digest(data)
        protocol_record = {'protocol': protocol, 'fingerprint': fingerprint, 'source': str(Path(protocol_path).resolve()),
                           'files': {name: digest(data) for name, data in frozen.items()}}
        atomic(run / 'protocol.json', protocol_record)
        materials['protocol.json'] = digest(encode(protocol_record))
        report = {'version': version, 'run': run_id, 'protocol': fingerprint, 'policies': identities,
                  'runner_sha256': digest(runner), 'status': 'candidate', 'phases': {},
                  'frozen_manifest_sha256': materials['protocol.json'],
                  'runtime_sources': {path.name: digest(data) for path, data in runtime_sources.items()},
                  'runtime': {'python': sys.version, 'executable': sys.executable, 'platform': sys.platform},
                  'enabled': None, 'tokens': None, 'money': None}
        if version == 2:
            report['checkpoints'] = {side: protocol[side] for side in ('baseline', 'candidate')}
            report['context'] = programs['baseline'].context
            for side, identity in report['checkpoints'].items():
                snapshot = programs[side].snapshot
                if digest(snapshot) != identity:
                    raise ExperimentError('noncanonical artifact checkpoint')
                (run / ('checkpoint-' + side + '.json')).write_bytes(snapshot)
                materials['checkpoint-' + side + '.json'] = identity
        atomic(run / 'report.json', report)
        # Arm before trials: if even the later intent publication fails, a
        # measured regression cannot silently leave the old policy executable.
        guard = dict(version=1, phase='evaluating', run=run_id, before=blob(before),
                     report=json.loads(encode(report)), materials=dict(materials))
        publish_pending(state, guard)
        transition_fault('evaluating-published')
        def verify_frozen():
            if (Path(__file__).read_bytes() != runner
                    or any(not Path(name).is_file() or Path(name).read_bytes() != data
                           for name, data in {**frozen, **runtime_sources}.items())):
                report.update(status='instrument-invalid', elapsed=time.monotonic() - started,
                              enabled=current['policy'] if current else None)
                commit_policy(state, guard, report, materials)
                raise ExperimentError('frozen experiment material changed; report=' + str(run / 'report.json'))

        if time.monotonic() >= deadline:
            report.update(status='run-budget', elapsed=time.monotonic() - started, within_budget=False,
                          calibration=dict(status='not-executed', cases=[], reason='run-budget', elapsed=0))
            report['status'], report['enabled'] = disposition(report, identities, current, False)
            return commit_policy(state, guard, report, materials)
        report['calibration'] = calibrate(programs['grader'], phases['calibration'],
                                          protocol['trial_seconds'], deadline, run)
        materials.update({row['output']: row['output_sha256'] for row in report['calibration']['cases']})
        verify_frozen()
        if report['calibration']['status'] != 'passed':
            report.update(status='instrument-invalid', enabled=current['policy'] if current else None,
                          elapsed=time.monotonic() - started, within_budget=time.monotonic() <= deadline)
            return commit_policy(state, guard, report, materials)
        for phase in ('development', 'holdout'):
            cases = phases[phase]
            pairs = []
            alpha = 0.05
            if time.monotonic() >= deadline:
                report['status'] = 'run-budget'
                break
            if phase == 'holdout':
                evaluation = testing['evaluations'] + 1
                alpha = 0.05 / (evaluation * (evaluation + 1))
                if math.ldexp(1, -len(cases)) > alpha:
                    report['phases'][phase] = {
                        'scheduled_pairs': len(cases), 'pairs': [],
                        'decision': {'pass': False, 'reason': 'holdout-underpowered',
                                     'alpha': alpha, 'minimum_decisive_pairs': math.ceil(-math.log2(alpha))}}
                    report['status'] = 'holdout-rejected'
                    break
                atomic(budget_path, {'version': 1, 'evaluations': evaluation})
                report.update(holdout_evaluation=evaluation, holdout_alpha=alpha)
            # Conservatively reserve this phase's input IDs before dispatch.
            # Development may be repeated, but can never become new holdout.
            used.update(case[0] for case in cases)
            atomic(used_path, sorted(used))
            invalid = False
            for index, (case_id, task, expected) in enumerate(cases):
                if time.monotonic() >= deadline:
                    break
                pair = {'case': case_id}
                order = ('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')
                pair['order'] = order
                for side in order:
                    record, output = trial(programs[side], programs['grader'], task, expected,
                                           protocol['trial_seconds'], deadline)
                    pair[side] = record
                    record_trial(run, phase, index, side, case_id, record, output)
                    if instrument_failed(record):
                        invalid = True
                        other = order[1]
                        if other not in pair:
                            pair[other] = {'ok': False, 'reason': 'not-dispatched-instrument-invalid',
                                           'elapsed': None, 'score': None, 'tokens': None, 'money': None}
                        break
                pairs.append(pair)
                # Frozen source/inputs are checked after every pair; a worker
                # cannot win by quietly replacing the original evaluator.
                report['phases'][phase] = {'scheduled_pairs': len(cases), 'pairs': pairs,
                                          'decision': {'pass': False, 'reason': 'frozen-material-changed'}}
                verify_frozen()
                if any(not pair[side]['ok'] for side in ('baseline', 'candidate')):
                    break  # A failed pair cannot pass this phase.
            decision = compare(pairs, protocol, alpha=alpha)
            if decision['pass'] and len(pairs) != len(cases):
                decision.update({'pass': False, 'reason': 'incomplete-phase'})
            report['phases'][phase] = {'scheduled_pairs': len(cases), 'pairs': pairs, 'decision': decision}
            atomic(run / 'report.json', report)
            if invalid:
                report['status'] = 'instrument-invalid'
                break
            if not decision['pass']:
                report['status'] = 'rejected' if phase == 'development' else 'holdout-rejected'
                break
            report['status'] = 'local-reproduced' if phase == 'development' else 'holdout-validated'
        report['elapsed'] = time.monotonic() - started
        report['within_budget'] = started + report['elapsed'] <= deadline
        report['status'], selected = disposition(report, identities, current, report['within_budget'])
        report['enabled'] = selected
        return commit_policy(state, guard, report, materials)
    finally:
        os.close(directory)


def main(argv):
    if argv[:1] == ['feedback']:
        parser = argparse.ArgumentParser(description='Read recorded failures and the next fresh-holdout requirement')
        parser.add_argument('--state', required=True)
        parser.add_argument('--run', required=True)
        args = parser.parse_args(argv[1:])
        print(json.dumps(feedback(args.state, args.run)))
        return 0
    if argv[:1] == ['recover']:
        parser = argparse.ArgumentParser(description='Finish a recorded policy switch without replaying trials')
        parser.add_argument('--state', required=True)
        parser.add_argument('--abort-incomplete', action='store_true',
                            help='quarantine an interrupted evaluation by disabling its policy; never replay trials')
        args = parser.parse_args(argv[1:])
        print(json.dumps(recover_policy(args.state, args.abort_incomplete)))
        return 0
    if argv[:1] == ['run-enabled']:
        parser = argparse.ArgumentParser(description='Execute the enabled archive for this experiment scope')
        parser.add_argument('--state', required=True)
        parser.add_argument('--seconds', type=float, required=True)
        args = parser.parse_args(argv[1:])
        output, rc, reason, error = run_enabled(args.state, args.seconds, sys.stdin.buffer.read())
        sys.stdout.buffer.write(output)
        if error:
            sys.stderr.write(error)
        if reason:
            print('EVOLVE: ' + reason, file=sys.stderr)
        return 4 if rc is None else rc

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('protocol')
    parser.add_argument('--state', required=True)
    parser.add_argument('--project', help='project with the version 2 artifact checkpoints')
    arguments = parser.parse_args(argv)
    result = experiment(arguments.protocol, arguments.state, arguments.project)
    print(json.dumps({'status': result['status'], 'enabled': result['enabled'],
                      'elapsed': result['elapsed'], 'report': str(Path(arguments.state) / result['run'] / 'report.json'),
                      'feedback': feedback(arguments.state, result['run'])}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ExperimentError, OSError, ValueError, KeyError, TypeError) as exc:
        print('EVOLVE: ERROR ' + str(exc), file=sys.stderr)
        sys.exit(4)
