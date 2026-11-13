#!/usr/bin/env python3
"""Independently reconstruct the recorded real-proposal experiment.

Reads archived bytes and raw outputs; deliberately does not import the
experiment runner or trust its pass/status fields without reconstruction.
The independent value oracle covers this fixture's integers, strings and
lists; it does not claim arbitrary Python-object equivalence.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys


class VerificationError(ValueError):
    """Recorded evidence does not establish the claimed result."""


def require(condition, message):
    # Evidence checks must remain active under -O and PYTHONOPTIMIZE.
    if not condition:
        raise VerificationError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def oracle(items):
    def valid(value):
        return type(value) in (int, str) or type(value) is list and all(valid(v) for v in value)
    require(all(valid(v) for v in items), 'oracle domain exceeded')
    seen, output = set(), []
    for value in items:
        key = json.dumps(value, sort_keys=True, separators=(',', ':'))
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def probability(wins, trials):
    return sum(math.comb(trials, k) for k in range(wins, trials+1)) / 2**trials


def frozen_protocol(run, report, state):
    frozen = json.loads((run/'protocol.json').read_bytes())
    protocol = frozen['protocol']
    require(protocol['version'] == report['version'] == 1, 'expected recorded Python-file protocol')
    originals = [Path(name) for name in frozen['files'] if Path(name).name == 'protocol.json']
    require(len(originals) == 1, 'ambiguous frozen protocol source')
    source = originals[0].parent
    files = {}
    for original, digest in frozen['files'].items():
        relative = Path(original).relative_to(source)
        require('..' not in relative.parts, 'unsafe frozen source path')
        name = relative.as_posix()
        require(sha(run/'frozen'/relative) == digest, 'frozen file hash mismatch: ' + name)
        files[name] = digest
    require(json.loads((run/'frozen/protocol.json').read_bytes()) == protocol, 'frozen protocol config mismatch')
    identity = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=True,
                                        separators=(',', ':')).encode('ascii')).hexdigest()
    require(identity == frozen['fingerprint'] == report['protocol'], 'protocol fingerprint mismatch')
    require(set(report['policies']) == {'baseline', 'candidate', 'grader'}, 'unexpected policy identities')
    for side in ('baseline', 'candidate', 'grader'):
        name = protocol[side]
        require(name in files, 'program absent from frozen manifest: ' + side)
        require(report['policies'][side] == files[name], side + ' policy does not match frozen program')
        if side != 'grader':
            archive = state/'policies'/(files[name]+'.py')
            require(sha(archive) == files[name], side + ' policy archive hash mismatch')
            require(archive.read_bytes() == (run/'frozen'/name).read_bytes(), side + ' policy archive bytes mismatch')
    require(report['policies']['baseline'] != report['policies']['candidate'], 'identical compared policies')
    inputs = []
    for phase in ('development', 'holdout'):
        require(len(protocol[phase]) >= protocol['minimum_pairs'], 'underpowered frozen phase')
        for case in protocol[phase]:
            require(set(case) == {'input', 'expected'} and all(name in files for name in case.values()), 'unfrozen case')
            inputs.append(files[case['input']])
    require(len(inputs) == len(set(inputs)), 'duplicate frozen case inputs')
    return protocol


def qualify(value, output, expected):
    """Rebuild this fixture's grade from the independent value oracle."""
    require(value['worker_exit'] == value['grader_exit'] == 0, 'unexpected failed recorded execution')
    try:
        observed = json.loads(output.read_bytes())
        floor, horizon = observed == expected, type(observed) is list
    except (ValueError, TypeError):
        floor = horizon = False
    grade = dict(floor=floor, horizon=horizon, score=int(floor))
    require(json.loads(value['grader_stdout']) == grade, 'grader output disagrees with value oracle')
    require(hashlib.sha256(value['grader_stdout'].encode()).hexdigest() == value['grader_sha256'], 'grader output hash mismatch')
    require(value['floor'] is floor and value['horizon'] is horizon and value['score'] == grade['score'], 'trial grade mismatch')
    eligible = floor and horizon
    require(value['ok'] is eligible and value['regression'] is (not eligible), 'trial eligibility mismatch')
    require(value['reason'] == (None if eligible else 'floor-or-horizon'), 'trial reason mismatch')
    require(type(value['elapsed']) in (int, float) and math.isfinite(value['elapsed']) and value['elapsed'] > 0,
            'invalid trial elapsed time')
    require(value['tokens'] is None and value['money'] is None, 'unexpected token or money measurement')
    return dict(eligible=eligible, score=grade['score'], elapsed=value['elapsed'])


