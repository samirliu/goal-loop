#!/usr/bin/env python3
"""Measure two policy generations and optionally a counterexample/repair.

Candidates are explicit fixtures. No model, hidden retry or invented telemetry.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recursive_improve', ROOT/'scripts/goal_improve.py')
improve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(improve)

PREFIX = 'import json,sys\na=list(json.load(sys.stdin))\n'
BASELINE = PREFIX+'''for stop in range(len(a)-1,0,-1):
    for j in range(stop):
        if a[j]>a[j+1]: a[j],a[j+1]=a[j+1],a[j]
print(json.dumps(a))
'''
FIRST = PREFIX+'''for i in range(1,len(a)):
    value=a[i]; j=i-1
    while j>=0 and a[j]>value:
        a[j+1]=a[j]; j-=1
    a[j+1]=value
print(json.dumps(a))
'''
FAST = PREFIX+'print(json.dumps(sorted(a)))\n'
BAD_FAST = PREFIX+'print(json.dumps(sorted(set(a))))\n'
GRADER = '''import json,sys
value=json.load(sys.stdin)
try:
    actual=json.loads(value['output']); expected=json.loads(value['expected'])
    okay=isinstance(actual,list) and actual==expected
except (ValueError,TypeError): okay=False
print(json.dumps(dict(floor=okay,horizon=okay,score=int(okay))))
'''


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def run(output, counterexample=False):
    require(not output.exists(), 'choose a fresh --output directory')
    output.mkdir(parents=True)
    project = output/'project'; project.mkdir()
    ctl = ROOT/'scripts/goal_ctl.sh'

    def command(*args, expect=0):
        result = subprocess.run(['bash', str(ctl), *args, '--project', str(project)],
                                capture_output=True, text=True, timeout=30)
        (output/('controller-'+str(len(list(output.glob('controller-*.txt'))))+'.txt')).write_text(result.stdout+result.stderr)
        require(result.returncode == expect, 'controller command failed: '+result.stdout+result.stderr)
        return result

    command('init')
    ledger = project/'.goal'
    (project/'check.py').write_text('import json\nfrom pathlib import Path\n'
        'actual=json.loads(Path("answer.json").read_text())\n'
        'expected=sorted(json.loads(Path("production.json").read_text()))\nassert actual==expected\n')
    (ledger/'goal.md').write_text('# Goal\n\n## Objective\n\nSort the actual production input, retaining every occurrence.\n\n'
        '## Acceptance criteria\n\n- AC-1 | Actual production output equals the independent sorted input including duplicates | '
        'check: `python3 check.py` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
    (ledger/'work-plan.md').write_text('- [ ] T1 sorted production output | files=answer.json\n')
    command('stamp', '--auto')
    host = improve.module('goal_host')
    host.begin(project, 'example', 'recursive-policy-demo', 180)
    original_runner = (ledger/'runner.json').read_bytes()
    proposals = ledger/'proposals'; proposals.mkdir(exist_ok=True)
    rng = random.Random(71423)
    profile_input = list(range(3500)); rng.shuffle(profile_input)
    cap = improve.binding(project)[1]
    started = time.monotonic()
    data, rc, reason, _ = improve.engine.run_program(BASELINE.encode(), json.dumps(profile_input).encode(), min(cap, started+10))
    require(rc == 0 and reason is None and json.loads(data) == sorted(profile_input), 'baseline profile failed')
    trigger = ledger/'evidence/baseline-profile.json'
    trigger.write_text(json.dumps(dict(elapsed=time.monotonic()-started, input_size=len(profile_input), output_correct=True)))
    declaration = dict(version=1, scope='integer sorting tool', consumer='tool', state='.goal/proposals/policy',
        protocol=None, max_attempts=4, reserve_fraction=.25, intent='improve', trigger=None, hypothesis=None)
    records = []

    def propose(label, baseline, candidate, evidence, hypothesis, *, monitor=False, duplicates=False):
        folder = proposals/label; folder.mkdir()
        for name, source in [('baseline.py',baseline),('candidate.py',candidate),('grader.py',GRADER)]:
            (folder/name).write_text(source)
        for name, value in [('good.json',[1,1,2]),('bad.json',[1,2]),('gold.json',[1,1,2])]:
            (folder/name).write_text(json.dumps(value))
        protocol = dict(version=1, baseline='baseline.py', candidate='candidate.py', grader='grader.py',
            calibration={kind:[dict(output=kind+'.json',expected='gold.json')] for kind in ('good','bad')},
            minimum_pairs=6, minimum_cost_gain=.15, quality_tolerance=0, trial_seconds=5, budget_seconds=100)
        for phase in ('development','holdout'):
            protocol[phase] = []
            for index in range(8):
                values = list(range(rng.randrange(3300,3700)))
                if duplicates:
                    values += values[:350]
                rng.shuffle(values)
                name = phase+'-'+str(index)
                (folder/(name+'.json')).write_text(json.dumps(values))
                (folder/(name+'-gold.json')).write_text(json.dumps(sorted(values)))
                protocol[phase].append(dict(input=name+'.json',expected=name+'-gold.json'))
        source = folder/'protocol.json'; source.write_text(json.dumps(protocol,indent=2))
        declaration.update(protocol=source.relative_to(project).as_posix(), intent='monitor' if monitor else 'improve',
            trigger=dict(artifact=evidence.relative_to(project).as_posix(),sha256=improve.engine.digest(evidence.read_bytes()),
                         observation=hypothesis), hypothesis=hypothesis)
        (project/improve.CONFIG).write_text(json.dumps(declaration,indent=2))

    def evaluate(expected='enabled'):
        report = improve.evaluate(project)
        records.append(dict(run=report['run'],status=report['status'],improvement=report['improvement'],
                            decisions={k:v['decision'] for k,v in report['phases'].items()}))
        (output/'generations.json').write_text(json.dumps(records,indent=2))
        require(report['status'] == expected, 'comparison did not establish '+expected+'; retained raw evidence, no retry')
        return report, proposals/'policy'/report['run']/'report.json'

    def consume():
        values = [9,2,9,1,0,2,7]
        (project/'production.json').write_text(json.dumps(values))
        result, rc, reason, _ = improve.consume(project, 2, json.dumps(values).encode())
        require(rc == 0 and reason is None, 'active archive did not execute')
        (project/'answer.json').write_bytes(result)
        checked = subprocess.run([sys.executable,'-I',str(project/'check.py')],cwd=project,capture_output=True,text=True)
        return checked

    propose('generation-1',BASELINE,FIRST,trigger,'Measured baseline uses repeated adjacent passes; compare insertion passes.')
    improve.initialize(project)
    first, first_evidence = evaluate()
    require(consume().returncode == 0, 'first generation failed actual production work')
    fast = BAD_FAST if counterexample else FAST
    propose('generation-2',FIRST,fast,first_evidence,'Qualified insertion policy still does quadratic work; compare built-in sorting.')
    second, _ = evaluate()
    checked = consume()
    if counterexample:
        require(checked.returncode != 0, 'declared bad fixture did not expose its duplicate-loss defect')
        evidence = ledger/'evidence/actual-consumer-failure.json'
        evidence.write_text(json.dumps(dict(command='python3 check.py',exit=checked.returncode,
            stderr=checked.stderr,input=(project/'production.json').read_text(),output=(project/'answer.json').read_text())))
        propose('counterexample',FIRST,fast,evidence,'Actual production checker rejects lost duplicates; monitor and retain qualified fallback.',monitor=True,duplicates=True)
        _, withdrawal = evaluate('withdrawn')
        require(consume().returncode == 0, 'fallback failed actual production work')
        propose('repair',FIRST,FAST,withdrawal,'Retain every occurrence using direct sorting; retest fresh duplicate-bearing inputs.',duplicates=True)
        evaluate()
        require(consume().returncode == 0, 'repair failed actual production work')
    else:
        require(checked.returncode == 0, 'second generation failed actual production work')
    (ledger/'work-plan.md').write_text('- [x] T1 sorted production output | files=answer.json\n')
    final = command('close-iteration','--operation-id','recursive-demo-final','--task','T1','--files','answer.json',
        '--checks-from-verify','--progress','yes','--exit-signal','yes','--adversarial','clear',
        '--adversarial-note','Actual check.py compared consumed output with independent sorted production input including duplicates.', '--receipt')
    require('GATE: GO ' in final.stdout and '"completion_verified": true' in final.stdout, 'original Gate did not verify completion')
    require((ledger/'runner.json').read_bytes() == original_runner, 'experiment renewed the goal budget')
    result = dict(generations=records, actual_consumer_pass=True, completion_verified=True,
        original_budget_preserved=True, model_generation_tested=False, scope='local sorting execution policy',
        note='Candidates are fixtures; measured tool costs exclude model generation and do not establish general agent improvement.')
    (output/'report.json').write_text(json.dumps(result,indent=2))
    host.end(project,'recursive-policy-demo','example')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--counterexample',action='store_true')
    args=parser.parse_args()
    result=run(args.output.resolve(),args.counterexample)
    print(json.dumps(dict(output=str(args.output),statuses=[r['status'] for r in result['generations']],
                          completion_verified=result['completion_verified']),indent=2))


if __name__=='__main__':
    main()
