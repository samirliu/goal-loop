#!/usr/bin/env python3
"""Reconstruct recorded acceptance evidence without running the tested engine."""
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def need(value, message):
    if not value:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipts(record):
    result = []
    for line in record['stdout'].splitlines():
        if line.startswith('{'):
            row = json.loads(line)
            if 'completion_verified' in row:
                result.append(row)
    return result


def accepted(record):
    values = receipts(record)
    need(record['result'] == 0 and values and values[-1]['completion_verified'] is True,
         'missing actual successful completion receipt')
    checks = values[-1]['checks']
    need(set(checks) == {'audit', 'gate'} and all(x['result'] == 0 for x in checks.values())
         and 'GATE: GO ' in checks['gate']['stdout'], 'receipt did not run original acceptance')
    return values[-1]


def cases(root, folders):
    result = {}
    for folder in folders:
        for row in load(root/folder/'results.json'):
            need(row['case'] not in result, 'duplicated comparison case')
            commands = load(root/folder/row['case']/'commands.json')
            need(commands[-1]['result'] == row['result'], 'case summary disagrees with raw command')
            if row['accepted']:
                accepted(commands[-1])
            else:
                need(row['result'] == 2 and not any(x['completion_verified'] for x in receipts(commands[-1])),
                     'case marked refused without actual refusal')
            result[row['case']] = row
    return result