def compare(pairs, protocol, alpha, scheduled, recorded):
    """Recompute both directions; a failed benefit test alone is no regression."""
    eligible = len(pairs) >= protocol['minimum_pairs'] and all(
        pair[side]['eligible'] for pair in pairs for side in ('baseline', 'candidate'))
    complete = len(pairs) == scheduled
    result = dict(pass_=False, regressed=False, complete=complete)
    if eligible:
        baseline = sum(pair['baseline']['elapsed'] for pair in pairs)
        candidate = sum(pair['candidate']['elapsed'] for pair in pairs)
        quality = [pair['candidate']['score'] - pair['baseline']['score'] for pair in pairs]
        wins = sum(pair['candidate']['elapsed'] < pair['baseline']['elapsed'] for pair in pairs)
        losses = sum(pair['candidate']['elapsed'] > pair['baseline']['elapsed'] for pair in pairs)
        forward, reverse = probability(wins, wins+losses), probability(losses, wins+losses)
        quality_p = probability(sum(delta < 0 for delta in quality), sum(delta != 0 for delta in quality))
        gain, delta = (baseline-candidate)/baseline, statistics.mean(quality)
        passed = delta >= -protocol['quality_tolerance'] and gain >= protocol['minimum_cost_gain'] and forward <= alpha
        regressed = ((delta < -protocol['quality_tolerance'] and quality_p <= alpha)
                     or (gain <= -protocol['minimum_cost_gain'] and reverse <= alpha))
        numbers = dict(cost_gain=gain, baseline_seconds=baseline, candidate_seconds=candidate,
                       quality_delta=delta, quality_delta_sd=statistics.stdev(quality),
                       paired_seconds_sd=statistics.stdev(pair['baseline']['elapsed']-pair['candidate']['elapsed']
                                                        for pair in pairs))
        for name, value in numbers.items():
            require(math.isclose(recorded[name], value), 'paired decision mismatch: ' + name)
        require(recorded['one_sided_sign_p'] == forward and recorded['alpha'] == alpha, 'paired sign test mismatch')
        require(recorded['pairs'] == len(pairs), 'paired count mismatch')
        result.update(pass_=passed and complete, regressed=regressed, cost_gain=gain,
                      one_sided_sign_p=forward, reverse_sign_p=reverse, quality_sign_p=quality_p)
    require(recorded['pass'] is result['pass_'], 'phase benefit decision mismatch')
    require(recorded.get('regressed', False) is result['regressed'], 'phase regression decision mismatch')
    return result


def selection(prior, identities, phases, rows, timely):
    """Derive the switch from qualified evidence, never report.status."""
    require(prior is None or prior in (identities['baseline'], identities['candidate']), 'prior policy not compared')
    development = phases.get('development', {}).get('pass_', False)
    holdout = phases.get('holdout', {}).get('pass_', False)
    if development and holdout and timely:
        return 'enabled', identities['candidate']
    baseline = identities['baseline'] if rows and all(row['baseline']['eligible'] for row in rows) else None
    if prior == identities['candidate']:
        regressed = any(not row['candidate']['eligible'] for row in rows)
        regressed |= any(phase['regressed'] and phase['complete'] for phase in phases.values())
        if regressed:
            return ('withdrawn', baseline) if baseline else ('blocked-no-qualified-policy', None)
        return 'retained-insufficient-counterevidence', prior
    if baseline is not None:
        status = 'rejected' if not development else 'holdout-rejected' if not holdout else 'run-budget'
        if development and 'holdout' not in phases:
            status = 'run-budget'
        return status, baseline
    if prior is not None and not any(not row['baseline']['eligible'] for row in rows):
        return 'retained-insufficient-counterevidence', prior
    return 'blocked-no-qualified-policy', None


