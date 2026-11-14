#!/usr/bin/env python3
"""Reconstruct the recorded visual acceptance evidence without running the SUT.

No model, browser, NPM, policy or Gate is invoked. Image hashes establish
identity; semantic grades remain the recorded independent reviewer's judgments.
"""
import hashlib
import json
from pathlib import Path
import re
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(path):
    value = load(path)
    encoded = json.dumps(value['payload'],sort_keys=True,separators=(',', ':'),ensure_ascii=True).encode('ascii')
    require(hashlib.sha256(encoded).hexdigest()==value['sha256'], 'damaged observation: '+path.name)
    return value['payload']


def receipt(value):
    objects = [json.loads(line) for line in value['stdout'].splitlines() if line.startswith('{')]
    require(value['result']==0 and objects and objects[-1]['completion_verified'] is True, 'missing original acceptance receipt')
    checks = objects[-1]['checks']
    require(set(checks)=={'audit','gate'} and all(row['result']==0 for row in checks.values()), 'original acceptance did not pass')
    require('GATE: GO ' in checks['gate']['stdout'], 'missing original GO')
    return objects[-1]


def images(root, value, expected):
    require(set(value['views'])==set(expected), 'missing/extra reviewed view')
    hashes = set()
    for name,row in value['views'].items():
        require(sha(root/row['artifact'])==row['sha256'], 'substituted image: '+name)
        require(row['sha256'] not in hashes, 'one image substituted for different views')
        hashes.add(row['sha256'])
        require((root/row['artifact']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'missing PNG evidence')


def calibration(root, value):
    for suffix, expected in [('good','PASS'),('bad','FAIL')]:
        row = value['calibration']['AC-1#'+suffix]
        require(row['verdict']==expected and sha(root/row['artifact'])==row['sha256'], 'missing actual anchor grade')


def verify(root):
    manifest = load(root/'source-manifest.json')
    for name,row in manifest.items():
        require(sha(root/'source'/name)==row['sha256'], 'study source changed: '+name)
    for name,checksum in load(root/'case-manifest.json').items():
        require(sha(root/'case'/name)==checksum, 'original case changed: '+name)
        if not name.startswith(('original-goal/','reports/')):
            require(sha(root/'baseline-live'/name)==checksum, 'baseline did not use original source: '+name)
    baseline = root/'baseline-live'
    rows = load(root/'baseline-replay.json')
    require(len(rows)==3 and all(row['result']==0 for row in rows), 'baseline attempts omitted or failed')
    accepted = receipt(rows[-1])
    raw = (baseline/'.goal/evidence/raw/1.txt').read_text()
    observed = re.findall(r'^GATE: VERIFY (AC-[0-9]+)\|PASS\|exit=0$', raw, re.M)
    require(observed==['AC-'+str(n) for n in range(1,8)], 'baseline seven actual observations missing')
    spans = [envelope(p) for p in (baseline/'.goal/evidence/runtime').glob('*.json')]
    for identity in observed:
        actual = [row for row in spans if row['kind']=='measurement' and row['label']=='check:'+identity]
        require(len(actual)==3 and all(row['state']=='complete' and row['result']==0 and row['elapsed']>0 for row in actual),
                'actual supervised baseline check missing: '+identity)
    changed = load(root/'final-case-gates.json')
    require([row['project'] for row in changed]==['baseline-live','visual-flow-fixed'], 'case comparison omitted')
    require(changed[0]['result']==2 and 'quality-contract-required' in changed[0]['stderr'], 'weak original contract accepted')
    require(changed[1]['result']==0 and 'GATE: GO ' in changed[1]['stdout'], 'compliant case always rejected')

    # Independent semantic observations are read and bound, not recomputed
    # from pixel statistics by this data checker.
    forward = root/'forward-review';review = load(forward/'independent-quality-review.json')
    images(forward,review,['exterior','nave','dome','apse','gallery','minaret'])
    require(review['verdict']=='FAIL' and review['completion_eligible'] is False and len(review['findings'])==3,
            'original visual findings discarded')
    for name,checksum in load(forward/'input-manifest.json').items():
        require(sha(forward/name)==checksum, 'forward reviewer input changed')
    rejection = load(root/'actual-review-rejection.json')
    require(rejection['findings']==3 and 'quality-open-findings' in rejection['machine_rejection'], 'actual findings waived')
    first = root/'visual-flow';second = root/'visual-flow-fixed'
    failed = load(first/'.goal/evidence/cold-review.json');passed = load(second/'.goal/evidence/cold-review.json')
    for directory,value in [(first,failed),(second,passed)]:
        images(directory,value,['front','top','rear']);calibration(directory,value)
        captured = load(directory/'.goal/evidence/captured-views.json')
        require(captured=={name:{k:row[k] for k in ('artifact','sha256')} for name,row in value['views'].items()},
                'review did not use actual captured views')
    require(failed['verdict']=='FAIL' and failed['findings'] and failed['views']['rear']['verdict']=='FAIL', 'failed attempt omitted')
    require(passed['verdict']=='PASS' and passed.get('completion_eligible',True) is True and passed['findings']==[]
            and all(row['verdict']=='PASS' for row in passed['views'].values()), 'positive review did not pass every view')
    require(failed['views']['rear']['sha256']!=passed['views']['rear']['sha256'], 'regraded unchanged failed image')
    require((first/'.goal/goal.md').read_bytes()==(second/'.goal/goal.md').read_bytes(), 'rubric changed to obtain PASS')
    for name in ['good.png','near-miss.png']:
        require(sha(first/'references'/name)==sha(second/'references'/name), 'calibration changed to obtain PASS')
    current = load(root/'visual-flow-fixed-receipts.json')
    qualified = receipt(current[-1]);result = load(root/'visual-flow-fixed-result.json')
    require(result['cold_verdict']=='PASS' and result['completion_verified'] is True
            and result['receipt']==qualified and result['attempts_retained']==2, 'positive receipt summary changed')
    verdicts = (second/'.goal/verdicts.rec').read_text().splitlines()
    identity = re.search(r'GATE: GO digest=(\S+)',qualified['checks']['gate']['stdout'])[1]
    for label,status,file in [('AC-1','PASS','.goal/evidence/cold-review.json'),
                              ('AC-1#good','PASS','references/good.png'),('AC-1#bad','FAIL','references/near-miss.png')]:
        actual = [line for line in verdicts if line.startswith(label+'|')]
        require(len(actual)==1 and actual[0].split('|')[1:4]==[status,'1',identity]
                and file in actual[0] and sha(second/file) in actual[0], 'unbound actual cold verdict: '+label)
    one,two = load(first/'.goal/runner.json'),load(second/'.goal/runner.json')
    controls = load(root/'visual-flow-controls.json')
    require(one['origin']==two['origin'] and one['deadline']==two['deadline'], 'original epoch/origin reset')
    difference = two['monotonic']['deadline']-one['monotonic']['deadline']
    require(controls['monotonic_deadline_delta_seconds']==difference, 'monotonic difference concealed')
    require('time-budget-exhausted' in qualified['checks']['gate']['stdout'], 'bounded-settlement limitation concealed')
    stripe = load(root/'stripe-counterexample.json');v = stripe['verdict'];m = v['metrics']
    require(stripe['width']==96 and stripe['height']==64 and len(stripe['colors'])==4 and v['ok'] is True
            and m['stdLuma']>=.05 and m['contrast']>=.35 and m['edgeDensity']>=.008
            and m['brightFraction']>=.004 and m['darkFraction']<=.97 and m['goldFraction']>=.02,
            'original non-building counterexample missing')
    require(set(load(root/'full-test-source-delta.json')['changed'])=={
        'scripts/goal_quality.py','tests/docs_consistency.sh','tests/test_visual_quality.py'}, 'full-suite source delta concealed')
    return dict(verified=True,actual_baseline_checks=7,supervised_baseline_measurements=21,
        original_contract_now_rejected=True,original_case_reviewed_views=6,original_findings=3,
        actual_acceptance_attempts=2,failed_attempt_retained=True,final_actual_gate='GO',
        unchanged_rubric_and_anchors=True,epoch_deadline_and_origin_unchanged=True,
        monotonic_mapping_difference_seconds=difference,positive_uses_bounded_settlement=True,
        semantic_grades='observed independent model judgments, not established by hashes',
        scope='recorded acceptance cases; no native lifecycle or general quality/efficiency benchmark')


def main():
    index = load(HERE/'archive.json');path = HERE/index['file']
    require(sha(path)==index['sha256'] and path.stat().st_size==index['bytes'], 'raw archive checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='goal-visual-replay-') as tmp:
        with tarfile.open(path) as archive:
            archive.extractall(tmp,filter='data')
        result = verify(Path(tmp))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
