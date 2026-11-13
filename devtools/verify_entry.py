#!/usr/bin/env python3
"""Legacy fixed-seed comparison B, both arms goal-loop; never a bare-host A."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def require(value,message):
    if not value:raise RuntimeError(message)


def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    prereg=read(root/'pre-registration.json')
    expected=[['before',911221],['after',911221],['after',911222],['before',911222]]
    require(prereg['order']==expected and prereg['maximum_calls']==4 and prereg['trial_seconds']==360
            and prereg['cli_seconds']==345 and prereg['maximum_turns']==80,'experiment protocol changed')
    require(sha(root/'frozen/grade.py')==prereg['grader_sha256'],'grader changed')
    require(sha(root/'frozen/tasks.py')==prereg['task_generator_sha256'],'task generator changed')
    sources=read(root/'source-hashes.json')
    for variant in ('before','after'):
        directory=root.parent/'sources'/variant/'goal-loop'
        actual={str(f.relative_to(directory)):sha(f) for f in directory.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
        require(actual==sources[variant],'frozen plugin source differs from pre-registration')
    combined=read(root/'report.json')['records']
    require(len(combined)==4,'incomplete pilot; retain every scheduled position')
    results=[]
    for position,(variant,seed) in enumerate(expected,1):
        trial=root/('%s-%s'%(position,variant));manifest=read(trial/'manifest.json');report=read(trial/'report.json')
        require(manifest['seed']==seed and manifest['seconds']==360 and manifest['cli_seconds']==345,'trial budget changed')
        require(sha(trial/'control/grade.py')==prereg['grader_sha256'],'trial grader differs')
        require(report=={k:v for k,v in combined[position-1].items() if k not in ('position','variant','seed')},'aggregate hides trial results')
        for name,digest in prereg['frozen_inputs'][str(seed)].items():
            if name=='solution.py':continue
            require(sha(trial/'work'/name)==digest,'frozen task input changed')
        calls={};errors=0;terminal=[]
        for line in (trial/'events.jsonl').read_text().splitlines():
            row=json.loads(line)
            require(manifest['entry']<=row['observed'],'event predates request')
            for block in row.get('content',[]):
                if block.get('type')=='tool_use' and block.get('id'):
                    require(block['id'] not in calls or calls[block['id']]==block,'conflicting tool identity')
                    calls[block['id']]=block
            errors+=sum(bool(r.get('is_error')) for r in row.get('results',[]))
            if row.get('type')=='result':terminal.append(row)
        require(report['tool_calls']==len(calls) and report['tool_errors']==errors,'tool counts do not match raw events')
        graded=subprocess.run([sys.executable,'-B',str(root/'frozen/grade.py'),'--project',str(trial/'work'),
            '--family','small','--seed',str(seed)],capture_output=True,text=True,timeout=15)
        plugin=root.parent/'sources'/variant/'goal-loop'
        replay={}
        for name,script,argv in [('audit','goal_audit.sh',[]),('gate','goal_gate.sh',['--check'])]:
            check=subprocess.run(['bash',str(plugin/'scripts'/script),*argv,'--project',str(trial/'work')],
                                 capture_output=True,text=True,timeout=12)
            replay[name]=dict(result=check.returncode,stdout=check.stdout,stderr=check.stderr)
        checks=report['checks']
        recorded=(set(checks)=={'independent','audit','gate'} and all(
            c.get('result')==0 and c.get('within_budget') and c.get('finished',float('inf'))<=manifest['entry']+360
            for c in checks.values()))
        if recorded:
            require('GATE: GO' in checks['gate']['stdout'],'gate result has no GO receipt')
        accepted=(recorded and graded.returncode==0 and all(c['result']==0 for c in replay.values()) and not report['inputs_changed'])
        require(report['accepted']==accepted,'unsupported acceptance claim')
        normal=report['cli_result']==0 and bool(terminal) and terminal[-1].get('subtype')=='success' and not terminal[-1].get('is_error') and terminal[-1].get('result_nonempty')
        require(report['normal_final_delivery']==normal,'unsupported final delivery claim')
        results.append(dict(position=position,variant=variant,seed=seed,accepted=accepted,
            normal_final_delivery=normal,tools=len(calls),tool_errors=errors,
            independent_replay_result=graded.returncode,cli_seconds=report['cli_elapsed'],
            final_checked_seconds=report['finished_elapsed'],posthoc_replay=replay))
    require(not any(read(root/'source-check.json').values()),'source changed during the pilot')
    pairs=[]
    for seed in (911221,911222):
        before=next(r for r in results if r['variant']=='before' and r['seed']==seed)
        after=next(r for r in results if r['variant']=='after' and r['seed']==seed)
        pairs.append(dict(seed=seed,tool_delta=after['tools']-before['tools'],
            checked_seconds_delta=after['final_checked_seconds']-before['final_checked_seconds']))
    totals={}
    for variant in ('before','after'):
        rows=[r for r in results if r['variant']==variant]
        count=sum(r['accepted'] for r in rows)
        wall=sum(r['final_checked_seconds'] for r in rows)
        totals[variant]=dict(attempted=len(rows),accepted=count,normal_deliveries=sum(r['normal_final_delivery'] for r in rows),
                             total_observed_wall_seconds=wall,all_trial_wall_per_accepted=wall/count if count else None)
    return dict(verified=True,scope='two held-out grading seeds of one task family; descriptive only',
        trials=results,pairs=pairs,totals=totals,accepted=sum(r['accepted'] for r in results),
        normal_deliveries=sum(r['normal_final_delivery'] for r in results),tokens=None,money=None)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args();result=verify(args.root.resolve())
    text=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='')