def verify(root):
    for name, row in load(root/'file-manifest.json').items():
        need(sha(root/name) == row['sha256'], 'raw evidence changed: '+name)
    for name, checksum in load(root/'validated-runtime-manifest.json').items():
        need(sha(root/'source'/name) == checksum, 'validated runtime differs from source snapshot: '+name)
    for platform, skipped in [('macos', 0), ('linux', 2)]:
        for group in ['full', 'focused', 'shell']:
            for run in load(root/('final-'+platform+'-'+group+'-checks.json')):
                need(run['result'] == 0, 'failed final validation command')
                raw = (root/run['log']).read_text()
                if group in ('full', 'focused'):
                    count = 454 if group == 'full' else 38
                    ending = 'OK (skipped=2)' if group == 'full' and skipped else 'OK'
                    need(re.search(r'^Ran '+str(count)+r' tests in [\d.]+s$', raw, re.M)
                         and raw.rstrip().endswith(ending), 'unverified final unittest result')
    before = cases(root, ['baseline-cases', 'baseline-extra-complete', 'quoted-baseline'])
    after = cases(root, ['final-v2-cases', 'final-v2-extra', 'quoted-after'])
    controls = {'calibration-positive', 'duplicate-ac-id-control'}
    need(set(before) == set(after) and len(before) == 17, 'comparison cases omitted')
    negatives = set(before)-controls
    need(len(negatives) == 15 and all(before[n]['accepted'] and not after[n]['accepted'] for n in negatives),
         'counterexample was not reproduced and then rejected')
    need(before['calibration-positive']['accepted'] and after['calibration-positive']['accepted']
         and not before['duplicate-ac-id-control']['accepted'] and not after['duplicate-ac-id-control']['accepted'],
         'positive or existing rejection control failed')
    need(before['judged-external-pending']['external_calls'] == '0'
         and int(after['judged-external-pending']['external_calls']) > 0, 'external query not actually exercised')
    need(before['external-cache-from-previous-artifact']['external_calls'] == '1'
         and after['external-cache-from-previous-artifact']['external_calls'] == '2', 'version cache did not remeasure')

    first = root/'forward';review = load(first/'independent-review.json')
    for name, checksum in review['artifact_sha256'].items():
        need(sha(first/name) == checksum, 'original independent input changed')
    with (first/'input.csv').open() as stream:
        nets = {r['region']: Decimal(r['revenue'])-Decimal(r['refund']) for r in csv.DictReader(stream)}
    need(nets == {'APAC': Decimal(100), 'EMEA': Decimal(80), 'AMER': Decimal(160)}
         and sum(nets.values()) == 340, 'source calculation changed')
    need(review['verdict'] == 'FAIL' and len(review['findings']) == 3
         and all(row['exit_code'] == 0 for row in review['checks_executed']), 'semantic counterexample discarded')

    forward = root/'forward-settlement';review = load(forward/'independent-review.json');live = root/'settlement-final'
    for name, checksum in load(forward/'input-manifest.json').items():
        need(sha(forward/name) == checksum, 'second independent input changed')
    for name in ['input.csv', 'report.md', 'anchors/good.md', 'anchors/near-miss.md']:
        need(sha(forward/name) == sha(live/name), 'unreviewed live artifact: '+name)
    need(sha(forward/'independent-review.json') == sha(live/'.goal/evidence/cold-review.json'), 'cold report rewritten')
    need(review['delivery_assessment']['current_delivery_requirements_satisfied'] is False
         and review['external_condition']['observed_state'] == 'PENDING', 'independent pending observation lost')
    rows = [review['content_judgments'][1], *review['calibration_judgments']]
    need([(r['id'], r['verdict']) for r in rows] == [('AC-2', 'PASS'), ('AC-2#good', 'PASS'), ('AC-2#bad', 'FAIL')],
         'actual independent content/calibration grades changed')
    commands = load(root/'settlement-final-commands.json');waiting = commands[-2];finished = accepted(commands[-1])
    need(waiting['result'] == 2 and receipts(waiting)[-1]['completion_verified'] is False
         and 'deferred-wait-not-counted' in waiting['stderr'], 'pending was delivered or penalized as a lie')
    result = load(root/'settlement-final-result.json')
    need(result['final_receipt'] == finished, 'positive receipt summary differs from actual output')
    digest = re.search(r'GATE: GO digest=(\S+)', finished['checks']['gate']['stdout'])[1]
    bound = [r.split('|') for r in (live/'.goal/verdicts.rec').read_text().splitlines()]
    for r in rows:
        binding = r['binding'];need(sha(live/binding['artifact']) == binding['digest'], 'actual grade hash mismatch')
        matches = [line for line in bound if line[0] == r['id']]
        need(len(matches) == 1 and matches[0][1:4] == [r['verdict'], '1', digest]
             and binding['evidence'] in matches[0][-1], 'actual cold verdict not bound by controller')
    state = dict(line.split('=', 1) for line in (live/'.goal/state.rec').read_text().splitlines())
    need(state['iteration'] == '1' and state['false_completes'] == '0', 'waiting reset/penalized the iteration')
    pending = load(live/'.goal/evidence/source-pending.json');settled = load(live/'.goal/evidence/reviewer-state.json')
    need(pending['state'] == 'PENDING' and settled['state'] == 'APPROVED'
         and pending['artifact_sha256'] == settled['artifact_sha256'] == sha(live/'report.md'), 'approval changed subject')
    spans = []
    for path in (live/'.goal/evidence/runtime').glob('*.json'):
        envelope = load(path);payload = envelope['payload']
        encoded = json.dumps(payload,sort_keys=True,separators=(',', ':'),ensure_ascii=True).encode('ascii')
        need(hashlib.sha256(encoded).hexdigest() == envelope['sha256'], 'damaged supervised observation')
        if payload.get('label') == 'external:AC-2':
            spans.append(payload)
    spans.sort(key=lambda r: r['start_monotonic'])
    need([r['result'] for r in spans] == [75,75,75,0]
         and all(r['state'] == 'complete' and r['elapsed'] > 0 for r in spans), 'actual external measurements missing')
    deadline = load(live/'.goal/runner.json')['monotonic']['deadline']
    need(all(r['start_monotonic']+r['elapsed'] < deadline for r in spans), 'controlled acceptance exceeded its recorded cap')
    return dict(verified=True,old_false_acceptances=15,current_refusals=15,positive_and_rejection_controls=2,
                independent_report_correct_total=340,actual_external_results=[75,75,75,0],
                final_completion_verified=True,semantic_scope='recorded source comparisons and actual independent observations; no universal semantic or native lifecycle guarantee')


def main():
    index = load(HERE/'archive.json');path = HERE/index['file']
    need(sha(path) == index['sha256'] and path.stat().st_size == index['bytes'], 'raw archive changed')
    with tempfile.TemporaryDirectory(prefix='goal-acceptance-replay-') as tmp:
        with tarfile.open(path) as archive:
            archive.extractall(tmp, filter='data')
        result = verify(Path(tmp))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
