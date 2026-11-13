"""Recheck frozen paired outputs without importing the experiment runner."""
import hashlib
import json
import math
from pathlib import Path
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


root = Path(__file__).resolve().parent
with tarfile.open(root / 'raw-trials.tar.gz') as archive:
    def read(path):
        with archive.extractfile(path) as file:
            return file.read()

    reports = {}
    exposed = set()
    for member in archive.getnames():
        if not member.startswith('state/') or not member.endswith('/report.json'):
            continue
        run = member.removesuffix('/report.json')
        report = json.loads(read(member))
        protocol = json.loads(read(run + '/frozen/protocol.json'))
        snapshots = {}
        for side in ('baseline', 'candidate'):
            snapshot = read(run + '/checkpoint-' + side + '.json')
            assert sha(snapshot) == protocol[side] == report['checkpoints'][side]
            snapshots[side] = json.loads(snapshot)
            identity = report['policies'][side]
            policy = read('state/policies/' + identity + '.json')
            assert sha(policy) == identity
            assert json.loads(policy) == {'entry': protocol['entry'], 'context': report['context'],
                                          'files': snapshots[side]['files']}
        assert snapshots['candidate']['base'] == report['checkpoints']['baseline']
        assert snapshots['baseline']['context'] == snapshots['candidate']['context'] == report['context']
        for name, phase in report['phases'].items():
            decision = phase['decision']
            for index, pair in enumerate(phase['pairs']):
                case = protocol[name][index]
                assert sha(read(run + '/frozen/' + case['input'])) == pair['case']
                assert pair['case'] not in exposed
                exposed.add(pair['case'])
                expected = json.loads(read(run + '/frozen/' + case['expected']))
                for side in ('baseline', 'candidate'):
                    trial = pair[side]
                    raw = read(f'{run}/{name}-{index}-{side}.out')
                    assert sha(raw) == trial['output_sha256']
                    if trial['ok']:
                        assert json.loads(raw) == expected
                    else:
                        assert report['status'] == 'withdrawn' and side == 'candidate'
                        assert trial['worker_exit'] == 1 and 'unhashable type' in trial['stderr']
            if decision['pass']:
                pairs = phase['pairs']
                assert len(pairs) == len(protocol[name]) >= protocol['minimum_pairs']
                differences = [p['baseline']['elapsed'] - p['candidate']['elapsed'] for p in pairs]
                assert sum(differences) / sum(p['baseline']['elapsed'] for p in pairs) >= protocol['minimum_cost_gain']
                nonzero = sum(delta != 0 for delta in differences)
                wins = sum(delta > 0 for delta in differences)
                assert sum(math.comb(nonzero, k) for k in range(wins, nonzero + 1)) / 2 ** nonzero <= decision['alpha']
        reports[report['run']] = report
    assert len(reports) == 3 and len(exposed) == 41
    selected = json.loads(read('state/enabled.json'))
    final = reports[selected['run']]
    assert selected['policy'] == final['enabled'] == final['policies']['candidate']
    assert final['status'] == 'enabled' and final['holdout_evaluation'] == 2
    withdrawn, = (row for row in reports.values() if row['status'] == 'withdrawn')
    assert withdrawn['enabled'] == withdrawn['policies']['baseline'] and 'holdout' not in withdrawn['phases']
    print('PASS: 41 pairs, output/checkpoint hashes, ground truth, paired gains, withdrawal, final policy')