def verify(root):
    state = root/'state'
    reports = []
    measured, previous = set(), set()
    total_pairs = 0
    for path in state.glob('*/report.json'):
        report = json.loads(path.read_bytes())
        reports.append((path.parent, report))
    require(len(reports) == 4, 'expected all four attempts, including withdrawal')
    # Use the archive's recorded order, not mutable filesystem mtimes or the
    # status/holdout fields whose consistency this verifier must establish.
    manifest = json.loads((root/'manifest.json').read_bytes())
    reports.sort(key=lambda item: manifest['files'][str((item[0]/'report.json').relative_to(root))]['mtime_ns'])
    holdouts, transitions = [], []
    prior, selected_record = None, None
    for run, report in reports:
        require(report['run'] == run.name, 'report run mismatch')
        protocol = frozen_protocol(run, report, state)
        require(sha(run/'runner.py') == report['runner_sha256'], 'runner hash mismatch')
        for name, digest in report['runtime_sources'].items():
            require(sha(run/name) == digest, 'runtime source hash mismatch: ' + name)
        raw = [json.loads(line) for line in (run/'trials.jsonl').read_text().splitlines()]
        pair_count, elapsed = 0, 0
        phases, qualified_rows = {}, []
        require(set(report['phases']) <= {'development', 'holdout'}, 'unexpected phase')
        for phase in ('development', 'holdout'):
            if phase not in report['phases']:
                continue
            if phase == 'holdout':
                require(phases.get('development', {}).get('pass_'), 'holdout without qualified development')
            record = report['phases'][phase]
            ids = []
            pairs = record['pairs']
            require(len(pairs) <= record['scheduled_pairs'] == len(protocol[phase]), 'phase schedule mismatch')
            qualified = []
            for index, pair in enumerate(pairs):
                case = protocol[phase][index]
                source = run/'frozen'/case['input']
                case_id = sha(source)
                require(case_id == pair['case'], 'case input hash mismatch')
                require(pair['order'] == (['baseline', 'candidate'] if index % 2 == 0 else ['candidate', 'baseline']),
                        'paired execution order mismatch')
                ids.append(case_id)
                expected = oracle(json.loads(source.read_bytes())['items'])
                require(expected == json.loads((run/'frozen'/case['expected']).read_bytes()),
                        'frozen expected output disagrees with value oracle')
                row = {}
                for side in ('baseline', 'candidate'):
                    value = pair[side]
                    output = run/('%s-%s-%s.out' % (phase, index, side))
                    require(sha(output) == value['output_sha256'], 'trial output hash mismatch')
                    row[side] = qualify(value, output, expected)
                    elapsed += row[side]['elapsed']
                    events = [r for r in raw if r['phase'] == phase and r['index'] == index and r['side'] == side]
                    require(len(events) == 1 and events[0]['case'] == case_id and events[0]['result'] == value,
                            'trial event ledger mismatch')
                qualified.append(row)
                pair_count += 1
            require(len(set(ids)) == len(ids), 'duplicate phase inputs')
            if phase == 'holdout':
                require(not previous.intersection(ids), 'reused exposed inputs')
                evaluation = report['holdout_evaluation']
                require(type(evaluation) is int and evaluation == len(holdouts)+1, 'holdout sequence mismatch')
                alpha = .05/(evaluation*(evaluation+1))
                require(report['holdout_alpha'] == alpha, 'holdout alpha mismatch')
                holdouts.append(evaluation)
            else:
                alpha = .05
            previous.update(ids); measured.update(ids)
            phases[phase] = compare(qualified, protocol, alpha, record['scheduled_pairs'], record['decision'])
            qualified_rows.extend(qualified)
        require(len(raw) == pair_count*2, 'raw trial count mismatch')
        total_pairs += pair_count
        require(math.isfinite(report['elapsed']) and elapsed <= report['elapsed'], 'invalid run elapsed time')
        require(type(report['within_budget']) is bool, 'invalid budget qualification')
        require(not report['within_budget'] or report['elapsed'] <= protocol['budget_seconds'], 'run exceeds frozen budget')
        status, selected = selection(prior, report['policies'], phases, qualified_rows, report['within_budget'])
        require((report['status'], report['enabled']) == (status, selected), 'policy transition mismatch: expected ' + status)
        transitions.append(dict(run=run.name, prior=prior, status=status, enabled=selected, phases=phases))
        if selected_record is None or selected != prior:
            selected_record = dict(version=1, policy=selected, program='policies/'+selected+'.py' if selected else None,
                                   run=run.name, protocol=report['protocol'])
        prior = selected
    require(set(json.loads((state/'used-holdout.json').read_bytes())) == measured, 'holdout exposure registry mismatch')
    require(holdouts == [1, 2, 3], 'holdout evaluations mismatch')
    require(json.loads((state/'statistical-budget.json').read_bytes())['evaluations'] == 3, 'statistical budget mismatch')
    selected = json.loads((state/'enabled.json').read_bytes())
    require(selected == selected_record, 'enabled pointer does not match reconstructed selection')
    require(selected['policy'] == sha(state/selected['program']), 'selected policy archive hash mismatch')
    original = json.loads((root/'frozen-before-proposal.json').read_bytes())
    require(all(sha(root/'initial'/name) == digest for name, digest in original.items()), 'pre-proposal frozen source mismatch')
    return dict(verified=True, attempts=4, pairs=total_pairs, raw_outputs=total_pairs*2,
                measured_inputs=len(measured), holdout_evaluations=holdouts, selected=selected['policy'],
                transitions=transitions)


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
