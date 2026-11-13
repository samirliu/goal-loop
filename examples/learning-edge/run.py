#!/usr/bin/env python3
"""Small production-path demonstration; controlled policy trial telemetry.

No models or external harnesses. Unit checks and dispatch rejection are real.
Controlled trial costs test state transitions, not agent efficiency.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


crew = module('goal_crew')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def run(output):
    project = output/'project'; project.mkdir(parents=True)
    state = project/'.goal'
    def ctl(*args):
        result = subprocess.run(['bash', str(ROOT/'scripts/goal_ctl.sh'), *args, '--project', str(project)], capture_output=True, text=True)
        require(result.returncode == 0, result.stdout+result.stderr)
        return result.stdout
    ctl('init')
    (project/'verify.py').write_text('from pathlib import Path\nimport sys\n'
        'for n in (sys.argv[1:] or ["a", "b"]):\n'
        ' if Path(n+".out").read_bytes()!=Path(n+".in").read_bytes(): raise SystemExit(1)\n')
    for n in ('a', 'b'):
        (project/(n+'.in')).write_text(n.upper())
    (state/'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'
        '- AC-1 | both copies match input bytes | check: `python3 verify.py` | expected: exit=0\n\n'
        '## Approval\n\napproved: PENDING\n')
    ctl('stamp', '--auto', '--time-budget=120')
    proposals = state/'proposals'; proposals.mkdir()
    graph = proposals/'crew.json'
    value = dict(version=2, context={'workload':'two-copies'}, capacity=2,
        inputs=['a.in','b.in'], instruments=[str(project/'verify.py')],
        jobs=[dict(id='T'+str(i), files=[n+'.out'], inputs=[n+'.in'], deps=[],
                   check=[sys.executable, 'verify.py', n]) for i,n in enumerate(('a','b'),1)],
        final_check=[sys.executable, 'verify.py'])
    write(graph,value)
    def fresh(name, policy=None):
        return crew.Wave(project,crew.begin(project,graph,'crew',name,policy,retry_note='correct only failed copy from its named input'))
    def work(wave, task, name, bad=False):
        wave.event(task,'dispatch')
        (project/(name+'.out')).write_bytes(b'wrong' if bad else (project/(name+'.in')).read_bytes())
        wave.event(task,'returned',0)
        result=wave.validate(task)
        if result==0: wave.event(task,'adopt')
        return result
    first=fresh('first')
    require(work(first,'T1','a')==0,'good copy rejected')
    require(work(first,'T2','b',True)!=0,'bad copy passed')
    require(not first.finish()['quality'],'bad batch accepted')
    original=(project/'a.out').read_bytes()
    repaired=fresh('repair')
    reused=crew.load(repaired.path)['jobs']['T1']['reused_from']
    require(reused['wave']==first.path.stem,'good unit was not reused')
    require(work(repaired,'T2','b')==0,'repair failed')
    require(repaired.finish()['quality'] and (project/'a.out').read_bytes()==original,'repair destroyed accepted work')

    # The actual W5 raw report motivates a scoped serial candidate. It remains
    # a hypothesis; the controlled transition test below cannot qualify its utility.
    trigger=ROOT/'docs/evals/native-host/claude-haha/w5-headless-v3/report.json'
    baseline=b'import json\nprint(json.dumps(dict(match=False,choice="baseline",reason="incumbent")))\n'
    candidate=(b'# candidate\nimport json,sys\nv=json.load(sys.stdin)\n'
        b'm=v["context"].get("workload")=="two-copies" and len(v["jobs"])==2\n'
        b'print(json.dumps(dict(match=m,choice="serial" if m else "baseline",reason="scoped startup-cost hypothesis")))\n')
    write(proposals/'routing-candidate.json',dict(source=str(trigger.relative_to(ROOT)),
        source_sha256=hashlib.sha256(trigger.read_bytes()).hexdigest() if trigger.exists() else None,
        hypothesis='Avoid measured coordination overhead on two small independent units',
        scope='two-copies with two jobs', expected='less coordination with unchanged acceptance',
        falsifier='paired end-to-end cost does not improve or correctness regresses',
        rollback='fresh held-out regression', utility_status='unproven',
        candidate_sha256=hashlib.sha256(candidate).hexdigest()))
    engine=crew.evolution(); policy=proposals/'routing'
    def protocol(name, offset):
        folder=output/name;folder.mkdir()
        (folder/'baseline.py').write_bytes(baseline);(folder/'candidate.py').write_bytes(candidate)
        (folder/'grader.py').write_text('import json,sys\njson.load(sys.stdin)\nprint(json.dumps(dict(floor=True,horizon=True,score=1)))\n')
        config=dict(version=1,baseline='baseline.py',candidate='candidate.py',grader='grader.py',
                    development=[],holdout=[],minimum_pairs=6,minimum_cost_gain=.15,quality_tolerance=0,
                    trial_seconds=2,budget_seconds=30)
        for phase in ('development','holdout'):
            for i in range(6):
                name=phase+str(i)+'.json';write(folder/name,dict(task=offset+i+(100 if phase=='holdout' else 0)))
                config[phase].append(dict(input=name,expected=name))
        write(folder/'protocol.json',config)
        return folder/'protocol.json'
    def telemetry(program, grader, task, expected, seconds, deadline, regression=False):
        is_candidate=b'# candidate' in program
        failed=regression and is_candidate
        return dict(ok=not failed,elapsed=1 if is_candidate else 2,score=1,
                    floor=not failed,horizon=not failed,regression=failed), b'controlled transition observation'
    with mock.patch.object(engine,'trial',side_effect=telemetry):
        enabled=engine.experiment(protocol('enable',0),policy)
    require(enabled['status']=='enabled','controlled promotion failed')
    applied=fresh('learned',policy)
    require(crew.load(applied.path)['mode']=='inline','qualified decision did not affect dispatch')
    applied.event('T1','dispatch')
    blocked=False
    try: applied.event('T2','dispatch')
    except ValueError as e: blocked='capacity' in str(e)
    require(blocked,'serial decision was advisory only')
    (project/'a.out').write_bytes(original);applied.event('T1','returned',0)
    require(applied.validate('T1')==0,'unchanged first copy invalid');applied.event('T1','adopt')
    require(work(applied,'T2','b')==0,'second copy failed')
    require(applied.finish()['quality'],'learned wave failed')
    value['context']['fresh-observation']=True;write(graph,value)
    stale=fresh('prepared-before-withdrawal',policy)
    with mock.patch.object(engine,'trial',side_effect=lambda *a: telemetry(*a,regression=True)):
        withdrawn=engine.experiment(protocol('monitor',1000),policy)
    require(withdrawn['status']=='withdrawn','regression did not withdraw')
    refused=False
    try: stale.event('T1','dispatch')
    except ValueError as e: refused='policy changed' in str(e)
    require(refused,'withdrawn rule was consumed')
    after=fresh('after-withdrawal',policy)
    require(crew.load(after.path)['mode']=='crew','baseline routing not restored')
    for abandoned in (stale,after):
        for task in ('T1','T2'):
            abandoned.event(task,'cancel',note='observed plan superseded before dispatch; no worker was started')
        require(not abandoned.finish()['quality'],'cancelled plan became accepted work')
    audit=subprocess.run(['bash',str(ROOT/'scripts/goal_audit.sh'),'--project',str(project)],capture_output=True,text=True)
    require(audit.returncode==0,audit.stdout+audit.stderr)
    closed=ctl('close-iteration','--operation-id','demo-close-001','--task','T1','--files','a.out b.out',
        '--checks-pass','1','--checks-fail','0','--checks-unverifiable','0','--progress','yes','--exit-signal','yes',
        '--adversarial','clear','--adversarial-note','Exact-byte verifier rejected wrong b.out; repaired bytes and unchanged a.out independently checked')
    context=module('goal_context')
    receipt=context.receipt(project)
    require(receipt['completion_verified'],'final receipt refused completion')
    # Remove the separate manual entry calls, retaining both original checks.
    # This measures API ceremony, not model tokens or real agent speed.
    def separate_checks():
        return {name:subprocess.run(['bash',str(ROOT/'scripts'/script),*args,'--project',str(project)],
            capture_output=True,text=True).returncode for name,script,args in
            [('audit','goal_audit.sh',[]),('gate','goal_gate.sh',['--check'])]}
    separate_good=separate_checks()
    require(separate_good=={n:r['result'] for n,r in receipt['checks'].items()},'merged entry changed successful checks')
    saved=(project/'b.out').read_bytes();(project/'b.out').write_bytes(b'bad after acceptance')
    separate_bad=separate_checks();combined_bad=context.receipt(project)
    require(not combined_bad['completion_verified'] and separate_bad=={n:r['result'] for n,r in combined_bad['checks'].items()},
            'merged entry lost rejection of changed/bad accepted work')
    (project/'b.out').write_bytes(saved)
    receipt=context.receipt(project)
    require(receipt['completion_verified'],'restored accepted bytes did not reproduce GO')
    ablation=dict(separate_public_entries=2,combined_public_entries=1,deterministic_checks_in_both=2,
                  good=separate_good,bad=separate_bad,bad_combined={n:r['result'] for n,r in combined_bad['checks'].items()},
                  scope='entry API calls only; no model efficiency claim')
    write(output/'ablation.json',ablation)
    write(output/'receipt.json',receipt)
    result=dict(kind='mechanism demonstration with controlled policy trial telemetry',
        first_rejected=True,repair_dispatched=['T2'],reused=reused,serial_enforced=True,
        enabled=enabled['enabled'],withdrawn=withdrawn['enabled'],stale_dispatch_refused=True,
        final_gate=receipt['checks']['gate']['result'],ablation=ablation,agent_utility='unproven',tokens=None,money=None)
    write(output/'result.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    output=args.output or Path(tempfile.mkdtemp(prefix='goal-learning-example-',dir='/tmp'))
    output.mkdir(parents=True,exist_ok=True)
    print(json.dumps(dict(output=str(output),result=run(output)),sort_keys=True))
