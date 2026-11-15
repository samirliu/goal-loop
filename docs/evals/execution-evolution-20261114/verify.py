#!/usr/bin/env python3
"""Reconstruct local evolution from archived outputs, without running policies."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location('independent_values', ROOT/'examples/evolution-dedupe/verify_agent.py')
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)
require, sha = evidence.require, evidence.sha


def verify_calibration(run, protocol, report):
    rows = report['calibration']['cases']
    fixtures = [(kind, index, case) for kind in ('good', 'bad')
                for index, case in enumerate(protocol['calibration'][kind])]
    require(len(rows) == len(fixtures), 'incomplete calibration')
    for row, (kind, index, fixture) in zip(rows, fixtures):
        require((row['kind'], row['index']) == (kind, index), 'calibration order mismatch')
        try:
            output = json.loads((run/'frozen'/fixture['output']).read_bytes())
            floor = output == json.loads((run/'frozen'/fixture['expected']).read_bytes())
            horizon = isinstance(output, list)
        except ValueError:
            floor = horizon = False
        grade = dict(floor=floor, horizon=horizon, score=int(floor))
        raw = run/row['output']
        require(sha(raw) == row['output_sha256'], 'calibration output hash mismatch')
        require(row['grader_exit'] == 0 and json.loads(raw.read_bytes()) == grade, 'calibration grader/oracle mismatch')
        require(all(row['observed'][key] == value for key, value in grade.items()), 'calibration observation mismatch')
        require(row['matched'] is True and (floor and horizon) == (kind == 'good'), 'calibration false pass')
    require(report['calibration']['status'] == 'passed', 'calibration not passed')


def verify(root):
    state = root/'agent-evolution/state'
    sequence = json.loads((root/'sequence.json').read_bytes())
    require([row['phase'] for row in sequence] == ['promotion', 'withdrawal', 'repair'], 'missing attempt')
    require([row['status'] for row in sequence] == ['enabled', 'withdrawn', 'enabled'], 'unexpected sequence')
    selected, pointer, evaluations, exposed = None, None, 0, set()
    pairs_total, transitions = 0, []
    for item in sequence:
        run = state/item['run']
        report = json.loads((run/'report.json').read_bytes())
        protocol = evidence.frozen_protocol(run, report, state)
        require(sha(run/'runner.py') == report['runner_sha256'], 'runner mismatch')
        for name, checksum in report['runtime_sources'].items():
            require(sha(run/name) == checksum, 'runtime source mismatch')
        verify_calibration(run, protocol, report)
        raw = [json.loads(line) for line in (run/'trials.jsonl').read_text().splitlines()]
        rows, decisions, count, elapsed = [], {}, 0, report['calibration']['elapsed']
        for phase in ('development', 'holdout'):
            if phase not in report['phases']:
                continue
            value = report['phases'][phase]
            require(value['scheduled_pairs'] == len(protocol[phase]), 'schedule mismatch')
            alpha = .05
            if phase == 'holdout':
                require(decisions['development']['pass_'], 'holdout without development')
                evaluations += 1
                alpha /= evaluations * (evaluations+1)
                require((report['holdout_evaluation'], report['holdout_alpha']) == (evaluations, alpha), 'testing budget reset')
                require(not exposed.intersection(sha(run/'frozen'/case['input']) for case in protocol[phase]), 'holdout reused')
            # The current runner reserves the whole dispatched phase, even
            # when its first counterexample stops subsequent trials.
            exposed.update(sha(run/'frozen'/case['input']) for case in protocol[phase])
            qualified = []
            for index, pair in enumerate(value['pairs']):
                case = protocol[phase][index]
                source = run/'frozen'/case['input']
                require(pair['case'] == sha(source), 'case hash mismatch')
                require(pair['order'] == (['baseline','candidate'] if index % 2 == 0 else ['candidate','baseline']), 'order mismatch')
                gold = evidence.oracle(json.loads(source.read_bytes())['items'])
                require(gold == json.loads((run/'frozen'/case['expected']).read_bytes()), 'bad gold')
                row = {}
                for side in ('baseline', 'candidate'):
                    record = pair[side]
                    output = run/('%s-%s-%s.out' % (phase, index, side))
                    require(sha(output) == record['output_sha256'], 'output hash mismatch')
                    events = [r for r in raw if (r['phase'],r['index'],r['side']) == (phase,index,side)]
                    require(len(events) == 1 and events[0]['result'] == record and events[0]['case'] == pair['case'], 'event mismatch')
                    if record['worker_exit'] == 0:
                        row[side] = evidence.qualify(record, output, gold)
                    else:
                        require(record['worker_exit'] == 1 and record['ok'] is False and record['regression'] is True,
                                'unconfirmed worker regression')
                        require(record['reason'] == 'worker-exit=1' and 'TypeError' in record['stderr'], 'missing failure evidence')
                        require(record['floor'] is None and record['horizon'] is None and record['score'] is None,
                                'failed worker was graded')
                        row[side] = dict(eligible=False, score=None, elapsed=record['elapsed'])
                    elapsed += record['elapsed']
                qualified.append(row)
            count += len(qualified)
            decisions[phase] = evidence.compare(qualified, protocol, alpha, value['scheduled_pairs'], value['decision'])
            rows.extend(qualified)
        require(len(raw) == count*2, 'missing failed trials')
        require(elapsed <= report['elapsed'] <= protocol['budget_seconds'] and report['within_budget'] is True, 'budget mismatch')
        status, policy = evidence.selection(selected, report['policies'], decisions, rows, True)
        require((status, policy) == (item['status'], report['enabled']), 'unjustified selection')
        if pointer is None or policy != selected:
            pointer = dict(version=1, policy=policy, program='policies/'+policy+'.py' if policy else None,
                           run=item['run'], protocol=report['protocol'])
        selected = policy
        transitions.append(dict(phase=item['phase'], status=status, pairs=count,
                                holdout_gain=decisions.get('holdout', {}).get('cost_gain')))
        pairs_total += count
    require(json.loads((state/'enabled.json').read_bytes()) == pointer, 'current selection mismatch')
    require(set(json.loads((state/'used-holdout.json').read_bytes())) == exposed, 'exposure registry mismatch')
    require(json.loads((state/'statistical-budget.json').read_bytes())['evaluations'] == evaluations == 2, 'statistical budget mismatch')
    later = json.loads((root/'later-task.json').read_bytes())
    require(later['worker_exit'] == 0 and later['selected'] == pointer, 'later task used different policy')
    require(json.loads((root/'later-task-output.json').read_bytes()) == evidence.oracle(
        json.loads((root/'later-task-input.json').read_bytes())['items']), 'later output mismatch')
    before = json.loads((root/'bad-grader-before-result.json').read_bytes())
    after = json.loads((root/'bad-grader-after-result.json').read_bytes())
    require(before['status'] == 'enabled' and before['enabled'] == before['policies']['candidate'], 'missing original counterexample')
    require(after['status'] == 'instrument-invalid' and after['enabled'] is None and not after['phases'], 'bad grader dispatched policies')
    bad = after['calibration']['cases'][-1]
    require(bad['kind'] == 'bad' and bad['matched'] is False and bad['observed']['ok'] is True, 'missing false-pass detection')
    return dict(verified=True, pairs=pairs_total, raw_outputs=pairs_total*2, exposed_inputs=len(exposed),
                holdout_evaluations=evaluations, transitions=transitions, later_task=True, bad_grader_stopped=True)


def main():
    archive = json.loads((HERE/'archive.json').read_bytes())
    require(sha(HERE/archive['file']) == archive['sha256'], 'archive checksum mismatch')
    benchmark = json.loads((HERE/'benchmark.json').read_bytes())
    for name, record in benchmark['cases'].items():
        rows = record['pairs']
        gain = 1-sum(row['after'] for row in rows)/sum(row['before'] for row in rows)
        require(math.isclose(gain, record['cost_gain']), 'benchmark aggregation mismatch: '+name)
        for label in ('before', 'after'):
            require(statistics.median(row[label] for row in rows) == record['median_seconds'][label], 'benchmark median mismatch')
    with tempfile.TemporaryDirectory(prefix='goal-evolution-replay-') as tmp:
        with tarfile.open(HERE/archive['file']) as bundle:
            bundle.extractall(tmp, filter='data')
        result = verify(Path(tmp))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
